"""Narrow official share-read API. Credentials never leave the box/API origin."""
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from bobbi_platform.paths import profile
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
    def __init__(self, credential=None, opener=None, session=None, account_scope=None):
        self.account_scope = None
        try:
            if session is None:
                path = Path(credential) if credential is not None else profile(name='115-os_linux.json')
                if path.stat().st_size > 16384 or path.is_symlink():
                    raise ValueError()
                session = json.loads(path.read_text(encoding='utf-8'))
            if account_scope is not None:
                from bobbi_platform.account_manager import validate_snapshot, account_id
                self.account_scope = validate_snapshot(account_scope, authenticated=True)
                if self.account_scope['account_id'] != account_id(session):
                    raise ValueError()
            cookies = session['cookies']
            if session.get('app') != 'os_linux' or any(not cookies.get(k) for k in ('UID', 'CID', 'SEID')):
                raise ValueError()
            if any(not isinstance(v, str) or re.search(r'[\s;\r\n]', v) for v in cookies.values()):
                raise ValueError()
            self.cookie = '; '.join(k + '=' + cookies[k] for k in ('UID', 'CID', 'SEID', 'KID') if k in cookies)
            self.ua = session['user_agent']
            if not isinstance(self.ua, str) or re.search(r'[\x00-\x1f\x7f]', self.ua):
                raise ValueError()
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            raise ShareError('login_required') from None
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path, share, params, deadline, cancelled=None):
        def guard():
            if cancelled is not None and (cancelled.is_set() if hasattr(cancelled, 'is_set') else cancelled()):
                raise ShareError('cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ShareError('deadline')
            return remaining
        remaining = guard()
        if path not in ('/share/search', '/share/snap', '/os_linux/2.0/share/downurl'):
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
                headers = getattr(response, 'headers', {})
                length = headers.get('Content-Length')
                if length is not None:
                    if not re.fullmatch(r'[0-9]{1,10}', str(length)) or int(length) > MAX_RESPONSE:
                        raise ShareError('invalid_response')
                    length = int(length)
                raw = bytearray()
                reader = getattr(response, 'read1', response.read)
                while True:
                    remaining = guard()
                    # HTTPResponse.read1 performs at most one underlying read;
                    # read(n) can wait for all n bytes while a peer drip-feeds.
                    sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                    if sock is not None:
                        sock.settimeout(min(4.0, remaining))
                    chunk = reader(min(65536, MAX_RESPONSE + 1 - len(raw)))
                    guard()
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise ShareError('invalid_response')
                if length is not None and len(raw) != length:
                    raise ShareError('invalid_response')
            result = json.loads(raw)
        except ShareError:
            raise
        except (OSError, ValueError, urllib.error.URLError):
            guard()
            raise ShareError('network') from None
        if not isinstance(result, dict):
            raise ShareError('invalid_response')
        guard()
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

    def resolve_reference(self, share, fid, deadline, cancelled=None):
        """Resolve one explicit same-share text FID, without a directory scan.

        Unlike a selected video tuple, a catalogue subtitle reference does not
        carry trusted filename/size metadata. Obtain those from the existing
        official share endpoint, validate them, and return them for the caller's
        work/episode and downloaded-byte checks. Never accepts a personal FID
        or creates an offline/cloud task.
        """
        if not isinstance(fid, str) or not re.fullmatch(r'[0-9]{1,32}', fid):
            raise ShareError('invalid_locator')
        data = self.get('/os_linux/2.0/share/downurl', share, dict(file_id=fid, dl=1), deadline, cancelled)
        if str(data.get('fid')) != fid:
            raise ShareError('identity_changed')
        name, size = data.get('fn'), data.get('fs')
        if (not isinstance(name, str) or not 1 <= len(name) <= 1024
                or re.search(r'[\\/\x00-\x1f\x7f]', name)
                or name.rsplit('.', 1)[-1].casefold() not in ('ass', 'ssa', 'srt', 'vtt')
                or '.' not in name):
            raise ShareError('invalid_response')
        if isinstance(size, str) and re.fullmatch(r'[0-9]{1,10}', size):
            size = int(size)
        if type(size) is not int or not 0 < size <= 2 * 1024 * 1024:
            raise ShareError('invalid_response')
        value = data.get('url')
        url = value.get('url') if isinstance(value, dict) else value
        if not isinstance(url, str) or not valid_cdn(url):
            raise ShareError('invalid_locator')
        return dict(fid=fid, name=name, size=size,
                    resolved=url + '|User-Agent=' + urllib.parse.quote(self.ua, safe=''))

    def list_directory(self, share, parent, offset, limit, deadline, cancelled=None):
        if (not re.fullmatch(r'\d{1,32}', str(parent)) or type(offset) is not int or offset < 0
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ShareError('invalid_locator')
        data = self.get('/share/snap', share, dict(cid=str(parent), offset=offset, limit=limit),
                        deadline, cancelled)
        values = data.get('list')
        if not isinstance(values, list) or len(values) > limit:
            raise ShareError('invalid_response')
        rows = []
        for value in values:
            if not isinstance(value, dict):
                continue
            fid, name = str(value.get('fid') or ''), value.get('n')
            is_dir = not bool(fid)
            fid = str(value.get('cid') or '') if is_dir else fid
            try:
                size = int(value.get('s') or 0)
            except (TypeError, ValueError):
                continue
            if (not re.fullmatch(r'\d{1,32}', fid) or not isinstance(name, str)
                    or not 0 < len(name) <= 1024 or re.search(r'[\x00-\x1f\x7f]', name)
                    or size < 0 or (not is_dir and size == 0)):
                continue
            rows.append(dict(fid=fid, name=name, size=size, is_dir=is_dir))
        total = data.get('count')
        if isinstance(total, str) and re.fullmatch(r'\d{1,12}', total):
            total = int(total)
        total = total if type(total) is int and total >= 0 else None
        return dict(rows=rows, total=total)
