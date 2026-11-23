"""Observation-only coverage: simulated time is NOT a throughput/device claim."""
from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from test_share_stream_observations import stream
from test_ce_progressive_http import pipeline, wait_end, PAYLOAD


MIB = 1024**2


def run_blocks(monkeypatch, blocks=100, block_bytes=MIB, fetch_seconds=.5,
               write_seconds=.5, wait_seconds=.125, noisy=True, failure=None,
               broken_observer=False, cancel_after=None):
    clock = [100.0]
    rows, reads, writes, gates, reports, errors, released = [], [], [], [], [], [], []
    active = [False]
    monkeypatch.setattr(stream, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000))

    class Gate:
        def acquire(self, cancelled, initial):
            assert not active[0]
            gates.append(initial)
            clock[0] += wait_seconds
            active[0] = True
            return True

        def release(self):
            assert active[0]
            active[0] = False

    def observer(row):
        assert not active[0], 'Observation sink must stay outside the existing gate'
        if broken_observer:
            raise RuntimeError('https://secret.invalid/?account=private')
        rows.append(row)

    entry = SimpleNamespace(body={'size': blocks*block_bytes}, io_lock=Gate())
    owner = SimpleNamespace(segment_bytes=block_bytes, acquire=lambda *args: entry,
        release=lambda *args: released.append(True), session=lambda selected, *, cancelled: nullcontext(None),
        observation=lambda entry: dict(run='1'*16, http=3, transport='2'*64,
            request='3'*16, file='4'*64, gate=5), observer=observer, report=reports.append)
    handler = stream.Handler.__new__(stream.Handler)
    handler.server, handler.path, handler.connection = SimpleNamespace(owner=owner), '/secret', object()
    handler.headers = {}
    handler.cancelled = lambda: cancel_after is not None and len(writes) >= cancel_after
    handler.send_error = errors.append
    handler.response_headers = lambda *args: None

    def fetch(session, selected, offset, upper, failures):
        assert active[0] and failures == 0
        reads.append((offset, upper, failures))
        if noisy:
            for _ in range(6):
                handler.observe('retry', reason='read_resumed', retry=1, token='private')
        clock[0] += fetch_seconds
        if failure == 'fetch' and len(reads) == 80:
            raise RuntimeError('https://secret.invalid/?account=private')
        return bytes(upper-offset+1), 0

    def write(block):
        assert not active[0]
        writes.append(len(block))
        clock[0] += write_seconds
        if failure == 'write' and len(writes) == 80:
            handler.observation_delivered += len(block)//2
            raise RuntimeError('/private/account/cookie')
        handler.observation_delivered += len(block)
        return True

    handler.read_block, handler.write_block = fetch, write
    handler.serve()
    return SimpleNamespace(rows=rows, reads=reads, writes=writes, gates=gates,
        reports=reports, errors=errors, released=released)


def windows(result):
    return [row for row in result.rows if row.get('timing_scope') == 'block_cumulative'
            and row['phase'] == 'window']


def test_dense_initial_events_cannot_consume_65_second_window_or_terminal_slots(monkeypatch):
    result = run_blocks(monkeypatch)
    sampled = windows(result)
    assert len(sampled) == 13
    assert len(result.rows) == stream.OBSERVATION_LIMIT == 48
    assert sampled[-1]['monotonic_us']-100_000_000 >= 65_000_000
    assert all(b['monotonic_us']-a['monotonic_us'] >= 5_000_000
               for a, b in zip(sampled, sampled[1:]))
    assert result.rows[-1]['phase'] == 'end'
    assert result.rows[-1]['outcome'] == 'complete'
    assert result.rows[-1]['suppressed'] > 0
    assert result.rows[-1]['delivered'] == 100*MIB


def test_high_byte_count_does_not_end_time_coverage_and_counters_are_aligned(monkeypatch):
    result = run_blocks(monkeypatch, block_bytes=2*MIB)
    sampled = windows(result)
    assert any(row['offset'] > 64*MIB and row['wall_ms'] >= 60_000 for row in sampled)
    for row in sampled + [result.rows[-1]]:
        assert row['observation_begin_us'] == 100_000_000
        assert row['monotonic_us']-row['observation_begin_us'] == row['wall_ms']*1000
        assert row['wait_ms']+row['fetch_ms']+row['write_ms'] == row['wall_ms']
        assert row['bytes'] >= row['delivered']
        assert row['bytes']-row['delivered'] in (0, 2*MIB)
        assert row['transport'] == '2'*64 and row['request'] == '3'*16 and row['http'] == 3
    final = result.rows[-1]
    assert final['wait_ms'] == 12_500 and final['fetch_ms'] == final['write_ms'] == 50_000
    assert final['bytes'] == final['delivered'] == 200*MIB
    assert not any(secret in json.dumps(result.rows+result.reports)
                   for secret in ('secret', 'private', 'account=', '115cdn', '/stream/'))


def test_single_long_block_reports_only_when_existing_operations_return(monkeypatch):
    result = run_blocks(monkeypatch, blocks=1, fetch_seconds=80, write_seconds=11,
                        wait_seconds=0, noisy=False)
    sampled = windows(result)
    assert [row['monotonic_us'] for row in sampled] == [180_000_000, 191_000_000]
    assert sampled[0]['bytes'] == MIB and sampled[0]['delivered'] == 0
    assert sampled[0]['fetch_ms'] == 80_000 and sampled[0]['write_ms'] == 0
    assert sampled[1]['delivered'] == MIB and sampled[1]['write_ms'] == 11_000
    assert result.rows[-1]['wall_ms'] == 91_000


def test_short_request_has_no_fabricated_window_and_keeps_terminal_totals(monkeypatch):
    result = run_blocks(monkeypatch, blocks=1, noisy=False)
    assert not windows(result)
    assert [row['phase'] for row in result.rows] == ['begin', 'fetch_end', 'gate_wait',
                                                   'response', 'write_end', 'end']
    assert result.rows[-1]['bytes'] == result.rows[-1]['delivered'] == MIB


@pytest.mark.parametrize('failure,cancel_after', [('fetch', None), ('write', None), (None, 80)])
def test_late_failure_or_cancellation_retains_terminal_after_all_windows(monkeypatch, failure, cancel_after):
    result = run_blocks(monkeypatch, failure=failure, cancel_after=cancel_after)
    assert len(windows(result)) == 13
    assert len(result.rows) <= 48
    final = result.rows[-1]
    assert final['phase'] == 'end'
    assert final['outcome'] == ('failed' if failure else 'cancelled')
    assert final['delivered'] == (79*MIB if failure == 'fetch' else
                                  79*MIB+MIB//2 if failure == 'write' else 80*MIB)
    assert result.released == [True] and not result.errors
    assert 'secret' not in json.dumps(result.rows+result.reports)


def test_disabled_and_throwing_observation_leave_ranges_gate_retry_and_delivery_identical(monkeypatch):
    observed = run_blocks(monkeypatch)
    broken = run_blocks(monkeypatch, broken_observer=True)
    monkeypatch.setattr(stream.Handler, 'observe', lambda *args, **kwargs: None)
    disabled = run_blocks(monkeypatch)
    for result in (broken, disabled):
        for name in ('reads', 'writes', 'gates', 'reports', 'errors', 'released'):
            assert getattr(result, name) == getattr(observed, name)


@pytest.mark.parametrize('mode', ['normal', 'short_once', 'expired'])
def test_real_loopback_retry_and_exact_range_are_identical_with_observer_failure(mode):
    results = []
    for broken in (False, True):
        headers = []
        with pipeline(False, mode=mode, range_headers=headers, segment_bytes=256*1024) as (
                service, connect, calls, events, resolves, peak):
            if broken:
                def failed_sink(row):
                    raise RuntimeError('private observer failure')
                service.observer = failed_sink
            connection, response = connect('bytes=117-1048692')
            try:
                assert response.status == 206
                assert response.read() == PAYLOAD[117:1048693]
            finally:
                response.close()
                connection.close()
            if not broken:
                wait_end(events)
                assert events[-1]['outcome'] == 'complete'
            assert peak[0] == 1 and not service.producers
            results.append((list(calls), list(headers), len(resolves)))
    assert results[0] == results[1]
