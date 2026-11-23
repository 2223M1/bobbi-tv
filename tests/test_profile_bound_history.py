"""Profile handoff uses captured paths, never credentials or a second writer."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import paths


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_binding_checks_both_roots_without_creating_them_and_never_revives(tmp_path):
    current = {'profile': 'A'}
    resolve = lambda addon: tmp_path / current['profile'] / addon
    binding = paths.ProfileBinding(resolve)
    assert binding.root() == tmp_path / 'A' / 'script.module.bobbi.platform'
    assert binding.root('plugin.video.bobbi') == tmp_path / 'A' / 'plugin.video.bobbi'
    assert binding.is_current() and not list(tmp_path.iterdir())
    current['profile'] = 'B'
    assert not binding.is_current()
    current['profile'] = 'A'
    assert not binding.is_current()
    with pytest.raises(ValueError, match='^PROFILE_CHANGED$'):
        binding.require_current()
    assert not list(tmp_path.iterdir())


def test_binding_rejects_capture_spanning_profile_switch(tmp_path):
    calls = []

    def resolve(addon):
        calls.append(addon)
        return tmp_path / ('A' if len(calls) <= 2 else 'B') / addon

    with pytest.raises(ValueError, match='^PROFILE_CHANGED$'):
        paths.ProfileBinding(resolve)


def test_plugin_root_change_alone_revokes_binding(tmp_path):
    plugin = {'root': 'A'}
    binding = paths.ProfileBinding(lambda addon: tmp_path /
        (plugin['root'] if addon == 'plugin.video.bobbi' else 'platform') / addon)
    plugin['root'] = 'B'
    assert not binding.is_current()


def test_resolution_failure_revokes_binding(tmp_path):
    fail = {'active': False}

    def resolve(addon):
        if fail['active']:
            raise OSError('Fixture inaccessible profile')
        return tmp_path / addon

    binding = paths.ProfileBinding(resolve)
    fail['active'] = True
    assert not binding.is_current()
    fail['active'] = False
    assert not binding.is_current()


def test_profile_root_is_read_only_and_refuses_unresolved_special_path(tmp_path, monkeypatch):
    target = tmp_path / 'not-yet-created'
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(target)))
    assert paths.profile_root() == target
    assert not target.exists()
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda value: value))
    with pytest.raises(ValueError, match='Absolute profile path required'):
        paths.profile_root()


@pytest.mark.parametrize('addon', ['plugin.bobbi/../../outside', 'plugin.bobbi\\outside', 'script.other', None])
def test_profile_root_rejects_addon_path_injection(addon, monkeypatch):
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: pytest.fail('Invalid addon resolved')))
    with pytest.raises(ValueError):
        paths.profile_root(addon)


@pytest.fixture
def writer(tmp_path, monkeypatch):
    active = {'root': tmp_path / 'A'}
    for name in ('A', 'B'):
        (tmp_path / name).mkdir()
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda _: str(active['root']),
        mkdirs=lambda root: Path(root).mkdir(parents=True, exist_ok=True)))
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=lambda *args: None))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(ADDON_ID='plugin.video.bobbi'))
    database = load('profile_bound_pickle_subject', 'addons/plugin.video.bobbi/lib/db/pickle_db.py')
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', database)
    observed = []

    def save(snapshot, database):
        observed.append((dict(snapshot), database._database_path))
        database.set_item('jt:lfh', snapshot['id'], snapshot)
        return True

    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=save))
    subject = load('profile_bound_history_subject', 'addons/plugin.video.bobbi/lib/db/deferred_history.py')
    queued = []

    class DeferredThread:
        def __init__(self, target, args, name, daemon):
            assert daemon is False
            self.target, self.args = target, args

        def start(self):
            queued.append(self)

        def run(self):
            self.target(*self.args)

    monkeypatch.setattr(subject, 'Thread', DeferredThread)
    return SimpleNamespace(subject=subject, database=database, active=active,
                           observed=observed, queued=queued, root=tmp_path)


def test_queued_a_snapshot_writes_a_after_kodi_has_switched_to_b(writer):
    data = dict(id='A-file', position=12)
    assert writer.subject.defer_watched_file(data)
    data['position'] = 99
    writer.active['root'] = writer.root / 'B'
    writer.queued.pop().run()
    assert writer.observed == [(dict(id='A-file', position=12), str(writer.root / 'A' / 'database.pickle'))]
    assert not (writer.root / 'B' / 'database.pickle').exists()
    assert writer.database.PickleDatabase(profile_root=writer.root / 'A').get_key('jt:lfh')['A-file']['position'] == 12


def test_a_b_a_submissions_keep_same_lane_and_separate_database_owners(writer):
    for name in ('A', 'B', 'A'):
        writer.active['root'] = writer.root / name
        assert writer.subject.defer_watched_file(dict(id=name + '-file', position=len(writer.observed)))
        assert not writer.subject.defer_watched_file(dict(id='busy', position=99))
        writer.queued.pop().run()
    for name, position in (('A', 2), ('B', 1)):
        rows = writer.database.PickleDatabase(profile_root=writer.root / name).get_key('jt:lfh')
        assert rows == {name + '-file': dict(id=name + '-file', position=position)}
    assert len(writer.subject._databases) == 2


def test_pending_profile_writers_are_not_evicted_and_admission_is_bounded(writer):
    subject = writer.subject
    for index in range(subject._MAX_PROFILES):
        subject._databases[writer.root / str(index)] = SimpleNamespace(has_pending=lambda: True)
    assert not subject.defer_watched_file(dict(id='new', position=1))
    assert not writer.queued and len(subject._databases) == subject._MAX_PROFILES
    assert subject._lane.acquire(blocking=False)
    subject._lane.release()


def test_clean_old_profile_writer_can_be_evicted_without_rebinding_another(writer):
    subject = writer.subject
    for index in range(subject._MAX_PROFILES):
        subject._databases[writer.root / str(index)] = SimpleNamespace(has_pending=lambda: False)
    assert subject.defer_watched_file(dict(id='new', position=1))
    writer.queued.pop().run()
    assert len(subject._databases) == subject._MAX_PROFILES
    assert writer.root / '0' not in subject._databases
    assert writer.database.PickleDatabase(profile_root=writer.root / 'A').get_key('jt:lfh')['new']['position'] == 1


def test_pending_receipts_are_profile_bound_even_with_identical_account_scopes(tmp_path, monkeypatch):
    from bobbi_platform import catalog_ui
    expected = dict(provider='quark', account_id='quark:' + 'a' * 64, epoch=1, authenticated=True)
    active = {'root': tmp_path / 'A'}
    properties = {}
    window = SimpleNamespace(getProperty=lambda key: properties.get(key, ''), setProperty=properties.__setitem__)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda _: window))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(active['root'])))
    catalog_ui._pending_receipts(expected, request_id='a' * 32, count=1)
    active['root'] = tmp_path / 'B'
    assert catalog_ui._pending_receipts(expected) == []
    catalog_ui._pending_receipts(expected, request_id='b' * 32, count=2)
    # A's delayed result uses its admission root, not whichever UI is active.
    catalog_ui._pending_receipts(expected, request_id='c' * 32, count=3, profile_root=tmp_path / 'A')
    assert catalog_ui._pending_receipts(expected) == [dict(request_id='b' * 32, count=2)]
    active['root'] = tmp_path / 'A'
    assert catalog_ui._pending_receipts(expected) == [dict(request_id='a' * 32, count=1), dict(request_id='c' * 32, count=3)]


def test_receipt_lookup_never_rebinds_after_profile_changes_in_dialog(tmp_path, monkeypatch):
    from bobbi_platform import catalog_ui, runtime
    expected = dict(provider='quark', account_id='quark:' + 'a' * 64, epoch=1, authenticated=True)
    active = {'root': tmp_path / 'A'}
    calls = []
    properties = {}
    window = SimpleNamespace(getProperty=lambda key: properties.get(key, ''), setProperty=properties.__setitem__)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda _: window))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(active['root'])))
    monkeypatch.setattr(runtime, 'bind_call', lambda path: lambda *args, **kwargs: calls.append(path) or dict(items=[]))
    catalog_ui._pending_receipts(expected, request_id='a' * 32, count=1)

    def select(*args):
        active['root'] = tmp_path / 'B'
        return 0

    dialog = SimpleNamespace(select=select, ok=lambda *args: None,
                             textviewer=lambda *args: pytest.fail('Old result displayed in B'))
    assert catalog_ui.query_receipt(dialog, expected) is None
    assert not calls
    assert catalog_ui._pending_receipts(expected) == []
