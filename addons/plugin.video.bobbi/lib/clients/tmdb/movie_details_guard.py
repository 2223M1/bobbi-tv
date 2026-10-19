"""Coalesce movie detail attempts without changing successful cache contracts.

The existing movie-years303 key/expiry remains the only successful cache. A
short, separate retry marker is not metadata or identity evidence. It survives
Kodi interpreter churn; neither failure nor a legacy fallback becomes a fresh
movie-years303 value. This does not extend a caller's search deadline.
"""
from datetime import date, timedelta
import hashlib
import os
from pathlib import Path
import threading
from time import monotonic, sleep, time

COOLDOWN = 20
_locks = [threading.Lock() for _ in range(64)]
_failures = {}
_failure_lock = threading.Lock()


def valid(params, data):
    """Bind shape to the requested movie, without inventing a release year."""
    request_id = params.get('id') if isinstance(params, dict) else params
    try:
        if type(request_id) not in (int, str) or int(request_id) <= 0:
            return False
        actual_id = data.get('id')
        title = data.get('title')
        if type(actual_id) not in (int, str) or int(actual_id) != int(request_id):
            return False
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 512:
            return False
        release = data.get('release_date')
        if release not in (None, ''):
            if not isinstance(release, str) or len(release) != 10:
                return False
            date.fromisoformat(release)
        return True
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def get(params, identifier, legacy_identifier, cache, fetch, expires,
        report=lambda *_: None, lock_root=None):
    digest = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    failure_key = 'movie-details-retry|' + digest
    lock = _locks[int(digest[:8], 16) % len(_locks)]
    lease = None

    def saved(key):
        row = cache.get(key=key)
        return row if valid(params, row) else None

    def store(key, data, ttl):
        try:
            cache.set(key=key, data=data, expires=ttl)
        except (AttributeError, OSError, ValueError, TypeError):
            # A cache write is optional; its failure is not a new network retry.
            report('CACHE_WRITE_UNAVAILABLE')

    current = saved(identifier)
    if current is not None:
        return current
    old = saved(legacy_identifier)
    if not lock.acquire(blocking=False):
        if old is not None:
            return old
        if not lock.acquire(timeout=22):
            report('COALESCED_REQUEST_TIMEOUT')
            return None
    try:
        # Kodi invocations have separate interpreters. File leases are striped
        # and non-destructive, matching the existing TV-detail coordination.
        if lock_root is not None:
            import fcntl
            directory = Path(lock_root)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            stripe = str(int(digest[:8], 16) % len(_locks))
            lease = os.open(str(directory / stripe), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            until = monotonic() + 24
            while True:
                try:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if old is not None or monotonic() >= until:
                        report('REFRESH_IN_FLIGHT' if old is not None else 'COALESCED_REQUEST_TIMEOUT')
                        return old
                    sleep(.05)
        current = saved(identifier)
        if current is not None:
            return current
        old = saved(legacy_identifier)
        with _failure_lock:
            recent = _failures.get(failure_key)
        persisted = cache.get(key=failure_key)
        if type(persisted) in (int, float) and 0 <= time() - persisted < COOLDOWN:
            recent = persisted
        if type(recent) in (int, float) and 0 <= time() - recent < COOLDOWN:
            report('RECENT_REQUEST_FAILED')
            return old
        try:
            data = fetch(params)
            if not valid(params, data):
                raise ValueError('INVALID_MOVIE_DETAILS')
        except Exception as error:
            failed = time()
            with _failure_lock:
                if len(_failures) >= 512:
                    _failures.pop(next(iter(_failures)))
                _failures[failure_key] = failed
            store(failure_key, failed, timedelta(seconds=COOLDOWN))
            report(type(error).__name__)
            return old
        store(identifier, data, expires)
        with _failure_lock:
            _failures.pop(failure_key, None)
        return data
    except OSError as error:
        # Failure to establish coordination must not start uncoalesced IO or
        # discard the separately validated legacy fallback.
        report(type(error).__name__)
        return old
    finally:
        try:
            if lease is not None:
                os.close(lease)
        finally:
            lock.release()
