"""A cold Home/provider request uses only the local display owner, including saved URLs."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib'


@pytest.mark.parametrize('extra', ['', '&rail=continue_watching&revision=7', '&resume_preview=true', '&page=2'])
def test_history_url_does_not_boot_generic_player_or_remote_metadata(monkeypatch, extra):
    spec=importlib.util.spec_from_file_location('local_history_router', ROOT/'router.py')
    router=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    calls=[]
    module=ModuleType('lib.utils.views.continue_watching')
    module.show_continue_watching=lambda params: calls.append(params) or 'rendered'
    monkeypatch.setitem(sys.modules,module.__name__,module)
    for forbidden in ('lib.utils.tmdb_init','lib.navigation','lib.nav.library_history'):
        monkeypatch.setitem(sys.modules,forbidden,None)
    monkeypatch.setattr(sys,'argv',['plugin://plugin.video.bobbi/', '1', '?action=continue_watching_menu'+extra])
    assert router.addon_router()=='rendered'
    assert calls==[dict(router.parse.parse_qsl('action=continue_watching_menu'+extra))]


def test_importing_history_display_does_not_open_legacy_singleton_stores():
    source=ast.parse((ROOT/'utils/views/continue_watching.py').read_text(encoding='utf8'))
    imports={n.module for n in source.body if isinstance(n,ast.ImportFrom)}
    assert 'lib.domain.source_types' in imports
    assert imports.isdisjoint({'lib.navigation','lib.utils.general.utils','lib.utils.views.last_files'})
