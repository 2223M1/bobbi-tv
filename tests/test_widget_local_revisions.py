"""Existing widget loop emits local dependency revisions, not global reloads."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
from threading import RLock
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def widgets(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT/'addons/plugin.video.bobbi'))
    state = SimpleNamespace(props={}, builtins=[], reads=0, initialized=0,
        values={'jt:lfh': {}, 'files': {}}, broken=False)
    state.path = tmp_path/'history.pkl'
    state.path.write_bytes(b'initial')
    class Database:
        def __init__(self):
            state.initialized += 1
            self._database_path = str(state.path)
        def get_keys_checked(self, keys):
            state.reads += 1
            if state.broken: raise OSError('broken history')
            return state.values
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', SimpleNamespace(PickleDatabase=Database))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='files'))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(
        execute_builtin=state.builtins.append, get_property=lambda key: '',
        get_setting=lambda *a: 60, kodilog=lambda *a, **kw: None, notification=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(getSkinDir=lambda: 'skin.bobbi.cinema'))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda _: SimpleNamespace(
        getProperty=lambda key: state.props.get(key, ''),
        setProperty=lambda key, value: state.props.update({key: value}))))
    spec = importlib.util.spec_from_file_location('widget_local_test',
        ROOT/'addons/plugin.video.bobbi/lib/services/widget_refresh.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state.host = SimpleNamespace(catalog=None)
    state.service = module.WidgetRefreshService(host=state.host)
    return state


def test_unchanged_ticks_do_not_reload_history_or_refresh_global_containers(widgets):
    widgets.props['Bobi.Rail.Revision.popular_tv'] = '7'
    for _ in range(10): widgets.service.refresh_widgets()
    assert widgets.initialized == 1 and widgets.reads == 1
    assert widgets.props == {'Bobi.Rail.Revision.popular_tv': '7',
                             'Bobi.Rail.Revision.continue_watching': '1'}
    assert not widgets.builtins and widgets.host.catalog is None


def test_history_content_revision_changes_only_continue_row(widgets):
    widgets.service.refresh_dependencies()
    widgets.path.write_bytes(b'new unrelated data')
    widgets.service.refresh_dependencies()
    assert widgets.props['Bobi.Rail.Revision.continue_watching'] == '1'
    widgets.values['jt:lfh']['record'] = {'progress': 50}
    widgets.path.write_bytes(b'new history')
    widgets.service.refresh_dependencies()
    assert widgets.props == {'Bobi.Rail.Revision.continue_watching': '2'}


def test_broken_history_does_not_block_existing_catalog_revision(widgets):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE catalog_meta(singleton,generation,revision)')
    db.execute("INSERT INTO catalog_meta VALUES(1,'boot',1)")
    widgets.host.catalog = SimpleNamespace(index=SimpleNamespace(db=db, lock=RLock()))
    widgets.broken = True
    widgets.service.refresh_dependencies()
    assert widgets.props == {'Bobi.Rail.Revision.personal_library': '1'}
    db.execute('UPDATE catalog_meta SET revision=2')
    widgets.service.refresh_dependencies()
    assert widgets.props == {'Bobi.Rail.Revision.personal_library': '2'}
    assert not widgets.builtins
    db.close()
