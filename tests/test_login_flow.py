"""Shared login mechanism only: no Kodi, network or real account material."""
from threading import Event, Timer, get_ident
import time
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from bobbi_platform.cloud115 import CloudError
from bobbi_platform.login_flow import LoginFlowError, LoginRunner, is_retryable
from bobbi_platform.pan_accounts import PanError


@pytest.fixture
def scene():
    s = SimpleNamespace(now=0.0, calls=[], statuses=[], rendered=[], aborted=False,
                        replies=[dict(state='ready')], ui_thread=get_ident())
    s.window = SimpleNamespace(cancelled=False)
    def status(value):
        assert get_ident() == s.ui_thread
        s.statuses.append(value)
    s.window.set_status = status
    def wait(seconds):
        s.now += seconds
        return s.aborted
    s.monitor = SimpleNamespace(abortRequested=lambda: s.aborted, waitForAbort=wait)
    s.runner = LoginRunner(s.window, s.monitor, clock=lambda: s.now)
    def begin():
        assert get_ident() != s.ui_thread
        s.calls.append('begin')
        return dict(state='waiting', qr='https://fixture.invalid/qr')
    def poll():
        assert get_ident() != s.ui_thread
        s.calls.append('poll')
        value = s.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    def commit():
        assert get_ident() == s.ui_thread
        s.calls.append('commit')
        return dict(state='committed')
    s.adapter = SimpleNamespace(begin=begin, poll=poll, commit=commit)
    def render(state):
        assert get_ident() == s.ui_thread
        s.rendered.append(state)
    s.render = render
    return s


def test_prepare_poll_are_workers_but_render_status_and_single_commit_are_ui(scene):
    scene.replies = [dict(state='scanned'), dict(state='ready')]
    assert scene.runner.run(scene.adapter, scene.render) is True
    assert scene.calls == ['begin', 'poll', 'poll', 'commit']
    assert len(scene.rendered) == 1
    assert scene.runner.diagnostic() == dict(phase='complete', code='NONE',
        commit_sent=True, commit_acknowledged=True)


@pytest.mark.parametrize('abort', [False, True])
def test_cancel_before_begin_never_starts_network_or_render(scene, abort):
    scene.aborted, scene.window.cancelled = abort, not abort
    assert scene.runner.run(scene.adapter, scene.render) is False
    assert scene.calls == scene.rendered == scene.statuses == []


@pytest.mark.parametrize('operation', ['begin', 'poll'])
@pytest.mark.parametrize('abort', [False, True])
def test_cancel_during_worker_discards_late_ready_and_image(scene, operation, abort):
    release, finished = Event(), Event()
    def blocked():
        scene.calls.append(operation)
        scene.aborted, scene.window.cancelled = abort, not abort
        assert release.wait(2)
        finished.set()
        return dict(state='waiting', qr='https://fixture.invalid/late') if operation == 'begin' else dict(state='ready')
    setattr(scene.adapter, operation, blocked)
    try:
        assert scene.runner.run(scene.adapter, scene.render) is False
        assert not finished.is_set()
        assert 'commit' not in scene.calls
        if operation == 'begin':
            assert not scene.rendered
    finally:
        release.set()
    assert finished.wait(1)
    assert 'commit' not in scene.calls
    assert len(scene.rendered) == (0 if operation == 'begin' else 1)


@pytest.mark.parametrize('operation', ['begin', 'poll'])
@pytest.mark.parametrize('abort', [False, True])
def test_kodi_callbacks_dispatch_while_network_worker_is_blocked(scene, operation, abort):
    queued, release, finished = Event(), Event(), Event()
    pumps, callbacks = [], []
    def wait(seconds):
        assert 0 < seconds <= .1  # Zero means an infinite wait on the target Kodi fork.
        pumps.append(seconds)
        if queued.is_set() and not callbacks:
            assert get_ident() == scene.ui_thread
            callbacks.append('abort' if abort else 'cancel')
            scene.aborted, scene.window.cancelled = abort, not abort
        return scene.aborted
    scene.monitor.waitForAbort = wait
    scene.runner = LoginRunner(scene.window, scene.monitor, clock=time.monotonic, lifetime=.5)
    def blocked():
        scene.calls.append(operation)
        queued.set()  # Only waitForAbort can deliver this queued Kodi callback.
        assert release.wait(2)
        finished.set()
        return dict(state='waiting', qr='https://fixture.invalid/late') if operation == 'begin' else dict(state='ready')
    setattr(scene.adapter, operation, blocked)
    started = time.monotonic()
    try:
        assert scene.runner.run(scene.adapter, scene.render) is False
        assert time.monotonic() - started < .4
        assert callbacks == ['abort' if abort else 'cancel']
        assert not finished.is_set() and 'commit' not in scene.calls
        assert scene.calls.count(operation) == 1
        assert len(scene.rendered) == (0 if operation == 'begin' else 1)
    finally:
        release.set()
    assert finished.wait(1)
    assert pumps and not scene.runner.commit_sent
    assert len(scene.rendered) == (0 if operation == 'begin' else 1)


@pytest.mark.parametrize('operation', ['begin', 'poll'])
def test_ready_worker_result_still_pumps_pending_cancel_before_render_or_commit(scene, operation):
    queued, callbacks = Event(), []
    def wait(seconds):
        assert seconds > 0
        if queued.is_set() and not callbacks:
            callbacks.append('cancel')
            scene.window.cancelled = True
        return False
    scene.monitor.waitForAbort = wait
    def ready():
        scene.calls.append(operation)
        queued.set()
        return dict(state='waiting', qr='https://fixture.invalid/late') if operation == 'begin' else dict(state='ready')
    setattr(scene.adapter, operation, ready)
    assert scene.runner.run(scene.adapter, scene.render) is False
    assert callbacks == ['cancel'] and 'commit' not in scene.calls
    assert len(scene.rendered) == (0 if operation == 'begin' else 1)


def test_nonblocking_monitor_stub_yields_to_worker_instead_of_busy_spinning(scene):
    release, entered = Event(), Event()
    pumps = []
    def wait(seconds):
        assert seconds > 0
        pumps.append(seconds)
        assert len(pumps) < 200, 'A no-wait monitor must not spin and starve its worker'
        return False
    scene.monitor.waitForAbort = wait
    scene.runner = LoginRunner(scene.window, scene.monitor, clock=time.monotonic, lifetime=1)
    def begin():
        entered.set()
        assert release.wait(1)
        scene.calls.append('begin')
        return dict(state='waiting', qr='https://fixture.invalid/qr')
    scene.adapter.begin = begin
    timer = Timer(.025, release.set)
    timer.start()
    try:
        assert scene.runner.run(scene.adapter, scene.render) is True
        assert entered.is_set() and scene.calls == ['begin', 'poll', 'commit']
    finally:
        release.set()
        timer.cancel()


@pytest.mark.parametrize('operation,elapsed', [('begin', 21), ('poll', 29)])
def test_wait_timeout_terminates_without_overlap_or_accepting_late_results(scene, operation, elapsed):
    release, finished = Event(), Event()
    def blocked():
        scene.calls.append(operation)
        scene.now += elapsed
        assert release.wait(2)
        finished.set()
        return dict(state='ready')
    setattr(scene.adapter, operation, blocked)
    try:
        with pytest.raises(LoginFlowError) as caught:
            scene.runner.run(scene.adapter, scene.render)
        assert caught.value.code == 'WAIT_TIMEOUT'
        assert not finished.is_set()
        assert scene.calls.count(operation) == 1 and 'commit' not in scene.calls
        with pytest.raises(LoginFlowError, match='INVALID_STATE'):
            scene.runner.run(scene.adapter, scene.render)
        assert scene.calls.count(operation) == 1
    finally:
        release.set()
    assert finished.wait(1)
    assert 'commit' not in scene.calls


def test_remaining_whole_attempt_budget_caps_prepare_wait(scene):
    scene.runner.lifetime = 5
    def begin():
        scene.calls.append('begin')
        scene.now = 6
        return dict(state='waiting', qr='https://fixture.invalid/late')
    scene.adapter.begin = begin
    with pytest.raises(LoginFlowError, match='EXPIRED'):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin'] and not scene.rendered


def test_structured_retries_cannot_extend_whole_attempt_deadline(scene):
    scene.runner.lifetime = 7
    scene.replies = [dict(state='retry', phase='confirm') for _ in range(20)]
    with pytest.raises(LoginFlowError, match='EXPIRED'):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll', 'poll', 'poll']


def test_remaining_whole_attempt_budget_caps_poll_wait_below_twenty_eight_seconds(scene):
    scene.runner.lifetime = 7
    def poll():
        scene.calls.append('poll')
        scene.now += 6
        return dict(state='ready')
    scene.adapter.poll = poll
    with pytest.raises(LoginFlowError, match='EXPIRED'):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll']


@pytest.mark.parametrize('lifetime', [0, -1, True, '180', 181, float('inf'), float('nan')])
def test_attempt_budget_cannot_be_unbounded_or_exceed_host_lifetime(scene, lifetime):
    with pytest.raises(LoginFlowError, match='INVALID_STATE'):
        LoginRunner(scene.window, scene.monitor, lifetime=lifetime)


@pytest.mark.parametrize('error', [PanError('PAN_NETWORK_ERROR'), CloudError('NETWORK_ERROR'),
    CloudError('QR_POLL_RETRY'), OSError('private-fixture'), TimeoutError('private-fixture')])
def test_explicit_transient_error_has_three_total_poll_calls_then_stops(scene, error):
    scene.replies = [error] * 4
    with pytest.raises(type(error)) as caught:
        scene.runner.run(scene.adapter, scene.render)
    assert caught.value is error
    assert scene.calls == ['begin', 'poll', 'poll', 'poll']
    assert sum('连接暂不可用，正在重试' in value for value in scene.statuses) == 2
    assert 'private-fixture' not in repr(scene.statuses)


def test_successful_poll_response_resets_explicit_failure_streak(scene):
    error = PanError('PAN_NETWORK_ERROR')
    scene.replies = [error, error, dict(state='waiting'), error, error, dict(state='ready')]
    assert scene.runner.run(scene.adapter, scene.render)
    assert scene.calls.count('poll') == 6 and scene.calls.count('commit') == 1


def test_begin_is_not_retried_even_for_network_error(scene):
    def begin():
        scene.calls.append('begin')
        raise PanError('PAN_NETWORK_ERROR')
    scene.adapter.begin = begin
    with pytest.raises(PanError):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin'] and not scene.rendered


@pytest.mark.parametrize('error', [PanError('PAN_API_REJECTED'), PanError('PAN_REPLY_INVALID'),
    CloudError('LOGIN_FAILED'), CloudError('INVALID_REPLY'), ValueError('private-fixture'),
    RuntimeError('private-fixture'), HTTPError('https://fixture.invalid/private', 403, 'private-fixture', {}, None)])
def test_terminal_error_is_preserved_without_retry_or_commit(scene, error):
    scene.replies = [error]
    with pytest.raises(type(error)) as caught:
        scene.runner.run(scene.adapter, scene.render)
    assert caught.value is error and scene.calls == ['begin', 'poll']
    assert not scene.runner.commit_sent


def test_adapter_gate_can_narrow_but_cannot_broaden_retry_policy(scene):
    scene.adapter.retryable = lambda error: False
    scene.replies = [PanError('PAN_NETWORK_ERROR')]
    with pytest.raises(PanError):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll']
    scene.runner = LoginRunner(scene.window, scene.monitor, clock=lambda: scene.now)
    scene.adapter.retryable = lambda error: True
    scene.replies = [PanError('PAN_API_REJECTED')]
    with pytest.raises(PanError):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll', 'begin', 'poll']


@pytest.mark.parametrize('phase', ['exchange', 'identity', 'https://fixture.invalid/private', None])
def test_error_phase_and_diagnostics_only_use_fixed_allowlists(scene, phase):
    scene.adapter.phase = phase
    error = PanError('PAN_API_REJECTED')
    scene.replies = [error]
    with pytest.raises(PanError):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.runner.diagnostic(error) == dict(
        phase=phase if phase in ('exchange', 'identity') else 'confirm',
        code='PAN_API_REJECTED', commit_sent=False, commit_acknowledged=False)


@pytest.mark.parametrize('phase', ['confirm', 'exchange', 'identity', 'private-fixture'])
def test_structured_retry_phase_never_displays_untrusted_text(scene, phase):
    scene.replies = [dict(state='retry', phase=phase), dict(state='ready')]
    assert scene.runner.run(scene.adapter, scene.render)
    assert 'private-fixture' not in repr(scene.statuses)


@pytest.mark.parametrize('result', [None, [], dict(state='failed'), dict(state='unexpected'), dict(state=True)])
def test_invalid_poll_state_is_terminal_without_commit(scene, result):
    scene.replies = [result]
    with pytest.raises(LoginFlowError, match='INVALID_STATE'):
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll']


@pytest.mark.parametrize('result', [None, [], dict(state='ready'), dict(state='waiting'), dict(state='waiting', qr=123)])
def test_invalid_begin_state_never_renders_or_polls(scene, result):
    scene.adapter.begin = lambda: result
    with pytest.raises(LoginFlowError, match='INVALID_STATE'):
        scene.runner.run(scene.adapter, scene.render)
    assert not scene.rendered and not scene.calls


def test_cancel_from_render_has_no_poll_or_commit(scene):
    def render(state):
        scene.window.cancelled = True
    assert scene.runner.run(scene.adapter, render) is False
    assert scene.calls == ['begin']


@pytest.mark.parametrize('result', [None, dict(state='ready'), dict(state='failed')])
def test_noncommitted_reply_is_uncertain_and_commit_is_never_repeated(scene, result):
    def commit():
        scene.calls.append('commit')
        return result
    scene.adapter.commit = commit
    with pytest.raises(LoginFlowError, match='COMMIT_UNCONFIRMED') as caught:
        scene.runner.run(scene.adapter, scene.render)
    assert scene.calls == ['begin', 'poll', 'commit']
    assert scene.runner.diagnostic(caught.value) == dict(phase='commit', code='COMMIT_UNCONFIRMED',
        commit_sent=True, commit_acknowledged=False)


def test_commit_exception_never_retries_and_does_not_claim_saved_or_unchanged(scene):
    error = TimeoutError('private-fixture')
    def commit():
        scene.calls.append('commit')
        raise error
    scene.adapter.commit = commit
    with pytest.raises(TimeoutError) as caught:
        scene.runner.run(scene.adapter, scene.render)
    assert caught.value is error
    assert scene.calls == ['begin', 'poll', 'commit']
    assert scene.runner.diagnostic(error) == dict(phase='commit', code='UNKNOWN',
        commit_sent=True, commit_acknowledged=False)


def test_ack_after_commit_dispatch_wins_over_late_cancel_and_deadline(scene):
    def commit():
        scene.calls.append('commit')
        scene.window.cancelled = True
        scene.now += 200
        return dict(state='committed')
    scene.adapter.commit = commit
    assert scene.runner.run(scene.adapter, scene.render) is True
    assert scene.runner.commit_acknowledged


def test_unknown_diagnostics_never_format_exception_or_output_untrusted_code(scene):
    class SecretError(Exception):
        def __str__(self): raise AssertionError('Do not format exception')
        def __repr__(self): raise AssertionError('Do not format exception')
    for error in (SecretError(), PanError('private-fixture'), CloudError('private-fixture')):
        assert scene.runner.diagnostic(error)['code'] == 'UNKNOWN'
    assert LoginFlowError('private-fixture').code == 'INVALID_STATE'
    assert not is_retryable(SecretError())
