"""Kodi action-item contract, not a simulated directory cancellation as success."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

from test_library_plugin import plugin
from bobbi_platform.libraries import Registry, Source


def assert_action(row):
    _, item, folder = row
    assert folder is False
    assert item.properties['IsPlayable'] == 'false'
    assert item.lookup is False
    assert item.art['icon'] == 'DefaultFolder.png'
    assert not hasattr(item, 'info')  # Not a zero-byte video or a playable action.


def test_root_modal_entries_use_kodi_script_action_not_folder_resolution(plugin):
    plugin.module.execute(17, {})
    for row in (plugin.rows[0], plugin.rows[2]):
        assert_action(row)
    assert plugin.rows[1][2] is True  # NAS is still a real directory.
    assert plugin.rows[3][2] is True  # Indexed library is still a directory.


def test_personal_cloud_hint_reaches_tv_tiles_without_claiming_provider_playback(plugin):
    from xml.etree import ElementTree as ET
    plugin.module.execute(17, {})
    row = next(item for _, item, _ in plugin.rows if item.properties.get('Bobbi.Library.Kind') == 'native_pan')
    assert row.label2 == row.properties['Bobbi.Library.Location']
    assert 'CD2' in row.label2 and '直连' not in row.label2
    skin = Path(plugin.module.__file__).resolve().parents[1] / 'skin.bobbi.cinema/1080p'
    hints = ET.parse(skin / 'Includes_Home.xml').find("variable[@name='LibraryTileHint']").findall('value')
    location = next(i for i, hint in enumerate(hints) if hint.text == '$VAR[BobbiLibraryLocation]')
    assert 'Bobbi.Library.Kind' not in hints[location].get('condition')
    assert all('直连' not in (hint.text or '') for hint in hints)


@pytest.mark.parametrize('result', [None, True])
def test_native_files_action_returns_without_directory_failure_or_player_control(plugin, monkeypatch, result):
    calls = []
    def choose(dialog):
        calls.append(dialog)
        return result
    monkeypatch.setitem(sys.modules, 'bobbi_platform.pan_ui', SimpleNamespace(choose_files=choose))
    plugin.module.execute(-1, {'action': 'native_files'})
    assert len(calls) == 1
    assert plugin.ended == [] and plugin.rows == [] and plugin.resolved == []
    assert plugin.calls == [] and plugin.closed == 0


def test_manage_action_uses_existing_setup_without_directory_failure(plugin):
    plugin.module.execute(-1, {'action': 'manage'})
    assert plugin.calls == [('builtin', 'RunScript(script.bobbi.setup,libraries)')]
    assert not plugin.ended and not plugin.rows and not plugin.resolved


def test_modal_action_exception_is_not_a_fake_successful_listing(plugin, monkeypatch):
    def failed(dialog):
        raise OSError('synthetic host failure')
    monkeypatch.setitem(sys.modules, 'bobbi_platform.pan_ui', SimpleNamespace(choose_files=failed))
    with pytest.raises(OSError):
        plugin.module.execute(-1, {'action': 'native_files'})
    assert not plugin.ended and not plugin.resolved and not plugin.rows


def test_script_action_entry_reports_error_without_ending_invalid_directory_handle(plugin, monkeypatch):
    def failed(dialog):
        raise OSError('synthetic host failure')
    monkeypatch.setitem(sys.modules, 'bobbi_platform.pan_ui', SimpleNamespace(choose_files=failed))
    monkeypatch.setattr(plugin.module.xbmc, 'log', lambda *args: None, raising=False)
    monkeypatch.setattr(plugin.module.xbmc, 'LOGWARNING', 2, raising=False)
    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi.library/', '-1', '?action=native_files'])
    parsed = ast.parse(Path(plugin.module.__file__).read_text(encoding='utf-8'))
    entry = parsed.body[-1]
    assert isinstance(entry, ast.If) and '__name__' in ast.unparse(entry.test)
    namespace = dict(plugin.module.__dict__, __name__='__main__')
    exec(compile(ast.Module(body=[entry], type_ignores=[]), plugin.module.__file__, 'exec'), namespace)
    assert len(plugin.calls) == 1 and plugin.calls[0][0] == 'dialog'
    assert not plugin.ended and not plugin.resolved and not plugin.rows


def test_server_browser_is_also_an_action_and_closes_its_registry(plugin, monkeypatch):
    source = Source('a' * 32, 'Fixture server', 'media_server', 'http://127.0.0.1:8096',
                    password='fixture-token', metadata=dict(schema=1, provider='jellyfin',
                        user_id='fixture-user', server_id='fixture-server'))
    store = Registry(plugin.path)
    store.save(source)
    store.close()
    plugin.module.execute(17, {})
    row = next(row for row in plugin.rows if row[1].label == source.name)
    assert_action(row)
    calls = []
    monkeypatch.setitem(sys.modules, 'bobbi_platform.server_ui', SimpleNamespace(
        browse=lambda dialog, chosen: calls.append(chosen)))
    plugin.ended.clear()
    plugin.rows.clear()
    plugin.module.execute(-1, dict(parse_qsl(urlsplit(row[0]).query)))
    assert calls == [source] and plugin.closed == 2
    assert not plugin.ended and not plugin.rows and not plugin.resolved


@pytest.mark.parametrize('action', ['manage', 'native_files'])
def test_old_saved_folder_routes_still_complete_their_existing_directory_handle(plugin, monkeypatch, action):
    monkeypatch.setitem(sys.modules, 'bobbi_platform.pan_ui', SimpleNamespace(choose_files=lambda _: None))
    plugin.module.execute(17, {'action': action})
    assert plugin.ended == [((17,), {'succeeded': False, 'cacheToDisc': False})]
    assert not plugin.resolved
