"""Standard Kodi lifecycle, not a native receipt or an atomic player API.

All mutations run on the resident thread. Workers return data, never player
commands. A ListItem request property AND the observed file associate AV start;
an unassociated event only retires this request. No global stop/fullscreen loop.
"""
from copy import deepcopy
import re
from threading import Event, Thread
import time

from .playback import check_media


class StandardSession:
    def __init__(self, accounts, history=lambda data: None, next_loader=None,
                 open_next=lambda data: None, clock=time.monotonic, *, paused=lambda: False,
                 observer=None):
        self.accounts, self.history = accounts, history
        self.next_loader, self.open_next, self.clock = next_loader, open_next, clock
        self.paused = paused
        self.observer = observer
        self.current = None
        self.generation = 0
        self.worker = self.job = None
        self.closed = False

    def _emit_observation(self, event, row, **extra):
        if self.observer is None or not row:
            return
        payload = dict(
            event=event,
            request_id=row['request_id'],
            generation=row['generation'],
            account=deepcopy(row['account']),
            position=row['position'],
            duration=row['duration'],
            paused=bool(row.get('last_paused', False)),
            data=deepcopy(row.get('data') or {}),
        )
        payload.update(extra)
        try:
            self.observer(payload)
        except Exception:
            pass

    def current_request(self, request):
        row = self.current
        return bool(not self.closed and row and row['request_id'] == request
                    and not row['cancel'].is_set() and self.accounts.is_current(row['account']))

    def next_summary(self):
        from bobbi_core.next_episode_summary import project, envelope
        row = self.current
        if not row or row['state'] != 'playing' or not self.current_request(row['request_id']):
            return None
        summary = project(row['data'] or {}, row['next_data'], preparing=bool(
            self.job and self.job['owner'] is row), failed=row.get('next_error', False))
        return envelope(summary, 'standard', dict(request_id=row['request_id'],
            generation=row['generation']), row['account'], row['generation'])

    def retire(self, reason='SUPERSEDED'):
        row = self.current
        if row:
            row['cancel'].set()
            row['next_data'] = None
            if row['state'] == 'playing':
                self._save(row, reason)
                self._emit_observation('TERMINAL', row, reason=reason)
            row['state'] = 'retired'

    def select(self, request, account):
        if self.closed:
            raise RuntimeError('STANDARD_SESSION_CLOSED')
        if not isinstance(request, str) or not re.fullmatch('[a-f0-9]{32}', request):
            raise ValueError('STANDARD_REQUEST_REQUIRED')
        self.accounts.require_current(account, authenticated=False)
        self.retire()
        self.generation += 1
        self.current = dict(request_id=request, account=deepcopy(account),
            generation=self.generation, state='selected', cancel=Event(), data=None,
            position=0., duration=0., observed=0., progress_observed=None,
            next_data=None, terminal=None)
        return dict(request_id=request, generation=self.generation)

    def register(self, request, data):
        check_media(data)
        if not self.current_request(request) or self.current['state'] != 'selected':
            return {'accepted': False}
        if data.get('request_id') != request or data.get('_account') != self.current['account']:
            raise ValueError('STANDARD_SELECTION_CHANGED')
        self.current.update(data=deepcopy(data), state='submitted')
        # Standard observations do not have native's atomic instance proof.
        self.current['data'].pop('_file_start_observation', None)
        return {'accepted': True}

    def dispatch(self, body):
        operation = body.get('operation')
        if operation == 'select':
            return self.select(body['request_id'], body['account'])
        if operation == 'register':
            return self.register(body['request_id'], body['data'])
        if operation == 'current':
            return {'current': self.current_request(body['request_id'])}
        if operation == 'cancel':
            if self.current_request(body['request_id']):
                self.retire('CANCELLED')
            return {'cancelled': True}
        if operation == 'snapshot':
            row = self.current
            data = row.get('data') or {} if row else {}
            return {'adapter': 'standard', 'desired': (dict(request_id=row['request_id'],
                cancelled=not self.current_request(row['request_id']),
                file_evidence=data.get('file_evidence', 'UNVERIFIED')) if row else None)}
        raise ValueError('STANDARD_OPERATION_UNKNOWN')

    def observe(self, request, url, position, duration):
        if not self.current_request(request):
            return False
        row = self.current
        data = row['data'] or {}
        # Kodi may remove transport options from getPlayingFile, not the path.
        if not url or url != str(data.get('url', '')).partition('|')[0]:
            return False
        if row['state'] not in ('submitted', 'playing'):
            return False
        first = row['state'] == 'submitted'
        now = self.clock()
        prev_pos = row['position']
        prev_obs = row['progress_observed']
        prev_paused = bool(row.get('last_paused', False))
        cur_paused = bool(self.paused())
        row.update(state='playing', observed=now, last_paused=cur_paused)
        observed = (type(position) in (int, float) and type(duration) in (int, float)
                    and 0 <= position <= duration and 0 < duration < 864000)
        if observed:
            row.update(position=float(position), duration=float(duration), progress_observed=now)
        if first:
            row['last_emit_at'] = now
            self._save(row, 'STARTED')
            self._emit_observation('AV_START', row, observed_clock=observed)
            if data.get('_pan_file') and data.get('_file_history') and data.get('selection_policy') == 'exact':
                from bobbi_core.playback_completion import FileProgressCheckpoint
                row['checkpoint'] = FileProgressCheckpoint()
        else:
            trigger = None
            if cur_paused != prev_paused:
                trigger = 'Pause' if cur_paused else 'Unpause'
            elif observed and prev_obs is not None:
                expected_advance = 0.0 if prev_paused else max(0.0, now - prev_obs)
                if abs(float(position) - (prev_pos + expected_advance)) >= 4.0:
                    trigger = 'TimeUpdate'
            if trigger is None and observed and (now - row.get('last_emit_at', 0.0)) >= 10.0:
                trigger = 'TimeUpdate'
            if trigger is not None:
                row['last_emit_at'] = now
                self._emit_observation('PROGRESS', row, trigger=trigger, observed_clock=observed)
        checkpoint = row.get('checkpoint')
        if checkpoint and observed and checkpoint.due(now, position, duration, paused=cur_paused) and not first:
            self._save(row, 'PROGRESS')
        return True

    def observe_other(self, request, url):
        """Only a successfully read, nonempty foreign item proves takeover.

        Missing observations during open/seek are not user intent. Pending new
        selections can also still see the old video while resolution finishes.
        """
        row = self.current
        if (not row or row['state'] not in ('playing', 'ended')
                or not self.current_request(row['request_id']) or not url):
            return False
        expected = str((row['data'] or {}).get('url', '')).partition('|')[0]
        if url != expected or (request and request != row['request_id']):
            self.retire('EXTERNAL_PLAYBACK')
            return True
        return False

    def terminal(self, request, kind, playing=False):
        if not self.current_request(request) or playing:
            return False
        row = self.current
        if row['state'] == 'ended' and kind in ('STOPPED', 'ERROR'):
            term_reason = 'STOP' if kind == 'STOPPED' else 'ERROR'
            self.retire(term_reason)
            self._save(row, term_reason)
            return False
        if row['state'] != 'playing':
            return False
        # Standard Ended can also mean an early read failure. A recent observed
        # end position is required; a percent threshold alone is not EOF.
        from bobbi_core.playback_completion import observed_end
        natural = (kind == 'ENDED' and observed_end(row['position'], row['duration'],
            row['progress_observed'], self.clock()))
        reason = 'NATURAL_EOF' if natural else ('STOP' if kind == 'STOPPED' else 'ERROR')
        row.update(state='ended' if natural else 'retired', terminal=self.clock())
        self._save(row, reason)
        self._emit_observation('TERMINAL', row, reason=reason)
        if not natural:
            row['cancel'].set()
        return natural

    def _save(self, row, reason):
        if row['data'].get('_pan_file'):
            row['data']['_file_history_sequence'] = row['data'].get('_file_history_sequence', 0) + 1
        data = deepcopy(row['data'])
        data.update(current_time=row['position'], total_time=row['duration'],
            progress=(100 * row['position'] / row['duration'] if row['duration'] else 0),
            terminal_reason=reason, completed=reason == 'NATURAL_EOF',
            lifecycle_evidence='standard-kodi-observation')
        try:
            if self.history(data) is False:
                row['history_error'] = True
        except Exception:
            # Persistence failure cannot kill the resident player observer.
            row['history_error'] = True

    def tick(self, playing=False):
        row = self.current
        if row and not self.accounts.is_current(row['account']):
            self.retire('ACCOUNT_CHANGED')
        if self.worker and not self.worker.is_alive():
            self.worker.join()
            job, self.worker, self.job = self.job, None, None
            if row is job['owner'] and self.current_request(row['request_id']):
                row['next_data'] = job.get('result')
                row['next_error'] = bool(job.get('failed'))
                if job.get('final'):
                    row['next_final_checked'] = True
                row['retry_at'] = self.clock() + (5, 15, 30, 30, 30)[min(row['attempts'] - 1, 4)]
        if not row or not self.current_request(row['request_id']):
            return
        # Expire independently of a ready candidate or unrelated active player.
        if row['state'] == 'ended' and self.clock() - row['terminal'] >= 20:
            self.retire('NEXT_DEADLINE')
            return
        near_end = (row['state'] == 'playing' and row['duration'] > 0
                    and row['duration'] - row['position'] <= 120
                    and row.get('attempts', 0) < 5 and self.clock() >= row.get('retry_at', 0))
        final_scan = row['state'] == 'ended' and not row.get('final_scan')
        provisional = bool(row['next_data'] and row['next_data'].get('_next_transport') == 'bt')
        needs_final = bool(row['next_data'] and row['next_data'].get('_next_recheck'))
        if (self.next_loader and self.worker is None and (not row['next_data'] or provisional or (final_scan and needs_final))
                and (near_end or final_scan)):
            row['attempts'] = row.get('attempts', 0) + 1
            if final_scan:
                row['final_scan'] = True
            job = dict(request_id=row['request_id'], owner=row,
                       data=deepcopy(row['data']), cancel=row['cancel'], final=final_scan)
            # Only this lifecycle can mint final-scan state. Never inherit
            # these internal fields from a ListItem or a previous handoff.
            job['data'].pop('_continuation_final', None)
            job['data'].pop('_continuation_direct_source', None)
            if final_scan:
                job['data']['_continuation_final'] = True
                candidate = row['next_data']
                if candidate and candidate.get('_catalog_next'):
                    job['data']['_continuation_direct_source'] = deepcopy(candidate['direct_source'])
            self.job = job
            def cancelled():
                return (job['cancel'].is_set() or not self.accounts.is_current(row['account'])
                        or (row['terminal'] is not None and self.clock() - row['terminal'] >= 20))
            def work():
                try:
                    job['result'] = self.next_loader(job['data'], cancelled)
                except Exception:
                    job['result'] = None  # Availability never changes release policy.
                    job['failed'] = True
            self.worker = Thread(target=work, name='bobbi-standard-next', daemon=True)
            self.worker.start()
        if row['state'] == 'ended' and not playing and self.clock() - row['terminal'] >= .25:
            if row['next_data'] and (not row['next_data'].get('_next_recheck') or row.get('next_final_checked')):
                data = row['next_data']
                row['next_data'] = None
                row['state'] = 'continued'  # Claim once before sending anything.
                self.open_next(data)

    def close(self):
        self.closed = True
        if self.job:
            self.job['cancel'].set()
        try:
            # Service retirement is neither a user STOP nor observed EOF.
            self.retire('SERVICE_CLOSED')
        finally:
            if self.worker:
                self.worker.join()
