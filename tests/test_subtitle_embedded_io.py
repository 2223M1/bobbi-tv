"""No CLI-Python Android/Windows fallback, not on-device certification."""
from pathlib import Path
import sys
from threading import Event
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import subtitle_io as io, subtitle_io_worker as worker


@pytest.fixture(autouse=True)
def no_cli(monkeypatch):
    def absent():
        raise io.SubtitleIOStopped('SUBTITLE_IO_PYTHON_UNAVAILABLE')
    monkeypatch.setattr(io, '_interpreter', absent)
    monkeypatch.setattr(io, '_EMBEDDED', None)


def read():
    return io.read_http('https://api.assrt.net/v1/sub/search', time.monotonic() + .5,
                        lambda: False, 1024)


def test_embedded_returns_only_bounded_worker_result(monkeypatch):
    seen = []
    def fetch(command):
        seen.append(command)
        return b'fixture'
    monkeypatch.setattr(worker, 'fetch', fetch)
    assert read() == b'fixture'
    assert callable(seen[0]['_cancelled'])
    assert seen[0]['_deadline'] > time.monotonic() - 1


def test_single_stuck_dns_worker_does_not_accumulate_or_publish_late(monkeypatch):
    release, entered = Event(), Event()
    def fetch(command):
        entered.set()
        release.wait(2)
        return b'late'
    monkeypatch.setattr(worker, 'fetch', fetch)
    try:
        with pytest.raises(io.SubtitleIOStopped, match='DEADLINE'):
            io.read_http('https://api.assrt.net/v1/sub/search', time.monotonic() + .04,
                         lambda: False, 1024)
        assert entered.is_set()
        with pytest.raises(io.SubtitleIOStopped, match='BUSY'):
            read()
    finally:
        release.set()
        io._EMBEDDED.join(2)
    monkeypatch.setattr(worker, 'fetch', lambda _: b'new')
    assert read() == b'new'


def test_embedded_error_cannot_export_url_or_credentials(monkeypatch):
    def fail(_):
        raise ValueError('ASSRT_HTTP_401 https://secret.example/?token=fixture')
    monkeypatch.setattr(worker, 'fetch', fail)
    with pytest.raises(io.SubtitleIOStopped, match='^SUBTITLE_IO_FAILED$'):
        read()


def test_embedded_opensubtitles_read_is_cooperatively_cancelled():
    stopped = Event()
    class Response:
        def read1(self, _):
            stopped.set()
            return b'first'
        def read(self, _):
            pytest.fail('Embedded mode must not use an unlimited drip read')
    with pytest.raises(ValueError, match='DEADLINE'):
        worker.read_body(Response(), {'_deadline': time.monotonic()+1,
                                     '_cancelled': stopped.is_set}, 1024)


def test_embedded_limit_during_read():
    class Response:
        def read1(self, amount):
            return b'x' * amount
    with pytest.raises(ValueError, match='SIZE'):
        worker.read_body(Response(), {'_deadline': time.monotonic()+1}, 3)
