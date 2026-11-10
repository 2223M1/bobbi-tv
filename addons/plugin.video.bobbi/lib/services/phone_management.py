"""Optional, TV-approved browser session over the existing local Host APIs.

This owns no sources, cloud credentials, media files, jobs or playback. Only a
short-lived single-browser permission is retained in memory.
"""
import hmac
from hashlib import sha256
from http.cookies import SimpleCookie
import ipaddress
import json
import re
import secrets
from threading import Event, RLock
import time
from urllib.parse import urlsplit

MAX_BODY = 8192
MAX_REPLY = 16384
SESSION_SECONDS = 900
COOKIE = 'bobbi_management'
SCOPES = frozenset(('catalog_read', 'catalog_review', 'catalog_tasks'))
ACTION_SCOPE = {
    'catalog_sources': 'catalog_read', 'catalog_items': 'catalog_read', 'catalog_jobs': 'catalog_read',
    'catalog_history': 'catalog_read',
    'catalog_preview': 'catalog_review', 'catalog_apply': 'catalog_review',
    'catalog_cancel': 'catalog_tasks', 'catalog_scan': 'catalog_tasks',
}


class PhoneError(ValueError):
    def __init__(self, code, status=403):
        super().__init__(code)
        self.status = status


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _id(value, length=32):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}' % length, value):
        raise PhoneError('INVALID_REQUEST', 400)
    return value


def _page(args):
    offset, limit = args.get('offset', 0), args.get('limit', 5)
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 5:
        raise PhoneError('INVALID_REQUEST', 400)
    return offset, limit


def parameters(action, args):
    if type(args) is not dict or len(encode(args)) > MAX_BODY:
        raise PhoneError('INVALID_REQUEST', 400)
    allowed = {
        'catalog_sources': {'offset', 'limit'}, 'catalog_items': {'source', 'state', 'offset', 'limit'},
        'catalog_jobs': {'task', 'offset', 'limit'}, 'catalog_preview': {'commands'},
        'catalog_history': {'offset', 'limit'},
        'catalog_apply': {'commands', 'request_id'}, 'catalog_cancel': {'task_id'}, 'catalog_scan': {'source_id'},
    }
    if action not in allowed or not set(args) <= allowed[action]:
        raise PhoneError('ACTION_FORBIDDEN')
    args = dict(args)
    if action in ('catalog_sources', 'catalog_items', 'catalog_jobs', 'catalog_history'):
        args['offset'], args['limit'] = _page(args)
        for key in ('source', 'task'):
            if args.get(key) is not None:
                _id(args[key])
        if args.get('state') not in (None, 'unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored'):
            raise PhoneError('INVALID_REQUEST', 400)
    elif action in ('catalog_preview', 'catalog_apply'):
        if (set(args) != allowed[action] or type(args['commands']) is not list
                or not 1 <= len(args['commands']) <= 5):
            raise PhoneError('INVALID_REQUEST', 400)
        from bobbi_core.catalog_review import command
        try:
            args['commands'] = [command(value) for value in args['commands']]
        except (ValueError, TypeError, KeyError):
            raise PhoneError('INVALID_REQUEST', 400) from None
        if action == 'catalog_apply':
            _id(args['request_id'])
    else:
        if set(args) != allowed[action]:
            raise PhoneError('INVALID_REQUEST', 400)
        _id(next(iter(args.values())))
    return args


# Recursive field projection is a second, browser-specific egress boundary.
# Never pass a future Host result field through merely because the RPC is local.
PUBLIC_FIELDS = frozenset(('items', 'next_offset', 'id', 'name', 'parent', 'truncated', 'file',
    'state', 'reason', 'candidates', 'revision', 'mapping', 'provenance', 'origin', 'season',
    'episode', 'year', 'kind', 'title', 'tmdb_id', 'version', 'status', 'before', 'after', 'action',
    'schema', 'task_id', 'stage', 'counts', 'pages', 'scanned', 'discovered', 'updated_at',
    'cancel_requested', 'result_summary', 'available', 'after_state', 'position', 'duration', 'completion_reason'))


def public(value, depth=0):
    if depth > 6:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {key: public(item, depth + 1) for key, item in value.items() if key in PUBLIC_FIELDS}
    if type(value) is list:
        if len(value) > 5:
            raise PhoneError('INVALID_REPLY', 502)
        return [public(item, depth + 1) for item in value]
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 1024 and '://' not in value:
        return value
    raise PhoneError('INVALID_REPLY', 502)


class PhoneManagement:
    def __init__(self, expected, origin, rpc=None, clock=time.monotonic, scopes=SCOPES):
        from bobbi_platform.pan_accounts import scope
        from bobbi_platform.runtime import call
        self.expected = scope(expected, authenticated=True)
        parts = urlsplit(origin)
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            raise PhoneError('ORIGIN_FORBIDDEN') from None
        if (parts.scheme != 'http' or not (address.is_private or address.is_loopback)
                or parts.path or parts.query or parts.fragment or parts.username or parts.password
                or not parts.port or not 1 <= parts.port <= 65535 or not set(scopes) <= SCOPES):
            raise PhoneError('ORIGIN_FORBIDDEN')
        self.origin, self.host, self.rpc, self.clock = origin, parts.netloc, rpc or call, clock
        self.scopes, self.lock = frozenset(scopes), RLock()
        self.revoked = Event()
        self.previews = {}
        self._challenge, self._session, self._csrf = secrets.token_urlsafe(32), None, None
        self.expires, self.closed = clock() + SESSION_SECONDS, False

    def __repr__(self):
        return '<Phone management: session hidden>'

    @property
    def pairing_url(self):
        with self.lock:
            if self.closed or self._challenge is None:
                raise PhoneError('SESSION_EXPIRED', 401)
            return self.origin + '/manage#' + self._challenge

    def check_origin(self, headers, write=True):
        if headers.get('Host') != self.host or write and headers.get('Origin') != self.origin:
            raise PhoneError('ORIGIN_FORBIDDEN')
        if headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            raise PhoneError('ORIGIN_FORBIDDEN')

    def _live(self):
        if self.revoked.is_set() or self.closed or self.clock() >= self.expires:
            self.revoke()
            raise PhoneError('SESSION_EXPIRED', 401)

    def _account(self):
        try:
            rows = self.rpc('pan_status', {}, timeout=2)['providers']
            current = next(row['account'] for row in rows if row['provider'] == self.expected['provider'])
            if current != self.expected:
                raise ValueError
        except (ValueError, OSError, KeyError, TypeError, StopIteration, RuntimeError):
            self.revoke()
            raise PhoneError('ACCOUNT_OR_SERVICE_CHANGED', 401) from None

    def _authorize(self, headers, csrf=True):
        self._live()
        try:
            cookie = SimpleCookie()
            cookie.load(headers.get('Cookie', ''))
            token = cookie[COOKIE].value
        except (KeyError, TypeError, ValueError):
            raise PhoneError('PAIRING_REQUIRED', 401) from None
        if (self._session is None or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token)
                or not hmac.compare_digest(token, self._session)):
            raise PhoneError('PAIRING_REQUIRED', 401)
        receipt = headers.get('X-Bobbi-CSRF', '')
        if csrf and (not re.fullmatch(r'[A-Za-z0-9_-]{43}', receipt)
                     or not hmac.compare_digest(receipt, self._csrf)):
            raise PhoneError('CSRF_REJECTED')

    def handle(self, path, headers, raw):
        """Return result + optional cookie; all writes happen after this gate."""
        with self.lock:
            self.check_origin(headers)
            self._live()
            if len(raw) > MAX_BODY:
                raise PhoneError('REQUEST_TOO_LARGE', 413)
            try:
                body = json.loads(raw)
                if type(body) is not dict:
                    raise ValueError
            except (ValueError, TypeError):
                raise PhoneError('INVALID_REQUEST', 400) from None
            if path == '/manage/api/pair':
                code = body.get('code')
                if (set(body) != {'code'} or type(code) is not str or len(code) != 43
                        or self._challenge is None or not hmac.compare_digest(code, self._challenge)):
                    raise PhoneError('PAIRING_REJECTED', 401)
                self._account()
                self._challenge = None
                self._session, self._csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                return dict(csrf=self._csrf, expires_in=int(self.expires - self.clock())), (
                    COOKIE + '=' + self._session + '; HttpOnly; SameSite=Strict; Path=/manage/api; Max-Age=900')
            self._authorize(headers, csrf=path != '/manage/api/session')
            self._account()
            if path == '/manage/api/session' and not body:
                return dict(csrf=self._csrf, expires_in=int(self.expires - self.clock())), None
            if path == '/manage/api/revoke' and not body:
                self.revoke()
                return dict(revoked=True), COOKIE + '=; HttpOnly; SameSite=Strict; Path=/manage/api; Max-Age=0'
            if path != '/manage/api' or set(body) != {'action', 'params'}:
                raise PhoneError('ACTION_FORBIDDEN')
            action = body['action']
            if type(action) is not str or ACTION_SCOPE.get(action) not in self.scopes:
                raise PhoneError('ACTION_FORBIDDEN')
            args = parameters(action, body['params'])
            digest = sha256(encode(args.get('commands', []))).hexdigest()
            if action == 'catalog_apply' and self.clock() - self.previews.get(digest, float('-inf')) > 120:
                raise PhoneError('PREVIEW_REQUIRED', 409)
            self._live()
            host_args = {} if action == 'catalog_sources' else args
            try:
                result = self.rpc(action, dict(host_args, expected=self.expected), timeout=3)
            except (ValueError, OSError, RuntimeError) as error:
                from bobbi_platform.runtime import CATALOG_ERRORS
                code = str(error)
                if code in CATALOG_ERRORS and code not in ('CATALOG_ACCOUNT_MISMATCH', 'CATALOG_SERVICE_CLOSED',
                        'CATALOG_SCHEMA_UNSUPPORTED', 'CATALOG_STORAGE_UNSAFE'):
                    raise PhoneError(code, 409 if code == 'CATALOG_SCAN_BUSY' else 400) from None
                self.revoke()
                raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
            self._account()
            self._live()
            if action == 'catalog_sources':
                rows, offset, limit = result['items'], args['offset'], args['limit']
                result = dict(items=rows[offset:offset+limit], next_offset=(offset+limit if len(rows) > offset+limit else None))
            result = public(result)
            if len(encode(result)) > MAX_REPLY:
                raise PhoneError('REPLY_TOO_LARGE', 502)
            if action == 'catalog_preview':
                self.previews[digest] = self.clock()
                while len(self.previews) > 8:
                    del self.previews[next(iter(self.previews))]
            return result, None

    def revoke(self):
        # Immediate logical revocation, even while an already-admitted domain
        # call is in flight. This does not undo a committed mapping mutation.
        self.revoked.set()
        self.closed = True
        self._session = self._csrf = self._challenge = None
