"""Real HTTP coverage for bounded initial ranges; not a CDN throughput claim."""
from array import array
from threading import Event, Thread
import socket
import time

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end


MIB = 1024 * 1024


@pytest.fixture(scope='module')
def large_payload():
    # Every four-byte position differs. A replay/skip of a 32 KiB prefix cannot
    # pass by coinciding with the old fixture's repeating 256-byte pattern.
    return array('I', range((65 * MIB + 128) // 4)).tobytes()


def wait_for(predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('real HTTP condition did not occur')


def small_downstream_socket(monkeypatch):
    original = stream.Handler.response_headers

    def headers(self, *args):
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        original(self, *args)

    monkeypatch.setattr(stream.Handler, 'response_headers', headers)


@pytest.mark.parametrize('segment_bytes,length', [
    (stream.MAX_SEGMENT_BYTES, 65 * MIB),
    (12 * MIB, 33 * MIB),
    (256 * 1024, 1024 * 1024),
    (stream.MAX_SEGMENT_BYTES, 32768),
])
def test_initial_upstream_range_uses_configured_cap_without_startup_ramp(
        large_payload, segment_bytes, length):
    start, end = 117, 117 + length - 1
    with pipeline(payload=large_payload, segment_bytes=segment_bytes,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (
                      _, connect, calls, events, _, peak):
        connection, response = connect('bytes={}-{}'.format(start, end))
        try:
            assert response.read() == large_payload[start:end+1]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls[0] == (start, min(end, start + segment_bytes - 1))
        assert all(upper == min(end, offset + segment_bytes - 1)
                   for offset, upper in calls)
        assert peak[0] == 1 and events[-1]['outcome'] == 'complete'
        assert all(row.get('queue_peak', 0) <= stream.PROGRESSIVE_QUEUE_BYTES
                   for row in events)


def test_block_mode_keeps_its_existing_startup_ramp(large_payload):
    length = 33 * MIB
    with pipeline(False, payload=large_payload) as (_, connect, calls, events, _, _):
        connection, response = connect('bytes=0-{}'.format(length - 1))
        try:
            assert response.read() == large_payload[:length]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls == [(0, 8*MIB-1), (8*MIB, 16*MIB-1),
                         (16*MIB, 32*MIB-1), (32*MIB, length-1)]


def test_large_range_delivers_prefix_before_upstream_body_can_finish(large_payload):
    paused, resume = Event(), Event()
    length = 12 * MIB
    with pipeline(payload=large_payload, queue_bytes=64*1024,
                  body_pause=(64*1024, paused, resume)) as (
                      _, connect, calls, events, _, _):
        connection, response = connect('bytes=0-{}'.format(length - 1))
        try:
            assert paused.wait(2)
            assert response.read(16384) == large_payload[:16384]
            assert not resume.is_set()  # The origin still cannot reach EOF.
            assert calls[0] == (0, length - 1)
            resume.set()
            assert response.read() == large_payload[16384:length]
        finally:
            resume.set()
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'complete'
        assert all(row.get('queue_peak', 0) <= 64*1024 for row in events)


def test_large_range_short_read_retries_only_accepted_suffix(large_payload):
    start, end = 117, 117 + 12*MIB - 1
    with pipeline(mode='short_once', payload=large_payload,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (
                      _, connect, calls, events, _, peak):
        connection, response = connect('bytes={}-{}'.format(start, end))
        try:
            assert response.read() == large_payload[start:end+1]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls[:2] == [(start, end), (start + 128*1024, end)]
        assert any(row['phase'] == 'retry' and row['reason'] == 'read_resumed'
                   for row in events)
        assert events[-1]['delivered'] == end-start+1
        assert events[-1]['outcome'] == 'complete' and peak[0] == 1


def test_large_paused_range_yields_gate_and_resumes_exact_suffix(
        monkeypatch, large_payload):
    small_downstream_socket(monkeypatch)
    length, tail = 12*MIB, 60*MIB+13
    with pipeline(payload=large_payload, queue_bytes=64*1024) as (
            _, connect, calls, events, _, peak):
        first, first_response = connect('bytes=0-{}'.format(length - 1))
        second = second_response = None
        try:
            wait_for(lambda: any(row['phase'] == 'yield' for row in events))
            # The first client is still paused. A new same-file range must get
            # an upstream turn without revoking the original HTTP response.
            second, second_response = connect('bytes={}-{}'.format(tail, tail+32767))
            assert second_response.read() == large_payload[tail:tail+32768]
            assert first_response.read() == large_payload[:length]
        finally:
            if second_response is not None:
                second_response.close()
            if second is not None:
                second.close()
            first_response.close()
            first.close()
        wait_end(events, 2)
        first_http = next(row['http'] for row in events if row['phase'] == 'begin')
        yielded = next(row for row in events
                       if row['http'] == first_http and row['phase'] == 'yield')
        sequential_calls = [(start, end) for start, end in calls if start < length]
        assert sequential_calls[0] == (0, length-1)
        assert sequential_calls[1][0] == yielded['offset'] + yielded['bytes']
        assert (tail, tail+32767) in calls
        assert all(row.get('queue_peak', 0) <= 64*1024 for row in events)
        assert peak[0] == 1
        assert len([row for row in events if row['phase'] == 'end'
                    and row['outcome'] == 'complete']) == 2


@pytest.mark.parametrize('abandon', [False, True])
def test_large_probe_yields_to_queued_tail_and_releases_producer(
        monkeypatch, large_payload, abandon):
    small_downstream_socket(monkeypatch)
    paused, resume, tail_done = Event(), Event(), Event()
    tail, result, failures = 60*MIB+13, [], []
    with pipeline(payload=large_payload, queue_bytes=64*1024,
                  body_pause=(64*1024, paused, resume)) as (
                      service, connect, calls, events, _, peak):
        first, first_response = connect()
        assert paused.wait(2)
        assert first_response.read(1) == large_payload[:1]
        entry = next(iter(service.records.values()))
        contention_seen = Event()
        contended = entry.io_lock.contended

        def observe_contention():
            result = contended()
            if result:
                contention_seen.set()
            return result

        monkeypatch.setattr(entry.io_lock, 'contended', observe_contention)

        def read_tail():
            connection = response = None
            try:
                connection, response = connect('bytes={}-{}'.format(tail, tail+32767))
                result.append(response.read())
            except Exception as error:
                failures.append(error)
            finally:
                if response is not None:
                    response.close()
                if connection is not None:
                    connection.close()
                tail_done.set()

        worker = Thread(target=read_tail, daemon=True)
        worker.start()
        try:
            # A fast producer may yield and serve the tail before the test
            # thread gets scheduled. Observe the real contention as an event,
            # not a queue state that can already have disappeared.
            wait_for(lambda: contention_seen.is_set() or observe_contention())
            if abandon:
                # Cancel only this probe. Its already queued tail range remains
                # valid, as do the account and source binding.
                first_response.close()
                first.close()
            resume.set()
            assert tail_done.wait(4)
            assert not failures and result == [large_payload[tail:tail+32768]]
            assert contention_seen.is_set()
            if not abandon:
                assert any(row['phase'] == 'yield' and row['start'] == 0 for row in events)
                # Urgent contention must yield even while the original range
                # remains live; the later suffix still completes byte-exactly.
                assert first_response.read() == large_payload[1:]
            wait_end(events, 2)
            wait_for(lambda: not service.producers)
        finally:
            resume.set()
            first_response.close()
            first.close()
            worker.join(5)
        assert not worker.is_alive()
        initial = next(row for row in events if row['phase'] == 'end' and row['start'] == 0)
        if abandon:
            assert initial['outcome'] != 'complete'
            assert initial['delivered'] < len(large_payload)
        else:
            assert initial['outcome'] == 'complete'
            assert initial['delivered'] == len(large_payload)
        assert calls[0] == (0, stream.MAX_SEGMENT_BYTES-1)
        assert (tail, tail+32767) in calls and peak[0] == 1
        for _ in range(6):
            assert service.producer_slots.acquire(blocking=False)
        assert not service.producer_slots.acquire(blocking=False)
        for _ in range(6):
            service.producer_slots.release()
