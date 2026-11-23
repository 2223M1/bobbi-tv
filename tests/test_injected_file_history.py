"""Plugin composition owns history storage; platform only consumes the adapter."""
import builtins
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_platform.catalog_navigation import history_links
from bobbi_platform.host import Host
from bobbi_platform.pan_history import history_summary
from bobbi_platform.paths import ProfileBinding
from bobbi_platform.runtime import bind_call
from test_ce2097_file_history import ACCOUNT, FILE, database, history, module, playback, service


@pytest.fixture
def no_plugin_database_imports(monkeypatch):
    original = builtins.__import__

    def checked(name, *args, **kwargs):
        if name == 'lib.db' or name.startswith('lib.db.'):
            pytest.fail('Platform tried to import plugin history storage: ' + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', checked)


@pytest.mark.parametrize('plugin_root', [False, True])
@pytest.mark.parametrize('action,body', [
    ('pan_prepare_history_play', dict(history_id='a' * 64, request_id='b' * 32)),
    ('catalog_history', dict(expected=ACCOUNT)),
    ('catalog_history_links', dict(history_ids=['a' * 64])),
])
def test_history_reads_without_injection_are_unavailable(
        tmp_path, no_plugin_database_imports, plugin_root, action, body):
    host = Host(tmp_path / 'platform', plugin_root=tmp_path / 'plugin' if plugin_root else None)
    host.accounts = object()
    host.pans = SimpleNamespace()
    host._catalog = lambda: pytest.fail('Missing history must not construct a catalog')
    with pytest.raises(OSError, match='^FILE_HISTORY_UNAVAILABLE$'):
        host.dispatch(action, body)


def test_helpers_have_no_default_database(service, no_plugin_database_imports):
    owner, expected, _ = service
    with pytest.raises(OSError, match='^FILE_HISTORY_UNAVAILABLE$'):
        history_summary(owner, expected)
    with pytest.raises(OSError, match='^FILE_HISTORY_UNAVAILABLE$'):
        history_links(None, owner, ['a' * 64])
    # Existing input validation still precedes use of the optional adapter.
    with pytest.raises(ValueError, match='^CATALOG_PAGE_INVALID$'):
        history_summary(owner, expected, limit=6)
    with pytest.raises(ValueError, match='^CATALOG_PAGE_INVALID$'):
        history_links(None, owner, [])


def test_real_claim_remains_playable_without_history(service, tmp_path, no_plugin_database_imports):
    owner, expected, _ = service
    owner.list_files(expected, '0', 1, refresh=True)
    ticket = owner.prepare_play(expected, FILE)['ticket']
    host = Host(tmp_path / 'platform', plugin_root=tmp_path / 'plugin')
    host.accounts, host.pans = owner.accounts, owner
    claimed = host.dispatch('pan_claim_play', {'ticket': ticket})
    assert claimed['file_ref'] == from_selected(expected, FILE, '0')
    assert claimed['history'] is None


def test_missing_history_is_unavailable_over_real_runtime(tmp_path, no_plugin_database_imports):
    host = Host(tmp_path / 'platform', plugin_root=tmp_path / 'plugin')
    host.start()
    try:
        with pytest.raises(OSError, match='^Local service temporarily unavailable$'):
            bind_call(host.runtime.path)('catalog_history_links', {'history_ids': ['a' * 64]})
    finally:
        host.close()


def test_injected_adapter_is_reused_without_inspecting_plugin_root(tmp_path, no_plugin_database_imports):
    # Falsy adapters are valid injections, not a signal to construct defaults.
    class Adapter:
        def __bool__(self):
            return False

    adapter = Adapter()
    host = Host(tmp_path / 'platform', plugin_root=tmp_path / 'A', file_history=adapter)
    assert host._file_history() is adapter
    host.plugin_root = tmp_path / 'B'
    assert host._file_history() is adapter


def test_fixed_profile_adapters_and_old_host_never_revive_after_a_b_a(database, monkeypatch):
    storage, root = database
    current, translated = {'profile': 'A'}, []

    def translate(value):
        translated.append(value)
        return str(root / current['profile'])

    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', translate)
    ref = from_selected(ACCOUNT, FILE, '0')

    def compose():
        binding = ProfileBinding(lambda addon: root / current['profile'] / addon)
        files = history.FileHistory(storage.PickleDatabase(
            profile_root=binding.root('plugin.video.bobbi')))
        host = Host(binding.root(), plugin_root=binding.root('plugin.video.bobbi'),
                    profile_current=binding.is_current, file_history=files)
        host.accounts = object()
        host.pans = SimpleNamespace(dispatch=lambda action, body: dict(file_ref=ref))
        return host, files

    first, a_files = compose()
    a_claim = first.dispatch('pan_claim_play', {})
    a_context = dict(a_claim['history'], file_ref=ref)
    assert a_files.save(playback(a_context, position=10))
    current['profile'] = 'B'
    with pytest.raises(OSError, match='^PROFILE_CHANGED$'):
        first.dispatch('pan_claim_play', {})
    second, b_files = compose()
    b_claim = second.dispatch('pan_claim_play', {})
    assert b_files.save(playback(dict(b_claim['history'], file_ref=ref), position=20))
    # A's admitted writer remains a separate owner; a delayed report writes A.
    a_writer = history.FileHistory(storage.PickleDatabase(
        profile_root=root / 'A' / 'plugin.video.bobbi'))
    assert a_writer.save(playback(a_context, sequence=2, position=12))
    assert a_files.get(ref['id'])['position'] == 12
    assert b_files.get(ref['id'])['position'] == 20
    current['profile'] = 'A'
    with pytest.raises(OSError, match='^PROFILE_CHANGED$'):
        first.dispatch('pan_claim_play', {})
    fresh, resumed = compose()
    assert resumed.get(ref['id'])['position'] == 12
    assert fresh.dispatch('pan_claim_play', {})['history']['generation'] == 2
    assert b_files.get(ref['id'])['generation'] == 1
    assert not any(value.startswith('special://profile') for value in translated)
    assert first._file_history() is a_files and second._file_history() is b_files


@pytest.fixture
def composition(database, monkeypatch):
    storage, root = database
    subject = module('injected_portable_runtime_subject', 'addons/plugin.video.bobbi/lib/portable_runtime.py')
    state = SimpleNamespace(created=[], reports=[], started=False, closed=False, playback=False)
    binding = ProfileBinding(lambda addon: root / 'A' / addon)
    monkeypatch.setitem(sys.modules, 'bobbi_platform.paths', SimpleNamespace(ProfileBinding=lambda: binding))
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', SimpleNamespace(
        configure=lambda *args, **kwargs: None, native_subtitle_abi=lambda caps: None))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', storage)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        log=lambda value, level: state.reports.append(value), LOGINFO=1,
        Player=lambda: SimpleNamespace(isPlaying=lambda: False),
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda seconds: True)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda number: object()))
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(Addon=lambda name:
        SimpleNamespace(getSetting=lambda key: '')))
    component = lambda *args, **kwargs: SimpleNamespace(start=lambda: None, tick=lambda: None, close=lambda: None)
    monkeypatch.setitem(sys.modules, 'lib.cinema.focus_anchor', SimpleNamespace(HomeRailLifecycle=component))
    monkeypatch.setitem(sys.modules, 'lib.services.widget_refresh', SimpleNamespace(WidgetRefreshService=component))

    def create(root, **kwargs):
        state.created.append(dict(root=root, **kwargs))
        host = Host(root, **kwargs)

        def start():
            assert host.check_profile()
            state.started = True

        def close():
            state.closed = True

        host.start, host.close = start, close
        return host

    def standard(host):
        state.playback = True
        return SimpleNamespace(tick=lambda: None)

    monkeypatch.setitem(sys.modules, 'bobbi_platform.host', SimpleNamespace(Host=create))
    monkeypatch.setitem(sys.modules, 'lib.services.standard_playback', SimpleNamespace(StandardPlayback=standard))
    return SimpleNamespace(subject=subject, storage=storage, state=state, binding=binding)


def test_portable_composition_injects_fixed_root_adapter(composition):
    composition.subject.main({'native_contract_available': False})
    state = composition.state
    assert state.started and state.playback and state.closed
    assert len(state.created) == 1
    args = state.created[0]
    assert args['plex_binding'].saved == dict(location='', token='', user_token='')
    assert args['plex_binding'].current()
    adapter = args['file_history']
    assert isinstance(adapter, history.FileHistory)
    assert Path(adapter.database._database_path) == args['plugin_root'] / 'database.pickle'
    assert args['plugin_root'] == composition.binding.root('plugin.video.bobbi')
    assert adapter.report is args['report']
    assert not any('FILE_HISTORY_UNAVAILABLE' in code for code in state.reports)


@pytest.mark.parametrize('failure', [ImportError, OSError, ValueError, RuntimeError, sqlite3.OperationalError])
def test_history_composition_failure_does_not_stop_portable_playback(composition, monkeypatch, failure):
    attempted = []

    def unavailable(*, profile_root):
        attempted.append(profile_root)
        raise failure('controlled history assembly failure')

    monkeypatch.setattr(composition.storage, 'PickleDatabase', unavailable)
    composition.subject.main({'native_contract_available': False})
    state = composition.state
    assert attempted == [composition.binding.root('plugin.video.bobbi')]
    assert state.created[0]['file_history'] is None
    assert state.started and state.playback and state.closed
    assert state.reports == ['[bobbi] FILE_HISTORY_UNAVAILABLE']
