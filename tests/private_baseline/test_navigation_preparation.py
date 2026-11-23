"""Selected-work preparation, not speculative playback or home-card fanout."""
from unittest.mock import MagicMock

import pytest

from lib.clients.tmdb import related_movies as films
from lib.clients.tmdb.tmdb import TmdbClient
from lib.utils.views import shows


def test_known_tmdb_identity_and_loaded_details_do_not_refetch(monkeypatch):
    from lib.api.tmdbv3api.as_obj import AsObj
    details = AsObj(dict(id=42, name='Example', seasons=[], external_ids={'imdb_id': 'tt42'}))
    monkeypatch.setattr(shows, 'tmdb_get', lambda *a: pytest.fail('duplicate metadata IO'))
    monkeypatch.setattr(shows, 'get_fanart_details', lambda **k: {})
    monkeypatch.setattr(shows, 'add_directory_items_batch', lambda *a: None)
    monkeypatch.setattr(films, 'append_directory_entry', lambda *a, **k: None)
    assert shows.show_season_info({'tmdb_id': 42, 'imdb_id': 'tt42'}, 'tv', 'tv', details=details) is not False


def test_single_season_animation_without_movies_skips_season_hub(monkeypatch):
    from lib.clients.tmdb import navigation
    import xbmc
    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: 'skin.bobbi.cinema')
    metadata = dict(id=42, name='Example', genres=[{'id': 16}], number_of_seasons=1,
                    seasons=[{'season_number': 1}], external_ids={})
    monkeypatch.setattr(navigation, 'prepare', lambda *a: dict(order=None,
        movies=dict(schema=3, id=42, show=metadata, movies=[], complete=True), pages={}))
    episodes, seasons = MagicMock(), MagicMock()
    monkeypatch.setattr(TmdbClient, 'show_episodes_details', episodes)
    monkeypatch.setattr(TmdbClient, 'show_seasons_details', seasons)
    TmdbClient._show_tmdb_shows(metadata, 'tv', 'Example', 42, 'tv')
    assert episodes.call_count == 1 and not seasons.called
    assert episodes.call_args.kwargs['season'] == 1


def test_discovery_does_not_silently_drop_sixth_film_or_second_page():
    show = dict(id=42, name='Example', original_name='Example', original_language='ja', genres=[{'id': 16}])
    movies = [dict(id=n, title='Example The Movie', original_language='ja',
                   genres=[{'id': 16}], runtime=90, release_date='2020-01-01') for n in range(100, 126)]
    calls = []
    def fetch(action, args):
        calls.append((action, args))
        if action == 'tv_details':
            return show
        if action == 'search_movie':
            return dict(results=movies[(args['page']-1)*20:args['page']*20], total_results=26, total_pages=2, page=args['page'])
        return movies[args-100]
    value, stale = films.discover(42, fetch, now=1000, show=show)
    assert not stale and value['complete']
    assert [row['id'] for row in value['movies']] == list(range(100, 126))
    assert not any(action == 'tv_details' for action, _ in calls)
    assert [args['page'] for action, args in calls if action == 'search_movie'] == [1, 2]


def test_route_string_and_idle_numeric_ids_join_one_detail_cache():
    from lib.clients.tmdb import detail_cache
    from types import SimpleNamespace
    saved, calls = {}, []
    cache = SimpleNamespace(get=lambda key: saved.get(key),
        set=lambda key, data, expires: saved.__setitem__(key, data))
    def fetch(params):
        calls.append(params)
        return dict(id=42, name='Example', seasons=[])
    first = detail_cache.get('tv_details', '42', 'zh-CN', cache, fetch)
    assert detail_cache.get('tv_details', 42, 'zh-CN', cache, fetch) == first
    assert len(calls) == 1


def test_alias_upgrade_retains_old_movie_on_failure_then_fetches_once():
    from datetime import timedelta
    from types import SimpleNamespace
    from lib.clients.tmdb import movie_details_guard as guard
    original = dict(id=42, title='Example', release_date='2020-01-01')
    saved, calls = {'canonical': original}, []
    cache = SimpleNamespace(get=lambda key: saved.get(key),
        set=lambda key, data, expires: saved.__setitem__(key, data))
    def fetch(params):
        calls.append(params)
        return dict(original, alternative_titles={'titles': []})
    result = guard.get(42, 'canonical', 'legacy', cache, fetch, timedelta(hours=24), require_aliases=True)
    assert result['alternative_titles'] == {'titles': []} and original == saved.get('legacy', original)
    assert guard.get(42, 'canonical', 'legacy', cache, fetch, timedelta(hours=24), require_aliases=True) == result
    assert len(calls) == 1


def test_failed_season_warm_is_not_marked_ready(monkeypatch):
    from lib.clients.tmdb import navigation, episode_order, related_movies
    from lib.utils.views import shows
    from types import SimpleNamespace
    import xbmc
    monkeypatch.setattr(xbmc, 'Monitor', lambda: SimpleNamespace(abortRequested=lambda: False))
    monkeypatch.setattr(shows, '_fetch_localized_season_pages', lambda *a, **k: {'zh-CN': None, 'zh-TW': None, 'en-US': None})
    monkeypatch.setattr(related_movies, 'load', lambda *a, **k: {'complete': True, 'movies': []})
    monkeypatch.setattr(episode_order, 'get_order', lambda *a, **k: None)
    result = navigation.prepare(dict(number_of_seasons=1, genres=[{'id': 16}], seasons=[{'season_number': 1}]), {'tmdb_id': 42})
    assert result['pages'] == {}
