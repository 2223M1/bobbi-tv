"""User-initiated official 115 QR login. No bundled accounts or password input."""
import json
from http.client import HTTPException, RemoteDisconnected
from http.cookiejar import CookieJar, DefaultCookiePolicy
from http.cookies import CookieError, SimpleCookie
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

USER_AGENT = 'Mozilla/5.0 115Browser/36.2.28'
MAX_REPLY = 2 * 1024 * 1024
# QR creation uses the web family; os_linux is the persisted exchange app.
# Juku normalizes desktop aliases to web, not to their cookie-exchange app.
QR_TOKEN = 'https://qrcodeapi.115.com/api/1.0/web/1.0/token/'
QR_EXCHANGE = 'https://passportapi.115.com/app/1.0/os_linux/1.0/login/qrcode'
QR_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                 '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 115Browser/36.2.28')
COOKIE_NAMES = ('UID', 'CID', 'SEID', 'KID')


class CloudError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class CloudTimeout(CloudError):
    """Internal timeout distinction; the public diagnostic remains fixed."""
    def __init__(self):
        super().__init__('NETWORK_ERROR')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise CloudError('UNEXPECTED_REDIRECT')


class _ExchangeReply(dict):
    """Transport-only header cookies; remote JSON cannot manufacture them."""
    def __init__(self, value, cookies):
        super().__init__(value)
        self.cookies = cookies


def _response_cookies(response, req):
    # Use normal expiry/domain parsing and only this exact first-party exchange.
    # A cookie for a foreign domain, or an expired cookie, is not a credential.
    headers = getattr(response, 'headers', None)
    if not hasattr(headers, 'get_all'):
        return {}
    rows = headers.get_all('Set-Cookie', [])
    if len(rows) > 64 or sum(len(row) for row in rows) > 16384:
        raise CloudError('INVALID_REPLY')
    seen = {}
    for row in rows:
        try:
            parsed = SimpleCookie(row)
        except CookieError:
            raise CloudError('INVALID_REPLY') from None
        for name in COOKIE_NAMES:
            if name in parsed:
                value = parsed[name].value
                if name in seen and seen[name] != value:
                    raise CloudError('INVALID_CREDENTIALS')
                seen[name] = value
    jar = CookieJar(DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrict))
    jar.extract_cookies(response, req)
    result = {}
    for cookie in jar:
        if (cookie.name not in COOKIE_NAMES or cookie.is_expired()
                or cookie.domain.lstrip('.') not in ('115.com', 'passportapi.115.com')):
            continue
        if cookie.name in result and result[cookie.name] != cookie.value:
            raise CloudError('INVALID_CREDENTIALS')
        result[cookie.name] = cookie.value
    return result


def request(url, values=None, cookie=None, opener=None):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in {
            'qrcodeapi.115.com', 'passportapi.115.com', 'webapi.115.com', 'proapi.115.com'}
            or parts.port not in (None, 443) or parts.username or parts.password):
        raise CloudError('INVALID_ORIGIN')
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', 'Cache-Control': 'no-store'}
    if url in (QR_TOKEN, QR_EXCHANGE):
        headers.update({'User-Agent': QR_USER_AGENT, 'Origin': 'https://115cdn.com',
                        'Referer': 'https://115cdn.com/'})
    elif parts.hostname == 'qrcodeapi.115.com' and parts.path == '/get/status/':
        headers['User-Agent'] = 'okhttp/5.3.2'
    if cookie:
        headers['Cookie'] = cookie
    data = urlencode(values).encode() if values is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = Request(url, data=data, headers=headers)
    transport = opener or build_opener(ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + 8
    try:
        with transport.open(req, timeout=8) as response:
            response_cookies = _response_cookies(response, req) if url == QR_EXCHANGE and data is not None else {}
            length = getattr(response, 'headers', {}).get('Content-Length')
            if length is not None:
                if not re.fullmatch(r'[0-9]{1,10}', str(length)) or int(length) > MAX_REPLY:
                    raise CloudError('INVALID_REPLY')
                length = int(length)
            raw = bytearray()
            reader = getattr(response, 'read1', response.read)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CloudTimeout()
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = reader(min(65536, MAX_REPLY + 1 - len(raw)))
                if time.monotonic() >= deadline:
                    raise CloudTimeout()
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_REPLY:
                    raise CloudError('INVALID_REPLY')
            # A parseable JSON prefix is not proof of a complete HTTP reply.
            if length is not None and len(raw) != length:
                raise CloudError('INVALID_REPLY')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise CloudError('INVALID_REPLY')
        return _ExchangeReply(value, response_cookies) if url == QR_EXCHANGE else value
    except CloudError:
        raise
    except RemoteDisconnected:
        # A peer closing before its status line is a connection failure, not
        # malformed JSON. RemoteDisconnected also inherits HTTPException.
        raise CloudError('NETWORK_ERROR') from None
    except TimeoutError:
        raise CloudTimeout() from None
    except URLError as error:
        if not isinstance(error, HTTPError) and isinstance(error.reason, TimeoutError):
            raise CloudTimeout() from None
        raise CloudError('NETWORK_ERROR') from None
    except (ValueError, HTTPException):
        raise CloudError('INVALID_REPLY') from None
    except OSError:
        raise CloudError('NETWORK_ERROR') from None


def credentials(value):
    if (not isinstance(value, dict) or value.get('app') != 'os_linux'
            or not isinstance(value.get('cookies'), dict)):
        raise CloudError('INVALID_CREDENTIALS')
    cookies = value['cookies']
    if not all(isinstance(cookies.get(k), str) and 0 < len(cookies[k]) <= 2048
            and not re.search(r'[\s;\x00-\x1f\x7f]', cookies[k]) for k in ('UID', 'CID', 'SEID')):
        raise CloudError('INVALID_CREDENTIALS')
    selected = {k: cookies[k] for k in ('UID', 'CID', 'SEID')}
    if cookies.get('KID'):
        kid = cookies['KID']
        if not isinstance(kid, str) or len(kid) > 2048 or re.search(r'[\s;\x00-\x1f\x7f]', kid):
            raise CloudError('INVALID_CREDENTIALS')
        selected['KID'] = kid
    return {'app': 'os_linux', 'cookies': selected, 'user_agent': USER_AGENT}


def save(path, value):
    value = credentials(value)
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CloudError('UNSAFE_STORAGE')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.115-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise CloudError('INVALID_CREDENTIALS')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value, dict) and set(value) == {'_account'}:
            from .account_manager import validate_snapshot
            scope = validate_snapshot(value['_account'])
            if not scope['authenticated']:
                return None
        return credentials(value)
    except (ValueError, OSError, RuntimeError):
        raise CloudError('INVALID_CREDENTIALS') from None


class Login:
    """A QR attempt can finish once; cancellation never replaces saved login."""
    def __init__(self, transport=request, clock=time.monotonic):
        self.transport, self.clock = transport, clock
        self.token, self.started, self.terminal = None, 0, False
        self.phase = 'prepare'

    def __repr__(self):
        return '<bobbi 115 Login: QR hidden>'

    def begin(self):
        self.phase = 'prepare'
        reply = self.transport(QR_TOKEN)
        data = reply.get('data')
        if not reply.get('state') or not isinstance(data, dict):
            raise CloudError('QR_UNAVAILABLE')
        if (not all(isinstance(data.get(k), str) and 0 < len(data[k]) <= 1024 for k in ('uid', 'sign', 'qrcode'))
                or type(data.get('time')) is not int):
            raise CloudError('INVALID_REPLY')
        qr = urlsplit(data['qrcode'])
        if qr.scheme != 'https' or qr.hostname not in ('115.com', 'qrcode.115.com') or qr.username or qr.password:
            raise CloudError('INVALID_REPLY')
        self.token = {k: data[k] for k in ('uid', 'sign', 'time')}
        self.started, self.terminal = self.clock(), False
        return data['qrcode']

    def cancel(self):
        self.terminal = True
        self.token = None

    def _check_active(self):
        if self.terminal or not self.token:
            raise CloudError('QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise CloudError('QR_EXPIRED')

    def poll(self):
        self._check_active()
        self.phase = 'confirm'
        try:
            reply = self.transport('https://qrcodeapi.115.com/get/status/?' + urlencode(self.token))
        except CloudTimeout:
            # This endpoint holds an unanswered confirmation request open.
            # A bounded empty poll is not an exhausted login attempt. Other
            # network failures, QR creation and one-use exchange still fail.
            self._check_active()
            return 'waiting', None
        self._check_active()  # A late reply cannot exchange after cancel/expiry.
        data = reply.get('data')
        if not reply.get('state') or not isinstance(data, dict):
            raise CloudError('QR_POLL_RETRY')
        status = data.get('status')
        if type(status) is not int:
            raise CloudError('INVALID_REPLY')
        if status in (-1, -2):
            self.cancel()
            raise CloudError('QR_EXPIRED' if status == -1 else 'QR_CANCELLED')
        if status == 0:
            return 'waiting', None
        if status == 1:
            return 'scanned', None
        if status != 2:
            raise CloudError('INVALID_REPLY')
        uid = self.token['uid']
        # Claim before the account exchange. Never retry ambiguous login writes.
        self.cancel()
        self.phase = 'exchange'
        result = self.transport(QR_EXCHANGE, values={'account': uid, 'app': 'os_linux'})
        value = result.get('data')
        if not result.get('state') or not isinstance(value, dict):
            raise CloudError('LOGIN_FAILED')
        self.phase = 'identity'
        merged = dict(result.cookies) if isinstance(result, _ExchangeReply) else {}
        nested = value.get('cookie', {})
        if not isinstance(nested, dict):
            raise CloudError('INVALID_CREDENTIALS')
        for source in (nested, value):
            for name in COOKIE_NAMES:
                if name not in source:
                    continue
                if name in merged and merged[name] != source[name]:
                    raise CloudError('INVALID_CREDENTIALS')
                merged[name] = source[name]
        return 'confirmed', credentials({'app': 'os_linux', 'cookies': merged})
