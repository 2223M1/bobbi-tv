"""Validated 24-hour details with a seven-day last-known-good fallback."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import threading
import time

FRESH = 24 * 3600
STALE = 7 * FRESH
_locks = [threading.Lock() for _ in range(64)]
_failures = {}
_failure_lock = threading.Lock()


def value(row, name, default=None):
    return row.get(name, default) if hasattr(row, 'get') else getattr(row, name, default)


def valid(path, params, data):
    if data is None:
        return False
    try:
        if path == 'tv_details':
            if int(value(data, 'id')) != int(params['id']) or not value(data, 'name'):
                return False
            rows = value(data, 'seasons')
            if rows is None:
                return False
            numbers = [value(row, 'season_number') for row in rows]
        else:
            if int(value(data, 'season_number')) != int(params['season']):
                return False
            rows = value(data, 'episodes')
            if rows is None:
                return False
            numbers = [value(row, 'episode_number') for row in rows]
            if any(value(row, 'season_number', params['season']) != int(params['season']) for row in rows):
                return False
        return len(numbers) <= 10000 and len(set(numbers)) == len(numbers) and all(type(n) is int and n >= 0 for n in numbers)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def get(path, params, language, cache, fetch, report=lambda *_: None, clock=time.time, lock_root=None):
    params = dict(params) if isinstance(params, dict) else {'id': params}
    wants_aliases = path == 'tv_details' and ('append_to_response' not in params or
        'alternative_titles' in str(params.get('append_to_response') or '').split(','))
    key = 'am6b_details283|' + json.dumps([path, params, params.get('language') or language], sort_keys=True)
    lock = _locks[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(_locks)]
    lease = None

    def saved():
        record = cache.get(key=key)
        if not isinstance(record, dict) or not isinstance(record.get('fetched'), (int, float)):
            return None
        age = clock() - record['fetched']
        return record if 0 <= age <= STALE and valid(path, params, record.get('data')) else None

    def fallback(record, reason):
        report('stale' if record else 'failed', reason)
        return deepcopy(record['data']) if record else None

    def fresh(record):
        if not record or clock() - record['fetched'] >= FRESH:
            return False
        # Upgrade legacy successful details once through the ordinary bounded,
        # coalesced request. A successful response may legitimately omit this
        # optional section; record that it was requested, not that it exists.
        return (not wants_aliases or record.get('tv_aliases_requested') is True
                or value(record['data'], 'alternative_titles') is not None)

    old = saved()
    if fresh(old):
        return deepcopy(old['data'])
    # Readers with a stale success do not wait behind the refresh leader.
    if not lock.acquire(blocking=False):
        if old:
            return fallback(old, 'REFRESH_IN_FLIGHT')
        if not lock.acquire(timeout=22):
            return fallback(None, 'COALESCED_REQUEST_TIMEOUT')
    try:
        # Kodi directory invocations use separate Python interpreters. A file
        # lease coalesces them too; in-memory locks alone are insufficient.
        if lock_root is not None:
            from bobbi_platform.instance_lock import InstanceLock
            directory = Path(lock_root)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            stripe = str(int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 64)
            lease = InstanceLock(directory / stripe)
            until = time.monotonic() + 24
            while True:
                try:
                    lease.acquire()
                    break
                except (BlockingIOError, PermissionError):
                    if old or time.monotonic() >= until:
                        return fallback(old, 'REFRESH_IN_FLIGHT' if old else 'COALESCED_REQUEST_TIMEOUT')
                    time.sleep(.05)
        old = saved()
        if fresh(old):
            return deepcopy(old['data'])
        with _failure_lock:
            recent = _failures.get(key, 0)
        persisted_failure = cache.get(key=key + '|failure')
        if type(persisted_failure) in (int, float):
            recent = max(recent, persisted_failure)
        if clock() - recent < 20:
            return fallback(old, 'RECENT_REQUEST_FAILED')
        try:
            data = fetch(params)
            if not valid(path, params, data):
                raise ValueError('INVALID_DETAILS')
        except Exception as error:
            with _failure_lock:
                if len(_failures) >= 512:
                    _failures.pop(next(iter(_failures)))
                _failures[key] = clock()
            cache.set(key=key + '|failure', data=clock(), expires=timedelta(seconds=20))
            return fallback(old, type(error).__name__)
        cache.set(key=key, data={'fetched': clock(), 'data': deepcopy(data),
            'tv_aliases_requested': wants_aliases}, expires=timedelta(seconds=STALE))
        with _failure_lock:
            _failures.pop(key, None)
        return data
    finally:
        if lease is not None:
            lease.close()
        lock.release()
