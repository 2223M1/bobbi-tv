"""Bounded provider orchestration; never renders GUI or starts a player."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread
from time import monotonic
from bobbi_core.search_admission import try_acquire
from bobbi_core.search_completion import SearchResults


class ProgressiveSearch:
    def __init__(self, session, setup, transform, workers=4, budget=30.0, on_complete=None, admission=try_acquire,
                 result_cache=None):
        if not 1 <= workers <= 4 or not 0 < budget <= 30:
            raise ValueError('Bounded search subscription required')
        self.session, self.setup, self.transform = session, setup, transform
        self.workers, self.budget = workers, budget
        self.cancelled = Event()
        self.started = False
        self.pool = None
        self.sequence = 0
        self.on_complete = on_complete
        self.admission, self.lease = admission, None
        self.result_cache = result_cache

    def start(self):
        if self.started:
            raise RuntimeError('One coordinator per list session')
        self.started = True
        self.session.publish(self.session.epoch, 'setup', state='PENDING')
        self.thread = Thread(target=self._run, name='BobiSourceCoordinator', daemon=True)
        self.thread.start()

    def _stop_pool(self):
        if self.pool is not None:
            try:
                self.pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # Kodi's Python 3.8 has no cancel_futures keyword. Every queued
                # run checks cancellation before any provider IO, and retains
                # its admission lease until that no-op actually exits.
                self.pool.shutdown(wait=False)

    def _run(self):
        self.deadline = monotonic() + self.budget
        try:
            while not self.cancelled.is_set() and monotonic() < self.deadline:
                self.lease = self.admission()
                if self.lease is not None:
                    break
                self.cancelled.wait(0.05)
            if self.lease is None or self.cancelled.is_set():
                if not self.cancelled.is_set():
                    self.session.publish(self.session.epoch, 'setup', state='TIMEOUT', error='PREVIOUS_SEARCH_IO_BUSY')
                return
            self.pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='BobiSource')
            self.setup(self)
            if not self.cancelled.is_set():
                self.session.publish(self.session.epoch, 'setup',
                    state='TIMEOUT' if monotonic() >= self.deadline else 'COMPLETE')
            while not self.cancelled.wait(0.1):
                states = self.session.status()['providers']
                if all(row['state'] in self.session.TERMINAL for row in states.values()):
                    if self.on_complete and all(row['state'] == 'COMPLETE' for row in states.values()):
                        self.on_complete()
                    return
                if monotonic() >= self.deadline:
                    for provider, record in states.items():
                        if record['state'] not in self.session.TERMINAL:
                            self.session.publish(self.session.epoch, provider, state='TIMEOUT', error='SEARCH_DEADLINE')
                    return
        except Exception as error:
            self.session.publish(self.session.epoch, 'coordinator', state='FAILED', error=type(error).__name__)
        finally:
            self.cancelled.set()
            self.session.stop_queries()
            self._stop_pool()
            if self.lease is not None:
                self.lease.release()

    def submit_task(self, name, indexer_key, fn, *args, **kwargs):
        progressive = kwargs.pop('_progressive', False)
        if self.cancelled.is_set() or monotonic() >= self.deadline:
            return None
        self.sequence += 1
        if self.sequence > 32:
            raise ValueError('Provider task budget exceeded')
        provider = '{}:{}'.format(indexer_key, self.sequence)
        self.session.publish(self.session.epoch, provider, state='PENDING')

        def run():
            if self.cancelled.is_set():
                return
            self.session.publish(self.session.epoch, provider, state='RUNNING')
            try:
                def emit(result):
                    if self.cancelled.is_set() or monotonic() >= self.deadline:
                        return False
                    completion = result.completion if isinstance(result, SearchResults) else None
                    rows = self.transform(result or [])
                    if self.cancelled.is_set() or monotonic() >= self.deadline:
                        return False
                    return self.session.publish(self.session.epoch, provider, rows,
                        state='RUNNING', error=completion.summary() if completion else '',
                        **({'completion': completion} if completion is not None else {}))
                cached = self.result_cache.get(indexer_key, name) if self.result_cache is not None else None
                call_options = dict(kwargs, publish=emit) if progressive else kwargs
                result = fn(*args, **call_options) if cached is None else cached
                if self.cancelled.is_set():
                    return
                completion = result.completion if isinstance(result, SearchResults) else None
                raw = result or []
                result = self.transform(raw)
                if not self.cancelled.is_set():
                    if monotonic() >= self.deadline:
                        self.session.publish(self.session.epoch, provider, state='TIMEOUT', error='SEARCH_DEADLINE',
                            **({'completion': completion} if completion is not None else {}))
                    else:
                        accepted = self.session.publish(self.session.epoch, provider, result,
                            state=completion.state if completion is not None else 'COMPLETE',
                            error=completion.summary() if completion is not None and not completion.complete else '',
                            **({'completion': completion} if completion is not None else {}))
                        if (accepted and cached is None and self.result_cache is not None
                                and (completion is None or completion.complete)):
                            self.result_cache.put(indexer_key, name, raw)
            except Exception as error:
                if not self.cancelled.is_set():
                    state = 'TIMEOUT' if ('timeout' in type(error).__name__.casefold()
                        or getattr(error, 'code', '') in ('DEADLINE', 'CANCELLED')) else 'FAILED'
                    self.session.publish(self.session.epoch, provider, state=state, error=type(error).__name__)
        self.lease.retain()
        try:
            future = self.pool.submit(run)
        except BaseException:
            self.lease.release()
            raise
        future.add_done_callback(self.lease.release)
        return future

    def cancel(self):
        self.cancelled.set()
        self.session.stop_queries()
        self._stop_pool()
