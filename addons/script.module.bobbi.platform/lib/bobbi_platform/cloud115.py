"""User-initiated official 115 QR login. No bundled accounts or password input."""
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

USER_AGENT = 'Mozilla/5.0 115Browser/36.2.28'
MAX_REPLY = 2 * 1024 * 1024


class CloudError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise CloudError('UNEXPECTED_REDIRECT')


def request(url, values=None, cookie=None, opener=None):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in {
            'qrcodeapi.115.com', 'passportapi.115.com', 'webapi.115.com', 'proapi.115.com'}
            or parts.port not in (None, 443) or parts.username or parts.password):
        raise CloudError('INVALID_ORIGIN')
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', 'Cache-Control': 'no-store'}
    if cookie:
        headers['Cookie'] = cookie
    data = urlencode(values).encode() if values is not None else None
    req = Request(url, data=data, headers=headers)
    transport = opener or build_opener(ProxyHandler({}), NoRedirect())
    try:
        with transport.open(req, timeout=8) as response:
            raw = response.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise CloudError('INVALID_REPLY')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise CloudError('INVALID_REPLY')
        return value
    except CloudError:
        raise
    except (ValueError, OSError):
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
        return credentials(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError, OSError):
        raise CloudError('INVALID_CREDENTIALS') from None


class Login:
    """A QR attempt can finish once; cancellation never replaces saved login."""
    def __init__(self, transport=request, clock=time.monotonic):
        self.transport, self.clock = transport, clock
        self.token, self.started, self.terminal = None, 0, False

    def __repr__(self):
        return '<bobbi 115 Login: QR hidden>'

    def begin(self):
        reply = self.transport('https://qrcodeapi.115.com/api/1.0/web/1.0/token/')
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

    def poll(self):
        if self.terminal or not self.token:
            raise CloudError('QR_FINISHED')
        if self.clock() - self.started > 180:
            self.cancel()
            raise CloudError('QR_EXPIRED')
        reply = self.transport('https://qrcodeapi.115.com/get/status/?' + urlencode(self.token))
        data = reply.get('data')
        if not reply.get('state') or not isinstance(data, dict):
            raise CloudError('QR_POLL_RETRY')
        status = data.get('status')
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
        result = self.transport('https://qrcodeapi.115.com/app/1.0/os_linux/1.0/login/qrcode/',
                                values={'account': uid})
        value = result.get('data')
        if not result.get('state') or not isinstance(value, dict):
            raise CloudError('LOGIN_FAILED')
        return 'confirmed', credentials({'app': 'os_linux', 'cookies': value.get('cookie')})
