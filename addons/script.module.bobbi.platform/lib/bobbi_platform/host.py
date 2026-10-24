"""Portable host with lazy capabilities and one account/renewable-stream owner.

The stock host needs no CD2, ffprobe, BT engine, proxy or native player. When
native Kodi is present its existing playback actor stays on the Kodi thread;
HTTP workers only enqueue bounded requests to that actor.
"""
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import time
from uuid import uuid4

from .account_manager import AccountManager, AccountError
from .runtime import Runtime


class _Call:
    def __init__(self, value, lifecycle=False):
        self.value, self.deadline = value, time.monotonic() + .25
        self.lifecycle = lifecycle
        self.done, self.lock = Event(), Lock()
        self.cancelled, self.result, self.error = False, None, False


class Host:
    def __init__(self, root, report=lambda code: None, stream_factory=None, native_rpc=None):
        self.root, self.report = Path(root), report
        self.stream_factory, self.native_rpc = stream_factory, native_rpc
        self.accounts = self.streams = self.engine = self.images = None
        self.owner = self.preparation = None
        self.preparation_attempted = False
        self.preparation_root = None
        self.playing = True
        self.calls, self.revocations = Queue(maxsize=32), Queue(maxsize=32)
        self.account_changes = Event()
        self.owner_account_changed = None
        self.lock = Lock()
        self.engine_check = 0
        self.engine_worker, self.engine_lock = None, Lock()
        self.refresh = self.refresh_worker = self.refresh_result = None
        self.idle_probe = lambda: False
        self.can_quiesce = lambda: False
        self.refresh_due, self.idle_check, self.idle = 0, 0, False
        self.stopping = Event()
        self.runtime = Runtime(self.dispatch, self.root / 'runtime.json')
        self.runtime.report = report
        self.unsubscribe = lambda: None

    def start(self):
        def prepare():
            self.accounts = AccountManager(self.root / '115-os_linux.json')
            self.unsubscribe = self.accounts.subscribe(self._account_changed)
        self.runtime.start(prepare=prepare)
        try:
            from bobbi_core.image_cache import ImageService
            self.images = ImageService(self.root, report=self.report)
            self.images.start()
        except (ImportError, OSError, ValueError, RuntimeError):
            if self.images is not None:
                self.images.close()
            self.images = None
            self.report('IMAGE_SERVICE_UNAVAILABLE')

    def _account_changed(self, previous, current):
        # Account callbacks may run on an HTTP worker. Playback and native
        # barrier revocation stay on the existing serialized Kodi owner.
        self.account_changes.set()  # Coalesced current-scope check cannot overflow.
        # This subscriber is registered before ShareStream's own revoke hook.
        # Collect only our unique old stream URLs, never a global player ID.
        streams = self.streams
        if streams is None:
            return
        with streams.lock:
            hashes = {e.transport_hash for e in streams.records.values()
                      if e.scope == previous and e.transport_hash}
        if hashes:
            try:
                self.revocations.put_nowait(hashes)
            except Full:
                self.report('ACCOUNT_STOP_QUEUE_FULL')
                # Stream revocation still runs. Never substitute global Stop.

    def _shares(self):
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('RUNTIME_NOT_READY')
            if self.streams is None:
                if self.stream_factory is not None:
                    self.streams = self.stream_factory(self.accounts)
                else:
                    from bobbi_core.share_stream import ShareStream, observation_line
                    from bobbi_core.share_catalog import selected, resolve
                    from bobbi_catalog.api import Client, valid_cdn
                    from .transport_preferences import load as transport_mode
                    try:
                        progressive = transport_mode(self.root)
                    except (OSError, ValueError):
                        progressive = False
                        self.report('SHARE_PREFERENCE_INVALID_USING_BLOCK')
                    def resolve_selected(body, expected):
                        session = self.accounts.credentials(expected)
                        client = Client(session=session, account_scope=expected)
                        address = resolve(body, client=client)
                        self.accounts.require_current(expected)
                        return address
                    self.streams = ShareStream(selected, resolve_selected, valid_cdn,
                        report=self.report, observer=lambda row: self.report(observation_line(row)),
                        account=self.accounts, progressive=progressive)
            return self.streams

    def bind_owner(self, dispatch, account_changed=None):
        self.owner = dispatch  # Called on the native owner thread, never via IPC.
        self.owner_account_changed = account_changed

    def bind_preparation(self, dispatch):
        self.preparation = dispatch  # An explicit capability, not a guessed endpoint.

    def configure_preparation(self, root):
        self.preparation_root = Path(root)

    def configure_catalog_refresh(self, refresh, idle, delay=60):
        self.refresh, self.idle_probe = refresh, idle
        self.refresh_due = time.monotonic() + max(0, delay)

    def sidecar_candidate(self, body, context, deadline, cancelled):
        if not isinstance(body, dict) or 'account' not in body:
            raise AccountError('ACCOUNT_SCOPE_INVALID')
        expected = self.accounts.require_current(body['account'])
        selected = {key: body[key] for key in ('locator', 'guid', 'title', 'size', 'media')}
        from bobbi_catalog.api import Client
        from bobbi_core.share_subtitles import fetch_candidate
        client = Client(session=self.accounts.credentials(expected), account_scope=expected)
        candidate = fetch_candidate(selected, context, deadline, cancelled, client=client,
                                   account_guard=lambda: self.accounts.is_current(expected),
                                   account_scope=expected)
        if candidate.get('account_scope') != expected:
            raise AccountError('SUBTITLE_ACCOUNT_SCOPE_MISSING')
        return self.accounts.run_if_current(expected, lambda: candidate)

    def _owner_request(self, body, lifecycle=False):
        if self.owner is None:
            raise ValueError('NATIVE_OWNER_UNAVAILABLE')
        job = _Call(body, lifecycle=lifecycle)
        try:
            self.calls.put_nowait(job)
        except Full:
            raise OSError('NATIVE_OWNER_BUSY') from None
        if not job.done.wait(.25):
            job.cancelled = True
            raise TimeoutError('NATIVE_OWNER_TIMEOUT')
        if job.error:
            if job.error == 'unavailable':
                raise OSError('NATIVE_OWNER_UNAVAILABLE')
            raise ValueError('NATIVE_OWNER_REJECTED')
        return job.result

    def dispatch(self, action, body):
        if self.stopping.is_set() or self.accounts is None:
            raise ValueError('RUNTIME_NOT_READY')
        if not isinstance(body, dict):
            raise ValueError('RUNTIME_FIELDS')
        if action == 'quiesce' and body == {'protocol': 1} and type(body['protocol']) is int:
            # Serialized with playback, never decide isPlaying on an HTTP
            # worker. The existing per-instance bearer token scopes this call.
            return self._owner_request(body, lifecycle=True)
        if action == 'account_status' and not body:
            return self.accounts.snapshot()
        if action == 'cloud_status' and not body:
            # A local view of the existing owners, not another health checker.
            # Account->preparation lock ordering matches account revocation.
            scope = self.accounts.snapshot()
            def view():
                if self.preparation is not None:
                    state = self.preparation.snapshot()
                    if state.get('account') is not None and state['account'] != scope:
                        state = dict(state='WAITING_ACCOUNT' if not scope['authenticated'] else 'STARTING')
                else:
                    state = dict(state='UNAVAILABLE' if self.preparation_attempted else
                                 'STARTING' if (self.root / 'preparation.json').is_file() else 'NOT_CONFIGURED')
                dependency = state.get('dependency') or {}
                return dict(authenticated=scope['authenticated'], preparation=dict(
                    state=state['state'], dependency=dependency.get('state', 'UNVERIFIED'),
                    ready=dependency.get('ready') is True))
            return self.accounts.run_if_current(scope, view, authenticated=False)
        if action == 'account_install' and set(body) == {'credentials', 'expected'}:
            return self.accounts.install(body['credentials'], body['expected'])
        if action == 'account_logout' and set(body) == {'expected'}:
            return self.accounts.logout(body['expected'])
        if action == 'share_open' and 'account' in body:
            expected = self.accounts.require_current(body['account'])
            payload = {key: value for key, value in body.items() if key != 'account'}
            return self._shares().register(payload, account=expected)
        if action == 'share_failure':
            import re
            from bobbi_core.share_stream import checked
            from bobbi_core.share_failure import TUPLE_FIELDS, tuple_hash
            if (set(body) != {'account', 'owner', 'selected'} or type(body['owner']) is not dict
                    or set(body['owner']) != {'boot_id', 'epoch', 'request_id', 'file_identity',
                                              'native_instance', 'url_sha256'}
                    or type(body['selected']) is not dict or set(body['selected']) != set(TUPLE_FIELDS)
                    or type(body['owner']['url_sha256']) is not str
                    or not re.fullmatch('[0-9a-f]{64}', body['owner']['url_sha256'])):
                raise ValueError('SHARE_FAILURE_FIELDS')
            selected = checked(dict(body['selected'], request_id='0'*32))
            expected = self.accounts.require_current(body['account'])
            streams = self.streams  # A diagnostic lookup never constructs a service.
            record = streams.failure_record(expected, selected, body['owner']['url_sha256']) if streams else None
            if record is None:
                return {'matched': False}
            entry, outcome = record
            owner = {key: body['owner'][key] for key in ('boot_id', 'epoch', 'request_id', 'file_identity')}
            fresh = self._owner_request(dict(owner, operation='startup_failure'))
            if (type(fresh) is not dict or fresh.get('failed') is not True
                    or fresh.get('receipt') != body['owner']):
                return {'matched': False}
            def publish_failure():
                with entry.outcome_lock:
                    if entry.outcome is not outcome or entry.revoked.is_set() or entry.diagnostic_expired():
                        return {'matched': False}
                    failure = {key: outcome['failure'][key]
                               for key in ('code', 'http_status', 'api_code', 'invalidation_failed')}
                    if 'share_state' in outcome['failure']:
                        failure['share_state'] = dict(outcome['failure']['share_state'])
                    return dict(matched=True, account=expected, owner=dict(body['owner']),
                                tuple_sha256=tuple_hash(selected), failure=failure)
            return self.accounts.run_if_current(expected, publish_failure)
        if action == 'share_known_failures':
            from bobbi_core.share_failure import proofs
            if set(body) != {'account', 'proofs'}:
                raise ValueError('SHARE_PROOFS_INVALID')
            submitted = proofs(body['proofs'])
            expected = self.accounts.require_current(body['account'])
            streams = self.streams
            return self.accounts.run_if_current(expected,
                lambda: dict(account=expected, denied=[dict(tuple_sha256=key, checked_at=submitted[key])
                    for key in (streams.denied_proofs(expected, submitted) if streams else [])]))
        if action == 'share_open_diagnostic':
            # Explicit maintainer experiment; no preference, second daemon or
            # change to an existing ordinary registration is permitted. Both
            # open_range modes pass the same closed mode/duration validator.
            from bobbi_core.share_stream import checked, checked_diagnostic
            if set(body) != {'request_id','locator','guid','title','size','media','account','diagnostic'}:
                raise ValueError('SHARE_DIAGNOSTIC_INVALID')
            diagnostic = checked_diagnostic(body['diagnostic'])
            payload = checked({key: value for key, value in body.items() if key not in ('account','diagnostic')})
            expected = self.accounts.require_current(body['account'])
            return self._shares().register_diagnostic(payload, expected, diagnostic)
        if action == 'share_subtitle_context' and 'account' in body:
            expected = self.accounts.require_current(body['account'])
            from bobbi_core.share_catalog import selected
            value = selected({key: body[key] for key in ('locator', 'guid', 'title', 'size', 'media')})
            self.accounts.require_current(expected)
            return dict(account=expected, selected=value)
        if action == 'share_search' and set(body) == {'account', 'share', 'query'}:
            import json
            import re
            from bobbi_catalog.api import Client
            expected = self.accounts.require_current(body['account'])
            share, query = body['share'], body['query']
            if (not isinstance(share, dict)
                    or not isinstance(share.get('code'), str)
                    or not re.fullmatch(r'[A-Za-z0-9]{1,128}', share['code'])
                    or not isinstance(share.get('password'), str)
                    or not re.fullmatch(r'[A-Za-z0-9]{0,32}', share['password'])
                    or not isinstance(query, str) or not 1 <= len(query) <= 1024
                    or re.search(r'[\x00-\x1f\x7f]', query)):
                raise ValueError('SHARE_SEARCH_FIELDS')
            client = Client(session=self.accounts.credentials(expected), account_scope=expected)
            rows = client.search({'code': share['code'], 'password': share['password']}, query,
                deadline=time.monotonic() + 6,
                cancelled=lambda: self.stopping.is_set() or not self.accounts.is_current(expected))
            result = dict(account=expected, rows=rows)
            if len(json.dumps(result, ensure_ascii=True).encode('utf-8')) > 15500:
                raise ValueError('SHARE_SEARCH_REPLY_LIMIT')
            return self.accounts.run_if_current(expected, lambda: result)
        if action in ('playback', 'standard_playback'):
            if '_verified_transport' in body:
                raise ValueError('PRIVATE_TRANSPORT_PROOF_REQUIRED')
            if body.get('operation') == 'transport_capture':
                # Re-read the SAME already completed verification, off the
                # Kodi owner thread and before its short account-CAS commit.
                # A client-supplied ready flag or cached title is never proof.
                from bobbi_core.transport_handoff import VerifiedTransportTarget
                if self.preparation is None or self.native_rpc is None:
                    raise ValueError('TRANSPORT_PREPARATION_UNAVAILABLE')
                scope = self.accounts.require_current(body.get('account_scope'))
                verification = body.get('prepared_verification')
                if (not isinstance(verification, dict)
                        or verification.get('request_id') != body.get('request_id')):
                    raise ValueError('TRANSPORT_VERIFICATION_REQUEST')
                result = self.preparation.request('resolve', verification, scope)
                if result.get('state') != 'ready':
                    return dict(authorized=False, state='NOT_READY')
                proof = VerifiedTransportTarget(result, verification, scope)
                body = dict(body)
                body.pop('prepared_verification')
                body['_verified_transport'] = proof
            return self._owner_request(body)
        if action == 'preparation':
            from bobbi_core.capabilities import IPC_PROTOCOL
            if (set(body) != {'method', 'body', 'protocol', 'account'}
                    or type(body['protocol']) is not int or body['protocol'] != IPC_PROTOCOL):
                raise ValueError('PREPARATION_PROTOCOL')
            if self.preparation is None:
                raise ValueError('PREPARATION_NOT_CONFIGURED')
            # The preparation implementation owns its own deadline/queue. This
            # bridge never fabricates a completed file, subtitle or font proof.
            scope = self.accounts.require_current(body['account'])
            if body['method'] in ('prepare', 'advance'):
                # Only a native-owner snapshot can grant automatic preparation.
                # UI properties and a manual file choice cannot manufacture it.
                snapshot = self._owner_request({'operation': 'snapshot'})
                desired = snapshot.get('desired') or {}
                if (not isinstance(body['body'], dict)
                        or body['body'].get('request_id') != desired.get('request_id')
                        or desired.get('cancelled')
                        or (snapshot.get('adapter') == 'standard'
                            and desired.get('file_evidence') != 'AUTO_VERIFIED_FILE')
                        or desired.get('file_evidence') == 'USER_CONFIRMED_FILE'):
                    raise ValueError('PREPARATION_CURRENT_VERIFIED_SELECTION_REQUIRED')
            return self.preparation.request(body['method'], body['body'], scope)
        if action == 'status' and not body:
            return dict(ready=True, version='0.1.0', native_owner=self.owner is not None and self.native_rpc is not None,
                        quiesce_protocol=1,
                        playback_adapter=('starting' if self.owner is None else
                                          'native' if self.native_rpc is not None else 'standard'),
                        preparation=self.preparation is not None, shares=self.streams is not None,
                        account=self.accounts.snapshot())
        raise ValueError('UNSUPPORTED_ACTION')

    def _conditional_stop(self, hashes):
        if self.native_rpc is None:
            return False  # Standard Kodi has no atomic expected-instance Stop.
        from bobbi_core.native_receipt import receipt
        state = self.native_rpc('Player.BobiState', {})
        if (not isinstance(state, dict) or state.get('protocol') != 1
                or type(state.get('selection_epoch')) is not int or state['selection_epoch'] < 0):
            return False
        current = receipt(state.get('playback'))
        if (current is None or current['phase'] not in ('OPEN', 'AV_STARTED')
                or current['url_sha256'] not in hashes):
            return False
        command = dict(native_instance=current['native_instance'], user_intent=current['user_intent'],
                       expected_sequence=current['sequence'], selection_epoch=state['selection_epoch'],
                       action='stop', command_id=uuid4().hex)
        result = self.native_rpc('Player.BobiControl', command)
        return isinstance(result, dict) and result.get('queued') is True

    def tick(self):
        if self.stopping.is_set():
            return
        # Revoke old scopes before accepting later opens/continuations. The
        # authority also guards each scoped command under AccountManager CAS.
        if self.account_changes.is_set() and self.owner_account_changed is not None:
            self.account_changes.clear()
            try:
                if self.owner_account_changed() == 'pending':
                    self.account_changes.set()
            except (ValueError, OSError, RuntimeError):
                self.account_changes.set()  # Retry revocation, never a playback open.
                self.report('ACCOUNT_OWNER_REVOKE_UNAVAILABLE')
        for _ in range(8):
            try:
                job = self.calls.get_nowait()
            except Empty:
                break
            with job.lock:
                if job.cancelled or time.monotonic() >= job.deadline:
                    job.error = 'unavailable'
                else:
                    try:
                        if job.lifecycle:
                            if self.can_quiesce() is not True:
                                raise ValueError('PLAYBACK_ACTIVE_OR_UNKNOWN')
                            self.stopping.set()
                            job.result = {'accepted': True}
                        elif self.stopping.is_set():
                            raise OSError('NATIVE_OWNER_UNAVAILABLE')
                        else:
                            job.result = self.owner(job.value)
                    except OSError:
                        job.error = 'unavailable'
                    except Exception:
                        job.error = True
                job.done.set()
        if self.stopping.is_set():
            return
        for _ in range(8):
            try:
                hashes = self.revocations.get_nowait()
            except Empty:
                break
            try:
                self._conditional_stop(hashes)
            except (ValueError, OSError, RuntimeError):
                self.report('ACCOUNT_STOP_UNAVAILABLE')
        self._tick_catalog()
        self._tick_preparation()
        # Import/start the optional native BT engine only after explicit local
        # installation. Empty config never imports subprocess, ctypes or CD2.
        now = time.monotonic()
        if now < self.engine_check:
            return
        self.engine_check = now + 1
        if self.engine_worker is None and (self.root / 'engine/enabled').is_file():
            def start_engine():
                engine = None
                try:
                    from .native_engine import Engine
                    engine = Engine()
                    engine.tick(cancelled=self.stopping.is_set)
                except (ValueError, OSError, RuntimeError):
                    self.report('OPTIONAL_ENGINE_UNAVAILABLE')
                finally:
                    # Hashing the 60MB binary, health IO and process startup
                    # never run on the serialized native actor. A close racing
                    # startup still owns and stops only our child process.
                    with self.engine_lock:
                        closing = self.stopping.is_set()
                        if not closing:
                            self.engine = engine
                    if closing and engine is not None:
                        engine.close()
            self.engine_worker = Thread(target=start_engine, name='bobbi-optional-engine', daemon=True)
            self.engine_worker.start()

    def _tick_catalog(self):
        now = time.monotonic()
        if now >= self.idle_check:
            self.idle_check = now + .5
            try:
                self.idle = self.idle_probe() is True
            except Exception:
                self.idle = False
        # Idle observation also throttles preparation when no catalogue runs.
        if self.refresh is None:
            return
        if self.refresh_worker is not None:
            if self.refresh_worker.is_alive():
                return
            self.refresh_worker.join()
            self.refresh_worker = None
            state = self.refresh_result.get('state') if isinstance(self.refresh_result, dict) else None
            active = {'FETCHED', 'IMPORTING', 'VALIDATED', 'DIRECTORY_PROGRESS', 'DIRECTORY_READY'}
            self.refresh_due = now + (.1 if state in active else 60)
        if not self.idle or now < self.refresh_due:
            return
        def work():
            try:
                self.refresh_result = self.refresh(deadline=time.monotonic() + 12,
                    cancelled=lambda: self.stopping.is_set() or not self.idle)
            except Exception:
                self.refresh_result = {'state': 'UNAVAILABLE'}
        self.refresh_worker = Thread(target=work, name='bobbi-idle-catalog', daemon=True)
        self.refresh_worker.start()

    def _tick_preparation(self):
        path = self.root / 'preparation.json'
        if self.preparation_attempted or self.preparation_root is None or not path.is_file():
            return
        self.preparation_attempted = True
        try:
            # This capability currently uses CE's configured CD2 mount and
            # ffprobe; Android/stock base paths never import or launch it.
            from .native_engine import architecture
            architecture()
            from bobbi_core.preparation_host import configuration, PreparationHost
            config = configuration(path)
            self.preparation = PreparationHost(self.preparation_root, self.accounts, config,
                playing=lambda: self.playing, report=self.report)
        except (ValueError, OSError, RuntimeError):
            self.report('OPTIONAL_PREPARATION_UNAVAILABLE')

    def close(self):
        if getattr(self, '_shutdown_complete', False):
            return
        self.stopping.set()
        self.idle = False
        errors = []
        def report(code):
            try:
                self.report(code)
            except Exception:
                pass  # Observability must not interrupt ownership drainage.
        def drain(close, label):
            report('SHUTDOWN_BEGIN_' + label)
            try:
                close()
            except BaseException as error:
                errors.append(error)
                report('SHUTDOWN_FAILED_' + label + '_' + type(error).__name__)
            else:
                report('SHUTDOWN_DRAINED_' + label)
        # Reject queued owner calls before draining HTTP. No new work may be
        # admitted after stopping; every already admitted consumer stays owned.
        while True:
            try:
                job = self.calls.get_nowait()
            except Empty:
                break
            job.error = True
            job.done.set()
        drain(lambda: self.runtime.close(release_lease=False), 'RUNTIME')
        playback = getattr(self, 'playback', None)
        if playback is not None:
            drain(playback.close, 'PLAYBACK')
        for label, component in (('IMAGES', self.images), ('PREPARATION', self.preparation), ('STREAMS', self.streams)):
            if component is not None:
                drain(component.close, label)
        drain(self.unsubscribe, 'ACCOUNT_SUBSCRIPTION')
        with self.engine_lock:
            engine = self.engine
        if engine is not None:
            drain(engine.close, 'ENGINE')
        for label, worker in (('ENGINE_WORKER', self.engine_worker), ('CATALOG_WORKER', self.refresh_worker)):
            if worker is not None:
                drain(worker.join, label)
        self.shutdown_errors = tuple(type(error).__name__ for error in errors)
        if errors:
            # Unknown drainage is not quiescence. Retain the OS descriptor;
            # retry may finish cleanup, or actual process exit reclaims it.
            # The installer still has its independent 15-second refusal bound.
            raise errors[0]
        self.owner = self.preparation = self.engine = None
        self._shutdown_complete = True
        self.runtime.lease.close()
