"""Single serialized owner adapter. No cloud, UI properties or unscoped Stop.

The resident service is the only caller. Native IO is supplied by the Kodi
adapter; tests supply a simulated actor and are not hardware acceptance.
"""
from copy import deepcopy
from threading import get_ident
from uuid import uuid4
from time import monotonic
import re

from bobbi_core.native_receipt import ReceiptHistory, SHA, receipt, subtitle_snapshot_follows
from bobbi_core.playback_owner import PlaybackOwner


class NativeObservationUnavailable(OSError):
    """Temporary native transport failure, not an invalid identity/protocol."""


def _subtitle_failure(reason):
    """Bounded observed failures, never infer 'no subtitles' from an IO error."""
    groups = {
        'NO_QUALIFIED_CHINESE_SUBTITLE': {'NO_MATCHED_CHINESE_TEXT'},
        'SUBTITLE_PROVIDER_AUTH_REQUIRED': {'ASSRT_TOKEN_NOT_CONFIGURED', 'ASSRT_HTTP_401', 'ASSRT_HTTP_403'},
        'SUBTITLE_PROVIDER_RATE_LIMITED': {'ASSRT_RATE_LIMIT', 'ASSRT_HTTP_429'},
        'SUBTITLE_LOOKUP_TIMEOUT': {'SUBTITLE_DEADLINE', 'SUBTITLE_IO_DEADLINE',
                                   'SUBTITLE_DOWNLOAD_TIMEOUT', 'ASSRT_HTTP_408'},
        'SUBTITLE_LOOKUP_STOPPED': {'CANCELLED_OR_DEADLINE', 'TORRENT_SUBTITLE_CANCELLED_OR_TIMEOUT'},
        'SUBTITLE_PROVIDER_UNAVAILABLE': {'ASSRT_HTTP_400', 'ASSRT_HTTP_404', 'ASSRT_HTTP_410',
            'ASSRT_HTTP_500', 'ASSRT_HTTP_502', 'ASSRT_HTTP_503', 'ASSRT_HTTP_504',
            'ASSRT_RESPONSE_INVALID', 'ASSRT_QUOTA_STATE_INVALID'},
        'SUBTITLE_CANDIDATE_UNAVAILABLE': {'MATCHED_SUBTITLE_UNAVAILABLE'},
        'SUBTITLE_TIMELINE_REJECTED': {'SUBTITLE_TIMELINE_MISMATCH'},
        'SUBTITLE_TEXT_REJECTED': {'SUBTITLE_NOT_TEXT', 'SUBTITLE_CHINESE_INSUFFICIENT',
            'SUBTITLE_CHINESE_PARTIAL', 'SUBTITLE_ENCODING_UNSUPPORTED'},
        'SUBTITLE_IDENTITY_REJECTED': {'TORRENT_METADATA_IDENTITY_CHANGED',
            'TORRENT_PLAYING_FILE_CHANGED', 'TORRENT_SUBTITLE_IDENTITY_MISMATCH'},
        'SUBTITLE_CONTEXT_UNAVAILABLE': {'MEDIA_CONTEXT_MISSING'},
        'SUBTITLE_SERVICE_UNAVAILABLE': {'SUBTITLE_IPC_UNAVAILABLE', 'SUBTITLE_IPC_TIMEOUT',
            'SUBTITLE_IPC_REJECTED', 'SUBTITLE_IO_REAP_FAILED', 'SUBTITLE_IO_BUSY',
            'SUBTITLE_IO_PYTHON_UNAVAILABLE', 'SUBTITLE_IO_LIFETIME_FAILED', 'SUBTITLE_ACCOUNT_CHANGED'},
        'MANUAL_PRESERVED': {'MANUAL_PRESERVED'},
    }
    if isinstance(reason, str):
        for status, known in groups.items():
            if reason in known:
                return {'status': status, 'reason': reason}
        # Unknown HTTP error codes still prove a provider response, not an
        # empty search or an unknown local failure. Do not infer auth, quota or
        # retry permission from nonstandard codes such as the observed 493.
        if re.fullmatch(r'ASSRT_HTTP_[45][0-9]{2}', reason):
            return {'status': 'SUBTITLE_PROVIDER_UNAVAILABLE', 'reason': reason}
    # Arbitrary provider messages, URLs and exception text cannot cross this
    # presentation boundary. Unknown failure is not proof of an empty search.
    return {'status': 'SUBTITLE_LOOKUP_UNAVAILABLE', 'reason': 'SUBTITLE_REASON_UNKNOWN'}


class PlaybackAuthority:
    def __init__(self, native):
        self.native = native
        self.owner = PlaybackOwner()
        self.history = ReceiptHistory()
        self.thread = get_ident()
        self.bound_url = None
        self.pending_stop = None
        self.last_native = None
        self.terminal_seen_at = None
        self.native_idle = False
        self.native_epoch = None
        self.reservation_epoch = None
        self.previous_instance = None
        self.gui_state = {}
        self.selection_gui_intent = None
        self.native_windows = {}
        self.continuation = None
        self.reserved_continuation = False
        self.subtitle_pending = None
        self.subtitle_completed = None
        self.start_receipt = None
        self.start_receipt_consumed = False
        self.loading_close = None
        self.fullscreen_attempt = None
        self.subtitle_status_receipt = None
        self.dismissed_startup_failure = None

    def _handoff_note(self, request_id, stage, reason, attempt):
        report = getattr(self.native, 'handoff_diagnostic', None)
        if report is not None:
            try:
                report(request_id, stage, reason, attempt)
            except Exception:
                pass  # Optional diagnostics cannot change playback ownership.

    def _loading_window(self, dialog_id, token):
        read = getattr(self.native, 'loading_window', None)
        if read is None:
            return None
        try:
            value = read(dialog_id, token)
        except (OSError, ValueError, RuntimeError):
            return None
        if (not isinstance(value, dict)
                or any(type(value.get(key)) is not bool for key in ('visible', 'matching', 'modal'))
                or type(value.get('active_window')) is not int):
            return None
        return value

    def _retry_retired_loading_fullscreen(self, args, instance, row):
        """One conditional requeue after retirement; native Claim remains final."""
        attempt, closing, owner = self.fullscreen_attempt, self.loading_close, self.owner
        if (not attempt or not closing or attempt['retried'] or not closing['released']
                or attempt['args'] != args or closing['args'] != args
                or attempt['instance'] != instance or closing['instance'] != instance
                or not owner.owns_instance(*args, instance)
                or owner.desired['fullscreen_confirmed'] or not owner.desired['fullscreen_allowed']
                or owner.windows or owner.user_intent != attempt['owner_intent']
                or not row or row['phase'] != 'AV_STARTED' or row['native_instance'] != instance
                or row['user_intent'] != attempt['native_intent']
                or row['user_intent'] != closing['native_intent']
                or self.native_epoch != self.reservation_epoch
                or self.gui_state['gui_user_intent'] != attempt['gui_intent']
                or self.gui_state['gui_user_intent'] != self.selection_gui_intent
                or not 0 <= monotonic() - attempt['started'] < 1.0):
            return False
        # Exactly the registered resolver's one retirement edge may invalidate
        # the first queued command. Other GUI changes do not grant retry rights.
        if (attempt['generation'] != closing['generation']
                or self.gui_state['gui_generation'] != closing['generation'] + 1):
            return False
        window = self._loading_window(closing['dialog_id'], closing['token'])
        if (not window or window['visible'] or window['modal']
                or window['active_window'] != closing['active_window']):
            return False
        closing['hidden'] = True
        attempt['retried'] = True
        command = dict(native_instance=instance, request_id=args[2],
                       selection_epoch=self.reservation_epoch,
                       gui_generation=self.gui_state['gui_generation'],
                       gui_user_intent=self.selection_gui_intent)
        self._handoff_note(args[2], 'RETRY', 'OWNED_LOADING_RETIRED', 2)
        result = self.native.fullscreen(command)
        return isinstance(result, dict) and result.get('queued') is True

    def _serial(self):
        if get_ident() != self.thread:
            raise RuntimeError('Playback authority has exactly one service thread')

    def event(self, sender, method, data):
        self._serial()
        if sender != 'xbmc' or method != 'Player.OnBobiState':
            return False
        row = self.history.accept(data)
        if row is None:
            return False
        self.last_native = row
        owner = self.owner
        if (self.start_receipt and owner.desired
                and row['request_id'] == owner.desired['request_id']
                and row['url_sha256'] == self.bound_url):
            self.start_receipt_consumed = True
        if row['phase'] == 'TERMINAL':
            self.terminal_seen_at = monotonic()
            # Only immutable native receipts reach here. ReceiptHistory already
            # deduplicates terminal events; log before cancellation can revoke
            # client reads. Diagnostic failure must never change lifecycle rules.
            diagnostic = getattr(self.native, 'terminal_diagnostic', None)
            if diagnostic is not None:
                try:
                    diagnostic(row['request_id'], row['native_instance'], row['reason'])
                except Exception:
                    pass
            # Startup may fail before the service polls OPEN. An immutable
            # matching terminal can establish OPEN, never invent AV_STARTED.
            desired = owner.desired
            if (owner.observed is None and desired and desired['file_bound']
                    and row['url_sha256'] == self.bound_url):
                owner.observe_open(owner.boot_id, desired['epoch'], row['request_id'],
                                   row['native_instance'], row['file_identity'])
            if owner.observed and owner.observed['native_instance'] == row['native_instance']:
                owner.observe_terminal(row['native_instance'], row['reason'])
                terminal = owner.terminal
                explicit_next = (self.continuation and self.continuation['kind'] == 'manual'
                    and self.continuation['request_id'] == terminal['request_id']
                    and self.continuation['native_instance'] == terminal['native_instance']
                    and self.continuation['native_user_intent'] == row['user_intent']
                    and terminal['reason'] == 'STOP')
                if (owner.desired and terminal['request_id'] == owner.desired['request_id']
                        and terminal['reason'] != 'NATURAL_EOF' and not explicit_next):
                    owner.cancel(owner.boot_id, owner.epoch, terminal['request_id'])
            return True
        desired = owner.desired
        if (row['phase'] in ('OPEN', 'AV_STARTED') and desired and desired['file_bound']
                and row['url_sha256'] == self.bound_url):
            observe = owner.observe_started if row['phase'] == 'AV_STARTED' else owner.observe_open
            observe(owner.boot_id, desired['epoch'], row['request_id'],
                    row['native_instance'], row['file_identity'])
        observed = owner.observed
        if observed and observed['native_instance'] == row['native_instance']:
            prior_intent = observed.get('native_user_intent')
            if prior_intent is not None and prior_intent != row['user_intent']:
                owner.user_intent += 1
                owner.pause = None
            observed['native_user_intent'] = row['user_intent']
            observed['paused'] = row['paused']
            owner.confirm_owned_pause(row['native_instance'], row['paused'])
        return True

    def refresh(self, strict_protocol=False):
        self._serial()
        try:
            response = self.native.state()
        except (OSError, RuntimeError) as error:
            raise NativeObservationUnavailable('Native observation temporarily unavailable') from error
        if strict_protocol and (not isinstance(response, dict) or type(response.get('protocol')) is not int):
            raise RuntimeError('Native presentation protocol requires integer version')
        if not isinstance(response, dict) or response.get('protocol') != 1 or 'playback' not in response:
            raise RuntimeError('原生播放实例接口不可用，未回退到不带归属的控制')
        if type(response.get('selection_epoch')) is not int or response['selection_epoch'] < 0:
            raise RuntimeError('原生开播请求屏障不可用')
        self.native_epoch = response['selection_epoch']
        self.gui_state = {key: response.get(key) for key in
                          ('gui_generation', 'gui_user_intent', 'fullscreen_instance')}
        if (self.reservation_epoch is not None and self.native_epoch != self.reservation_epoch
                and self.owner.desired and not self.owner.desired['cancelled']):
            self.owner.cancel(self.owner.boot_id, self.owner.epoch, self.owner.desired['request_id'])
        row = receipt(response.get('playback'))
        self.native_idle = response['playback'] is None
        if not self.native_idle and row is None:
            raise ValueError('Invalid native playback is not an idle player')
        if row:
            observed = self.owner.observed
            if (row['phase'] != 'TERMINAL' and observed
                    and observed['native_instance'] != row['native_instance']):
                self.owner.observe_terminal(observed['native_instance'], 'SUPERSEDED')
            self.event('xbmc', 'Player.OnBobiState', row)
            if row['phase'] != 'TERMINAL' and self.owner.observed is None:
                self.owner.observe_external(row['native_instance'], row['file_identity'] or row['url_sha256'])
        self._reconcile_windows(response.get('windows', []), row)
        return row

    def _continuation_receipt(self, row):
        if row is not None:
            return row
        # CApplicationPlayer destroys IPlayer after EOF; polling then returns
        # null. Retain the already observed immutable terminal, not an inferred
        # EOF. The native selection barrier and GUI intent still gate takeover.
        previous, terminal = self.last_native, self.owner.terminal
        if (self.native_idle and previous and terminal and previous['phase'] == 'TERMINAL'
                and previous['native_instance'] == terminal['native_instance']
                and previous['request_id'] == terminal['request_id']
                and self.native_epoch == self.reservation_epoch
                and self.terminal_seen_at is not None and 0 <= monotonic() - self.terminal_seen_at <= 3.0):
            return previous
        return None

    def _reconcile_windows(self, windows, row):
        if not isinstance(windows, list) or len(windows) > 8:
            raise ValueError('Bounded native window snapshot required')
        current = {}
        for window in windows:
            if (not isinstance(window, dict) or window.get('role') not in ('subtitles', 'audio')
                    or not isinstance(window.get('token'), str)
                    or not re.fullmatch('[0-9a-f]{32}', window['token'])):
                raise ValueError('Native window token required')
            current[window['token']] = window
        owner = self.owner
        # Acquire nested windows before releasing closing parents.
        for token, window in current.items():
            if token in self.native_windows or not row or row['phase'] != 'AV_STARTED':
                continue
            args = (owner.boot_id, owner.epoch, window.get('request_id'))
            instance = window.get('native_instance')
            if row['native_instance'] != instance or not owner.owns_instance(*args, instance):
                continue
            if owner.register_window(*args, token, window['role']):
                self.native_windows[token] = (args, instance)
                action = owner.acquire_pause(*args, instance, token, row['paused'])
                if action:
                    self._control(row, action['action'], token)
        for token in tuple(self.native_windows):
            if token in current:
                continue
            args, instance = self.native_windows.pop(token)
            action = owner.release_pause(*args, instance, token)
            owner.close_window(*args, token)
            if action and row and row['native_instance'] == instance:
                self._control(row, action['action'], token)

    def _control(self, row, action, window_token=None):
        command = {'native_instance': row['native_instance'], 'user_intent': row['user_intent'],
                   'expected_sequence': row['sequence'], 'selection_epoch': self.native_epoch,
                   'action': action, 'command_id': uuid4().hex}
        if window_token:
            command['window_token'] = window_token
        result = self.native.control(command)
        return isinstance(result, dict) and result.get('queued') is True

    def dispatch(self, message):
        self._serial()
        if not isinstance(message, dict):
            raise ValueError('Object command required')
        operation = message.get('operation')
        if operation == 'capabilities':
            from bobbi_core import CORE_VERSION, CORE_CAPABILITIES
            return dict(version=CORE_VERSION, capabilities=list(CORE_CAPABILITIES))
        if operation == 'resource_snapshot':
            if set(message) != {'operation'}:
                raise ValueError('Read-only resource snapshot takes no arguments')
            response = self.native.state()
            if (not isinstance(response, dict) or type(response.get('protocol')) is not int
                    or response['protocol'] != 1 or 'playback' not in response):
                raise RuntimeError('Native resource observation unavailable')
            raw = response['playback']
            checked = receipt(raw) if raw is not None else None
            if raw is not None and checked is None:
                raise ValueError('Native resource receipt invalid')
            # Do not call refresh(): observing retention must never reconcile
            # windows, pause/resume, claim playback or mutate playback authority.
            return dict(protocol=1, playback=checked)
        row = self.refresh()
        owner = self.owner
        if operation == 'snapshot':
            return owner.snapshot()
        args = (message.get('boot_id'), message.get('epoch'), message.get('request_id'))
        if operation == 'startup_failure':
            # Read-only recovery receipt. Cancellation still revokes ALL control
            # rights; acknowledging an exact failed open does not restore them.
            desired, terminal, native = owner.desired, owner.terminal, self.last_native
            if (args != (owner.boot_id, owner.epoch, (desired or {}).get('request_id'))
                    or self.dismissed_startup_failure == args
                    or self.native_epoch != self.reservation_epoch
                    or not desired or not desired['start_claimed'] or not desired['file_bound']
                    or desired['file_identity'] != message.get('file_identity')
                    or not terminal or terminal['request_id'] != args[2]
                    or terminal['epoch'] != args[1] or terminal['reason'] != 'ERROR'
                    or terminal['av_started'] or terminal['file_identity'] != desired['file_identity']
                    or owner.observed is not None or not native
                    or native['phase'] != 'TERMINAL' or native['reason'] != 'ERROR'
                    or native['native_instance'] != terminal['native_instance']
                    or native['request_id'] != args[2] or native['url_sha256'] != self.bound_url
                    or (row is not None and row != native)):
                return {'failed': False}
            return dict(failed=True, receipt=dict(boot_id=args[0], epoch=args[1], request_id=args[2],
                file_identity=terminal['file_identity'], native_instance=terminal['native_instance']))
        if operation == 'font_preflight_guard':
            if set(message) != {'operation', 'boot_id', 'epoch', 'request_id', 'file_identity'}:
                raise ValueError('Exact font preflight ownership required')
            desired = owner.desired
            allowed = bool(owner._current(*args)
                and self.native_epoch == self.reservation_epoch
                and desired and desired['file_bound'] and desired['start_claimed']
                and desired['file_identity'] == message['file_identity']
                and (self.native_idle or (row and row['phase'] == 'TERMINAL'))
                and owner.observed is None)
            return {'allowed': allowed}
        if operation == 'select':
            old = owner.snapshot()
            result = owner.select(*args, message.get('selection_identity'))
            if owner.epoch != old['epoch']:
                reserved = self.native.intent({'expected_epoch': self.native_epoch, 'request_id': args[2]})
                if not isinstance(reserved, dict) or reserved.get('reserved') is not True:
                    owner.cancel(owner.boot_id, owner.epoch, args[2])
                    raise RuntimeError('Native selection changed; stale intent rejected')
                self.reservation_epoch = reserved['selection_epoch']
                self.selection_gui_intent = self.gui_state['gui_user_intent']
                self.continuation = None
                self.reserved_continuation = False
                self.subtitle_pending = None
                self.start_receipt = None
                self.start_receipt_consumed = False
                self.loading_close = None
                self.fullscreen_attempt = None
                self.bound_url, self.pending_stop = None, None
                self.previous_instance = row['native_instance'] if row and row['phase'] != 'TERMINAL' else None
                if row and row['phase'] != 'TERMINAL' and owner.observed is None:
                    owner.observe_external(row['native_instance'], row['file_identity'] or row['url_sha256'])
            return result
        if operation == 'bind_file':
            url_hash = message.get('url_sha256')
            if not isinstance(url_hash, str) or not SHA.fullmatch(url_hash):
                raise ValueError('Actual resolved transport digest required, not media hash')
            if self.bound_url is not None and self.bound_url != url_hash:
                return {'bound': False}
            accepted = owner.bind_file(*args, message.get('selection_identity'), message.get('file_identity'),
                                      message.get('file_evidence', 'AUTO_VERIFIED_FILE'))
            if accepted:
                self.bound_url = url_hash
            return {'bound': accepted}
        if operation == 'torrent_subtitle_context':
            from bobbi_core.torrent_subtitles import checked_context
            if (not owner._current(*args) or self.native_epoch != self.reservation_epoch
                    or not owner.desired['file_bound'] or not owner.desired['start_claimed']):
                return {'registered': False}
            metadata = checked_context(message.get('torrent'), owner.desired['file_identity'])
            setter = getattr(self.native, 'set_torrent_context', None)
            if setter is None:
                return {'registered': False}
            setter(args[2], owner.desired['file_identity'], metadata)
            return {'registered': True}
        if operation in ('claim_start', 'claim_status'):
            if not owner._current(*args) or self.native_epoch != self.reservation_epoch:
                return {'status': 'STALE'}
            claim_id = message.get('claim_id')
            if claim_id is not None and (not isinstance(claim_id, str)
                    or not re.fullmatch('[0-9a-f]{32}', claim_id)):
                raise ValueError('Exact claim command identity required')
            if operation == 'claim_status' and claim_id is None:
                raise ValueError('Receipt query requires its command identity')
            if (self.reserved_continuation
                    and self.gui_state.get('gui_user_intent') != self.selection_gui_intent):
                owner.cancel(*args)
                return {'status': 'STALE'}
            if owner.desired['resolver_failure']:
                return {'status': 'STALE'}
            if self.start_receipt is not None:
                expected = dict(boot_id=args[0], epoch=args[1], request_id=args[2],
                    claim_id=claim_id, route=message.get('route'),
                    file_identity=owner.desired['file_identity'], url_sha256=self.bound_url)
                if expected != self.start_receipt:
                    return {'status': 'ALREADY_CLAIMED'}
                if (self.start_receipt_consumed or owner.desired['observed_once'] or owner.observed is not None
                        or (row and row['phase'] != 'TERMINAL')):
                    return {'status': 'CONSUMED'}
                return {'status': 'CLAIMED', 'receipt': deepcopy(self.start_receipt)}
            if operation == 'claim_status':
                return {'status': 'ALREADY_CLAIMED' if owner.desired['start_claimed'] else 'NOT_RECEIVED'}
            target = owner.stop_barrier_target(*args)
            if target:
                if target['native_instance'] != self.previous_instance:
                    return {'status': 'OTHER_PLAYBACK'}
                if not row or row['native_instance'] != target['native_instance']:
                    return {'status': 'WAIT_TERMINAL'}
                stop_key = (row['native_instance'], row['sequence'], row['user_intent'])
                if self.pending_stop != stop_key:
                    if not self._control(row, 'stop'):
                        return {'status': 'CONTROL_UNAVAILABLE'}
                    self.pending_stop = stop_key
                return {'status': 'WAIT_TERMINAL'}
            # A newer external open must not be silently stopped or displaced.
            if row and row['phase'] != 'TERMINAL':
                return {'status': 'OTHER_PLAYBACK'}
            if not owner.desired['file_bound']:
                return {'status': 'UNBOUND_FILE'}
            if not owner.claim_start(*args, message.get('route')):
                return {'status': 'ALREADY_CLAIMED'}
            if claim_id is None:
                return {'status': 'CLAIMED'}  # Isolated legacy caller, no replay rights.
            self.start_receipt = dict(boot_id=args[0], epoch=args[1], request_id=args[2],
                claim_id=claim_id, route=message.get('route'),
                file_identity=owner.desired['file_identity'], url_sha256=self.bound_url)
            return {'status': 'CLAIMED', 'receipt': deepcopy(self.start_receipt)}
        if operation == 'resolver_failed':
            return {'recorded': owner.resolver_failed(*args, message.get('category'))}
        if operation == 'cancel':
            if args == (owner.boot_id, owner.epoch, (owner.desired or {}).get('request_id')):
                self.dismissed_startup_failure = args
            observed = deepcopy(owner.observed)
            accepted = owner.cancel(*args)
            if accepted:
                if self.fullscreen_attempt and self.fullscreen_attempt['args'] == args and not owner.desired['fullscreen_confirmed']:
                    self._handoff_note(args[2], 'FAIL', 'NATIVE_FULLSCREEN_UNCONFIRMED',
                                       2 if self.fullscreen_attempt['retried'] else 1)
                cancelled_native = False
                if self.native_epoch == self.reservation_epoch:
                    reserved = self.native.intent({'expected_epoch': self.native_epoch, 'request_id': ''})
                    cancelled_native = (isinstance(reserved, dict) and reserved.get('reserved') is True
                                        and type(reserved.get('selection_epoch')) is int)
                    if cancelled_native:
                        self.native_epoch = reserved['selection_epoch']
                if cancelled_native and row and row['request_id'] == args[2] and row['phase'] != 'TERMINAL':
                    self._control(row, 'stop')
            return {'cancelled': accepted}
        if operation == 'register_window':
            return {'registered': owner.register_window(*args, message.get('token'), message.get('role'))}
        if operation == 'begin_window_close':
            token = message.get('token')
            registered = owner.windows.get(token) if isinstance(token, str) else None
            window = self._loading_window(message.get('dialog_id'), token)
            if (self.fullscreen_attempt is not None or not owner._current(*args)
                    or not registered or registered['role'] != 'loading'
                    or not row or row['phase'] != 'AV_STARTED'
                    or not owner.owns_instance(*args, row['native_instance'])
                    or not window or not window['visible'] or not window['matching']
                    or type(self.gui_state['gui_generation']) is not int
                    or self.gui_state['gui_user_intent'] != self.selection_gui_intent):
                return {'tracked': False}
            self.loading_close = dict(args=args, token=token, dialog_id=message['dialog_id'],
                instance=row['native_instance'], native_intent=row['user_intent'],
                generation=self.gui_state['gui_generation'], active_window=window['active_window'],
                released=False, hidden=False)
            self._handoff_note(args[2], 'WINDOW_CLOSE', 'OWNED_LOADING_VISIBLE', 0)
            return {'tracked': True}
        if operation == 'close_window':
            closed = owner.close_window(*args, message.get('token'))
            pending = self.loading_close
            if closed and pending and pending['args'] == args and pending['token'] == message.get('token'):
                pending['released'] = True
                window = self._loading_window(pending['dialog_id'], pending['token'])
                pending['hidden'] = bool(window and not window['visible']
                    and window['active_window'] == pending['active_window'])
            return {'closed': closed}
        instance = message.get('native_instance')
        if operation == 'auto_chinese_subtitle':
            result = self._auto_chinese_subtitle(args, instance, row, message.get('subtitle_context'))
            self._publish_subtitle_status(args, instance, result,
                                          message.get('subtitle_final_attempt') is True)
            return result
        if operation in ('authorize_next', 'manual_next'):
            identity = message.get('selection_identity')
            if not isinstance(identity, str) or not identity or len(identity) > 1024:
                raise ValueError('Exact next-release identity required')
            if (self.continuation or not owner._current(*args)
                    or owner.desired['file_evidence'] == 'USER_CONFIRMED_FILE'):
                return {'authorized': False}
            if operation == 'authorize_next':
                row = self._continuation_receipt(row)
                if row is None or row['native_instance'] != instance:
                    return {'authorized': False}
                accepted = owner.consume_next(*args, instance)
            else:
                accepted = bool(row and row['phase'] == 'AV_STARTED'
                    and row['native_instance'] == instance and owner.owns_instance(*args, instance))
                if accepted:
                    accepted = self._control(row, 'stop')
            if not accepted:
                return {'authorized': False}
            self.continuation = dict(token=uuid4().hex, request_id=args[2],
                native_instance=instance, selection_identity=identity,
                native_user_intent=row['user_intent'] if row else None,
                gui_user_intent=self.gui_state.get('gui_user_intent'),
                kind='natural' if operation == 'authorize_next' else 'manual')
            return {'authorized': True, 'token': self.continuation['token']}
        if operation == 'reserve_child':
            row = self._continuation_receipt(row)
            grant, terminal = self.continuation, owner.terminal
            allowed_reasons = {'NATURAL_EOF'} if grant and grant['kind'] == 'natural' else {'STOP', 'NATURAL_EOF'}
            if (not owner._current(*args) or not grant or not terminal
                    or grant['request_id'] != args[2] or grant['token'] != message.get('token')
                    or grant['selection_identity'] != message.get('selection_identity')
                    or terminal['native_instance'] != grant['native_instance']
                    or not row or row['native_instance'] != grant['native_instance']
                    or row['user_intent'] != grant['native_user_intent']
                    or self.gui_state.get('gui_user_intent') != grant['gui_user_intent']
                    or terminal['reason'] not in allowed_reasons or owner.observed is not None):
                raise RuntimeError('Continuation has no matching terminal and one-use grant')
            result = self.dispatch(dict(operation='select', boot_id=args[0], epoch=args[1],
                request_id=message.get('child_request_id'), selection_identity=grant['selection_identity']))
            self.reserved_continuation = True
            return result
        if operation == 'consume_next':
            return {'consumed': owner.consume_next(*args, instance)}
        if operation == 'return_to_menu':
            return {'accepted': owner.user_action(*args, instance, operation)}
        if operation == 'claim_fullscreen':
            return {'claimed': owner.claim_fullscreen(*args, instance)}
        if operation == 'request_fullscreen':
            gui = self.gui_state
            if (not row or row['phase'] != 'AV_STARTED' or row['native_instance'] != instance
                    or type(gui['gui_generation']) is not int or type(self.selection_gui_intent) is not int
                    or gui['gui_user_intent'] != self.selection_gui_intent
                    or not owner.claim_fullscreen(*args, instance)):
                return {'queued': False}
            command = dict(native_instance=instance, request_id=args[2],
                           selection_epoch=self.reservation_epoch,
                           gui_generation=gui['gui_generation'], gui_user_intent=self.selection_gui_intent)
            self.fullscreen_attempt = dict(args=args, instance=instance, generation=gui['gui_generation'],
                gui_intent=self.selection_gui_intent, native_intent=row['user_intent'],
                owner_intent=owner.user_intent, started=monotonic(), retried=False)
            self._handoff_note(args[2], 'REQUEST', 'CONDITIONAL_NATIVE_COMMAND', 1)
            result = self.native.fullscreen(command)
            return {'queued': isinstance(result, dict) and result.get('queued') is True}
        if operation == 'confirm_fullscreen':
            # A caller-controlled visibility bool is not a native GUI receipt.
            actual = self.gui_state.get('fullscreen_instance') == instance
            was_confirmed = bool(owner.desired and owner.desired['fullscreen_confirmed'])
            confirmed = owner.confirm_fullscreen(*args, instance, actual)
            if confirmed and not was_confirmed:
                self._handoff_note(args[2], 'CONFIRM', 'NATIVE_INSTANCE_RECEIPT',
                    2 if self.fullscreen_attempt and self.fullscreen_attempt['retried'] else 1)
            elif not confirmed:
                self._retry_retired_loading_fullscreen(args, instance, row)
            return {'confirmed': confirmed}
        if operation in ('acquire_pause', 'release_pause'):
            if not row or row['native_instance'] != instance:
                return {'queued': False}
            if operation == 'acquire_pause':
                action = owner.acquire_pause(*args, instance, message.get('token'), row['paused'])
            else:
                action = owner.release_pause(*args, instance, message.get('token'))
            return {'queued': bool(action and self._control(row, action['action'], message.get('token')))}
        raise ValueError('Unknown playback-owner operation')

    def _publish_subtitle_status(self, args, instance, result, final_attempt=False):
        """Presentation has the same serialized owner as native subtitle work."""
        publish = getattr(self.native, 'publish_subtitle_status', None)
        if publish is None or result.get('status') == 'STALE':
            return
        try:
            current = self.refresh(strict_protocol=True)
            event = self.history.items.get(instance)
            previous = self.subtitle_status_receipt
            if previous and previous['native_instance'] != instance:
                previous = None
            if (current and current['phase'] == 'AV_STARTED'
                    and current['native_instance'] == instance
                    and current['request_id'] == args[2]
                    and event and event['sequence'] == current['sequence']
                    and subtitle_snapshot_follows(current, event)
                    and subtitle_snapshot_follows(current, previous)
                    and self.native_epoch == self.reservation_epoch
                    and self.owner.owns_instance(*args, instance)):
                # A display watermark is not an accepted playback event. Keep
                # manual intent even if later native reads repeat an older row.
                self.subtitle_status_receipt = deepcopy(current)
                publish(current, result.get('status'), final_attempt)
        except (OSError, ValueError, RuntimeError):
            # Unknown native/presentation state is not a stop, a new owner, or
            # permission to replace manual intent. It cannot fail playback.
            return

    def _auto_chinese_subtitle(self, args, instance, row, context=None):
        from bobbi_core.subtitle_language import chinese_track

        if (not row or row['phase'] != 'AV_STARTED' or row['native_instance'] != instance
                or not self.owner.owns_instance(*args, instance)):
            return {'status': 'STALE'}
        catalog = self.native.subtitles()
        if not isinstance(catalog, dict) or catalog.get('status') != 'READY':
            return {'status': 'CATALOG_UNAVAILABLE'}
        captured = receipt(catalog.get('receipt'))
        if (not captured or captured['native_instance'] != instance
                or captured['request_id'] != args[2] or captured['phase'] != 'AV_STARTED'
                or catalog.get('selection_epoch') != self.reservation_epoch):
            return {'status': 'STALE'}
        for key in ('subtitle_intent', 'subtitle_auto_intent'):
            if type(captured.get(key)) is not int or captured[key] < 0:
                return {'status': 'INTENT_PROTOCOL_UNAVAILABLE'}
        if captured['subtitle_intent'] != captured['subtitle_auto_intent']:
            return {'status': 'MANUAL_PRESERVED'}
        completed_key = (instance, args[2], captured['subtitle_intent'], self.reservation_epoch)
        if self.subtitle_completed and self.subtitle_completed[0] == completed_key:
            return dict(self.subtitle_completed[1])
        context_setter = getattr(self.native, 'set_subtitle_context', None)
        if context_setter is not None and context is not None:
            context_setter(captured, context)
        if captured.get('subtitle_file_applied') is True:
            current = self.refresh()
            if (not current or current['native_instance'] != instance
                    or current.get('subtitle_intent') != captured['subtitle_intent']
                    or not self.owner.owns_instance(*args, instance)
                    or not isinstance(captured.get('subtitle_file_sha256'), str)
                    or not SHA.fullmatch(captured['subtitle_file_sha256'])):
                return {'status': 'STALE'}
            candidate = (self.subtitle_pending and self.subtitle_pending.get('candidate') is True
                         and self.subtitle_pending['claim'][:2] == (instance, captured.get('subtitle_file_sha256')))
            result = {'status': ('CANDIDATE_LOADED' if candidate else 'CONFIRMED') if catalog.get('visible') is True else 'CONTROL_NOT_CONFIRMED',
                      'subtitle_sha256': captured.get('subtitle_file_sha256')}
            if catalog.get('visible') is True:
                self.subtitle_completed = (completed_key, result)
            return result
        streams = catalog.get('streams')
        if not isinstance(streams, list) or len(streams) > 256:
            return {'status': 'CATALOG_UNAVAILABLE'}
        track = chinese_track(streams)
        if track is None:
            return self._auto_external_subtitle(args, instance, captured)
        if not isinstance(track.get('stream_key'), str) or not SHA.fullmatch(track['stream_key']):
            return {'status': 'STREAM_IDENTITY_UNAVAILABLE'}
        # Re-read before admission; the native actor repeats this comparison at
        # execution and also verifies the actual stream fingerprint, not ordinal.
        current = self.refresh()
        if (not current or current['native_instance'] != instance
                or current.get('subtitle_intent') != captured['subtitle_intent']
                or not self.owner.owns_instance(*args, instance)):
            return {'status': 'STALE'}
        if catalog.get('current_index') == track['index'] and catalog.get('visible') is True:
            cancel_lookup = getattr(self.native, 'cancel_external_subtitle_lookup', None)
            if cancel_lookup is not None:
                cancel_lookup()
            self.subtitle_pending = None
            result = {'status': 'CONFIRMED', 'stream_key': track['stream_key']}
            self.subtitle_completed = (completed_key, result)
            return result
        claim = (instance, track['stream_key'], captured['subtitle_intent'], self.reservation_epoch)
        if (self.subtitle_pending and self.subtitle_pending['claim'][0] == instance
                and self.subtitle_pending['claim'][2:] == claim[2:]):
            return {'status': 'QUEUED' if monotonic() - self.subtitle_pending['submitted'] < 3.0
                    else 'CONTROL_NOT_CONFIRMED', 'stream_key': track['stream_key']}
        command = dict(native_instance=instance, request_id=args[2],
            selection_epoch=self.reservation_epoch, subtitle_intent=captured['subtitle_intent'],
            command_id=uuid4().hex, index=track['index'], stream_key=track['stream_key'])
        accepted = self.native.subtitle(command)
        if isinstance(accepted, dict) and accepted.get('queued') is True:
            self.subtitle_pending = dict(claim=claim, submitted=monotonic(), command_id=command['command_id'])
            cancel_lookup = getattr(self.native, 'cancel_external_subtitle_lookup', None)
            if cancel_lookup is not None:
                cancel_lookup()
        return {'status': 'QUEUED' if isinstance(accepted, dict) and accepted.get('queued') is True
                else 'CONTROL_UNAVAILABLE', 'stream_key': track['stream_key']}

    def _auto_external_subtitle(self, args, instance, captured):
        lookup = getattr(self.native, 'external_subtitle', None)
        if lookup is None:
            return {'status': 'NO_FULL_CHINESE_TRACK'}
        try:
            result = lookup(captured)
        except (OSError, ValueError, RuntimeError):
            return {'status': 'SUBTITLE_SERVICE_UNAVAILABLE'}
        if not isinstance(result, dict) or result.get('state') not in ('ready', 'candidate'):
            if isinstance(result, dict) and result.get('state') == 'pending':
                return {'status': 'SUBTITLE_PREPARING'}
            return _subtitle_failure(result.get('reason') if isinstance(result, dict) else None)
        if any(result.get(k) != captured[k] for k in ('native_instance', 'request_id', 'subtitle_intent')):
            return {'status': 'STALE'}
        file = result.get('file')
        import os
        from pathlib import Path
        from .runtime_paths import ProfilePath
        root = str(Path(ProfilePath('subtitle-browser'))) + os.sep
        if (not isinstance(file, dict) or set(file) != {'path', 'sha256', 'bytes'}
                or not isinstance(file['path'], str) or not file['path'].startswith(root)
                or not re.fullmatch(r'[0-9a-f]{32}\.(?:srt|ass|ssa|vtt)', file['path'][len(root):])
                or not isinstance(file['sha256'], str) or not SHA.fullmatch(file['sha256'])
                or type(file['bytes']) is not int or not 0 < file['bytes'] <= 8 * 1024 * 1024):
            return {'status': 'SUBTITLE_EXPORT_INVALID'}
        current = self.refresh()
        if (not current or current['phase'] != 'AV_STARTED' or current['native_instance'] != instance
                or current.get('subtitle_intent') != captured['subtitle_intent']
                or current.get('subtitle_auto_intent') != captured['subtitle_auto_intent']
                or not self.owner.owns_instance(*args, instance)):
            return {'status': 'STALE'}
        claim = (instance, file['sha256'], captured['subtitle_intent'], self.reservation_epoch)
        if (self.subtitle_pending and self.subtitle_pending['claim'][0] == instance
                and self.subtitle_pending['claim'][2:] == claim[2:]):
            return {'status': 'QUEUED' if monotonic() - self.subtitle_pending['submitted'] < 3.0
                    else 'CONTROL_NOT_CONFIRMED'}
        command = dict(file, native_instance=instance, request_id=args[2],
            selection_epoch=self.reservation_epoch, subtitle_intent=captured['subtitle_intent'],
            command_id=uuid4().hex)
        if result.get('account_scope') is not None:
            current_account = getattr(self.native, 'subtitle_candidate_current', None)
            if current_account is None or current_account(result) is not True:
                return {'status': 'STALE'}
        accepted = self.native.subtitle_file(command)
        if isinstance(accepted, dict) and accepted.get('queued') is True:
            self.subtitle_pending = dict(claim=claim, submitted=monotonic(), command_id=command['command_id'],
                                         candidate=result.get('state') == 'candidate')
            return {'status': 'QUEUED'}
        return {'status': 'CONTROL_UNAVAILABLE'}
