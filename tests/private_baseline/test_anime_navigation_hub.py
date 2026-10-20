"""One anime entry keeps seasons and independent related-film source actions."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import xbmc

from lib.clients.tmdb import related_movies as films


def show():
    return dict(id=1200, name='测试动画', original_name='Example Story',
                original_language='ja', genres=[{'id': 16}])


def movie():
    return dict(id=8900, title='剧场版 测试动画', original_title='Example Story The Movie',
                original_language='ja', genres=[{'id': 16}], runtime=95,
                release_date='2024-04-01')


def cached(now=1000):
    return dict(schema=2, id=1200, time=now, show=show(), movies=[movie()])


class Item:
    def __init__(self, label):
        self.label, self.properties, self.tag = label, {}, MagicMock()

    def setProperty(self, key, value):
        self.properties[key] = value

    def setLabel(self, value):
        self.label = value

    def getVideoInfoTag(self):
        return self.tag

    def addContextMenuItems(self, _):
        pass

    def setArt(self, _):
        pass


@pytest.fixture
def ui(monkeypatch):
    from lib.clients.tmdb import base
    from lib.utils.kodi import utils
    from lib.utils.general import utils as general
    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: 'skin.bobbi.cinema')
    monkeypatch.setattr(utils, 'make_list_item', lambda label: Item(label))
    monkeypatch.setattr(utils, 'build_url', lambda action, **fields: dict(action=action, **fields))
    monkeypatch.setattr(base, 'build_url', lambda action, **fields: dict(action=action, **fields))
    monkeypatch.setattr(base, 'add_tmdb_movie_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(base, 'add_simkl_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(base, 'add_nuvio_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(base, 'is_trakt_auth', lambda: False)
    monkeypatch.setattr(general, 'set_media_infoTag', lambda *a, **k: None)
    return utils


@pytest.mark.parametrize('change', [
    {'title': '剧场版 另一个故事', 'original_title': 'Unrelated The Movie'},
    {'title': '测试动画 相似题材', 'original_title': 'Example Story Inspired'},
    {'original_language': 'en'}, {'genres': [{'id': 28}]}, {'runtime': 5},
])
def test_similar_or_incompatible_movie_is_not_a_series_installment(change):
    assert not films.related(show(), dict(movie(), **change))


def test_explicit_full_catalog_title_and_movie_marker_prove_only_related_candidate():
    assert films.related(show(), movie())
    assert movie()['id'] != show()['id']


@pytest.mark.parametrize('mutation', ['wrong-show', 'old-schema', 'expired', 'bad-relation', 'duplicate'])
def test_inline_cache_rechecks_relation_and_current_show(mutation):
    value = cached()
    if mutation == 'wrong-show':
        value['show']['id'] = 1201
    elif mutation == 'old-schema':
        value.pop('schema')
    elif mutation == 'expired':
        value['time'] -= 8 * 86400
    elif mutation == 'bad-relation':
        value['movies'][0]['original_language'] = 'en'
    else:
        value['movies'].append(deepcopy(value['movies'][0]))
    assert films.checked_cache(1200, value, now=1000) is None


def test_explicit_discovery_records_evidence_and_reuses_bounded_success_cache():
    calls = []
    def fetch(action, args):
        calls.append(action)
        return (show() if action == 'tv_details' else movie() if action == 'movie_details'
                else dict(results=[movie()], total_results=1))
    value, stale = films.discover(1200, fetch, now=1000)
    assert stale is False and value['schema'] == 2
    assert value['show'] == show() and value['movies'] == [movie()]
    assert calls == ['tv_details', 'search_movie', 'search_movie', 'movie_details']
    assert films.discover(1200, lambda *_: pytest.fail('Fresh cache makes no request'),
                          value, now=1100) == (value, False)


def test_only_successful_related_cache_can_be_used_when_network_fails():
    def offline(*_):
        raise OSError('offline')
    value = cached()
    assert films.discover(1200, offline, value, now=1000 + 2 * 86400) == (value, True)
    with pytest.raises(OSError):
        films.discover(1200, offline, value, now=1000 + 8 * 86400)


def test_inline_movie_and_lazy_entry_do_not_fetch_or_start_playback(ui, monkeypatch):
    from lib.db.cached import cache
    monkeypatch.setattr(films.time, 'time', lambda: 1000)
    monkeypatch.setattr(cache, 'get', lambda key: cached() if key == films.CACHE_PREFIX + '1200' else None)
    monkeypatch.setattr(films, 'discover', lambda *_: pytest.fail('Season page must not search movies'))
    rows = films.directory_entries({'tmdb_id': 1200}, include_cached=True)
    assert len(rows) == 2
    route, item, is_folder = rows[0]
    assert route == dict(action='show_tmdb_item', mode='movies', submode='', id=8900,
                         title='剧场版 测试动画', media_type='movie')
    assert is_folder is False and item.properties['IsPlayable'] == 'false'
    assert item.label == '相关电影 · 剧场版 测试动画'
    assert rows[1][0] == dict(action='bobi_related_movies', ids={'tmdb_id': 1200})
    assert rows[1][2] is True


def test_first_open_keeps_lazy_movie_entry_without_extra_requests(ui, monkeypatch):
    from lib.db.cached import cache
    monkeypatch.setattr(cache, 'get', lambda _: None)
    monkeypatch.setattr(films, 'discover', lambda *_: pytest.fail('No first-open fanout'))
    rows = films.directory_entries({'tmdb_id': 1200}, include_cached=True)
    assert len(rows) == 1 and rows[0][0]['action'] == 'bobi_related_movies'


@pytest.mark.parametrize('skin,animation,expected', [
    ('skin.bobbi.cinema', True, 'seasons'), ('skin.bobbi.cinema', False, 'episodes'),
    ('skin.estuary', True, 'episodes'),
])
def test_single_season_anime_enters_hub_only_in_current_ui(monkeypatch, skin, animation, expected):
    from lib.clients.tmdb.tmdb import TmdbClient
    from lib.clients.tmdb import episode_order
    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: skin)
    monkeypatch.setattr(episode_order, 'show_collapsed_seasons', lambda *a: False)
    seasons, episodes = MagicMock(), MagicMock()
    monkeypatch.setattr(TmdbClient, 'show_seasons_details', seasons)
    monkeypatch.setattr(TmdbClient, 'show_episodes_details', episodes)
    metadata = dict(show(), number_of_seasons=1, genres=[{'id': 16 if animation else 18}])
    TmdbClient._show_tmdb_shows(metadata, 'tv', '测试动画', 1200, 'tv')
    assert bool(seasons.call_count) == (expected == 'seasons')
    assert bool(episodes.call_count) == (expected == 'episodes')


def test_multiseason_browser_keeps_every_season_before_movie_entries(monkeypatch):
    from lib.utils.views import shows
    collected, appended = [], []
    details = SimpleNamespace(name='测试动画', seasons=[3, 1, 2], external_ids={})
    monkeypatch.setattr(shows, 'tmdb_get', lambda *_: details)
    monkeypatch.setattr(shows, 'get_fanart_details', lambda **_: {})
    monkeypatch.setattr(shows, 'execute_thread_pool_collection',
                        lambda values, *_: [(n, 'season:' + str(n), Item(str(n))) for n in values])
    monkeypatch.setattr(shows, 'add_directory_items_batch', collected.extend)
    monkeypatch.setattr(films, 'append_directory_entry',
                        lambda ids, **opts: appended.append((ids, opts)))
    shows.show_season_info({'tmdb_id': 1200}, 'tv', 'tv')
    assert [row[0] for row in collected] == ['season:1', 'season:2', 'season:3']
    assert appended[0][1] == {'include_cached': True}


def test_collapsed_production_seasons_keep_specials_and_independent_films(ui, monkeypatch):
    from lib.clients.tmdb import episode_order, frontend_metadata
    from lib.utils.general import utils as general
    rows = []
    monkeypatch.setattr(episode_order, 'get_order', lambda *a, **k:
                        dict(seasons=[{'season': 1}, {'season': 2}], digest='a' * 64))
    monkeypatch.setattr(frontend_metadata, 'apply', lambda *a, **k: None)
    monkeypatch.setattr(general, 'set_content_type', lambda *_: None)
    monkeypatch.setattr(ui, 'add_directory_items_batch', rows.extend)
    monkeypatch.setattr(ui, 'end_of_directory', lambda: None)
    monkeypatch.setattr(ui, 'apply_section_view', lambda *a, **k: None)
    film = ('film:8900', Item('电影'), False)
    monkeypatch.setattr(films, 'directory_entries', lambda ids, **opts: [film])
    metadata = dict(show(), number_of_seasons=1, seasons=[{'season_number': 0}])
    assert episode_order.show_collapsed_seasons(metadata, '测试动画', {'tmdb_id': 1200}, 'tv', 'tv')
    assert [row[0]['season'] for row in rows[:2]] == [1, 2]
    assert rows[2][0]['action'] == 'show_episodes_details' and rows[2][0]['season'] == 0
    assert rows[3] is film


def test_related_movie_click_uses_movie_identity_and_existing_manual_search(monkeypatch):
    from lib.clients.tmdb.tmdb import TmdbClient
    from lib import search
    entered = []
    monkeypatch.setattr(search, 'run_search_entry', entered.append)
    TmdbClient._show_tmdb_movie(dict(movie(), external_ids={'imdb_id': 'tt12345'}),
                                'movies', '剧场版 测试动画', 8900)
    assert entered[0]['mode'] == 'movies'
    assert json.loads(entered[0]['ids']) == {'tmdb_id': 8900, 'imdb_id': 'tt12345'}
    assert 'tv_data' not in entered[0] and 'auto_play' not in entered[0]


@pytest.mark.parametrize('title', [
    '劇場版 测试动画：新的旅程', '映画 Example Story A New Journey',
    '电影 测试动画：新的旅程', '電影版 测试动画 - 新的旅程',
    'Eiga Example Story: A New Journey', 'Gekijouban Example Story: A New Journey',
    'Example Story: A New Journey The Movie', '测试动画：新的旅程 劇場版',
    'Example Story Movie: A New Journey', 'Example Story The Movie - A New Journey',
    '测试动画 劇場版：新的旅程', '映画 Ｅｘａｍｐｌｅ Ｓｔｏｒｙ：A New Journey',
])
def test_explicit_marker_full_title_boundary_and_subtitle_are_related(title):
    value = dict(movie(), title=title, original_title=title)
    assert films.related(show(), value)
    value.pop('runtime')
    assert films.candidate(show(), value)  # Search hit is not yet final evidence.
    assert not films.related(show(), value)


@pytest.mark.parametrize('title', [
    '映画 Example Storybook: A New Journey', '映画 测试动画别传：新的旅程',
    'Example Storybook Movie: A New Journey', '测试动画别传 劇場版：新的旅程',
    '映画 ExampleStory: A New Journey', 'Example Story: A New Journey Notmovie',
    'Example Story: A New Journey', '测试动画：新的旅程',
    'Example Story Movie: ---',
    'Other Story: Example Story The Movie', '映画 Another Example Story: A New Journey',
])
def test_expanded_relation_rejects_collisions_unmarked_names_and_empty_subtitles(title):
    assert not films.related(show(), dict(movie(), title=title, original_title=title))


@pytest.mark.parametrize('title', ['映画 Example Story： · -', 'Example Story Movie: ---'])
def test_punctuation_alone_is_not_a_subtitle_for_the_expanded_matcher(title):
    assert not films.marked_subtitle(title, films.aliases(show(), 'tv'))


@pytest.mark.parametrize('runtime', [None, 0, 39, True, 95.0, '95'])
def test_subtitle_bearing_film_needs_known_integer_feature_runtime(runtime):
    value = dict(movie(), title='映画 Example Story: A New Journey',
                 original_title='', runtime=runtime)
    assert not films.related(show(), value)


def test_exact_old_film_root_still_works_without_runtime_and_expansion_accepts_40():
    assert films.related(show(), dict(movie(), runtime=None))
    assert films.related(show(), dict(movie(), title='映画 Example Story: A New Journey',
                                     original_title='', runtime=40))


@pytest.mark.parametrize('change', [{'original_language': 'en'}, {'genres': [{'id': 18}]}])
def test_subtitle_expansion_preserves_language_and_animation_checks(change):
    value = dict(movie(), title='映画 Example Story: A New Journey', original_title='')
    value.update(change)
    assert not films.related(show(), value)


def test_movie_marker_and_full_title_cannot_be_combined_across_different_aliases():
    value = dict(movie(), title='Example Story: A New Journey',
                 original_title='映画 Another Story: A New Journey',
                 alternative_titles={'titles': [{'title': 'Unrelated The Movie'}]})
    assert films.candidate(show(), value)
    assert not films.related(show(), value)


def test_public_odd_taxi_metadata_discovers_independent_movie_once():
    # Public TMDb report captured 2026-10-19, fields relevant to this matcher.
    series = dict(id=116727, name='奇巧计程车', original_name='オッドタクシー',
                  original_language='ja', genres=[{'id': 16}, {'id': 35}, {'id': 9648}, {'id': 80}],
                  alternative_titles={'results': [{'title': 'ODDTAXI'}, {'title': 'Odd Taxi'}]})
    hit = dict(id=919609, title='奇巧计程车：扑朔谜林',
               original_title='映画 オッドタクシー イン・ザ・ウッズ',
               original_language='ja', genre_ids=[16, 35, 9648, 80], release_date='2022-04-01')
    feature = dict(hit, runtime=128, alternative_titles={'titles': [
        {'title': 'Eiga ODDTAXI: In the Woods'}, {'title': 'Odd Taxi: In the Woods'},
        {'title': '映画 ODDTAXI イン・ザ・ウッズ'}, {'title': 'ODDTAXI Movie: In the Woods'}]})
    calls = []
    def fetch(action, args):
        calls.append((action, args))
        return (series if action == 'tv_details' else feature if action == 'movie_details'
                else dict(results=[hit], total_results=1))
    value, stale = films.discover(116727, fetch, now=1000)
    assert not stale and [item['id'] for item in value['movies']] == [919609]
    assert [args['query'] for action, args in calls if action == 'search_movie'] == ['オッドタクシー', '奇巧计程车']
    assert [args['id'] for action, args in calls if action == 'movie_details'] == [919609]
    # The original-language alias alone must shortlist before alternatives are fetched.
    assert films.candidate(series, dict(hit, title=''))


def test_expanded_names_do_not_increase_search_or_detail_budget():
    values = [dict(movie(), id=9000 + n, title='映画 Example Story: Journey ' + str(n),
                   original_title='') for n in range(10)]
    calls = []
    def fetch(action, args):
        calls.append(action)
        return (show() if action == 'tv_details' else values[args['id'] - 9000]
                if action == 'movie_details' else dict(results=values, total_results=10))
    value, _ = films.discover(1200, fetch, now=1000)
    assert calls.count('search_movie') == 2 and calls.count('movie_details') == 5
    assert [item['id'] for item in value['movies']] == list(range(9000, 9005))


def test_old_empty_relation_cache_is_not_reused_after_matching_policy_change(ui, monkeypatch):
    from lib.db.cached import cache
    requested = []
    old_empty = dict(cached(), movies=[])
    def get(key):
        requested.append(key)
        return old_empty if key == 'bobi_related_movies_v2:1200' else None
    monkeypatch.setattr(cache, 'get', get)
    rows = films.directory_entries({'tmdb_id': 1200}, include_cached=True)
    assert len(rows) == 1
    assert requested == ['bobi_related_movies_v3:1200']
