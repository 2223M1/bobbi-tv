"""Explicit playback grants use the same phone gate, not catalog privilege."""
from uuid import uuid4
import pytest

from test_ce2097_phone_management import phone, pair, invoke


def scope():
    return dict(boot_id=uuid4().hex, epoch=1, request_id=uuid4().hex, native_instance=str(uuid4()),
        file_sha256='a'*64, selection_epoch=1, expected_sequence=1, user_intent=0, subtitle_intent=0, audio_intent=0)


@pytest.mark.parametrize('action,args', [('playback_presentation', {}), ('playback_receipt', {}), ('playback_command', {})])
def test_old_catalog_grant_never_expands_to_playback(phone, action, args):
    result, _ = pair(phone)
    assert set(result['scopes']) == phone.module.SCOPES
    with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
        invoke(phone, action, args)
    assert not [call for call in phone.calls if call[0] == 'playback']


def test_read_grant_cannot_issue_even_a_valid_control(phone):
    phone.manager.scopes |= frozenset(('playback_read',))
    pair(phone)
    phone.result = dict(available=False, reason='SCOPED_CONTROL_UNAVAILABLE')
    assert invoke(phone, 'playback_presentation') == phone.result
    with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
        invoke(phone, 'playback_command', dict(expected=scope(), command_id=uuid4().hex, action='seek',params={'position_ms':1000}))
    calls = [body for action,body in phone.calls if action == 'playback']
    assert calls == [dict(operation='playback_presentation',account_scope=phone.expected)]


def test_explicit_control_preserves_original_expectation_and_only_public_receipt(phone):
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    pair(phone)
    command = dict(expected=scope(), command_id=uuid4().hex, action='subtitle_visible', params={'visible':False})
    phone.result = dict(command_id=command['command_id'], status='queued', token='private', url='https://secret.invalid')
    assert invoke(phone, 'playback_command', command) == dict(command_id=command['command_id'],status='queued')
    calls = [body for action,body in phone.calls if action == 'playback']
    assert calls == [dict(operation='playback_command',account_scope=phone.expected,command=command)]


@pytest.mark.parametrize('params', [{'expected':{}}, {'action':'Player.Seek'}, {'position_ms':True},
                                  {'url':'http://secret.invalid'}, {'visible':0}])
def test_arbitrary_playback_authority_is_rejected_before_owner(phone, params):
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    pair(phone)
    with pytest.raises(phone.module.PhoneError):
        invoke(phone, 'playback_command', params)
    assert not [call for call in phone.calls if call[0] == 'playback']
