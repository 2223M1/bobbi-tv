"""Validated once does not mean authorized once: every read checks current scope."""
from threading import Event, Thread

import pytest

from bobbi_platform import account_manager
from bobbi_platform.account_manager import AccountError
from test_accounts import credential, logged_in


def test_guard_copies_input_and_checks_existing_authority_on_every_call(tmp_path, monkeypatch):
    manager, scope = logged_in(tmp_path)
    caller = dict(scope)
    calls = []
    original = account_manager.validate_snapshot
    def validated(value, *args, **kwargs):
        calls.append(dict(value))
        return original(value, *args, **kwargs)
    monkeypatch.setattr(account_manager, 'validate_snapshot', validated)
    guard = manager.current_guard(caller)
    assert guard() is True
    caller.update(account_id='115:' + 'f' * 64, epoch=99)
    for _ in range(20):
        assert guard() is True
    assert len(calls) == 1
    other = manager.install(credential('456'), scope)
    caller.update(other)
    assert guard() is False
    returned = manager.install(credential(), other)
    assert returned['account_id'] == scope['account_id']
    assert returned['epoch'] != scope['epoch'] and guard() is False


def test_same_account_renewal_preserves_guard_logout_does_not(tmp_path):
    manager, scope = logged_in(tmp_path)
    guard = manager.current_guard(scope)
    current = manager.install(credential(suffix='A2_new'), scope)
    assert current == scope and guard() is True
    manager.logout(current)
    assert guard() is False


def test_broken_listener_cannot_authorize_old_scope(tmp_path):
    manager, scope = logged_in(tmp_path)
    guard = manager.current_guard(scope)
    def broken(*args):
        raise RuntimeError('fixture listener')
    manager.subscribe(broken)
    manager.install(credential('456'), scope)
    assert guard() is False


def test_failed_storage_keeps_actual_generation(tmp_path, monkeypatch):
    manager, scope = logged_in(tmp_path)
    guard = manager.current_guard(scope)
    def fail(*args):
        raise OSError('fixture storage failure')
    monkeypatch.setattr(account_manager, '_write', fail)
    with pytest.raises(OSError):
        manager.logout(scope)
    assert guard() is True and manager.snapshot() == scope


def test_guard_creation_rejects_stale_or_invalid_scope(tmp_path):
    manager, scope = logged_in(tmp_path)
    manager.logout(scope)
    with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
        manager.current_guard(scope)
    with pytest.raises(AccountError, match='ACCOUNT_SCOPE_INVALID'):
        manager.current_guard(dict(scope, epoch=True))


def test_guard_uses_existing_lock_not_a_cached_true(tmp_path):
    manager, scope = logged_in(tmp_path)
    guard = manager.current_guard(scope)
    entered, finished = Event(), Event()
    results = []
    def check():
        entered.set()
        results.append(guard())
        finished.set()
    worker = Thread(target=check)
    with manager.lock:
        worker.start()
        assert entered.wait(1)
        assert not finished.wait(.05)
        manager.logout(scope)
    worker.join(2)
    assert not worker.is_alive() and results == [False]


def test_switch_after_creation_before_first_call_revokes(tmp_path):
    manager, scope = logged_in(tmp_path)
    guard = manager.current_guard(scope)
    manager.install(credential('456'), scope)
    assert guard() is False
