"""Search-local row ownership and publication lifetime, not account isolation.

The default factory still uses legacy authentication (including RD OAuth and
Debrider IP discovery). No credential generation or pure authentication factory
is claimed here. Only the scoped aggregate row cache is excluded.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from bobbi_core.search_completion import SearchCompletion, SearchResults


class CheckHandle:
    """One check and its explicitly owned cleanup; borrowed resources omit close."""
    def __init__(self, check, close=None):
        self.check, self.close = check, close


class _QuietProgress:
    def update(self, *args, **kwargs):
        pass


class SearchDebridContext:
    """Captured entry settings plus one search round's cancellation/deadline.

Factories must return a fresh CheckHandle, with cleanup only for resources they
own. Factory exceptions must clean their own not-yet-returned resources.
"""
    def __init__(self, providers, *, show_uncached, include_all_uncached, workers,
                 current, cancelled, deadline, helper_factory):
        self.providers = tuple(providers)
        self.show_uncached = bool(show_uncached)
        self.include_all_uncached = bool(include_all_uncached)
        self.workers = max(1, min(6, int(workers))) if self.providers else 1
        self.current, self.cancelled, self.deadline = current, cancelled, deadline
        self.helper_factory = helper_factory
        self.failures = []  # Original exceptions retained in memory, never cached/logged as text.
        self._lock, self._revoked = Lock(), False

    def live(self):
        # Serialize sticky observation, not provider IO or executor shutdown.
        with self._lock:
            if not self._revoked:
                try:
                    self._revoked = (self.current() is not True or self.cancelled.is_set()
                                     or monotonic() >= self.deadline)
                except Exception:
                    self._revoked = True
            return not self._revoked

    def _failed(self, provider, phase, error):
        with self._lock:
            self.failures.append((provider, phase, error))

    def _check(self, provider, rows):
        if not self.live():
            return []
        handle, close = None, None
        try:
            # Keep construction inside the retained outer provider worker's
            # synchronous child lifetime. Legacy auth is deliberately unchanged.
            handle = self.helper_factory(provider)
            close = handle.close
            if not self.live():
                return []
            local = copy.deepcopy(rows)
            cached, uncached = [], []
            if not self.live():
                return []
            handle.check(local, cached, uncached, len(local), _QuietProgress(), Lock())
            if not self.live():
                return []
            # RD/AD may append their uncached list into cached according to an
            # ambient display preference. Interpret the final row facts using
            # the captured preference and eliminate that local identity alias.
            include = self.show_uncached and (self.include_all_uncached
                                              or provider in ('RealDebrid', 'AllDebrid'))
            found, output = set(), []
            for row in cached + uncached:
                if id(row) not in found and (row.isCached or include):
                    found.add(id(row))
                    output.append(row)
            return output
        except Exception as error:
            self._failed(provider, 'factory' if handle is None else 'check', error)
            return []
        finally:
            if close is not None:
                try:
                    close()
                except Exception as error:
                    self._failed(provider, 'close', error)

    def check(self, rows, direct):
        if not self.live():
            return []
        if not rows or not self.providers:
            return SearchResults(direct, SearchCompletion()) if self.live() else []
        output, futures, completed = [], [], set()
        # Do not change to wait=False: the outer ProgressiveSearch callback owns
        # its admission lease until every child call AND cleanup actually exit.
        try:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(self.providers)),
                                    thread_name_prefix='BobbiDebrid') as executor:
                for provider in self.providers:
                    if not self.live():
                        break
                    try:
                        futures.append((provider, executor.submit(self._check, provider, rows)))
                    except Exception as error:
                        self._failed(provider, 'submit', error)
                        break
                for provider, future in futures:
                    try:
                        batch = future.result()
                        completed.add(provider)
                        if self.live():
                            output.extend(batch)
                    except Exception as error:
                        self._failed(provider, 'future', error)
        except Exception as error:
            self._failed('', 'executor', error)
        if not self.live():
            return []
        # Report actual check/cleanup outcomes through the existing receipt.
        # Rows are independent evidence: a close failure may retain good rows,
        # while an empty successful availability check is still successful.
        failed = {provider for provider, _, _ in self.failures}
        submitted = {provider for provider, _ in futures}
        succeeded = sum(provider in completed and provider not in failed for provider in self.providers)
        skipped = sum(provider not in submitted and provider not in failed for provider in self.providers)
        completion = SearchCompletion(len(self.providers), succeeded=succeeded,
            failed=len(self.providers) - succeeded - skipped, skipped=skipped)
        if '' in failed:
            completion = completion.combine(SearchCompletion(1, failed=1))
        return SearchResults(output + direct, completion)
