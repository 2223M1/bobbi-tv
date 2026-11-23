"""Bounded provider orchestration; never renders GUI or starts a player."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from math import ceil
from threading import Event, Thread, RLock
from time import monotonic
from bobbi_core.search_completion import SearchCompletion, SearchResults, provider_failed


def _failure_diagnostic(error, invocation, ordinal):
    """Retain code locations, never exception text, source URLs or locals."""
    import json
    import logging
    import re
    import traceback
    from pathlib import Path
    module = getattr(error, 'name', None) if isinstance(error, ImportError) else None
    if not isinstance(module, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]{0,160}', module):
        module = None
    frames = [dict(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
              for frame in traceback.extract_tb(error.__traceback__)[-8:]]
    logging.getLogger(__name__).warning('BOBBI-SEARCH-FAILURE %s', json.dumps(dict(
        invocation=invocation, ordinal=ordinal, error=type(error).__name__, module=module, frames=frames)))


class ProgressiveSearch:
    def __init__(self, session, setup, transform, workers=4, budget=30.0, on_complete=None, admission=None,
                 result_cache=None, current=lambda: True, on_close=None):
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
        self.current = current
        self._profile_revoked = False
        self.result_cache = result_cache
        self._lifecycle = RLock()
        self._closed = False
        self._on_close, self._pending = on_close, 0
        self._futures = []
        self._task_ids = {}
        self._occurrences = {}
        self._retry_targets = None
        self._submitted = set()

    @property
    def retrying(self):
        return self._retry_targets is not None

    def scope_current(self):
        if not self._profile_revoked:
            try:
                if self.current() is not True:
                    self._profile_revoked = True
            except Exception:
                self._profile_revoked = True
        return not self._profile_revoked

    def scope_cancelled(self):
        if not self.scope_current():
            self.cancel()
        return self.cancelled.is_set()

    def retry_candidates(self):
        if not self.scope_current():
            self.cancel()
        with self._lifecycle:
            return self._retry_candidates_locked()

    def _retry_candidates_locked(self):
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
        if not self.scope_current():
            self.cancel()
            return False
        with self._lifecycle:
            if (not self.started or self.thread.is_alive()
                    or any(not future.done() for future in self._futures)):
                return False
            targets = self._retry_candidates_locked()
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
        self._retain_work()
        try:
            self.thread = Thread(target=self._run, name='BobbiSourceCoordinator', daemon=True)
            self.thread.start()
        except Exception:
            self._closed = True
            self.cancelled.set()
            self.session.stop_queries()
            self._release_work()
            raise

    def _retain_work(self):
        with self._lifecycle:
            self._pending += 1

    def _release_work(self, _future=None):
        with self._lifecycle:
            self._pending -= 1
            self._close_if_drained()

    def _close_if_drained(self):
        if self._closed and not self._pending and self._on_close is not None:
            close, self._on_close = self._on_close, None
            close()

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
            if not callable(self.admission):
                raise ValueError('SEARCH_ADMISSION_REQUIRED')
            while not self.scope_cancelled() and monotonic() < self.deadline:
                self.lease = self.admission()
                if self.lease is not None:
                    break
                self.cancelled.wait(0.05)
            if self.lease is None or self.scope_cancelled():
                if not self.cancelled.is_set():
                    self.session.publish(self.session.epoch, 'setup', state='TIMEOUT', error='PREVIOUS_SEARCH_IO_BUSY')
                    for provider in self._retry_targets or ():
                        self.session.publish(self.session.epoch, provider,
                            state='TIMEOUT', error='PREVIOUS_SEARCH_IO_BUSY')
                return
            self.pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='BobbiSource')
            self.setup(self)
            if not self.scope_cancelled():
                self.session.publish(self.session.epoch, 'setup',
                    state='TIMEOUT' if monotonic() >= self.deadline else 'COMPLETE')
                for provider in (self._retry_targets or set()) - self._submitted:
                    self.session.publish(self.session.epoch, provider,
                                         state='FAILED', error='RETRY_PROVIDER_UNAVAILABLE')
            while not self.cancelled.wait(0.1):
                if self.scope_cancelled():
                    return
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
            self._release_work()

    def submit_task(self, name, indexer_key, fn, *args, **kwargs):
        progressive = kwargs.pop('_progressive', False)
        cache_seed_only = kwargs.pop('_cache_seed_only', False)
        if self.scope_cancelled() or monotonic() >= self.deadline:
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
            if self.scope_cancelled():
                return
            self.session.publish(self.session.epoch, provider, state='RUNNING')
            streamed, result, saved, receipt, stream_overflow = [], None, False, None, False
            streamed_origin = None
            try:
                def emit(result, *, seed=False):
                    nonlocal stream_overflow, streamed_origin
                    emitted_at = monotonic()
                    if self.scope_cancelled() or monotonic() >= self.deadline:
                        return False
                    completion = result.completion if isinstance(result, SearchResults) else None
                    rows = self.transform(result if result is not None else [])
                    # A receipt-bearing transform returns the complete receipt
                    # (upstream plus its own work), never a delta to add again.
                    if isinstance(rows, SearchResults):
                        completion = rows.completion
                    if self.scope_cancelled() or monotonic() >= self.deadline:
                        return False
                    accepted = self.session.publish(self.session.epoch, provider, rows,
                        state='RUNNING', error=completion.summary() if completion else '',
                        **({'completion': completion} if completion is not None else {}))
                    if accepted and not seed and self.result_cache is not None:
                        origin = emitted_at - (completion.snapshot_age if completion is not None else 0)
                        streamed_origin = min(streamed_origin, origin) if streamed_origin is not None else origin
                        stream_overflow |= len(streamed) + len(result or []) > 2048
                        streamed.extend(list(result or [])[:max(0, 2048-len(streamed))])
                    return accepted
                cached = (self.result_cache.get(indexer_key, name)
                          if self.result_cache is not None and not self.retrying else None)
                if cached is not None and (cache_seed_only or
                        isinstance(cached, SearchResults) and not cached.completion.complete):
                    # Show retained cards immediately, but keep the producer
                    # live so its per-query cache can fill only missing work.
                    # Seed rows are never counted as freshly streamed output.
                    if not emit(cached, seed=True):
                        return
                    cached = None
                call_options = dict(kwargs, publish=emit) if progressive else kwargs
                result = fn(*args, **call_options) if cached is None else cached
                returned_at = monotonic()
                receipt = result.completion if isinstance(result, SearchResults) else None
                from bobbi_core.search_trace import observe
                observe('provider_return', result or [], 'network' if cached is None else 'cache',
                        invocation=self.session.epoch)
                if self.scope_cancelled():
                    return
                completion = result.completion if isinstance(result, SearchResults) else None
                raw = result if result is not None else []
                result = self.transform(raw)
                if isinstance(result, SearchResults):
                    completion = result.completion
                if not self.scope_cancelled():
                    if monotonic() >= self.deadline:
                        self.session.publish(self.session.epoch, provider, state='TIMEOUT', error='SEARCH_DEADLINE',
                            **({'completion': completion} if completion is not None else {}))
                    else:
                        accepted = self.session.publish(self.session.epoch, provider, result,
                            state=completion.state if completion is not None else 'COMPLETE',
                            error=completion.summary() if completion is not None and not completion.complete else '',
                            **({'completion': completion} if completion is not None else {}))
                        if accepted and cached is None and self.result_cache is not None:
                            # Raw provider rows keep only their upstream receipt;
                            # downstream check failures must be re-evaluated, not
                            # cached into raw rows or counted again on the next run.
                            if receipt is not None:
                                raw = SearchResults(raw, replace(receipt,
                                    snapshot_age=receipt.snapshot_age + ceil(monotonic() - returned_at)))
                            self.result_cache.put(indexer_key, name, raw)
                            saved = True
            except Exception as error:
                _failure_diagnostic(error, self.session.epoch, ordinal)
                if not self.scope_cancelled():
                    state = 'TIMEOUT' if ('timeout' in type(error).__name__.casefold()
                        or getattr(error, 'code', '') in ('DEADLINE', 'CANCELLED')) else 'FAILED'
                    self.session.publish(self.session.epoch, provider, state=state, error=type(error).__name__)
            finally:
                # Final parsing/ranking can outlive the coordinator deadline.
                # Preserve only rows already accepted while it was live; late
                # rows never enter the current UI or this fallback snapshot.
                # Explicit user closure/cancellation still revokes the work.
                if (streamed and not saved and self.result_cache is not None
                        and self.scope_current() and not self._closed and not self.session.cancelled):
                    receipt = receipt or SearchCompletion(1, succeeded=1)
                    if receipt.complete:
                        receipt = receipt.combine(SearchCompletion(1, timed_out=1))
                    if stream_overflow:
                        receipt = receipt.combine(SearchCompletion(truncated=1))
                    receipt = replace(receipt, snapshot_age=max(receipt.snapshot_age,
                        ceil(monotonic() - streamed_origin) if streamed_origin is not None else 0))
                    self.result_cache.put(indexer_key, name, SearchResults(streamed, receipt))
        self.lease.retain()
        self._retain_work()
        try:
            future = self.pool.submit(run)
        except BaseException:
            self.lease.release()
            self._release_work()
            raise
        future.add_done_callback(self.lease.release)
        future.add_done_callback(self._release_work)
        self._futures.append(future)
        return future

    def cancel(self):
        with self._lifecycle:
            self._closed = True
            self.cancelled.set()
            self.session.stop_queries()
        # shutdown(cancel_futures=True) invokes done callbacks synchronously.
        # Never hold our lifecycle lock while acquiring the executor's lock:
        # its concurrent shutdown may already be running _release_work.
        self._stop_pool()
        with self._lifecycle:
            self._close_if_drained()
