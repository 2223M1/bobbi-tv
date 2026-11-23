"""Real account-generation lock around native continuation admission."""
from copy import deepcopy
from uuid import uuid4

import pytest

from bobbi_platform.account_manager import AccountManager, AccountError
from test_playback_authority import playing, row, select


def credentials(uid='123', suffix='first'):
    return dict(app='os_linux', cookies=dict(UID=uid + '_' + suffix, CID='fixture', SEID='fixture'))


def scoped(tmp_path):
    authority, native, args = playing()
    manager = AccountManager(tmp_path / 'account.json')
    account = manager.install(credentials(), manager.snapshot())
    authority.configure_accounts(manager)
    return authority, native, args, manager, account


def authorize(authority, native, args, account, manual=False):
    if not manual:
        native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    return authority.dispatch(dict(args, operation='manual_next' if manual else 'authorize_next',
        native_instance=native.current['native_instance'], selection_identity='next', account_scope=account))


def reserve(authority, args, grant, account):
    return authority.dispatch(dict(args, operation='reserve_child', selection_identity='next',
        token=grant['token'], child_request_id=uuid4().hex, account_scope=account))


@pytest.mark.parametrize('mutation', ['switch', 'logout', 'logout_login'])
def test_switch_between_proof_and_authorize_cannot_queue_stop(tmp_path, mutation):
    authority, native, args, manager, account = scoped(tmp_path)
    if mutation == 'switch':
        manager.install(credentials('456'), account)
    else:
        out = manager.logout(account)
        if mutation == 'logout_login':
            manager.install(credentials(), out)
    with pytest.raises(AccountError):
        authorize(authority, native, args, account, manual=True)
    assert native.commands == [] and authority.continuation is None


def test_renew_same_account_keeps_exact_grant(tmp_path):
    authority, native, args, manager, account = scoped(tmp_path)
    grant = authorize(authority, native, args, account)
    assert manager.install(credentials(suffix='renewed'), account) == account
    state = reserve(authority, args, grant, account)
    assert state['desired']['selection_identity'] == 'next'
    assert authority.selection_account == account


@pytest.mark.parametrize('wrong', ['omitted', 'new_scope', 'old_scope_after_logout'])
def test_child_requires_original_still_current_grant_account(tmp_path, wrong):
    authority, native, args, manager, account = scoped(tmp_path)
    grant = authorize(authority, native, args, account)
    scope = None if wrong == 'omitted' else account
    if wrong != 'omitted':
        new = manager.install(credentials('456'), account)
        if wrong == 'new_scope':
            scope = new
    epoch = native.epoch
    with pytest.raises(RuntimeError):
        reserve(authority, args, grant, scope)
    assert native.epoch == epoch


def test_reserved_child_bind_and_claim_cannot_drop_account_guard(tmp_path):
    authority, native, args, manager, account = scoped(tmp_path)
    grant = authorize(authority, native, args, account)
    state = reserve(authority, args, grant, account)
    child = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=state['desired']['request_id'])
    manager.logout(account)
    for command in (dict(operation='bind_file', selection_identity='next', file_identity='next|file', url_sha256='b' * 64),
                    dict(operation='claim_start', route='player_play')):
        with pytest.raises(AccountError):
            authority.dispatch(dict(child, **command))
    assert authority.owner.desired['start_claimed'] is False


def test_revoke_pending_grant_does_not_stop_independent_bt(tmp_path):
    authority, native, args, manager, account = scoped(tmp_path)
    grant = authorize(authority, native, args, account, manual=True)
    count = len(native.commands)
    manager.logout(account)
    assert authority.account_changed()
    assert len(native.commands) == count
    assert authority.continuation is None
    assert authority.owner.desired['cancelled']


def test_revoke_open_cloud_child_stops_only_matching_instance(tmp_path):
    authority, native, args, manager, account = scoped(tmp_path)
    state = reserve(authority, args, authorize(authority, native, args, account), account)
    child = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=state['desired']['request_id'])
    assert authority.dispatch(dict(child, operation='bind_file', selection_identity='next',
        file_identity='next|file', url_sha256='b' * 64))['bound']
    assert authority.dispatch(dict(child, operation='claim_start', route='player_play'))['status'] == 'CLAIMED'
    native.current = row(child['request_id'], 'next|file', url_sha256='b' * 64)
    authority.refresh()
    manager.logout(account)
    assert authority.account_changed()
    assert native.commands[-1]['action'] == 'stop'
    assert native.commands[-1]['native_instance'] == native.current['native_instance']


def test_late_revocation_never_stops_new_manual_selection(tmp_path):
    authority, native, args, manager, account = scoped(tmp_path)
    reserve(authority, args, authorize(authority, native, args, account), account)
    select(authority, 'external-new')
    native.current = row('c' * 32, 'external', url_sha256='c' * 64)
    before = deepcopy(native.commands)
    manager.logout(account)
    assert not authority.account_changed()
    assert native.commands == before


def test_command_admission_holds_existing_account_lock(tmp_path, monkeypatch):
    authority, native, args, manager, account = scoped(tmp_path)
    original = native.control
    observed = []
    def checked(command):
        observed.append(manager.lock._is_owned())
        return original(command)
    monkeypatch.setattr(native, 'control', checked)
    assert authorize(authority, native, args, account, manual=True)['authorized']
    assert observed == [True]


@pytest.mark.parametrize('applied', [False, True])
def test_revocation_barrier_lost_reply_is_reconciled_after_owner_cancel(tmp_path, monkeypatch, applied):
    authority, native, args, manager, account = scoped(tmp_path)
    authorize(authority, native, args, account, manual=True)
    original = native.intent
    calls = []
    def lost(value):
        calls.append(deepcopy(value))
        if len(calls) == 1:
            if applied:
                original(value)
            raise OSError('lost')
        return original(value)
    monkeypatch.setattr(native, 'intent', lost)
    epoch = native.epoch
    manager.logout(account)
    with pytest.raises(OSError):
        authority.account_changed()
    assert authority.owner.desired['cancelled']
    assert authority.account_changed()
    assert authority.account_revocation is None and native.epoch == epoch + 1
    assert len(calls) == (1 if applied else 2)


def test_lost_applied_revoke_still_stops_exact_old_cloud_child(tmp_path, monkeypatch):
    authority, native, args, manager, account = scoped(tmp_path)
    state = reserve(authority, args, authorize(authority, native, args, account), account)
    child = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=state['desired']['request_id'])
    assert authority.dispatch(dict(child, operation='bind_file', selection_identity='next',
        file_identity='next|file', url_sha256='b' * 64))['bound']
    authority.dispatch(dict(child, operation='claim_start', route='player_play'))
    native.current = row(child['request_id'], 'next|file', url_sha256='b' * 64)
    authority.refresh()
    old = native.intent
    def lost(value):
        old(value)
        raise OSError('applied but reply lost')
    monkeypatch.setattr(native, 'intent', lost)
    manager.logout(account)
    with pytest.raises(OSError): authority.account_changed()
    assert authority.account_changed()
    assert len(native.commands) == 1
    assert native.commands[0]['native_instance'] == native.current['native_instance']
    assert native.commands[0]['action'] == 'stop'
