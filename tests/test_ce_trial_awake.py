"""Maintenance trials cannot mistake wake-up ACKs for window actions."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def functions():
    path = Path(__file__).resolve().parents[1] / 'tools/ce_trial_remote.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'gui_observation', 'prepare_home'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = dict(PICKER_WINDOWS=(13001, 13002), RETIRING_WINDOWS=(13001, 13002), PICKER_LABELS=())
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return scope


@pytest.mark.parametrize('screensaver,dpms', [(True, False), (False, True), (False, False)])
def test_observation_includes_both_wake_consumers(screensaver, dpms):
    scope = functions()
    def rpc(method, params=None):
        if method == 'Player.BobiState':
            return dict(gui_generation=1, gui_user_intent=0)
        if method == 'GUI.GetProperties':
            return dict(currentwindow={'id': 13001})
        if method == 'XBMC.GetInfoLabels':
            return {}
        values = {key: False for key in params['booleans']}
        values.update({'System.ScreenSaverActive': screensaver, 'System.DPMSActive': dpms})
        return values
    scope['rpc'] = rpc
    assert scope['gui_observation']()['asleep'] is (screensaver or dpms)


@pytest.mark.parametrize('window,asleep,error', [
    (13001, True, 'DISPLAY_ASLEEP_ATTENDED_WAKE_REQUIRED'),
    (12002, False, 'UNOWNED_MODAL'),
    (10100, False, 'UNOWNED_MODAL'),
])
def test_no_action_on_asleep_or_unowned_modal(window, asleep, error):
    scope = functions()
    scope.update(time=SimpleNamespace(monotonic=lambda: 0), assert_picker_idle=lambda _: None,
        gui_observation=lambda: dict(stable=True, generation=1, intent=0,
            window=window, modal=True, visible=[window] if window == 13001 else [], asleep=asleep),
        rpc=lambda *a: pytest.fail('No automatic wake/Back/Home or global modal close'))
    with pytest.raises(AssertionError, match=error):
        scope['prepare_home']({})


def test_awake_owned_picker_uses_one_back_and_observed_home():
    scope, calls, state = functions(), [], {'now': 0, 'back': False}
    def rpc(method):
        calls.append(method)
        assert method == 'Input.Back'
        state['back'] = True
    def view():
        return dict(stable=True, generation=2 if state['back'] else 1, intent=0,
            window=10000 if state['back'] else 13001, modal=not state['back'],
            visible=[] if state['back'] else [13001], asleep=False)
    def sleep(seconds):
        state['now'] += seconds
    scope.update(rpc=rpc, gui_observation=view, assert_picker_idle=lambda _: None,
                 time=SimpleNamespace(monotonic=lambda: state['now'], sleep=sleep))
    assert scope['prepare_home']({})['generation'] == 2
    assert calls == ['Input.Back']
