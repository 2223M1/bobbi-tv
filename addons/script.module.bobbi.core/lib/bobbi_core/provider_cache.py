"""Bounded successful discovery snapshots; never a playback/readiness cache.

Each provider/query scope owns one receipt. A failed sibling cannot suppress a
healthy provider's cache, and partial responses never replace its last success.
Fixed slots bound storage without deleting any active selection/prepare record.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import math


class ProviderResultCache:
    SLOTS = 256
    MAX_ROWS = 2048

    def __init__(self, backend, scope, hours=0, refresh=False, cacheable=None):
        self.backend, self.scope = backend, str(scope)
        value = float(hours)
        self.hours = max(0, min(168, value)) if math.isfinite(value) else 0
        self.refresh = bool(refresh)
        self.cacheable = cacheable or (lambda key: True)

    def _identity(self, provider, name):
        token = sha256((self.scope + '\0' + str(provider) + '\0' + str(name)).encode()).hexdigest()
        return 'cinema:provider-success:v1:' + str(int(token, 16) % self.SLOTS), token

    def get(self, provider, name):
        if not self.hours or self.refresh or not self.cacheable(provider):
            return None
        key, token = self._identity(provider, name)
        try:
            record = self.backend.get(key)
            if (isinstance(record, dict) and record.get('scope') == token
                    and isinstance(record.get('rows'), list)
                    and len(record['rows']) <= self.MAX_ROWS):
                return deepcopy(record['rows'])
        except (OSError, ValueError, TypeError, RuntimeError):
            pass  # Optional search acceleration must never block a new title.
        return None

    def put(self, provider, name, rows):
        if not self.hours or not self.cacheable(provider) or len(rows) > self.MAX_ROWS:
            return
        key, token = self._identity(provider, name)
        # Empty *successful* responses have only the existing 30-second cooldown.
        ttl = timedelta(hours=self.hours) if rows else timedelta(seconds=30)
        try:
            self.backend.set(key, dict(scope=token, rows=deepcopy(list(rows))), ttl)
        except (OSError, ValueError, TypeError, RuntimeError):
            pass
