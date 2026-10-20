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


def rpc_for(methods, major=21, native=None):
    def rpc(method, params):
        if method == 'Application.GetProperties':
            return {'version': {'major': major}}
        if method == 'Player.BobiState':
            return native
        assert method == 'JSONRPC.Introspect'
        return {'methods': dict.fromkeys(methods, {})}
    return rpc


def test_stock_kodi_never_invents_native_evidence():
    result = probe(rpc_for(STANDARD_METHODS), 'android')
    assert result['standard_playback']
    assert not result['native_contract_available']
    assert result['automatic_continuation']
    with pytest.raises(RuntimeError):
        require(result, 'native_contract_available')


def test_native_method_presence_is_not_health_or_certification():
    result = probe(rpc_for(STANDARD_METHODS | NATIVE_METHODS), 'coreelec')
    assert not result['native_contract_available']
    assert not result['native_contract_healthy']
    assert not result['zidoo_player_verified']
    assert result['automatic_continuation']


def test_introspection_failure_fails_closed():
    def rpc(method, params):
        raise OSError('offline')
    result = probe(rpc)
    assert not result['standard_playback']
    assert 'RPC_INTROSPECTION_UNAVAILABLE' in result['errors']
    assert all('MISSING_API:' + name in result['errors'] for name in STANDARD_METHODS)


@pytest.mark.parametrize('major', [20, 21, 22, 99, 0])
def test_actual_api_not_version_label_decides_standard_path(major):
    assert probe(rpc_for(STANDARD_METHODS, major))['standard_playback']


def test_known_readonly_native_protocol_preserves_enhancement():
    value = {'protocol': 1, 'selection_epoch': 0, 'playback': None}
    assert probe(rpc_for(STANDARD_METHODS | NATIVE_METHODS, 22, value))['native_contract_available']


@pytest.mark.parametrize('state', [None, {}, {'protocol': 99},
    {'protocol': True, 'selection_epoch': 0, 'playback': None}])
def test_wrong_protocol_keeps_standard_features_without_native_receipts(state):
    result = probe(rpc_for(STANDARD_METHODS | NATIVE_METHODS, native=state))
    assert result['standard_playback'] and result['automatic_continuation']
    assert not result['native_contract_available']


def test_partial_native_methods_do_not_disable_standard_features():
    result = probe(rpc_for(STANDARD_METHODS | {'Player.BobiState'}))
    assert result['standard_playback'] and result['automatic_continuation']
    assert not result['native_contract_available']
