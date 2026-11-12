"""One dependency reader feeds a bounded owner-side revision publication."""
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
    state = SimpleNamespace(props={}, reads=0, initialized=0,
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
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(getSkinDir=lambda: 'skin.bobbi.cinema'))
    window = SimpleNamespace(getProperty=lambda key: state.props.get(key, ''),
        setProperty=lambda key, value: state.props.update({key: value}))
    spec = importlib.util.spec_from_file_location('widget_local_test',
        ROOT/'addons/plugin.video.bobbi/lib/services/widget_refresh.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state.host = SimpleNamespace(catalog=None)
    state.service = module.WidgetRefreshService(host=state.host, window=window)
    def sample():
        state.service.refresh_dependencies()
        state.service.tick()
    state.sample = sample
    return state


def test_unchanged_samples_do_not_reload_history_or_refresh_other_rows(widgets):
    widgets.props['Bobi.Rail.Revision.popular_tv'] = '7'
    for _ in range(10): widgets.sample()
    assert widgets.initialized == 1 and widgets.reads == 1
    assert widgets.props == {'Bobi.Rail.Revision.popular_tv': '7',
                             'Bobi.Rail.Revision.continue_watching': '1'}
    assert widgets.host.catalog is None


def test_history_content_revision_changes_only_continue_row(widgets):
    widgets.sample()
    widgets.path.write_bytes(b'new unrelated data')
    widgets.sample()
    assert widgets.props['Bobi.Rail.Revision.continue_watching'] == '1'
    widgets.values['jt:lfh']['record'] = {'progress': 50}
    widgets.path.write_bytes(b'new history')
    widgets.sample()
    assert widgets.props == {'Bobi.Rail.Revision.continue_watching': '2'}


def test_broken_history_does_not_block_existing_catalog_revision(widgets):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE catalog_meta(singleton,generation,revision)')
    db.execute("INSERT INTO catalog_meta VALUES(1,'boot',1)")
    widgets.host.catalog = SimpleNamespace(index=SimpleNamespace(db=db, lock=RLock()))
    widgets.broken = True
    widgets.sample()
    assert widgets.props == {'Bobi.Rail.Revision.personal_library': '1'}
    db.execute('UPDATE catalog_meta SET revision=2')
    widgets.sample()
    assert widgets.props == {'Bobi.Rail.Revision.personal_library': '2'}
    db.close()


def test_owner_ticks_never_read_storage_and_worker_never_writes_window(widgets):
    for _ in range(100): widgets.service.tick()
    assert widgets.reads == 0 and widgets.initialized == 0
    widgets.service.refresh_dependencies()
    assert widgets.reads == 1 and widgets.props == {}
    widgets.service.tick()
    assert widgets.props['Bobi.Rail.Revision.continue_watching'] == '1'
    for _ in range(100): widgets.service.tick()
    assert widgets.reads == 1


def test_mailbox_coalesces_changes_and_failed_window_write_retries(widgets, monkeypatch):
    for number in range(50):
        widgets.service._offer({'personal_library': ('generation', number)})
    assert widgets.service.mailbox.qsize() == 1
    original = widgets.service.window.setProperty
    failed = []
    def write(key, value):
        if not failed:
            failed.append(key)
            raise RuntimeError('Temporary Window failure')
        original(key, value)
    monkeypatch.setattr(widgets.service.window, 'setProperty', write)
    with pytest.raises(RuntimeError): widgets.service.tick()
    widgets.service.tick()
    assert widgets.props['Bobi.Rail.Revision.personal_library'] == '1'
    assert widgets.service.revisions['personal_library'] == ('generation', 49)


def catalog_dependency(widgets, lock=None):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE catalog_meta(singleton,generation,revision)')
    db.execute("INSERT INTO catalog_meta VALUES(1,'boot',1)")
    widgets.host.catalog = SimpleNamespace(index=SimpleNamespace(db=db, lock=lock or RLock()))
    return db


def test_named_views_change_only_personal_library_revision(widgets):
    from lib.db.catalog_views import KEY
    db = catalog_dependency(widgets)
    widgets.sample()
    widgets.values[KEY] = {'schema': 1, 'items': [], 'active': 'a'*32}
    widgets.path.write_bytes(b'named view updated')
    widgets.sample()
    assert widgets.props == {'Bobi.Rail.Revision.continue_watching': '1',
                             'Bobi.Rail.Revision.personal_library': '2'}
    assert widgets.reads == 2
    widgets.sample()
    assert widgets.reads == 2 and widgets.props['Bobi.Rail.Revision.personal_library'] == '2'
    db.close()


def test_busy_index_defers_view_revision_until_real_catalog_snapshot(widgets):
    from lib.db.catalog_views import KEY
    locked = [False]
    lock = SimpleNamespace(acquire=lambda **kw: not locked[0], release=lambda: None)
    db = catalog_dependency(widgets, lock)
    widgets.sample()
    original = widgets.service.revisions['personal_library']
    locked[0] = True
    widgets.values[KEY] = {'changed': True}
    widgets.path.write_bytes(b'changed saved views with held lock')
    widgets.sample()
    assert widgets.service.revisions['personal_library'] == original
    assert widgets.props['Bobi.Rail.Revision.personal_library'] == '1'
    locked[0] = False
    widgets.sample()
    assert widgets.service.revisions['personal_library'][:2] == original[:2]
    assert widgets.props['Bobi.Rail.Revision.personal_library'] == '2'
    db.close()


def test_profile_change_after_worker_read_cannot_publish_old_profile(widgets):
    current = [True]
    widgets.host.check_profile = lambda: current[0]
    widgets.service.refresh_dependencies()
    assert widgets.service.mailbox.qsize() == 1 and not widgets.props
    current[0] = False
    widgets.service.tick()
    widgets.service.refresh_dependencies()
    assert not widgets.props and widgets.reads == 1


def test_dependency_database_uses_captured_host_profile_root(widgets, monkeypatch, tmp_path):
    roots = []
    original = sys.modules['lib.db.pickle_db'].PickleDatabase
    monkeypatch.setattr(sys.modules['lib.db.pickle_db'], 'PickleDatabase',
                        lambda profile_root: (roots.append(profile_root) or original()))
    widgets.host.plugin_root = tmp_path/'captured-profile'
    widgets.sample()
    assert roots == [widgets.host.plugin_root]
