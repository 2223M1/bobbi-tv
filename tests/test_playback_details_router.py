"""OSD details must not initialize online metadata or create a directory."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def test_details_dispatches_only_to_the_resident_owner(monkeypatch):
    path = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib/router.py'
    spec = importlib.util.spec_from_file_location('details_router_test', path)
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    calls = []
    dialogs = ModuleType('lib.gui.custom_dialogs')
    dialogs.publish_playback_details = lambda params: calls.append(params) or 'published'
    monkeypatch.setitem(sys.modules, 'lib.gui.custom_dialogs', dialogs)
    metadata = ModuleType('lib.utils.tmdb_init')
    def forbidden():
        raise AssertionError('Playback details must not initialize metadata')
    metadata.ensure_tmdb_init = forbidden
    monkeypatch.setitem(sys.modules, 'lib.utils.tmdb_init', metadata)
    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '-1', '?action=playback_details'])
    assert router.addon_router() == 'published'
    assert calls == [{'action': 'playback_details'}]
    assert router._is_gui_action('playback_details')
