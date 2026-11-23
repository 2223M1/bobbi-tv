"""Reload recovery retains correlation, never a second playback authority."""
from copy import deepcopy
from uuid import uuid4

import pytest

from test_ce2097_phone_management import phone, pair, invoke
from test_phone_playback_scopes import scope


def admitted(phone):
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    pair(phone)
    return dict(expected=scope(), command_id=uuid4().hex, action='seek', params={'position_ms':1000})


def session(phone):
    return phone.manager.handle('/manage/api/session', phone.headers, b'{}')[0]


def test_reload_keeps_original_unknown_command_and_blocks_new_same_instance(phone):
    command = admitted(phone)
    phone.result = dict(status='queued', command_id=command['command_id'])
    invoke(phone, 'playback_command', command)
    recovered = session(phone)['playback_operations']
    assert recovered == [dict(command=command, status='queued')]
    recovered[0]['command']['expected']['epoch'] = 42
    assert session(phone)['playback_operations'][0]['command'] == command
    another = dict(command, command_id=uuid4().hex, expected=dict(command['expected'], expected_sequence=99))
    with pytest.raises(phone.module.PhoneError, match='PLAYBACK_PENDING'):
        invoke(phone, 'playback_command', another)
    assert len([body for action, body in phone.calls if action == 'playback']) == 1
    phone.result = dict(status='applied', command_id=command['command_id'])
    invoke(phone, 'playback_receipt', dict(expected=command['expected'], command_id=command['command_id']))
    assert session(phone)['playback_operations'][0]['status'] == 'applied'
    invoke(phone, 'playback_command', another)


def test_transport_loss_keeps_authorization_and_original_receipt_without_resend(phone):
    command = admitted(phone)
    original_rpc = phone.manager.rpc
    def transport(action, body, **kwargs):
        if action == 'playback' and body['operation'] == 'playback_command':
            phone.calls.append((action, deepcopy(body)))
            raise OSError('lost response after execution')
        return original_rpc(action, body, **kwargs)
    phone.manager.rpc = transport
    assert invoke(phone, 'playback_command', command) == dict(command_id=command['command_id'], status='unknown')
    assert session(phone)['playback_operations'] == [dict(command=command, status='unknown')]
    phone.result = dict(command_id=command['command_id'], status='applied')
    # A duplicate POST can only read the original receipt, even from another tab.
    assert invoke(phone, 'playback_command', command)['status'] == 'applied'
    operations = [body['operation'] for action, body in phone.calls if action == 'playback']
    assert operations == ['playback_command', 'playback_receipt']


def test_forget_requires_a_fresh_distinct_instance_and_never_controls_player(phone):
    command = admitted(phone)
    phone.result = dict(status='unknown')
    invoke(phone, 'playback_command', command)
    params = dict(expected=command['expected'], command_id=command['command_id'])
    for view in (dict(available=False), dict(available=True, expected=command['expected'])):
        phone.result = view
        with pytest.raises(phone.module.PhoneError, match='PLAYBACK_PENDING'):
            invoke(phone, 'playback_forget', params)
        assert len(session(phone)['playback_operations']) == 1
    phone.result = dict(available=True, expected=scope())
    assert invoke(phone, 'playback_forget', params) == dict(command_id=command['command_id'], status='forgotten')
    assert session(phone)['playback_operations'] == []
    assert [body['operation'] for action, body in phone.calls if action == 'playback'] == [
        'playback_command', 'playback_presentation', 'playback_presentation', 'playback_presentation']


def test_bounded_journal_cannot_discard_unknown_and_revocation_clears_it(phone):
    command = admitted(phone)
    phone.result = dict(status='unknown')
    for _ in range(8):
        invoke(phone, 'playback_command', dict(command, command_id=uuid4().hex, expected=scope()))
    with pytest.raises(phone.module.PhoneError, match='PLAYBACK_JOURNAL_FULL'):
        invoke(phone, 'playback_command', command)
    assert len(session(phone)['playback_operations']) == 8
    phone.manager.revoke()
    assert phone.manager.playback_operations == {}


def test_wrong_expected_receipt_cannot_unlock_original_unknown(phone):
    command = admitted(phone)
    phone.result = dict(status='unknown')
    invoke(phone, 'playback_command', command)
    phone.result = dict(status='rejected', command_id=command['command_id'])
    invoke(phone, 'playback_receipt', dict(expected=scope(), command_id=command['command_id']))
    assert session(phone)['playback_operations'][0]['status'] == 'unknown'


def test_account_change_during_lost_response_revokes_original_session(phone):
    command = admitted(phone)
    original_rpc = phone.manager.rpc
    def transport(action, body, **kwargs):
        if action == 'playback':
            phone.expected = dict(phone.expected, epoch=phone.expected['epoch'] + 1)
            raise OSError('lost')
        return original_rpc(action, body, **kwargs)
    phone.manager.rpc = transport
    with pytest.raises(phone.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(phone, 'playback_command', command)
    assert phone.manager.closed
    assert phone.manager.playback_operations == {}
