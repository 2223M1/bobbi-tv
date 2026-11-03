import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace
from threading import BoundedSemaphore, Event
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_http_test',
    ROOT / 'addons/plugin.video.bobbi/lib/clients/portable_http.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)


@pytest.fixture(autouse=True)
def bounded_test_slots(monkeypatch):
    slots = BoundedSemaphore(4)
    monkeypatch.setattr(http, '_slot', lambda key=None: SimpleNamespace(release=slots.release)
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


def test_next_query_uses_released_slot_while_caller_processes_previous_response():
    release, next_started = Event(), Event()
    def get(url, **options):
        ordinal = int(url.rsplit('/', 1)[1])
        if ordinal == 4:
            next_started.set()
        if ordinal != 0:
            assert release.wait(2)
        return Response([b'{}'])
    events = http.iter_events(SimpleNamespace(get=get),
        ['https://example.invalid/'+str(n) for n in range(5)],
        time.monotonic()+3, lambda: False, 'json', 1024)
    try:
        first = next(row for row in events if row[1] == 'succeeded')
        assert first[0] == 0
        # The consumer is busy transforming the first result: it does not
        # request another iterator event. IO should already reuse its slot.
        assert next_started.wait(.3)
    finally:
        release.set()
        events.close()


@pytest.mark.parametrize('failure_stage', ['constructor', 'start'])
def test_replacement_start_failure_does_not_hide_completed_response(monkeypatch, failure_stage):
    release = Event()
    original = http.Thread
    admission = http._slot
    counts = {'acquired': 0, 'released': 0}
    def slot(key=None):
        lease = admission()
        if lease is None:
            return None
        counts['acquired'] += 1
        def relinquish():
            counts['released'] += 1
            lease.release()
        return SimpleNamespace(release=relinquish)
    monkeypatch.setattr(http, '_slot', slot)
    class Thread(original):
        def __init__(self, **kwargs):
            if failure_stage == 'constructor' and kwargs['args'][0] == 4:
                raise RuntimeError('replacement unavailable')
            super().__init__(**kwargs)
        def start(self):
            if failure_stage == 'start' and self._args[0] == 4:
                raise RuntimeError('replacement unavailable')
            return super().start()
    monkeypatch.setattr(http, 'Thread', Thread)
    def get(url, **options):
        if not url.endswith('/0'):
            assert release.wait(2)
        return Response([b'{}'])
    events = http.iter_events(SimpleNamespace(get=get),
        ['https://example.invalid/'+str(n) for n in range(5)],
        time.monotonic()+3, lambda: False, 'json', 1024)
    try:
        first = next(row for row in events if row[1] == 'succeeded')
        assert first[0] == 0 and first[3]._content == b'{}'
        release.set()
        with pytest.raises(RuntimeError, match='replacement unavailable'):
            next(events)
    finally:
        release.set()
        events.close()
    assert counts['acquired'] == counts['released'] == 5


@pytest.mark.parametrize('expiry', [False, True])
def test_stop_during_refill_does_not_publish_older_success(monkeypatch, expiry):
    release, cancelled = Event(), Event()
    counts = {'acquired': 0, 'released': 0, 'attempted': 0}
    now = [0.0]
    monkeypatch.setattr(http, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def relinquish():
        counts['released'] += 1
    def slot(key=None):
        counts['attempted'] += 1
        if counts['attempted'] == 5:
            now[0] = 10.0 if expiry else 0.0
            if not expiry:
                cancelled.set()
            release.set()
            return None
        counts['acquired'] += 1
        return SimpleNamespace(release=relinquish)
    monkeypatch.setattr(http, '_slot', slot)
    def get(url, **options):
        if not url.endswith('/0'):
            assert release.wait(2)
        return Response([b'{}'])
    rows = list(http.iter_events(SimpleNamespace(get=get),
        ['https://example.invalid/'+str(n) for n in range(5)],
        10.0, cancelled.is_set, 'json', 1024))
    assert not any(row[1] == 'succeeded' for row in rows)
    assert counts['acquired'] == counts['released'] == 4


def test_thread_constructor_failure_releases_admission(monkeypatch):
    released = []
    monkeypatch.setattr(http, '_slot', lambda key=None: SimpleNamespace(release=lambda: released.append(True)))
    def fail(**options):
        raise RuntimeError('constructor unavailable')
    monkeypatch.setattr(http, 'Thread', fail)
    with pytest.raises(RuntimeError, match='constructor unavailable'):
        run(Response([b'{}']))
    assert released == [True]
