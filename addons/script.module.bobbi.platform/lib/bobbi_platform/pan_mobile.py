"""139 first-party QR and personal drive (legacy and PDS accounts).

Protocol verified against yun.139.com web app/chunk-5111af4d, 2026-11-09.
RSA encrypts a fresh per-attempt AES key with the server's public key. No
borrowed app secret, device identity, arbitrary script evaluation or cloud writes.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import string
import time
from urllib.parse import quote_plus, urlencode
from xml.etree import ElementTree

from .pan_accounts import PanError
from .pan_http import Session, USER_AGENT
from .pan_tokens import identifier, listing, number, original_url, page_number, text

API = 'https://yun.139.com/orchestration/'
AUTH = API + 'auth-rebuild/'
ROUTES = 'https://user-njs.yun.139.com/user/route/qryRoutePolicy'
REFRESH = 'https://aas.caiyun.feixin.10086.cn:443/tellin/authTokenRefresh.do'
CATALOG_ROOT = '00019700101000000001'


def random_text(length):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


def crypto(name):
    # Kodi may hide CE's system site-packages, or expose an incompatible
    # Cryptodome alias. Reuse the existing exact-package, single-suite loader.
    from bobbi_core.juku_api import crypto_module
    try:
        return crypto_module('Crypto.' + name)
    except (ImportError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
        raise PanError('PAN_CRYPTO_UNAVAILABLE') from None


def compact(value):
    # Same bytes are signed and sent by Session, including JSON escaping.
    return json.dumps(value, separators=(',', ':'))


def headers(body, device, wall_clock=time.time):
    stamp = datetime.fromtimestamp(wall_clock(), timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S%f')[:17]
    nonce = random_text(16)
    encoded = ''.join(sorted(quote_plus(compact(body), safe='')))
    md5 = lambda s: hashlib.md5(s.encode('ascii')).hexdigest()
    digest = md5(md5(base64.b64encode(encoded.encode('ascii')).decode('ascii')) + md5(stamp + ':' + nonce)).upper()
    info = '||3|12.27.0|chrome|131.0.0.0|' + identifier(device) + '||windows 10|1920X919|zh-CN|||'
    return {'mcloud-client': '10701', 'mcloud-sign': ','.join((stamp, nonce, digest)), 'X-Deviceinfo': info}


def code(value):
    if type(value) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    result = value['data'].get('result') if type(value.get('data')) is dict else None
    value = result.get('resultCode') if type(result) is dict else value.get('code')
    if type(value) is int:
        value = str(value)
    if type(value) is not str or not re.fullmatch('[0-9]{1,12}', value):
        raise PanError('PAN_REPLY_INVALID')
    return value


def checked(value):
    status = code(value)
    if status not in ('0', '0000'):
        raise PanError('PAN_LOGIN_REQUIRED' if status in ('401', '200000401', '200050432', '1010010005') else 'PAN_API_REJECTED')
    if type(value.get('data')) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    return value['data']


def route(value):
    if type(value) is not str or not re.fullmatch(r'https://personal(?:-[a-z0-9]+){0,3}\.yun\.139\.com/hcy', value):
        raise PanError('PAN_ROUTE_REJECTED')
    return value


def personal_route(rows):
    if type(rows) is not list or len(rows) > 64:
        raise PanError('PAN_ROUTE_REJECTED')
    matches = [r for r in rows if type(r) is dict and str(r.get('modName', '')).lower() == 'personal']
    if len(matches) != 1:
        raise PanError('PAN_ROUTE_REJECTED')
    return route(matches[0].get('httpsUrl'))


def auth_token(value):
    # This provider's token contains pipe-separated expiry metadata. Keep the
    # broader alphabet local; it is neither a generic OAuth token nor XML.
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9._~+/=|\-]{1,8192}', value):
        raise PanError('PAN_CREDENTIALS_INVALID')
    return value


def expires_at(value):
    parts = auth_token(value).split('|')
    if len(parts) >= 4 and re.fullmatch(r'[0-9]{10,16}', parts[3]):
        return int(parts[3]) / 1000
    return None


def phone(value):
    if type(value) is not str:
        return None
    value = value.strip()
    if value.startswith('+86'):
        value = value[3:]
    elif len(value) == 13 and value.startswith('86'):
        value = value[2:]
    return value if re.fullmatch(r'1[0-9]{10}', value) else None


def login_account(data):
    candidates = {p for p in (phone(data.get(k)) for k in ('account', 'userPhone', 'msisdn')) if p}
    encrypted = data.get('encryptAccount')
    if encrypted:
        try:
            decoded = base64.b64decode(text(encrypted, 128), validate=True).decode('ascii')
        except (ValueError, UnicodeError):
            raise PanError('PAN_REPLY_INVALID') from None
        decoded = phone(decoded)
        if decoded:
            candidates.add(decoded)
    if len(candidates) != 1:
        raise PanError('PAN_CREDENTIALS_INVALID')
    return candidates.pop()


def credentials(value):
    required = {'provider', 'subject', 'auth_token', 'device_id', 'pds', 'route'}
    if (type(value) is not dict or not required <= set(value) or set(value) - required - {'user_domain_id'}
            or value['provider'] != '139' or type(value['pds']) is not bool
            or type(value['subject']) is not str or not re.fullmatch(r'[0-9]{8,15}', value['subject'])):
        raise PanError('PAN_CREDENTIALS_INVALID')
    auth_token(value['auth_token'])
    identifier(value['device_id'])
    if 'user_domain_id' in value:
        identifier(value['user_domain_id'])
    if value['pds'] and value['route']:
        route(value['route'])
    elif value['route'] != '':
        raise PanError('PAN_CREDENTIALS_INVALID')
    return value['subject'], deepcopy(value)


def authorization(value):
    return 'Basic ' + base64.b64encode(('pc:' + value['subject'] + ':' + value['auth_token']).encode('ascii')).decode('ascii')


class Login:
    def __init__(self, session=None, clock=time.monotonic, wall_clock=time.time):
        self.session = session if session is not None else Session('139')
        self.clock, self.wall_clock = clock, wall_clock
        self.device, self.sid = random_text(32), random_text(16)
        self.key, self.secret, self.accepted = None, None, None
        self.started, self.next_poll, self.terminal = None, 0, False
        self.phase = 'new'

    def __repr__(self):
        return '<139 QR: temporary keys and tickets hidden>'

    def cancel(self):
        self.key = self.secret = self.sid = self.accepted = None
        self.terminal = True

    def _check_active(self):
        if self.terminal:
            self.cancel()
            raise PanError('PAN_QR_FINISHED')
        if self.started is not None and self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')

    def begin(self):
        if self.terminal or self.started is not None:
            raise PanError('PAN_QR_FINISHED')
        self.started = self.clock()
        PKCS1_v1_5, RSA = crypto('Cipher.PKCS1_v1_5'), crypto('PublicKey.RSA')
        body = dict(clientCode='10701', type=1)
        value = checked(self.session.request(AUTH + 'key/v1.0/getRsaPublicKey', body=body,
            headers=headers(body, self.device, self.wall_clock)))
        self._check_active()
        try:
            public = text(value.get('publicKey'), 4096)
            key = RSA.import_key(base64.b64decode(public, validate=True))
            if key.has_private() or not 1024 <= key.size_in_bits() <= 4096:
                raise ValueError
            self.key = random_text(16).encode('ascii')
            self.secret = base64.b64encode(PKCS1_v1_5.new(key).encrypt(self.key)).decode('ascii')
        except (ValueError, TypeError, IndexError):
            raise PanError('PAN_QR_KEY_INVALID') from None
        self._check_active()
        self.phase = 'waiting'
        return 'https://yun.139.com/w/#/qrcLogin?' + urlencode(dict(sID=self.sid, dID=self.device, cType=9))

    def poll(self):
        if self.terminal or self.started is None:
            raise PanError('PAN_QR_FINISHED')
        self._check_active()
        if self.clock() < self.next_poll:
            return 'waiting', None
        self.next_poll = self.clock() + 2
        if self.accepted is None:
            AES, pad = crypto('Cipher.AES'), crypto('Util.Padding').pad
            inner = compact(dict(dycPwd=self.sid, loginStyle='QRCode', clientEnv='3', setCookie='0')).encode('ascii')
            cipher = AES.new(self.key, AES.MODE_ECB).encrypt(pad(inner, 16))
            body = dict(encryptMsg=base64.b64encode(cipher).decode('ascii'), clientId='10701', returnToken=True)
            h = dict(headers(body, self.device, self.wall_clock), **{'mcloud-skey': self.secret})
            value = self.session.request(AUTH + 'permission/v1.0/login', body=body, headers=h)
            self._check_active()
            status = code(value)
            # Outer success/code=0 ALSO accompanies pending replies. The
            # nested resultCode is authoritative (541 observed anonymously).
            if status in ('200059541', '200059548'):
                if status == '200059548':
                    self.phase = 'confirm'
                return 'waiting', None
            if status in ('200059542', '200059543', '200059545', '200059546', '200059547', '200059549'):
                self.cancel()
                raise PanError('PAN_QR_EXPIRED')
            data = checked(value)
            self.phase = 'identity'
            account = login_account(data)
            # Route metadata describes drive access, not whether the official
            # authorization succeeded. Keep usable hints; defer route IO.
            cutover = data.get('cutoverStatus')
            pds = type(cutover) in (int, str) and str(cutover) == '1'
            saved = dict(provider='139', subject=account, auth_token=auth_token(data.get('authToken')),
                         device_id=self.device, pds=pds, route='')
            try:
                discovered = personal_route(data.get('routerInfo'))
            except PanError:
                discovered = None
            if discovered and cutover not in (0, '0'):
                saved.update(pds=True, route=discovered)
            try:
                user_id = identifier(data.get('userDomainId'))
            except PanError:
                user_id = None
            if saved['pds'] and user_id:
                saved['user_domain_id'] = user_id
            self.accepted = credentials(saved)[1]
        result = self.accepted
        self._check_active()
        self.cancel()
        return 'ready', result


def entry(row, pds, directory=None):
    if type(row) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    if pds:
        if row.get('type') not in ('file', 'folder'):
            raise PanError('PAN_REPLY_INVALID')
        directory = row['type'] == 'folder'
        return dict(file_id=identifier(row.get('fileId')), name=text(row.get('name')), directory=directory,
                    size=0 if directory else number(row.get('size')), modified=text(row.get('updatedAt'), 64))
    prefix = 'catalog' if directory else 'content'
    return dict(file_id=identifier(row.get(prefix + 'Id')), name=text(row.get(prefix + 'Name')),
                directory=directory, size=0 if directory else number(row.get('contentSize')),
                modified=text(row['updateTime'], 64) if 'updateTime' in row else '')


class Client:
    def __init__(self, saved, session=None, clock=time.time):
        self.saved = credentials(saved)[1]
        self.session = session if session is not None else Session('139')
        self.clock, self.refresh_attempted = clock, False

    def __repr__(self):
        return '<139 personal drive: credentials hidden>'

    def _uses_pds(self):
        if not self.saved['pds']:
            return False
        if self.saved['route']:
            return True
        user_id = self.saved.get('user_domain_id')
        if not user_id:
            # The official login already established the account. With no
            # routing hint, use the catalog API on demand, as legacy accounts
            # do; access failure must not retroactively undo that login.
            return False
        body = dict(userInfo=dict(userDomainId=user_id), modAddrType=1)
        h = dict(headers(body, self.saved['device_id']), Authorization=authorization(self.saved))
        routes = checked(self.session.request(ROUTES, body=body, headers=h)).get('routePolicyList')
        self.saved['route'] = personal_route(routes)  # Client-local cache only.
        return True

    def renew_if_needed(self, publish):
        expiry = expires_at(self.saved['auth_token'])
        # Opaque credentials saved by earlier releases remain usable. Only
        # known timestamped tokens are proactively renewed, once per operation.
        if expiry is None or expiry > self.clock() + 60:
            return
        if self.refresh_attempted:
            raise PanError('PAN_LOGIN_REQUIRED')
        self.refresh_attempted = True
        previous = deepcopy(self.saved)
        root = ElementTree.Element('root')
        for key, value in (('token', previous['auth_token']), ('account', previous['subject']), ('clienttype', '656')):
            ElementTree.SubElement(root, key).text = value
        raw = self.session.request_raw(REFRESH, xml_body=ElementTree.tostring(root, encoding='utf-8'), limit=16384)
        if type(raw) is not bytes or not 0 < len(raw) <= 16384 or b'<!' in raw or b'\x00' in raw:
            raise PanError('PAN_REPLY_INVALID')
        try:
            reply = ElementTree.fromstring(raw)
        except (ElementTree.ParseError, ValueError):
            raise PanError('PAN_REPLY_INVALID') from None
        values = {}
        if reply.tag != 'root' or reply.attrib or reply.text and reply.text.strip():
            raise PanError('PAN_REPLY_INVALID')
        for child in reply:
            if (child.tag not in ('return', 'desc', 'token', 'account') or child.tag in values
                    or child.attrib or len(child) or child.tail and child.tail.strip()):
                raise PanError('PAN_REPLY_INVALID')
            values[child.tag] = (child.text or '').strip()
        if values.get('return') != '0':
            raise PanError('PAN_LOGIN_REQUIRED')
        if 'account' in values and phone(values['account']) != previous['subject']:
            raise PanError('PAN_RENEW_IDENTITY_CHANGED')
        renewed = auth_token(values.get('token'))
        expiry = expires_at(renewed)
        if expiry is not None and expiry <= self.clock():
            raise PanError('PAN_LOGIN_REQUIRED')
        current = credentials(dict(previous, auth_token=renewed))[1]
        publish(current, previous)
        self.saved = current

    def _call(self, endpoint, body):
        h = headers(body, self.saved['device_id'])
        if endpoint not in (API + 'personalCloud/catalog/v1.0/getDirectoryCatalog',
                            API + 'personalCloud/upload/v1.0/getDownloadUrl'):
            h.update(Authorization=authorization(self.saved), **{'x-yun-api-version': 'v1',
                'x-yun-module-type': '100', 'x-yun-app-channel': '10000034',
                'x-yun-client-info': h['X-Deviceinfo'], 'x-yun-svc-type': '1'})
        else:
            h.update(Authorization=self.saved['auth_token'], **{'x-account': self.saved['subject']})
        return checked(self.session.request(endpoint, body=body, headers=h))

    def list_files(self, parent='0', page=1, size=10, cursor=''):
        page_number(page, size)
        identifier(parent)
        if type(cursor) is not str or len(cursor) > 2048 or (page == 1 and cursor):
            raise PanError('PAN_PAGE_INVALID')
        pds = self._uses_pds()
        if pds:
            if page > 1 and not cursor:
                raise PanError('PAN_PAGE_INVALID')
            data = self._call(self.saved['route'] + '/file/list', dict(parentFileId='/' if parent == '0' else parent,
                orderBy='updated_at', orderDirection='DESC', pageInfo=dict(pageCursor=cursor, pageSize=size)))
            rows, next_cursor = data.get('items'), data.get('nextPageCursor')
            if type(next_cursor) is not str or len(next_cursor) > 2048 or next_cursor and next_cursor == cursor:
                raise PanError('PAN_REPLY_INVALID')
            result = listing(rows, page * size + (1 if next_cursor else 0), page, size, lambda r: entry(r, True))
            result['next_cursor'] = next_cursor
        else:
            if cursor:
                raise PanError('PAN_PAGE_INVALID')
            data = self._call(API + 'personalCloud/catalog/v1.0/getDirectoryCatalog',
                dict(catalogId=CATALOG_ROOT if parent == '0' else parent, pageNo=page, pageSize=size,
                     sortDirection=0, sortType=1, catalogSortType=1))
            if type(data) is not dict or type(data.get('catalogList')) is not list or type(data.get('contentList')) is not list:
                raise PanError('PAN_REPLY_INVALID')
            rows = [(r, True) for r in data['catalogList']] + [(r, False) for r in data['contentList']]
            # This API has no required count field. Probe the following page
            # only for a full page, keeping all work inside the scan budget.
            total = (page - 1) * size + len(rows) + (1 if len(rows) == size else 0)
            result = listing(rows, total, page, size, lambda r: entry(r[0], False, r[1]))
        for item in result['items']:
            if not item['directory']:
                item['listing'] = dict(parent=parent, page=page, size=size, cursor=cursor)
        return result

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) != {'file_id', 'name', 'size', 'directory', 'modified', 'listing'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        fid, size = identifier(selected['file_id']), number(selected['size'], 1)
        location = selected['listing']
        if type(location) is not dict or set(location) != {'parent', 'page', 'size', 'cursor'}:
            raise PanError('PAN_SELECTION_INVALID')
        matches = [r for r in self.list_files(**location)['items'] if r['file_id'] == fid]
        if len(matches) != 1 or matches[0] != selected:
            raise PanError('PAN_FILE_CHANGED')
        if self._uses_pds():
            data = self._call(self.saved['route'] + '/file/getDownloadUrl', dict(fileId=fid))
            url = data.get('cdnUrl') if data.get('cdnSwitch') is True and data.get('cdnUrl') else data.get('url')
        else:
            data = self._call(API + 'personalCloud/upload/v1.0/getDownloadUrl', {'contentId': fid})
            url = data.get('url')
        return dict(url=original_url(url, ('139.com', 'caiyun.feixin.10086.cn')), size=size,
                    original=True, headers={'User-Agent': USER_AGENT})
