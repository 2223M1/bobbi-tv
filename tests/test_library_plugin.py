import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

from bobbi_platform.libraries import LibraryError, Registry, import_catalog, vfs_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    state = SimpleNamespace(rows=[], resolved=[], ended=[], calls=[], props={},
        directories=['Season 1'], files=['film.mkv'], aborted=False, exists=True,
        submit_error=False, on_make=None, category=None, content=None, closed=0)
    state.path = tmp_path / 'libraries.sqlite3'
    state.source = vfs_source('NAS', 'smb://nas.example/Movies', 'user', 'test-secret')
    store = Registry(state.path)
    store.save(state.source)
    store.close()

    class ListItem:
        def __init__(self, label='', path=''):
            self.label, self.path, self.properties, self.art = label, path, {}, {}
            if path and state.on_make:
                state.on_make()

        def setProperty(self, key, value):
            self.properties[key] = value

        def setLabel2(self, value):
            self.label2 = value

        def setInfo(self, kind, value):
            self.info = value

        def setContentLookup(self, value):
            self.lookup = value

        def setArt(self, value):
            self.art = value

        def getVideoInfoTag(self):
            return SimpleNamespace(setTitle=lambda value: setattr(self, 'title', value))

    def resolve(handle, success, item):
        state.resolved.append((handle, success, item))
        if state.submit_error:
            raise RuntimeError('lost acknowledgement')

    def listdir(path):
        state.calls.append(('listdir', path))
        return state.directories, state.files

    xbmc = SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: state.aborted),
        Player=lambda: SimpleNamespace(play=lambda *args: state.calls.append(('play', args))),
        executebuiltin=lambda command: state.calls.append(('builtin', command)))
    gui = SimpleNamespace(ListItem=ListItem,
        Window=lambda _: SimpleNamespace(setProperty=lambda k, v: state.props.update({k: v}),
            getProperty=lambda k: state.props.get(k, '')),
        Dialog=lambda: SimpleNamespace(ok=lambda *args: state.calls.append(('dialog', args))))
    kodi_plugin = SimpleNamespace(setResolvedUrl=resolve,
        endOfDirectory=lambda *a, **kw: state.ended.append((a, kw)),
        addDirectoryItems=lambda h, rows, size: state.rows.extend(rows),
        setPluginCategory=lambda h, c: setattr(state, 'category', c),
        setContent=lambda h, c: setattr(state, 'content', c))
    vfs = SimpleNamespace(translatePath=lambda _: str(tmp_path),
        listdir=listdir, exists=lambda _: state.exists)
    for name, value in [('xbmc', xbmc), ('xbmcgui', gui), ('xbmcplugin', kodi_plugin), ('xbmcvfs', vfs)]:
        monkeypatch.setitem(sys.modules, name, value)
    spec = importlib.util.spec_from_file_location('_bobbi_library_plugin', ROOT / 'addons/plugin.video.bobbi.library/default.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class TrackedRegistry(Registry):
        def close(self):
            state.closed += 1
            super().close()

    monkeypatch.setattr(module, 'registry', lambda _: TrackedRegistry(state.path))
    state.module = module
    return state


def test_root_lists_sources_without_network_or_credentials(plugin):
    plugin.module.execute(17, {})
    assert len(plugin.rows) == 2
    assert not plugin.calls and not plugin.resolved
    assert plugin.rows[0][1].label == '管理片库来源'
    assert plugin.rows[1][1].label == 'NAS'
    assert plugin.rows[0][1].properties['Bobi.Library.Manage'] == 'true'
    assert plugin.rows[1][1].properties['Bobi.Library.Kind'] == 'smb'
    assert plugin.rows[1][1].label2 == 'SMB · nas.example'
    assert plugin.rows[1][1].properties['Bobi.Library.Location'] == 'SMB · nas.example'
    assert all('test-secret' not in target and 'nas.example' not in target for target, _, _ in plugin.rows)
    assert plugin.content == 'files' and plugin.closed == 1


def test_browse_filters_files_and_routes_only_local_ids(plugin):
    plugin.files += ['execute.py', 'remote.strm']
    plugin.module.execute(17, {'action': 'browse', 'source': plugin.source.id})
    assert len(plugin.rows) == 2
    assert plugin.rows[0][1].label == 'Season 1' and plugin.rows[0][2]
    target, row, folder = plugin.rows[1]
    assert not folder and row.properties['IsPlayable'] == 'true'
    assert row.lookup is False
    assert row.info['size'] == -1  # missing metadata is not a zero-byte file
    assert 'test-secret' not in target
    assert dict(parse_qsl(urlsplit(target).query)) == {
        'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'}
    assert plugin.category == 'NAS'
    assert plugin.calls[0][0] == 'listdir' and not plugin.resolved


@pytest.mark.parametrize('location,expected', [
    ('/mnt/CloudDrive', '/mnt/CloudDrive/Season 1/'),
    ('smb://nas.example/Movies', 'smb://nas.example/Movies/Season%201/'),
    ('davs://nas.example/Movies', 'davs://nas.example/Movies/Season%201/'),
    (r'C:\Movies', 'C:\\Movies\\Season 1\\'),
])
def test_nested_directory_uses_kodi_folder_exists_semantics(plugin, monkeypatch, location, expected):
    source = vfs_source('Existing files', location)
    store = Registry(plugin.path)
    try:
        store.save(source)
    finally:
        store.close()
    checked, listed = [], []
    def folder_exists(path):
        checked.append(path)
        return path == expected  # Kodi treats a slashless path as a file.
    def listing(path):
        listed.append(path)
        return ((False, 'film.mkv'),), {}
    monkeypatch.setattr(plugin.module.xbmcvfs, 'exists', folder_exists)
    monkeypatch.setattr(plugin.module, 'listing_with_metadata', listing)
    plugin.module.execute(17, {'action': 'browse', 'source': source.id, 'relative': 'Season 1'})
    assert checked == listed == [expected]
    assert plugin.rows[0][1].label == 'film.mkv'
    assert not plugin.resolved


def test_pagination_reaches_last_page_without_losing_or_repeating_items(plugin):
    plugin.directories = []
    plugin.files = ['film-%05d.mkv' % n for n in range(10000)]
    labels = []
    params = {'action': 'browse', 'source': plugin.source.id}
    for page in range(50):
        plugin.rows = []
        plugin.module.execute(17, params)
        labels.extend(row.label for _, row, folder in plugin.rows if not folder)
        next_rows = [target for target, row, _ in plugin.rows if row.label == '下一页']
        assert all(row.properties.get('Bobi.NextPage') == 'true' for _, row, _ in plugin.rows if row.label == '下一页')
        if page < 49:
            assert len(next_rows) == 1
            params = dict(parse_qsl(urlsplit(next_rows[0]).query))
        else:
            assert not next_rows
    assert len(labels) == 10000 and len(set(labels)) == 10000
    assert not plugin.resolved


def test_chosen_nas_file_is_handed_off_once_not_downloaded(plugin):
    plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id,
                               'relative': 'Season 1/first.mkv'})
    assert len(plugin.resolved) == 1
    handle, success, item = plugin.resolved[0]
    assert handle == 17 and success is True
    assert item.path == 'smb://user:test-secret@nas.example/Movies/Season%201/first.mkv'
    assert not plugin.calls and not plugin.ended and plugin.closed == 1


def test_catalog_selection_resolves_exact_entry_not_first(plugin):
    value = {'schema': 'bobbi-library-v1', 'name': 'My list', 'items': [
        {'id': str(i), 'title': 'Film ' + str(i), 'url': 'https://media.example/%d.mkv' % i}
        for i in range(3)]}
    source = import_catalog(json.dumps(value))
    store = Registry(plugin.path)
    store.save(source)
    store.close()
    plugin.module.execute(17, {'action': 'play', 'source': source.id, 'entry': '2'})
    assert plugin.resolved[0][2].path == 'https://media.example/2.mkv'
    assert not plugin.calls


@pytest.mark.parametrize('relative', ['../x.mkv', 'bad.strm', 'bad.py', '', '/other/film.mkv'])
def test_forged_play_route_is_resolved_as_failure(plugin, relative):
    with pytest.raises(LibraryError):
        plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': relative})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False
    assert not plugin.calls


def test_abort_or_new_selection_prevents_late_play(plugin):
    plugin.on_make = lambda: plugin.props.update({'bobbi.portable_selection': 'newer-request'})
    plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False
    plugin.resolved = []
    plugin.on_make = None
    plugin.aborted = True
    plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False


def test_removed_configuration_cannot_submit_stale_credentials(plugin):
    def remove():
        store = Registry(plugin.path)
        store.remove(plugin.source.id)
        store.close()
    plugin.on_make = remove
    with pytest.raises(LibraryError, match='SOURCE_NOT_FOUND'):
        plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False


def test_lost_submission_acknowledgement_never_retries_or_sends_failure(plugin):
    plugin.submit_error = True
    with pytest.raises(RuntimeError, match='lost acknowledgement'):
        plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is True
    assert plugin.closed == 1 and not plugin.calls


def test_failed_registry_initialization_ends_play_resolver(plugin, monkeypatch):
    def unavailable(_):
        raise LibraryError('STORAGE_UNAVAILABLE')
    monkeypatch.setattr(plugin.module, 'registry', unavailable)
    with pytest.raises(LibraryError):
        plugin.module.execute(17, {'action': 'play', 'source': plugin.source.id, 'relative': 'film.mkv'})
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False


def test_manage_is_explicit_and_does_not_play(plugin):
    plugin.module.execute(17, {'action': 'manage'})
    assert plugin.calls == [('builtin', 'RunScript(script.bobbi.setup,libraries)')]
    assert not plugin.resolved and plugin.ended[0][1]['succeeded'] is False


def test_native_metadata_is_one_listing_not_per_file_stat(plugin, monkeypatch):
    requests = []
    def rpc(raw):
        request = json.loads(raw)
        requests.append(request)
        base = request['params']['directory']
        return json.dumps({'result': {'files': [
            {'file': base + 'Season%201/', 'filetype': 'directory'},
            {'file': base + 'film.mkv', 'filetype': 'file', 'size': 2000000000,
             'lastmodified': '2026-10-21 09:10:11'},
            {'file': base + 'bad.strm', 'filetype': 'file'}], 'limits': {'total': 3}}})
    monkeypatch.setattr(plugin.module.xbmc, 'executeJSONRPC', rpc, raising=False)
    plugin.module.execute(17, {'action': 'browse', 'source': plugin.source.id})
    assert len(requests) == 1 and not plugin.calls
    assert len(plugin.rows) == 2
    assert plugin.rows[1][1].info == {'size': 2000000000, 'date': '21.10.2026'}


def test_catalog_metadata_no_media_probe(plugin):
    source = import_catalog(json.dumps({'schema': 'bobbi-library-v1', 'name': 'Catalog', 'items': [
        {'id': 'a', 'title': 'Film', 'url': 'https://media.example/file.mkv',
         'size': 12345678, 'modified': '2026-10-21'}]}))
    store = Registry(plugin.path)
    store.save(source)
    store.close()
    plugin.module.execute(17, {'action': 'browse', 'source': source.id})
    assert plugin.rows[0][1].info == {'size': 12345678, 'date': '21.10.2026'}
    assert not plugin.calls
