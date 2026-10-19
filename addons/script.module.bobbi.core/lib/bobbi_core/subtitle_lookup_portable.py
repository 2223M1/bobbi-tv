"""One bounded host lookup off the native actor, with exact intent ownership."""
from copy import deepcopy
import json
from threading import Thread
import time


class SubtitleLookup:
    def __init__(self, call=None, clock=time.monotonic):
        if call is None:
            from .preparation_client import call
        self.call, self.clock = call, clock
        self.key = self.result = self.pending = self.active = None
        self.worker = None
        self.completed = 0
        self.stopped = False

    def request(self, receipt):
        if self.stopped:
            return {'state': 'unavailable', 'reason': 'SUBTITLE_LOOKUP_STOPPED'}
        fields = ('native_instance', 'request_id', 'file_identity', 'url_sha256',
                  'subtitle_intent', 'subtitle_auto_intent')
        key = json.dumps({field: receipt.get(field) for field in fields}, sort_keys=True)
        if len(json.dumps(receipt).encode('utf-8')) > 14000:
            raise ValueError('Subtitle lookup byte budget')
        self.tick()
        if self.key == key and self.result is not None:
            if self.clock() - self.completed < 30:
                result, self.result, self.key = self.result, None, None
                return deepcopy(result)
        elif self.key == key:
            return {'state': 'pending'}
        # Keep only the latest intent. A still-running previous request may
        # finish, but cannot apply/publish its result into this key.
        self.key, self.result = key, None
        self.pending = dict(key=key, body=deepcopy(receipt), deadline=self.clock() + .65)
        self.tick()
        return {'state': 'pending'}

    def tick(self):
        if self.stopped:
            return
        if self.worker is not None:
            if self.worker.is_alive():
                return
            self.worker.join()
            completed, self.worker, self.active = self.active, None, None
            if completed['key'] == self.key:
                self.result = (completed['result'] if self.clock() <= completed['deadline'] else
                               {'state': 'unavailable', 'reason': 'SUBTITLE_IPC_TIMEOUT'})
                self.completed = self.clock()
        if self.pending is None:
            return
        job, self.pending = self.pending, None
        if self.clock() >= job['deadline']:
            self.result = {'state': 'unavailable', 'reason': 'SUBTITLE_IPC_TIMEOUT'}
            self.completed = self.clock()
            return
        self.active = job
        def work():
            try:
                result = self.call('subtitle', job['body'], timeout=min(.3, job['deadline'] - self.clock()))
                if not isinstance(result, dict):
                    raise ValueError('Invalid subtitle response')
                job['result'] = result
            except Exception:
                job['result'] = {'state': 'unavailable', 'reason': 'SUBTITLE_IPC_UNAVAILABLE'}
        self.worker = Thread(target=work, name='bobbi-subtitle-lookup', daemon=True)
        self.worker.start()

    def close(self):
        self.stopped = True
        self.key = self.result = self.pending = None
        # Call is bounded to .3s. Do not block the serialized native actor or
        # use an unbounded executor queue on rapid track/film changes.
        if self.worker is not None:
            self.worker.join(timeout=.01)
