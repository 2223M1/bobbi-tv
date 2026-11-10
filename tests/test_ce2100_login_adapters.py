"""115 runner adapter retains one account owner and discards abandoned work."""
from copy import deepcopy
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_platform import account_dialog, account_manager, cloud_ui, pan_ui
from bobbi_platform.cloud115 import CloudError
from bobbi_platform.login_flow import LoginRunner
from bobbi_platform.pan_accounts import empty_scope
from test_accounts import credential


@pytest.mark.parametrize('operation', ['begin', 'poll'])
def test_115_cancel_discards_late_begin_token_and_confirmed_credentials(monkeypatch, operation):
    entered, release, done = Event(), Event(), Event()
    job = {}
    class Flow:
        token, terminal, cancel_calls = 'fixture-pending', False, 0
        def begin(self):
            entered.set()
            assert release.wait(2)
            # Simulate a network reply rearming the protocol after cancellation.
            self.token, self.terminal = 'fixture-late-token', False
            return 'https://fixture.invalid/qr'
        def poll(self):
            entered.set()
            assert release.wait(2)
            return 'confirmed', credential('502')
        def cancel(self):
            self.token, self.terminal = None, True
            self.cancel_calls += 1
    flow = Flow()
    adapter = cloud_ui._LoginAdapter(flow, dict(account_id='', epoch=0, authenticated=False))
    def forbidden(*args, **kwargs):
        pytest.fail('An abandoned QR must not call the account owner')
    monkeypatch.setattr(cloud_ui, 'call', forbidden)
    def invoke():
        try:
            job['result'] = getattr(adapter, operation)()
        except Exception as error:
            job['error'] = error
        finally:
            done.set()
    worker = Thread(target=invoke, daemon=True)
    worker.start()
    try:
        assert entered.wait(1)
        adapter.cancel()
        assert adapter._saved is None and flow.token is None
    finally:
        release.set()
    assert done.wait(1)
    worker.join(1)
    assert 'error' not in job
    assert job['result'] == dict(state='cancelled')
    assert adapter._saved is None and flow.token is None and flow.terminal
    assert flow.cancel_calls == (2 if operation == 'begin' else 1)
    with pytest.raises(CloudError, match='QR_FINISHED'):
        adapter.commit()


@pytest.fixture
def owner_scene(tmp_path, monkeypatch):
    owner = account_manager.AccountManager(tmp_path / '115-os_linux.json')
    expected = owner.install(credential('501'), owner.snapshot())
    original = owner.path.read_bytes()
    next_credentials = credential('502')
    calls = []
    flow = SimpleNamespace(
        begin=lambda: 'https://fixture.invalid/qr',
        poll=lambda: ('confirmed', deepcopy(next_credentials)),
        cancel=lambda: None, phase='confirm', terminal=False)
    adapter = cloud_ui._LoginAdapter(flow, expected)
    def call(action, body):
        calls.append(action)
        assert action == 'account_install' and set(body) == {'credentials', 'expected'}
        assert body['expected'] == expected
        return owner.install(body['credentials'], body['expected'])
    monkeypatch.setattr(cloud_ui, 'call', call)
    return SimpleNamespace(owner=owner, expected=expected, original=original, adapter=adapter,
                           next_credentials=next_credentials, calls=calls)


def test_115_ready_does_not_persist_and_only_explicit_commit_changes_real_owner(owner_scene):
    s = owner_scene
    assert s.adapter.begin()['state'] == 'waiting'
    assert s.owner.path.read_bytes() == s.original and s.owner.snapshot() == s.expected
    assert s.adapter.poll() == dict(state='ready')
    assert s.owner.path.read_bytes() == s.original and s.owner.snapshot() == s.expected
    assert s.calls == []
    assert s.adapter.commit() == dict(state='committed')
    assert s.calls == ['account_install']
    assert s.owner.snapshot()['authenticated'] is True
    assert s.owner.snapshot()['account_id'] == account_manager.account_id(s.next_credentials)
    assert s.owner.path.read_bytes() != s.original
    s.adapter.cancel()
    assert s.adapter._saved is None


def test_115_cancel_after_ready_preserves_real_old_account_and_prevents_commit(owner_scene):
    s = owner_scene
    assert s.adapter.poll() == dict(state='ready')
    s.adapter.cancel()
    with pytest.raises(CloudError, match='QR_FINISHED'):
        s.adapter.commit()
    assert s.adapter._saved is None and s.calls == []
    assert s.owner.snapshot() == s.expected and s.owner.path.read_bytes() == s.original


def test_115_stale_ready_cannot_overwrite_real_owner_cas(owner_scene):
    s = owner_scene
    assert s.adapter.poll() == dict(state='ready')
    third = s.owner.install(credential('503'), s.expected)
    third_bytes = s.owner.path.read_bytes()
    with pytest.raises(account_manager.AccountError, match='ACCOUNT_CHANGED'):
        s.adapter.commit()
    assert s.calls == ['account_install']
    assert s.owner.snapshot() == third and s.owner.path.read_bytes() == third_bytes
    s.adapter.cancel()
    assert s.adapter._saved is None


def test_115_failed_atomic_save_preserves_real_owner_and_clears_pending_credentials(owner_scene, monkeypatch):
    s = owner_scene
    assert s.adapter.poll() == dict(state='ready')
    def failed_write(*args):
        raise OSError('synthetic-storage-failure')
    monkeypatch.setattr(account_manager, '_write', failed_write)
    with pytest.raises(OSError):
        s.adapter.commit()
    assert s.calls == ['account_install']
    assert s.owner.snapshot() == s.expected and s.owner.path.read_bytes() == s.original
    s.adapter.cancel()
    assert s.adapter._saved is None


@pytest.mark.parametrize('reply', [None, {}, dict(account_id='', epoch=1, authenticated=False)])
def test_115_commit_requires_valid_authenticated_owner_receipt(owner_scene, monkeypatch, reply):
    s = owner_scene
    assert s.adapter.poll() == dict(state='ready')
    def call(action, body):
        s.calls.append(action)
        return reply
    monkeypatch.setattr(cloud_ui, 'call', call)
    with pytest.raises(account_manager.AccountError):
        s.adapter.commit()
    assert s.calls == ['account_install']
    assert s.owner.snapshot() == s.expected and s.owner.path.read_bytes() == s.original
    s.adapter.cancel()
    assert s.adapter._saved is None


def test_115_runner_does_not_repoll_or_reexchange_after_ambiguous_exchange_failure(monkeypatch):
    calls, statuses = [], []
    class Flow:
        terminal, phase = False, 'prepare'
        def begin(self):
            calls.append('begin')
            self.phase = 'confirm'
            return 'https://fixture.invalid/qr'
        def poll(self):
            calls.append('poll')
            self.terminal, self.phase = True, 'exchange'
            raise CloudError('NETWORK_ERROR')
        def cancel(self):
            self.terminal = True
    adapter = cloud_ui._LoginAdapter(Flow(), dict(account_id='', epoch=0, authenticated=False))
    window = SimpleNamespace(cancelled=False, set_status=statuses.append)
    monitor = SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda seconds: False)
    runner = LoginRunner(window, monitor)
    monkeypatch.setattr(cloud_ui, 'call', lambda *a, **kw: pytest.fail('No commit after failed exchange'))
    try:
        with pytest.raises(CloudError) as caught:
            runner.run(adapter, lambda state: None)
        assert calls == ['begin', 'poll']
        assert runner.diagnostic(caught.value) == dict(phase='exchange', code='NETWORK_ERROR',
            commit_sent=False, commit_acknowledged=False)
        assert not any('正在重试' in value for value in statuses)
    finally:
        adapter.cancel()
    assert adapter._saved is None


@pytest.mark.parametrize('error', [RuntimeError('synthetic Kodi closed'), ValueError('synthetic bug')])
def test_safe_close_only_suppresses_kodi_runtime_error(error):
    calls = []
    def close():
        calls.append('close')
        raise error
    window = SimpleNamespace(close=close)
    if isinstance(error, RuntimeError):
        account_dialog.safe_close(window)
    else:
        with pytest.raises(ValueError) as caught:
            account_dialog.safe_close(window)
        assert caught.value is error
    assert calls == ['close']


def test_native_ipc_timeout_preserves_last_identity_phase(monkeypatch):
    calls = []
    def call(action, body, **kwargs):
        calls.append(action)
        if action == 'pan_login_begin':
            return dict(state='waiting', qr='https://fixture.invalid/qr')
        if calls.count('pan_login_poll') == 1:
            return dict(state='retry', phase='identity')
        raise TimeoutError('synthetic IPC failure without phase')
    monkeypatch.setattr(pan_ui, 'call', call)
    adapter = pan_ui._NativeLogin(dict(provider='quark', attempt='a' * 32), empty_scope('quark'))
    adapter.begin()
    assert adapter.poll() == dict(state='retry', phase='identity')
    assert adapter.phase == 'identity'
    with pytest.raises(TimeoutError):
        adapter.poll()
    assert adapter.phase == 'identity'
    assert calls == ['pan_login_begin', 'pan_login_poll', 'pan_login_poll']


def test_native_begin_transitions_to_confirm_once_before_poll(monkeypatch):
    monkeypatch.setattr(pan_ui, 'call', lambda *args, **kwargs:
        dict(state='waiting', qr='https://fixture.invalid/qr'))
    adapter = pan_ui._NativeLogin(dict(provider='quark', attempt='a' * 32), empty_scope('quark'))
    assert adapter.phase == 'prepare'
    assert adapter.begin()['state'] == 'waiting'
    assert adapter.phase == 'confirm'
