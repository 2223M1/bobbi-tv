"""External cancellation never owns queue progress; no TV throughput claim."""
from pathlib import Path
from threading import Event, Thread
from types import ModuleType
import subprocess
import sys

import pytest

from bobbi_core import share_stream as stream

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'c58cd3ede800ef401d203838bdc0c5e59c0a1686'


@pytest.fixture(scope='module')
def baseline():
    """Execute the actual pre-fix class, not a handwritten locking imitation."""
    source = subprocess.check_output(['git', 'show', BASELINE + ':' +
        'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py'], cwd=ROOT)
    name = '_frozen_share_queue_lock_baseline'
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, '<frozen-' + BASELINE[:7] + '-share-stream>', 'exec'), module.__dict__)
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize('method', ['get', 'room'])
@pytest.mark.parametrize('operation', ['put', 'stop'])
@pytest.mark.parametrize('old', [False, True])
def test_callback_waiting_for_external_queue_operation_exposes_actual_baseline_convoy(
        baseline, method, operation, old):
    queue = (baseline if old else stream).ByteQueue(limit=32768)
    queue.put(b'x' * 16385)
    entered, attempted, completed = Event(), Event(), Event()
    observed = []

    def external():
        assert entered.wait(2)
        attempted.set()
        queue.put(b'y') if operation == 'put' else queue.stop()
        completed.set()

    worker = Thread(target=external)
    worker.start()
    def cancelled():
        # Ownership is asserted directly; bounded Event waits expose the blocked
        # dependency. No throughput or scheduler-duration threshold is the oracle.
        owned = queue.condition._is_owned()
        entered.set()
        assert attempted.wait(2)
        progressed = completed.wait(.05 if owned else 2)
        observed.append((owned, progressed))
        return True
    try:
        assert getattr(queue, method)(cancelled) is (None if method == 'get' else False)
    finally:
        entered.set()
        worker.join(2)
    assert not worker.is_alive() and completed.is_set()
    assert observed == ([(True, False)] if old else [(False, True)])


@pytest.mark.parametrize('method', ['get', 'room'])
@pytest.mark.parametrize('operation', ['put', 'stop', 'error', 'eof'])
def test_queue_state_is_revalidated_after_unlocked_callback(method, operation):
    queue = stream.ByteQueue(limit=32768)
    if method == 'room':
        queue.put(b'x' * 16385)
    completed = Event()
    error = OSError('SHARE_RANGE_OVERFLOW')
    def external():
        if operation == 'put':
            if method == 'room':
                assert queue.get(lambda: False) == b'x' * 16385
            else:
                queue.put(b'available-during-check')
        elif operation == 'stop':
            queue.stop()
        else:
            queue.finish(error if operation == 'error' else None)
            if method == 'room':
                assert queue.get(lambda: False) == b'x' * 16385
        completed.set()
    workers, calls = [], []
    def cancelled():
        assert not queue.condition._is_owned()
        calls.append(1)
        assert len(calls) == 1, 'State/notification during callback was lost'
        worker = Thread(target=external)
        workers.append(worker)
        worker.start()
        assert completed.wait(2)
        return False
    try:
        if operation == 'error' and method == 'get':
            with pytest.raises(OSError) as caught:
                queue.get(cancelled)
            assert caught.value is error
        else:
            result = getattr(queue, method)(cancelled)
            assert result == (operation != 'stop' if method == 'room' else
                              b'available-during-check' if operation == 'put' else None)
    finally:
        for worker in workers: worker.join(2)
    assert all(not worker.is_alive() for worker in workers)


@pytest.mark.parametrize('method', ['get', 'room'])
def test_cancel_wins_even_when_callback_allows_an_external_put(method):
    queue = stream.ByteQueue(limit=32768)
    completed = Event()
    def external():
        queue.put(b'never-authorized-for-output')
        completed.set()
    workers = []
    def cancelled():
        assert not queue.condition._is_owned()
        worker = Thread(target=external)
        workers.append(worker)
        worker.start()
        assert completed.wait(2)
        return True
    try:
        assert getattr(queue, method)(cancelled) is (None if method == 'get' else False)
        assert queue.gets == 0
    finally:
        for worker in workers: worker.join(2)


@pytest.mark.parametrize('method', ['get', 'room'])
def test_every_poll_checks_cancellation_outside_condition_and_stops_after_notification(monkeypatch, method):
    queue = stream.ByteQueue(limit=32768)
    if method == 'room': queue.put(b'x' * 16385)
    calls, waits = [], []
    revoked = [False]
    def cancelled():
        assert not queue.condition._is_owned()
        calls.append(revoked[0])
        return revoked[0]
    def wake(seconds):
        assert queue.condition._is_owned()
        waits.append(seconds)
        revoked[0] = True
        queue.condition.notify_all()
    monkeypatch.setattr(queue.condition, 'wait', wake)
    assert getattr(queue, method)(cancelled) is (None if method == 'get' else False)
    assert calls == [False, True] and waits == [.05]
    assert queue.gets == 0


@pytest.mark.parametrize('terminal', ['cancel', 'stop', 'error', 'eof'])
def test_microbatch_checks_each_wake_outside_lock_with_fixed_deadline(monkeypatch, terminal):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'first')
    assert queue.get(lambda: False) == b'first'
    queue.put(b'b')
    now, waits, checks, revoked = [10.0], [], [], [False]
    error = OSError('SHARE_RANGE_OVERFLOW')
    monkeypatch.setattr(stream.time, 'monotonic', lambda: now[0])
    def cancelled():
        assert not queue.condition._is_owned()
        checks.append(now[0])
        return revoked[0]
    def wake(seconds):
        assert queue.condition._is_owned()
        waits.append(seconds)
        now[0] += .0007
        if len(waits) == 1:
            queue.put(b'c')
        elif terminal == 'cancel': revoked[0] = True
        elif terminal == 'stop': queue.stop()
        elif terminal == 'error': queue.finish(error)
        else: queue.finish()
    monkeypatch.setattr(queue.condition, 'wait', wake)
    if terminal == 'error':
        with pytest.raises(OSError) as caught:
            queue.get(cancelled)
        assert caught.value is error
    else:
        assert queue.get(cancelled) == (b'bc' if terminal == 'eof' else None)
    assert waits == pytest.approx([.002, .0013])
    assert checks == pytest.approx([10.0, 10.0007] if terminal == 'stop' else [10.0, 10.0007, 10.0014])
    assert now[0] < 10.002


def test_microbatch_expired_deadline_still_checks_revocation_after_wake(monkeypatch):
    queue = stream.ByteQueue(microbatch=True)
    queue.put(b'a'); assert queue.get(lambda: False) == b'a'
    queue.put(b'b')
    now, revoked = [10.0], [False]
    monkeypatch.setattr(stream.time, 'monotonic', lambda: now[0])
    def wake(seconds):
        assert seconds == pytest.approx(.002)
        now[0] = 10.01
        revoked[0] = True
        queue.put(b'c')
    monkeypatch.setattr(queue.condition, 'wait', wake)
    assert queue.get(lambda: revoked[0]) is None and queue.gets == 1


@pytest.mark.parametrize('method', ['get', 'room'])
def test_external_callback_failure_never_retains_queue_lock(method):
    queue = stream.ByteQueue()
    error = RuntimeError('cancel check failed')
    def failed():
        assert not queue.condition._is_owned()
        raise error
    with pytest.raises(RuntimeError) as caught:
        getattr(queue, method)(failed)
    assert caught.value is error
    assert queue.put(b'after') and queue.get(lambda: False) == b'after'


def test_real_http_cancel_checks_inside_queue_calls_do_not_hold_queue_lock(monkeypatch):
    from test_ce_progressive_http import pipeline, wait_end
    calls = {'get': 0, 'room': 0}
    for name in calls:
        original = getattr(stream.ByteQueue, name)
        def checked(queue, cancelled, original=original, name=name):
            def check():
                assert not queue.condition._is_owned()
                calls[name] += 1
                return cancelled()
            return original(queue, check)
        monkeypatch.setattr(stream.ByteQueue, name, checked)
    payload = bytes(range(251)) * 4097
    with pipeline(False, payload=payload, diagnostic=dict(mode='open_range_microbatch', seconds=60)) as (
            _, connect, _, events, _, peak):
        connection, response = connect('bytes=117-')
        try:
            assert response.read() == payload[117:]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'complete' and peak[0] == 1
    assert all(value > 0 for value in calls.values())


@pytest.mark.parametrize('mode', [None, 'open_range', 'open_range_microbatch'])
def test_real_http_downstream_half_close_is_not_revocation(mode):
    import socket
    from test_ce_progressive_http import pipeline, wait_end
    paused, resume = Event(), Event()
    payload = bytes(range(251)) * 4097
    diagnostic = dict(mode=mode, seconds=60) if mode else None
    with pipeline(payload=payload, diagnostic=diagnostic,
                  body_pause=(65536, paused, resume)) as (_, connect, _, events, _, _):
        connection, response = connect()
        try:
            assert paused.wait(2)
            # Connection: close transfers the live socket to HTTPResponse's
            # buffered reader; HTTPConnection.sock is already cleared.
            response.fp.raw._sock.shutdown(socket.SHUT_WR)
            resume.set()
            assert response.read() == payload
        finally:
            resume.set()
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'complete' and events[-1]['cancel'] == 'none'
