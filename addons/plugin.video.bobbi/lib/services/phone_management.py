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
PLAYBACK_SCOPES = frozenset(('playback_read', 'playback_control'))
ACTION_SCOPE = {
    'catalog_sources': 'catalog_read', 'catalog_items': 'catalog_read', 'catalog_jobs': 'catalog_read',
    'catalog_history': 'catalog_read',
    'catalog_query': 'catalog_read', 'catalog_item': 'catalog_read', 'catalog_receipt': 'catalog_review',
    'catalog_candidates': 'catalog_read', 'catalog_group': 'catalog_read',
    'catalog_preview': 'catalog_review', 'catalog_apply': 'catalog_review',
    'catalog_cancel': 'catalog_tasks', 'catalog_scan': 'catalog_tasks',
    'playback_presentation': 'playback_read', 'playback_receipt': 'playback_read',
    'playback_command': 'playback_control',
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
    if action in ('playback_presentation', 'playback_receipt', 'playback_command'):
        from bobbi_core.playback_presentation import command, expected
        try:
            if action == 'playback_presentation' and not args:
                return {}
            if action == 'playback_command':
                return command(args)
            if action == 'playback_receipt' and set(args) == {'expected', 'command_id'}:
                return dict(expected=expected(args['expected']), command_id=_id(args['command_id']))
        except (ValueError, TypeError, KeyError):
            pass
        raise PhoneError('INVALID_REQUEST', 400)
    allowed = {
        'catalog_sources': {'offset', 'limit'}, 'catalog_items': {'source', 'state', 'offset', 'limit'},
        'catalog_jobs': {'task', 'offset', 'limit'}, 'catalog_preview': {'commands'},
        'catalog_history': {'offset', 'limit'},
        'catalog_query': {'query', 'cursor', 'limit'}, 'catalog_item': {'file_id'}, 'catalog_receipt': {'request_id'},
        'catalog_candidates': {'query', 'media_kind', 'year'},
        'catalog_group': {'file_id', 'source_id', 'offset', 'limit', 'projection_revision'},
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
    elif action == 'catalog_candidates':
        from lib.clients.tmdb.catalog_candidates import parameters as candidate_parameters
        try:
            args = candidate_parameters(args)
        except (ValueError, TypeError):
            raise PhoneError('INVALID_REQUEST', 400) from None
    elif action == 'catalog_group':
        _id(args.get('file_id'), 64)
        args['offset'], args['limit'] = _page(args)
        if args.get('source_id') is not None:
            _id(args['source_id'])
        if args.get('projection_revision') is not None and (type(args['projection_revision']) is not int or args['projection_revision'] < 0):
            raise PhoneError('INVALID_REQUEST', 400)
    elif action == 'catalog_query':
        from bobbi_core.catalog_query import parameters as query_parameters
        try:
            args['query'] = query_parameters(args.get('query', {}))
        except (ValueError, TypeError):
            raise PhoneError('INVALID_REQUEST', 400) from None
        args['limit'] = args.get('limit', 20)
        if type(args['limit']) is not int or not 1 <= args['limit'] <= 32:
            raise PhoneError('INVALID_REQUEST', 400)
        if args.get('cursor') is not None:
            _id(args['cursor'])
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
        _id(next(iter(args.values())), 64 if action == 'catalog_item' else 32)
    return args


# Recursive field projection is a second, browser-specific egress boundary.
# Never pass a future Host result field through merely because the RPC is local.
PUBLIC_FIELDS = frozenset(('items', 'next_offset', 'id', 'name', 'parent', 'truncated', 'file',
    'state', 'reason', 'candidates', 'revision', 'mapping', 'provenance', 'origin', 'season',
    'episode', 'year', 'kind', 'title', 'tmdb_id', 'version', 'status', 'before', 'after', 'action',
    'schema', 'task_id', 'stage', 'counts', 'pages', 'scanned', 'discovered', 'updated_at',
    'cancel_requested', 'result_summary', 'available', 'after_state', 'position', 'duration', 'completion_reason', 'index',
    'observation', 'coverage', 'availability', 'recheck_required', 'indexed_count', 'latest_state',
    'work_title', 'version_label', 'description', 'navigation', 'view', 'parent_entity_id',
    'supplement', 'before_supplement', 'after_supplement', 'metadata_key', 'parent_file_id',
    'parent_revision', 'parent_evidence', 'observation_key', 'needs_review'))

# Query summaries have their own read budget; this never enlarges review batches.
QUERY_FIELDS = frozenset(('schema', 'items', 'next_cursor', 'projection_revision', 'truncated',
    'entity_id', 'entity_kind', 'display_title', 'media_kind', 'season', 'episode', 'review_state',
    'availability', 'variant_count', 'available_count', 'source_count', 'metadata_key', 'year', 'art', 'poster', 'thumb', 'fanart',
    'file_name', 'file_size', 'version_label', 'sources', 'source_total', 'id', 'name',
    'review_revision', 'observation_key', 'supplement', 'kind', 'title', 'parent_file_id',
    'parent_revision', 'parent_evidence', 'state'))
CANDIDATE_FIELDS = frozenset(('items', 'media_kind', 'tmdb_id', 'title', 'original_title',
                            'year', 'poster_path', 'basis', 'mismatch'))
GROUP_FIELDS = PUBLIC_FIELDS | frozenset(('group_id', 'anchor_id', 'source_id', 'projection_revision'))
PLAYBACK_FIELDS = frozenset(('available', 'reason', 'expected', 'boot_id', 'epoch', 'request_id',
    'native_instance', 'file_sha256', 'selection_epoch', 'expected_sequence', 'user_intent',
    'subtitle_intent', 'audio_intent', 'position_ms', 'duration_ms', 'can_seek', 'subtitle_visible',
    'subtitle_status', 'audio_status', 'audio', 'subtitles', 'chapters', 'name', 'language', 'index',
    'stream_key', 'selected', 'audio_truncated', 'subtitles_truncated', 'chapters_truncated', 'command_id', 'status'))


def public(value, depth=0, fields=PUBLIC_FIELDS, max_items=5):
    if depth > 6:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {key: public(item, depth + 1, fields, max_items) for key, item in value.items() if key in fields}
    if type(value) is list:
        if len(value) > max_items:
            raise PhoneError('INVALID_REPLY', 502)
        return [public(item, depth + 1, fields, max_items) for item in value]
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 1024 and '://' not in value:
        return value
    raise PhoneError('INVALID_REPLY', 502)


class PhoneManagement:
    def __init__(self, expected, origin, rpc=None, clock=time.monotonic, scopes=SCOPES, profile_binding=None):
        from bobbi_platform.pan_accounts import scope
        from bobbi_platform.paths import ProfileBinding
        from bobbi_platform.runtime import bind_call
        # An injected transport may supply its own binding in fixtures. The
        # production path always captures both Kodi roots and this exact Host.
        self.profile_binding = profile_binding or (ProfileBinding() if rpc is None else None)
        if rpc is None:
            rpc = bind_call(self.profile_binding.root('script.module.bobbi.platform') / 'runtime.json')
            self.profile_binding.require_current()
        self.mounted = type(expected) is dict and expected.get('reference_kind') == 'mounted_path'
        if self.mounted and set(scopes) & PLAYBACK_SCOPES:
            raise PhoneError('ACTION_FORBIDDEN')
        if self.mounted:
            if set(expected) - {'reference_kind', 'source_id', 'namespace', 'generation'}:
                raise PhoneError('INVALID_REQUEST', 400)
            self.expected = dict(reference_kind='mounted_path', source_id=_id(expected.get('source_id')),
                                 namespace=_id(expected.get('namespace'), 64), generation='')
        else:
            self.expected = scope(expected, authenticated=True)
        parts = urlsplit(origin)
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            raise PhoneError('ORIGIN_FORBIDDEN') from None
        if (parts.scheme != 'http' or not (address.is_private or address.is_loopback)
                or parts.path or parts.query or parts.fragment or parts.username or parts.password
                or not parts.port or not 1 <= parts.port <= 65535 or not set(scopes) <= SCOPES | PLAYBACK_SCOPES
                or ('playback_control' in scopes and 'playback_read' not in scopes)):
            raise PhoneError('ORIGIN_FORBIDDEN')
        self.origin, self.host, self.rpc, self.clock = origin, parts.netloc, rpc, clock
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
        self._profile()
        if self.revoked.is_set() or self.closed or self.clock() >= self.expires:
            self.revoke()
            raise PhoneError('SESSION_EXPIRED', 401)

    def _profile(self):
        try:
            if self.profile_binding is not None:
                self.profile_binding.require_current()
        except (OSError, ValueError, RuntimeError):
            self.revoke()
            raise PhoneError('ACCOUNT_OR_SERVICE_CHANGED', 401) from None

    def _rpc(self, action, args, timeout):
        self._profile()
        result = self.rpc(action, args, timeout=timeout)
        self._profile()
        return result

    def _account(self):
        try:
            if self.mounted:
                current = self._rpc('catalog_mount_scope', {'source_id': self.expected['source_id']}, timeout=2)
                if type(current) is not dict:
                    raise ValueError
                current = current.get('scope', current)
                if type(current) is not dict:
                    raise ValueError
                if any(current.get(key) != self.expected[key] for key in ('reference_kind', 'source_id', 'namespace')):
                    raise ValueError
            else:
                rows = self._rpc('pan_status', {}, timeout=2)['providers']
                current = next(row['account'] for row in rows if row['provider'] == self.expected['provider'])
                if current != self.expected:
                    raise ValueError
        except (ValueError, OSError, KeyError, TypeError, StopIteration, RuntimeError):
            self.revoke()
            raise PhoneError('ACCOUNT_OR_SERVICE_CHANGED', 401) from None

    def _host(self, action, args):
        self._profile()
        if action in ('playback_presentation', 'playback_command', 'playback_receipt'):
            body = dict(operation=action, account_scope=self.expected)
            if action == 'playback_command':
                body['command'] = args
            else:
                body.update(args)
            return self._rpc('playback', body, timeout=3)
        if not self.mounted:
            return self._rpc(action, dict(args, expected=self.expected), timeout=3)
        if action == 'catalog_history':
            raise PhoneError('ACTION_FORBIDDEN')
        for value in (args.get('source'), args.get('source_id'), (args.get('query') or {}).get('source_id')):
            if value is not None and value != self.expected['source_id']:
                raise PhoneError('ACTION_FORBIDDEN')
        if action == 'catalog_sources':
            listed = self._rpc('catalog_mount_sources', {}, timeout=3)
            # The browser grant covers exactly one registered namespace. Keep
            # other source names and observations out of its public response.
            return dict(items=[row for row in listed['items'] if row['id'] == self.expected['source_id']])
        params = dict(args, source_id=self.expected['source_id'], namespace=self.expected['namespace'])
        return self._rpc(action.replace('catalog_', 'catalog_mount_', 1), params, timeout=3)

    def _session_description(self):
        return dict(csrf=self._csrf, expires_in=int(self.expires - self.clock()),
                    scopes=sorted(self.scopes),
                    catalog_kind='mounted' if self.mounted else 'native',
                    source_id=self.expected['source_id'] if self.mounted else None)

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
                return self._session_description(), (
                    COOKIE + '=' + self._session + '; HttpOnly; SameSite=Strict; Path=/manage/api; Max-Age=900')
            self._authorize(headers, csrf=path != '/manage/api/session')
            self._account()
            if path == '/manage/api/session' and not body:
                return self._session_description(), None
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
                if action == 'catalog_candidates':
                    from lib.clients.tmdb.catalog_candidates import search
                    try:
                        result = search(**args, cancelled=self.revoked.is_set)
                    except (ValueError, OSError, RuntimeError):
                        self._live()
                        raise PhoneError('CATALOG_CANDIDATE_UNAVAILABLE', 502) from None
                else:
                    result = self._host(action, host_args)
            except PhoneError:
                raise
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
            if action in ('playback_presentation', 'playback_command', 'playback_receipt'):
                result = public(result, fields=PLAYBACK_FIELDS, max_items=32)
            elif action == 'catalog_query':
                result = public(result, fields=QUERY_FIELDS, max_items=32)
            else:
                fields = CANDIDATE_FIELDS if action == 'catalog_candidates' else GROUP_FIELDS if action == 'catalog_group' else PUBLIC_FIELDS
                result = public(result, fields=fields)
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
