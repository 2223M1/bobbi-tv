"""Bounded direct HTTPS JSON and provider-private cookie jars. No redirects."""
from http.client import HTTPException
from contextlib import contextmanager
from http.cookiejar import Cookie, CookieJar
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener

from .pan_accounts import PanError


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'
MAX_REPLY = 2 * 1024 * 1024
DOMAINS = {'quark': 'quark.cn', 'uc': 'uc.cn', 'baidu': 'baidu.com', '189': '189.cn'}
API = {'quark': 'https://drive-pc.quark.cn', 'uc': 'https://pc-api.uc.cn', 'baidu': 'https://pan.baidu.com'}
API['189'] = 'https://cloud.189.cn'
WEB = {'quark': 'https://pan.quark.cn', 'uc': 'https://drive.uc.cn', 'baidu': 'https://pan.baidu.com'}
WEB.update(aliyun='https://www.alipan.com', **{'123': 'https://yun.123pan.cn'})
WEB.update(guangya='https://www.guangyapan.com', xunlei='https://pan.xunlei.com')
WEB['189'] = 'https://cloud.189.cn'
WEB['139'] = 'https://yun.139.com/w'
TOKEN_ROUTES = {
    '139': {
        ('POST', 'https://yun.139.com/orchestration/auth-rebuild/key/v1.0/getRsaPublicKey'),
        ('POST', 'https://yun.139.com/orchestration/auth-rebuild/permission/v1.0/login'),
        ('POST', 'https://user-njs.yun.139.com/user/route/qryRoutePolicy'),
        ('POST', 'https://yun.139.com/orchestration/personalCloud/catalog/v1.0/getDisk'),
        ('POST', 'https://yun.139.com/orchestration/personalCloud/uploadAndDownload/v1.0/downloadRequest'),
    },
    '189': {
        ('GET', 'https://cloud.189.cn/api/portal/loginUrl.action'),
        ('GET', 'https://open.e.189.cn/api/logbox/separate/web/index.html'),
        ('GET', 'https://open.e.189.cn/api/logbox/oauth2/separate/auth/unifyAccountLogin.do'),
        ('POST', 'https://open.e.189.cn/api/logbox/oauth2/appConf.do'),
        ('POST', 'https://open.e.189.cn/api/logbox/oauth2/getUUID.do'),
        ('GET', 'https://open.e.189.cn/api/logbox/oauth2/image.do'),
        ('POST', 'https://open.e.189.cn/api/logbox/oauth2/qrcodeLoginState.do'),
        ('GET', 'https://cloud.189.cn/api/portal/callbackUnify.action'),
        ('GET', 'https://cloud.189.cn/web/redirect.html'),
        ('GET', 'https://cloud.189.cn/web/main'),
        ('GET', 'https://cloud.189.cn/main.action'),
        ('GET', 'https://cloud.189.cn/api/portal/v2/getUserBriefInfo.action'),
        ('GET', 'https://cloud.189.cn/api/open/user/getUserInfoForPortal.action'),
        ('GET', 'https://cloud.189.cn/api/open/file/listFiles.action'),
        ('GET', 'https://cloud.189.cn/api/open/file/getFileDownloadUrl.action'),
    },
    'aliyun': {
        ('GET', 'https://passport.aliyundrive.com/newlogin/qrcode/generate.do'),
        ('POST', 'https://passport.aliyundrive.com/newlogin/qrcode/query.do'),
        ('POST', 'https://auth.alipan.com/v2/account/token'),
        ('POST', 'https://api.alipan.com/v2/user/get'),
        ('POST', 'https://api.alipan.com/adrive/v3/file/list'),
        ('POST', 'https://api.alipan.com/v2/file/get'),
        ('POST', 'https://api.alipan.com/v2/file/get_download_url'),
    },
    '123': {
        ('GET', 'https://user.123pan.cn/centerlogin'),
        ('GET', 'https://user.123pan.cn/api/user/qr-code/generate'),
        ('GET', 'https://user.123pan.cn/api/user/qr-code/result'),
        ('POST', 'https://user.123pan.cn/api/user/qr-code/wx_code'),
        ('POST', 'https://user.123pan.cn/api/user/sign_in'),
        ('GET', 'https://api.123pan.cn/b/api/user/info'),
        ('GET', 'https://www.123pan.cn/b/api/file/list/new'),
        ('POST', 'https://www.123pan.cn/a/api/file/download_info'),
    },
    'guangya': {
        ('POST', 'https://account.guangyapan.com/v1/auth/device/code'),
        ('POST', 'https://account.guangyapan.com/v1/auth/token'),
        ('GET', 'https://account.guangyapan.com/v1/user/me'),
        ('POST', 'https://api.guangyapan.com/userres/v1/file/get_file_list'),
        ('POST', 'https://api.guangyapan.com/nd.bizuserres.s/v1/get_res_download_url'),
    },
    'xunlei': {
        ('POST', 'https://xluser-ssl.xunlei.com/v1/shield/captcha/init'),
        ('POST', 'https://xluser-ssl.xunlei.com/v1/auth/device/code'),
        ('POST', 'https://xluser-ssl.xunlei.com/v1/auth/token'),
        ('GET', 'https://xluser-ssl.xunlei.com/v1/user/me'),
        ('GET', 'https://api-pan.xunlei.com/drive/v1/files'),
    },
}
API_ROUTES = {
    ('GET', '/1/clouddrive/file/sort'), ('GET', '/1/clouddrive/member'),
    ('POST', '/1/clouddrive/file/download'),
    ('POST', '/1/clouddrive/share/sharepage/token'),
    ('GET', '/1/clouddrive/share/sharepage/detail'),
}
AUTH_ROUTES = {
    ('GET', 'https://uop.quark.cn/cas/ajax/getTokenForQrcodeLogin'),
    ('GET', 'https://uop.quark.cn/cas/ajax/getServiceTicketByQrcodeToken'),
    ('GET', 'https://pan.quark.cn/account/info'),
}
UC_AUTH_ROUTES = {
    ('GET', 'https://api.open.uc.cn/cas/ajax/getTokenForQrcodeLogin'),
    ('GET', 'https://api.open.uc.cn/cas/ajax/getServiceTicketByQrcodeToken'),
    ('GET', 'https://drive.uc.cn/account/info'),
}
BAIDU_ROUTES = {
    ('GET', 'https://passport.baidu.com/v2/api/getqrcode'),
    ('GET', 'https://passport.baidu.com/v2/api/qrcode'),
    ('GET', 'https://passport.baidu.com/channel/unicast'),
    ('GET', 'https://passport.baidu.com/v3/login/main/qrbdusslogin'),
    ('GET', 'https://pan.baidu.com/api/gettemplatevariable'),
    ('GET', 'https://pan.baidu.com/api/list'),
    ('GET', 'https://pan.baidu.com/api/filemetas'),
}


def _cookie_rows(provider, rows):
    domain = DOMAINS.get(provider)
    if domain is None or type(rows) is not list or len(rows) > 32:
        raise PanError('PAN_CREDENTIALS_INVALID')
    result, seen = [], set()
    for row in rows:
        if (type(row) is not dict or set(row) != {'name', 'value', 'domain', 'path'}
                or any(type(v) is not str for v in row.values())
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', row['name'])
                or not 0 < len(row['value']) <= 4096
                or not row['value'].isascii()
                or re.search(r'[;\x00-\x20\x7f-\uffff]', row['value'])
                or row['domain'].lstrip('.') not in (domain, urlsplit(API[provider]).hostname,
                    urlsplit(WEB[provider]).hostname, 'passport.baidu.com' if provider == 'baidu' else domain,
                    'open.e.189.cn' if provider == '189' else domain, 'e.189.cn' if provider == '189' else domain)
                or not row['path'].startswith('/') or len(row['path']) > 256
                or re.search(r'[\x00-\x20\x7f]', row['path'])):
            raise PanError('PAN_CREDENTIALS_INVALID')
        key = row['domain'], row['path'], row['name']
        if key in seen:
            raise PanError('PAN_CREDENTIALS_INVALID')
        seen.add(key)
        result.append(dict(row))
    if len(json.dumps(result).encode('utf-8')) > 24576:
        raise PanError('PAN_CREDENTIALS_INVALID')
    return result


def credentials(provider, value):
    fields = ({'provider', 'cookies', 'subject', 'session_key'} if provider == '189' else
              {'provider', 'cookies', 'subject'} if provider == 'baidu' else {'provider', 'cookies'})
    if type(value) is not dict or set(value) != fields or value['provider'] != provider:
        raise PanError('PAN_CREDENTIALS_INVALID')
    rows = _cookie_rows(provider, value['cookies'])
    if provider == '189':
        if (type(value['subject']) is not str or not re.fullmatch(r'[A-Za-z0-9@._+-]{1,256}', value['subject'])
                or type(value['session_key']) is not str
                or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', value['session_key'])
                or not any(r['name'] == 'COOKIE_LOGIN_USER' for r in rows)):
            raise PanError('PAN_CREDENTIALS_INVALID')
        return value['subject'], dict(provider=provider, cookies=rows,
            subject=value['subject'], session_key=value['session_key'])
    if provider == 'baidu':
        if (type(value['subject']) is not str or not re.fullmatch(r'[1-9][0-9]{0,31}', value['subject'])
                or not any(r['name'] == 'BDUSS' and len(r['value']) >= 64 for r in rows)):
            raise PanError('PAN_CREDENTIALS_INVALID')
        return value['subject'], dict(provider=provider, cookies=rows, subject=value['subject'])
    # Never derive account identity from a rotating session token.
    subjects = {r['value'] for r in rows if r['name'] == '__uid'}
    if (len(subjects) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', next(iter(subjects)))
            or not any(r['name'] == '__pus' for r in rows)):
        raise PanError('PAN_CREDENTIALS_INVALID')
    return next(iter(subjects)), dict(provider=provider, cookies=rows)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise PanError('PAN_REDIRECT_REJECTED')


class HandoffRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # Report a bounded 302; the 189 adapter validates each hop.


class Session:
    def __init__(self, provider, saved=None, opener=None, clock=time.monotonic):
        if provider not in DOMAINS and provider not in TOKEN_ROUTES:
            raise PanError('PAN_PROVIDER_INVALID')
        self.provider, self.jar, self.clock = provider, CookieJar(), clock
        self.deadline = None
        if saved is not None:
            _, saved = credentials(provider, saved)
            for row in saved['cookies']:
                self.jar.set_cookie(Cookie(0, row['name'], row['value'], None, False,
                    row['domain'], row['domain'].startswith('.'), row['domain'].startswith('.'),
                    row['path'], True, True, None, True, None, None, {}))
        redirect = HandoffRedirect() if provider == '189' else NoRedirect()
        self.opener = opener or build_opener(ProxyHandler({}), redirect, HTTPCookieProcessor(self.jar))

    def __repr__(self):
        return '<Pan HTTPS session: credentials hidden>'

    @contextmanager
    def budget(self, seconds):
        previous = self.deadline
        self.deadline = min(previous, self.clock() + seconds) if previous is not None else self.clock() + seconds
        try:
            yield
        finally:
            self.deadline = previous

    def export(self, subject=None, session_key=None):
        rows = [dict(name=c.name, value=c.value, domain=c.domain, path=c.path) for c in self.jar
                if not c.is_expired()]
        value = dict(provider=self.provider, cookies=rows)
        if self.provider in ('baidu', '189'):
            value['subject'] = subject
        if self.provider == '189':
            value['session_key'] = session_key
        return credentials(self.provider, value)[1]

    def cookie_header(self, url):
        request = Request(url)
        self.jar.add_cookie_header(request)
        return request.get_header('Cookie', '')

    def request(self, url, query=None, body=None, **options):
        raw = self.request_raw(url, query, body, **options)
        try:
            value = json.loads(raw)
            if type(value) is not dict:
                raise ValueError
            return value
        except ValueError:
            raise PanError('PAN_REPLY_INVALID') from None

    def request_raw(self, url, query=None, body=None, limit=MAX_REPLY, headers=None, form=None, metadata=False):
        if metadata and self.provider != '189':
            raise PanError('PAN_REQUEST_INVALID')
        if body is not None and form is not None:
            raise PanError('PAN_REQUEST_INVALID')
        method = 'POST' if body is not None or form is not None else 'GET'
        parsed = urlsplit(url)
        api = self.provider in ('quark', 'uc') and parsed.scheme + '://' + parsed.netloc == API[self.provider]
        auth = self.provider == 'quark' and (method, url) in AUTH_ROUTES
        auth = auth or self.provider == 'uc' and (method, url) in UC_AUTH_ROUTES
        baidu = self.provider == 'baidu' and (method, url) in BAIDU_ROUTES
        file_route = (self.provider == 'xunlei' and method == 'GET'
            and re.fullmatch(r'https://api-pan\.xunlei\.com/drive/v1/files/[A-Za-z0-9_-]{1,128}', url))
        mobile_route = (self.provider == '139' and method == 'POST'
            and re.fullmatch(r'https://personal(?:-[a-z0-9]+){0,3}\.yun\.139\.com/hcy/file/(?:list|getDownloadUrl)', url))
        if (parsed.query or parsed.fragment or parsed.username or parsed.password
                or not (api and (method, parsed.path) in API_ROUTES or auth or baidu
                        or (method, url) in TOKEN_ROUTES.get(self.provider, ()) or file_route or mobile_route)):
            raise PanError('PAN_ORIGIN_REJECTED')
        if query:
            url += '?' + urlencode(query)
        data = json.dumps(body, separators=(',', ':')).encode('utf-8') if body is not None else None
        extra = headers or {}
        if (type(extra) is not dict or len(extra) > 16 or any(
                key not in {'Authorization', 'Origin', 'Referer', 'X-Device-Id', 'X-Canary',
                            'platform', 'app-version', 'loginuuid', 'X-Client-Id', 'X-Device-Sign',
                            'X-Client-Version', 'X-Platform-Version', 'X-Protocol-Version',
                            'X-SDK-Version', 'X-Captcha-Token', 'Did', 'Dt', 'Lt', 'Reqid',
                            'mcloud-client', 'mcloud-sign', 'mcloud-skey', 'X-Deviceinfo',
                            'x-yun-api-version', 'x-yun-app-channel', 'x-yun-client-info',
                            'x-yun-module-type', 'x-yun-svc-type'}
                or type(value) is not str or not 0 < len(value) <= 8192
                or not value.isascii() or re.search(r'[\x00-\x1f\x7f]', value)
                for key, value in extra.items())):
            raise PanError('PAN_HEADERS_INVALID')
        if 'X-Captcha-Token' in extra and not (self.provider == 'xunlei'
                and parsed.hostname == 'api-pan.xunlei.com'):
            raise PanError('PAN_ORIGIN_REJECTED')
        if 'Authorization' in extra and not (
                self.provider == 'aliyun' and parsed.hostname == 'api.alipan.com'
                or self.provider == '123' and parsed.hostname in ('api.123pan.cn', 'www.123pan.cn')
                or self.provider == 'guangya' and parsed.hostname in ('account.guangyapan.com', 'api.guangyapan.com')
                or self.provider == 'xunlei' and (parsed.hostname == 'api-pan.xunlei.com'
                    or parsed.hostname == 'xluser-ssl.xunlei.com' and parsed.path == '/v1/user/me')
                or self.provider == '139' and (mobile_route or url in {
                    'https://user-njs.yun.139.com/user/route/qryRoutePolicy',
                    'https://yun.139.com/orchestration/personalCloud/catalog/v1.0/getDisk',
                    'https://yun.139.com/orchestration/personalCloud/uploadAndDownload/v1.0/downloadRequest'})):
            raise PanError('PAN_ORIGIN_REJECTED')
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json',
                   'Referer': WEB[self.provider] + '/', 'Cache-Control': 'no-store'}
        headers.update(extra)
        if data is not None:
            headers['Content-Type'] = 'application/json'
        if form is not None:
            if type(form) is not dict:
                raise PanError('PAN_REQUEST_INVALID')
            data = urlencode(form).encode('ascii')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        timeout = 8 if self.deadline is None else min(8, self.deadline - self.clock())
        if timeout <= 0:
            raise PanError('PAN_NETWORK_ERROR')
        deadline = self.clock() + timeout
        oauth_error = method == 'POST' and (self.provider, url.split('?', 1)[0]) in {
            ('guangya', 'https://account.guangyapan.com/v1/auth/token'),
            ('xunlei', 'https://xluser-ssl.xunlei.com/v1/auth/token')}
        shield_error = self.provider == 'xunlei' and (parsed.hostname == 'api-pan.xunlei.com'
            or parsed.path == '/v1/shield/captcha/init')
        try:
            try:
                reply = self.opener.open(Request(url, data=data, headers=headers), timeout=timeout)
            except HTTPError as error:
                if not (error.code == 400 and oauth_error or error.code in (400, 401, 403) and shield_error
                        or error.code in (301, 302, 303, 307, 308) and metadata):
                    raise
                reply = error  # OAuth pending is structured, bounded JSON, not success.
            with reply:
                if metadata and reply.status in (301, 302, 303, 307, 308):
                    return b'', reply.status, reply.headers.get('Location')
                if reply.status != 200 and not (reply.status == 400 and oauth_error
                        or reply.status in (400, 401, 403) and shield_error):
                    raise PanError('PAN_HTTP_REJECTED')
                length = reply.headers.get('Content-Length')
                if length is not None:
                    if not re.fullmatch(r'[0-9]{1,10}', str(length)) or int(length) > limit:
                        raise PanError('PAN_REPLY_INVALID')
                    length = int(length)
                raw = bytearray()
                reader = getattr(reply, 'read1', reply.read)
                while True:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        raise PanError('PAN_NETWORK_ERROR')
                    sock = getattr(getattr(getattr(reply, 'fp', None), 'raw', None), '_sock', None)
                    if sock is not None:
                        sock.settimeout(remaining)
                    chunk = reader(min(65536, limit + 1 - len(raw)))
                    if self.clock() >= deadline:
                        raise PanError('PAN_NETWORK_ERROR')
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > limit:
                        raise PanError('PAN_REPLY_INVALID')
                if length is not None and len(raw) != length:
                    raise PanError('PAN_REPLY_INVALID')
                if shield_error and reply.status != 200:
                    try:
                        error_value = json.loads(raw)
                        if type(error_value) is not dict or not (error_value.get('error') or error_value.get('error_code')):
                            raise ValueError
                    except ValueError:
                        raise PanError('PAN_REPLY_INVALID') from None
            return (bytes(raw), reply.status, None) if metadata else bytes(raw)
        except PanError:
            raise
        except HTTPError as error:
            error.close()
            raise PanError('PAN_LOGIN_REQUIRED' if error.code in (401, 403) else 'PAN_HTTP_REJECTED') from None
        except (HTTPException, ValueError):
            raise PanError('PAN_REPLY_INVALID') from None
        except OSError:
            raise PanError('PAN_NETWORK_ERROR') from None
