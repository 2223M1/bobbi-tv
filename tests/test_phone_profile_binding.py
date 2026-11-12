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
    import bobbi_platform.paths as paths
    import bobbi_platform.runtime as runtime
    current = [tmp_path / 'A']
    captured = []
    monkeypatch.setattr(paths, 'profile_root', lambda addon: current[0] / addon)
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
