"""Bounded successful discovery snapshots; never a playback/readiness cache.

Each provider/query scope owns one receipt. A failed sibling cannot suppress a
healthy provider's cache, and partial responses never replace its last success.
Fixed slots bound storage without deleting any active selection/prepare record.
"""
from copy import deepcopy
from datetime import timedelta
from dataclasses import asdict, replace
from hashlib import sha256
import math
from time import time

from .search_completion import SearchCompletion, SearchResults


class ProviderResultCache:
    SLOTS = 256
    MAX_ROWS = 2048
    PARTIAL_SECONDS = 1800
    LANES = 4

    def __init__(self, backend, scope, hours=0, refresh=False, cacheable=None):
        self.backend, self.scope = backend, str(scope)
        value = float(hours)
        self.hours = max(0, min(168, value)) if math.isfinite(value) else 0
        self.refresh = bool(refresh)
        self.cacheable = cacheable or (lambda key: True)

    def resume_cached_queries(self):
        """A retry may reuse successes written during the initial forced pass."""
        self.refresh = False

    def _identity(self, provider, name):
        token = sha256((self.scope + '\0' + str(provider) + '\0' + str(name)).encode()).hexdigest()
        return 'cinema:provider-snapshot:v2:' + str(int(token, 16) % self.SLOTS), token

    def _read(self, key, token):
        record = next((record for _, record in self._lanes(key)
                       if isinstance(record, dict) and record.get('scope') == token), None)
        if (not isinstance(record, dict) or record.get('scope') != token
                or not isinstance(record.get('rows'), list) or len(record['rows']) > self.MAX_ROWS
                or type(record.get('created')) not in (float, int)
                or type(record.get('expires')) not in (float, int)
                or not record['created'] <= time() < record['expires']):
            return None
        completion = SearchCompletion(**record['completion'])
        return SearchResults(deepcopy(record['rows']), replace(completion,
            snapshot_age=completion.snapshot_age + max(0, int(time() - record['created']))))

    def _lanes(self, key):
        # Independent keys avoid a read/modify/write bucket replacing another
        # producer. Lane zero also reads pre-upgrade snapshots unchanged.
        for index in range(self.LANES):
            lane = key if index == 0 else key + ':lane:' + str(index)
            yield lane, self.backend.get(lane)

    def _write(self, key, token, value, ttl):
        lanes = list(self._lanes(key))
        owned = next((lane for lane, row in lanes
                      if isinstance(row, dict) and row.get('scope') == token), None)
        def expiry(row):
            value = row.get('expires') if isinstance(row, dict) else None
            return value if type(value) in (int, float) and math.isfinite(value) else 0
        target = owned or min(lanes, key=lambda item: expiry(item[1]))[0]
        self.backend.set(target, value, ttl)

    @staticmethod
    def _merge(old, new):
        # The same identity boundary as the picker: never dedup on title,
        # quality, group or a guessed equivalence between BT and cloud files.
        from .source_list_session import SourceListSession
        identity = SourceListSession({}, lambda rows: rows)
        rows, seen = [], set()
        for row in list(old) + list(new):
            try:
                key = identity.key(row)
            except (ValueError, TypeError, AttributeError):
                key = None  # Uncertain identity must not erase another source.
            if key is None or key not in seen:
                rows.append(row)
                seen.add(key)
        return rows

    def get(self, provider, name):
        if not self.hours or self.refresh or not self.cacheable(provider):
            return None
        key, token = self._identity(provider, name)
        try:
            success = self._read(key, token)
            partial = self._read(key + ':partial', token)
            if partial is not None:
                rows = self._merge(success or [], partial)
                return SearchResults(rows[:self.MAX_ROWS], replace(partial.completion,
                    truncated=partial.completion.truncated + int(len(rows) > self.MAX_ROWS),
                    snapshot_age=max(partial.completion.snapshot_age,
                                     success.completion.snapshot_age if success is not None else 0)))
            return success
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, OverflowError):
            pass  # Optional search acceleration must never block a new title.
        return None

    def put(self, provider, name, rows):
        if not self.hours or not self.cacheable(provider) or len(rows) > self.MAX_ROWS:
            return
        key, token = self._identity(provider, name)
        try:
            completion = rows.completion if isinstance(rows, SearchResults) else SearchCompletion()
            if not completion.complete:
                # Never pin an empty failure as "no sources". Preserve the last
                # successful snapshot independently from this short-lived view.
                if not rows or not completion.succeeded:
                    return
                key += ':partial'
                old = self._read(key, token)
                if old is not None:
                    rows = self._merge(old, rows)
                    completion = replace(completion, snapshot_age=max(
                        old.completion.snapshot_age, completion.snapshot_age))
                # Repeated failed refreshes cannot renew old rows indefinitely.
                remaining = self.PARTIAL_SECONDS - completion.snapshot_age
                if remaining <= 0:
                    return
                ttl = timedelta(seconds=min(remaining, self.hours * 3600))
            else:
                remaining = self.hours * 3600 - completion.snapshot_age if rows else 30
                if remaining <= 0:
                    return
                ttl = timedelta(seconds=remaining)
            if len(rows) > self.MAX_ROWS:
                completion = replace(completion, truncated=completion.truncated + 1)
            now = time()
            self._write(key, token, dict(scope=token, rows=deepcopy(list(rows)[:self.MAX_ROWS]),
                completion=asdict(completion), created=now, expires=now + ttl.total_seconds()), ttl)
            if completion.complete:
                # A complete refresh supersedes the previous incomplete view.
                # Both supported cache backends expose get/set, not delete.
                for lane, record in self._lanes(key + ':partial'):
                    if isinstance(record, dict) and record.get('scope') == token:
                        self.backend.set(lane, {}, timedelta(seconds=1))
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, OverflowError):
            pass
