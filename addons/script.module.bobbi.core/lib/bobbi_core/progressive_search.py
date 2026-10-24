"""Bounded provider orchestration; never renders GUI or starts a player."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread, RLock
from time import monotonic
from bobbi_core.search_admission import try_acquire
from bobbi_core.search_completion import SearchResults, provider_failed


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
        self._lifecycle = RLock()
        self._closed = False
        self._futures = []
        self._task_ids = {}
        self._occurrences = {}
        self._retry_targets = None
        self._submitted = set()

    @property
    def retrying(self):
        return self._retry_targets is not None

    def retry_candidates(self):
        with self._lifecycle:
            status = self.session.status()
            if self._closed or status['cancelled'] or status['confirmed']:
                return ()
            known = set(self._task_ids.values())
            return tuple(key for key, row in status['providers'].items()
                         if key in known and provider_failed(row))

    def retry_failed(self):
        """Explicit user retry, never a timer or a second search subscription.

        A fresh deadline/cancel token is created only after ALL old IO exits.
        setup resubmits descriptors; successful siblings are filtered before IO.
        """
        with self._lifecycle:
            if (not self.started or self.thread.is_alive()
                    or any(not future.done() for future in self._futures)):
                return False
            targets = self.retry_candidates()
            if not targets or not self.session.retry_providers(targets):
                return False
            self._retry_targets = set(targets)
            self.cancelled = Event()
            self.pool, self.lease = None, None
            self._futures, self._occurrences, self._submitted = [], {}, set()
            self._start_thread()
            return True

    def start(self):
        with self._lifecycle:
            if self.started or self._closed:
                raise RuntimeError('One coordinator per list session')
            self.started = True
            self.session.publish(self.session.epoch, 'setup', state='PENDING')
            self._start_thread()

    def _start_thread(self):
        self.thread = Thread(target=self._run, name='BobiSourceCoordinator', daemon=True)
        try:
            self.thread.start()
        except Exception:
            self.cancelled.set()
            self.session.stop_queries()
            raise

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
                    for provider in self._retry_targets or ():
                        self.session.publish(self.session.epoch, provider,
                            state='TIMEOUT', error='PREVIOUS_SEARCH_IO_BUSY')
                return
            self.pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='BobiSource')
            self.setup(self)
            if not self.cancelled.is_set():
                self.session.publish(self.session.epoch, 'setup',
                    state='TIMEOUT' if monotonic() >= self.deadline else 'COMPLETE')
                for provider in (self._retry_targets or set()) - self._submitted:
                    self.session.publish(self.session.epoch, provider,
                                         state='FAILED', error='RETRY_PROVIDER_UNAVAILABLE')
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
        identity = (str(indexer_key), str(name))
        ordinal = self._occurrences.get(identity, 0) + 1
        self._occurrences[identity] = ordinal
        task_id = identity + (ordinal,)
        provider = self._task_ids.get(task_id)
        if self.retrying and provider not in self._retry_targets:
            return None
        self.sequence = sum(self._occurrences.values())
        if self.sequence > 32:
            raise ValueError('Provider task budget exceeded')
        if provider is None:
            provider = '{}:{}'.format(indexer_key, self.sequence)
            self._task_ids[task_id] = provider
        self._submitted.add(provider)
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
                cached = (self.result_cache.get(indexer_key, name)
                          if self.result_cache is not None and not self.retrying else None)
                call_options = dict(kwargs, publish=emit) if progressive else kwargs
                result = fn(*args, **call_options) if cached is None else cached
                from bobbi_core.search_trace import observe
                observe('provider_return', result or [], 'network' if cached is None else 'cache',
                        invocation=self.session.epoch)
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
        self._futures.append(future)
        return future

    def cancel(self):
        with self._lifecycle:
            self._closed = True
            self.cancelled.set()
            self.session.stop_queries()
            self._stop_pool()
