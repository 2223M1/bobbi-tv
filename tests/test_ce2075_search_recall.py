"""Real viewing counterexamples: discovery recall, stable caches and no false EOF."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from test_provider_streaming import chain, client, search, Response, rss
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.provider_cache import ProviderResultCache
from bobbi_core.search_completion import SearchCompletion, SearchResults

LIB = ROOT / 'addons/plugin.video.bobbi/lib'
ALIASES = ['学生会也有洞！', '學生會也有洞！', '生徒会にも穴はある!',
           'Seitokai ni mo Ana wa Aru!', 'Seitokai ni mo Ana wa Aru',
           'Even the Student Council Has Its Holes!', '脑洞学生会']
TITLES = [
    '[搬運][ANi] Seitokai ni mo Ana wa Aru / 學生會也有洞！ - 04 [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4]',
    '[ANi] Seitokai ni mo Ana wa Aru / 学生会也有洞！ - 04 [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4]',
    '[黒ネズミたち] 学生会也有洞！ / Seitokai ni mo Ana wa Aru! - 04 (Baha 1920x1080 AVC AAC MP4)',
    '[黒ネズミたち] 学生会也有洞！ / Seitokai ni mo Ana wa Aru! - 04 (B-Global 1920x1080 HEVC AAC MKV)',
    '[TV版&无修版] 学生会也有洞！ - EP04 [简／繁] (1080p H.264 AAC SRTx2) {生徒会にも穴はある！ | 脑洞学生会 | Even the Student Council Has Its Holes!}',
]


@pytest.fixture
def gate(chain):
    chain.stub('lib.utils.kodi.utils', get_setting=lambda key, default=None: default,
               notification=lambda *a: None, translation=str, kodilog=lambda *a, **kw: None)
    chain.package('lib.cinema', LIB/'cinema')
    chain.stub('lib.cinema._shared')
    for name in ('utils.parsers.title_parser', 'utils.parsers.pack_parser',
                 'utils.general.source_resolution', 'utils.general.anime_identity', 'utils.general.processors'):
        chain.load('lib.'+name, LIB.joinpath(*name.split('.')).with_suffix('.py'))
    tree = ast.parse((LIB/'search.py').read_text(encoding='utf-8'))
    names = {'_cinema_requires_catalog_admission', '_cinema_filter_catalog_candidates'}
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = dict(Indexer=SimpleNamespace(JACKETT='Jackett'), kodilog=lambda *a, **kw: None,
                 xbmc=SimpleNamespace(LOGINFO=1))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'search.py', 'exec'), scope)
    return lambda title: scope['_cinema_filter_catalog_candidates'](
        [SimpleNamespace(title=title, indexer='Jackett')], ALIASES, 'tv', 1, 4, anime=True)


@pytest.mark.parametrize('title', TITLES)
def test_real_chinese_candidates_survive_full_gate(gate, title):
    assert gate(title)


@pytest.mark.parametrize('title', [
    TITLES[1].replace(' - 04 ', ' - 05 '),
    TITLES[1].replace(' - 04 ', ' S02E04 '),
    '[Group] Other Show - 04 [1080p][CHS]',
    TITLES[1].replace(' - 04 ', ' OVA - 04 '),
    TITLES[1].replace(' - 04 ', ' - 03-04 '),
    TITLES[1].replace(' - 04 ', ' - 04.5 '),
])
def test_conflicting_work_episode_special_stays_out(gate, title):
    assert not gate(title)


def backend():
    values = {}
    return SimpleNamespace(values=values, get=values.get,
        set=lambda key, value, ttl: values.__setitem__(key, value))


def row(number):
    return SimpleNamespace(title='candidate', infoHash=format(number, '040x'))


def test_partial_snapshot_reopens_without_claiming_complete_or_repeating_network():
    storage = backend()
    cache = ProviderResultCache(storage, 'episode4', hours=24)
    receipt = SearchCompletion(96, succeeded=8, failed=4, skipped=82, timed_out=2)
    cache.put('jackett', 'search', SearchResults([row(1)], receipt))
    result = cache.get('jackett', 'search')
    assert isinstance(result, SearchResults) and result == [row(1)]
    assert result.completion == receipt and not result.completion.complete
    assert ProviderResultCache(storage, 'episode5', hours=24).get('jackett', 'search') is None
    assert ProviderResultCache(storage, 'episode4', hours=24, refresh=True).get('jackett', 'search') is None


def test_lower_coverage_refresh_keeps_old_candidates_and_deduplicates_exact_hash():
    cache = ProviderResultCache(backend(), 'scope', hours=24)
    good = SearchResults([row(1), row(2)], SearchCompletion(4, succeeded=4))
    cache.put('jackett', 'search', good)
    cache.put('jackett', 'search', SearchResults([row(2), row(3)], SearchCompletion(4, succeeded=1, timed_out=3)))
    result = cache.get('jackett', 'search')
    assert {r.infoHash for r in result} == {r.infoHash for r in [row(1), row(2), row(3)]}
    assert len(result) == 3 and not result.completion.complete


def test_query_cache_retries_only_failed_http_requests(chain):
    storage = backend()
    cache = ProviderResultCache(storage, 'queries', hours=1/6)
    calls = []
    bodies = {'http://fixture.invalid/ok': Response(rss('First')),
              'http://fixture.invalid/fail': Response(b'', 400)}
    def get(url, **kw):
        calls.append(url)
        return bodies[url]
    value = client(chain, bodies, get)
    first = search(value, query_cache=cache)
    assert len(first) == 1 and not first.completion.complete
    calls.clear()
    second = search(value, query_cache=cache)
    assert calls == ['http://fixture.invalid/fail']
    assert [r.title for r in second] == ['First'] and not second.completion.complete


def test_dedup_uses_swarm_and_file_not_title(gate):
    import base64
    from lib.utils.general.processors import PreProcessBuilder
    first = row(1)
    equivalent = SimpleNamespace(title='translated title', infoHash=base64.b32encode(bytes.fromhex(first.infoHash)).decode())
    other_encode = row(2)
    same_title_a = SimpleNamespace(title='same title', url='https://fixture.invalid/a')
    same_title_b = SimpleNamespace(title='same title', url='https://fixture.invalid/b')
    other_file = SimpleNamespace(**vars(first), stremioMetadata={'fileIdx': 2})
    rows = PreProcessBuilder([first, equivalent, other_encode, same_title_a, same_title_b, other_file]).remove_duplicates().get_results()
    assert rows == [first, other_encode, same_title_a, same_title_b, other_file]


def test_partial_expiry_and_empty_failure_do_not_replace_good_snapshot(monkeypatch):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    cache = module.ProviderResultCache(backend(), 'scope', hours=24)
    cache.put('jackett', 'search', SearchResults([row(1)], SearchCompletion(2, succeeded=1, skipped=1)))
    clock[0] += 1799
    assert cache.get('jackett', 'search').completion.snapshot_age == 1799
    clock[0] += 2
    assert cache.get('jackett', 'search') is None
    cache.put('jackett', 'search', [row(2)])
    cache.put('jackett', 'search', SearchResults([], SearchCompletion(1, timed_out=1)))
    assert cache.get('jackett', 'search') == [row(2)]


def test_complete_refresh_supersedes_partial_snapshot():
    cache = ProviderResultCache(backend(), 'scope', hours=24)
    cache.put('jackett', 'search', SearchResults([row(1)], SearchCompletion(2, succeeded=1, skipped=1)))
    cache.put('jackett', 'search', SearchResults([row(2)], SearchCompletion(2, succeeded=2)))
    result = cache.get('jackett', 'search')
    assert result == [row(2)] and result.completion.complete


def test_partial_refresh_does_not_renew_old_results_forever(monkeypatch):
    import bobbi_core.provider_cache as module
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', lambda: clock[0])
    cache = module.ProviderResultCache(backend(), 'scope', hours=24)
    receipt = SearchCompletion(2, succeeded=1, skipped=1)
    cache.put('jackett', 'search', SearchResults([row(1)], receipt))
    clock[0] += 1790
    cache.put('jackett', 'search', SearchResults([row(2)], receipt))
    result = cache.get('jackett', 'search')
    assert result == [row(1), row(2)] and result.completion.snapshot_age == 1790
    clock[0] += 11
    assert cache.get('jackett', 'search') is None


@pytest.mark.parametrize('cancelled', [False, True])
def test_deadline_keeps_only_previously_accepted_streamed_snapshot(tmp_path, cancelled):
    from threading import Event
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_core.source_list_session import SourceListSession
    from bobbi_core.search_admission import try_acquire
    cache = ProviderResultCache(backend(), 'deadline', hours=24)
    session = SourceListSession({}, lambda rows: rows)
    entered, release = Event(), Event()
    def produce(publish):
        assert publish(SearchResults([row(1)], SearchCompletion(1, succeeded=1)))
        entered.set()
        assert release.wait(3)
        # This late, never-shown row must not be promoted into the cache.
        return SearchResults([row(1), row(2)], SearchCompletion(2, succeeded=1, timed_out=1))
    def setup(manager):
        manager.submit_task('search', 'jackett', produce, _progressive=True)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, budget=.15,
        result_cache=cache, admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start()
        assert entered.wait(2)
        if cancelled:
            pump.cancel()
        pump.thread.join(2)
        assert not pump.thread.is_alive()
        release.set()
        for future in pump._futures:
            future.result(2)
        result = cache.get('jackett', 'search')
        if cancelled:
            assert result is None
        else:
            assert result == [row(1)] and not result.completion.complete
            assert len(session.entries) == 1
    finally:
        release.set()
        pump.cancel()
