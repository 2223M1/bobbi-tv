"""Use real projection/discovery functions; IO and Kodi presentation are isolated."""
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from lib.clients.tmdb import related_movies as films


def _related(now, complete=True):
    show = dict(id=42, name='Example', original_name='Example',
                original_language='ja', genres=[{'id': 16}])
    return dict(schema=3, id=42, time=now, complete=complete,
                movies=[], show=show, detail_after=None)


@pytest.mark.parametrize('age,failed', [(0, False), (90000, True)])
def test_reading_related_hit_or_failure_fallback_never_writes(monkeypatch, age, failed):
    from lib.db.cached import cache
    from lib.clients.tmdb.utils import utils
    old = _related(200000-age)
    monkeypatch.setattr(films.time, 'time', lambda: 200000)
    monkeypatch.setattr(cache, 'get', lambda key: old)
    put = MagicMock()
    monkeypatch.setattr(cache, 'set', put)
    def fetch(*args):
        if failed:
            raise OSError('offline')
        pytest.fail('A fresh complete cache hit must not fetch')
    monkeypatch.setattr(utils, 'tmdb_get', fetch)
    for _ in range(2):
        result = films.load(42)
        assert result['time'] == old['time'] and result['stale'] is failed
    put.assert_not_called()


def test_new_related_snapshot_is_written_and_cancelled_snapshot_is_not(monkeypatch):
    from lib.db.cached import cache
    from lib.clients.tmdb.utils import utils
    old = _related(100000)
    monkeypatch.setattr(films.time, 'time', lambda: 200000)
    monkeypatch.setattr(cache, 'get', lambda key: old)
    put = MagicMock()
    monkeypatch.setattr(cache, 'set', put)
    def fetch(action, args):
        if action == 'tv_details':
            return old['show']
        assert action == 'search_movie'
        return dict(results=[], total_results=0, total_pages=1, page=1)
    monkeypatch.setattr(utils, 'tmdb_get', fetch)
    assert films.load(42)['time'] == 200000
    put.assert_called_once()
    put.reset_mock()
    # Preserve the final cancellation gate even when discovery just finished.
    updated = dict(old, complete=False, detail_after=99)
    monkeypatch.setattr(films, 'discover', lambda *a, **k: (updated, True))
    films.load(42, cancelled=lambda: True)
    put.assert_not_called()
    films.load(42)
    assert put.call_args.args[1]['detail_after'] == 99


class Item:
    def __init__(self, label=''):
        self.label, self.label2, self.art, self.properties = label, '', {}, {}
        self.tag = MagicMock()
    def getVideoInfoTag(self): return self.tag
    def setArt(self, value): self.art.update(value)
    def setProperty(self, key, value): self.properties[key] = value
    def setLabel(self, value): self.label = value
    def setLabel2(self, value): self.label2 = value
    def addContextMenuItems(self, rows): self.context = rows


@pytest.fixture
def metadata(monkeypatch):
    from lib.db.cached import cache
    from lib.clients.tmdb import frontend_metadata as front
    show = dict(id=42, name='作品', original_name='Example', original_language='en',
        translations=dict(translations=[dict(iso_639_1='zh', iso_3166_1='CN', data=dict(name='作品'))]),
        poster_path='/work.jpg', backdrop_path='/bg.jpg')
    season = dict(season_number=1, name='副标题', poster_path='/season.jpg',
        episodes=[dict(episode_number=n, name='第{}话'.format(n), still_path='/ep{}.jpg'.format(n))
                  for n in range(1, 101)])
    store = {front.PREFIX+'tv:42': dict(refresh_after=1e20, data=show),
             front.PREFIX+'tv:42:season:1': dict(refresh_after=1e20, data=season)}
    reads = []
    monkeypatch.setattr(cache, 'get', lambda key: (reads.append(key), store.get(key))[1])
    monkeypatch.setattr(front, 'image_url', lambda value, size: size + ':' + value if value else '')
    monkeypatch.setattr(front, '_pending', {})
    return front, store, reads


def _card(front, number, projection=None, **extra):
    item = Item()
    front.apply(item, 42, 'episode', dict(title='Fallback', season=1, episode=number, **extra),
                projection=projection)
    return item


def _shown(item):
    return item.label, item.label2, item.properties, item.art, item.tag.mock_calls


@pytest.mark.parametrize('missing_bilingual', [False, True])
def test_page_snapshot_reduces_100_episode_reads_without_changing_cards(metadata, missing_bilingual):
    front, store, reads = metadata
    if missing_bilingual:
        details = store[front.PREFIX+'tv:42']['data']
        details.pop('translations')
        details.pop('original_language')
        store['am6b_anime_titles_v1|tv|42'] = dict(zh='缓存标题', en='Cached title')
    original = deepcopy(store)
    reference = [_shown(_card(front, number)) for number in range(1, 101)]
    assert len(reads) == (300 if missing_bilingual else 200)
    reads.clear()
    projection = front.episode_projection('42', '1')
    actual = [_shown(_card(front, number, projection)) for number in range(1, 101)]
    assert actual == reference
    assert len(reads) == (3 if missing_bilingual else 2)
    assert store == original


def test_snapshot_is_one_page_only_and_wrong_identity_does_not_reuse_it(metadata):
    front, store, reads = metadata
    old = front.episode_projection(42, 1)
    store[front.PREFIX+'tv:42:season:1']['data']['episodes'][0]['name'] = '更新标题'
    _card(front, 1, old).tag.setTitle.assert_called_with('第1话')
    new = front.episode_projection(42, 1)
    _card(front, 1, new).tag.setTitle.assert_called_with('更新标题')
    reads.clear()
    item = Item()
    front.apply(item, 99, 'episode', dict(title='Other', season=1, episode=1), projection=old)
    assert front.PREFIX+'tv:99' in reads
    assert not item.art
    reads.clear()
    front.apply(Item(), 42, 'episode', dict(season=2, episode=1), projection=old)
    assert front.PREFIX+'tv:42:season:2' in reads


def test_snapshot_retains_stale_refresh_and_urgent_upgrade(metadata):
    front, store, reads = metadata
    for record in store.values():
        record['refresh_after'] = 0
    projection = front.episode_projection(42, 1)
    assert front._pending == {'tv:42': False, 'tv:42:season:1': False}
    _card(front, 1, projection, continue_watching=True)
    assert front._pending == {'tv:42': True, 'tv:42:season:1': True}
    assert len(reads) == 2


def test_malformed_optional_cache_row_does_not_drop_the_episode_page(metadata):
    front, store, reads = metadata
    season = store[front.PREFIX+'tv:42:season:1']['data']
    season['episodes'].append(None)
    view = front.episode_projection(42, 1)
    assert view is not None
    _card(front, 1, view).tag.setTitle.assert_called_with('第1话')
    season['episodes'] = None
    assert front.episode_projection(42, 1) is None


def test_real_episode_directory_shares_projection_with_thread_workers(metadata, monkeypatch):
    from lib.utils.views import shows
    from lib.utils.general import utils as general
    front, store, reads = metadata
    rows = []
    monkeypatch.setattr(shows, 'get_fanart_details', lambda **k: {})
    monkeypatch.setattr(shows, 'make_list_item', Item)
    monkeypatch.setattr(shows, 'set_media_infoTag', lambda *a, **k: None)
    monkeypatch.setattr(shows, 'add_tmdb_episode_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'is_trakt_auth', lambda: False)
    monkeypatch.setattr(shows, 'add_simkl_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'add_nuvio_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'build_url', lambda action, **kw: dict(action=action, **kw))
    monkeypatch.setattr(shows, 'add_directory_items_batch', rows.extend)
    monkeypatch.setattr(general, 'get_setting', lambda *a: 4)
    page = store[front.PREFIX+'tv:42:season:1']['data']
    assert shows.show_episode_info('Example', 1, {'tmdb_id': 42}, 'tv', 'tv',
        prepared_pages={'zh-CN': page}) == 100
    assert len(reads) == 2
    assert [row[0]['tv_data']['episode'] for row in rows] == list(range(1, 101))
    assert all(row[0]['action'] == 'search' and not row[2] for row in rows)
    assert all(row[0]['tv_data']['season'] == 1 for row in rows)
    # A display-only remapping still writes its own season/episode after the
    # real metadata projection; neither that identity nor the route is changed.
    result = shows._process_episode(page['episodes'][0], 'Example', 1, {'tmdb_id': 42},
        'tv', 'tv', {}, display_order={'season': 2, 'episode': 3},
        projection=front.episode_projection(42, 1))
    assert result[1]['tv_data']['season'] == 1 and result[1]['tv_data']['episode'] == 1
    result[2].tag.setSeason.assert_called_with(2)
    result[2].tag.setEpisode.assert_called_with(3)
    assert result[2].properties['Bobi.SeasonName'] == ''
