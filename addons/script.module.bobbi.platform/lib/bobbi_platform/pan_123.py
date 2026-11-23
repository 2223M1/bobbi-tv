"""123 web QR and read-only personal drive. No password, transfer or deletion.

The QR exchange is the public first-party web flow, not an Open API app secret.
Protocol observations are recorded separately from this independent code.
"""
import time
from urllib.parse import urlencode
from uuid import uuid4

from .pan_accounts import PanError
from .pan_http import Session, USER_AGENT
from .pan_tokens import decimal, identifier, listing, number, original_url, page_number, saved, text, token

AUTH = 'https://user.123pan.cn'
API = 'https://www.123pan.cn'
FILES = 'https://yun.123pan.com'
SIGN_IN = 'https://login.123pan.com'


def credentials(value):
    value = saved('123', value, {'provider', 'subject', 'access_token', 'device_id'})
    decimal(value['subject'])
    identifier(value['device_id'])
    return value['subject'], value


def data(value, codes=(0,)):
    if type(value.get('code')) is not int or value['code'] not in codes:
        raise PanError('PAN_LOGIN_REQUIRED' if value.get('code') in (401, 40101) else 'PAN_API_REJECTED')
    if type(value.get('data')) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    return value['data']


def entry(row):
    if type(row) is not dict or type(row.get('Type', 0)) is not int or row.get('Type', 0) not in (0, 1):
        raise PanError('PAN_REPLY_INVALID')
    directory = row.get('Type', 0) == 1 or number(row.get('Category', 0)) == 1
    result = dict(file_id=decimal(row.get('FileId')), name=text(row.get('FileName')),
        size=number(row.get('Size', 0 if directory else None)), directory=directory)
    if not result['directory']:
        result['etag'] = identifier(row.get('Etag'))
        result['storage_key'] = text(row['S3KeyFlag'], 256) if 'S3KeyFlag' in row else ''
    return result


class Client:
    def __init__(self, value, session=None):
        self.saved = credentials(value)[1]
        self.session = session if session is not None else Session('123')

    def __repr__(self):
        return '<123 drive: credentials hidden>'

    def _headers(self):
        return {'Authorization': 'Bearer ' + self.saved['access_token'], 'platform': 'web',
                'app-version': '3', 'loginuuid': self.saved['device_id']}

    def list_files(self, parent='0', page=1, size=10):
        page_number(page, size)
        value = data(self.session.request(FILES + '/b/api/file/list/new', query=dict(
            driveId=0, limit=size, next=0, orderBy='update_time', orderDirection='desc',
            parentFileId=decimal(parent), trashed='false', SearchData='', Page=page,
            OnlyLookAbnormalFile=0, event='homeListFile', operateType=1,
            inDirectSpace='false', fileCategory=0, isSearchOrder='false'), headers=self._headers()), codes=(0, 200))
        rows = value.get('InfoList')
        if type(rows) is not list:
            raise PanError('PAN_REPLY_INVALID')
        total = value['Total'] if 'Total' in value else (page - 1) * size + len(rows) + (1 if len(rows) == size else 0)
        result = listing(rows, total, page, size, entry)
        for item in result['items']:
            if not item['directory']:
                item['listing'] = dict(parent=parent, page=page, size=size)
        return result

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'name', 'size', 'directory', 'etag', 'storage_key', 'listing'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        # Query the current exact file before requesting its original URL. A
        # stale listing or changed hash is not authority to play another file.
        fid = decimal(selected['file_id'])
        number(selected['size'], 1)
        location = selected['listing']
        if type(location) is not dict or set(location) != {'parent', 'page', 'size'}:
            raise PanError('PAN_SELECTION_INVALID')
        rows = self.list_files(**location)['items']
        matches = [r for r in rows if r['file_id'] == fid]
        if len(matches) != 1 or matches[0] != selected:
            raise PanError('PAN_FILE_CHANGED')
        body = dict(
            driveId=0, fileId=int(fid), fileName=selected['name'], etag=selected['etag'],
            size=selected['size'], type=0)
        if selected['storage_key']:
            body['s3keyFlag'] = selected['storage_key']
        value = data(self.session.request(API + '/a/api/file/download_info', body=body, headers=self._headers()))
        # No decoding redirect wrappers, spoofed Android route or VIP bypass.
        url = original_url(value.get('DownloadUrl'), ('123pan.cn', '123pan.com', '123684.com', '123865.com'))
        return dict(url=url, size=selected['size'], original=True,
                    headers={'User-Agent': USER_AGENT, 'Referer': 'https://yun.123pan.cn/'})


class Login:
    def __init__(self, session=None, clock=time.monotonic):
        self.session = session if session is not None else Session('123')
        self.clock, self.started, self.terminal = clock, 0, False
        self.device, self.qr_id, self.phase, self.access = uuid4().hex, None, 'new', None

    def __repr__(self):
        return '<123 QR: credentials hidden>'

    def cancel(self):
        self.terminal, self.qr_id, self.access = True, None, None

    def _headers(self):
        return {'platform': 'web', 'app-version': '3', 'loginuuid': self.device,
                'Origin': AUTH, 'Referer': AUTH + '/centerlogin'}

    def _check_active(self):
        if self.terminal:
            self.cancel()
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 120:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')

    def begin(self):
        if self.terminal or self.phase != 'new':
            raise PanError('PAN_QR_FINISHED')
        self.started = self.clock()
        value = data(self.session.request(AUTH + '/api/user/qr-code/generate',
            headers=self._headers()))
        self._check_active()
        qr_id = identifier(value.get('uniID'))
        url = value.get('url')
        # Never show a server-selected phishing QR or an unrelated login page.
        if url not in ('https://yun.123pan.cn/wx-app-login.html',
                       'https://www.123684.com/wx-app-login.html'):
            raise PanError('PAN_QR_ORIGIN_REJECTED')
        self.qr_id, self.phase = qr_id, 'waiting'
        return url + '?' + urlencode(dict(env='production', uniID=qr_id, source='123pan', type='login'))

    def poll(self):
        if self.terminal or self.qr_id is None:
            raise PanError('PAN_QR_FINISHED')
        self._check_active()
        if self.phase in ('waiting', 'confirm'):
            reply = self.session.request(AUTH + '/api/user/qr-code/result',
                query={'uniID': self.qr_id}, headers=self._headers())
            self._check_active()
            value = data(reply, codes=(0, 200))
            status = 3 if reply['code'] == 200 else value.get('loginStatus')
            if type(status) is not int:
                raise PanError('PAN_QR_STATE_INVALID')
            if status in (0, 1):
                if status == 1:
                    self.phase = 'confirm'
                return 'waiting', None
            if status == 2:
                self.cancel()
                raise PanError('PAN_QR_FINISHED')
            if status != 3:
                raise PanError('PAN_QR_STATE_INVALID')
            platform = value.get('login_type', 4) if reply['code'] == 200 else value.get('scanPlatform')
            if reply['code'] == 200 and platform == 0:
                platform = 4
            if type(platform) is not int or platform not in (4, 7):
                raise PanError('PAN_QR_STATE_INVALID')
            if platform == 7:
                self.access, self.phase = token(value.get('token')), 'identity'
            else:
                self.phase = 'exchange'
        if self.phase == 'exchange':
            try:
                value = data(self.session.request(AUTH + '/api/user/qr-code/wx_code',
                    body={'uniID': self.qr_id}, headers=self._headers()))
                self._check_active()
                code = token(value.get('wxCode'))
                value = data(self.session.request(SIGN_IN + '/api/user/sign_in', body={
                    'from': 'web', 'wechat_code': code, 'type': 4}, headers={
                    'app-version': '43', 'Origin': SIGN_IN,
                    'Referer': SIGN_IN + '/centerlogin?redirect_url=https%3A%2F%2Fwww.123684.com&source_page=website'}))
                self._check_active()
                self.access, self.phase = token(value.get('token')), 'identity'
            except PanError:
                # An ambiguous exchange must not replay a one-use code. A new
                # QR is safe; retrying the identity read below is also safe.
                self.cancel()
                raise
        # Retain exchange result privately if this read times out: never
        # re-consume a one-use WeChat code on the next poll.
        self._check_active()
        value = data(self.session.request('https://api.123pan.cn/b/api/user/info',
            headers={'Authorization': 'Bearer ' + self.access, 'platform': 'web', 'app-version': '3'}))
        self._check_active()
        subject = decimal(value.get('UID'))
        if subject == '0':
            raise PanError('PAN_CREDENTIALS_INVALID')
        result = credentials(dict(provider='123', subject=subject, access_token=self.access, device_id=self.device))[1]
        self.cancel()
        return 'ready', result
