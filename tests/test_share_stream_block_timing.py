"""Explicit ordinary-block timing: policy parity, not a device speed claim."""
from frozen_history import source_bytes
from contextlib import nullcontext
from http.client import HTTPConnection, IncompleteRead
import json
from pathlib import Path
import socket
import sys
from threading import Event
import time
from types import ModuleType, SimpleNamespace

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end, PAYLOAD
from test_share_stream_block_startup import background_fetch, fetch
from test_accounts import credential, logged_in

MIB = 1024**2
DIAGNOSTIC = dict(mode='block_timing', seconds=60)
TIMINGS = {'grant_us', 'connect_us', 'read_wait_us', 'socket_send_us',
           'consumer_cancel_calls', 'consumer_cancel_us'}


@pytest.fixture(scope='module')
def baseline():
    # Mainline integration of 288b2c; its share_stream blob is byte-identical.
    # Run the retained original mainline blob, even in a shallow clean checkout.
    revision = '7220670f1ac3dda3bfd8e8e182c778311b14be48'
    source = source_bytes(revision, 'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py')
    name = '_frozen_block_timing_baseline'
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, '<frozen-block-timing-baseline>', 'exec'), module.__dict__)
        yield module
    finally:
        sys.modules.pop(name, None)


def simulated(module, monkeypatch, diagnostic=None, size=130*MIB, delay=0,
              noisy=False, broken_observer=False):
    """Run real serve/read_block/write_block using controlled IO, not fake policy."""
    clock, rows, ranges, checks, sent = [100.0], [], [], [], []
    active, closed = [False], []
    module_time = SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000)
    monkeypatch.setattr(module, 'time', module_time)
    handler = module.Handler.__new__(module.Handler)

    class Gate:
        def acquire(self, cancelled, initial):
            assert not active[0]
            active[0] = True
            clock[0] += .003
            return True
        def release(self): active[0] = False
        def contended(self): return False
        def note_yield(self): pass

    class Response:
        status_code = 206
        def __init__(self, start, end):
            self.remaining = end-start+1
            self.headers = {'Content-Range': 'bytes {}-{}/{}'.format(start, end, size),
                            'Content-Length': str(self.remaining)}
            self.raw = self
        def read1(self, requested, decode_content):
            assert requested == 32768 and decode_content is False
            clock[0] += delay or .00001
            length = min(requested, self.remaining)
            self.remaining -= length
            return b'x'*length
        def __enter__(self): return self
        def __exit__(self, *args): closed.append(self.remaining)

    class Session:
        def get(self, address, headers, **kwargs):
            assert active[0] and headers['Connection'] == 'close'
            assert kwargs == dict(stream=True, allow_redirects=False, timeout=(3.05, 10))
            ranges.append(headers['Range'])
            start, end = map(int, headers['Range'][6:].split('-'))
            clock[0] += .002
            if noisy:
                for _ in range(20):
                    handler.observe('retry', reason='read_resumed', retry=1, token='private')
            return Response(start, end)

    class Connection:
        def settimeout(self, value): pass
        def send(self, value):
            assert not active[0] and closed, 'Upstream must close before downstream write'
            sent.append(bytes(value))
            clock[0] += .00001
            return len(value)

    def grant():
        clock[0] += .001
        return 'https://secret.invalid/file|User-Agent=private'
    entry = SimpleNamespace(body={'size': size}, io_lock=Gate(), grant=grant,
                            diagnostic=diagnostic)
    def observer(row):
        assert not active[0]
        if broken_observer: raise RuntimeError('https://secret.invalid/?account=private')
        rows.append(row)
    def cancelled():
        checks.append(clock[0])
        clock[0] += .00001
        return False
    owner = SimpleNamespace(segment_bytes=64*MIB, acquire=lambda *args: entry,
        # The frozen baseline opens an unbound session; current product
        # selects the reader using the already admitted entry.
        release=lambda *args: None, session=lambda selected=None, *, cancelled=None: nullcontext(Session()),
        observation=lambda selected: dict(http=1), observer=observer, report=lambda _: None)
    handler.server, handler.path, handler.connection = SimpleNamespace(owner=owner), '/secret', Connection()
    handler.headers = {}
    handler.cancelled, handler.response_headers = cancelled, lambda *args: None
    handler.send_error = lambda status: pytest.fail('Unexpected response {}'.format(status))
    handler.serve()
    return SimpleNamespace(rows=rows, ranges=ranges, checks=checks,
        payload=b''.join(sent), closed=closed, handler=handler)


@pytest.mark.parametrize('size,delay', [(130*MIB, 0), (4*MIB, .2)])
def test_actual_baseline_and_timing_have_identical_ranges_prefixes_and_cancel_checks(
        monkeypatch, baseline, size, delay):
    old = simulated(baseline, monkeypatch, size=size, delay=delay)
    ordinary = simulated(stream, monkeypatch, size=size, delay=delay)
    timed = simulated(stream, monkeypatch, diagnostic=DIAGNOSTIC, size=size, delay=delay)
    for candidate in (ordinary, timed):
        assert candidate.ranges == old.ranges
        assert candidate.payload == old.payload == b'x'*size
        assert candidate.closed == old.closed
        assert candidate.checks == old.checks
    assert not hasattr(ordinary.handler, 'diagnostic_timings')
    assert not any(TIMINGS & row.keys() for row in old.rows + ordinary.rows)
    assert TIMINGS <= timed.rows[-1].keys()
    assert timed.rows[-1]['consumer_cancel_calls'] == len(timed.checks)
    assert timed.rows[-1]['consumer_cancel_us'] > 0
    assert all(timed.rows[-1][key] > 0 for key in ('grant_us', 'connect_us', 'read_wait_us', 'socket_send_us'))
    assert not any(key.startswith('producer_') for row in timed.rows for key in row)
    if not delay:
        assert timed.ranges == ['bytes=0-8388607', 'bytes=8388608-16777215',
            'bytes=16777216-33554431', 'bytes=33554432-67108863',
            'bytes=67108864-134217727', 'bytes=134217728-136314879']
    else:
        assert all(remaining > 0 for remaining in timed.closed[:-1])
        assert any(row.get('reason') == 'delivery_window' for row in timed.rows)


def test_windows_remain_bounded_cumulative_and_observer_failure_never_changes_policy(monkeypatch):
    observed = simulated(stream, monkeypatch, diagnostic=DIAGNOSTIC, size=8*MIB, delay=.2, noisy=True)
    broken = simulated(stream, monkeypatch, diagnostic=DIAGNOSTIC, size=8*MIB, delay=.2,
                       noisy=True, broken_observer=True)
    assert observed.ranges == broken.ranges and observed.payload == broken.payload
    assert observed.checks == broken.checks and observed.closed == broken.closed
    windows = [row for row in observed.rows if row['phase'] == 'window']
    assert 8 <= len(windows) <= 13 and len(observed.rows) <= 48
    assert observed.rows[-1]['phase'] == 'end' and observed.rows[-1]['suppressed'] > 0
    assert all(row['timing_scope'] == 'block_cumulative' and TIMINGS <= row.keys() for row in windows)
    assert all(b['monotonic_us']-a['monotonic_us'] >= 5_000_000 for a, b in zip(windows, windows[1:]))
    for key in TIMINGS:
        assert all(b[key] >= a[key] for a, b in zip(windows, windows[1:]))
    assert not any(secret in json.dumps(observed.rows) for secret in ('secret', 'private', 'account=', 'https://'))


@pytest.mark.parametrize('mode', ['normal', 'short_once', 'expired', 'chunked'])
def test_real_http_default_and_timing_bytes_ranges_retry_and_identity_match(mode):
    results = []
    for diagnostic in (None, DIAGNOSTIC):
        headers = []
        with pipeline(False, mode=mode, diagnostic=diagnostic, range_headers=headers,
                      segment_bytes=256*1024) as (service, connect, calls, rows, resolves, peak):
            assert fetch(connect, 'bytes=117-1048692') == (206, PAYLOAD[117:1048693])
            wait_end(rows)
            assert peak[0] == 1 and not service.producers and not service.progressive
            assert rows[-1]['outcome'] == 'complete'
            assert (TIMINGS <= rows[-1].keys()) is (diagnostic is not None)
            results.append((calls[:], headers[:], len(resolves)))
    assert results[0] == results[1]


def test_real_http_keeps_eight_mib_floor_even_if_owner_default_is_progressive():
    payload = PAYLOAD*3
    results = []
    for progressive, diagnostic in ((False, None), (False, DIAGNOSTIC), (True, DIAGNOSTIC)):
        with pipeline(progressive, payload=payload, diagnostic=diagnostic) as (
                service, connect, calls, rows, _, _):
            assert fetch(connect, 'bytes=0-9437183') == (206, payload[:9*MIB])
            wait_end(rows)
            assert calls == [(0, 8*MIB-1), (8*MIB, 9*MIB-1)]
            assert next(row for row in rows if row['phase'] == 'response')['first_block_bytes'] == 8*MIB
            assert service.progressive is progressive and not service.producers
            results.append(calls[:])
    assert results[0] == results[1] == results[2]


@pytest.mark.parametrize('mode', ['wrong_range', 'wrong_length', 'encoding', 'overflow'])
def test_real_http_invalid_upstream_cannot_become_diagnostic_media(mode):
    with pipeline(False, mode=mode, diagnostic=DIAGNOSTIC) as (_, connect, calls, rows, _, _):
        assert fetch(connect, 'bytes=17-99999')[0] == 503
        wait_end(rows)
        assert calls == [(17, 99999)]
        assert rows[-1]['delivered'] == 0 and rows[-1]['outcome'] == 'failed'
        assert TIMINGS <= rows[-1].keys()


@pytest.mark.parametrize('diagnostic,signal', [(None, 'logout'), (None, 'aba')] +
                         [(DIAGNOSTIC, signal) for signal in ('expire', 'revoke', 'logout', 'aba')])
def test_real_http_inflight_authority_change_never_delivers_stale_prefix(tmp_path, diagnostic, signal):
    manager, scope = logged_in(tmp_path)
    paused, resume = Event(), Event()
    with pipeline(False, diagnostic=diagnostic, body_pause=(128*1024, paused, resume),
                  account=manager, scope=scope) as (service, connect, calls, rows, _, _):
        worker, results, errors, done = background_fetch(connect)
        try:
            assert paused.wait(2)
            entry = next(iter(service.records.values()))
            if signal == 'expire': entry.diagnostic_deadline = time.monotonic()-1
            elif signal == 'revoke': entry.revoke()
            else:
                service.unsubscribe()  # Still require live scope comparison if event delivery is absent.
                logged_out = manager.logout(scope)
                if signal == 'aba':
                    current = manager.install(credential(), logged_out)
                    assert current['account_id'] == scope['account_id'] and current['epoch'] > scope['epoch']
            resume.set()
            assert done.wait(4)
            wait_end(rows)
            assert rows[-1]['delivered'] == 0 and rows[-1]['outcome'] != 'complete'
            if diagnostic is not None:
                assert rows[-1]['consumer_cancel_calls'] > 0
            assert len(calls) == 1
            assert all(status >= 400 for status, _ in results)
            assert all(isinstance(error, (ConnectionError, OSError)) for error in errors)
            assert fetch(connect, 'bytes=0-1')[0] == (404 if signal in ('expire', 'revoke') else 503)
            assert len(calls) == 1
        finally:
            resume.set()
            worker.join(5)


def test_real_http_half_close_is_not_revocation():
    paused, resume = Event(), Event()
    with pipeline(False, diagnostic=DIAGNOSTIC, body_pause=(128*1024, paused, resume)) as (
            service, connect, _, rows, _, _):
        # A block sends headers only after fetching. Half-close the request
        # socket directly while the upstream is paused, before getresponse().
        entry = next(iter(service.records.values()))
        connection = HTTPConnection('127.0.0.1', service.server.server_port, timeout=8)
        try:
            connection.request('GET', '/stream/{}/video.mkv'.format(entry.token))
            assert paused.wait(2)
            connection.sock.shutdown(socket.SHUT_WR)
            resume.set()
            response = connection.getresponse()
            assert response.status == 200 and response.read() == PAYLOAD
            response.close()
        finally:
            resume.set()
            connection.close()
        wait_end(rows)
        assert rows[-1]['outcome'] == 'complete' and rows[-1]['cancel'] == 'none'


@pytest.mark.parametrize('point', ['after_fetch', 'after_write'])
@pytest.mark.parametrize('signal', ['expire', 'revoke'])
def test_completed_prefix_still_respects_before_send_and_before_next_fetch(monkeypatch, point, signal):
    method = 'read_block' if point == 'after_fetch' else 'write_block'
    original = getattr(stream.Handler, method)
    def change(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if signal == 'expire': self.entry.diagnostic_deadline = time.monotonic()-1
        else: self.entry.revoke()
        return result
    monkeypatch.setattr(stream.Handler, method, change)
    with pipeline(False, diagnostic=DIAGNOSTIC, segment_bytes=256*1024) as (
            _, connect, calls, rows, _, _):
        try:
            connection, response = connect()
        except (ConnectionError, OSError):
            assert point == 'after_fetch'
        else:
            try:
                if point == 'after_write':
                    with pytest.raises(IncompleteRead) as caught: response.read()
                    assert caught.value.partial == PAYLOAD[:256*1024]
                else:
                    assert response.status == 503
                    response.read()
            finally:
                response.close()
                connection.close()
        wait_end(rows)
        assert calls == [(0, 256*1024-1)]
        assert rows[-1]['delivered'] == (0 if point == 'after_fetch' else 256*1024)
        assert rows[-1]['outcome'] != 'complete'


def test_slow_trickle_uses_existing_real_deadline_and_does_not_extend_on_reads():
    began = time.monotonic()
    with pipeline(False, mode='trickle', delay=.004, payload=PAYLOAD[:800],
                  diagnostic=dict(DIAGNOSTIC, seconds=1)) as (service, connect, calls, rows, _, _):
        assert fetch(connect)[0] == 503
        wait_end(rows)
        assert rows[-1]['cancel'] == 'diagnostic_expired' and rows[-1]['delivered'] == 0
        assert len(calls) == 1 and not service.producers
        assert time.monotonic()-began < 2.5


def test_diagnostic_registration_is_strict_bounded_and_never_rearmed():
    assert stream.checked_diagnostic(DIAGNOSTIC) == DIAGNOSTIC
    for invalid in (dict(DIAGNOSTIC, seconds=61), dict(DIAGNOSTIC, seconds=0),
                    dict(DIAGNOSTIC, seconds=True), dict(DIAGNOSTIC, sample_ms=1),
                    dict(mode='block_timing_extra', seconds=60)):
        with pytest.raises(ValueError, match='SHARE_DIAGNOSTIC_INVALID'):
            stream.checked_diagnostic(invalid)
    with pipeline(False, diagnostic=DIAGNOSTIC) as (service, _, _, _, resolves, _):
        entry = next(iter(service.records.values()))
        deadline = entry.diagnostic_deadline
        service.register_diagnostic(entry.body, None, DIAGNOSTIC)
        assert entry.diagnostic_deadline == deadline and not resolves
        with pytest.raises(ValueError, match='SHARE_REQUEST_RETARGETED'):
            service.register_diagnostic(entry.body, None, dict(DIAGNOSTIC, seconds=59))
        service.register(dict(entry.body, request_id='b'*32))
        ordinary = service.records['b'*32]
        assert ordinary.diagnostic is None and not service.progressive


def test_timing_receipt_is_explicit_revision_twelve_and_exact_mode_duration(tmp_path):
    from test_ce2039_diagnostic_log_probe import receipt, scope_for
    value = receipt()
    value.update(tool_revision=12, route='sharestream-block-timing', transport_diagnostic=dict(DIAGNOSTIC))
    assert scope_for(tmp_path, value)['route'] == 'sharestream-block-timing'
    for change in ({'tool_revision': 11}, {'transport_diagnostic': dict(mode='block_startup_1m', seconds=60)},
                   {'transport_diagnostic': dict(DIAGNOSTIC, seconds=59)}):
        with pytest.raises(ValueError, match='DIAGNOSTIC_RECEIPT_INVALID'):
            scope_for(tmp_path, dict(value, **change))
