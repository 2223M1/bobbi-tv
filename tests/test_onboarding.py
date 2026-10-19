import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from bobbi_platform.onboarding import steps, summary, engine_message
from bobbi_platform.pairing import load, from_export, save
from bobbi_platform.torrserver import TorrServerError, Cancelled

ROOT = Path(__file__).resolve().parents[1]


def test_steps_never_ask_for_box_model_or_claim_ready_cinema():
    rows = steps({'standard_playback': True}, '/media', 'ready')
    assert len({key for key, _ in rows}) == len(rows)
    text = '\n'.join(label for _, label in rows)
    assert '机型' not in text and '选择型号' not in text
    assert '还需实播' in text and '扫码登录' in text and '测试版' in text
    assert '可跳过' in dict(steps({}))['library']
    assert '需要处理' in dict(steps({}))['check']


def test_status_explains_limit_in_plain_language():
    assert '不代表' in summary({'standard_playback': True})
    assert 'Kodi 21' in summary({})
    assert '重新导出' in engine_message('ENGINE_AUTH_REJECTED')
    assert 'unknown-secret-detail' not in engine_message('unknown-secret-detail')


def test_library_status_counts_saved_sources_without_claiming_online():
    assert '已保存 2 个来源' in dict(steps({}, library_count=2))['library']
    assert '在线' not in dict(steps({}, library_count=2))['library']
    assert '需要检查' in dict(steps({}, library_count=None))['library']


@pytest.fixture
def setup_ui(monkeypatch):
    state = SimpleNamespace(choice=3, selected='selected.json', raw=None, called=[], dialogs=[],
                            error=None, closed=False, android=True, builtins=[])
    xbmc = SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
        getCondVisibility=lambda _: state.android, executebuiltin=lambda command: state.builtins.append(command))
    stream = SimpleNamespace(readBytes=lambda size: state.raw[:size], close=lambda: setattr(state, 'closed', True))
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(File=lambda _: stream))
    spec = importlib.util.spec_from_file_location('_bobbi_setup_test', ROOT / 'addons/script.bobbi.setup/default.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def ready(**kwargs):
        state.called.append('ready')
        if state.error:
            raise state.error
        return True
    monkeypatch.setattr(module, 'TorrServerClient', lambda document: SimpleNamespace(ready=ready))
    state.module = module
    state.dialog = SimpleNamespace(select=lambda *args: state.choice,
        browse=lambda *args, **kwargs: state.selected,
        ok=lambda *args: state.dialogs.append(args))
    state.value = {'schema': 'bobbi-local-engine-v1', 'engine': 'TorrServer',
        'version': 'MatriX.147', 'url': 'http://127.0.0.1:8090',
        'username': 'bobbi_' + '1' * 12, 'password': '2' * 48}
    state.raw = json.dumps(state.value).encode()
    return state


def test_file_import_saves_only_after_actual_ready_check(setup_ui, tmp_path):
    path = tmp_path / 'pairing.json'
    setup_ui.module.pair_helper(setup_ui.dialog, path)
    assert setup_ui.called == ['ready']
    assert load(path).password == setup_ui.value['password']
    assert setup_ui.closed
    assert setup_ui.value['password'] not in str(setup_ui.dialogs)


@pytest.mark.parametrize('error', [TorrServerError('ENGINE_AUTH_REJECTED'), Cancelled('USER_CANCELLED')])
def test_failed_new_pair_keeps_previous_pairing(setup_ui, tmp_path, error):
    path = tmp_path / 'pairing.json'
    value = dict(setup_ui.value, password='9' * 48)
    save(path, from_export(json.dumps(value)))
    old = path.read_bytes()
    setup_ui.error = error
    setup_ui.module.pair_helper(setup_ui.dialog, path)
    assert path.read_bytes() == old


def test_cancel_file_chooser_creates_no_file(setup_ui, tmp_path):
    setup_ui.selected = ''
    path = tmp_path / 'pairing.json'
    setup_ui.module.pair_helper(setup_ui.dialog, path)
    assert not path.exists() and not setup_ui.called


def test_open_helper_is_explicit_android_action(setup_ui, tmp_path):
    setup_ui.choice = 1
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path / 'pairing.json')
    assert setup_ui.builtins == ['StartAndroidActivity(org.bobbi.helper)']
    setup_ui.android = False
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path / 'pairing.json')
    assert len(setup_ui.builtins) == 1
