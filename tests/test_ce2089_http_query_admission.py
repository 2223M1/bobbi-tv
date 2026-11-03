"""Real bounded OS admission across callers, including abandoned IO workers."""
import importlib.util
from pathlib import Path
from threading import Event, Thread, Lock
import time
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))

spec = importlib.util.spec_from_file_location('query_admission_http',
    Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/clients/portable_http.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)


class Response:
    status_code = 200
    headers = {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield b'{}'


@pytest.fixture
def private_slots(tmp_path, monkeypatch):
    from bobbi_core import runtime_paths
    monkeypatch.setattr(runtime_paths, 'ProfilePath', lambda name: tmp_path / name)
    return tmp_path


def test_cancelled_owner_keeps_same_query_excluded_without_blocking_other_urls(private_slots):
    release, entered, closed = Event(), Event(), Event()
    lock, calls = Lock(), []
    def get(url, **options):
        with lock: calls.append(url)
        if url.endswith('/blocked'):
            entered.set()
            assert release.wait(3)
            closed.set()
        return Response()
    session = SimpleNamespace(get=get)
    try:
        first = list(http.iter_events(session, ['https://fixture.invalid/blocked'],
            time.monotonic()+.08, lambda: False, 'json', 1024))
        assert entered.is_set() and not closed.is_set()
        assert not any(row[1]=='succeeded' for row in first)
        second = list(http.iter_events(session,
            ['https://fixture.invalid/blocked', 'https://fixture.invalid/healthy'],
            time.monotonic()+.15, lambda: False, 'json', 1024))
        assert calls.count('https://fixture.invalid/blocked') == 1
        assert any(row[0]==1 and row[1]=='succeeded' for row in second)
    finally:
        release.set()
        assert closed.wait(1)


def test_closed_owner_allows_fresh_retry_and_context_is_not_shared(private_slots):
    calls=[]
    def get(url, **options):
        calls.append(url)
        return Response()
    session=SimpleNamespace(get=get)
    for _ in range(2):
        rows=list(http.iter_events(session,['https://fixture.invalid/ok'],
            time.monotonic()+1,lambda:False,'json',1024))
        assert any(row[1]=='succeeded' for row in rows)
    assert len(calls)==2


def test_duplicate_wait_respects_caller_cancel(private_slots):
    release, entered, cancel = Event(), Event(), Event()
    calls=[]
    def get(url, **options):
        calls.append(url)
        entered.set()
        assert release.wait(3)
        return Response()
    session=SimpleNamespace(get=get)
    try:
        list(http.iter_events(session,['https://fixture.invalid/cancel'],
            time.monotonic()+.05,lambda:False,'json',1024))
        assert entered.is_set()
        timer=Thread(target=lambda:(time.sleep(.05),cancel.set()))
        timer.start();began=time.monotonic()
        rows=list(http.iter_events(session,['https://fixture.invalid/cancel'],
            time.monotonic()+2,cancel.is_set,'json',1024))
        timer.join(1)
        assert time.monotonic()-began<.5
        assert len(calls)==1 and not any(row[1]=='succeeded' for row in rows)
    finally:
        release.set()
