import pytest
from bobbi_platform.environment import DEFAULTS, load_config, save_config, private_path
from bobbi_platform.capabilities import probe, STANDARD_METHODS, NATIVE_METHODS, require


def test_profile_default_is_not_private_environment(tmp_path):
    path = tmp_path / 'config.json'
    assert load_config(path) == DEFAULTS
    save_config(path, DEFAULTS)
    assert load_config(path) == DEFAULTS
    assert DEFAULTS['cd2_url'] == DEFAULTS['helper_url'] == ''
    assert DEFAULTS['source_selection'] == 'manual'


@pytest.mark.parametrize('key,value', [('transcode', True), ('source_selection', 'auto'),
    ('helper_url', 'http://example.com'), ('cd2_url', 'http://user:pass@example.com'),
    ('automatic_updates', 'true'), ('profile', 'zidoo-certified')])
def test_invalid_settings_fail_without_write(tmp_path, key, value):
    config = dict(DEFAULTS, **{key: value})
    path = tmp_path / 'config.json'
    with pytest.raises(ValueError):
        save_config(path, config)
    assert not path.exists()


def test_paths_are_injected_and_contained(tmp_path):
    translate = lambda path: str(tmp_path / 'profile')
    assert private_path(translate, 'cache') == tmp_path / 'profile/cache'
    with pytest.raises(ValueError):
        private_path(translate, '../other-addon')


def rpc_for(methods, major=21):
    def rpc(method, params):
        if method == 'Application.GetProperties':
            return {'version': {'major': major}}
        assert method == 'JSONRPC.Introspect'
        return {'methods': dict.fromkeys(methods, {})}
    return rpc


def test_stock_kodi_never_invents_native_evidence():
    result = probe(rpc_for(STANDARD_METHODS), 'android')
    assert result['standard_playback']
    assert not result['native_contract_available']
    assert not result['automatic_continuation']
    with pytest.raises(RuntimeError):
        require(result, 'native_contract_available')


def test_native_method_presence_is_not_health_or_certification():
    result = probe(rpc_for(STANDARD_METHODS | NATIVE_METHODS), 'coreelec')
    assert result['native_contract_available']
    assert not result['native_contract_healthy']
    assert not result['zidoo_player_verified']
    assert not result['automatic_continuation']


def test_introspection_failure_fails_closed():
    def rpc(method, params):
        raise OSError('offline')
    result = probe(rpc)
    assert not result['standard_playback']
    assert len(result['errors']) == 2


def test_unknown_kodi_major_requires_port_validation():
    assert not probe(rpc_for(STANDARD_METHODS, 22))['standard_playback']
