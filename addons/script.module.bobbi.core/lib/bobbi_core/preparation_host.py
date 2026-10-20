"""Opt-in preparation capability, not a prerequisite for the portable host.

One dedicated owner thread owns all SQLite state. The existing bounded IO,
resolver and ASS/font lanes remain separate. Every incarnation captures an
AccountManager generation; logout revokes admission immediately and drains
old work before opening another incarnation. An already sent cloud request
cannot be recalled: its durable uncertainty is retained, never auto-replayed.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
import time
from urllib.parse import urlsplit


def _private(path):
    path = Path(path)
    if (not path.is_file() or path.stat().st_size > 16384
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise ValueError('PREPARATION_PRIVATE_INPUT')
    return path.read_text(encoding='utf-8').strip()


def _endpoint(value):
    target = urlsplit(value)
    if (target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port
            or target.username or target.password or target.path not in ('', '/')
            or target.query or target.fragment):
        raise ValueError('PREPARATION_LOCAL_ENDPOINT')
    return value.rstrip('/')


def configuration(path):
    value = json.loads(_private(path))
    required = {'schema', 'enabled', 'cd2_endpoint', 'cd2_token_file', 'account',
                'destination', 'ffprobe', 'download_capability', 'torrserver_endpoint'}
    optional = {'cd2_login_file', 'tmdb_proxy', 'torrserver_pairing_file', 'tmdb_api_key_file',
                'jackett_endpoint', 'jackett_api_key_file', 'font_tool', 'font_native_directory'}
    if (not isinstance(value, dict) or set(value) - required - optional or required - set(value)
            or type(value['schema']) is not int or value['schema'] != 1
            or value['enabled'] is not True):
        raise ValueError('PREPARATION_CONFIG')
    for pair in ({'jackett_endpoint', 'jackett_api_key_file'}, {'font_tool', 'font_native_directory'}):
        if set(value) & pair not in (set(), pair):
            raise ValueError('PREPARATION_CONFIG_PAIR')
    for key in ('cd2_endpoint', 'torrserver_endpoint', 'tmdb_proxy'):
        if key in value:
            value[key] = _endpoint(value[key])
    import re
    from .preparation import scope_path
    if not re.fullmatch('[0-9a-f]{64}', str(value['account'])):
        raise ValueError('PREPARATION_LEGACY_SCOPE')
    scope_path(value['destination'])
    return value


class Lease:
    """Immutable account generation with immediate local revocation."""
    def __init__(self, accounts, scope):
        self.accounts, self.scope = accounts, deepcopy(scope)
        self.revoked = Event()

    def valid(self):
        return not self.revoked.is_set() and self.accounts.is_current(self.scope)

    def check(self):
        if not self.valid():
            raise RuntimeError('PREPARATION_ACCOUNT_REVOKED')

    def commit(self, operation):
        self.check()
        return self.accounts.run_if_current(self.scope, operation)


class ScopedProvider:
    """Verify real CD2 UID and local epoch before each provider operation."""
    def __init__(self, provider, lease, legacy):
        self.provider, self.lease, self.legacy = provider, lease, legacy
        self.session = provider.session

    def account_scope(self):
        self.lease.check()
        identity = self.provider.provider_identity()
        self.lease.check()
        if (identity.get('account_id') != self.lease.scope['account_id']
                or identity.get('legacy_scope') != self.legacy):
            raise RuntimeError('PREPARATION_PROVIDER_ACCOUNT_MISMATCH')
        return self.legacy

    def __getattr__(self, name):
        if name not in {'rpc', 'space', 'files', 'identified_files', 'download_path',
                        'offline_tasks', 'offline_files', 'add_offline', 'search', 'list_directory', 'runtime_info'}:
            raise AttributeError(name)
        operation = getattr(self.provider, name)
        def guarded(*args, **kwargs):
            self.account_scope()
            result = operation(*args, **kwargs)
            self.lease.check()
            return result
        return guarded


class _Request:
    def __init__(self, method, body, scope):
        self.method, self.body, self.scope = method, deepcopy(body), deepcopy(scope)
        self.deadline, self.done = time.monotonic() + .23, Event()
        self.result, self.failed = None, False


class PreparationHost:
    def __init__(self, root, accounts, config, playing=lambda: True,
                 report=lambda code: None, session_factory=None):
        self.root, self.accounts, self.config = Path(root), accounts, deepcopy(config)
        self.playing, self.report = playing, report
        self.factory = session_factory or Session
        self.stop, self.wake = Event(), Event()
        self.calls = Queue(maxsize=32)
        self.lock = Lock()
        self.lease = None
        self.state, self.last_revoke = 'STARTING', None
        self.unsubscribe = accounts.subscribe(self._changed)
        self.thread = Thread(target=self._run, name='bobbi-preparation-owner', daemon=True)
        self.thread.start()

    def _changed(self, previous, current):
        # Called under AccountManager's brief commit lock: no network/joins.
        with self.lock:
            if self.lease is not None and self.lease.scope == previous:
                self.lease.revoked.set()
                self.last_revoke = dict(account=previous, admission_closed=True, drained=False)
                self.state = 'REVOKING'
        self.wake.set()

    def snapshot(self):
        with self.lock:
            return dict(state=self.state, account=deepcopy(self.lease.scope) if self.lease else None,
                        revoke=deepcopy(self.last_revoke))

    def request(self, method, body, scope):
        from .capabilities import descriptor
        self.accounts.require_current(scope)
        if method == 'ping':
            return dict(ok=True, component=descriptor(), **self.snapshot())
        job = _Request(method, body, scope)
        try:
            self.calls.put_nowait(job)
        except Full:
            raise RuntimeError('PREPARATION_BUSY') from None
        self.wake.set()
        if not job.done.wait(.23):
            raise RuntimeError('PREPARATION_OWNER_TIMEOUT')
        self.accounts.require_current(scope)
        if job.failed:
            raise RuntimeError('PREPARATION_UNAVAILABLE')
        return dict(ok=True, component=descriptor(), **job.result)

    def _requests(self, session, lease):
        for _ in range(8):
            try:
                job = self.calls.get_nowait()
            except Empty:
                break
            try:
                if (time.monotonic() >= job.deadline or session is None or lease is None
                        or job.scope != lease.scope):
                    raise RuntimeError('PREPARATION_STALE_REQUEST')
                def dispatch():
                    if time.monotonic() >= job.deadline:
                        raise RuntimeError('PREPARATION_STALE_REQUEST')
                    return session.dispatch(job.method, job.body)
                job.result = lease.commit(dispatch)
            except Exception:
                job.failed = True
            finally:
                job.done.set()

    def _run(self):
        session, lease, retry, attempted_scope = None, None, 0, None
        try:
            while not self.stop.is_set():
                if lease is not None and not lease.valid():
                    # Stop admissions first; close waits only already-bounded IO.
                    # No finish/publication happens in Session.close().
                    if session is not None:
                        session.close()
                    session, lease = None, None
                    with self.lock:
                        self.lease = None
                        if self.last_revoke:
                            self.last_revoke['drained'] = True
                        self.state = 'WAITING_ACCOUNT'
                scope = self.accounts.snapshot()
                if scope != attempted_scope:
                    retry, attempted_scope = 0, scope
                if session is None and not scope['authenticated']:
                    with self.lock:
                        self.state = 'WAITING_ACCOUNT'
                if session is None and scope['authenticated'] and time.monotonic() >= retry:
                    lease = Lease(self.accounts, scope)
                    with self.lock:
                        self.lease, self.state = lease, 'STARTING'
                    try:
                        session = self.factory(self.root, self.config, lease, self.playing, self.report)
                        lease.check()
                        with self.lock:
                            self.state = 'RUNNING'
                    except Exception as error:
                        if session is not None:
                            session.close()
                        session = None
                        lease.revoked.set()
                        with self.lock:
                            self.state = 'UNAVAILABLE'
                            self.lease = None
                        self.report('PREPARATION_START_' + type(error).__name__)
                        self._first_failure(error)
                        # Keep lease until retry, but do not busy-reconstruct.
                        lease = None
                        retry = time.monotonic() + 60
                self._requests(session, lease)
                if session is not None:
                    try:
                        session.tick()
                    except Exception as error:
                        self.report('PREPARATION_TICK_' + type(error).__name__)
                        self._first_failure(error)
                        retry = time.monotonic() + 60
                        lease.revoked.set()
                self.wake.wait(.05)
                self.wake.clear()
        finally:
            if lease is not None:
                lease.revoked.set()
            if session is not None:
                session.close()
            self._requests(None, None)
            with self.lock:
                self.state = 'STOPPED'
                if self.last_revoke:
                    self.last_revoke['drained'] = True

    def _first_failure(self, error):
        import traceback
        path = self.root / 'preparation-first-failure.json'
        record = dict(error=type(error).__name__, frames=[dict(file=Path(f.filename).name,
            line=f.lineno, function=f.name) for f in traceback.extract_tb(error.__traceback__)[-12:]])
        try:
            with path.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, separators=(',', ':'))
        except OSError:
            pass

    def close(self):
        self.stop.set()
        with self.lock:
            if self.lease is not None:
                self.lease.revoked.set()
        self.unsubscribe()
        self.wake.set()
        # Session.close drains admitted provider IO before releasing its DBs.
        # Do not report a quiescent host while that cleanup still owns them.
        self.thread.join()


class Session:
    """Existing preparation policies, assembled only for explicit CE config."""
    def __init__(self, root, config, lease, playing, report):
        self.resources = ExitStack()
        self.config, self.lease, self.playing_probe, self.report = config, lease, playing, report
        self.future = self.owner = None
        self.playing, self.next_work, self.next_fonts = True, 0, 0
        try:
            self._initialize(Path(root))
        except BaseException:
            self.resources.close()
            raise

    def _initialize(self, root):
        from concurrent.futures import ThreadPoolExecutor
        from .authenticated_cd2 import AuthenticatedCD2
        from .cd2 import CD2
        from .cloud_qualifier import CloudQualifier
        from .ledger import Ledger
        from .preparation import PreparationQueue
        from .preparation_intake import Intake
        from .preparation_worker import PreparationWorker
        from .catalog_identity import Catalog
        from .metadata_cache import MetadataCache
        from .account_readiness import AccountReadiness
        from .subtitle_store import SubtitleStore
        from .subtitle_preparation import SubtitlePreparation
        from .torrent_selection import select_exact_file
        from .torrent_subtitles import matching_chinese_sidecars
        from .prepared_protection import PreparedProtection, ProtectionLane
        from .prepared_resolver import PreparedResolver
        from .resolve_lane import ResolveLane
        from .media_profile_refresh import MediaProfileRefresh
        from .direct_cloud import DirectQueue, DirectResolver
        from .direct_cloud_io import DirectIO
        import requests
        c, cancelled = self.config, lambda: not self.lease.valid()
        state = root / 'preparation' / (self.lease.scope['account_id'][4:] + '-' + str(self.lease.scope['epoch']))
        state.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (state, *state.parents)):
            raise ValueError('PREPARATION_STATE_PATH')
        # Runtime teardown may return while bounded old IO drains. Keep this
        # separate inode locked until the last old SQLite connection closes.
        from bobbi_platform.instance_lock import InstanceLock
        process_lock = InstanceLock(state / 'owner.lock')
        process_lock.acquire()
        self.resources.callback(process_lock.close)
        self.snapshot_path = root / 'bobi-prepared.json'
        token = _private(c['cd2_token_file'])
        def provider_client():
            base = c['cd2_endpoint'] + '/clouddrive.CloudDriveFileSrv/'
            raw = (AuthenticatedCD2(token, base, lambda: json.loads(_private(c['cd2_login_file'])))
                   if c.get('cd2_login_file') else CD2(token, base))
            return ScopedProvider(raw, self.lease, c['account'])
        self.provider, resolve_provider = provider_client(), provider_client()
        self.resources.callback(self.provider.session.close)
        self.resources.callback(resolve_provider.session.close)
        self.readiness = AccountReadiness(c['account'])
        self.selector = select_exact_file
        self.torrent_session, catalog_session = requests.Session(), requests.Session()
        for session in (self.torrent_session, catalog_session):
            session.trust_env = False
            self.resources.callback(session.close)
        if c.get('torrserver_pairing_file'):
            from bobbi_platform.pairing import load
            pair = load(Path(c['torrserver_pairing_file']))
            if pair is None or pair.endpoint != c['torrserver_endpoint']:
                raise ValueError('PREPARATION_TORRENT_PAIRING')
            self.torrent_session.auth = (pair.username, pair.password)
        if c.get('tmdb_proxy'):
            catalog_session.proxies = {'https': c['tmdb_proxy']}
        from .project_metadata import tmdb_key
        project_key = tmdb_key()
        self.catalog = Catalog(catalog_session, project_key or
                               (_private(c['tmdb_api_key_file']) if c.get('tmdb_api_key_file') else ''))
        self.metadata_cache = MetadataCache(state / 'torrent-file-metadata')
        self.ledger = self.resources.enter_context(Ledger(state / 'resources.sqlite'))
        self.queue, self.intake = PreparationQueue(self.ledger), Intake(self.ledger)
        qualifier = CloudQualifier(c['ffprobe'], c['cd2_endpoint'], c['download_capability'], cancelled)
        store = SubtitleStore(self.ledger, state / 'subtitles', metadata_cache=self.metadata_cache,
                              release_matcher=matching_chinese_sidecars)
        self.subtitles = SubtitlePreparation(self.queue, store, self.metadata_cache,
            matching_chinese_sidecars, self.provider, qualifier, cancelled)
        self.font_cache = self.font_work = None
        if c.get('font_tool'):
            from .font_cache import FontCache
            from .release_font_loader import ReleaseFontLoader
            from .subtitle_font_preparation import SubtitleFontPreparation
            self.font_cache = FontCache(self.ledger, state / 'fonts', c['font_native_directory'])
            store.font_cache = self.font_cache
            loader = ReleaseFontLoader(self.provider, qualifier, state / 'font-work', c['font_tool'],
                                       lambda: self.lease.valid() and not self.playing)
            self.font_work = SubtitleFontPreparation(self.subtitles, self.font_cache, loader,
                                                      lambda: self.lease.valid() and not self.playing)
        from .font_playback_preflight import FontPlaybackPreflight
        from .font_preflight_lane import FontPreflightLane
        def font_allowed(body):
            from .playback_ipc import call
            if not self.lease.valid():
                return False
            try:
                return call(dict(operation='font_preflight_guard', **{key: body[key]
                    for key in ('boot_id', 'epoch', 'request_id', 'file_identity')})).get('allowed') is True
            except (OSError, RuntimeError, ValueError, KeyError):
                return False
        self.font_preflight = FontPreflightLane(FontPlaybackPreflight(self.subtitles, self.font_cache, font_allowed))
        self.resources.callback(self.font_preflight.close)
        self.worker = PreparationWorker(self.queue, self.provider, qualifier)
        profile_qualifier = CloudQualifier(c['ffprobe'], c['cd2_endpoint'], c['download_capability'],
                                          lambda: cancelled() or self.playing)
        self.profile_work = MediaProfileRefresh(self.queue, self.provider, profile_qualifier,
                                                lambda: self.lease.valid() and not self.playing)
        protection = PreparedProtection(self.ledger)
        self.protection_lane = ProtectionLane(protection)
        self.resources.callback(self.protection_lane.close)
        self.resolve_lane = ResolveLane(PreparedResolver(self.queue, c['account'], resolve_provider, protection))
        self.resources.callback(self.resolve_lane.close)
        direct_io = DirectIO(self.provider, provider_client, qualifier, cancelled)
        self.direct_queue = DirectQueue(state / 'direct.sqlite3', root / 'bobi-direct.json',
                                       c['account'], c['destination'], direct_io, account_scope=self.lease.scope)
        self.resources.callback(self.direct_queue.close)
        self.direct_resolve = ResolveLane(DirectResolver(self.direct_queue, direct_io))
        self.resources.callback(self.direct_resolve.close)
        self.discovery = None
        if c.get('jackett_endpoint'):
            from .discovery_service import NextDiscovery
            from .jackett_protocol import JackettProtocol
            from .candidate_metadata import candidate_metadata
            from .discovery_playback import may_discover
            searcher = JackettProtocol(c['jackett_endpoint'], _private(c['jackett_api_key_file']))
            self.discovery = NextDiscovery(self.queue, self.catalog, searcher,
                lambda source, **kw: candidate_metadata(self.torrent_session, c['torrserver_endpoint'], source, **kw),
                self.selector, self.metadata_cache, cancelled, may_discover=may_discover)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bobbi-preparation-io')
        # Registered last: drain IO before closing providers/SQLite. Python3.8
        # has no cancel_futures; only one already-running future exists here.
        self.resources.callback(lambda: self.executor.shutdown(wait=True))
        self.generation = self.subtitle_revision = -1

    def dispatch(self, method, body):
        self.lease.check()
        # Local durable intake/status and immutable subtitle/font reads must
        # remain available during a transient CD2 health failure. Cloud IO is
        # still gated here and in tick(), and this account lease stays required.
        if method in ('resolve', 'catalog_resolve') and not self.readiness.ready:
            return dict(state='unavailable', reason='cloud_dependency_not_ready', dependency=self.readiness.snapshot())
        if method == 'prepare':
            return self.intake.accept(body)
        if method == 'advance':
            return self.intake.accept_advance(body)
        if method == 'status' and isinstance(body, dict) and set(body) == {'request_id'}:
            import re
            identifier = body['request_id']
            if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
                raise ValueError('PREPARATION_REQUEST_ID')
            try:
                return self.intake.status(identifier)
            except KeyError:
                # Explicit negative receipt, unlike an IPC timeout/rejection.
                return dict(request_id=identifier, state='absent')
        if method == 'catalog_prepare':
            return self.direct_queue.accept(body)
        if method == 'catalog_status' and isinstance(body, dict) and set(body) == {'key'}:
            return self.direct_queue.status(body['key'])
        if method == 'catalog_resolve':
            return self.direct_resolve.request(body)
        if method == 'resolve':
            return self.resolve_lane.request(body)
        if method == 'subtitle':
            result = self.subtitles.for_playback(body)
            if isinstance(result, dict) and result.get('state') in ('ready', 'candidate'):
                # Local reads may be cached after this RPC: retain the captured
                # account generation for the final playback-owner check too.
                return self.lease.commit(lambda: dict(result, account_scope=dict(self.lease.scope)))
            return result
        if method == 'font_preflight':
            return (self.font_preflight.request(body) if self.font_cache else
                    dict(state='unavailable', reason='FONT_CACHE_DISABLED'))
        raise ValueError('PREPARATION_METHOD')

    def _submit(self, kind, value, operation, *args):
        self.lease.check()
        self.future, self.owner = self.executor.submit(operation, *args), (kind, value)

    def _complete(self, kind, value, result):
        if kind == 'account':
            self.readiness.complete(account=result)
        elif kind == 'intent':
            accepted = [dict(self.queue.request(request, selection), version_key=request['version_key'],
                             media_id=request['media_id']) for request, selection in result]
            self.intake.finish(value['request_id'], {'tasks': accepted}, True)
            if self.discovery:
                try:
                    self.discovery.after_intent(result, accepted)
                except Exception:
                    self.report('NEXT_DISCOVERY_SCHEDULE_UNAVAILABLE')
        elif kind == 'worker':
            self.worker.complete(value, result)
        elif kind == 'discovery':
            self.discovery.complete(value, result)
        elif kind == 'subtitle':
            self.subtitles.complete(value, result)
        elif kind == 'subtitle_fonts':
            self.font_work.complete(value, result)
        elif kind == 'font_bytes':
            self.font_cache.finish_byte_action(value, result)
        elif kind == 'media_profile':
            self.profile_work.complete(value, result)
        elif kind == 'direct':
            self.direct_queue.complete(value, result)

    def _failed(self, kind, value, error):
        self.report('PREPARATION_' + kind.upper() + '_' + type(error).__name__)
        if kind == 'account':
            self.readiness.complete(error=error)
        elif kind == 'intent':
            self.intake.finish(value['request_id'], {'error': type(error).__name__}, False)
        elif kind == 'worker':
            # Preserve submission uncertainty. Never retry a mutation because
            # a local publication or process was interrupted.
            self.worker.complete(value, {'ok': False, 'error': type(error).__name__})
        elif kind == 'discovery':
            self.discovery.failed(value)
        elif kind == 'direct':
            self.direct_queue.complete(value, {'ok': False, 'error': type(error).__name__})
        else:
            component = {'subtitle': self.subtitles, 'subtitle_fonts': self.font_work,
                         'media_profile': self.profile_work}.get(kind)
            if component is not None:
                component.pending = None

    def _validate(self, value):
        from .torrent_metadata import registered_metadata
        from .source_intent import verified_intents
        self.provider.account_scope()
        metadata = self.metadata_cache.load(value['selected']['source_info_hash'])
        if metadata is None:
            metadata = registered_metadata(self.torrent_session, self.config['torrserver_endpoint'],
                value['selected']['source_info_hash'], lambda: not self.lease.valid())
        result = verified_intents(value, metadata, self.config['account'], self.config['destination'],
                                  self.selector, self.catalog.lookup(value['media']))
        self.lease.commit(lambda: self.metadata_cache.store(metadata))
        return result

    def _publish(self):
        from .prepared_index import publish
        from .subtitle_projection import generation
        revision = generation(self.queue.db)
        if self.queue.generation() != self.generation or revision != self.subtitle_revision:
            self.generation = publish(self.queue, self.snapshot_path, self.config['account'],
                                      account_scope=self.lease.scope)
            self.subtitle_revision = revision

    def tick(self):
        self.lease.check()
        self.playing = self.playing_probe() is not False
        self.lease.commit(self.protection_lane.tick)
        self.lease.commit(self.font_preflight.tick)
        self.lease.commit(lambda: self.resolve_lane.tick(allow_submit=self.readiness.ready))
        self.lease.commit(lambda: self.direct_resolve.tick(allow_submit=self.readiness.ready))
        if self.future is not None:
            if not self.future.done():
                return
            kind, value = self.owner
            try:
                result = self.future.result()
                self.lease.commit(lambda: self._complete(kind, value, result))
            except Exception as error:
                self.lease.commit(lambda: self._failed(kind, value, error))
            self.future = self.owner = None
        if self.readiness.begin():
            self._submit('account', None, self.provider.account_scope)
            return
        now = time.monotonic()
        if self.font_cache and not self.playing and now >= self.next_fonts:
            self.next_fonts = now + 2
            action = self.lease.commit(self.font_cache.next_byte_action)
            if action:
                self._submit('font_bytes', action, self.font_cache.warm_bytes, action,
                             lambda: self.lease.valid() and not self.playing)
                return
        if not self.readiness.ready:
            return
        self.lease.commit(self._publish)
        if now < self.next_work:
            return
        self.next_work = now + 1
        direct = self.lease.commit(self.direct_queue.next_action)
        if direct:
            self._submit('direct', direct, self.direct_queue.perform, direct)
            return
        intent = self.lease.commit(self.intake.take)
        if intent:
            self._submit('intent', intent, self._validate, intent)
            return
        action = self.lease.commit(lambda: self.worker.next_action(self.playing))
        if action:
            self._submit('worker', action, self.worker.perform, action)
            return
        if not self.playing:
            for kind, component in (('subtitle', self.subtitles), ('subtitle_fonts', self.font_work)):
                action = self.lease.commit(component.next_action) if component else None
                if action:
                    self._submit(kind, action, component.perform, action)
                    return
        if self.discovery:
            action = self.lease.commit(self.discovery.claim)
            if action:
                self._submit('discovery', action, self.discovery.perform, action)
                return
        if not self.playing:
            action = self.lease.commit(self.profile_work.next_action)
            if action:
                self._submit('media_profile', action, self.profile_work.perform, action)

    def close(self):
        self.lease.revoked.set()
        # ExitStack drains provider IO before SQLite closes. No completion,
        # subtitle activation, index publication or cloud retry runs here.
        self.resources.close()
