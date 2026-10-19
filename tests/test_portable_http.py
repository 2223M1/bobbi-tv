import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace
from threading import BoundedSemaphore
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_http_test',
    ROOT / 'addons/plugin.video.bobbi/lib/clients/portable_http.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)


@pytest.fixture(autouse=True)
def bounded_test_slots(monkeypatch):
    slots = BoundedSemaphore(4)
    monkeypatch.setattr(http, '_slot', lambda: SimpleNamespace(release=slots.release)
                        if slots.acquire(blocking=False) else None)


class Response:
    status_code = 200
    headers = {}
    def __init__(self, parts):
        self.parts = parts
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True
    def iter_content(self, size):
        yield from self.parts


def run(response, cancel=lambda: False, limit=1024):
    session = SimpleNamespace(get=lambda *a, **k: response)
    return list(http.iter_events(session, ['https://example.invalid'], time.monotonic() + 2,
        cancel, 'json', limit))


def test_completed_json_is_owned_and_response_closed():
    response = Response([b'{"ok":', b'true}'])
    events = run(response)
    assert [e[1] for e in events] == ['started', 'succeeded']
    assert events[-1][3]._content == b'{"ok":true}' and response.closed


def test_cancel_never_emits_success():
    state = [False]
    class Slow(Response):
        def iter_content(self, size):
            yield b'{}'
            state[0] = True
    response = Slow([])
    assert not any(row[1] == 'succeeded' for row in run(response, lambda: state[0]))
    assert response.closed


def test_oversize_and_invalid_json_not_complete():
    for parts in ([b'x' * 2048], [b'{broken']):
        response = Response(parts)
        assert run(response)[-1][1] == 'failed'
        assert response.closed


def test_error_status_is_not_a_search_result():
    response = Response([b'{}'])
    response.status_code = 429
    assert run(response)[-1][1] == 'failed'
    assert response.closed
