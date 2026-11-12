"""One real renderer for native and typed scopes; metadata has no file authority."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
from unittest.mock import MagicMock

import pytest

from bobbi_platform.libraries import Registry
from test_library_plugin import plugin
from test_personal_catalog import catalog, card
from test_scan_source_ports import cd2, mounted_ui, scan, movie


@pytest.fixture
def real_metadata(catalog, monkeypatch, tmp_path):
    """Load shipped apply/hydrate; replace only Kodi, cache IO and the HTTP edge."""
    path = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/clients/tmdb/frontend_metadata.py'
    spec = importlib.util.spec_from_file_location('_catalog_frontend_metadata', path)
    front = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, front)
    spec.loader.exec_module(front)
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.frontend_metadata', front)
    show = dict(id=123, name='作品中文', original_name='Example show', original_language='en',
        translations=dict(translations=[dict(iso_639_1='zh', iso_3166_1='CN', data=dict(name='作品中文'))]),
        poster_path='/work.jpg', backdrop_path='/background.jpg')
    store = {front.PREFIX + 'tv:123': dict(refresh_after=1e20, data=show)}
    cache = SimpleNamespace(get=store.get, set=lambda key, value, ttl: store.update({key: value}))
    monkeypatch.setitem(sys.modules, 'lib.db.cached', SimpleNamespace(cache=cache))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='history',
        FileHistory=lambda: SimpleNamespace(database=SimpleNamespace(get_key_checked=lambda key: {}))))
    monkeypatch.setitem(sys.modules, 'lib.utils.tmdb_init', SimpleNamespace(ensure_tmdb_init=lambda: None))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.logging', SimpleNamespace(kodilog=lambda *a: None))
    monkeypatch.setattr(front, '_root', lambda: tmp_path)
    monkeypatch.setattr(front, '_fetch', lambda key: pytest.fail('Unexpected metadata HTTP: ' + key))
    gui = sys.modules['xbmcgui']
    original = gui.ListItem

    class Item(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.label2, self.tag = '', MagicMock()
        def setLabel(self, value): self.label = value
        def getLabel2(self): return self.label2
        def getVideoInfoTag(self): return self.tag

    monkeypatch.setattr(gui, 'ListItem', Item)
    xbmc = sys.modules['xbmc']
    monkeypatch.setattr(xbmc, 'Player', lambda: SimpleNamespace(isPlayingVideo=lambda: False))
    monkeypatch.setattr(xbmc, 'getCondVisibility', lambda _: False, raising=False)
    labels = {}
    monkeypatch.setattr(xbmc, 'getInfoLabel', lambda key: labels.get(key, ''), raising=False)
    return SimpleNamespace(front=front, store=store, labels=labels, item=Item, catalog=catalog)


def test_mounted_cards_use_the_same_renderer_and_survive_remount(cd2, mounted_ui):
    service, source, _, mounts = cd2
    scan(cd2)
    params = dict(source=source.id, view='works')
    mounted_ui.catalog.execute(params, 17, mounted_ui.dispatch)
    before = [target for target, _, _ in mounted_ui.plugin.rows]
    assert before and all('plugin://plugin.video.bobbi/' in target for target in before)
    assert not any(action == 'pan_status' for action, _ in mounted_ui.calls)
    mounts[0]['generation'] = 'e' * 64
    mounted_ui.plugin.rows.clear()
    mounted_ui.catalog.execute(params, 17, mounted_ui.dispatch)
    assert [target for target, _, _ in mounted_ui.plugin.rows] == before
    assert all(item.properties['Bobi.File.State'] == 'unverified' for _, item, _ in mounted_ui.plugin.rows)
    assert not mounted_ui.plugin.resolved


def test_changed_registered_root_cannot_publish_old_cards(cd2, mounted_ui):
    service, source, media, _ = cd2
    scan(cd2)
    def changed(action, body):
        if action == 'catalog_mount_query':
            store = Registry(service.root / 'libraries.sqlite3')
            try:
                store.save(replace(source, location=(media / 'Season 0').as_posix()))
            finally:
                store.close()
    mounted_ui.after_action = changed
    mounted_ui.catalog.execute(dict(source=source.id, view='works'), 17, mounted_ui.dispatch)
    assert not mounted_ui.plugin.rows
    assert mounted_ui.plugin.ended[-1][1]['succeeded'] is False


def test_declining_current_file_selection_never_reserves_or_claims(cd2, mounted_ui):
    scan(cd2)
    mounted_ui.confirmed = False
    mounted_ui.play(movie(cd2)['entity_id'])
    assert not mounted_ui.plugin.resolved
    assert [action for action, _ in mounted_ui.calls] == ['catalog_mount_scope']


def test_mounted_menu_exposes_shared_management_and_explicit_scan(cd2, mounted_ui):
    source = cd2[1]
    mounted_ui.catalog.execute(dict(source=source.id), 17, mounted_ui.dispatch)
    routes = [dict(parse_qsl(urlsplit(target).query)) for target, _, _ in mounted_ui.plugin.rows]
    scoped = [row for row in routes if row.get('action') == 'personal_catalog_manage']
    assert len(scoped) == 2 and any(row.get('mode') == 'scan' for row in scoped)
    assert all(row['source'] == source.id and len(row['namespace']) == 64 for row in scoped)


@pytest.mark.parametrize('action', ['mounted_root', 'mounted_browse', 'mounted_search',
                                  'mounted_play', 'mounted_jobs', 'mounted_scan', 'mounted_cancel'])
def test_legacy_routes_are_small_redirects_without_io(plugin, action):
    from bobbi_platform.mounted_catalog_ui import target
    values = dict(action=action, source='a'*32, object='b'*64, parent='c'*64, task='d'*32)
    url = target(values)
    assert url.startswith('plugin://plugin.video.bobbi/?')
    plugin.module.execute(17, values)
    assert not plugin.rows and not plugin.resolved
    assert plugin.calls == [('builtin', ('RunPlugin' if action in (
        'mounted_play', 'mounted_jobs', 'mounted_scan', 'mounted_cancel') else 'Container.Update') + '(' + url + ')')]


def test_public_metadata_enriches_card_without_searching_or_changing_route(catalog, monkeypatch):
    calls = []
    def apply(item, identifier, mode, data):
        calls.append((identifier, mode, data))
        item.setArt({'poster': 'https://image.tmdb.org/t/p/w342/public.jpg'})
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.frontend_metadata', SimpleNamespace(
        apply=apply, flush=lambda: calls.append('flush')))
    catalog.page['items'] = [card(metadata_key='tmdb:tv:123', year=2026)]
    catalog.catalog.execute(catalog.params, 17, catalog.rpc)
    assert len(catalog.rows) == 1 and calls[0][:2] == (123, 'tv')
    target, item, _ = catalog.rows[0]
    assert item.art['poster'].endswith('public.jpg')
    assert item.properties['Bobi.Metadata.Key'] == 'tv:123'
    assert 'tmdb' not in dict(parse_qsl(urlsplit(target).query))
    assert [a for a, _ in catalog.query_calls] == ['pan_status', 'catalog_query', 'pan_status']


def test_real_apply_keeps_file_name_and_source_detail_in_actual_skin_fields(real_metadata):
    catalog = real_metadata.catalog
    row = card('file', metadata_key='tmdb:tv:123', year=2026)
    row['display_title'] = 'Example.S01E02.2160p.Remux.mkv'
    catalog.page['items'] = [row]
    catalog.catalog.execute(dict(catalog.params, view='files'), 17, catalog.rpc)
    target, item, folder = catalog.rows[0]
    assert not folder and target == catalog.catalog.card_target(row, catalog.account)[0]
    assert item.label == item.properties['Bobi.Title.zh'] == item.properties['AM6B.Title.zh'] == row['display_title']
    assert item.label2 == item.properties['Bobi.Library.Location'] == '已收录 · 播放前核验 · 夸克'
    item.tag.setTitle.assert_called_with(row['display_title'])
    item.tag.setOriginalTitle.assert_called_with('')
    assert all(item.properties[key] == '' for key in ('Bobi.Title.en', 'AM6B.Title.en', 'AM6B.Title.original'))
    assert item.art['poster'].endswith('/w342/work.jpg')
    assert item.art['fanart'].endswith('/w1280/background.jpg')
    assert not catalog.resolved


@pytest.mark.parametrize('kind', ['season', 'episode'])
@pytest.mark.parametrize('changed', ['', 'directory', 'work', 'season'])
def test_season_only_hydration_refreshes_only_current_directory_and_selected_season(
        real_metadata, monkeypatch, kind, changed):
    front, catalog = real_metadata.front, real_metadata.catalog
    catalog.page['items'] = [card(kind, metadata_key='tmdb:tv:123', season=0, episode=2)]
    catalog.catalog.execute(catalog.params, 17, catalog.rpc)
    _, item, _ = catalog.rows[0]
    assert item.properties['Bobi.Metadata.Key'] == 'tv:123'
    assert item.properties['Bobi.Metadata.SeasonKey'] == 'tv:123:season:0'
    start = 'plugin://plugin.video.bobbi/?action=personal_catalog&scope=first&view=episodes'
    labels = real_metadata.labels
    labels.update({'Container.FolderPath': start,
        'ListItem.Property(Bobi.Metadata.Key)': item.properties['Bobi.Metadata.Key'],
        'ListItem.Property(Bobi.Metadata.SeasonKey)': item.properties['Bobi.Metadata.SeasonKey']})
    fetched = []
    def fetch(key):
        fetched.append(key)
        if changed == 'directory':
            labels['Container.FolderPath'] = start.replace('first', 'second')
        elif changed == 'work':
            labels['ListItem.Property(Bobi.Metadata.Key)'] = 'tv:456'
        elif changed == 'season':
            labels['ListItem.Property(Bobi.Metadata.SeasonKey)'] = 'tv:123:season:1'
        return dict(season_number=0, name='特别篇', poster_path='/specials.jpg',
            episodes=[dict(episode_number=2, name='特别篇二', still_path='/special-2.jpg')])
    monkeypatch.setattr(front, '_fetch', fetch)
    catalog.calls.clear()
    assert front.hydrate()
    assert fetched == ['tv:123:season:0'], 'Hot work data must not be fetched again'
    assert catalog.calls == ([] if changed else [('builtin', 'Container.Refresh')])
    if not changed:
        catalog.rows.clear()
        catalog.catalog.execute(catalog.params, 17, catalog.rpc)
        refreshed = catalog.rows[0][1]
        assert refreshed.art['poster'].endswith('/w342/specials.jpg')
        if kind == 'episode':
            assert refreshed.art['thumb'].endswith('/w780/special-2.jpg')


@pytest.mark.parametrize('same,selected,updated,allowed', [
    (True, 'tv:123', {'tv:123'}, True), (False, 'tv:123', {'tv:123'}, False),
    (True, 'tv:456', {'tv:123'}, False), (True, '', {'tv:123'}, False),
])
def test_late_metadata_never_refreshes_another_scope_or_entity(real_metadata, same, selected, updated, allowed):
    start = 'plugin://plugin.video.bobbi/?action=personal_catalog&scope=first&view=works'
    assert real_metadata.front._refresh_catalog(start, start if same else start.replace('first', 'second'), selected, updated) is allowed
    assert not real_metadata.front._refresh_catalog('plugin://other/?action=personal_catalog',
        'plugin://other/?action=personal_catalog', selected, updated)


@pytest.mark.parametrize('selected,season', [('tv:456', 'tv:123:season:0'),
    ('tv:123', 'tv:123:season:0:extra'), ('movie:123', 'movie:123:season:0'), ('', 'tv:123:season:0')])
def test_season_refresh_requires_exact_related_public_key(real_metadata, selected, season):
    path = 'plugin://plugin.video.bobbi/?action=personal_catalog&scope=first&view=episodes'
    assert not real_metadata.front._refresh_catalog(path, path, selected, {season}, season)
