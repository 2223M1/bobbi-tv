"""Tianyi web QR and read-only personal drive. No borrowed app secret.

QR field/state protocol: official App.7bf19c91.js, 2026-11-09. Every SSO
redirect is checked locally; no arbitrary server-provided URL is followed.
"""
import base64
from datetime import datetime, timedelta, timezone
import time
from urllib.parse import parse_qsl, quote, urlsplit

from .pan_accounts import PanError
from .pan_http import Session, USER_AGENT
from .pan_tokens import decimal, listing, number, original_url, page_number, text

AUTH = 'https://open.e.189.cn/api/logbox/oauth2/'
API = 'https://cloud.189.cn'
HANDOFFS = {
    API + '/api/portal/loginUrl.action',
    'https://open.e.189.cn/api/logbox/separate/web/index.html',
    'https://open.e.189.cn/api/logbox/oauth2/separate/auth/unifyAccountLogin.do',
    API + '/api/portal/callbackUnify.action', API + '/web/redirect.html',
    API + '/web/main', API + '/main.action',
}


def split_handoff(value):
    text(value, 16384)
    parsed = urlsplit(value)
    base = parsed.scheme + '://' + parsed.netloc + parsed.path
    if (base not in HANDOFFS or parsed.username or parsed.password or parsed.fragment):
        raise PanError('PAN_REDIRECT_REJECTED')
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if len(pairs) > 24 or len(dict(pairs)) != len(pairs):
        raise PanError('PAN_REDIRECT_REJECTED')
    return base, dict(pairs)


def follow(session, url):
    for _ in range(5):
        base, query = split_handoff(url)
        _, status, target = session.request_raw(base, query=query, metadata=True)
        if status == 200:
            return base, query
        if status not in (301, 302, 303, 307, 308):
            raise PanError('PAN_REDIRECT_REJECTED')
        url = target
    raise PanError('PAN_REDIRECT_REJECTED')


def checked(value):
    if value.get('errorCode') == 'InvalidSessionKey':
        raise PanError('PAN_LOGIN_REQUIRED')
    if type(value.get('res_code')) is not int or value['res_code'] != 0:
        raise PanError('PAN_API_REJECTED')
    return value


class Login:
    def __init__(self, session=None, clock=time.monotonic, wall_clock=time.time):
        self.session = session if session is not None else Session('189')
        self.clock, self.wall_clock = clock, wall_clock
        self.config = self.uuid = self.encrypted = self.redirect = self.brief = None
        self.started, self.terminal = 0, False

    def __repr__(self):
        return '<Tianyi QR: cookies and tickets hidden>'

    def cancel(self):
        self.terminal = True
        self.config = self.uuid = self.encrypted = self.redirect = self.brief = None

    def begin(self):
        if self.terminal or self.config is not None:
            raise PanError('PAN_QR_FINISHED')
        base, query = follow(self.session, API + '/api/portal/loginUrl.action?redirectURL=' +
                             quote(API + '/web/redirect.html', safe=''))
        if base != 'https://open.e.189.cn/api/logbox/separate/web/index.html':
            raise PanError('PAN_QR_UNAVAILABLE')
        lt, reqid, appid = (text(query.get(k), 4096) for k in ('lt', 'reqId', 'appId'))
        headers = {'Lt': lt, 'Reqid': reqid, 'Referer': base}
        conf = self.session.request(AUTH + 'appConf.do', form=dict(version='2.0', appKey=appid), headers=headers)
        if conf.get('result') != '0' or type(conf.get('data')) is not dict:
            raise PanError('PAN_QR_UNAVAILABLE')
        conf = conf['data']
        if type(conf.get('isOauth2')) is not bool or conf.get('clientType') != 1:
            raise PanError('PAN_REPLY_INVALID')
        split_handoff(conf.get('returnUrl'))
        for key in ('reqId', 'appKey', 'paramId'):
            text(conf.get(key), 4096)
        value = self.session.request(AUTH + 'getUUID.do', form={'appId': conf['appKey']}, headers=headers)
        if type(value.get('result')) is not int or value['result'] != 0:
            raise PanError('PAN_QR_UNAVAILABLE')
        uuid, encrypted, encoded = (text(value.get(key), 4096) for key in ('uuid', 'encryuuid', 'encodeuuid'))
        raw = self.session.request_raw(AUTH + 'image.do', query=dict(uuid=encoded, REQID=conf['reqId']), limit=8192)
        if (len(raw) < 33 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR'
                or not 32 <= int.from_bytes(raw[16:20], 'big') <= 1024
                or not 32 <= int.from_bytes(raw[20:24], 'big') <= 1024):
            raise PanError('PAN_QR_IMAGE_INVALID')
        self.config, self.uuid, self.encrypted, self.started = conf, uuid, encrypted, self.clock()
        return {'png': base64.b64encode(raw).decode('ascii')}

    def poll(self):
        if self.terminal or self.config is None:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')
        conf = self.config
        if self.redirect is None:
            stamp = self.wall_clock()
            date = datetime.fromtimestamp(stamp, timezone(timedelta(hours=8))).strftime('%Y-%m-%d%H:%M:%S') + '0'
            value = self.session.request(AUTH + 'qrcodeLoginState.do', form=dict(
                appId=conf['appKey'], encryuuid=self.encrypted, uuid=self.uuid, date=date,
                returnUrl=quote(conf['returnUrl'], safe=''), clientType=1, timeStamp=int(stamp * 1000),
                cb_SaveName='3', isOauth2='true' if conf['isOauth2'] else 'false',
                state=conf.get('state', ''), paramId=conf['paramId']), headers={'Reqid': conf['reqId']})
            status = value.get('status')
            if type(status) is not int or value.get('result') == -20099:
                raise PanError('PAN_QR_EXPIRED' if value.get('result') == -20099 else 'PAN_REPLY_INVALID')
            # -106 observed before scanning on the official endpoint;
            # -11002 is the scanned/awaiting-confirmation state in its JS.
            if status in (-106, -11002):
                return 'waiting', None
            if status == -11001:
                self.cancel()
                raise PanError('PAN_QR_EXPIRED')
            if status == -134:
                raise PanError('PAN_CHALLENGE_REQUIRED')
            if status != 0:
                raise PanError('PAN_QR_STATE_INVALID')
            self.redirect = text(value.get('redirectUrl'), 16384)
            split_handoff(self.redirect)
        if self.redirect:
            follow(self.session, self.redirect)
            self.redirect = ''
        # A failed identity read retries this stage; never re-consume the QR.
        if self.brief is None:
            self.brief = checked(self.session.request(API + '/api/portal/v2/getUserBriefInfo.action'))
        key = text(self.brief.get('sessionKey'), 4096)
        value = checked(self.session.request(API + '/api/open/user/getUserInfoForPortal.action',
            query={'sessionKey': key}))
        subject = text(value.get('loginName'), 256)
        saved = self.session.export(subject=subject, session_key=key)
        self.cancel()
        return 'ready', saved


def entry(row, directory):
    if type(row) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    return dict(file_id=decimal(row.get('id')), name=text(row.get('name')),
                size=0 if directory else number(row.get('size')), directory=directory,
                modified=text(row.get('lastOpTime'), 64))


class Client:
    def __init__(self, saved, session=None):
        from .pan_http import credentials
        self.saved = credentials('189', saved)[1]
        self.session = session if session is not None else Session('189', self.saved)

    def __repr__(self):
        return '<Tianyi personal drive: credentials hidden>'

    def _call(self, path, query):
        return checked(self.session.request(API + path, query=dict(query, sessionKey=self.saved['session_key'])))

    def list_files(self, parent='0', page=1, size=10):
        page_number(page, size)
        value = self._call('/api/open/file/listFiles.action', dict(folderId=decimal(parent),
            mediaType=0, pageNum=page, pageSize=size, iconOption=0, orderBy='filename', descending='false'))
        files = value.get('fileListAO')
        if (type(files) is not dict or type(files.get('fileList')) is not list
                or type(files.get('folderList')) is not list):
            raise PanError('PAN_REPLY_INVALID')
        rows = [(r, True) for r in files['folderList']] + [(r, False) for r in files['fileList']]
        result = listing(rows, files.get('count'), page, size, lambda r: entry(*r))
        for item in result['items']:
            if not item['directory']:
                item['listing'] = dict(parent=parent, page=page, size=size)
        return result

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'name', 'size', 'directory', 'modified', 'listing'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        fid = decimal(selected['file_id'])
        number(selected['size'], 1)
        location = selected['listing']
        if type(location) is not dict or set(location) != {'parent', 'page', 'size'}:
            raise PanError('PAN_SELECTION_INVALID')
        matches = [r for r in self.list_files(**location)['items'] if r['file_id'] == fid]
        if len(matches) != 1 or matches[0] != selected:
            raise PanError('PAN_FILE_CHANGED')
        value = self._call('/api/open/file/getFileDownloadUrl.action', {'fileId': fid})
        url = original_url(value.get('fileDownloadUrl'), ('189.cn', 'ctyun.cn', 'ctyunapi.cn'))
        return dict(url=url, size=selected['size'], original=True, headers={'User-Agent': USER_AGENT})
