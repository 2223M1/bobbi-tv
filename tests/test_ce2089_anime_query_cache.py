"""Anime alias supplementation through the real HTTP/fanout/cache chain."""
import json
from threading import Event
import time
from types import SimpleNamespace

import pytest

from test_ce2077_search_completion import garden
from test_provider_streaming import chain, Response, CORE


def page(token, *, complete=True, malformed=False, empty=False):
    return json.dumps(dict(status='OK', pagination=dict(page=1, pageSize=200, complete=complete),
        resources=[] if empty else [dict(type='动画', title='[ANi] Fixture - 01', size=123,
            provider='mikan', magnet='bad' if malformed else 'magnet:?xt=urn:btih:'+token*40)])).encode()


def test_partial_alias_search_reuses_real_response_binding_and_receipt(garden, chain, monkeypatch):
    ProviderResultCache = chain.load('bobbi_core.provider_cache', CORE/'provider_cache.py').ProviderResultCache
    store, calls = {}, []
    cache = ProviderResultCache(SimpleNamespace(get=store.get,
        set=lambda k,v,ttl: store.__setitem__(k,v)), 'anime-query', hours=.5)
    urls = garden.query_plan([('zh-CN', '测试作品'), ('zh-TW', '測試作品')])
    fail = [True]
    def get(session, url, **kw):
        calls.append(url)
        return Response(page('a' if url == urls[0] else 'b'),
                        status=503 if fail[0] and url == urls[1] else 200)
    monkeypatch.setattr(garden.requests.Session, 'get', get)
    monkeypatch.setattr(garden, '_network_proxy', lambda path: None)
    def search():
        return garden.find_sources({'tmdb_id':123}, 'tv',
            [('zh-CN','测试作品'),('zh-TW','測試作品')], time.monotonic()+5, Event(), query_cache=cache,
            slot_factory=lambda key: chain.http._slot(key, directory=chain.slot_root))
    first = search()
    assert len(first) == 1 and first.completion.failed == 1
    assert cache.get('animegarden-query', urls[0]) is not None
    assert cache.get('animegarden-query', urls[1]) is None
    fail[0] = False
    second = search()
    assert len(second) == 2 and second.completion.complete
    assert calls.count(urls[0]) == 1 and calls.count(urls[1]) == 2
    third = search()
    assert len(third) == 2 and third.completion.complete and len(calls) == 3


@pytest.mark.parametrize('kind', ['empty', 'truncated', 'malformed'])
def test_cached_query_keeps_empty_truncation_and_failure_distinct(garden, chain, monkeypatch, kind):
    provider_cache = chain.load('bobbi_core.provider_cache', CORE/'provider_cache.py')
    ProviderResultCache = provider_cache.ProviderResultCache
    clock, store, calls = [1000.], {}, []
    monkeypatch.setattr(provider_cache, 'time', lambda: clock[0])
    cache = ProviderResultCache(SimpleNamespace(get=store.get,
        set=lambda k,v,ttl: store.__setitem__(k,v)), 'anime-query', hours=.5)
    def get(session, url, **kw):
        calls.append(url)
        return Response(page('a', complete=kind!='truncated', malformed=kind=='malformed', empty=kind=='empty'))
    monkeypatch.setattr(garden.requests.Session, 'get', get)
    monkeypatch.setattr(garden, '_network_proxy', lambda path: None)
    def search():
        return garden.find_sources({'tmdb_id':123}, 'tv', [('zh-CN','测试作品')],
            time.monotonic()+5, Event(), query_cache=cache,
            slot_factory=lambda key: chain.http._slot(key, directory=chain.slot_root))
    first = search()
    clock[0] += 20
    second = search()
    assert len(calls) == (2 if kind=='malformed' else 1)
    assert first.completion.complete == second.completion.complete == (kind=='empty')
    if kind == 'truncated':
        assert first.completion.skipped == second.completion.skipped == 1
    clock[0] += 11 if kind=='empty' else 1800
    search()
    assert len(calls) == (3 if kind=='malformed' else 2)


def test_fast_alias_is_cached_before_slow_sibling_exhausts_deadline(garden, chain, monkeypatch):
    ProviderResultCache = chain.load('bobbi_core.provider_cache', CORE/'provider_cache.py').ProviderResultCache
    store, calls, published = {}, [], []
    cache = ProviderResultCache(SimpleNamespace(get=store.get,
        set=lambda k,v,ttl: store.__setitem__(k,v)), 'slow-alias', hours=.5)
    urls = garden.query_plan([('zh-CN','测试作品'),('zh-TW','測試作品')])
    entered, release, finished, expired = Event(), Event(), Event(), Event()
    # Control only the provider's clock. Let both real workers enter and the
    # fast result reach its real cache before expiring this search; CI thread
    # scheduling is not part of the behaviour under test.
    origin = time.monotonic()
    def now():
        return origin + (60 if expired.is_set() else 0)
    monkeypatch.setattr(chain.http, 'time', SimpleNamespace(monotonic=now))
    monkeypatch.setattr(chain.fanout, 'time', SimpleNamespace(monotonic=now))
    monkeypatch.setattr(garden, 'monotonic', now)
    def get(session,url,**kw):
        calls.append(url)
        if url==urls[1] and calls.count(url)==1:
            entered.set()
            assert release.wait(10)
            finished.set()
        return Response(page('a' if url==urls[0] else 'b'))
    monkeypatch.setattr(garden.requests.Session,'get',get)
    monkeypatch.setattr(garden,'_network_proxy',lambda path:None)
    def publish(rows):
        published.extend(rows)
        if not release.is_set():
            assert entered.wait(5)
            assert cache.get('animegarden-query',urls[0]) is not None
            expired.set()
    def search():
        return garden.find_sources({'tmdb_id':123},'tv',[('zh-CN','测试作品'),('zh-TW','測試作品')],
            now()+20,Event(),query_cache=cache,publish=publish,
            slot_factory=lambda key: chain.http._slot(key, directory=chain.slot_root))
    try:
        first=search()
        assert len(first)==1 and not first.completion.complete
        assert published and cache.get('animegarden-query',urls[0])
    finally:
        release.set()
        assert finished.wait(5)
    expired.clear()
    second=search()
    assert len(second)==2 and second.completion.complete
    assert calls.count(urls[0])==1 and calls.count(urls[1])==2
