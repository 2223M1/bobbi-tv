"""One body-window clock, with the actual frozen pre-change transport as control."""
from frozen_history import source_bytes
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end, PAYLOAD


BASE = 'e58718b783adb0803b0812db03bfd5d7f21d0b73'
CHUNK = 32768
DATA = bytes(range(256)) * 4096


@pytest.fixture(scope='module')
def frozen():
    source = source_bytes(BASE, 'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py')
    name = '_frozen_share_body_window'
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, '<frozen-e58718b-share-stream>', 'exec'), module.__dict__)
        yield module
    finally:
        sys.modules.pop(name, None)


def case(module, monkeypatch, attempts=None, grant_delay=0, body_delay=.01,
         contended=False, consume=None):
    """Actual read_block and chunk iterator; deterministic time, scripted IO only."""
    clock, calls, grants, closed, observations, read_lengths = [0.0], [], [], [], [], []
    attempts = list(attempts or [{}])
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    stopped = [False]

    def wait(delay):
        clock[0] += delay
        return stopped[0]

    def grant(**kwargs):
        clock[0] += grant_delay
        grants.append(kwargs)
        return 'https://fixture.invalid/file|User-Agent=fixture'

    class Response:
        def __init__(self, start, end, spec):
            self.start, self.end, self.spec = start, end, spec
            self.status_code = spec.get('status', 206)
            self.headers = {'Content-Range': 'bytes {}-{}/{}'.format(start, end, len(DATA)),
                            'Content-Length': str(end-start+1)}
            if spec.get('invalid'):
                self.headers[spec['invalid']] = 'invalid'
        def __enter__(self): return self
        def __exit__(self, *args): closed.append((self.start, self.end))
        def iter_content(self, requested):
            assert requested == CHUNK
            offset = self.start
            steps = self.spec.get('steps')
            if steps is None:
                steps = [(body_delay, min(CHUNK, self.end-pos+1))
                         for pos in range(offset, self.end+1, CHUNK)]
            for delay, value in steps:
                clock[0] += delay
                if isinstance(value, BaseException):
                    raise value
                if value == 'stop':
                    stopped[0] = True
                    value = CHUNK
                chunk = DATA[offset:min(offset+value, self.end+1)]
                offset += len(chunk)
                read_lengths.append(len(chunk))
                yield chunk

    class Session:
        def get(self, address, headers, **kwargs):
            spec = attempts[min(len(calls), len(attempts)-1)]
            start, end = map(int, headers['Range'][6:].split('-'))
            assert headers['User-Agent'] == 'fixture' and headers['Connection'] == 'close'
            assert kwargs == dict(stream=True, allow_redirects=False, timeout=(3.05, 10))
            calls.append((start, end))
            clock[0] += spec.get('connect', 0)
            if spec.get('connect_error'):
                raise OSError('connect')
            return Response(start, end, spec)

    entry = SimpleNamespace(body={'size': len(DATA)}, grant=grant,
        io_lock=SimpleNamespace(contended=lambda: contended, note_yield=lambda: None,
                                recently_yielded=lambda: False))
    handler = module.Handler.__new__(module.Handler)
    handler.server = SimpleNamespace(owner=SimpleNamespace(
        stopping=SimpleNamespace(wait=wait), report=lambda _: None))
    handler.cancelled = lambda: stopped[0]
    handler.observe = lambda phase, **fields: observations.append(dict(phase=phase, **fields))
    handler.diagnostic_timings = None
    result = SimpleNamespace(clock=clock, calls=calls, grants=grants, closed=closed,
        observations=observations, reads=read_lengths, result=None, error=None)
    try:
        result.result = handler.read_block(Session(), entry, 0, len(DATA)-1, 0, consume=consume)
    except Exception as error:
        result.error = error
    return result


@pytest.mark.parametrize('grant_delay,connect_delay', [(1.2, 0), (0, 1.2), (.6, .6)])
def test_slow_setup_does_not_spend_body_budget(monkeypatch, grant_delay, connect_delay):
    result = case(stream, monkeypatch, grant_delay=grant_delay,
                  attempts=[dict(connect=connect_delay)])
    assert result.error is None and result.result[1] == 0
    assert len(result.result[0]) == len(DATA)
    assert result.result[0] == DATA
    assert result.calls == [(0, len(DATA)-1)]
    assert not any(row.get('reason') == 'delivery_window' for row in result.observations)


@pytest.mark.parametrize('grant_delay,connect_delay', [(1.2, 0), (0, 1.2), (.6, .6)])
def test_frozen_source_is_a_failing_control_for_slow_setup(frozen, monkeypatch, grant_delay, connect_delay):
    result = case(frozen, monkeypatch, grant_delay=grant_delay,
                  attempts=[dict(connect=connect_delay)])
    assert result.error is None and result.result == (DATA[:CHUNK], 0)
    assert any(row.get('reason') == 'delivery_window' for row in result.observations)


@pytest.mark.parametrize('body_delay', [0, .125, .5, 1.25])
def test_zero_setup_keeps_frozen_body_boundaries(frozen, monkeypatch, body_delay):
    old = case(frozen, monkeypatch, body_delay=body_delay)
    new = case(stream, monkeypatch, body_delay=body_delay)
    assert new.error is old.error is None
    assert new.result == old.result and new.clock == old.clock
    assert new.calls == old.calls and new.observations == old.observations


def test_first_byte_wait_and_empty_chunks_still_consume_body_window(monkeypatch):
    for steps in ([(1.25, CHUNK)], [(.5, 0), (.5, 0), (.125, CHUNK)]):
        result = case(stream, monkeypatch, attempts=[dict(connect=1.2, steps=steps)])
        assert result.error is None and result.result == (DATA[:CHUNK], 0)
        assert result.observations[-1]['reason'] == 'delivery_window'
        assert result.clock[0] >= 2.325  # Soft threshold: only checked after a nonempty read returns.


@pytest.mark.parametrize('first', [dict(status=403, connect=1.2),
                                 dict(connect_error=True, connect=1.2)])
def test_setup_retry_before_valid_body_does_not_arm_clock(monkeypatch, first):
    result = case(stream, monkeypatch, attempts=[first, dict(connect=1.2)])
    assert result.error is None and result.result[1] == 1
    assert len(result.result[0]) == len(DATA)
    assert result.result[0] == DATA
    assert result.calls == [(0, len(DATA)-1), (0, len(DATA)-1)]


@pytest.mark.parametrize('renew', [False, True])
def test_retries_after_valid_body_do_not_reset_clock_and_keep_exact_suffix(monkeypatch, renew):
    attempts = [dict(steps=[(.25, CHUNK), (0, OSError('short'))])]
    if renew:
        attempts.append(dict(status=403, connect=.2))
    attempts.append(dict(connect=.4, steps=[(.125, CHUNK), (.125, CHUNK)]))
    result = case(stream, monkeypatch, attempts=attempts)
    assert result.error is None and result.result == (DATA[:2*CHUNK], 2 if renew else 1)
    assert result.calls == [(0, len(DATA)-1)] + [(CHUNK, len(DATA)-1)]*(2 if renew else 1)
    assert result.observations[-1]['reason'] == 'delivery_window'


def test_valid_empty_body_arms_clock_before_retry_without_any_accepted_byte(monkeypatch):
    result = case(stream, monkeypatch, attempts=[
        dict(connect=1.2, steps=[(.6, 0)]), dict(connect=.2)])
    assert result.error is None and result.result == (DATA[:CHUNK], 1)
    assert result.calls == [(0, len(DATA)-1), (0, len(DATA)-1)]
    assert result.observations[-1]['reason'] == 'delivery_window'


@pytest.mark.parametrize('invalid', ['Content-Range', 'Content-Length', 'Content-Encoding'])
def test_invalid_response_never_enters_body(monkeypatch, invalid):
    result = case(stream, monkeypatch, attempts=[dict(connect=2, invalid=invalid)])
    assert isinstance(result.error, ValueError) and str(result.error) == 'SHARE_RANGE_IDENTITY'
    assert not result.reads and len(result.calls) == 1


def test_contention_still_yields_first_accepted_prefix(monkeypatch):
    result = case(stream, monkeypatch, attempts=[dict(connect=1.2)], contended=True)
    assert result.error is None and result.result == (DATA[:CHUNK], 0)
    assert result.observations[-1]['phase'] == 'yield'
    assert 'reason' not in result.observations[-1]


def test_cancellation_still_wins_before_accepting_late_chunk(monkeypatch):
    result = case(stream, monkeypatch, attempts=[dict(connect=1.2, steps=[(.1, 'stop')])])
    assert isinstance(result.error, OSError) and str(result.error) == 'SHARE_STOPPED'
    assert len(result.calls) == 1 and len(result.closed) == 1


@pytest.mark.parametrize('attempt', [dict(connect_error=True), dict(steps=[(0, OSError('read'))])])
def test_four_failures_keep_existing_per_block_budget(monkeypatch, attempt):
    result = case(stream, monkeypatch, attempts=[attempt]*4)
    assert isinstance(result.error, OSError) and str(result.error) == 'SHARE_READ_UNAVAILABLE'
    assert len(result.calls) == 4


def test_progressive_consumer_remains_outside_block_window(monkeypatch):
    accepted = []
    result = case(stream, monkeypatch, attempts=[dict(connect=1.2)], body_delay=.125,
                  consume=lambda chunk: accepted.append(chunk) or True)
    assert result.error is None and result.result == (len(DATA), 0)
    assert b''.join(accepted) == DATA and len(result.calls) == 1


def test_real_http_slow_headers_are_not_an_early_body_cutoff(monkeypatch):
    # The upstream's existing header pause is deterministic; no throughput claim.
    from threading import Event
    from test_share_stream_block_startup import background_fetch
    entered, release = Event(), Event()
    original = stream.Handler.diagnostic_call

    def delay_headers(self, key, function, *args, **kwargs):
        if key == 'connect_us':
            from threading import Timer
            timer = Timer(1.2, release.set)
            timer.start()
            try:
                return original(self, key, function, *args, **kwargs)
            finally:
                timer.cancel()
        return original(self, key, function, *args, **kwargs)

    monkeypatch.setattr(stream.Handler, 'diagnostic_call', delay_headers)
    with pipeline(False, payload=PAYLOAD[:CHUNK*4], header_pause=(entered, release)) as (
            _, connect, calls, events, _, peak):
        worker, results, errors, done = background_fetch(connect)
        try:
            assert entered.wait(2) and done.wait(5)
            assert not errors and results == [(200, PAYLOAD[:CHUNK*4])]
        finally:
            release.set()
            worker.join(5)
        wait_end(events)
        assert calls == [(0, CHUNK*4-1)] and peak[0] == 1
        assert not any(row.get('reason') == 'delivery_window' for row in events)
