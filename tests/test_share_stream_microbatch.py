"""Explicit diagnostic microbatch contracts; no device or CDN access."""
from pathlib import Path
import sys
from http.client import IncompleteRead

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import share_stream as stream

MICRO = {'mode': 'open_range_microbatch', 'seconds': 60}


def test_microbatch_is_explicit_while_original_control_remains_distinct():
    assert stream.checked_diagnostic(MICRO) == MICRO
    assert stream.checked_diagnostic({'mode': 'open_range', 'seconds': 60}) == {
        'mode': 'open_range', 'seconds': 60}


def test_first_microbatch_prefix_never_waits_to_fill(monkeypatch):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'first')
    monkeypatch.setattr(queue.condition, 'wait', lambda *_: pytest.fail('First prefix delayed'))
    assert queue.get(lambda: False) == b'first'


def test_subsequent_microbatch_has_one_fixed_two_ms_deadline(monkeypatch):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'a'); assert queue.get(lambda: False) == b'a'
    queue.put(b'b')
    now, waits = [10.0], []
    monkeypatch.setattr(stream.time, 'monotonic', lambda: now[0])
    def wait(seconds):
        waits.append(seconds)
        assert len(waits) <= 3, 'A new fragment must not reset the two ms window'
        now[0] = min(10.002, now[0] + .0007)
        queue.put(bytes([ord('b') + len(waits)]))
    monkeypatch.setattr(queue.condition, 'wait', wait)
    assert queue.get(lambda: False) == b'bcde'
    assert waits == pytest.approx([.002, .0013, .0006])
    assert now[0] == pytest.approx(10.002)


@pytest.mark.parametrize('terminal', ['cancel', 'stop', 'error', 'eof'])
def test_terminal_during_microbatch_does_not_wait_out_the_window(monkeypatch, terminal):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'a'); assert queue.get(lambda: False) == b'a'
    queue.put(b'b')
    now, cancelled, waits = [10.0], [False], []
    error = OSError('SHARE_RANGE_OVERFLOW')
    monkeypatch.setattr(stream.time, 'monotonic', lambda: now[0])
    def wait(seconds):
        waits.append(seconds)
        assert len(waits) == 1, 'Terminal state must interrupt the collection window'
        now[0] += .0002
        if terminal == 'cancel': cancelled[0] = True
        elif terminal == 'stop': queue.stop()
        elif terminal == 'error': queue.finish(error)
        else: queue.finish()
    monkeypatch.setattr(queue.condition, 'wait', wait)
    if terminal == 'error':
        with pytest.raises(OSError) as caught: queue.get(lambda: cancelled[0])
        assert caught.value is error and queue.gets == 1
    else:
        assert queue.get(lambda: cancelled[0]) == (b'b' if terminal == 'eof' else None)
    assert len(waits) == 1 and now[0] < 10.002


def test_full_batch_and_finite_eof_return_without_added_wait(monkeypatch):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'a'); assert queue.get(lambda: False) == b'a'
    queue.put(b'b' * (stream.DELIVERY_CHUNK_BYTES + 1))
    monkeypatch.setattr(queue.condition, 'wait', lambda *_: pytest.fail('Already full/finished batch delayed'))
    assert queue.get(lambda: False) == b'b' * stream.DELIVERY_CHUNK_BYTES
    queue.finish()
    assert queue.get(lambda: False) == b'b' and queue.get(lambda: False) is None
    assert queue.limit == 8 * 1024**2


def test_ordinary_queue_keeps_immediate_subsequent_delivery(monkeypatch):
    queue = stream.ByteQueue()
    monkeypatch.setattr(queue.condition, 'wait', lambda *_: pytest.fail('Control path changed'))
    for byte in (b'a', b'b'):
        queue.put(byte)
        assert queue.get(lambda: False) == byte


@pytest.mark.parametrize('mode', ['open_range', 'open_range_microbatch'])
@pytest.mark.parametrize('requested', [None, 'bytes=117-', 'bytes=117-524404'])
def test_exact_wire_bytes_ranges_and_sparse_diagnostic_metrics(mode, requested):
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    headers = []
    with pipeline(False, diagnostic={'mode': mode, 'seconds': 60}, range_headers=headers,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (service, connect, calls, rows, _, peak):
        connection, response = connect(requested)
        try:
            start, end, _ = stream.byte_range(requested, len(PAYLOAD))
            assert response.read() == PAYLOAD[start:end+1]
        finally:
            response.close(); connection.close()
        wait_end(rows)
        last = rows[-1]
        assert headers[0] == ('bytes=0-' if requested is None else requested)
        assert calls[0] == (start, end) and peak[0] == 1
        assert last['outcome'] == 'complete' and last['producer_complete'] is True
        assert last['diagnostic_mode'] == mode
        assert last['batch_budget_us'] == (2000 if mode.endswith('_microbatch') else 0)
        assert sum(last['get_' + bucket] for bucket in ('zero', 'le4k', 'le32k', 'le128k', 'gt128k')) == last['queue_gets']
        assert last['get_gt128k'] == 0 and last['read_le32k'] + last['read_le4k'] > 0
        for role in ('producer', 'consumer'):
            assert last[role + '_cancel_calls'] > 0 and last[role + '_cancel_us'] >= 0
            if last['thread_cpu_supported']:
                assert type(last[role + '_cpu_us']) is int and last[role + '_cpu_us'] >= 0
        assert len(rows) <= stream.OBSERVATION_LIMIT == 48
        assert service.progressive is False and service.queue_bytes == 8 * 1024**2
        assert all(row.get('queue_peak', 0) <= 8 * 1024**2 for row in rows)


def test_ordinary_progressive_path_has_no_new_diagnostic_metrics():
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    with pipeline() as (_, connect, _, rows, _, _):
        connection, response = connect('bytes=0-65535')
        try: assert response.read() == PAYLOAD[:65536]
        finally: response.close(); connection.close()
        wait_end(rows)
        assert not any(key in rows[-1] for key in ('diagnostic_mode', 'batch_budget_us',
            'producer_cpu_us', 'consumer_cpu_us', 'read_le4k', 'get_le4k'))


@pytest.mark.parametrize('mode', ['short_once', 'expired', 'chunked'])
def test_microbatch_preserves_existing_suffix_and_renewal(mode):
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    with pipeline(mode=mode, diagnostic=MICRO, queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (
            _, connect, calls, rows, resolves, peak):
        connection, response = connect('bytes=117-')
        try: assert response.read() == PAYLOAD[117:]
        finally: response.close(); connection.close()
        wait_end(rows)
        if mode == 'short_once': assert calls[1][0] == 117 + 128 * 1024
        if mode == 'expired': assert len(resolves) == 2
        assert all(end == len(PAYLOAD)-1 for start, end in calls) and peak[0] == 1
        assert rows[-1]['outcome'] == 'complete'


@pytest.mark.parametrize('mode', ['wrong_range', 'wrong_length', 'encoding', 'overflow'])
def test_microbatch_keeps_identity_and_excess_eof_rejection(mode):
    from test_ce_progressive_http import pipeline, wait_end
    with pipeline(mode=mode, diagnostic=MICRO) as (_, connect, _, rows, _, _):
        connection, response = connect('bytes=17-99999')
        try:
            if response.status == 503:
                response.read()
            else:
                with pytest.raises(IncompleteRead): response.read()
        finally: response.close(); connection.close()
        wait_end(rows)
        assert rows[-1]['outcome'] == 'failed' and rows[-1]['delivered'] < 99983


def test_microbatch_trickle_expiry_cannot_complete_or_leave_a_producer():
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    with pipeline(mode='trickle', delay=.01, diagnostic=dict(MICRO, seconds=1)) as (
            service, connect, _, rows, _, _):
        connection, response = connect('bytes=0-9999')
        try:
            assert response.read(1) == PAYLOAD[:1]
            with pytest.raises((IncompleteRead, ConnectionError, OSError)): response.read()
        finally: response.close(); connection.close()
        wait_end(rows)
        assert rows[-1]['outcome'] != 'complete' and rows[-1]['cancel'] == 'diagnostic_expired'
        assert not service.producers


def test_host_validates_explicit_modes_and_cannot_retarget_or_persist(tmp_path):
    from bobbi_platform.host import Host
    from bobbi_platform.account_manager import AccountError
    from test_accounts import credential
    def factory(accounts):
        return stream.ShareStream(lambda _: None, lambda *args: None, lambda _: True,
                                  account=accounts, observer=lambda _: None)
    host = Host(tmp_path, stream_factory=factory); host.start()
    try:
        account = host.accounts.install(credential(), host.accounts.snapshot())
        base = dict(request_id='a'*32, locator='am6bqqdocs://A1/123', guid='qqdocs:test',
                    title='Fixture.mkv', size=1000, media='movie:1:0:0', account=account)
        host.dispatch('share_open', base)
        request = dict(base, request_id='b'*32, diagnostic=MICRO)
        host.dispatch('share_open_diagnostic', request)
        entry = host.streams.records['b'*32]
        deadline = entry.diagnostic_deadline
        host.dispatch('share_open_diagnostic', request)
        assert entry.diagnostic_deadline == deadline
        assert entry.io_lock is host.streams.records['a'*32].io_lock
        assert host.streams.records['a'*32].diagnostic is None and not host.streams.progressive
        with pytest.raises(ValueError, match='SHARE_REQUEST_RETARGETED'):
            host.dispatch('share_open_diagnostic', dict(request, diagnostic={'mode': 'open_range', 'seconds': 60}))
        for diagnostic in ({'mode': 'open_range_microbatch', 'seconds': 61},
                           dict(MICRO, wait_ms=3), dict(MICRO, seconds=True)):
            with pytest.raises(ValueError, match='SHARE_DIAGNOSTIC_INVALID'):
                host.dispatch('share_open_diagnostic', dict(request, diagnostic=diagnostic))
        with pytest.raises(ValueError): host.dispatch('share_open', request)
        assert not (tmp_path/'share-transport.json').exists()
        host.accounts.logout(account)
        with pytest.raises(AccountError):
            host.dispatch('share_open_diagnostic', dict(request, request_id='c'*32))
    finally: host.close()


def test_metrics_have_a_closed_numeric_and_enum_schema():
    assert stream.observation_fields(dict(diagnostic_mode='open_range_microbatch', batch_budget_us=2000,
        producer_cpu_us=2, consumer_cancel_calls=3, get_le4k=4, read_eof=1,
        token='private', read_le32k='secret', producer_cancel_us=-1)) == dict(
        diagnostic_mode='open_range_microbatch', batch_budget_us=2000, producer_cpu_us=2,
        consumer_cancel_calls=3, get_le4k=4, read_eof=1)


def test_optional_thread_clock_absence_does_not_change_stream(monkeypatch):
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    monkeypatch.setattr(stream.time, 'thread_time_ns', None)
    with pipeline(diagnostic=MICRO) as (_, connect, _, rows, _, _):
        connection, response = connect('bytes=0-65535')
        try: assert response.read() == PAYLOAD[:65536]
        finally: response.close(); connection.close()
        wait_end(rows)
        assert rows[-1]['thread_cpu_supported'] is False and rows[-1]['producer_complete'] is True
        assert not {'producer_cpu_us', 'consumer_cpu_us'} & rows[-1].keys()
        assert rows[-1]['producer_cancel_calls'] > 0 and rows[-1]['consumer_cancel_calls'] > 0


def test_microbatch_queue_pressure_and_new_range_keep_one_upstream(monkeypatch):
    from test_ce_progressive_http import pipeline, wait_end, PAYLOAD
    from test_ce2035_progressive_initial_range import small_downstream_socket, wait_for
    small_downstream_socket(monkeypatch)
    with pipeline(diagnostic=MICRO, queue_bytes=64*1024) as (_, connect, calls, rows, _, peak):
        first, response = connect(); second = other = None
        try:
            wait_for(lambda: any(row['phase'] == 'yield' for row in rows))
            second, other = connect('bytes=3000000-3032767')
            assert other.read() == PAYLOAD[3000000:3032768]
            assert response.read() == PAYLOAD
        finally:
            response.close(); first.close()
            if other: other.close()
            if second: second.close()
        wait_end(rows, 2)
        yielded = next(row for row in rows if row['phase'] == 'yield' and row['start'] == 0)
        assert any(start == yielded['offset'] + yielded['bytes'] for start, end in calls[1:])
        assert peak[0] == 1 and all(row.get('queue_peak', 0) <= 64*1024 for row in rows)
