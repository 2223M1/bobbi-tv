"""Queue batching invariants; no claim that batching explains device stalls."""
from array import array
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end


def drain(queue):
    result = []
    while True:
        value = queue.get(lambda: False)
        if value is None:
            return result
        assert len(value) <= stream.DELIVERY_CHUNK_BYTES
        result.append(value)
        assert queue.bytes == sum(len(part) for part in queue.chunks)


def test_already_queued_four_kib_fragments_are_one_available_batch(monkeypatch):
    queue = stream.ByteQueue()
    payloads = [bytes([index]) * 4096 for index in range(40)]
    for part in payloads:
        assert queue.put(part)
    monkeypatch.setattr(queue.condition, 'wait', lambda *args: pytest.fail('No wait for already queued data'))
    assert queue.get(lambda: False) == b''.join(payloads[:32])
    assert queue.bytes == 8 * 4096
    queue.finish()
    assert b''.join(drain(queue)) == b''.join(payloads[32:])
    assert queue.puts == 40 and queue.gets == 2 and queue.peak == 40 * 4096


@pytest.mark.parametrize('length', [stream.DELIVERY_CHUNK_BYTES + 1,
    3 * stream.DELIVERY_CHUNK_BYTES + 19, stream.PROGRESSIVE_QUEUE_BYTES])
def test_oversized_single_injected_chunk_splits_and_preserves_exact_suffix(length):
    queue = stream.ByteQueue()
    payload = (array('I', range((length + 3) // 4)).tobytes())[:length]
    assert queue.put(payload)
    queue.finish()
    blocks = drain(queue)
    assert b''.join(blocks) == payload
    assert queue.puts == 1 and queue.gets == (length + stream.DELIVERY_CHUNK_BYTES - 1) // stream.DELIVERY_CHUNK_BYTES
    assert queue.bytes == 0 and queue.peak == length


def test_partial_boundary_combines_current_chunks_but_retains_next_byte_exactly():
    cap, queue = stream.DELIVERY_CHUNK_BYTES, stream.ByteQueue()
    payloads = [b'a' * (cap - 3), b'bcdefghij', b'klm']
    for value in payloads:
        assert queue.put(value)
    assert queue.get(lambda: False) == payloads[0] + b'bcd'
    assert queue.bytes == 9 and queue.chunks[0] == b'efghij'
    queue.finish()
    assert b''.join(drain(queue)) == b'efghijklm'


def test_tiny_first_prefix_returns_without_waiting_for_another_chunk(monkeypatch):
    queue = stream.ByteQueue()
    assert queue.put(b'x')
    monkeypatch.setattr(queue.condition, 'wait', lambda *args: pytest.fail('Must not wait to fill 128 KiB'))
    assert queue.get(lambda: False) == b'x'
    assert not queue.finished and queue.bytes == 0 and queue.gets == 1


def test_empty_injected_prefix_does_not_scan_an_unbounded_zero_byte_batch():
    queue = stream.ByteQueue()
    for _ in range(1000):
        assert queue.put(b'')
    assert queue.put(b'video')
    assert queue.get(lambda: False) == b''
    assert len(queue.chunks) == 1000 and queue.bytes == 5


def test_cancel_and_stop_do_not_deliver_or_count_queued_prefixes():
    queue = stream.ByteQueue()
    assert queue.put(b'kept-until-stop')
    assert queue.get(lambda: True) is None and queue.gets == 0
    assert queue.bytes == len(b'kept-until-stop')
    queue.stop()
    assert queue.get(lambda: False) is None and queue.bytes == 0 and not queue.chunks
    assert not queue.put(b'late') and queue.puts == 1


def test_terminal_error_follows_all_accepted_prefix_bytes_and_is_not_eof():
    queue = stream.ByteQueue()
    payload = b'prefix' * (stream.DELIVERY_CHUNK_BYTES // 2)
    assert queue.put(payload)
    error = OSError('SHARE_READ_TRUNCATED')
    queue.finish(error)
    values = []
    while queue.bytes:
        values.append(queue.get(lambda: False))
    assert b''.join(values) == payload
    with pytest.raises(OSError) as raised:
        queue.get(lambda: False)
    assert raised.value is error


def test_get_notifies_half_queue_room_waiter_without_a_new_delay():
    queue = stream.ByteQueue(2 * stream.FETCH_CHUNK_BYTES)
    assert queue.put(b'a' * queue.limit)
    began, completed = Event(), Event()
    def wait_room():
        began.set()
        assert queue.room(lambda: False)
        completed.set()
    worker = Thread(target=wait_room)
    worker.start()
    try:
        assert began.wait(1) and not completed.is_set()
        assert queue.get(lambda: False) == b'a' * queue.limit
        assert completed.wait(1)
    finally:
        queue.stop()
        worker.join(1)
    assert not worker.is_alive()


def test_concurrent_producer_consumer_preserve_all_bytes_and_queue_budget():
    payload = array('I', range(512 * 1024)).tobytes()
    queue = stream.ByteQueue(256 * 1024)
    cancelled, failures, parts = Event(), [], []
    def produce():
        try:
            offset, index = 0, 0
            sizes = (1, 7, 4096, 32768, 1123, 257, 131071)
            while offset < len(payload):
                part = payload[offset:offset + sizes[index % len(sizes)]]
                while not queue.put(part):
                    if not queue.room(cancelled.is_set):
                        return
                parts.append(part)
                offset += len(part)
                index += 1
            queue.finish()
        except Exception as error:
            failures.append(error)
            queue.finish(error)
    worker = Thread(target=produce)
    worker.start()
    try:
        result = drain(queue)
    finally:
        cancelled.set()
        queue.stop()
        worker.join(2)
    assert not worker.is_alive() and not failures
    assert b''.join(result) == b''.join(parts) == payload
    assert queue.peak <= queue.limit and queue.puts == len(parts) and queue.gets == len(result)


def test_batched_write_retains_timeout_partial_send_and_exact_delivered_count():
    queue = stream.ByteQueue()
    pieces = [bytes([i]) * 4096 for i in range(8)]
    for value in pieces:
        assert queue.put(value)
    block = queue.get(lambda: False)
    delivered, attempts = [], []
    def send(view):
        attempts.append(len(view))
        if len(attempts) == 1:
            raise TimeoutError()
        size = min(len(view), 123 if len(attempts) == 2 else 7777)
        delivered.append(bytes(view[:size]))
        return size
    handler = stream.Handler.__new__(stream.Handler)
    handler.connection = SimpleNamespace(settimeout=lambda seconds: None, send=send)
    handler.cancelled = lambda: False
    handler.observation_delivered = handler.progressive_send_calls = 0
    assert handler.write_block(block)
    assert b''.join(delivered) == block == b''.join(pieces)
    assert handler.observation_delivered == len(block) and handler.progressive_send_calls == len(attempts)
    assert max(attempts) <= stream.DELIVERY_CHUNK_BYTES


def test_cancel_during_partial_batched_send_does_not_mark_batch_delivered():
    handler = stream.Handler.__new__(stream.Handler)
    cancelled, output = Event(), []
    def send(view):
        output.append(bytes(view[:7]))
        cancelled.set()
        return 7
    handler.connection = SimpleNamespace(settimeout=lambda seconds: None, send=send)
    handler.cancelled = cancelled.is_set
    handler.observation_delivered = handler.progressive_send_calls = 0
    assert not handler.write_block(b'original-exact-payload')
    assert output == [b'origina'] and handler.observation_delivered == 7 and handler.progressive_send_calls == 1


def test_real_http_trace_has_only_bounded_counts_and_exact_complete_bytes():
    with pipeline(queue_bytes=256 * 1024) as (service, connect, calls, observations, resolves, peak):
        connection, response = connect('bytes=117-524404')
        try:
            from test_ce_progressive_http import PAYLOAD
            assert response.read() == PAYLOAD[117:524405]
        finally:
            response.close()
            connection.close()
        wait_end(observations)
        end = observations[-1]
        assert end['outcome'] == 'complete' and end['delivered'] == 524288
        assert 0 < end['queue_gets'] <= end['queue_puts'] and end['send_calls'] >= end['queue_gets']
        assert len(observations) <= stream.OBSERVATION_LIMIT and peak[0] == 1
        assert max(row.get('queue_peak', 0) for row in observations) <= 256 * 1024
        for _ in range(6): assert service.producer_slots.acquire(blocking=False)
        for _ in range(6): service.producer_slots.release()


@pytest.mark.parametrize('bad', [-1, True, 1.2, 'secret', 2**63])
def test_new_observation_counts_keep_closed_numeric_schema(bad):
    assert stream.observation_fields(dict(queue_puts=bad, queue_gets=bad, send_calls=bad, url='secret')) == {}
    assert stream.observation_fields(dict(queue_puts=4, queue_gets=1, send_calls=2)) == dict(
        queue_puts=4, queue_gets=1, send_calls=2)
