"""Coordinator-level cache recovery, not just isolated cache get/set tests."""
from threading import Event

import pytest

from test_ce2062_source_retry import finish, source
from test_ce2075_search_recall import backend
from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.provider_cache import ProviderResultCache
from bobbi_core.search_admission import try_acquire
from bobbi_core.search_completion import SearchCompletion, SearchResults
from bobbi_core.source_list_session import SourceListSession


def test_partial_seed_is_visible_while_only_failed_query_is_retried(tmp_path):
    storage = backend()
    cache = ProviderResultCache(storage, 'provider', hours=.5)
    queries = ProviderResultCache(storage, 'queries', hours=.5)
    a, b = source('a'), source('b')
    queries.put('query', 'Q1', [a])
    cache.put('jackett', 'search', SearchResults([a], SearchCompletion(2, succeeded=1, failed=1)))
    session = SourceListSession({}, lambda rows: rows)
    entered, release = Event(), Event()
    calls = []

    def provider(publish):
        entered.set()
        assert release.wait(2)
        rows = []
        for key, value in [('Q1', a), ('Q2', b)]:
            cached = queries.get('query', key)
            if cached is None:
                calls.append(key)
                cached = [value]
                queries.put('query', key, cached)
            rows.extend(cached)
        return SearchResults(rows, SearchCompletion(2, succeeded=2))

    def setup(manager):
        manager.submit_task('search', 'jackett', provider, _progressive=True)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, result_cache=cache,
                             admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start()
        assert entered.wait(1), 'Partial cache must not suppress missing-query work'
        seed = session.snapshot()
        assert [row for _, row in seed['entries']] == [a]
        assert seed['providers']['jackett:1']['state'] == 'RUNNING'
        session.focus(session.key(a), 0)
        release.set()
        finish(pump)
        assert calls == ['Q2']
        assert [row for _, row in session.snapshot()['entries']] == [a, b]
        assert session.focus_key == session.key(a)
        assert cache.get('jackett', 'search').completion.complete
    finally:
        release.set()
        pump.cancel()


@pytest.mark.parametrize('cancel', [False, True])
def test_cached_seed_is_not_new_work_and_cannot_renew_expiry(tmp_path, monkeypatch, cancel):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    storage = backend()
    cache = ProviderResultCache(storage, 'seed', hours=.5)
    cache.put('jackett', 'search', SearchResults([source('a')], SearchCompletion(2, succeeded=1, failed=1)))
    original = dict(storage.values)
    clock[0] += 100
    entered, release = Event(), Event()
    session = SourceListSession({}, lambda rows: rows)
    def provider(publish):
        entered.set()
        release.wait(2)
        raise TimeoutError()
    def setup(manager):
        manager.submit_task('search', 'jackett', provider, _progressive=True)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, budget=.15,
                             result_cache=cache, admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start()
        assert entered.wait(1)
        if cancel:
            session.cancel()
            pump.cancel()
        finish(pump)
        release.set()
        for future in pump._futures:
            future.result(2)
        assert storage.values == original
        assert session.status()['providers']['jackett:1']['completion']['snapshot_age'] == 100
    finally:
        release.set()
        pump.cancel()


def test_forced_refresh_bypasses_old_values_but_retry_reads_this_round_success():
    cache = ProviderResultCache(backend(), 'refresh', hours=.5, refresh=True)
    cache.put('query', 'Q1', [source('a')])
    assert cache.get('query', 'Q1') is None
    cache.resume_cached_queries()
    assert cache.get('query', 'Q1') == [source('a')]


@pytest.mark.parametrize('partial', [False, True])
def test_nonempty_query_lives_thirty_minutes_without_failed_refresh_extension(monkeypatch, partial):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    cache = ProviderResultCache(backend(), 'ttl', hours=.5)
    receipt = SearchCompletion(2, succeeded=1, failed=1) if partial else SearchCompletion(1, succeeded=1)
    cache.put('provider', 'search', SearchResults([source('a')], receipt))
    clock[0] += 1799
    assert cache.get('provider', 'search')
    cache.put('provider', 'search', SearchResults([], SearchCompletion(1, failed=1)))
    clock[0] += 2
    assert cache.get('provider', 'search') is None


def test_successful_empty_query_lives_only_thirty_seconds(monkeypatch):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    cache = ProviderResultCache(backend(), 'empty', hours=.5)
    cache.put('query', 'Q', [])
    clock[0] += 29
    assert cache.get('query', 'Q') == []
    clock[0] += 2
    assert cache.get('query', 'Q') is None


def test_status_ticks_do_not_rerank_or_copy_cards_but_new_data_does():
    calls = []
    def rank(rows):
        calls.append(len(rows))
        return rows
    session = SourceListSession({}, rank)
    session.publish(session.epoch, 'provider', [source('a')], state='RUNNING')
    first = session.snapshot()
    first['entries'][0][1].title = 'caller mutation'
    session.publish(session.epoch, 'provider', state='RUNNING')
    update = session.snapshot(after_content_revision=first['content_revision'])
    assert update['entries'] is None
    assert calls == [1]
    assert session.snapshot()['entries'][0][1].title == 'a'
    assert calls == [1]
    session.publish(session.epoch, 'provider', [source('b')], state='COMPLETE')
    update = session.snapshot(after_content_revision=first['content_revision'])
    assert len(update['entries']) == 2 and calls == [1, 2]
    session.set_metadata({'title': 'a'})
    session.snapshot()
    assert calls == [1, 2, 2]


def test_rejected_share_observation_does_not_mutate_projection():
    a = source('a')
    a.verifiedShareFile = True
    a.url, a.guid, a.size, a.indexer, a.type = 'am6bjuku://a', 'juku:a', 100, 'catalog', 'Direct'
    session = SourceListSession({}, lambda rows: rows)
    session.publish(session.epoch, 'catalog', [a])
    before = session.snapshot()
    selected = session.capture(session.epoch, session.key(a))
    assert not session.invalidate_share(session.epoch, selected, 'share_revoked', state={})
    session.reopen()
    after = session.snapshot()
    assert after['content_revision'] == before['content_revision']
    assert after['entries'][0][1].verifiedShareFile is True
    assert session.invalidate_share(session.epoch, selected, '') is False  # No active capture.
    selected = session.capture(session.epoch, session.key(a))
    assert session.invalidate_share(session.epoch, selected, '')
    session.reopen()
    assert session.snapshot()['entries'][0][1].verifiedShareFile is False


def test_complete_snapshot_keeps_oldest_query_expiry(monkeypatch):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    cache = ProviderResultCache(backend(), 'complete', hours=.5)
    cache.put('provider', 'search', SearchResults([source('a'), source('b')],
        SearchCompletion(2, succeeded=2, snapshot_age=1000)))
    clock[0] += 799
    assert cache.get('provider', 'search')
    clock[0] += 2
    assert cache.get('provider', 'search') is None


def test_complete_seed_does_not_hide_expired_empty_queries(tmp_path, monkeypatch):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    storage = backend()
    provider_cache = ProviderResultCache(storage, 'provider', hours=.5)
    query_cache = ProviderResultCache(storage, 'query', hours=.5)
    a = source('a')
    query_cache.put('query', 'positive', [a])
    query_cache.put('query', 'empty', [])
    provider_cache.put('provider', 'search', SearchResults([a], SearchCompletion(2, succeeded=2)))
    clock[0] += 31
    calls = []
    def fetch(publish):
        result = []
        for key in ('positive', 'empty'):
            rows = query_cache.get('query', key)
            if rows is None:
                calls.append(key)
                rows = [source('b')]
            result.extend(rows)
        return SearchResults(result, SearchCompletion(2, succeeded=2))
    def setup(manager):
        manager.submit_task('search', 'provider', fetch, _progressive=True, _cache_seed_only=True)
    session = SourceListSession({}, lambda rows: rows)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, result_cache=provider_cache,
        admission=lambda: try_acquire(tmp_path/'lease'))
    pump.start()
    finish(pump)
    assert calls == ['empty']
    assert len(session.entries) == 2
    pump.cancel()


def test_hash_bucket_collision_does_not_repeat_successful_sibling_queries():
    cache = ProviderResultCache(backend(), 'same-title-queries', hours=.5)
    first, second = 'https://fixture.invalid?q=0', 'https://fixture.invalid?q=16'
    assert cache._identity('jackett-query', first)[0] == cache._identity('jackett-query', second)[0]
    cache.put('jackett-query', first, [source('a')])
    cache.put('jackett-query', second, [source('b')])
    assert cache.get('jackett-query', first) == [source('a')]
    assert cache.get('jackett-query', second) == [source('b')]


def test_cache_lanes_stay_bounded_and_do_not_mix_scopes():
    storage = backend()
    for index in range(1200):
        ProviderResultCache(storage, str(index), hours=.5).put('query', 'Q', [source('a')])
    assert len(storage.values) <= ProviderResultCache.SLOTS * 4 * 2
    assert ProviderResultCache(storage, 'new-scope', hours=.5).get('query', 'Q') is None


def test_stream_fallback_age_includes_the_time_spent_filtering(tmp_path, monkeypatch):
    import bobbi_core.progressive_search as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    cache = ProviderResultCache(backend(), 'slow-transform', hours=.5)
    session = SourceListSession({}, lambda rows: rows)
    def transform(rows):
        clock[0] += 2
        return rows
    def provider(publish):
        publish(SearchResults([source('a')], SearchCompletion(1, succeeded=1, snapshot_age=10)))
        raise TimeoutError()
    def setup(manager):
        manager.submit_task('search', 'provider', provider, _progressive=True)
    pump = ProgressiveSearch(session, setup, transform, result_cache=cache,
        admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start()
        finish(pump)
        assert cache.get('provider', 'search').completion.snapshot_age >= 12
    finally:
        pump.cancel()
def test_failure_diagnostic_retains_import_location_not_exception_text(caplog):
    import logging
    from bobbi_core.progressive_search import _failure_diagnostic
    try:
        raise ImportError('secret-signed-url-and-cookie', name='lib.example')
    except ImportError as error:
        with caplog.at_level(logging.WARNING):
            _failure_diagnostic(error, 'fixed-invocation', 3)
    assert 'lib.example' in caplog.text
    assert 'test_failure_diagnostic_retains_import_location_not_exception_text' in caplog.text
    assert 'secret-signed-url-and-cookie' not in caplog.text
