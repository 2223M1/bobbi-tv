"""Aliyun first-party web QR, token rotation and original-file read APIs.

No borrowed OAuth application, third-party refresh service or device secret.
"""
import base64
from copy import deepcopy
import json
import re
import time
from uuid import uuid4

from .pan_accounts import PanError
from .pan_http import Session, USER_AGENT
from .pan_tokens import identifier, number, original_url, page_number, saved, text, token

AUTH = 'https://passport.aliyundrive.com/newlogin/qrcode/'
API = 'https://api.aliyundrive.com'
TOKEN_URL = 'https://auth.aliyundrive.com/v2/account/token'
USER_URL = 'https://user.aliyundrive.com/v2/user/get'
WEB_HEADERS = {'Origin': 'https://www.alipan.com', 'Referer': 'https://www.alipan.com/'}


def credentials(value):
    value = saved('aliyun', value, {'provider', 'subject', 'access_token', 'refresh_token',
        'expires_at', 'device_id', 'drives'})
    token(value['refresh_token'])
    number(value['expires_at'], 1)
    identifier(value['device_id'])
    if (type(value['drives']) is not dict
            or not set(value['drives']) <= {'default', 'resource', 'backup'}):
        raise PanError('PAN_CREDENTIALS_INVALID')
    for drive in value['drives'].values():
        identifier(drive)
    return value['subject'], value


def checked(value):
    if value.get('code'):
        raise PanError('PAN_LOGIN_REQUIRED' if value['code'] in
            ('AccessTokenInvalid', 'AccessTokenExpired', 'RefreshTokenExpired') else 'PAN_API_REJECTED')
    return value


def refreshed(session, refresh, device, clock):
    value = checked(session.request(TOKEN_URL,
        body={'grant_type': 'refresh_token', 'refresh_token': token(refresh)}, headers=WEB_HEADERS))
    lifetime = number(value.get('expires_in'), 1)
    if lifetime > 31 * 86400:
        raise PanError('PAN_REPLY_INVALID')
    drives = {key: value[key + '_drive_id'] for key in ('default', 'resource', 'backup')
              if value.get(key + '_drive_id')}
    return credentials(dict(provider='aliyun', subject=value.get('user_id'),
        access_token=value.get('access_token'), refresh_token=value.get('refresh_token'),
        expires_at=int(clock()) + lifetime, device_id=device, drives=drives))[1]


def entry(row, drive):
    if (type(row) is not dict or row.get('type') not in ('file', 'folder')
            or row.get('drive_id') != drive):
        raise PanError('PAN_REPLY_INVALID')
    result = dict(file_id=drive + ':' + identifier(row.get('file_id')),
        name=text(row.get('name')), directory=row['type'] == 'folder', size=number(row.get('size', 0)))
    if not result['directory']:
        result['content_hash'] = identifier(row.get('content_hash'))
    return result


class Client:
    def __init__(self, value, session=None, clock=time.time):
        self.saved = credentials(value)[1]
        self.drives = dict(self.saved['drives'])
        self.session = session if session is not None else Session('aliyun')
        self.clock = clock

    def __repr__(self):
        return '<Aliyun drive: credentials hidden>'

    def renew_if_needed(self, publish):
        if self.saved['expires_at'] > self.clock() + 60:
            return
        previous = deepcopy(self.saved)
        current = refreshed(self.session, previous['refresh_token'], previous['device_id'], self.clock)
        if current['subject'] != previous['subject']:
            raise PanError('PAN_RENEW_IDENTITY_CHANGED')
        publish(current, previous)  # Persist before further IO; CAS owned by Host.
        self.saved = current
        self.drives = dict(current['drives'])

    def _call(self, path, body):
        return checked(self.session.request(API + path, body=body, headers={
            'Authorization': 'Bearer ' + self.saved['access_token'],
            'X-Device-Id': self.saved['device_id'],
            'X-Canary': 'client=web,app=adrive,version=v2.4.0'}))

    def _parent(self, parent):
        if type(parent) is not str or parent.count(':') != 1:
            raise PanError('PAN_FILE_ID_INVALID')
        drive, fid = parent.split(':')
        identifier(drive)
        identifier(fid)
        self._ensure_drives()
        if drive not in self.drives.values():
            raise PanError('PAN_FILE_ID_INVALID')
        return drive, fid

    def _ensure_drives(self):
        if self.drives:
            return
        # Drive discovery belongs to browsing/playback, not QR authorization.
        # No account publication or credential rotation occurs on this read.
        value = checked(self.session.request(USER_URL, body={}, headers=dict(WEB_HEADERS,
            Authorization='Bearer ' + self.saved['access_token'])))
        if 'user_id' in value and value['user_id'] != self.saved['subject']:
            raise PanError('PAN_RENEW_IDENTITY_CHANGED')
        drives = {kind: identifier(value[kind + '_drive_id']) for kind in ('default', 'resource', 'backup')
                  if value.get(kind + '_drive_id')}
        if not drives:
            raise PanError('PAN_REPLY_INVALID')
        self.drives = drives

    def list_files(self, parent='0', page=1, size=10, cursor=''):
        page_number(page, size)
        if type(cursor) is not str or len(cursor) > 2048 or re.search(r'[\x00-\x20\x7f]', cursor):
            raise PanError('PAN_PAGE_INVALID')
        if parent == '0':
            if page != 1 or cursor:
                raise PanError('PAN_PAGE_INVALID')
            self._ensure_drives()
            items, seen = [], set()
            for kind, label in (('resource', '资源库'), ('backup', '备份盘'), ('default', '默认网盘')):
                drive = self.drives.get(kind)
                if drive and drive not in seen:
                    seen.add(drive)
                    items.append(dict(file_id=drive + ':root', name=label, size=0, directory=True))
            return dict(items=items, page=1, has_more=False, next_cursor='')
        if bool(cursor) != (page > 1):
            raise PanError('PAN_PAGE_INVALID')
        drive, fid = self._parent(parent)
        value = self._call('/adrive/v3/file/list', dict(drive_id=drive, parent_file_id=fid,
            limit=size, marker=cursor, order_by='name', order_direction='ASC', fields='*'))
        rows, marker = value.get('items'), value.get('next_marker')
        if (type(rows) is not list or len(rows) > size or type(marker) is not str
                or len(marker) > 2048 or re.search(r'[\x00-\x20\x7f]', marker)
                or marker and (not rows or marker == cursor)):
            raise PanError('PAN_REPLY_INVALID')
        items = [entry(row, drive) for row in rows]
        if len({r['file_id'] for r in items}) != len(items):
            raise PanError('PAN_REPLY_INVALID')
        return dict(items=items, page=page, has_more=bool(marker), next_cursor=marker)

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'name', 'size', 'directory', 'content_hash'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        number(selected['size'], 1)
        drive, fid = self._parent(selected['file_id'])
        metadata = self._call('/v2/file/get', dict(drive_id=drive, file_id=fid))
        if entry(metadata, drive) != selected:
            raise PanError('PAN_FILE_CHANGED')
        value = self._call('/v2/file/get_download_url', dict(drive_id=drive, file_id=fid, expire_sec=900))
        if value.get('size') != selected['size'] or type(value.get('size')) is not int:
            raise PanError('PAN_FILE_CHANGED')
        url = original_url(value.get('url'), ('alipan.com', 'aliyundrive.com', 'aliyunpds.com'))
        return dict(url=url, size=selected['size'], original=True,
            headers={'User-Agent': USER_AGENT, 'Referer': 'https://www.alipan.com/'})


class Login:
    def __init__(self, session=None, clock=time.monotonic, wall_clock=time.time):
        self.session = session if session is not None else Session('aliyun')
        self.clock, self.wall_clock = clock, wall_clock
        self.device, self.ck, self.stamp, self.refresh = uuid4().hex, None, None, None
        self.started, self.terminal = 0, False
        self.pending, self.phase = None, 'prepare'

    def __repr__(self):
        return '<Aliyun QR: credentials hidden>'

    def cancel(self):
        self.terminal, self.ck, self.stamp, self.refresh = True, None, None, None
        self.pending = None

    @staticmethod
    def _content(value):
        content = value.get('content')
        if type(content) is not dict or type(content.get('data')) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        if content.get('success') is False:
            raise PanError('PAN_QR_UNAVAILABLE')
        return content['data']

    def begin(self):
        if self.terminal or self.ck is not None:
            raise PanError('PAN_QR_FINISHED')
        self.phase = 'prepare'
        value = self._content(self.session.request(AUTH + 'generate.do', query=dict(
            appName='aliyun_drive', fromSite='52', appEntrance='web', isMobile='false',
            lang='zh_CN', returnUrl='', bizParams='', **{'_bx-v': '2.2.3'}), headers=WEB_HEADERS))
        if self.terminal:
            raise PanError('PAN_QR_FINISHED')
        qr = original_url(value.get('codeContent'), ('aliyundrive.com', 'alipan.com'))
        self.ck = text(value.get('ck'), 2048)
        stamp = value.get('t')
        if type(stamp) is int:
            stamp = str(number(stamp, 1))
        if type(stamp) is not str or not re.fullmatch(r'[0-9]{1,20}', stamp):
            raise PanError('PAN_REPLY_INVALID')
        self.stamp, self.started = stamp, self.clock()
        return qr

    def _check_active(self):
        if self.terminal or self.ck is None:
            self.cancel()
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')

    def poll(self):
        self._check_active()
        if self.pending is None:
            self.phase = 'confirm'
            value = self._content(self.session.request(AUTH + 'query.do',
                query=dict(appName='aliyun_drive', fromSite='52', **{'_bx-v': '2.2.3'}),
                form=dict(t=self.stamp, ck=self.ck, appName='aliyun_drive', appEntrance='web',
                    isMobile='false', lang='zh_CN', returnUrl='', fromSite='52', bizParams='',
                    navlanguage='zh-CN', navPlatform='Win32'), headers=WEB_HEADERS))
            self._check_active()
            status = value.get('qrCodeStatus')
            if status in ('NEW', 'SCANED'):
                return 'waiting', None
            if status in ('EXPIRED', 'CANCELED'):
                self.cancel()
                raise PanError('PAN_QR_EXPIRED' if status == 'EXPIRED' else 'PAN_QR_CANCELLED')
            if status != 'CONFIRMED':
                raise PanError('PAN_QR_STATE_INVALID')
            try:
                raw = base64.b64decode(text(value.get('bizExt'), 32768), validate=True)
                content = json.loads(raw.decode('gb18030'))
                self.refresh = token(content['pds_login_result']['refreshToken'])
            except (ValueError, KeyError, TypeError):
                raise PanError('PAN_QR_EXCHANGE_FAILED') from None
            self.phase = 'exchange'
            # This refresh rotates credentials. Do not replay after an ambiguous
            # exchange failure; retain a successful result for identity-only retry.
            try:
                self.pending = refreshed(self.session, self.refresh, self.device, self.wall_clock)
            except Exception:
                self.cancel()
                raise
            self.refresh = None
            self._check_active()
        # The successful token exchange already carries the stable user_id.
        # Member/drive metadata is not another login gate; absent drive IDs
        # are discovered only when the user opens the drive.
        self.phase = 'identity'
        self._check_active()
        result = self.pending
        self.cancel()
        return 'ready', result
