"""Pure state of the single service-side playback owner, never a global UI bool.

The service adapter must validate native open-instance/file evidence and execute
returned actions conditionally for that instance. JSON-RPC playerid/OnPlay alone
must never call observe_started(). This module does no Kodi or network IO.
"""
from copy import deepcopy
import re
from uuid import uuid4


class StaleIntent(ValueError):
    pass


class PlaybackOwner:
    TERMINALS = {'NATURAL_EOF', 'STOP', 'ERROR', 'CANCEL', 'SUPERSEDED'}

    def __init__(self, boot_id=None):
        self.boot_id = boot_id or uuid4().hex
        self.epoch = 0
        self.desired = None
        self.observed = None
        self.windows = {}
        self.pause = None
        self.user_intent = 0
        self.terminal = None

    def snapshot(self):
        return deepcopy({'boot_id': self.boot_id, 'epoch': self.epoch, 'desired': self.desired,
                         'observed': self.observed, 'terminal': self.terminal})

    def _current(self, boot_id, epoch, request_id):
        return (boot_id == self.boot_id and epoch == self.epoch and self.desired is not None
                and self.desired['request_id'] == request_id and not self.desired['cancelled'])

    def select(self, boot_id, expected_epoch, request_id, file_identity, retry_from=None):
        if (not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id)
                or not isinstance(file_identity, str) or not file_identity or len(file_identity) > 1024):
            raise ValueError('Bounded request and exact source identity required')
        if boot_id != self.boot_id:
            raise StaleIntent('Service restarted; old UI intent has no authority')
        if retry_from is not None:
            # Automatic same-file selection is not a fresh human choice. The
            # caller's last snapshot can precede an already queued Stop, which
            # does not increment owner.epoch. Check the original closed request
            # inside this admission, before mutating either owner or native.
            if (not isinstance(retry_from, dict)
                    or set(retry_from) != {'request_id', 'selection_identity', 'category'}
                    or not isinstance(retry_from['request_id'], str)
                    or not re.fullmatch('[0-9a-f]{32}', retry_from['request_id'])
                    or not isinstance(retry_from['selection_identity'], str)
                    or not re.fullmatch('bt:[0-9a-f]{40}', retry_from['selection_identity'])
                    or not isinstance(retry_from['category'], str)
                    or retry_from['category'] not in {'prepared_ready', 'buffer_timeout', 'preload_error'}
                    or request_id == retry_from['request_id']
                    or not re.fullmatch('prepared:[0-9a-f]{64}', file_identity)):
                raise ValueError('Exact closed-request retry guard required')
            desired = self.desired
            if (expected_epoch != self.epoch or not desired
                    or desired['request_id'] != retry_from['request_id']
                    or desired['selection_identity'] != retry_from['selection_identity']
                    or desired['resolver_failure'] != dict(request_id=retry_from['request_id'],
                                                           category=retry_from['category'])
                    or desired['start_claimed'] or desired['observed_once'] or self.observed is not None
                    or (retry_from['category'] == 'prepared_ready' and desired['cancelled'])):
                raise StaleIntent('Closed request changed before automatic retry admission')
        if self.desired and self.desired['request_id'] == request_id:
            if self.desired['selection_identity'] != file_identity:
                raise ValueError('Request identity cannot change its selected file')
            return self.snapshot()
        if type(expected_epoch) is not int or expected_epoch != self.epoch:
            raise StaleIntent('Selection was issued before a newer user choice')
        self.epoch += 1
        self.user_intent += 1
        self.desired = {'request_id': request_id, 'epoch': self.epoch, 'file_identity': file_identity,
                        'selection_identity': file_identity, 'file_bound': False,
                        'file_evidence': 'UNBOUND',
                        'cancelled': False, 'start_claimed': False, 'route': None,
                        'resolver_failure': None,
                        'observed_once': False, 'fullscreen_allowed': True,
                        'fullscreen_requested': False, 'fullscreen_confirmed': False}
        # Old observed video remains A until the adapter proves it terminated.
        # Selection of B invalidates A's pause/next/foreground rights, not facts.
        self.pause = None
        self.windows.clear()
        return self.snapshot()

    def bind_file(self, boot_id, epoch, request_id, selection_identity, file_identity,
                  file_evidence='AUTO_VERIFIED_FILE'):
        """Bind the resolver's exact file once, without changing selected release."""
        if (not self._current(boot_id, epoch, request_id)
                or self.desired['selection_identity'] != selection_identity
                or self.desired['resolver_failure']
                or self.desired['observed_once']):
            return False
        if not isinstance(file_identity, str) or not file_identity or len(file_identity) > 1024:
            raise ValueError('Exact bounded file identity required')
        if file_evidence not in ('AUTO_VERIFIED_FILE', 'USER_CONFIRMED_FILE'):
            raise ValueError('Explicit file evidence required')
        if self.desired['file_bound']:
            return (self.desired['file_identity'] == file_identity
                    and self.desired['file_evidence'] == file_evidence)
        self.desired['file_identity'] = file_identity
        self.desired['file_evidence'] = file_evidence
        self.desired['file_bound'] = True
        return True

    def observe_external(self, native_instance, file_identity):
        """Record an actually observed unowned player; never grant next/UI rights."""
        if self.observed is not None or not native_instance or not file_identity:
            return False
        self.observed = {'request_id': '', 'epoch': -1, 'native_instance': native_instance,
                         'file_identity': file_identity, 'paused': False, 'error': False,
                         'av_started': False}
        return True

    def stop_barrier_target(self, boot_id, epoch, request_id):
        if not self._current(boot_id, epoch, request_id):
            return None
        if self.observed and self.observed['request_id'] != request_id:
            return deepcopy(self.observed)
        return None

    def claim_start(self, boot_id, epoch, request_id, route):
        if route not in ('resolved_url', 'player_play'):
            raise ValueError('One explicit playback entry required')
        if (not self._current(boot_id, epoch, request_id) or self.desired['start_claimed']
                or self.desired['resolver_failure']):
            return False
        if self.observed is not None:
            return False  # The adapter must complete the old-instance stop barrier.
        self.desired['start_claimed'], self.desired['route'] = True, route
        return True

    def observe_open(self, boot_id, epoch, request_id, native_instance, file_identity):
        if (not self._current(boot_id, epoch, request_id) or not self.desired['start_claimed']
                or self.desired['resolver_failure']
                or self.desired['file_identity'] != file_identity):
            return False
        if not isinstance(native_instance, str) or not native_instance or len(native_instance) > 128:
            return False
        if self.observed:
            if self.observed['native_instance'] != native_instance:
                return False
            if self.observed['request_id'] == request_id:
                return True
            if self.observed['request_id']:
                return False
        if self.desired['observed_once'] or (self.terminal and self.terminal['native_instance'] == native_instance):
            return False
        self.observed = {'request_id': request_id, 'epoch': epoch, 'native_instance': native_instance,
                         'file_identity': file_identity, 'paused': False, 'error': False,
                         'av_started': False}
        self.terminal = None
        return True

    def observe_started(self, boot_id, epoch, request_id, native_instance, file_identity):
        if not self.observe_open(boot_id, epoch, request_id, native_instance, file_identity):
            return False
        self.desired['observed_once'] = True
        self.observed['av_started'] = True
        return True

    def owns_instance(self, boot_id, epoch, request_id, native_instance):
        return (self._current(boot_id, epoch, request_id) and self.observed is not None
                and self.observed['request_id'] == request_id and self.observed['epoch'] == epoch
                and self.observed['native_instance'] == native_instance)

    def resolver_failed(self, boot_id, epoch, request_id, category):
        """Pre-AV resolver outcome, never a fabricated native terminal/EOF."""
        allowed = {'playback_failed', 'no_candidate', 'metadata_timeout', 'buffer_timeout',
                   'cancelled', 'aborted', 'torrserver_error', 'preload_error',
                   'selected_file_missing', 'invalid_request', 'invalid_binding',
                   'target_unresolved', 'superseded', 'source_identity_mismatch',
                   'torrent_download_failed', 'torrent_download_timeout', 'prepared_ready'}
        if not isinstance(category, str) or category not in allowed:
            raise ValueError('Known bounded resolver failure required')
        if (not self._current(boot_id, epoch, request_id) or self.desired['resolver_failure']
                or self.desired['observed_once']
                or (category == 'prepared_ready' and (self.desired['start_claimed'] or self.observed is not None))
                or (self.observed and self.observed['request_id'] == request_id)):
            return False
        self.desired['resolver_failure'] = dict(request_id=request_id, category=category)
        self.desired['fullscreen_allowed'] = False
        return True

    def cancel(self, boot_id, epoch, request_id):
        if not self._current(boot_id, epoch, request_id):
            return False
        self.desired['cancelled'] = True
        self.desired['fullscreen_allowed'] = False
        self.user_intent += 1
        self.pause = None
        self.windows.clear()
        return True

    def user_action(self, boot_id, epoch, request_id, native_instance, action):
        if action not in ('pause', 'resume', 'stop', 'return_to_menu'):
            raise ValueError('Explicit user action required')
        if not self.owns_instance(boot_id, epoch, request_id, native_instance):
            return False
        self.user_intent += 1
        self.pause = None
        if action in ('pause', 'resume'):
            self.observed['paused'] = action == 'pause'
        if action in ('stop', 'return_to_menu'):
            self.desired['fullscreen_allowed'] = False
        if action == 'stop':
            self.desired['cancelled'] = True
        return True

    def register_window(self, boot_id, epoch, request_id, token, role):
        if not self._current(boot_id, epoch, request_id):
            return False
        if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('Unique window instance token required')
        if role not in ('source', 'loading', 'subtitles', 'audio'):
            raise ValueError('Known window role required')
        row = {'request_id': request_id, 'epoch': epoch, 'role': role}
        if token in self.windows:
            return self.windows[token] == row
        if len(self.windows) >= 16:
            raise ValueError('Window lease budget exceeded')
        self.windows[token] = row
        return True

    def close_window(self, boot_id, epoch, request_id, token):
        if not self._current(boot_id, epoch, request_id) or token not in self.windows:
            return False
        # Caller must release an OSD pause lease separately before closing.
        self.windows.pop(token)
        return True

    def acquire_pause(self, boot_id, epoch, request_id, native_instance, token, actually_paused):
        if (not self.owns_instance(boot_id, epoch, request_id, native_instance)
                or token not in self.windows or self.windows[token]['role'] not in ('subtitles', 'audio')
                or type(actually_paused) is not bool):
            return None
        if self.pause is not None:
            self.pause['windows'].add(token)
            return None
        if actually_paused:
            return None  # A user's existing pause never creates auto-resume rights.
        self.pause = {'native_instance': native_instance, 'request_id': request_id,
                      'user_intent': self.user_intent, 'windows': {token}, 'confirmed': False}
        return {'action': 'pause', 'native_instance': native_instance}

    def confirm_owned_pause(self, native_instance, actually_paused):
        if self.pause and self.pause['native_instance'] == native_instance and actually_paused is True:
            self.pause['confirmed'] = True
            return True
        return False

    def release_pause(self, boot_id, epoch, request_id, native_instance, token):
        if (not self.owns_instance(boot_id, epoch, request_id, native_instance) or not self.pause
                or token not in self.pause['windows']):
            return None
        self.pause['windows'].remove(token)
        if self.pause['windows']:
            return None
        lease, self.pause = self.pause, None
        if lease['confirmed'] and lease['user_intent'] == self.user_intent:
            return {'action': 'resume', 'native_instance': native_instance}
        return None

    def claim_fullscreen(self, boot_id, epoch, request_id, native_instance):
        if (not self.owns_instance(boot_id, epoch, request_id, native_instance)
                or not self.observed['av_started']
                or not self.desired['fullscreen_allowed'] or self.desired['fullscreen_requested']
                or any(row['role'] in ('source', 'loading') for row in self.windows.values())):
            return False
        self.desired['fullscreen_requested'] = True
        return True

    def confirm_fullscreen(self, boot_id, epoch, request_id, native_instance, actually_fullscreen):
        if (actually_fullscreen is not True or not self.owns_instance(boot_id, epoch, request_id, native_instance)
                or not self.desired['fullscreen_requested'] or not self.desired['fullscreen_allowed']
                or any(row['role'] in ('source', 'loading') for row in self.windows.values())):
            return False
        self.desired['fullscreen_confirmed'] = True
        return True

    def record_error(self, native_instance):
        if self.observed and self.observed['native_instance'] == native_instance:
            self.observed['error'] = True
            return True
        return False

    def observe_terminal(self, native_instance, reason):
        if reason not in self.TERMINALS:
            raise ValueError('Explicit terminal reason required')
        if not self.observed or self.observed['native_instance'] != native_instance:
            return False
        current = self.observed
        if current['error'] or (reason == 'NATURAL_EOF' and not current['av_started']):
            reason = 'ERROR'
        elif not self.desired or current['request_id'] != self.desired['request_id']:
            reason = 'SUPERSEDED'
        elif self.desired['cancelled']:
            reason = 'CANCEL'
        self.terminal = dict(current, reason=reason, consumed=False)
        self.observed = None
        self.pause = None
        return True

    def consume_next(self, boot_id, epoch, request_id, native_instance):
        if (not self._current(boot_id, epoch, request_id) or not self.terminal
                or self.desired['file_evidence'] == 'USER_CONFIRMED_FILE'
                or self.terminal['native_instance'] != native_instance
                or self.terminal['request_id'] != request_id or self.terminal['reason'] != 'NATURAL_EOF'
                or not self.terminal['av_started']
                or self.terminal['consumed']):
            return False
        self.terminal['consumed'] = True
        return True
