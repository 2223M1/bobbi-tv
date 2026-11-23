"""One bounded host lookup off the native actor, with exact intent ownership."""
from copy import deepcopy
import json
from threading import Thread
import time


class SubtitleLookup:
    def __init__(self, call=None, clock=time.monotonic, *, capture=None):
        if call is not None and capture is not None:
            raise ValueError('One explicit subtitle transport binding required')
        self.capture = capture if capture is not None else lambda receipt: call
        self.clock = clock
        self.binding_key = self.binding = None
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
        if key != self.binding_key:
            # Capture on the caller/owner thread, never in the worker or on a
            # retry after consuming a result. None is a retained failed capture.
            self.binding_key, self.binding = key, dict(call=None)
            self.key = self.result = self.pending = None
            try:
                call = self.capture(deepcopy(receipt))
                if callable(call):
                    self.binding['call'] = call
            except Exception:
                pass  # Optional prepared subtitles cannot stop ordinary video.
        if self.binding['call'] is None:
            return {'state': 'unavailable', 'reason': 'SUBTITLE_BINDING_UNAVAILABLE'}
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
        self.pending = dict(key=key, binding=self.binding, call=self.binding['call'],
                            body=deepcopy(receipt), deadline=self.clock() + .65)
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
            if (completed['key'] == self.key and completed['binding'] is self.binding
                    and self.binding['call'] is not None):
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
                result = job['call']('subtitle', job['body'], timeout=min(.3, job['deadline'] - self.clock()))
                if not isinstance(result, dict):
                    raise ValueError('Invalid subtitle response')
                job['result'] = result
            except Exception:
                job['result'] = {'state': 'unavailable', 'reason': 'SUBTITLE_IPC_UNAVAILABLE'}
        self.worker = Thread(target=work, name='bobbi-subtitle-lookup', daemon=True)
        self.worker.start()

    def cancel(self):
        # Keep the failed slot for this receipt. An embedded/manual track must
        # not cause a later same-intent request to discover a new account.
        if self.binding is not None:
            self.binding['call'] = None
        self.key = self.result = self.pending = None

    def close(self):
        self.stopped = True
        self.cancel()
        # This is final host shutdown, not track switching. The call already
        # has a .3s IO budget, but only actual completion releases code ownership.
        if self.worker is not None:
            self.worker.join()
