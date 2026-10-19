"""Bounded pre-AV cache verification; ledger and activation stay on the owner."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import re
import time


class FontPreflightLane:
    def __init__(self, worker, clock=time.monotonic):
        self.worker, self.clock = worker, clock
        self.records = {}
        self.future = self.active = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cinema-font-preflight-io')

    def request(self, body):
        key = body.get('request_id') if isinstance(body, dict) else None
        if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key):
            raise ValueError('Exact font request identity required')
        now = self.clock()
        for old, record in list(self.records.items()):
            if old != self.active and record['expires'] <= now:
                self.records.pop(old)
        if key in self.records:
            record = self.records[key]
            if record['body'] != body:
                raise ValueError('Font request cannot be retargeted')
            if now >= record['expires']:
                return dict(state='unavailable', reason='FONT_PREFLIGHT_EXPIRED')
            return deepcopy(record['result'])
        if len(self.records) >= 8:
            return dict(state='unavailable', reason='FONT_PREFLIGHT_CAPACITY')
        self.records[key] = dict(body=deepcopy(body), expires=now+3, phase='queued',
                                 result=dict(state='pending', request_id=key))
        return deepcopy(self.records[key]['result'])

    def tick(self):
        now = self.clock()
        if self.future is not None and self.future.done():
            record = self.records[self.active]
            try:
                result = self.future.result()
                reply = (self.worker.complete(record['plan'], result) if now < record['expires']
                         else dict(state='unavailable', reason='FONT_PREFLIGHT_EXPIRED'))
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                reply = dict(state='unavailable', reason='FONT_PREFLIGHT_REJECTED', error_type=type(error).__name__)
            record.update(phase='done', result=reply)
            self.future = self.active = None
        if self.future is not None:
            return
        for key, record in self.records.items():
            if record['phase'] != 'queued':
                continue
            if now >= record['expires']:
                record.update(phase='done', result=dict(state='unavailable', reason='FONT_PREFLIGHT_EXPIRED'))
                continue
            try:
                plan = self.worker.plan(record['body'])
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                plan = dict(state='unavailable', reason='FONT_PREFLIGHT_REJECTED', error_type=type(error).__name__)
            if plan['state'] != 'planned':
                record.update(phase='done', result=plan)
                continue
            record.update(phase='checking', plan=plan)
            self.active = key
            self.future = self.executor.submit(self.worker.perform, plan)
            break

    def close(self):
        # Never commit a result while shutting down, including a late IO success.
        self.executor.shutdown(wait=True)  # Python 3.8; at most one IO future.
        self.records.clear()
        self.future = self.active = None
