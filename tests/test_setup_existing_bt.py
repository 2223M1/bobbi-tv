"""Setup reuses the real configured adapter and performs only its echo probe."""
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import requests

from bobbi_platform import bt_setup
from bobbi_platform.onboarding import steps
from test_onboarding import setup_ui

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    path = tmp_path/'profile/plugin.video.bobbi.torrent/backend.json'
    path.parent.mkdir(parents=True)
    config = dict(schema=1, endpoint='http://127.0.0.1:8090',
                  auth={'username': 'fixture_user', 'password': 'fixture_private_value'},
                  metadata_seconds=30, buffering_seconds=90)
    path.write_text(json.dumps(config))
    state = SimpleNamespace(path=path, calls=[], closes=0, sessions=[], version=b'MatriX.144.1',
                            status=200, error=None, addon_calls=[])
    def translate(value):
        if value.startswith('special://profile/'):
            return str(path)
        return value
    def addon(identifier):
        state.addon_calls.append(identifier)
        assert identifier == 'plugin.video.bobbi.torrent'
        return SimpleNamespace(getAddonInfo=lambda key: str(ROOT/'addons/plugin.video.bobbi.torrent'))
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        @property
        def status_code(self): return state.status
        def iter_content(self, chunk_size): yield state.version
    class Session:
        def __init__(self):
            self.trust_env = True
            state.sessions.append(self)
        def request(self, method, url, **kwargs):
            state.calls.append((method, url, kwargs))
            if state.error: raise state.error
            return Response()
        def close(self): state.closes += 1
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(Addon=addon))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=translate))
    monkeypatch.setattr(requests, 'Session', Session)
    state.translate = translate
    return state


@pytest.mark.parametrize('version', [b'MatriX.144.1', b'MatriX.147'])
def test_existing_cinema_backend_uses_real_validation_and_only_get_echo(adapter, version):
    adapter.version = version
    before = adapter.path.read_bytes()
    assert bt_setup.adapter_status(adapter.translate) == 'adapter_ready'
    assert [(method, url) for method, url, _ in adapter.calls] == [('GET', 'http://127.0.0.1:8090/echo')]
    request = adapter.calls[0][2]
    assert request['allow_redirects'] is False and request['stream'] is True
    assert request['timeout'][0] <= 3.05 and request['timeout'][1] <= 4
    assert 'json' not in request and 'files' not in request and 'data' not in request
    assert adapter.sessions[0].trust_env is False and adapter.closes == 1
    assert adapter.path.read_bytes() == before
    assert not list(adapter.path.parent.glob('*pairing*'))
    assert '_bobbi_setup_existing_torrent' not in sys.modules
    assert '_bobbi_setup_existing_torrent.backend' not in sys.modules
    assert '_bobbi_setup_existing_torrent.http_io' not in sys.modules


@pytest.mark.parametrize('failure', ['offline', 'unsupported', 'unauthorized'])
def test_failed_echo_preserves_existing_configuration_and_closes_session(adapter, failure):
    before = adapter.path.read_bytes()
    if failure == 'offline': adapter.error = requests.exceptions.ConnectionError('fixture_private_value')
    elif failure == 'unsupported': adapter.version = b'MatriX.100'
    else: adapter.status = 401
    state = bt_setup.adapter_status(adapter.translate)
    assert state == 'adapter_offline' and adapter.closes == 1
    assert adapter.path.read_bytes() == before
    assert all(method == 'GET' and url.endswith('/echo') for method, url, _ in adapter.calls)
    assert 'fixture_private_value' not in bt_setup.adapter_message(state)


def test_missing_adapter_configuration_falls_back_without_import_or_network(adapter, monkeypatch):
    adapter.path.unlink()
    monkeypatch.setattr(bt_setup, '_backend_module', lambda: pytest.fail('adapter must stay optional'))
    assert bt_setup.adapter_status(adapter.translate) is None
    assert adapter.calls == [] and adapter.addon_calls == []


def test_invalid_adapter_configuration_is_not_misreported_as_unpaired(adapter):
    adapter.path.write_text('{"schema": 0}')
    assert bt_setup.adapter_status(adapter.translate) == 'adapter_invalid'
    assert adapter.calls == [] and adapter.sessions == []


def test_unavailable_adapter_with_existing_configuration_does_not_create_another_engine(adapter, monkeypatch):
    def unavailable(): raise ImportError('fixture_private_value')
    monkeypatch.setattr(bt_setup, '_backend_module', unavailable)
    state = bt_setup.adapter_status(adapter.translate)
    assert state == 'adapter_unavailable' and not adapter.calls
    assert 'fixture_private_value' not in bt_setup.adapter_message(state)


def test_cancelled_check_never_claims_ready_or_sends_requests(adapter):
    assert bt_setup.adapter_status(adapter.translate, cancelled=lambda: True) == 'adapter_configured'
    assert adapter.calls == [] and adapter.sessions == []


def test_status_bridge_import_has_no_kodi_adapter_or_network_startup_dependency(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in ('xbmc', 'xbmcaddon', 'xbmcvfs', 'bobbi_torrent', 'requests'):
            pytest.fail('Optional dependency imported at UI module startup: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    spec = importlib.util.spec_from_file_location('_bt_setup_import_test', Path(bt_setup.__file__))
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


@pytest.mark.parametrize('state', ['adapter_ready', 'adapter_offline', 'adapter_invalid',
                                   'adapter_unavailable', 'adapter_configured'])
def test_existing_backend_has_one_status_and_no_pairing_or_install_menu(setup_ui, monkeypatch, tmp_path, state):
    monkeypatch.setattr(setup_ui.module, 'existing_backend_status', lambda: state)
    monkeypatch.setattr(setup_ui.module, 'load_pairing', lambda path: pytest.fail('do not substitute another helper'))
    assert setup_ui.module.helper_status(tmp_path/'pairing.json') == state
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path/'pairing.json')
    assert setup_ui.selections == [] and setup_ui.called == [] and setup_ui.builtins == []
    assert not (tmp_path/'pairing.json').exists()
    label = dict(steps({}, helper_state=state))['helper']
    assert '尚未连接' not in label and '重新配对' not in label
    assert '现有' in str(setup_ui.dialogs) or '已有' in str(setup_ui.dialogs)


@pytest.mark.parametrize('choice', [0, 2, 3])
def test_adapter_configured_while_selector_open_blocks_second_pairing_or_engine(setup_ui, monkeypatch,
                                                                              tmp_path, choice):
    setup_ui.choice = choice
    states = iter((None, 'adapter_ready'))
    monkeypatch.setattr(setup_ui.module, 'existing_backend_status', lambda: next(states))
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path/'pairing.json')
    assert setup_ui.called == [] and setup_ui.builtins == []
    assert not (tmp_path/'pairing.json').exists()
    assert '现有 BT 后台' in str(setup_ui.dialogs)


def test_legacy_helper_still_works_when_no_adapter_is_configured(setup_ui, monkeypatch, tmp_path):
    from bobbi_platform.pairing import from_export, save
    monkeypatch.setattr(setup_ui.module, 'existing_backend_status', lambda: None)
    path = tmp_path/'pairing.json'
    save(path, from_export(setup_ui.raw))
    assert setup_ui.module.helper_status(path) == 'ready'
    assert setup_ui.called == ['ready']
    assert setup_ui.module.helper_status(tmp_path/'missing.json') == 'not_paired'


@pytest.mark.parametrize('choice,appear_at', [(0, 'input'), (2, 'yesno'), (2, 'progress'),
                                           (3, 'browse'), (0, 'ready'), (3, 'ready')])
def test_adapter_appearing_during_final_dialog_or_probe_preserves_previous_pairing(
        setup_ui, monkeypatch, tmp_path, choice, appear_at):
    from bobbi_platform.pairing import from_export, save
    path = tmp_path/'pairing.json'
    save(path, from_export(json.dumps(dict(setup_ui.value, password='9' * 48))))
    before = path.read_bytes()
    state = SimpleNamespace(present=False, effects=[], progress_closed=False)
    setup_ui.choice = choice
    def step(name, value):
        if name == appear_at:
            state.present = True
        return value
    def effect(name, value=None):
        state.effects.append(name)
        return value
    monkeypatch.setattr(setup_ui.module, 'existing_backend_status',
                        lambda: 'adapter_ready' if state.present else None)
    setup_ui.dialog.input = lambda *args, **kwargs: step('input', '123456')
    setup_ui.dialog.yesno = lambda *args: step('yesno', True)
    setup_ui.dialog.browse = lambda *args, **kwargs: step('browse', setup_ui.selected)
    progress = SimpleNamespace(create=lambda *args: step('progress', None), update=lambda *args: None,
        close=lambda: setattr(state, 'progress_closed', True), iscanceled=lambda: False)
    monkeypatch.setattr(setup_ui.module.xbmcgui, 'INPUT_NUMERIC', 1, raising=False)
    monkeypatch.setattr(setup_ui.module.xbmcgui, 'DialogProgress', lambda: progress, raising=False)
    monkeypatch.setitem(sys.modules, 'bobbi_platform.native_engine',
                        SimpleNamespace(install=lambda **kwargs: effect('install')))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.pair_code',
                        SimpleNamespace(exchange=lambda code: effect('exchange', from_export(setup_ui.raw))))
    monkeypatch.setattr(setup_ui.module, 'TorrServerClient',
                        lambda document: SimpleNamespace(ready=lambda **kwargs: step('ready', True)))
    monkeypatch.setattr(setup_ui.module, 'save_pairing', lambda *args: effect('save'))
    setup_ui.module.pair_helper(setup_ui.dialog, path)
    assert state.present and path.read_bytes() == before
    assert 'install' not in state.effects and 'save' not in state.effects
    assert state.effects == (['exchange'] if choice == 0 and appear_at == 'ready' else [])
    assert '现有 BT 后台' in str(setup_ui.dialogs)
    if choice == 2:
        assert state.progress_closed
