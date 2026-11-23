"""Binding uses a validated guard without caching per-call authorization."""
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from types import ModuleType, SimpleNamespace
from urllib.parse import urlsplit

import pytest

from test_accounts import credential, logged_in
from test_account_streams import body, stream
from bobbi_platform import account_manager
from bobbi_core.share_stream import Binding, checked_diagnostic, observation_fields

DIAGNOSTIC = dict(mode='open_range_bound_guard', seconds=60)
MODES = [None, 'open_range', 'open_range_microbatch', 'open_range_bound_guard',
         'block_startup_1m', 'block_timing']


def diagnostic(mode):
    return dict(mode=mode, seconds=60) if mode else None


class UnprintableGuard:
    def __repr__(self):
        raise AssertionError('Invalid guard must not be formatted into an error')
    __str__ = __repr__


def test_bound_guard_mode_is_explicit_and_has_safe_observation_name():
    assert checked_diagnostic(DIAGNOSTIC) == DIAGNOSTIC
    assert observation_fields(dict(diagnostic_mode=DIAGNOSTIC['mode'])) == {
        'diagnostic_mode': DIAGNOSTIC['mode']}


@pytest.mark.parametrize('mode', MODES)
def test_guard_binding_admission_is_once_but_account_comparison_stays_live(tmp_path, monkeypatch, mode):
    manager, scope = logged_in(tmp_path)
    service = stream(manager)
    entry = None
    calls = []
    original = manager.current_guard
    def guard(value):
        calls.append(dict(value))
        return original(value)
    monkeypatch.setattr(manager, 'current_guard', guard)
    try:
        def register():
            return (service.register_diagnostic(body(), scope, diagnostic(mode)) if mode
                    else service.register(body(), account=scope))
        ready, same = register(), register()
        assert ready == same and calls == [scope]
        entry = service.acquire(urlsplit(ready['url']).path)
        def old_path(value):
            pytest.fail('Binding repeats structural validation')
        monkeypatch.setattr(manager, 'is_current', old_path)
        assert entry.cancelled() is False
        service.unsubscribe()  # Even a missing revoke listener cannot preserve authorization.
        current = manager.install(credential(suffix='A2_new'), scope)
        assert entry.cancelled() is False
        manager.logout(current)
        assert entry.cancelled() is True
    finally:
        if entry is not None: service.release(entry)
        service.close()


@pytest.mark.parametrize('mode', [mode for mode in MODES if mode != 'open_range_bound_guard'])
@pytest.mark.parametrize('capability', ['absent', 'noncallable'])
def test_adapters_without_guard_keep_every_live_account_check(tmp_path, mode, capability):
    manager, scope = logged_in(tmp_path)
    calls = []
    adapter = SimpleNamespace(is_current=lambda value: (calls.append(dict(value)), manager.is_current(value))[1])
    if capability == 'noncallable':
        adapter.current_guard = None
    entry = Binding(body(), lambda *args: '', lambda value: True,
                    account=adapter, scope=scope, diagnostic=diagnostic(mode))
    for _ in range(20):
        assert entry.cancelled() is False
    manager.logout(scope)
    assert entry.cancelled() is True and calls == [scope]*21


@pytest.mark.parametrize('account', [None, SimpleNamespace(current_guard=None)])
def test_guard_mode_refuses_unavailable_account_protocol(account):
    with pytest.raises(ValueError, match='SHARE_DIAGNOSTIC_INVALID'):
        Binding(body(), lambda *args: '', lambda value: True, account=account, diagnostic=DIAGNOSTIC)


@pytest.mark.parametrize('mode', MODES)
def test_guard_factory_failure_is_not_silently_downgraded(tmp_path, monkeypatch, mode):
    manager, scope = logged_in(tmp_path)
    def fail(value):
        raise account_manager.AccountError('ACCOUNT_CHANGED')
    monkeypatch.setattr(manager, 'current_guard', fail)
    monkeypatch.setattr(manager, 'is_current', lambda _: pytest.fail('Must not bypass a failed guard'))
    with pytest.raises(account_manager.AccountError, match='ACCOUNT_CHANGED'):
        Binding(body(), lambda *args: '', lambda value: True,
                account=manager, scope=scope, diagnostic=diagnostic(mode))


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('invalid_guard', [None, False, True, 0, object(),
                                         'https://private.invalid/?token=secret', UnprintableGuard()],
                         ids=['none', 'false', 'true', 'zero', 'object', 'private-string', 'unprintable'])
def test_invalid_guard_return_is_rejected_during_binding_construction(
        tmp_path, monkeypatch, mode, invalid_guard):
    manager, scope = logged_in(tmp_path)
    captured = []
    def factory(value):
        captured.append(dict(value))
        return invalid_guard
    monkeypatch.setattr(manager, 'current_guard', factory)
    monkeypatch.setattr(manager, 'is_current', lambda _: pytest.fail('Must not bypass an invalid guard'))
    with pytest.raises(ValueError) as failure:
        Binding(body(), lambda *args: pytest.fail('Must not resolve'), lambda value: True,
                account=manager, scope=scope, diagnostic=diagnostic(mode))
    assert str(failure.value) == 'SHARE_ACCOUNT_GUARD_INVALID'
    assert captured == [scope]


@pytest.mark.parametrize('mode', MODES)
def test_falsey_callable_guard_is_valid_and_remains_live(tmp_path, monkeypatch, mode):
    manager, scope = logged_in(tmp_path)
    live = manager.current_guard(scope)
    checks = []
    class Guard:
        def __bool__(self):
            return False
        def __call__(self):
            checks.append(True)
            return live()
    monkeypatch.setattr(manager, 'current_guard', lambda value: Guard())
    monkeypatch.setattr(manager, 'is_current', lambda _: pytest.fail('Must not bypass the guard'))
    entry = Binding(body(), lambda *args: '', lambda value: True,
                    account=manager, scope=scope, diagnostic=diagnostic(mode))
    assert entry.cancelled() is False
    manager.logout(scope)
    assert entry.cancelled() is True and len(checks) == 2


@pytest.mark.parametrize('mode', [None, 'block_timing'])
def test_registration_cannot_publish_binding_with_invalid_guard(tmp_path, monkeypatch, mode):
    manager, scope = logged_in(tmp_path)
    service = stream(manager, resolver=lambda *args: pytest.fail('Must not resolve'))
    monkeypatch.setattr(manager, 'current_guard', lambda value: None)
    monkeypatch.setattr(manager, 'is_current', lambda _: pytest.fail('Must not bypass an invalid guard'))
    try:
        with pytest.raises(ValueError, match='^SHARE_ACCOUNT_GUARD_INVALID$'):
            if mode:
                service.register_diagnostic(body(), scope, diagnostic(mode))
            else:
                service.register(body(), account=scope)
        assert not service.records
    finally:
        service.close()


@pytest.mark.parametrize('mode', [None, 'block_timing', 'open_range_bound_guard'])
def test_bound_guard_does_not_publish_a_late_grant_after_switch(tmp_path, mode):
    manager, scope = logged_in(tmp_path)
    entered, finish = Event(), Event()
    failures = []
    def resolve(*args):
        entered.set()
        assert finish.wait(2)
        return 'https://fixture.115cdn.com/video|User-Agent=fixture'
    entry = Binding(body(), resolve, lambda value: True, account=manager,
                    scope=scope, diagnostic=diagnostic(mode))
    def run():
        try: entry.grant()
        except Exception as error: failures.append(type(error))
    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(1)
        manager.install(credential('456'), scope)
    finally:
        finish.set()
        worker.join(2)
    assert not worker.is_alive() and failures == [OSError] and entry.address is None


@pytest.mark.parametrize('mode', [None, 'block_timing'])
def test_caller_mutation_and_failed_listener_cannot_retarget_guard(tmp_path, mode):
    manager, scope = logged_in(tmp_path)
    caller = dict(scope)
    entry = Binding(body(), lambda *args: '', lambda value: True,
                    account=manager, scope=caller, diagnostic=diagnostic(mode))
    def broken(*args):
        raise RuntimeError('fixture listener')
    manager.subscribe(broken)
    caller.update(epoch=99, account_id='115:' + 'f'*64)
    assert entry.cancelled() is False and entry.scope == scope
    other = manager.install(credential('456'), scope)
    caller.update(other)
    assert entry.cancelled() is True and not entry.revoked.is_set()
    returned = manager.install(credential(), other)
    caller.update(returned)
    assert returned['account_id'] == scope['account_id'] and returned['epoch'] != scope['epoch']
    assert entry.cancelled() is True and not entry.revoked.is_set()


@pytest.fixture(scope='module')
def frozen_binding():
    # Pre-change integrated source: the negative control must exercise the
    # actual old Binding, not emulate its repeated validation with a stub.
    revision = 'ff0422cff75b58b72053898057d8b87356eea85c'
    source = subprocess.check_output(['git', 'show', revision + ':' +
        'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py'],
        cwd=Path(__file__).resolve().parents[1])
    name = '_frozen_binding_current_guard_baseline'
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, '<frozen-binding-current-guard-baseline>', 'exec'), module.__dict__)
        yield module.Binding
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize('mode', [None, 'block_timing'])
def test_actual_old_source_revalidates_but_candidate_checks_live_scope_without_revalidation(
        tmp_path, monkeypatch, frozen_binding, mode):
    manager, scope = logged_in(tmp_path)
    validations, lock_entries = [], []
    original_validate, original_lock = account_manager.validate_snapshot, manager.lock
    def validate(value, *args, **kwargs):
        validations.append(dict(value))
        return original_validate(value, *args, **kwargs)
    class CountLock:
        def __enter__(self):
            original_lock.acquire()
            lock_entries.append(True)
        def __exit__(self, *args):
            original_lock.release()
    monkeypatch.setattr(account_manager, 'validate_snapshot', validate)
    monkeypatch.setattr(manager, 'lock', CountLock())
    counts = []
    for binding in (frozen_binding, Binding):
        validations.clear()
        lock_entries.clear()
        entry = binding(body(), lambda *args: '', lambda value: True,
                        account=manager, scope=scope, diagnostic=diagnostic(mode))
        admission_locks = len(lock_entries)
        for _ in range(1000):
            assert entry.cancelled() is False
        assert len(lock_entries)-admission_locks == 1000
        counts.append(len(validations))
    assert counts == [1000, 1]  # Structural work only; no elapsed-time/speed claim.
