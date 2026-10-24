"""Android entry points cannot install the CoreELEC generation by accident."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import android_ui, ce_install_ui

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ui(monkeypatch):
    state = SimpleNamespace(playing=False, choice=2, builtins=[], dialogs=[], rows=[])
    def select(title, rows):
        state.rows = rows
        return state.choice
    state.dialog = SimpleNamespace(select=select, ok=lambda *args: state.dialogs.append(args))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Player=lambda: SimpleNamespace(isPlaying=lambda: state.playing),
        getCondVisibility=lambda name: name == 'System.Platform.Android',
        executebuiltin=state.builtins.append))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog))
    return state


def test_real_install_entry_never_constructs_ce_installer_on_android(ui, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Android entered the CE installation transaction')
    monkeypatch.setattr(ce_install_ui, 'KodiHost', forbidden)
    monkeypatch.setattr(ce_install_ui, 'Installer', forbidden)
    ce_install_ui.main()
    assert ui.builtins == ['RunScript(script.bobbi.setup)']


@pytest.mark.parametrize('options', [dict(online=True), dict(storage=True)])
def test_old_maintenance_links_explain_apk_updates_without_mutation(ui, options):
    ce_install_ui.main(**options)
    assert ui.builtins == []
    assert 'APK' in str(ui.dialogs) and '直接覆盖安装' in str(ui.dialogs)
    assert all('恢复上一版本' not in row and '本地完整包' not in row for row in ui.rows)


def test_playback_blocks_android_maintenance_without_stop(ui):
    ui.playing = True
    assert android_ui.show_updates(ui.dialog) is False
    assert ui.rows == [] and ui.builtins == []


@pytest.mark.parametrize('choice,target', [(0, 'dependencies'), (1, 'user/all')])
def test_dependency_management_remains_available(ui, choice, target):
    ui.choice = choice
    assert android_ui.show_updates(ui.dialog) is True
    assert ui.builtins == ['ActivateWindow(addonbrowser,addons://%s/,return)' % target]


def test_playback_beginning_during_dialog_cancels_navigation(ui):
    ui.choice = 0
    ui.dialog.ok = lambda *args: setattr(ui, 'playing', True)
    assert android_ui.show_updates(ui.dialog) is False
    assert ui.builtins == []


def test_cancel_does_nothing(ui):
    ui.choice = -1
    assert android_ui.show_updates(ui.dialog) is False
    assert ui.dialogs == [] and ui.builtins == []


def test_actual_start_script_routes_android_without_bootstrap_install(ui, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(Addon=lambda _: SimpleNamespace(
        getAddonInfo=lambda _: str(tmp_path))))
    monkeypatch.setattr(sys, 'argv', ['script.bobbi.start'])
    previous = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location('android_start_entry', ROOT/'addons/script.bobbi.start/default.py')
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
    finally:
        sys.path[:] = previous
    assert ui.builtins == ['RunScript(script.bobbi.setup)']
