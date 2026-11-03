"""Production entry -> plan -> coordinator/cache -> headless result contracts."""
from threading import Event
from types import SimpleNamespace

import pytest


@pytest.fixture
def shared(monkeypatch, tmp_path):
    from lib import search
    from lib.clients import bobi_library, catalog_providers, mdsub_provider
    from lib.clients.tmdb import episode_order
    from lib.clients.tmdb.utils import utils as tmdb
    from lib.utils.general import cinema_source_rank
    from lib.utils.kodi import settings
    from bobbi_core import runtime_paths, share_failure
    from lib.domain.torrent import TorrentStream
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    storage, calls, processed = {}, [], []
    monkeypatch.setattr(search, 'cache', SimpleNamespace(get=storage.get,
        set=lambda k,v,ttl: storage.__setitem__(k,v)))
    monkeypatch.setattr(runtime_paths, 'ProfilePath', lambda name: tmp_path/name)
    monkeypatch.setattr(share_failure, 'account_scope', lambda **kw: None)
    monkeypatch.setattr(search.xbmc, 'Monitor', lambda: SimpleNamespace(abortRequested=lambda:False))
    monkeypatch.setattr(search, 'get_setting', lambda k, default=None: {
        'jackett_enabled':True, 'indexer':'Jackett', 'indexers_total_results':100,
        'torrent_enable':True, 'thread_number':4}.get(k, default if default is not None else False))
    monkeypatch.setattr(search, '_is_source_enabled', lambda *a, **kw: True)
    monkeypatch.setattr(search, 'reconcile_source_selection', lambda **kw: None)
    monkeypatch.setattr(search, '_build_search_cache_scope', lambda *a: 'shared-fixture')
    monkeypatch.setattr(settings, 'get_cache_expiration', lambda:24)
    monkeypatch.setattr(settings, 'is_cache_enabled', lambda:True)
    monkeypatch.setattr(tmdb, 'get_tmdb_media_details', lambda *a: {})
    monkeypatch.setattr(episode_order, 'release_pair', lambda *a: None)
    monkeypatch.setattr(search, 'build_media_metadata', lambda *a, **kw: {})
    monkeypatch.setattr(search, '_cinema_catalog_aliases', lambda *a, **kw: ['Fixture'])
    monkeypatch.setattr(search, '_build_title_fallback_queries', lambda *a, **kw: ['Fixture'])
    monkeypatch.setattr(search, '_infer_tmdb_year', lambda *a, **kw: 2020)
    monkeypatch.setattr(search, '_movie_catalog_context', lambda *a: {})
    monkeypatch.setattr(search, '_tv_completed_context', lambda *a: {})
    monkeypatch.setattr(search, '_filter_movie_year_candidates', lambda rows,*a: rows)
    monkeypatch.setattr(search, '_filter_tv_completed_candidates', lambda rows,*a: rows)
    monkeypatch.setattr(search, '_cinema_filter_catalog_candidates', lambda rows,*a,**kw: rows)
    monkeypatch.setattr(search, '_prepare_stremio_results', lambda rows,*a,**kw: rows)
    monkeypatch.setattr(cinema_source_rank, 'rank_sources', lambda rows,*a: rows)
    monkeypatch.setattr(bobi_library, 'load_index', lambda: {})
    monkeypatch.setattr(bobi_library, 'find_sources', lambda *a: [])
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a: [])
    monkeypatch.setattr(catalog_providers, 'submit_catalogs', lambda *a,**kw: None)
    monkeypatch.setattr(catalog_providers, 'provider_for', lambda row: None)
    def transform(rows, *a, **kw):
        assert kw['suppress_debrid_dialog'] and kw['suppress_busy_dialog']
        processed.extend(row.infoHash for row in rows)
        return rows
    monkeypatch.setattr(search, '_process_search_results', transform)
    failed = [True]
    def provider(indexer, *a, **kw):
        assert kw['show_dialog'] is False
        assert kw['deadline'] and kw['cancelled']
        cache = kw['query_cache']
        rows, errors = [], 0
        for key, token in [('Q1','a'),('Q2','b')]:
            hit = cache.get('query', key)
            if hit is None:
                calls.append(key)
                if key=='Q2' and failed[0]:
                    errors += 1
                    continue
                hit = [TorrentStream(title='Fixture S01E01', infoHash=token*40, indexer='Jackett')]
                cache.put('query', key, hit)
            rows.extend(hit)
        return SearchResults(rows, SearchCompletion(2, succeeded=2-errors, failed=errors))
    monkeypatch.setattr(search, '_perform_search', provider)
    def forbidden(*a, **kw):
        pytest.fail('Headless search must not manipulate a window or busy dialog')
    monkeypatch.setattr(search, 'close_busy_dialog', forbidden)
    monkeypatch.setattr(search, 'SearchStatusWindow', forbidden)
    return SimpleNamespace(search=search, calls=calls, failed=failed, processed=processed)


def invoke(shared, **kw):
    return shared.search.search_client('Fixture', {'tmdb_id':123}, 'tv', 'tv', False,
        1, 1, show_dialog=False, **kw)


def test_headless_and_picker_share_plan_success_cache_and_partial_receipt(shared):
    first = invoke(shared)
    assert len(first)==1 and not first.completion.complete
    shared.failed[0] = False
    second = invoke(shared)
    assert len(second)==2 and second.completion.complete
    assert shared.calls == ['Q1','Q2','Q2']
    third = invoke(shared)
    assert len(third)==2 and third.completion.complete
    assert shared.calls == ['Q1','Q2','Q2']


def test_headless_cancel_raises_and_never_returns_late_rows(shared):
    cancel = Event(); cancel.set()
    with pytest.raises(shared.search.SearchCancelled):
        invoke(shared, cancelled=cancel.is_set)


def test_empty_partial_receipt_survives_cancel_exception(shared):
    from bobbi_core.search_completion import SearchResults, SearchCompletion
    rows=SearchResults([], SearchCompletion(1, failed=1))
    assert shared.search.SearchCancelled(rows).results is rows


def test_autoscrape_catalogue_candidate_never_becomes_playback_address(monkeypatch):
    from lib import search
    from lib.utils.player import utils
    from lib.clients import catalog_providers
    from lib.domain.torrent import TorrentStream
    from bobbi_core.search_completion import SearchResults, SearchCompletion
    source=TorrentStream(title='Fixture S01E02 1080p', type='Direct', indexer='Library',
        guid='qqdocs:A1:123', url='am6bqqdocs://A1/123')
    rows=SearchResults([source], SearchCompletion(1,succeeded=1))
    calls, saved = [], []
    def search_candidates(**kw):
        calls.append(kw)
        return rows
    monkeypatch.setattr(search, 'search_client', search_candidates)
    monkeypatch.setattr(utils, 'get_setting', lambda k,default=None: {
        'autoscrape_next_episode':True,'auto_play':True,'auto_play_quality':'1080p'}.get(k,default))
    monkeypatch.setattr(utils, 'cache_autoscrape_result', lambda key,data,**kw:saved.append((key,data)))
    monkeypatch.setattr(catalog_providers,'provider_for',lambda row:'qqdocs')
    monkeypatch.setattr(utils,'resolve_playback_url',lambda **kw:pytest.fail('Discovery locator cannot be resolved by legacy URL path'))
    utils.autoscrape_next_episode({'ids':{'tmdb_id':123},'title':'Fixture','mode':'tv','media_type':'tv'},
                                {'season':1,'episode':2})
    assert calls[0]['rescrape'] is False and calls[0]['show_dialog'] is False
    assert len(saved)==1 and saved[0][0].startswith('as_results:') and saved[0][1] is rows
