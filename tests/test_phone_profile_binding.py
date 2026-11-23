"""An old browser grant must never follow Kodi to a new profile/Host."""
from pathlib import Path

import pytest

from bobbi_platform.paths import ProfileBinding
from test_ce2097_phone_management import phone, pair, invoke


@pytest.mark.parametrize('during_reply', [False, True])
def test_profile_switch_revokes_even_with_same_cloud_account(phone, tmp_path, during_reply):
    current = [tmp_path / 'A']
    binding = ProfileBinding(lambda addon: current[0] / addon)
    phone.manager.profile_binding = binding
    pair(phone)
    original = phone.manager.rpc
    def rpc(action, args, **kwargs):
        result = original(action, args, **kwargs)
        if action == 'catalog_items':
            current[0] = tmp_path / 'B'
        return result
    phone.manager.rpc = rpc
    phone.calls.clear()
    if not during_reply:
        current[0] = tmp_path / 'B'
    with pytest.raises(phone.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(phone)
    assert phone.manager.closed
    assert len([a for a, _ in phone.calls if a == 'catalog_items']) == int(during_reply)
    current[0] = tmp_path / 'A'
    with pytest.raises(phone.module.PhoneError):
        invoke(phone)


def test_default_transport_captures_exact_runtime_before_pairing(phone, monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    import bobbi_platform.runtime as runtime
    current = [tmp_path / 'A']
    captured = []
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda special: str(current[0] / special.rsplit('/', 1)[-1])))
    def bind(path):
        captured.append(path)
        return phone.manager.rpc
    monkeypatch.setattr(runtime, 'bind_call', bind)
    manager = phone.module.PhoneManagement(phone.expected, 'http://127.0.0.1:8081')
    assert captured == [tmp_path / 'A' / 'script.module.bobbi.platform' / 'runtime.json']
    current[0] = tmp_path / 'B'
    with pytest.raises(phone.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        manager._live()
    assert not phone.calls


@pytest.mark.parametrize('operation', ['playback_command', 'playback_receipt'])
@pytest.mark.parametrize('during_reply', [False, True])
def test_user_stop_and_original_receipt_cannot_follow_profile_change(phone, tmp_path, operation, during_reply):
    from uuid import uuid4
    from test_phone_playback_scopes import scope
    current = [tmp_path / 'A']
    phone.manager.profile_binding = ProfileBinding(lambda addon: current[0] / addon)
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    pair(phone)
    command = dict(expected=scope(), command_id=uuid4().hex, action='user_stop', params={})
    phone.result = dict(command_id=command['command_id'], status='queued')
    if operation == 'playback_receipt':
        invoke(phone, 'playback_command', command)
    params = command if operation == 'playback_command' else {
        key: command[key] for key in ('expected', 'command_id')}
    original = phone.manager.rpc
    def rpc(action, args, **kwargs):
        result = original(action, args, **kwargs)
        if action == 'playback':
            current[0] = tmp_path / 'B'
        return result
    phone.manager.rpc = rpc
    phone.calls.clear()
    if not during_reply:
        current[0] = tmp_path / 'B'
    with pytest.raises(phone.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(phone, operation, params)
    assert phone.manager.closed and phone.manager.playback_operations == {}
    assert len([action for action, _ in phone.calls if action == 'playback']) == int(during_reply)
    current[0] = tmp_path / 'A'
    with pytest.raises(phone.module.PhoneError):
        invoke(phone, operation, params)
