"""Independent web-protocol adapter. Original downloads only; no transfer/delete.

Public protocol references are recorded in review-evidence/ce2096. The two
providers share directory semantics, never a cookie jar or an account scope.
"""
import re
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .pan_accounts import PanError
from .pan_http import API, WEB, USER_AGENT, Session


def _text(value, limit=256):
    if (type(value) is not str or not 0 < len(value) <= limit
            or re.search(r'[\x00-\x1f\x7f]', value)):
        raise PanError('PAN_REPLY_INVALID')
    return value


def file_id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise PanError('PAN_FILE_ID_INVALID')
    return value


def file_entry(row):
    if (type(row) is not dict or type(row.get('file')) is not bool
            or type(row.get('size')) is not int or not 0 <= row['size'] < 2**63):
        raise PanError('PAN_REPLY_INVALID')
    return dict(file_id=file_id(row.get('fid')), name=_text(row.get('file_name'), 1024),
                size=row['size'], directory=not row['file'])


class Client:
    def __init__(self, provider, saved=None, session=None):
        if provider not in ('quark', 'uc'):
            raise PanError('PAN_PROVIDER_INVALID')
        self.provider = provider
        self.session = session if session is not None else Session(provider, saved)

    def _call(self, path, query=None, body=None):
        query = dict(query or {}, pr='ucpro' if self.provider == 'quark' else 'UCBrowser', fr='pc')
        value = self.session.request(API[self.provider] + '/1/clouddrive' + path, query, body)
        if (type(value.get('code')) is not int or value['code'] != 0
                or type(value.get('status')) is not int or value['status'] != 200):
            raise PanError('PAN_API_REJECTED')
        return value

    def _page(self, value, page, size):
        data, meta = value.get('data'), value.get('metadata')
        if (type(data) is not dict or type(data.get('list')) is not list
                or len(data['list']) > size or type(meta) is not dict
                or type(meta.get('_total')) is not int or not 0 <= meta['_total'] < 2**31):
            raise PanError('PAN_REPLY_INVALID')
        rows = [file_entry(row) for row in data['list']]
        if len({row['file_id'] for row in rows}) != len(rows):
            raise PanError('PAN_REPLY_INVALID')
        more = page * size < meta['_total']
        if more and not rows:
            raise PanError('PAN_REPLY_INVALID')
        return dict(items=rows, page=page, has_more=more)

    @staticmethod
    def _pagination(page, size):
        if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 20:
            raise PanError('PAN_PAGE_INVALID')

    def list_files(self, parent='0', page=1, size=10):
        self._pagination(page, size)
        value = self._call('/file/sort', dict(pdir_fid=file_id(parent), _page=page, _size=size,
            _fetch_total=1, fetch_all_file=1, _sort='file_type:asc,file_name:asc'))
        return self._page(value, page, size)

    def share_token(self, share_id, password=''):
        if type(password) is not str or not re.fullmatch(r'[A-Za-z0-9]{0,16}', password):
            raise PanError('PAN_SHARE_PASSWORD_INVALID')
        value = self._call('/share/sharepage/token', body=dict(pwd_id=file_id(share_id), passcode=password))
        data = value.get('data')
        if type(data) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        return _text(data.get('stoken'), 8192)

    def list_share(self, share_id, token, parent='0', page=1, size=10):
        self._pagination(page, size)
        value = self._call('/share/sharepage/detail', dict(pwd_id=file_id(share_id),
            stoken=_text(token, 8192), pdir_fid=file_id(parent), _page=page, _size=size,
            _fetch_total=1, _sort='file_type:asc,file_name:asc'))
        return self._page(value, page, size)

    def resolve_original(self, selected):
        # This internal result must go through an account-bound local stream,
        # never a Kodi URL with cookies, UI status, source card or history.
        if (type(selected) is not dict or set(selected) != {'file_id', 'name', 'size', 'directory'}
                or selected['directory'] is not False or type(selected['size']) is not int
                or selected['size'] <= 0):
            raise PanError('PAN_SELECTION_INVALID')
        file_id(selected['file_id'])
        _text(selected['name'], 1024)
        value = self._call('/file/download', body=dict(fids=[selected['file_id']]))
        rows = value.get('data')
        if type(rows) is not list or len(rows) != 1 or file_entry(rows[0]) != selected:
            raise PanError('PAN_FILE_CHANGED')
        url = _text(rows[0].get('download_url'), 16384)
        parsed = urlsplit(url)
        suffix = '.quark.cn' if self.provider == 'quark' else '.uc.cn'
        if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith(suffix)
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment):
            raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
        return dict(url=url, original=True, size=selected['size'], headers={
            'Cookie': self.session.cookie_header(url), 'Referer': WEB[self.provider] + '/',
            'User-Agent': USER_AGENT})


class QuarkLogin:
    """Official web QR. Poll only prepares credentials; Host separately commits."""
    def __init__(self, session=None, clock=time.monotonic, provider='quark'):
        if provider not in ('quark', 'uc'):
            raise PanError('PAN_PROVIDER_INVALID')
        self.provider = provider
        self.session = session if session is not None else Session(provider)
        self.clock, self.started, self.token, self.terminal = clock, 0, None, False

    def __repr__(self):
        return '<Cloud web QR login: token hidden>'

    def cancel(self):
        self.token, self.terminal = None, True

    def _request(self, operation, query=None):
        host = 'https://uop.quark.cn' if self.provider == 'quark' else 'https://api.open.uc.cn'
        client = '532' if self.provider == 'quark' else '381'
        return self.session.request(host + '/cas/ajax/' + operation,
            dict(query or {}, client_id=client, v='1.2', request_id=str(uuid4())))

    def begin(self):
        if self.token is not None or self.terminal:
            raise PanError('PAN_QR_FINISHED')
        value = self._request('getTokenForQrcodeLogin')
        if value.get('status') != 2000000:
            raise PanError('PAN_QR_UNAVAILABLE')
        try:
            self.token = _text(value['data']['members']['token'], 2048)
        except (KeyError, TypeError):
            raise PanError('PAN_REPLY_INVALID') from None
        self.started = self.clock()
        if self.provider == 'uc':
            return 'https://su.uc.cn/1_n0ZCv?' + urlencode(dict(token=self.token, client_id='381',
                uc_param_str='', uc_biz_str='S:custom|C:titlebar_fix'))
        return 'https://su.quark.cn/4_eMHBJ?' + urlencode(dict(token=self.token, client_id='532',
            ssb='weblogin', uc_param_str='', uc_biz_str='S:custom|OPT:SAREA@0|OPT:IMMERSIVE@1|OPT:BACK_BTN_STYLE@0'))

    def poll(self):
        if self.terminal or self.token is None:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')
        value = self._request('getServiceTicketByQrcodeToken', dict(token=self.token))
        status = value.get('status')
        if status == 50004001:
            return 'waiting', None
        if status in (50004002, 50004003, 50004004):
            self.cancel()
            raise PanError('PAN_QR_EXPIRED' if status == 50004002 else 'PAN_QR_CANCELLED')
        if status != 2000000:
            raise PanError('PAN_QR_POLL_RETRY')
        try:
            ticket = _text(value['data']['members']['service_ticket'], 4096)
        except (KeyError, TypeError):
            raise PanError('PAN_REPLY_INVALID') from None
        value = self.session.request(WEB[self.provider] + '/account/info', dict(st=ticket, lw='scan'))
        if value.get('success') is not True:
            raise PanError('PAN_QR_EXCHANGE_FAILED')
        # A read-only drive request both verifies access and collects refreshed
        # drive cookies. Neither the ticket nor remote user details cross IPC.
        Client(self.provider, session=self.session)._call('/member', dict(fetch_subscribe='false', fetch_identity='false'))
        saved = self.session.export()
        self.cancel()
        return 'ready', saved


class UCLogin(QuarkLogin):
    """UC's public browser client, not Juku's separate desktop-client identity."""
    def __init__(self, session=None, clock=time.monotonic):
        super().__init__(session=session, clock=clock, provider='uc')
