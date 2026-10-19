"""Narrow official share-read API. Credentials never leave the box/API origin."""
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from bobbi_platform.paths import profile
CREDENTIAL = profile(name='115-os_linux.json')
MAX_RESPONSE = 2 * 1024 * 1024


class ShareError(RuntimeError):
    """Only fixed safe codes, never server messages or request URLs."""
    CODES = {'login_required', 'share_unavailable', 'network', 'invalid_response',
             'cancelled', 'deadline', 'identity_changed', 'invalid_locator', 'refresh_required'}

    def __init__(self, code):
        self.code = code if code in self.CODES else 'invalid_response'
        super().__init__(self.code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ShareError('invalid_response')


def valid_cdn(url):
    try:
        value = urllib.parse.urlsplit(url)
        host = value.hostname or ''
        return (len(url) <= 8192 and value.scheme in ('http', 'https') and not value.username
                and not value.password and value.port in (None, 80, 443) and not value.fragment
                and not re.search(r'[\x00-\x20\x7f|]', url)
                and any(host == root or host.endswith('.' + root)
                        for root in ('115.com', '115cdn.com', '115cdn.net')))
    except (TypeError, ValueError):
        return False


class Client:
    def __init__(self, credential=CREDENTIAL, opener=None):
        try:
            path = Path(credential)
            if path.stat().st_size > 16384 or path.is_symlink():
                raise ValueError()
            session = json.loads(path.read_text(encoding='utf-8'))
            cookies = session['cookies']
            if session.get('app') != 'os_linux' or any(not cookies.get(k) for k in ('UID', 'CID', 'SEID')):
                raise ValueError()
            if any(not isinstance(v, str) or re.search(r'[\s;\r\n]', v) for v in cookies.values()):
                raise ValueError()
            self.cookie = '; '.join(k + '=' + cookies[k] for k in ('UID', 'CID', 'SEID', 'KID') if k in cookies)
            self.ua = session['user_agent']
            if not isinstance(self.ua, str) or re.search(r'[\x00-\x1f\x7f]', self.ua):
                raise ValueError()
        except (OSError, ValueError, TypeError, KeyError):
            raise ShareError('login_required') from None
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path, share, params, deadline, cancelled=None):
        if cancelled is not None and cancelled.is_set():
            raise ShareError('cancelled')
        remaining = deadline - time.monotonic()
        if remaining <= .15:
            raise ShareError('deadline')
        if path not in ('/share/search', '/os_linux/2.0/share/downurl'):
            raise ShareError('invalid_locator')
        values = dict(share_code=share['code'], receive_code=share['password'], **params)
        base = 'https://webapi.115.com'
        if path == '/os_linux/2.0/share/downurl':
            base = 'https://proapi.115.com'
            values['app_ver'] = '36.2.28'
        request = urllib.request.Request(base + path + '?' + urllib.parse.urlencode(values),
            headers={'User-Agent': self.ua, 'Referer': 'https://115.com/', 'Cookie': self.cookie,
                     'Cache-Control': 'no-store'})
        try:
            with self.opener.open(request, timeout=min(4.0, remaining)) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ShareError('invalid_response')
            result = json.loads(raw)
        except ShareError:
            raise
        except (OSError, ValueError, urllib.error.URLError):
            raise ShareError('network') from None
        if not isinstance(result, dict):
            raise ShareError('invalid_response')
        if not result.get('state'):
            code = str(result.get('errno', result.get('code', '')))
            raise ShareError('login_required' if code in ('99', '990001', '40101004') else 'share_unavailable')
        data = result.get('data')
        if not isinstance(data, dict):
            raise ShareError('invalid_response')
        return data

    def search(self, share, query, deadline, cancelled=None):
        data = self.get('/share/search', share, dict(cid='', search_value=query, offset=0, limit=100), deadline, cancelled)
        values = data.get('list')
        if not isinstance(values, list):
            raise ShareError('invalid_response')
        rows = []
        for value in values[:100]:
            if not isinstance(value, dict):
                continue
            fid, name = str(value.get('fid') or ''), value.get('n')
            try:
                size = int(value.get('s') or 0)
            except (ValueError, TypeError):
                continue
            if not re.fullmatch(r'\d{1,32}', fid) or not isinstance(name, str) or size <= 0:
                continue
            if len(name) > 1024 or re.search(r'[\x00-\x1f\x7f]', name):
                continue
            rows.append(dict(fid=fid, name=name, size=size))
        return rows

    def resolve(self, share, row, deadline):
        data = self.get('/os_linux/2.0/share/downurl', share, dict(file_id=row['fid'], dl=1), deadline)
        if (str(data.get('fid')) != row['fid'] or data.get('fn') != row['name']
                or str(data.get('fs')) != str(row['size'])):
            raise ShareError('identity_changed')
        value = data.get('url')
        url = value.get('url') if isinstance(value, dict) else value
        if not isinstance(url, str) or not valid_cdn(url):
            raise ShareError('invalid_locator')
        return url + '|User-Agent=' + urllib.parse.quote(self.ua, safe='')
