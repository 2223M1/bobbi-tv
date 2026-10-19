"""Bounded read-only playback lane; all ledger work remains on the owner thread."""
from concurrent.futures import ThreadPoolExecutor
import time


class ResolveLane:
    def __init__(self, resolver, clock=time.monotonic):
        self.resolver, self.clock = resolver, clock
        self.records = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cinema-resolve-io')
        self.future = self.active = None

    def _drop(self, key):
        record = self.records.pop(key)
        self.resolver.finish(record['plan'], False)

    def _finish(self, plan, verified):
        try:
            return self.resolver.finish(plan, verified)
        except (ValueError, RuntimeError) as error:
            # An expired/rejected playback binding is this request's failure,
            # not permission to terminate the service and every cloud task.
            # Cleanup must itself succeed; DB/integrity errors still propagate.
            self.resolver.finish(plan, False)
            return dict(state='unavailable', reason='resolve_finish_rejected',
                        error_type=type(error).__name__)

    def request(self, body):
        # A new verification nonce is used for each consumption stage. Polls
        # reuse it; BaseWindow and actual player startup never share cached IO.
        now = self.clock()
        for key, record in list(self.records.items()):
            if record['expires'] <= now and key != self.active:
                self._drop(key)
        key = body.get('verification_id') if isinstance(body, dict) else None
        record = self.records.get(key)
        if record:
            if record['plan']['body'] != body:
                raise ValueError('Resolve verification cannot be retargeted')
            if record['expires'] <= now:
                return {'state': 'unavailable'}
            if record['state'] == 'done' and record['result'].get('state') == 'ready':
                # Suppression and generation changes must also invalidate a
                # short-lived completed response between client polls.
                record['result'] = self._finish(record['plan'], True)
            return record['result']
        if len(self.records) >= 32:
            raise ValueError('Resolve queue is full')
        plan = self.resolver.plan(body)
        result = {'state': 'pending', 'request_id': body['request_id'], 'verification_id': key}
        self.records[key] = dict(plan=plan, state='queued', expires=now + 3, result=result)
        return result

    def tick(self, allow_submit=True):
        now = self.clock()
        if self.future is not None and self.future.done():
            record = self.records[self.active]
            try:
                verified = self.future.result() is True and now < record['expires'] and allow_submit
            except Exception:
                verified = False
            record['result'] = self._finish(record['plan'], verified)
            record.update(state='done', expires=now + 2)
            self.future = self.active = None
        for key, record in list(self.records.items()):
            if record['expires'] <= now and key != self.active:
                self._drop(key)
        if self.future is None and allow_submit:
            key = next((key for key, record in self.records.items() if record['state'] == 'queued'), None)
            if key is not None:
                self.active = key
                self.records[key]['state'] = 'checking'
                self.future = self.executor.submit(self.resolver.perform, self.records[key]['plan'])

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
        for key in list(self.records):
            self._drop(key)
