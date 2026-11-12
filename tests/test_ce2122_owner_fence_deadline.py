"""Slow admission checks must not execute expired or cancelled owner calls."""
from queue import Queue
from threading import Event, Thread
import time

import pytest

from bobbi_platform.host import Host


class ObservedQueue(Queue):
    def __init__(self):
        super().__init__(maxsize=32)
        self.submitted = Event()
        self.job = None

    def put_nowait(self, job):
        self.job = job
        super().put_nowait(job)
        self.submitted.set()


class FencedCall:
    def __init__(self, lifecycle, wait_point):
        # Exercise real Host methods without creating a runtime socket or files.
        self.host = host = Host.__new__(Host)
        host.calls = ObservedQueue()
        host.revocations = Queue(maxsize=32)
        host.stopping = Event()
        host.account_changes = Event()
        host.owner_account_changed = None
        host.profile_revoked = False
        host.report = lambda code: None
        host._tick_catalog = lambda: None
        host._tick_preparation = lambda: None
        host.engine_check = float('inf')
        self.entered, self.release = Event(), Event()
        self.owner_calls, self.quiesce_calls = [], []
        self.replies, self.caller_errors, self.tick_errors = [], [], []
        self.checks = 0
        self.lifecycle = lifecycle
        self.wait_point = wait_point
        self.body = {'protocol': 1} if lifecycle else {'operation': 'snapshot'}
        host.profile_current = self.profile_current
        host.owner = self.owner
        host.can_quiesce = self.can_quiesce
        self.caller = Thread(target=self.call, daemon=True)
        self.ticker = Thread(target=self.tick, daemon=True)

    def profile_current(self):
        self.checks += 1
        # The first check is tick entry; the second guards the dequeued job.
        if self.checks == 2 and self.wait_point == 'profile':
            self.wait_for_release()
        return True

    def wait_for_release(self):
        self.entered.set()
        if not self.release.wait(2):
            raise RuntimeError('Test admission check was not released')

    def owner(self, body):
        self.owner_calls.append(body)
        return {'snapshot': 'current'}

    def can_quiesce(self):
        self.quiesce_calls.append(True)
        if self.wait_point == 'quiesce':
            self.wait_for_release()
        return True

    def call(self):
        try:
            self.replies.append(self.host._owner_request(self.body, lifecycle=self.lifecycle))
        except BaseException as error:
            self.caller_errors.append(error)

    def tick(self):
        try:
            self.host.tick()
        except BaseException as error:
            self.tick_errors.append(error)

    def start(self, extend_deadline=False):
        self.caller.start()
        assert self.host.calls.submitted.wait(1)
        if extend_deadline:
            self.host.calls.job.deadline = time.monotonic() + 1
        self.ticker.start()
        assert self.entered.wait(1), 'Owner job did not reach its admission check'

    def finish(self):
        self.release.set()
        self.caller.join(1)
        self.ticker.join(1)
        assert not self.caller.is_alive(), 'Caller did not finish'
        assert not self.ticker.is_alive(), 'Owner tick did not finish'
        assert not self.tick_errors

    def assert_not_dispatched(self):
        assert not self.owner_calls
        assert self.quiesce_calls == ([True] if self.wait_point == 'quiesce' else [])
        assert not self.host.stopping.is_set()
        assert not self.replies
        assert self.host.calls.job.done.is_set()
        assert self.host.calls.job.error == 'unavailable'


@pytest.fixture(params=[(False, 'profile'), (True, 'profile'), (True, 'quiesce')],
                ids=['owner-profile', 'lifecycle-profile', 'lifecycle-quiesce'])
def fenced(request):
    call = FencedCall(*request.param)
    try:
        yield call
    finally:
        call.release.set()
        for worker in (call.caller, call.ticker):
            if worker.ident is not None:
                worker.join(2)
                assert not worker.is_alive(), 'Test worker was not drained'


@pytest.mark.parametrize('clear_cancellation', [False, True], ids=['timeout', 'deadline-only'])
def test_caller_timeout_during_admission_check_never_dispatches(fenced, clear_cancellation):
    fenced.start()
    # Keep the selected check blocked until the real .25 s caller wait expires.
    fenced.caller.join(1)
    assert not fenced.caller.is_alive()
    assert len(fenced.caller_errors) == 1
    assert isinstance(fenced.caller_errors[0], TimeoutError)
    assert str(fenced.caller_errors[0]) == 'NATIVE_OWNER_TIMEOUT'
    job = fenced.host.calls.job
    assert job.cancelled and time.monotonic() >= job.deadline
    if clear_cancellation:
        # Prove expiry rejects independently of the cancellation signal.
        job.cancelled = False
    fenced.finish()
    fenced.assert_not_dispatched()


def test_explicit_cancellation_during_admission_check_never_dispatches(fenced):
    fenced.start(extend_deadline=True)
    job = fenced.host.calls.job
    assert time.monotonic() < job.deadline
    job.cancelled = True
    fenced.finish()
    fenced.assert_not_dispatched()
    assert len(fenced.caller_errors) == 1
    assert type(fenced.caller_errors[0]) is OSError
    assert str(fenced.caller_errors[0]) == 'NATIVE_OWNER_UNAVAILABLE'


def test_current_call_dispatches_after_admission_check_returns(fenced):
    fenced.start(extend_deadline=True)
    fenced.finish()
    assert not fenced.caller_errors
    assert fenced.host.calls.job.done.is_set()
    assert not fenced.host.calls.job.error
    if fenced.lifecycle:
        assert fenced.replies == [{'accepted': True}]
        assert not fenced.owner_calls
        assert fenced.quiesce_calls == [True]
        assert fenced.host.stopping.is_set()
    else:
        assert fenced.replies == [{'snapshot': 'current'}]
        assert fenced.owner_calls == [fenced.body]
        assert not fenced.quiesce_calls
        assert not fenced.host.stopping.is_set()
