"""UI-only EOF permission; simulated authority, never hardware acceptance."""
from uuid import uuid4

import pytest

from test_playback_authority import bind, playing, row, select
from test_native_continuation_account_guard import credentials, scoped


def reserve(authority, native, parent, account=None, child=None):
    return authority.dispatch(dict(parent, operation='reserve_next_picker',
        native_instance=native.current['native_instance'] if native.current else authority.last_native['native_instance'],
        child_request_id=child or uuid4().hex,
        **({'account_scope': account} if account is not None else {})))


def child_args(result):
    snapshot = result['snapshot']
    return dict(boot_id=snapshot['boot_id'], epoch=snapshot['epoch'],
                request_id=snapshot['desired']['request_id'])


def ended():
    authority, native, parent = playing()
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    return authority, native, parent


def status(authority, child):
    return authority.dispatch(dict(child, operation='next_picker_status'))


@pytest.mark.parametrize('destroyed', [False, True])
def test_eof_reserves_one_ui_only_request_before_slow_search(destroyed, monkeypatch):
    import lib.cinema.playback_authority as module
    clock = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    authority, native, parent = ended()
    authority.refresh()
    if destroyed:
        native.current = None
    result = reserve(authority, native, parent)
    assert result['reserved']
    child = child_args(result)
    assert result['snapshot']['desired']['selection_identity'] == 'next-picker:' + parent['request_id']
    assert result['snapshot']['terminal']['consumed']
    clock[0] += 60  # Search is not allowed to renew/reconsume the old EOF.
    assert status(authority, child)['allowed']
    assert not reserve(authority, native, parent)['reserved']
    assert native.commands == [] and native.gui_commands == []


def test_expired_cached_eof_cannot_create_picker(monkeypatch):
    import lib.cinema.playback_authority as module
    clock = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    authority, native, parent = ended()
    authority.refresh()
    native.current = None
    clock[0] += 3.01
    assert reserve(authority, native, parent) == {'reserved': False}
    assert not authority.owner.terminal['consumed']


@pytest.mark.parametrize('change', ['playing', 'STOP', 'ERROR', 'cancel', 'new-selection',
                                    'wrong-instance', 'wrong-request', 'user-confirmed', 'unknown-gui'])
def test_non_exact_natural_end_never_grants_picker(change):
    authority, native, parent = ended()
    if change == 'playing': native.current.update(phase='AV_STARTED')
    elif change in ('STOP', 'ERROR'): native.current['reason'] = change
    elif change == 'cancel': authority.dispatch(dict(parent, operation='cancel'))
    elif change == 'new-selection': select(authority, 'new-source')
    elif change == 'wrong-instance': native.current['native_instance'] = str(uuid4())
    elif change == 'wrong-request': native.current['request_id'] = uuid4().hex
    elif change == 'user-confirmed': authority.owner.desired['file_evidence'] = 'USER_CONFIRMED_FILE'
    elif change == 'unknown-gui': native.gui['gui_user_intent'] = None
    assert not reserve(authority, native, parent)['reserved']
    assert authority.next_picker is None


@pytest.mark.parametrize('operation', ['bind_file', 'claim_start', 'claim_status'])
def test_picker_placeholder_can_never_bind_or_start_media(operation):
    authority, native, parent = ended()
    result = reserve(authority, native, parent)
    child = child_args(result)
    command = dict(child, operation=operation, selection_identity='next-picker:' + parent['request_id'],
                   file_identity='file-b', url_sha256='b' * 64, route='player_play', claim_id=uuid4().hex)
    response = authority.dispatch(command)
    assert response == ({'bound': False} if operation == 'bind_file' else {'status': 'UI_ONLY'})
    assert not authority.owner.desired['file_bound'] and not authority.owner.desired['start_claimed']
    assert native.commands == []


@pytest.mark.parametrize('change', ['cancel', 'new-selection', 'gui', 'epoch', 'external', 'boot',
                                    'wrong-child', 'terminal-intent'])
def test_late_picker_status_fails_closed_after_changed_owner_or_user(change):
    authority, native, parent = ended()
    child = child_args(reserve(authority, native, parent))
    if change == 'cancel': authority.dispatch(dict(child, operation='cancel'))
    elif change == 'new-selection': select(authority, 'new-source')
    elif change == 'gui': native.gui['gui_user_intent'] += 1
    elif change == 'epoch': native.epoch += 1
    elif change == 'external': native.current = row('f' * 32, 'external')
    elif change == 'boot': child['boot_id'] = 'old'
    elif change == 'wrong-child': child['request_id'] = uuid4().hex
    elif change == 'terminal-intent': native.current['user_intent'] += 1
    assert not status(authority, child)['allowed']
    assert native.commands == []


def test_unknown_native_state_does_not_reauthorize_picker(monkeypatch):
    authority, native, parent = ended()
    child = child_args(reserve(authority, native, parent))
    original = native.state
    monkeypatch.setattr(native, 'state', lambda: {k: v for k, v in original().items() if k != 'playback'})
    with pytest.raises(RuntimeError): status(authority, child)


def test_observed_external_playback_revocation_cannot_reopen_after_it_stops():
    authority, native, parent = ended()
    child = child_args(reserve(authority, native, parent))
    native.current = row('f' * 32, 'external')
    assert not status(authority, child)['allowed']
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    authority.refresh()
    native.current = None
    assert not status(authority, child)['allowed']
    assert authority.next_picker is None and native.commands == []


def test_manual_source_selection_supersedes_permit_and_old_cancel_is_harmless():
    authority, native, parent = ended()
    child = child_args(reserve(authority, native, parent))
    snapshot = status(authority, child)['snapshot']
    request = uuid4().hex
    selected = authority.dispatch(dict(operation='select', boot_id=snapshot['boot_id'], epoch=snapshot['epoch'],
                                      request_id=request, selection_identity='release-a'))
    manual = dict(boot_id=selected['boot_id'], epoch=selected['epoch'], request_id=request)
    assert authority.next_picker is None
    assert not authority.dispatch(dict(child, operation='cancel'))['cancelled']
    assert not status(authority, child)['allowed']
    assert not authority.owner.desired['cancelled']
    bind(authority, manual)
    assert authority.dispatch(dict(manual, operation='claim_start', route='player_play'))['status'] == 'CLAIMED'
    assert native.commands == []


@pytest.mark.parametrize('when', ['before-reserve', 'after-reserve'])
@pytest.mark.parametrize('mutation', ['switch', 'logout', 'logout-login'])
def test_account_generation_change_revokes_picker(tmp_path, when, mutation):
    authority, native, parent, manager, account = scoped(tmp_path)
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    child = child_args(reserve(authority, native, parent, account)) if when == 'after-reserve' else None
    if mutation == 'switch': manager.install(credentials('456'), account)
    else:
        out = manager.logout(account)
        if mutation == 'logout-login': manager.install(credentials(), out)
    with pytest.raises(RuntimeError):
        if child: status(authority, child)
        else: reserve(authority, native, parent, account)
    assert native.commands == []


def test_same_account_refresh_preserves_picker_and_revocation_cannot_stop_new_source(tmp_path):
    authority, native, parent, manager, account = scoped(tmp_path)
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    child = child_args(reserve(authority, native, parent, account))
    assert manager.install(credentials(suffix='renewed'), account) == account
    assert status(authority, child)['allowed']
    select(authority, 'manual-new')
    native.current = row('f' * 32, 'external')
    manager.logout(account)
    assert not authority.account_changed()
    assert native.commands == []


@pytest.mark.parametrize('child', [None, 'short', 'a' * 31, 'z' * 32])
def test_invalid_child_id_does_not_consume_terminal(child):
    authority, native, parent = ended()
    with pytest.raises(ValueError):
        authority.dispatch(dict(parent, operation='reserve_next_picker', child_request_id=child,
                                 native_instance=native.current['native_instance']))
    assert not authority.owner.terminal['consumed']


def test_selection_epoch_failure_consumes_eof_without_ui_or_start(monkeypatch):
    authority, native, parent = ended()
    monkeypatch.setattr(native, 'intent', lambda command: {'reserved': False})
    with pytest.raises(RuntimeError): reserve(authority, native, parent)
    assert authority.owner.terminal['consumed'] and authority.next_picker is None
    assert authority.owner.desired['cancelled'] and native.commands == []


@pytest.mark.parametrize('applied', [False, True])
def test_lost_native_reservation_reply_never_turns_placeholder_into_playback(monkeypatch, applied):
    authority, native, parent = ended()
    original = native.intent
    def lost(command):
        if applied:
            original(command)
        raise OSError('lost native selection receipt')
    monkeypatch.setattr(native, 'intent', lost)
    with pytest.raises(OSError): reserve(authority, native, parent)
    snapshot = authority.owner.snapshot()
    child = child_args({'snapshot': snapshot})
    assert not status(authority, child)['allowed']
    assert authority.dispatch(dict(child, operation='bind_file', selection_identity='next-picker:' + parent['request_id'],
        file_identity='file', url_sha256='b' * 64)) == {'bound': False}
    assert authority.dispatch(dict(child, operation='claim_start', route='player_play')) == {'status': 'UI_ONLY'}
    assert authority.next_picker is None and native.commands == []


def test_gui_input_during_native_reservation_blocks_first_display(monkeypatch):
    authority, native, parent = ended()
    original = native.intent
    def changed(command):
        native.gui['gui_user_intent'] += 1
        return original(command)
    monkeypatch.setattr(native, 'intent', changed)
    child = child_args(reserve(authority, native, parent))
    assert not status(authority, child)['allowed']


def test_picker_admission_uses_existing_account_lock(tmp_path, monkeypatch):
    authority, native, parent, manager, account = scoped(tmp_path)
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    original = native.intent
    locks = []
    def checked(command):
        locks.append(manager.lock._is_owned())
        return original(command)
    monkeypatch.setattr(native, 'intent', checked)
    child = child_args(reserve(authority, native, parent, account))
    assert status(authority, child)['allowed'] and locks == [True]


def test_account_independent_bt_parent_captures_eof_account_for_picker(tmp_path):
    authority, native, parent, manager, account = scoped(tmp_path)
    assert authority.selection_account is None
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    reserved = reserve(authority, native, parent)
    child = child_args(reserved)
    assert reserved['account_scope'] == account
    reserved['account_scope']['epoch'] += 1  # Returned metadata cannot mutate authority.
    assert authority.selection_account == account
    assert status(authority, child)['allowed']
    manager.install(credentials('456'), account)
    with pytest.raises(RuntimeError): status(authority, child)
    assert native.commands == []
