"""Observed rotating indexer download URLs and scoped anime search routing."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_provider_streaming import chain

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.source_list_session import SourceListSession


def row(**kw):
    return SimpleNamespace(title='Same release', type='Torrent', indexer='Jackett',
        provider='ACG.RIP', infoHash='', guid='https://acg.rip/t/366665.torrent',
        url='http://127.0.0.1:19117/dl/acgrip/?path=encrypted-one', **kw)


def test_rotating_download_address_keeps_one_stable_card_and_focus():
    session = SourceListSession({}, lambda values: values)
    first = row()
    second = row(); second.url = second.url.replace('one', 'two')
    session.publish(session.epoch, 'a', [first], state='RUNNING')
    key = session.key(first)
    session.focus(key, 0)
    session.publish(session.epoch, 'a', [second])
    assert len(session.entries) == 1
    assert session.focus_key == key == session.key(second)
    assert session.capture(session.epoch, key).url == first.url


@pytest.mark.parametrize('field,value', [
    ('provider', 'Other site'), ('guid', 'https://acg.rip/t/366666.torrent'),
    ('stremioMetadata', {'fileIdx': 2}), ('type', 'Catalog'),
])
def test_stable_guid_does_not_merge_other_sites_files_or_transport(field, value):
    session = SourceListSession({}, lambda values: values)
    first = row(); second = row(); setattr(second, field, value)
    second.url += 'different'
    assert session.key(first) != session.key(second)


def test_title_alone_and_unscoped_guid_never_merge():
    session = SourceListSession({}, lambda values: values)
    first = row(); second = row(); second.url += 'different'
    first.provider = second.provider = ''
    assert session.key(first) != session.key(second)


@pytest.mark.parametrize('guid', [None, {}, '', 'https://acg.rip/',
    'https://user:pass@acg.rip/t/1', 'javascript:alert(1)', 'https://[invalid/t/1',
    'https://acg.rip/t/1\n', 'https://acg.rip/t/1' + 'x' * 8192])
def test_malformed_or_unscoped_locator_keeps_transport_identity(guid):
    session = SourceListSession({}, lambda values: values)
    first = row(); second = row()
    first.guid = second.guid = guid
    second.url += 'different'
    assert session.key(first) != session.key(second)


def test_known_hash_and_file_identity_remain_authoritative():
    import base64
    session = SourceListSession({}, lambda values: values)
    first = row(); second = row()
    first.infoHash = '186769f8fc42c027b23a4a5c949702d5cd34effe'
    second.infoHash = base64.b32encode(bytes.fromhex(first.infoHash)).decode()
    second.provider, second.guid = 'Other site', 'https://other.invalid/release/2'
    assert session.key(first) == session.key(second)
    second.infoHash = 'a' * 40
    assert session.key(first) != session.key(second)


def test_partial_cache_merges_rotating_links_without_erasing_other_editions():
    from bobbi_core.provider_cache import ProviderResultCache
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    values = {}
    cache = ProviderResultCache(SimpleNamespace(get=values.get,
        set=lambda key, value, ttl: values.__setitem__(key, value)), 'episode5', hours=24)
    first = row(); again = row(); again.url += 'different'
    other = row(); other.guid = 'https://acg.rip/t/366666.torrent'
    partial = SearchCompletion(2, succeeded=1, failed=1)
    cache.put('jackett', 'search', SearchResults([first], partial))
    cache.put('jackett', 'search', SearchResults([again, other], partial))
    result = cache.get('jackett', 'search')
    assert len(result) == 2 and {r.guid for r in result} == {first.guid, other.guid}
    assert not result.completion.complete


@pytest.fixture
def garden(chain):
    lib = ROOT/'addons/plugin.video.bobbi/lib'
    chain.package('lib.cinema', lib/'cinema'); chain.stub('lib.cinema._shared')
    return chain.load('lib.clients.animegarden_provider', lib/'clients/animegarden_provider.py')


def test_only_explicit_local_anime_proxy_is_accepted(garden, tmp_path):
    path = tmp_path/'network.json'
    path.write_text(json.dumps({'schema': 1, 'animegarden_proxy': 'http://127.0.0.1:17895'}))
    assert garden._network_proxy(path) == 'http://127.0.0.1:17895'
    for value in ('http://remote.invalid:8080', 'http://user:pass@127.0.0.1:80',
                  'http://127.0.0.1:80/path', 'https://127.0.0.1:80', 'http://127.0.0.1:0'):
        path.write_text(json.dumps({'schema': 1, 'animegarden_proxy': value}))
        assert garden._network_proxy(path) is None
    path.write_text('{broken')
    assert garden._network_proxy(path) is None


def test_anime_proxy_failure_falls_back_within_original_deadline(garden, monkeypatch):
    import time
    from threading import Event
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    import lib.clients.jackett_fanout as fanout
    calls = []
    monkeypatch.setattr(garden, '_network_proxy', lambda: 'http://127.0.0.1:17895')
    def fetch(session, urls, **kw):
        calls.append((dict(session.proxies), session.trust_env, kw['deadline']))
        return SearchResults([], SearchCompletion(len(urls), failed=len(urls)))
    monkeypatch.setattr(fanout, 'fetch_independent', fetch)
    garden.find_sources({'tmdb_id': 123}, 'tv', [('zh-CN', '测试作品')], time.monotonic()+30, Event())
    assert len(calls) == 2
    assert calls[0][0] == {'https://api.animes.garden': 'http://127.0.0.1:17895'}
    assert calls[1][0] == {} and calls[0][1] is False and calls[1][1] is False
    assert calls[0][2] == calls[1][2] and calls[0][2] <= time.monotonic()+4


@pytest.mark.parametrize('reason', ['cancel', 'budget_exhausted', 'partial_success'])
def test_proxy_never_replays_success_or_revives_cancelled_budget(garden, monkeypatch, reason):
    from threading import Event
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    import lib.clients.jackett_fanout as fanout
    calls, cancelled = [], Event()
    clock = [100.0]
    monkeypatch.setattr(garden, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(garden, '_network_proxy', lambda: 'http://127.0.0.1:17895')
    def fetch(session, urls, **kw):
        calls.append(1)
        if reason == 'cancel':
            cancelled.set()
        if reason == 'budget_exhausted':
            clock[0] = kw['deadline']
        if reason == 'partial_success':
            content = json.dumps(dict(status='OK', pagination=dict(page=1, pageSize=200, complete=True),
                resources=[dict(type='动画', title='[ANi] Sample - 05', size=123, provider='mikan',
                    magnet='magnet:?xt=urn:btih:' + 'a'*40)])).encode()
            return SearchResults([SimpleNamespace(status_code=200, content=content)],
                                 SearchCompletion(2, succeeded=1, failed=1))
        return SearchResults([], SearchCompletion(2, timed_out=2))
    monkeypatch.setattr(fanout, 'fetch_independent', fetch)
    result = garden.find_sources({'tmdb_id': 123}, 'tv',
        [('zh-CN', '测试作品'), ('zh-TW', '測試作品')], 130, cancelled)
    assert calls == [1] and not result.completion.complete
    assert len(result) == int(reason == 'partial_success')


def test_missing_or_invalid_config_does_not_change_direct_defaults(garden, tmp_path, monkeypatch):
    from threading import Event
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    import lib.clients.jackett_fanout as fanout
    path = tmp_path/'absent.json'
    assert garden._network_proxy(path) is None
    path.write_text('x'*2049)
    assert garden._network_proxy(path) is None
    monkeypatch.setattr(garden, '_network_proxy', lambda: None)
    def fetch(session, urls, **kw):
        assert session.proxies == {} and session.trust_env is True and session.verify is True
        return SearchResults([], SearchCompletion(len(urls), failed=len(urls)))
    monkeypatch.setattr(fanout, 'fetch_independent', fetch)
    garden.find_sources({'tmdb_id': 123}, 'tv', [('zh-CN', '测试作品')], float('inf'), Event())
    import time
    garden.find_sources({'tmdb_id': 123}, 'tv', [('zh-CN', '测试作品')], time.monotonic()+30, Event())
