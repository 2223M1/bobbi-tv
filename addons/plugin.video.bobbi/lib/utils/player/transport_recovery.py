"""One same-file BT-to-115 recovery; workers verify, the monitor issues controls.

Nothing here treats a stall as EOF or applies a global seek/track operation.
The native capsule owns initial position and presentation restoration.
"""
from copy import deepcopy
import math
import re
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4

from lib.cinema import _shared
from bobbi_core.video_context import checked_video


DIAGNOSTIC_EVENTS = frozenset('''
ENTRY_POLICY ENTRY_NOT_BT ENTRY_PREPARED ENTRY_NO_INSTANCE ENTRY_CANCELLED ENTRY_NOT_BUFFERING ENTRY_ACTIVE
CONTEXT_OWNER_CHANGED CONTEXT_REJECTED CONTEXT_READY CONTEXT_CACHED CONTEXT_ERROR
WATCH_SUSPENDED WATCH_CONTEXT_MISSING WATCH_CONTEXT_CHANGED WATCH_NOT_BUFFERING WATCH_INVALID_POSITION
WATCH_STARTED WATCH_MOVING WATCH_WAITING WATCH_THRESHOLD
WORKER_START WORKER_READY WORKER_UNAVAILABLE WORKER_CANCELLED WORKER_ERROR WORKER_START_ERROR WORKER_DISCARDED
VERIFY_SNAPSHOT VERIFY_NO_CANDIDATE VERIFY_AMBIGUOUS VERIFY_CANCELLED VERIFY_STATUS VERIFY_STATUS_REJECTED
VERIFY_VERSION_MISMATCH VERIFY_RESOLVE VERIFY_READY VERIFY_UNAVAILABLE
CAPTURE_REQUEST CAPTURE_REPLY CAPTURE_REJECTED CAPTURE_ERROR
CAPTURE_REVERIFY_SCHEDULED CAPTURE_REVERIFY_UNAVAILABLE
POLL_REPLY POLL_IO_ERROR POLL_ERROR POLL_INVALID_REPLY POLL_EXPIRED POLL_RECEIPT_REJECTED POLL_STOPPED
STOP_REQUEST STOP_REPLY STOP_IO_ERROR STOP_ERROR
RESERVE_SKIPPED RESERVE_REQUEST RESERVE_READY RESERVE_ERROR RECOVERY_CLOSED RECOVERY_REJECTED RECOVERY_CONSUMED
DIAGNOSTIC_LIMIT
'''.split())
DIAGNOSTIC_STATES = frozenset('''
NONE UNKNOWN WATCHING CAPTURING PENDING CAPTURED STOP_REQUESTED STOPPING STOPPED EXPIRED REJECTED CONSUMED
QUEUED ACCEPTED ABSENT VALIDATING FAILED READY UNAVAILABLE CANCELLED NOT_READY ALREADY_ATTEMPTED UNSUPPORTED
'''.split())
DIAGNOSTIC_LIMIT = 64
DIAGNOSTIC_ERRORS = frozenset(('NONE', 'TIMEOUT', 'OS_ERROR', 'VALUE_ERROR', 'TYPE_ERROR',
                              'KEY_ERROR', 'RUNTIME_ERROR', 'OTHER'))


def exception_kind(error):
    if error is None:
        return 'NONE'
    if isinstance(error, str) and error in DIAGNOSTIC_ERRORS:
        return error
    for kind, label in ((TimeoutError, 'TIMEOUT'), (OSError, 'OS_ERROR'), (ValueError, 'VALUE_ERROR'),
                        (TypeError, 'TYPE_ERROR'), (KeyError, 'KEY_ERROR'), (RuntimeError, 'RUNTIME_ERROR')):
        if isinstance(error, kind):
            return label
    return 'OTHER'  # Never an exception name, message, URL or credential.


def diagnostic_state(state):
    if state is None:
        return 'NONE'
    return (state.upper() if isinstance(state, str) and len(state) <= 32
            and state.upper() in DIAGNOSTIC_STATES else 'UNKNOWN')


def elapsed_milliseconds(started):
    try:
        return max(0, min(600000, int((monotonic() - started) * 1000)))
    except (ValueError, TypeError, OverflowError):
        return None


def diagnostic_note(callback, event, state=None, error=None, elapsed_ms=None):
    if callback is None:
        return
    try:
        if not isinstance(event, str) or event not in DIAGNOSTIC_EVENTS:
            return
        callback(event, state=diagnostic_state(state), error=exception_kind(error),
                 elapsed_ms=elapsed_ms if type(elapsed_ms) is int and 0 <= elapsed_ms <= 600000 else None)
    except Exception:
        pass  # Observability must never change playback/control behavior.


class Diagnostics:
    """Bounded, thread-safe per-session deduplication, not playback authority."""
    def __init__(self, emit, request_id=''):
        self.emit = emit
        self.request = request_id if isinstance(request_id, str) and re.fullmatch('[0-9a-f]{32}', request_id) else ''
        self.seen, self.lock = set(), Lock()

    def __call__(self, event, state=None, error=None, elapsed_ms=None):
        if not isinstance(event, str) or event not in DIAGNOSTIC_EVENTS:
            return
        state = diagnostic_state(state)
        error = exception_kind(error)
        key = (event, state, error)
        with self.lock:
            if key in self.seen or len(self.seen) >= DIAGNOSTIC_LIMIT:
                return
            if len(self.seen) == DIAGNOSTIC_LIMIT - 1:
                key = ('DIAGNOSTIC_LIMIT', 'NONE', 'NONE')
            self.seen.add(key)
            row = dict(schema=1, request=self.request, sequence=len(self.seen),
                       event=key[0], state=key[1], error=key[2])
            if key[0] != 'DIAGNOSTIC_LIMIT' and type(elapsed_ms) is int and 0 <= elapsed_ms <= 600000:
                row['elapsed_ms'] = elapsed_ms
        try:
            self.emit(row)  # Do not hold the lock across the optional log sink.
        except Exception:
            pass


def exact_context(data, target, snapshot, instance):
    from bobbi_core.playback_request import torrent_file_identity
    from bobbi_core.source_intent import checked_body
    if (data.get('selection_policy') != 'exact' or not data.get('is_torrent')
            or data.get('prepared_resource_id') or not isinstance(target, dict)):
        return None
    try:
        media, selected, source_hash = checked_body(target)
        television = data.get('tv_data') or {}
        if (str(media['tmdb_id']) != str((data.get('ids') or {}).get('tmdb_id'))
                or (media['kind'] == 'tv') != (data.get('mode') in ('tv', 'anime', 'episode'))
                or (media['kind'] == 'tv' and any(str(media[key]) != str(television.get(key))
                                                for key in ('season', 'episode')))):
            return None
        desired, observed = snapshot['desired'], snapshot['observed']
        request = data['request_id']
        if (target['purpose'] != 'current' or target['request_id'] != request
                or desired['request_id'] != request or observed['request_id'] != request
                or desired['cancelled'] or desired['file_evidence'] != 'AUTO_VERIFIED_FILE'
                or observed['native_instance'] != instance or not observed['av_started']
                or observed['file_identity'] != desired['file_identity']):
            return None
        canonical = torrent_file_identity(source_hash, selected['torrent_file_id'],
                                          selected['torrent_path'], selected['torrent_file_bytes'])
        identity = desired['selection_identity']
        expected = identity + '|' + canonical if identity.startswith('transport:') else canonical
        if desired['file_identity'] != expected:
            return None
        current_media = ('tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], media['episode'])
                        if media['kind'] == 'tv' else 'tmdb:movie:{}'.format(media['tmdb_id']))
        return dict(owner={key: snapshot[key] for key in ('boot_id', 'epoch')}, request_id=request,
            native_instance=instance, selection_identity=identity, file_identity=expected,
            selected=deepcopy(selected), media_id=current_media, data=deepcopy(data),
            account_scope=deepcopy(data['_account']))
    except (ValueError, TypeError, KeyError):
        return None


def verify_ready(context, cancelled, diagnostic=None):
    """Actual qualified same-file lookup plus one nonce-bound fresh resolver."""
    from .bt_continuity import prepared_snapshot
    from bobbi_core.preparation_client import call, resolve_entry
    diagnostic_note(diagnostic, 'VERIFY_SNAPSHOT')
    snapshot = prepared_snapshot()
    candidates = []
    for title in snapshot.get('titles', []):
        for row in title.get('sources', []):
            try:
                video = checked_video(row['video_context'])
                if (row.get('state') == 'qualified' and video['media_id'] == context['media_id']
                        and video['selected'] == context['selected']
                        and row.get('prepared_version_key') == video['release_key']
                        and row.get('prepared_source_info_hash') == context['selected']['source_info_hash']
                        and row.get('bytes') == context['selected']['torrent_file_bytes']
                        and re.fullmatch('[0-9a-f]{64}', row.get('prepared_qualification', ''))):
                    candidates.append(row)
            except (KeyError, TypeError, ValueError):
                continue
    if len(candidates) != 1:
        diagnostic_note(diagnostic, 'VERIFY_NO_CANDIDATE' if not candidates else 'VERIFY_AMBIGUOUS')
        return None
    if cancelled():
        diagnostic_note(diagnostic, 'VERIFY_CANCELLED')
        return None
    diagnostic_note(diagnostic, 'VERIFY_STATUS')
    status = call('status', {'request_id': context['request_id']}, expected_account=context['account_scope'])
    if (cancelled() or status.get('request_id') != context['request_id'] or status.get('state') != 'accepted'):
        diagnostic_note(diagnostic, 'VERIFY_STATUS_REJECTED',
                        state=status.get('state') if isinstance(status, dict) else 'UNKNOWN')
        return None
    versions = {row['version_key'] for row in status.get('result', {}).get('tasks', [])
                if row.get('media_id') == context['media_id']}
    entry = candidates[0]
    if versions != {entry['prepared_version_key']}:
        diagnostic_note(diagnostic, 'VERIFY_VERSION_MISMATCH')
        return None
    diagnostic_note(diagnostic, 'VERIFY_RESOLVE')
    result = resolve_entry(context['data'], snapshot, entry, cancelled, return_verification=True)
    if result and not cancelled():
        from bobbi_core.prepared_transport import playback_path
        value = dict(result, url=playback_path(snapshot['mount_root'], result['entry']))
        diagnostic_note(diagnostic, 'VERIFY_READY')
        return value
    diagnostic_note(diagnostic, 'VERIFY_UNAVAILABLE')
    return None


def checked_handoff(value, data):
    if (not isinstance(value, dict) or set(value) != {'capsule', 'child_request_id', 'position_ms', 'file_identity'}
            or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', str(value.get('capsule', '')))
            or value['child_request_id'] != data.get('request_id')
            or data.get('_ui_reserved_request') != data.get('request_id')
            or type(value['position_ms']) is not int or not 0 <= value['position_ms'] <= 864000000
            or not isinstance(value['file_identity'], str) or not 1 <= len(value['file_identity']) <= 1024
            or data.get('is_torrent') or not data.get('prepared_resource_id')):
        raise ValueError('Invalid same-file transport handoff')
    return deepcopy(value)


def child_data(context, result, child, capsule, position_ms):
    data = deepcopy(context['data'])
    for key in tuple(data):
        if (key.startswith('_transport_') or 'resume' in key.lower()
                or key in {'progress', 'current_time', 'total_time', 'next_tv_data', 'playback_session_id',
                           'request_id', '_ui_reserved_request', '_parent_request_id', '_continuation_token',
                           'subtitles_path', 'stream_subtitles', '_share', 'magnet', 'is_pack', 'pack_type',
                           'pack_seasons', 'episode_binding', '_bobi_start_over', '_catalog_next',
                           '_bt_next_selected', '_bt_current_selected', '_next_recheck', '_next_transport',
                           '_next_cloud_pending', '_next_cloud_verified', 'completed', 'terminal_reason'}):
            data.pop(key, None)
    entry = result['entry']
    data.update(url=result['url'], is_torrent=False, type='Direct', indexer='115 · CD2',
        source_title=entry['title'], info_hash=context['selected']['source_info_hash'],
        prepared_resource_id=entry['key'], prepared_version_key=entry['prepared_version_key'],
        prepared_source_info_hash=entry['prepared_source_info_hash'], video_context=deepcopy(entry['video_context']),
        request_id=child, _ui_reserved_request=child, direct_playback_handoff=True,
        autoplay=True, playnext_context=False,
        _transport_handoff=dict(capsule=capsule, child_request_id=child,
                                position_ms=position_ms, file_identity=context['file_identity']))
    checked_handoff(data['_transport_handoff'], data)
    return data


class Recovery:
    def __init__(self, verify=verify_ready, threshold=6.0, retry=5.0, diagnostic=None):
        self.verify, self.threshold, self.retry = verify, threshold, retry
        self.diagnostic = diagnostic
        self.position = self.since = None
        self.revision, self.due = 0, 0.
        self.worker = self.job = self.context = self.result = None
        self.state, self.attempted, self.stop_sent = 'WATCHING', False, False
        self.token = self.child = self.capsule = None
        self.position_ms = None
        self.deadline, self.poll_due = 0., 0.
        self.closed = False
        self._diagnostic_ready_at = None
        self._capture_reverify_used = False

    def note(self, event, state=None, error=None, elapsed_ms=None):
        diagnostic_note(self.diagnostic, event, state, error, elapsed_ms)

    def reset_watch(self):
        self.position = self.since = None
        self.revision += 1
        if self.job:
            self.job['cancel'].set()
        if not self.attempted:
            self.result = None
        if self.attempted and self.state not in ('STOPPING', 'STOPPED', 'CONSUMED'):
            self.state = 'REJECTED'

    def abandon(self):
        self.reset_watch()
        self.state = 'REJECTED'

    def stalled(self, now, position, buffering, suspended):
        if (suspended or buffering is not True or type(position) not in (int, float)
                or not math.isfinite(position) or not 0 <= position <= 864000
                or self.position is None or abs(position - self.position) >= .25):
            if suspended:
                self.note('WATCH_SUSPENDED')
            elif buffering is not True:
                self.note('WATCH_NOT_BUFFERING')
            elif (type(position) not in (int, float) or not math.isfinite(position)
                  or not 0 <= position <= 864000):
                self.note('WATCH_INVALID_POSITION')
            else:
                self.note('WATCH_STARTED' if self.position is None else 'WATCH_MOVING')
            self.reset_watch()
            if (not suspended and buffering is True and type(position) in (int, float)
                    and math.isfinite(position) and 0 <= position <= 864000):
                self.position, self.since = position, now
            return False
        stalled = self.since is not None and now - self.since >= self.threshold
        self.note('WATCH_THRESHOLD' if stalled else 'WATCH_WAITING')
        return stalled

    def tick(self, now, position, buffering, suspended, context, command):
        if self.closed or self.state in ('REJECTED', 'CONSUMED'):
            self.note('RECOVERY_CLOSED' if self.closed else 'RECOVERY_' + self.state)
            return
        if suspended or context is None:
            self.note('WATCH_SUSPENDED' if suspended else 'WATCH_CONTEXT_MISSING')
            if self.stop_sent:
                self.abandon()
            else:
                self.reset_watch()
            return
        if self.context and any(context[key] != self.context[key] for key in
                ('owner', 'request_id', 'native_instance', 'file_identity', 'account_scope')):
            self.note('WATCH_CONTEXT_CHANGED')
            self.abandon()
            return
        if self.stop_sent:
            self.poll(now, command)
            return
        active_stall = self.stalled(now, position, buffering, suspended)
        if self.worker is not None and not self.worker.is_alive():
            self.worker.join()
            job, self.worker, self.job = self.job, None, None
            self.due = now + self.retry
            if active_stall and job['revision'] == self.revision and not job['cancel'].is_set():
                self.result = job.get('result')
                self._diagnostic_ready_at = job.get('finished_at')
            else:
                self.note('WORKER_DISCARDED')
            if job.get('capture_reverify'):
                # One fresh bounded verification only. Failed/cancelled/stale
                # results cannot turn this exception into an unbounded loop.
                if self.result:
                    self.attempted = False
                else:
                    self.state = 'REJECTED'
                    self.note('CAPTURE_REVERIFY_UNAVAILABLE')
                    return
        if not active_stall:
            return
        if self.token:
            self.poll(now, command)
            return
        if self.result and not self.attempted:
            self.attempted = True
            self.context, self.child = deepcopy(context), uuid4().hex
            body = dict(context['owner'], request_id=context['request_id'], operation='transport_capture',
                native_instance=context['native_instance'], child_request_id=self.child,
                account_scope=context['account_scope'], prepared_verification=self.result['verification'],
                selection_identity=context['selection_identity'])
            try:
                self.note('CAPTURE_REQUEST', elapsed_ms=elapsed_milliseconds(self._diagnostic_ready_at))
                reply = command(body)
                self.note('CAPTURE_REPLY', state=reply.get('state') if isinstance(reply, dict) else 'UNKNOWN')
                if (isinstance(reply, dict) and set(reply) == {'authorized', 'state'}
                        and reply['authorized'] is False and reply['state'] == 'NOT_READY'
                        and not self._capture_reverify_used):
                    # Host returned before _owner_request/native control. Its
                    # short-lived completed nonce may have expired while the
                    # monitor was busy. Discard it; verify once with a new nonce
                    # using the unchanged file/account and existing backoff.
                    self._capture_reverify_used = True
                    self.attempted, self.result = False, None
                    self.child = None
                    self.due = now + self.retry
                    self.note('CAPTURE_REVERIFY_SCHEDULED')
                    return
                if (not isinstance(reply, dict) or reply.get('authorized') is not True
                        or not re.fullmatch('[0-9a-f]{32}', str(reply.get('token', '')))):
                    self.state = 'REJECTED'
                    self.note('CAPTURE_REJECTED')
                    return
                self.token, self.state = reply['token'], 'CAPTURING'
                self.deadline, self.poll_due = now + 30., now
            except (OSError, ValueError, TypeError, RuntimeError, KeyError) as error:
                self.note('CAPTURE_ERROR', error=error)
                self.state = 'REJECTED'  # Lost capture acknowledgement never triggers a stop.
            return
        if not self.attempted and self.worker is None and now >= self.due:
            self.context = deepcopy(context)
            job = dict(revision=self.revision, cancel=Event(), context=deepcopy(context),
                       capture_reverify=self._capture_reverify_used)
            if job['capture_reverify']:
                self.attempted = True  # Consumed even if the worker cannot start.
            self.job = job
            def run():
                try:
                    started = monotonic()
                    self.note('WORKER_START')
                    result = (self.verify(job['context'], job['cancel'].is_set, diagnostic=self.diagnostic)
                              if self.verify is verify_ready else self.verify(job['context'], job['cancel'].is_set))
                    if not job['cancel'].is_set():
                        job['result'] = deepcopy(result)
                        job['finished_at'] = monotonic()
                        self.note('WORKER_READY' if result else 'WORKER_UNAVAILABLE',
                                  elapsed_ms=elapsed_milliseconds(started))
                    else:
                        self.note('WORKER_CANCELLED')
                except (OSError, ValueError, TypeError, RuntimeError, KeyError) as error:
                    self.note('WORKER_ERROR', error=error)
                    job['result'] = None
            self.worker = Thread(target=run, name='bobbi-transport-verify', daemon=True)
            try:
                self.worker.start()
            except RuntimeError as error:
                self.note('WORKER_START_ERROR', error=error)
                self.worker = self.job = None
                self.due = now + self.retry
                if job['capture_reverify']:
                    self.state = 'REJECTED'

    def poll(self, now, command, allow_stop=True):
        if self.closed or not self.token or self.state in ('REJECTED', 'CONSUMED'):
            return None
        if now >= self.deadline:
            self.note('POLL_EXPIRED')
            self.abandon()
            return None
        if now < self.poll_due:
            return None
        self.poll_due = now + .25
        context = self.context
        args = dict(context['owner'], request_id=context['request_id'], token=self.token,
                    account_scope=context['account_scope'])
        try:
            reply = command(dict(args, operation='transport_status'))
        except OSError as error:
            self.note('POLL_IO_ERROR', error=error)
            return None  # Keep a possibly queued stop until its real terminal/TTL.
        except (ValueError, TypeError, RuntimeError) as error:
            self.note('POLL_ERROR', error=error)
            self.abandon()
            return None
        if not isinstance(reply, dict):
            self.note('POLL_INVALID_REPLY')
            return None
        state = reply.get('state')
        self.note('POLL_REPLY', state=state)
        if state in ('REJECTED', 'EXPIRED'):
            self.abandon()
            return None
        if state not in ('CAPTURED', 'STOPPED'):
            return None
        capsule, position = reply.get('capsule'), reply.get('position_ms')
        if (not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', str(capsule))
                or type(position) is not int or not 0 <= position <= 864000000
                or reply.get('child_request_id') != self.child
                or reply.get('file_identity') != context['file_identity']
                or (self.capsule is not None and capsule != self.capsule)):
            self.note('POLL_RECEIPT_REJECTED')
            self.abandon()
            return None
        self.capsule, self.position_ms = capsule, position
        if state == 'STOPPED' and self.stop_sent:
            self.state = 'STOPPED'
            self.note('POLL_STOPPED')
            return reply
        if state == 'CAPTURED' and allow_stop and not self.stop_sent:
            self.stop_sent, self.state = True, 'STOPPING'
            try:
                self.note('STOP_REQUEST')
                response = command(dict(args, operation='transport_stop'))
                self.note('STOP_REPLY', state=('QUEUED' if isinstance(response, dict) and response.get('queued') is True
                          else 'REJECTED' if isinstance(response, dict) and response.get('queued') is False else 'UNKNOWN'))
                if isinstance(response, dict) and response.get('queued') is False:
                    self.abandon()
            except OSError as error:
                self.note('STOP_IO_ERROR', error=error)
                pass  # Query this exact grant; never resend transport_stop.
            except (ValueError, TypeError, RuntimeError) as error:
                self.note('STOP_ERROR', error=error)
                self.abandon()
        return None

    def reserve(self, command):
        if self.state != 'STOPPED':
            self.note('RESERVE_SKIPPED', state=self.state)
            return None
        self.state = 'CONSUMED'  # Lost reservation replies are never blindly replayed.
        context = self.context
        try:
            self.note('RESERVE_REQUEST')
            response = command(dict(context['owner'], request_id=context['request_id'],
                operation='reserve_child', token=self.token, child_request_id=self.child,
                selection_identity=context['selection_identity'], account_scope=context['account_scope']))
            from bobbi_core.playback_request import context as checked_owner
            checked_owner(response, self.child)
            data = child_data(context, self.result, self.child, self.capsule, self.position_ms)
            self.note('RESERVE_READY')
            return data
        except (OSError, ValueError, TypeError, RuntimeError, KeyError) as error:
            self.note('RESERVE_ERROR', error=error)
            return None

    def close(self):
        self.note('RECOVERY_CLOSED')
        self.closed = True
        if self.job:
            self.job['cancel'].set()
