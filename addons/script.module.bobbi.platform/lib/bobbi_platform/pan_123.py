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
    if type(row) is not dict or type(row.get('Type')) is not int or row['Type'] not in (0, 1):
        raise PanError('PAN_REPLY_INVALID')
    result = dict(file_id=decimal(row.get('FileId')), name=text(row.get('FileName')),
        size=number(row.get('Size')), directory=row['Type'] == 1)
    if not result['directory']:
        result['etag'] = identifier(row.get('Etag'))
        result['storage_key'] = text(row.get('S3KeyFlag'), 256)
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
        value = data(self.session.request(API + '/b/api/file/list/new', query=dict(
            driveId=0, limit=size, next=0, orderBy='file_id', orderDirection='asc',
            parentFileId=decimal(parent), trashed='false', SearchData='', Page=page,
            OnlyLookAbnormalFile=0, event='homeListFile', operateType=1,
            inDirectSpace='false', fileCategory=0, isSearchOrder='false'), headers=self._headers()))
        result = listing(value.get('InfoList'), value.get('Total'), page, size, entry)
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
        value = data(self.session.request(API + '/a/api/file/download_info', body=dict(
            driveId=0, fileId=int(fid), fileName=selected['name'], etag=selected['etag'],
            size=selected['size'], s3keyFlag=selected['storage_key'], type=0), headers=self._headers()))
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
        return {'platform': 'web', 'app-version': '132', 'loginuuid': self.device,
                'Origin': AUTH, 'Referer': AUTH + '/centerlogin'}

    def begin(self):
        if self.terminal or self.phase != 'new':
            raise PanError('PAN_QR_FINISHED')
        self.session.request_raw(AUTH + '/centerlogin', query=dict(
            redirect_url='https://yun.123pan.cn', source_page='website'), headers=self._headers())
        value = data(self.session.request(AUTH + '/api/user/qr-code/generate',
            query={'uniID': str(uuid4())}, headers=self._headers()))
        qr_id = identifier(value.get('uniID'))
        url = value.get('url')
        # Never show a server-selected phishing QR or an unrelated login page.
        if url not in ('https://yun.123pan.cn/wx-app-login.html',
                       'https://www.123684.com/wx-app-login.html'):
            raise PanError('PAN_QR_ORIGIN_REJECTED')
        self.qr_id, self.phase, self.started = qr_id, 'waiting', self.clock()
        return url + '?' + urlencode(dict(uniID=qr_id, env='production'))

    def poll(self):
        if self.terminal or self.qr_id is None:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 120:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')
        if self.phase == 'waiting':
            value = data(self.session.request(AUTH + '/api/user/qr-code/result',
                query=dict(uniID=self.qr_id, remember='true', gray='true'), headers=self._headers()))
            status = value.get('loginStatus')
            if type(status) is not int:
                raise PanError('PAN_QR_STATE_INVALID')
            if status in (0, 1):
                return 'waiting', None
            if status in (3, 4):
                self.cancel()
                raise PanError('PAN_QR_EXPIRED')
            if status != 2:
                raise PanError('PAN_QR_STATE_INVALID')
            self.phase = 'exchange'
        if self.phase == 'exchange':
            value = data(self.session.request(AUTH + '/api/user/qr-code/wx_code',
                body={'uniID': self.qr_id}, headers=self._headers()))
            code = token(value.get('wxCode') or value.get('wechat_code'))
            value = data(self.session.request(AUTH + '/api/user/sign_in', body={
                'from': 'web', 'wechat_code': code, 'type': 4, 'remember': True, 'gray': True},
                headers=self._headers()), codes=(0, 200))
            access = value.get('token')
            if access is None:
                candidates = {c.value for c in self.session.jar if c.name == 'sso-token'
                    and c.domain.lstrip('.') in ('123pan.cn', 'user.123pan.cn') and not c.is_expired()}
                if len(candidates) == 1:
                    access = candidates.pop()
            if type(access) is str and access.startswith('Bearer '):
                access = access[7:]
            self.access, self.phase = token(access), 'identity'
        # Retain exchange result privately if this read times out: never
        # re-consume a one-use WeChat code on the next poll.
        value = data(self.session.request('https://api.123pan.cn/b/api/user/info',
            headers={'Authorization': 'Bearer ' + self.access, 'platform': 'web', 'app-version': '3'}))
        subject = decimal(value.get('UID'))
        if subject == '0':
            raise PanError('PAN_CREDENTIALS_INVALID')
        result = credentials(dict(provider='123', subject=subject, access_token=self.access, device_id=self.device))[1]
        self.cancel()
        return 'ready', result
