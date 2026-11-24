"""Nested cancellation diagnostics preserve live authorization and socket policy."""
from frozen_history import source_bytes
from pathlib import Path
import sys
from threading import Event, Thread
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_core import share_stream as stream
from test_account_streams import body
from test_accounts import credential, logged_in
from test_ce_progressive_http import pipeline, PAYLOAD, wait_end
from test_share_stream_block_startup import fetch


def counters():
    return dict(consumer_cancel_calls=0, consumer_cancel_us=0,
                account_guard_calls=0, account_guard_us=0,
                socket_probe_calls=0, socket_probe_us=0, cancel_timing_failures=0)


@pytest.fixture(scope='module')
def frozen():
    source = source_bytes('629597c7c6655a992438f1903e3066dfa72cf61a', 'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py')
    name = '_frozen_cancel_timing_baseline'
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, '<frozen-cancellation-baseline>', 'exec'), module.__dict__)
        yield module
    finally:
        sys.modules.pop(name, None)


def cancellation(module, monkeypatch, case, measured=False):
    calls = []
    account = SimpleNamespace(is_current=lambda scope: calls.append(('account', scope)) or case != 'revoked')
    entry = module.Binding(body(), lambda: '', lambda value: True, account=account, scope={'fixed': 1})
    entry.diagnostic_expired = lambda: calls.append(('expired',)) or case == 'expired'
    handler = module.Handler.__new__(module.Handler)
    handler.entry = entry
    handler.disconnected = case == 'disconnected'
    handler.server = SimpleNamespace(owner=SimpleNamespace(stopping=SimpleNamespace(
        is_set=lambda: calls.append(('stopping',)) or case == 'stopping')))
    class Connection:
        def getsockopt(self, *args):
            calls.append(('getsockopt', args))
            return int(case == 'socket_error')
        def recv(self, *args):
            calls.append(('recv', args))
            if case == 'recv_error':
                raise OSError('private exception must not enter metrics')
            return b''  # A receive-half-close is not cancellation.
    handler.connection = Connection()
    def select(read, write, error, timeout):
        calls.append(('select', timeout))
        if case == 'select_error':
            raise ValueError('invalid descriptor')
        return ([handler.connection] if case in ('readable', 'recv_error') else [], [], [])
    monkeypatch.setattr(module.select, 'select', select)
    rows = counters()
    if measured:
        handler.measure_cancel = lambda prefix, check, *args: stream.measure_cancellation(rows, prefix, check, *args)
    result = handler.cancelled()
    return result, getattr(handler, 'cancel_reason', None), calls, rows


@pytest.mark.parametrize('case', ['current', 'expired', 'revoked', 'stopping', 'disconnected',
                                  'socket_error', 'readable', 'recv_error', 'select_error'])
def test_frozen_checks_order_and_results_are_identical(monkeypatch, frozen, case):
    old = cancellation(frozen, monkeypatch, case)
    ordinary = cancellation(stream, monkeypatch, case)
    timed = cancellation(stream, monkeypatch, case, True)
    assert old[:3] == ordinary[:3] == timed[:3]
    assert ordinary[3] == counters()
    assert timed[3]['account_guard_calls'] == sum(call[0] == 'account' for call in timed[2])
    assert timed[3]['socket_probe_calls'] == sum(call[0] == 'getsockopt' for call in timed[2])


def test_wall_and_cpu_are_distinct_nested_measurements(monkeypatch):
    wall, cpu = iter([10.0, 10.025]), iter([1000, 9000])
    monkeypatch.setattr(stream, 'time', SimpleNamespace(monotonic=lambda: next(wall), thread_time_ns=lambda: next(cpu)))
    rows, calls = counters(), []
    token = object()
    assert stream.measure_cancellation(rows, 'account_guard', lambda: calls.append(1) or token) is token
    assert calls == [1] and rows['account_guard_calls'] == 1
    assert rows['account_guard_us'] == pytest.approx(25000, abs=1)
    assert rows['account_guard_cpu_us'] == 8 and rows['cancel_timing_failures'] == 0


@pytest.mark.parametrize('clock_kind', ['missing_cpu', 'failed_cpu', 'failed_wall'])
@pytest.mark.parametrize('raises', [False, True])
def test_optional_clock_failure_cannot_change_return_or_original_exception(monkeypatch, clock_kind, raises):
    def broken(): raise RuntimeError('private clock details')
    fake = SimpleNamespace(monotonic=broken if clock_kind == 'failed_wall' else lambda: 10.0)
    if clock_kind != 'missing_cpu':
        fake.thread_time_ns = broken if clock_kind == 'failed_cpu' else lambda: 1000
    monkeypatch.setattr(stream, 'time', fake)
    rows, calls, original = counters(), [], OSError('original authorization failure')
    def check():
        calls.append(1)
        if raises: raise original
        return False
    if raises:
        with pytest.raises(OSError) as caught:
            stream.measure_cancellation(rows, 'account_guard', check)
        assert caught.value is original
    else:
        assert stream.measure_cancellation(rows, 'account_guard', check) is False
    assert calls == [1] and rows['account_guard_calls'] == 1
    if clock_kind in ('missing_cpu', 'failed_cpu'):
        assert 'account_guard_cpu_us' not in rows
    assert rows['cancel_timing_failures'] == (0 if clock_kind == 'missing_cpu' else 2)
    assert 'private' not in str(stream.observation_fields(rows))


def test_measured_account_guard_still_waits_for_live_lock_and_rejects_aba(tmp_path):
    account, scope = logged_in(tmp_path)
    entry = stream.Binding(body(), lambda: '', lambda value: True, account=account, scope=scope)
    rows, entered, finished, results = counters(), Event(), Event(), []
    original = entry._account_current_guard
    def guard():
        entered.set()
        return original()
    entry._account_current_guard = guard
    measure = lambda prefix, check, *args: stream.measure_cancellation(rows, prefix, check, *args)
    def worker():
        try: results.append(entry.cancelled(measure))
        finally: finished.set()
    with account.lock:
        thread = Thread(target=worker)
        thread.start()
        assert entered.wait(2) and not finished.is_set()
    thread.join(2)
    assert not thread.is_alive() and results == [False]
    # Same account identity restored after logout is a new generation.
    logged_out = account.logout(scope)
    account.install(credential(), logged_out)
    assert entry.cancelled(measure) is True
    assert rows['account_guard_calls'] == 2


@pytest.mark.parametrize('values', [(10.0, 9.0), (0.0, 1e308)])
@pytest.mark.parametrize('raises', [False, True])
def test_invalid_derived_clock_interval_cannot_override_check(monkeypatch, values, raises):
    ticks = iter(values)
    monkeypatch.setattr(stream, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    rows, original = counters(), OSError('original failure')
    def check():
        if raises: raise original
        return True
    if raises:
        with pytest.raises(OSError) as caught:
            stream.measure_cancellation(rows, 'socket_probe', check)
        assert caught.value is original
    else:
        assert stream.measure_cancellation(rows, 'socket_probe', check) is True
    assert rows['socket_probe_us'] == 0 and rows['cancel_timing_failures'] == 1


@pytest.mark.parametrize('diagnostic', [None, dict(mode='block_timing', seconds=60)])
def test_real_http_only_opted_in_block_timing_exports_nested_counters(diagnostic, tmp_path):
    account, scope = logged_in(tmp_path)
    with pipeline(False, diagnostic=diagnostic, account=account, scope=scope) as (
            service, connect, calls, events, _, _):
        assert fetch(connect) == (200, PAYLOAD)
        wait_end(events)
        assert events[-1]['outcome'] == 'complete'
        if diagnostic is None:
            assert not any(set(counters()) & row.keys() for row in events)
        else:
            last = events[-1]
            assert last['account_guard_calls'] == last['consumer_cancel_calls']
            assert last['socket_probe_calls'] == last['consumer_cancel_calls']
            assert last['cancel_timing_failures'] == 0
            assert last['consumer_cancel_us'] >= last['account_guard_us']
            assert last['consumer_cancel_us'] >= last['socket_probe_us']
            assert last['consumer_cancel_cpu_us'] >= last['account_guard_cpu_us']
        assert service.progressive is False
