"""Visible texture delivery must not depend on slow/optional disk maintenance."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import time

import pytest

from test_image_cache import PNG
from bobbi_core import image_cache as module


def test_visible_busy_probe_is_not_blocked_by_disk_pruning(tmp_path, monkeypatch):
    cache = module.ImageCache(tmp_path, transport=lambda *a: dict(status=200, body=PNG))
    entered, release = Event(), Event()
    original = cache._prune
    def slow(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(cache, '_prune', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        transfer = pool.submit(cache.get, '/t/p/w342/a.png', time.monotonic()+4)
        assert entered.wait(1)
        probe = pool.submit(cache.busy)
        try:
            # Production idle work calls this probe on the Kodi owner thread.
            assert probe.result(timeout=.2) is True
        finally:
            release.set()
        assert transfer.result() == (PNG, 'image/png')


def test_cached_image_still_works_if_access_time_cannot_be_written(tmp_path, monkeypatch):
    cache = module.ImageCache(tmp_path, transport=lambda *a: pytest.fail('No network on valid cache hit'))
    target = cache._file('/t/p/w342/a.png')
    target.write_bytes(PNG)
    def denied(*args, **kwargs): raise PermissionError('read-only cache metadata')
    monkeypatch.setattr(Path, 'touch', denied)
    assert cache.get('/t/p/w342/a.png', time.monotonic()+1) == (PNG, 'image/png')


def test_valid_download_is_renderable_when_disk_cache_is_full(tmp_path, monkeypatch):
    events, calls = [], []
    cache = module.ImageCache(tmp_path, report=events.append,
        transport=lambda *a: (calls.append(1), dict(status=200, body=PNG))[1])
    def full(*args, **kwargs): raise OSError(28, 'disk full')
    monkeypatch.setattr(module.tempfile, 'mkstemp', full)
    for _ in range(2):
        assert cache.get('/t/p/w342/a.png', time.monotonic()+1) == (PNG, 'image/png')
    assert calls == [1, 1]  # Failed optional persistence is not a network cooldown.
    assert events == ['IMAGE_CACHE_IO', 'IMAGE_CACHE_IO']
    assert not list(tmp_path.iterdir())


def test_single_flight_waiters_share_success_without_writable_cache(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    calls = []
    def fetch(*args):
        calls.append(1); entered.set()
        assert release.wait(3)
        return dict(status=200, body=PNG)
    cache = module.ImageCache(tmp_path, transport=fetch)
    waiter_ready = Event()
    def denied(*args, **kwargs): raise PermissionError('cache unavailable')
    monkeypatch.setattr(module.tempfile, 'mkstemp', denied)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.get, '/t/p/w342/a.png', time.monotonic()+4)
        assert entered.wait(1)
        flight = cache.inflight['/t/p/w342/a.png']
        event = getattr(flight, 'done', flight)
        original_wait = event.wait
        def wait(timeout):
            waiter_ready.set()
            return original_wait(timeout)
        monkeypatch.setattr(event, 'wait', wait)
        second = pool.submit(cache.get, '/t/p/w342/a.png', time.monotonic()+4)
        try:
            assert waiter_ready.wait(1)
        finally: release.set()
        assert first.result() == second.result() == (PNG, 'image/png')
    assert calls == [1]


def test_storage_lock_wait_obeys_cancel_and_does_not_publish(tmp_path):
    from threading import Lock
    stop, waiting = Event(), Event()
    cache = module.ImageCache(tmp_path, stopped=stop, transport=lambda *a: dict(status=200, body=PNG))
    lock = Lock(); lock.acquire()
    class StorageLock:
        def acquire(self, timeout):
            waiting.set()
            return lock.acquire(timeout=timeout)
        def release(self): lock.release()
    cache.storage_lock = StorageLock()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cache.get, '/t/p/w342/a.png', time.monotonic()+3)
        try:
            assert waiting.wait(1)
            stop.set()
            with pytest.raises(module.MetadataError, match='CANCELLED'):
                future.result(timeout=1)
        finally: lock.release()
    assert not list(tmp_path.iterdir()) and not cache.inflight


def test_expired_prune_cannot_publish_late_bytes(tmp_path, monkeypatch):
    stop = Event()
    cache = module.ImageCache(tmp_path, stopped=stop, transport=lambda *a: dict(status=200, body=PNG))
    original = cache._prune
    def expire(*args):
        original(*args)
        stop.set()
    monkeypatch.setattr(cache, '_prune', expire)
    with pytest.raises(module.MetadataError, match='CANCELLED'):
        cache.get('/t/p/w342/a.png', time.monotonic()+1)
    assert not list(tmp_path.iterdir())


def test_failed_eviction_does_not_exceed_quota_or_hide_valid_network_image(tmp_path, monkeypatch):
    cache = module.ImageCache(tmp_path, transport=lambda *a: dict(status=200, body=PNG), max_files=1)
    old = cache._file('/t/p/w342/old.png'); old.write_bytes(PNG)
    unlink = Path.unlink
    def protected(path, *args, **kwargs):
        if path == old: raise PermissionError('cannot evict')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', protected)
    assert cache.get('/t/p/w342/new.png', time.monotonic()+1) == (PNG, 'image/png')
    assert list(tmp_path.iterdir()) == [old]


def test_concurrent_publish_preserves_count_bytes_and_unowned_files(tmp_path):
    cache = module.ImageCache(tmp_path, transport=lambda *a: dict(status=200, body=PNG),
                              max_files=3, max_bytes=len(PNG)*3)
    (tmp_path/'notes').write_text('keep')
    (tmp_path/('a'*64+'.png')).mkdir()
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda n: cache.get('/t/p/w342/p%d.png'%n, time.monotonic()+3), range(12)))
    images = [p for p in tmp_path.glob('*.png') if p.is_file()]
    assert len(images) == 3 and sum(p.stat().st_size for p in images) == len(PNG)*3
    assert all(value == (PNG, 'image/png') for value in values)
    assert (tmp_path/'notes').read_text() == 'keep'
    assert (tmp_path/('a'*64+'.png')).is_dir()
    assert not cache.inflight


def test_real_http_returns_success_despite_failed_persistence(tmp_path, monkeypatch):
    from urllib.request import build_opener, ProxyHandler
    service = module.ImageService(tmp_path, transport=lambda *a: dict(status=200, body=PNG))
    service.start()
    try:
        def full(*args, **kwargs): raise OSError(28, 'full')
        monkeypatch.setattr(service.cache, '_store', full)
        with build_opener(ProxyHandler({})).open(module.image_url('/http.png', 'w342', tmp_path), timeout=2) as response:
            assert response.status == 200 and response.read() == PNG
        assert not service.cache.failures
    finally: service.close()
