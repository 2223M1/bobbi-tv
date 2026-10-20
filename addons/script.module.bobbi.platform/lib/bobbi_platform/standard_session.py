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
                 open_next=lambda data: None, clock=time.monotonic):
        self.accounts, self.history = accounts, history
        self.next_loader, self.open_next, self.clock = next_loader, open_next, clock
        self.current = None
        self.generation = 0
        self.worker = self.job = None
        self.closed = False

    def current_request(self, request):
        row = self.current
        return bool(not self.closed and row and row['request_id'] == request
                    and not row['cancel'].is_set() and self.accounts.is_current(row['account']))

    def retire(self, reason='SUPERSEDED'):
        row = self.current
        if row:
            row['cancel'].set()
            row['next_data'] = None
            if row['state'] == 'playing':
                self._save(row, reason)
            row['state'] = 'retired'

    def select(self, request, account):
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
        row.update(state='playing', observed=self.clock())
        if type(position) in (int, float) and type(duration) in (int, float):
            if 0 <= position <= duration and 0 < duration < 864000:
                row.update(position=float(position), duration=float(duration),
                           progress_observed=self.clock())
        if first:
            self._save(row, 'STARTED')
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
            self.retire('STOP' if kind == 'STOPPED' else 'ERROR')
            self._save(row, 'STOP' if kind == 'STOPPED' else 'ERROR')
            return False
        if row['state'] != 'playing':
            return False
        # Standard Ended can also mean an early read failure. A recent observed
        # end position is required; a percent threshold alone is not EOF.
        natural = (kind == 'ENDED' and row['duration'] > 0
            and row['duration'] - row['position'] <= 3
            and row['progress_observed'] is not None
            and 0 <= self.clock() - row['progress_observed'] <= 3)
        reason = 'NATURAL_EOF' if natural else ('STOP' if kind == 'STOPPED' else 'ERROR')
        row.update(state='ended' if natural else 'retired', terminal=self.clock())
        self._save(row, reason)
        if not natural:
            row['cancel'].set()
        return natural

    def _save(self, row, reason):
        data = deepcopy(row['data'])
        data.update(current_time=row['position'], total_time=row['duration'],
            progress=(100 * row['position'] / row['duration'] if row['duration'] else 0),
            terminal_reason=reason, completed=reason == 'NATURAL_EOF',
            lifecycle_evidence='standard-kodi-observation')
        try:
            self.history(data)
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
        if (self.next_loader and self.worker is None and not row['next_data']
                and (near_end or final_scan)):
            row['attempts'] = row.get('attempts', 0) + 1
            if final_scan:
                row['final_scan'] = True
            job = dict(request_id=row['request_id'], owner=row,
                       data=deepcopy(row['data']), cancel=row['cancel'])
            self.job = job
            def cancelled():
                return (job['cancel'].is_set() or not self.accounts.is_current(row['account'])
                        or (row['terminal'] is not None and self.clock() - row['terminal'] >= 20))
            def work():
                try:
                    job['result'] = self.next_loader(job['data'], cancelled)
                except Exception:
                    job['result'] = None  # Availability never changes release policy.
            self.worker = Thread(target=work, name='bobbi-standard-next', daemon=True)
            self.worker.start()
        if row['state'] == 'ended' and not playing and self.clock() - row['terminal'] >= .25:
            if row['next_data']:
                data = row['next_data']
                row['next_data'] = None
                row['state'] = 'continued'  # Claim once before sending anything.
                self.open_next(data)

    def close(self):
        self.retire('SERVICE_STOPPED')
        self.closed = True
        if self.worker:
            self.worker.join(timeout=.1)
