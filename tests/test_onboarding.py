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
    assert '还需实播' in text and '扫码登录' in text and '支持范围' in text
    assert '私人候选' not in text
    assert '可跳过' in dict(steps({}))['library']
    assert '需要处理' in dict(steps({}))['check']


def test_status_explains_limit_in_plain_language():
    assert '不代表' in summary({'standard_playback': True})
    assert '播放器接口' in summary({})
    assert '重新导出' in engine_message('ENGINE_AUTH_REJECTED')
    assert 'unknown-secret-detail' not in engine_message('unknown-secret-detail')


def test_library_status_counts_saved_sources_without_claiming_online():
    assert '已保存 2 个来源' in dict(steps({}, library_count=2))['library']
    assert '在线' not in dict(steps({}, library_count=2))['library']
    assert '需要检查' in dict(steps({}, library_count=None))['library']


@pytest.fixture
def setup_ui(monkeypatch, tmp_path):
    state = SimpleNamespace(choice=3, selected='selected.json', raw=None, called=[], dialogs=[],
                            error=None, closed=False, android=True, builtins=[], playing=False,
                            selections=[])
    xbmc = SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
        Player=lambda: SimpleNamespace(isPlaying=lambda: state.playing),
        getCondVisibility=lambda _: state.android, executebuiltin=lambda command: state.builtins.append(command))
    stream = SimpleNamespace(readBytes=lambda size: state.raw[:size], close=lambda: setattr(state, 'closed', True))
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(File=lambda _: stream,
        translatePath=lambda value: str(tmp_path/'profile'/value.rsplit('/', 1)[-1])))
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
    def select(*args):
        state.selections.append(args)
        return state.choice
    state.dialog = SimpleNamespace(select=select,
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


def test_full_android_cinema_never_launches_itself_as_legacy_helper(setup_ui, tmp_path):
    setup_ui.choice = 1
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path / 'pairing.json')
    assert setup_ui.builtins == []
    assert '不是旧助手' in str(setup_ui.dialogs)
    setup_ui.android = False
    setup_ui.module.pair_helper(setup_ui.dialog, tmp_path / 'pairing.json')
    assert setup_ui.builtins == []


def test_update_label_distinguishes_original_addons_from_bobbi_bundle():
    label = dict(steps({}))['updates']
    assert '在线更新' in label and '本地安装' in label and '回退' in label


@pytest.mark.parametrize('choice,target', [
    (0, 'addons://dependencies/'),
    (1, 'addons://user/all/'),
])
def test_original_addon_menu_only_opens_native_browser(setup_ui, choice, target):
    setup_ui.choice = choice
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert setup_ui.builtins == ['ActivateWindow(addonbrowser,%s,return)' % target]
    assert setup_ui.called == []
    explanation = str(setup_ui.dialogs)
    assert '原 ID' in explanation and '已安装的旧播放组件' in explanation
    assert '不能整体用原版覆盖' in explanation


def test_bobbi_bundle_menu_opens_real_installer_without_applying(setup_ui):
    setup_ui.choice = 2
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert setup_ui.builtins == ['RunScript(script.bobbi.start)'] and setup_ui.called == []


def test_cancel_update_menu_does_nothing(setup_ui):
    setup_ui.choice = -1
    assert setup_ui.module.show_updates(setup_ui.dialog) is False
    assert setup_ui.builtins == [] and setup_ui.called == [] and setup_ui.dialogs == []


@pytest.mark.parametrize('choice', [0, 1, 2, 3])
def test_playing_blocks_update_menu_without_stopping_video(setup_ui, choice):
    setup_ui.choice = choice
    setup_ui.playing = True
    assert setup_ui.module.show_updates(setup_ui.dialog) is False
    assert setup_ui.selections == [] and setup_ui.builtins == [] and setup_ui.called == []
    assert '请先停止播放' in str(setup_ui.dialogs)


@pytest.mark.parametrize('choice', [0, 1])
def test_playback_started_during_menu_blocks_native_management(setup_ui, choice):
    setup_ui.choice = choice
    def explain_then_start(*args):
        setup_ui.dialogs.append(args)
        setup_ui.playing = True
    setup_ui.dialog.ok = explain_then_start
    assert setup_ui.module.show_updates(setup_ui.dialog) is False
    assert setup_ui.builtins == [] and setup_ui.called == []
    assert '当前已经开始播放' in str(setup_ui.dialogs)
