"""One Host-owned adapter into ShareStream for authorized finite HTTP media."""
from functools import partial
from hashlib import sha256
import json
import re
from threading import Lock, local
from urllib.parse import urlencode, urlsplit

from bobbi_core.library_contract import LibraryError, direct_url
from bobbi_core.server_ref import identifier
from bobbi_core.share_stream import ShareStream
from bobbi_core.t4 import ALLOWED_HEADERS
from .libraries import Registry
from .pan_accounts import PanError
from .source_media_http import Session, evidence, probe_stream
from .t4_tokens import T4TokenStore

ALLOWED_STREAM_HEADER_NAMES = frozenset(ALLOWED_HEADERS.values()) | {'If-Match'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def local_media_url(result):
    if (
        not isinstance(result, dict)
        or not ({'size', 'url'} <= set(result) <= {'size', 'url', 'identity_mode', 'play_session_id'})
        or type(result['size']) is not int
        or not 0 < result['size'] < 2**63
        or type(result['url']) is not str
        or not re.fullmatch(
            r'http://127\.0\.0\.1:[0-9]{1,5}/stream/[0-9a-f]{32}/video\.[a-z0-9]+',
            result['url'],
        )
        or not 0 < urlsplit(result['url']).port <= 65535
        or (
            'play_session_id' in result
            and (
                type(result['play_session_id']) is not str
                or len(result['play_session_id']) > 128
                or any(ord(c) < 32 for c in result['play_session_id'])
            )
        )
    ):
        raise LibraryError('SOURCE_STREAM_INVALID')
    return result['url']


class SourceStreams:
    def __init__(self, root, current, session_factory=Session):
        self.root = root
        self.path, self.current = root / 'libraries.sqlite3', current
        self.token_db_path = root / 't4-tokens.sqlite3'
        self.sessions, self.lock = session_factory, Lock()
        self._active_policy = local()
        self.transport, self.closed = None, False

    def _dispatch_origin_policy(self, target_url: str) -> None:
        policy = getattr(self._active_policy, 'fn', None)
        if policy is None:
            if self.closed or not self.current():
                raise LibraryError('SOURCE_STREAM_CHANGED')
            return
        policy(target_url)

    def _transport_sessions(self):
        if self.sessions is Session:
            return partial(Session, max_redirects=3, origin_policy=self._dispatch_origin_policy)

        def wrapped_factory():
            sess = self.sessions()
            if isinstance(sess, Session) and sess.origin_policy is None:
                sess.origin_policy = self._dispatch_origin_policy
            return sess

        return wrapped_factory

    def source(self, body):
        if self.closed or not self.current():
            raise LibraryError('SOURCE_STREAM_CHANGED')
        store = Registry(self.path, read_only=True)
        try:
            source, version = store.source_snapshot(body['source_id'])
        finally:
            store.close()
        if version != body['generation']:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return source

    def _validate_emby_selection(self, source, selection):
        if (
            source.kind != 'media_server'
            or source.metadata.get('provider') != 'emby'
            or not source.password
            or not isinstance(selection, dict)
            or not ({'kind', 'server_id', 'user_id', 'item_id', 'media_source_id'} <= set(selection) <= {
                'kind', 'server_id', 'user_id', 'item_id', 'media_source_id', 'open_session',
            })
            or selection.get('kind') != 'emby_http'
            or type(selection.get('open_session', False)) is not bool
        ):
            raise LibraryError('SOURCE_STREAM_INVALID')
        try:
            srv_id = identifier(selection['server_id'])
            usr_id = identifier(selection['user_id'])
            itm_id = identifier(selection['item_id'])
            med_id = identifier(selection['media_source_id'])
        except ValueError:
            raise LibraryError('SOURCE_STREAM_INVALID') from None
        if srv_id != source.metadata.get('server_id') or usr_id != source.metadata.get('user_id'):
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return srv_id, usr_id, itm_id, med_id, bool(selection.get('open_session', False))

    def _make_origin_policy(self, body):
        selection = body['selection']
        kind = selection.get('kind')

        def verify_hop(target_url: str) -> None:
            live_source = self.source(body)
            if kind == 'strm':
                return
            if kind == 't4':
                from .t4_http import _media_origin_allowed, canonical_media_origin, site_for_choice
                site = site_for_choice(live_source, selection)
                with T4TokenStore(self.token_db_path, read_only=True) as tstore:
                    approved = tstore.approved_origins(live_source.id, body['generation'])
                if not _media_origin_allowed(target_url, site, approved):
                    err = LibraryError('T4_MEDIA_ORIGIN')
                    err.blocked_origin = canonical_media_origin(target_url)
                    raise err
                return
            if kind == 'emby_http':
                from .server_emby import emby_media_origin_allowed
                from .t4_http import canonical_media_origin
                self._validate_emby_selection(live_source, selection)
                with T4TokenStore(self.token_db_path, read_only=True) as tstore:
                    approved = tstore.approved_origins(live_source.id, body['generation'])
                if not emby_media_origin_allowed(target_url, live_source.location, approved):
                    err = LibraryError('T4_MEDIA_ORIGIN')
                    err.blocked_origin = canonical_media_origin(target_url)
                    raise err
                return
            raise LibraryError('SOURCE_STREAM_INVALID')

        return verify_hop

    def resolve(self, body):
        source = self.source(body)
        selection = body['selection']
        if source.kind == 't4' and selection.get('kind') == 't4':
            from .t4_http import resolve_selected
            with T4TokenStore(self.token_db_path, read_only=True) as tstore:
                url, hdrs, title = resolve_selected(
                    source,
                    selection,
                    generation=body['generation'],
                    token_store=tstore,
                    cancelled=lambda: self.closed or not self.current(),
                )
                return url, hdrs, title, None, ''
        if source.kind == 'vfs' and set(selection) == {'kind', 'relative', 'observation'} and selection['kind'] == 'strm':
            from .source_pointers import read
            url, observation = read(source, selection['relative'])
            if observation != selection['observation']:
                raise LibraryError('SOURCE_STREAM_CHANGED')
            return url, {}, selection['relative'].rsplit('/', 1)[-1][:-5], None, ''
        if source.kind == 'media_server' and selection.get('kind') == 'emby_http':
            from .server_emby import Client
            srv_id, usr_id, itm_id, med_id, open_sess = self._validate_emby_selection(source, selection)
            saved = {
                'provider': 'emby',
                'location': source.location,
                'token': source.password,
                'server_id': srv_id,
                'user_id': usr_id,
            }
            client = Client('emby', saved)
            try:
                with client.session.budget(16):
                    resolved = client.resolve_gateway_http(itm_id, med_id, is_playback=open_sess)
            except PanError as exc:
                code_map = {
                    'PAN_SERVER_UNAUTHORIZED': 'MEDIA_AUTH',
                    'PAN_SERVER_FORBIDDEN': 'MEDIA_AUTH',
                    'PAN_AUTH_REQUIRED': 'MEDIA_AUTH',
                    'PAN_ACCOUNT_ID_INVALID': 'SOURCE_STREAM_CHANGED',
                    'PAN_FILE_CHANGED': 'SOURCE_STREAM_CHANGED',
                    'PAN_MEDIA_UNSUPPORTED': 'MEDIA_TYPE_UNSUPPORTED',
                    'PAN_BUDGET_EXHAUSTED': 'MEDIA_TIMEOUT',
                }
                raise LibraryError(code_map.get(str(exc), 'MEDIA_UNAVAILABLE')) from None
            return (
                resolved['url'],
                resolved['headers'],
                resolved['title'],
                resolved['declared_size'],
                resolved['play_session_id'],
            )
        raise LibraryError('SOURCE_STREAM_INVALID')

    def check(self, body):
        self._active_policy.fn = self._make_origin_policy(body)
        if body['selection']['kind'] == 'strm':
            self.resolve(body)  # Never follow a replaced pointer on a later seek.
        elif body['selection']['kind'] == 'emby_http':
            live_source = self.source(body)
            self._validate_emby_selection(live_source, body['selection'])
        else:
            self.source(body)

    @staticmethod
    def check_reply(body, reply):
        mode = body.get('identity_mode', 'strong_etag')
        if mode == 'strong_etag':
            if evidence(reply, require_etag=True) != body['etag']:
                raise LibraryError('SOURCE_STREAM_CHANGED')
        else:
            evidence(reply, require_etag=False)
        actual_mime = reply.headers.get('Content-Type', '').partition(';')[0].strip().lower()
        if body.get('mime') and actual_mime != body['mime']:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        cr = reply.headers.get('Content-Range', '')
        match = re.fullmatch(r'bytes \d+-\d+/([1-9][0-9]{0,18})', cr)
        if not match or int(match[1]) != body['size']:
            raise LibraryError('SOURCE_STREAM_CHANGED')

    def grant(self, body):
        self.check(body)
        url, headers = body['upstream'], body['headers']
        if digest(url) != body['target'] or not self.headers(body, url, headers):
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return url + '|' + urlencode(headers)

    @staticmethod
    def headers(body, url, headers):
        if digest(url) != body['target'] or not (set(headers) <= ALLOWED_STREAM_HEADER_NAMES):
            return False
        mode = body.get('identity_mode', 'strong_etag')
        if mode == 'strong_etag':
            return headers.get('If-Match') == body['etag']
        # weak_session NEVER sends If-Match or If-Range (REV-10).
        return 'If-Match' not in headers and 'If-Range' not in headers

    def open(self, request):
        if (set(request) != {'request_id', 'source_id', 'generation', 'selection'} or
                any(type(request[k]) is not str or not re.fullmatch(pattern, request[k]) for k, pattern in (
                    ('request_id', '[a-f0-9]{32}'), ('source_id', '[a-f0-9]{32}'), ('generation', '[a-f0-9]{64}'))) or
                not isinstance(request['selection'], dict)):
            raise LibraryError('SOURCE_STREAM_INVALID')
        origin_policy = self._make_origin_policy(request)
        self._active_policy.fn = origin_policy
        # Resolve outside the admission lock. Never transmit credentials or a
        # target URL across the runtime control socket or the Kodi plugin route.
        try:
            url, headers, _, declared_size, play_session_id = self.resolve(request)
            origin_policy(url)
            probed = probe_stream(
                url,
                {'User-Agent': 'BobbiTV', **headers},
                self.sessions,
                max_redirects=3,
                cancelled=lambda: self.closed or not self.current(),
                origin_policy=origin_policy,
            )
        except LibraryError as err:
            blocked = getattr(err, 'blocked_origin', None)
            if err.code == 'T4_MEDIA_ORIGIN' and blocked and self.root.is_dir():
                try:
                    with T4TokenStore(self.token_db_path) as tstore:
                        tstore.record_blocked_origin(
                            request['source_id'],
                            request['generation'],
                            request['request_id'],
                            blocked,
                        )
                except LibraryError:
                    pass
            raise

        size = probed['size']
        if declared_size is not None and size != declared_size:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        tag = probed['etag']
        identity_mode = probed['identity_mode']
        mime = probed['mime']
        key = digest([request['source_id'], request['generation'], request['selection']])
        ext = urlsplit(probed['final_url']).path.rsplit('.', 1)[-1].lower()
        if ext not in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'iso'):
            ext = urlsplit(url).path.rsplit('.', 1)[-1].lower()
        name = 'video.' + ext if ext in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'iso') else 'video.bin'
        stream_headers = {'User-Agent': 'BobbiTV', **headers}
        if identity_mode == 'strong_etag':
            stream_headers['If-Match'] = tag
        body = dict(
            request,
            locator='source:' + key,
            guid=key,
            media=key,
            title=name,
            size=size,
            etag=tag,
            mime=mime,
            identity_mode=identity_mode,
            target=digest(url),
            upstream=url,
            headers=stream_headers,
        )
        self.check(body)
        with self.lock:
            if self.closed:
                raise LibraryError('SOURCE_STREAM_CHANGED')
            if self.transport is None:
                # Only open() can construct a body. The transport is private
                # and never accepts caller-provided stream registration fields.
                self.transport = ShareStream(
                    lambda _: None,
                    self.grant,
                    direct_url,
                    body_check=lambda value: value,
                    header_check=self.headers,
                    session_factory=self._transport_sessions(),
                    observer=lambda _: None,
                    binding_check=self.check,
                    response_check=self.check_reply,
                )
            result = self.transport.register(body)
        self.check(body)
        out = dict(url=result['url'], size=size, identity_mode=identity_mode)
        if play_session_id:
            out['play_session_id'] = play_session_id
        return out

    def close(self):
        with self.lock:
            self.closed, transport = True, self.transport
        if transport is not None:
            transport.close()


def open_emby_http_gateway_playback(
    reservation,
    dialog,
    root,
    *,
    source_id: str,
    generation: str,
    server_id: str,
    user_id: str,
    item_id: str,
    media_source_id: str,
    require_current,
    open_session: bool = True,
) -> dict | None:
    """Open an Emby HTTP / RequiredHttpHeaders MediaSource through SourceStreams with per-hop TV approval (U09)."""
    selection = {
        'kind': 'emby_http',
        'server_id': server_id,
        'user_id': user_id,
        'item_id': item_id,
        'media_source_id': media_source_id,
        'open_session': bool(open_session),
    }
    for _ in range(5):
        try:
            result = reservation.host_call(
                'source_stream_open',
                {
                    'source_id': source_id,
                    'generation': generation,
                    'request_id': reservation.request_id,
                    'selection': selection,
                },
                timeout=24,
            )
            local_media_url(result)
            return result
        except LibraryError as err:
            if err.code != 'T4_MEDIA_ORIGIN':
                raise
            cand_origin = getattr(err, 'blocked_origin', None)
            if not cand_origin:
                with T4TokenStore(root / 't4-tokens.sqlite3') as tstore:
                    cand_origin = tstore.pop_blocked_origin(source_id, generation, reservation.request_id)
            if not cand_origin or not dialog.yesno(
                '允许连接外部媒体域名？',
                f'此 Emby 片源位于 {cand_origin}，是否允许当前来源按需读取（不会发送 Emby 凭据）？',
            ):
                return None
            require_current()
            reservation.require_current()
            with T4TokenStore(root / 't4-tokens.sqlite3') as tstore:
                tstore.approve_origin(source_id, generation, cand_origin)
    raise LibraryError('MEDIA_REDIRECT')
