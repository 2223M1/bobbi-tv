import json
from pathlib import Path
import sys
from threading import Event, Thread

import pytest

from bobbi_platform.account_manager import AccountManager, AccountError, account_id, validate_snapshot
from bobbi_platform.cloud115 import load, save

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))


def credential(user='123', suffix='A1_old', seid='fixture-seid'):
    return {'app': 'os_linux', 'cookies': {'UID': user + '_' + suffix, 'CID': 'fixture-cid', 'SEID': seid}}


def logged_in(tmp_path):
    manager = AccountManager(tmp_path / '115-os_linux.json')
    scope = manager.install(credential(), manager.snapshot())
    return manager, scope


def test_empty_profile_is_unauthenticated_and_does_not_create_credentials(tmp_path):
    manager = AccountManager(tmp_path / 'account.json')
    assert manager.snapshot() == {'account_id': '', 'epoch': 0, 'authenticated': False}
    assert not manager.path.exists()
    with pytest.raises(AccountError):
        manager.credentials(manager.snapshot())


def test_same_account_renewal_keeps_epoch_and_does_not_revoke(tmp_path):
    manager, before = logged_in(tmp_path)
    revoked = []
    manager.subscribe(lambda *args: revoked.append(args))
    after = manager.install(credential(suffix='A2_new', seid='new-seid'), before)
    assert before == after
    assert revoked == []
    assert manager.credentials(before)['cookies']['SEID'] == 'new-seid'
    assert AccountManager(manager.path).snapshot() == before


def test_logout_and_return_to_same_account_never_revive_old_epoch(tmp_path):
    manager, a = logged_in(tmp_path)
    logged_out = manager.logout(a)
    assert logged_out == {'account_id': '', 'epoch': 2, 'authenticated': False}
    assert load(manager.path) is None
    assert 'cookies' not in json.loads(manager.path.read_text())
    restarted = AccountManager(manager.path)
    later_a = restarted.install(credential(), restarted.snapshot())
    assert later_a['account_id'] == a['account_id'] and later_a['epoch'] == 3
    assert not restarted.is_current(a)


def test_account_b_revokes_a_and_late_qr_cannot_overwrite_b(tmp_path):
    manager, a = logged_in(tmp_path)
    transitions = []
    manager.subscribe(lambda old, new: transitions.append((old, new)))
    b = manager.install(credential('456'), a)
    assert b['epoch'] == 2 and b['account_id'] != a['account_id']
    assert transitions == [(a, b)]
    with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
        manager.install(credential('789'), a)
    with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
        manager.logout(a)
    assert manager.snapshot() == b


def test_cancelled_task_cannot_publish_or_read_b_credentials(tmp_path):
    manager, a = logged_in(tmp_path)
    captured = manager.credentials(a)
    manager.install(credential('456'), a)
    assert captured['cookies']['UID'].startswith('123_')
    captured['cookies']['UID'] = '789_other'
    assert not manager.is_current(a)
    published = []
    with pytest.raises(AccountError):
        manager.run_if_current(a, lambda: published.append('stale'))
    with pytest.raises(AccountError):
        manager.credentials(a)
    assert published == []


def test_atomic_local_commit_serializes_with_switch(tmp_path):
    manager, a = logged_in(tmp_path)
    entered, finish, switched = Event(), Event(), Event()
    def commit():
        entered.set()
        assert finish.wait(2)
    worker = Thread(target=lambda: manager.run_if_current(a, commit))
    worker.start()
    assert entered.wait(1)
    switch = Thread(target=lambda: (manager.install(credential('456'), a), switched.set()))
    switch.start()
    assert not switched.wait(.05)
    finish.set()
    worker.join(2)
    switch.join(2)
    assert switched.is_set()


def test_invalid_credentials_and_failed_persistence_preserve_account(tmp_path, monkeypatch):
    from bobbi_platform import account_manager
    manager, a = logged_in(tmp_path)
    old = manager.path.read_bytes()
    with pytest.raises(AccountError):
        manager.install(credential('not-numeric'), a)
    def fail(*_):
        raise OSError('fixture failure')
    monkeypatch.setattr(account_manager, '_write', fail)
    with pytest.raises(OSError):
        manager.logout(a)
    assert manager.snapshot() == a and manager.path.read_bytes() == old


def test_existing_local_login_is_migrated_without_cookie_change(tmp_path):
    path = tmp_path / 'account.json'
    save(path, credential())
    before = load(path)
    manager = AccountManager(path)
    assert manager.snapshot()['epoch'] == 1
    assert load(path) == before
    assert 'cookies' not in manager.snapshot()


@pytest.mark.parametrize('change', [{'epoch': True}, {'epoch': -1}, {'authenticated': 1},
                                   {'account_id': '123'}, {'token': 'not-allowed'}])
def test_scope_validation_rejects_ambiguous_types_and_unknown_fields(change):
    with pytest.raises(AccountError):
        validate_snapshot(dict({'account_id': '', 'epoch': 0, 'authenticated': False}, **change))


def test_observer_failure_does_not_skip_stream_revocation(tmp_path):
    manager, a = logged_in(tmp_path)
    called = []
    def broken(*_):
        raise RuntimeError('fixture failure')
    manager.subscribe(broken)
    manager.subscribe(lambda *args: called.append(args))
    manager.logout(a)
    assert len(called) == 1


def test_share_client_uses_captured_account_not_later_file(tmp_path):
    from bobbi_catalog.api import Client, ShareError
    manager, a = logged_in(tmp_path)
    session = manager.credentials(a)
    b = manager.install(credential('456'), a)
    client = Client(session=session, account_scope=a)
    assert 'UID=123_' in client.cookie and '456_' not in client.cookie
    assert client.account_scope == a
    with pytest.raises(ShareError):
        Client(session=session, account_scope=b)
