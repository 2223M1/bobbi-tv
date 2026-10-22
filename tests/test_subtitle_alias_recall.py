"""Cache-bound subtitle aliases; all provider responses are offline fixtures."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'addons/plugin.video.bobbi/lib'
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import subtitle_candidates as subtitles


CONTEXT = dict(mode='series', title='Tengoku Daimakyo', tmdb=208891,
               season=1, episode=1, duration=1500, year=2023, release='')
RAW = '1\n00:00:01,000 --> 00:00:03,000\n中文字幕对白\nEnglish dialogue\n'.encode()
EXACT = dict(id=100001, native_name='天国大魔境 S01E01',
             lang={'langlist': {'langchs': True, 'langdou': True}})


def stub(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def load(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def titles(kind='tv', ident=208891, names=('Tengoku Daimakyo', '天国大魔境', 'Heavenly Delusion')):
    # English is synthetic fixture evidence, not a claim about the captured cache.
    return subtitles.SubtitleTitles(kind, ident, names)


def provider(tmp_path, search, detail=None, body=RAW, on_call=None):
    calls, clock, stopped = [], [0.0], [False]
    def transport(url, deadline, cancelled, limit, **kwargs):
        assert deadline <= 30 and not cancelled()
        parsed = urlsplit(url)
        if parsed.netloc == 'api.assrt.net':
            operation = parsed.path.rsplit('/', 1)[-1]
            params = parse_qs(parsed.query)
            value = params['q'][0] if operation == 'search' else int(params['id'][0])
            call = (operation, value)
            calls.append(call)
            if on_call:
                on_call(call, clock, stopped)
            rows = search(value) if operation == 'search' else (
                detail(value) if detail else [dict(EXACT, id=value, filelist=[
                    dict(f='天国大魔境 S01E01.chs.eng.srt', url='https://assrt.net/offline/sub.srt')])])
            return json.dumps(dict(status=0, sub=dict(subs=rows))).encode()
        assert parsed.netloc == 'assrt.net'
        calls.append(('file', parsed.path))
        if on_call:
            on_call(calls[-1], clock, stopped)
        return body(calls[-1]) if callable(body) else body
    result = subtitles.AssrtCandidates(None, tmp_path / 'state', clock=lambda: clock[0],
        wall=lambda: 1792626200, transport=transport)
    result.token_file = SimpleNamespace(read_text=lambda: '0' * 32)
    return SimpleNamespace(value=result, calls=calls, clock=clock, stopped=stopped,
        run=lambda context: result.candidates(context, 30, lambda: stopped[0], tmp_path / 'texts'))


def test_captured_three_empty_queries_reach_verified_chinese_alias(tmp_path, monkeypatch):
    # Exact CE2042 queries, timestamps and successful empty responses from
    # ce2042-runtime-contract2.json; the Chinese response is an offline fixture.
    p = provider(tmp_path, lambda query: [EXACT] if query == '天国大魔境 S01E01' else [])
    for query, stamp in [('Tengoku Daimakyo S01E01', 1792626110.7277496),
                         ('Tengoku Daimakyo S01', 1792626111.4538445),
                         ('Tengoku Daimakyo', 1792626112.2384458)]:
        import hashlib
        p.value.save('search-' + hashlib.sha256(query.encode()).hexdigest() + '.json',
                     dict(time=stamp, rows=[]))
    stub(monkeypatch, 'lib.clients.tmdb.subtitle_scope', cached_scope=lambda _: None,
         cached_identity=lambda ident: dict(titles=titles(), scope=None))
    fallback = load(monkeypatch, 'alias_fallback', LIB / 'services/subtitle_fallback.py')
    original = p.value.candidates
    p.value.candidates = lambda context, deadline, cancelled: original(
        context, deadline, cancelled, tmp_path / 'texts')
    result = fallback.discover_candidate(CONTEXT, 30, lambda: False, p.value, clock=lambda: 0)
    assert result['origin'] == 'assrt:100001' and result['state'] == 'candidate'
    assert p.calls == [('search', '天国大魔境 S01E01'), ('detail', 100001), ('file', '/offline/sub.srt')]
    assert len(p.value.load('quota.json', [])) == 2


@pytest.mark.parametrize('evidence', [None, {'kind': 'tv', 'tmdb_id': 208891, 'titles': ['天国大魔境']},
    ('tv', 208891, ('天国大魔境',)), 'wrong-id', 'wrong-kind'])
def test_unverified_titles_do_not_widen_query_or_rank(tmp_path, evidence):
    if evidence == 'wrong-id':
        evidence = titles(ident=999)
    elif evidence == 'wrong-kind':
        evidence = titles(kind='movie')
    context = dict(CONTEXT, _subtitle_titles=evidence)
    p = provider(tmp_path, lambda query: [EXACT])
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run(context)
    assert len(p.calls) == 3 and all(call[0] == 'search' for call in p.calls)
    assert subtitles.rank(EXACT, context) is None


def test_evidence_is_bounded_immutable_and_deduplicated():
    from dataclasses import FrozenInstanceError
    evidence = subtitles.titles_from_catalog('tv', dict(tmdb_id=208891,
        aliases=['Tengoku Daimakyo', 'Tengoku.Daimakyo', '天国大魔境', ' -- ',
                 'http://example.test/title', 'Control\x00Title', 'a' * 129]))
    assert evidence.titles == ('Tengoku Daimakyo', '天国大魔境')
    with pytest.raises(FrozenInstanceError):
        evidence.titles = ('Other',)
    huge = subtitles.titles_from_catalog('tv', dict(tmdb_id=208891,
        aliases=['名' * 120 + str(i) for i in range(20)]))
    assert len(huge.titles) <= 16 and sum(len(x.encode()) for x in huge.titles) <= 2048
    for values in [[], ['Only Name'], ('Only Name', 'only.name'), ('Only\nName',)]:
        with pytest.raises(ValueError):
            subtitles.SubtitleTitles('tv', 208891, values)


def test_priority_identity_and_full_title_boundary():
    context = dict(CONTEXT, _subtitle_titles=titles(names=('別名', 'Heavenly Delusion', '天国大魔境')))
    assert subtitles.query_titles(context) == ('Tengoku Daimakyo', '別名', 'Heavenly Delusion')
    assert subtitles.identity(context) == subtitles.identity(CONTEXT)
    for name in ('Heavenly Delusion S01E01', '天国大魔境 S01E01'):
        assert subtitles.rank(dict(EXACT, native_name=name), context) is not None
    for name in ('Heavenly S01E01', 'Heavenly Delusions S01E01', '新天国大魔境 S01E01'):
        assert subtitles.rank(dict(EXACT, native_name=name), context) is None


@pytest.mark.parametrize('name', ['天国大魔境 S02E01', 'Heavenly Delusion S01E02',
    '天国大魔境 S01E01 extended', '天国大魔境 S01E01 forced', '天国大魔境 S01E01 commentary',
    '天国大魔境 S01E01 OVA', '天国大魔境 S01E01 Final Season'])
def test_alias_never_relaxes_episode_edition_or_dialogue_policy(name):
    context = dict(CONTEXT, _subtitle_titles=titles())
    assert subtitles.rank(dict(EXACT, native_name=name), context) is None


@pytest.mark.parametrize('extra', ['OVA', 'Season 2', 'Final Season', '第二季'])
def test_long_catalog_alias_cannot_hide_added_scope(extra):
    context = dict(CONTEXT, _subtitle_titles=titles(names=('天国大魔境', '天国大魔境 ' + extra)))
    assert subtitles.rank(dict(EXACT, native_name='天国大魔境 ' + extra + ' S01E01'), context) is None


@pytest.mark.parametrize('name', ['Special Delivery', '第二季', 'Final Season'])
def test_canonical_words_are_exempt_once(name):
    context = dict(CONTEXT, _subtitle_titles=titles(names=(name,)))
    assert subtitles.rank(dict(EXACT, native_name=name + ' S01E01'), context) is not None
    if name != 'Special Delivery':
        assert subtitles.rank(dict(EXACT, native_name=name + ' ' + name + ' S01E01'), context) is None


def test_mixed_aliases_preserve_conflicts_in_every_metadata_field():
    context = dict(CONTEXT, _subtitle_titles=titles())
    for row in [dict(EXACT, videoname='Heavenly Delusion S02E01'),
                dict(EXACT, filename='Heavenly Delusion S01E02.srt'),
                dict(EXACT, filename='天国大魔境 EP01-02.srt')]:
        assert subtitles.rank(row, context) is None


def test_single_season_proof_is_independent_of_aliases():
    from bobbi_core.subtitle_episode import SingleSeason
    context = dict(CONTEXT, _subtitle_titles=titles())
    row = dict(EXACT, native_name='天国大魔境', filename='天国大魔境 EP01.srt')
    assert subtitles.rank(row, context) is None
    assert subtitles.rank(row, dict(context, _subtitle_single_season=SingleSeason(208891, 13))) is not None
    assert subtitles.rank(row, dict(context, _subtitle_single_season=SingleSeason(999, 13))) is None


def test_movie_alias_title_digits_and_years_share_one_parser():
    from bobbi_core.movie_years import MovieYears
    context = dict(mode='movie', title='太空漫游', tmdb=62, year=1968, release='',
        _movie_years=MovieYears(62, 1968, (1968,)),
        _subtitle_titles=titles('movie', 62, ('2001 A Space Odyssey',)))
    row = dict(native_name='2001 A Space Odyssey 1968', lang={'desc': '中文'})
    assert subtitles.rank(row, context) is not None
    assert subtitles.rank(dict(row, filename='2001 A Space Odyssey 2001.srt'), context) is None
    assert subtitles.rank(dict(row, native_name='2001 A Space Odyssey 1969'), context) is None


def test_all_alias_queries_stop_at_nine_and_keep_original_successful_empty_cache(tmp_path):
    p = provider(tmp_path, lambda query: [])
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert len(p.calls) == 9 and len(set(p.calls)) == 9
    assert len(p.value.load('quota.json', [])) == 9
    assert [call[1] for call in p.calls[:4]] == [
        'Tengoku Daimakyo S01E01', 'Tengoku Daimakyo S01', 'Tengoku Daimakyo', '天国大魔境 S01E01']
    assert len(p.value.search_observations) == 9
    assert all(set(note) == {'query_sha256', 'title_slot', 'source', 'rows', 'admitted'}
               for note in p.value.search_observations)
    p.calls.clear()
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert not p.calls and all(note['source'] == 'cache' for note in p.value.search_observations)


def test_movie_searches_include_accepted_years_but_global_limit_is_nine(tmp_path):
    from bobbi_core.movie_years import MovieYears
    context = dict(mode='movie', title='Movie Example', tmdb=10, year=2001, duration=100,
        _movie_years=MovieYears(10, 2001, (1998, 1999, 2000, 2001)),
        _subtitle_titles=titles('movie', 10, ('电影范例', 'Film Example')))
    p = provider(tmp_path, lambda query: [])
    with pytest.raises(subtitles.LookupStopped):
        p.run(context)
    assert len(p.calls) == 9
    assert [call[1] for call in p.calls[:4]] == [
        'Movie Example 2001', 'Movie Example 1998', 'Movie Example 1999', 'Movie Example 2000']


def test_one_shared_six_detail_budget_and_two_files_per_detail(tmp_path):
    rows = [dict(EXACT, id=100001 + n) for n in range(12)]
    def details(ident):
        return [dict(EXACT, id=ident, filelist=[dict(f='天国大魔境 S01E01.chs.{}.srt'.format(n),
                    url='https://assrt.net/offline/{}-{}.srt'.format(ident, n)) for n in range(5)])]
    p = provider(tmp_path, lambda query: rows, details, body=b'<html>bad</html>')
    with pytest.raises(subtitles.LookupStopped, match='^MATCHED_SUBTITLE_UNAVAILABLE$'):
        p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert sum(kind == 'search' for kind, _ in p.calls) == 1
    assert sum(kind == 'detail' for kind, _ in p.calls) == 6
    assert sum(kind == 'file' for kind, _ in p.calls) == 12
    assert len(p.value.load('quota.json', [])) == 7  # Files are not API quota entries.


def test_repeated_ids_are_detailed_once_and_broken_alias_file_rotates(tmp_path):
    rows = [dict(EXACT, id=100001), dict(EXACT, id='100001'), dict(EXACT, id=100002)]
    count = [0]
    def body(call):
        count[0] += 1
        return b'<html>bad</html>' if count[0] == 1 else RAW
    p = provider(tmp_path, lambda query: rows, body=body)
    result = p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert result['origin'] == 'assrt:100002'
    assert [call for call in p.calls if call[0] == 'detail'] == [('detail', 100001), ('detail', 100002)]


@pytest.mark.parametrize('stop', ['cancel', 'deadline'])
@pytest.mark.parametrize('stage', ['search', 'detail', 'file'])
def test_alias_io_never_outlives_cancel_or_global_deadline(tmp_path, stop, stage):
    def on_call(call, now, cancelled):
        if call[0] == stage:
            if stop == 'cancel':
                cancelled[0] = True
            else:
                now[0] = 30
    p = provider(tmp_path, lambda query: [EXACT], on_call=on_call)
    with pytest.raises(subtitles.LookupStopped, match='^CANCELLED_OR_DEADLINE$'):
        p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert p.calls[-1][0] == stage
    assert not (tmp_path / 'texts').exists()


def test_existing_global_quota_stops_alias_fallback(tmp_path):
    p = provider(tmp_path, lambda query: [])
    p.value.save('quota.json', [1792626190] * 18)
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_RATE_LIMIT$'):
        p.run(dict(CONTEXT, _subtitle_titles=titles()))
    assert len(p.calls) == 2 and len(p.value.load('quota.json', [])) == 20


def test_cached_alias_candidate_is_revalidated_against_current_evidence(tmp_path):
    p = provider(tmp_path, lambda query: [EXACT])
    context = dict(CONTEXT, _subtitle_titles=titles())
    first = p.run(context)
    p.calls.clear()
    p.clock[0] = 24
    assert p.run(context)['file'] == first['file'] and not p.calls
    p.clock[0] = 0
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run(CONTEXT)
    assert all(call[0] == 'search' for call in p.calls)


@pytest.fixture
def cache_reader(monkeypatch):
    calls, records = [], {}
    stub(monkeypatch, 'lib.api.tmdbv3api.as_obj', AsObj=type('AsObj', (), {}))
    stub(monkeypatch, 'lib.api.tmdbv3api.tmdb', TMDb=lambda: SimpleNamespace(language='zh-CN'))
    def get(*, key):
        calls.append(key)
        return records.get(key)
    stub(monkeypatch, 'lib.db.cached', cache=SimpleNamespace(get=get))
    load(monkeypatch, 'lib.clients.tmdb.detail_cache', LIB / 'clients/tmdb/detail_cache.py')
    module = load(monkeypatch, 'lib.clients.tmdb.subtitle_scope', LIB / 'clients/tmdb/subtitle_scope.py')
    monkeypatch.setattr(module.time, 'time', lambda: 1000000.0)
    def save(identifier, *, fetched=999999, detail=None, requested=False):
        records['am6b_details283|' + json.dumps(['tv_details', {'id': identifier}, 'zh-CN'], sort_keys=True)] = dict(
            fetched=fetched, data=detail or tv_detail(), tv_aliases_requested=requested)
    return SimpleNamespace(module=module, calls=calls, records=records, save=save)


def tv_detail(**changes):
    return dict(dict(id=208891, name='Tengoku Daimakyo', original_name='天国大魔境',
        number_of_seasons=1, seasons=[dict(season_number=1, episode_count=13)],
        alternative_titles=dict(results=[dict(title='Heavenly Delusion')])), **changes)


def test_tv_cache_binds_titles_and_scope_from_one_response(cache_reader):
    from bobbi_core.subtitle_episode import SingleSeason
    cache_reader.save(208891)
    result = cache_reader.module.cached_identity(208891)
    assert result['scope'] == SingleSeason(208891, 13)
    assert result['titles'] == titles()
    assert len(cache_reader.calls) == 2


def test_tv_multiseason_aliases_do_not_require_single_season(cache_reader):
    cache_reader.save(208891, detail=tv_detail(number_of_seasons=2, seasons=[
        dict(season_number=1, episode_count=13), dict(season_number=2, episode_count=12)]))
    result = cache_reader.module.cached_identity(208891)
    assert result['scope'] is None and result['titles'] == titles()


@pytest.mark.parametrize('fault', ['missing', 'stale', 'future', 'wrong_id', 'string_id',
                                  'bool_id', 'missing_name', 'conflicting_equal_time'])
def test_invalid_or_conflicting_cache_never_produces_alias_evidence(cache_reader, fault):
    if fault != 'missing':
        detail = tv_detail()
        if fault in ('wrong_id', 'string_id', 'bool_id'):
            detail['id'] = {'wrong_id': 999, 'string_id': '208891', 'bool_id': True}[fault]
        if fault == 'missing_name':
            detail.pop('name')
        cache_reader.save(208891, detail=detail, fetched=(1 if fault == 'stale' else
                          1000001 if fault == 'future' else 999999))
        if fault == 'conflicting_equal_time':
            cache_reader.save('208891', detail=tv_detail(original_name='Different Work'))
    assert cache_reader.module.cached_identity(208891) is None
    assert len(cache_reader.calls) == 2


def test_tv_two_cache_keys_choose_coverage_then_age_without_merging(cache_reader):
    cache_reader.save(208891, fetched=999999, detail=tv_detail(alternative_titles=None, original_name='Old Name'))
    cache_reader.save('208891', fetched=999990)
    assert cache_reader.module.cached_identity(208891)['titles'] == titles()
    cache_reader.save(208891, fetched=999999, detail=tv_detail(original_name='New Name'))
    result = cache_reader.module.cached_identity(208891)
    assert 'New Name' in result['titles'].titles and '天国大魔境' not in result['titles'].titles


@pytest.mark.parametrize('fetched', [999990, 999999])
@pytest.mark.parametrize('change', ['multiseason', 'episode_count'])
def test_alias_coverage_cannot_overrule_equal_or_newer_season_information(cache_reader, fetched, change):
    cache_reader.save(208891, fetched=999990)
    updated = tv_detail(alternative_titles=None, seasons=[dict(season_number=1, episode_count=12)])
    if change == 'multiseason':
        updated = tv_detail(alternative_titles=None, number_of_seasons=2, seasons=[
            dict(season_number=1, episode_count=13), dict(season_number=2, episode_count=12)])
    cache_reader.save('208891', fetched=fetched, detail=updated)
    result = cache_reader.module.cached_identity(208891)
    assert result['titles'] == titles() and result['scope'] is None
    row = dict(EXACT, native_name='天国大魔境', filename='天国大魔境 EP01.srt')
    assert subtitles.rank(row, dict(CONTEXT, _subtitle_titles=result['titles'],
                                   _subtitle_single_season=result['scope'])) is None


@pytest.mark.parametrize('stamp', [10**400, -10**400, float('nan'), float('inf'), float('-inf'), True, '999999'])
def test_malformed_timestamp_cannot_interrupt_optional_cache_read(cache_reader, stamp):
    cache_reader.save(208891, fetched=stamp)
    assert cache_reader.module.cached_identity(208891) is None


def test_matching_newer_basic_scope_keeps_rich_aliases_and_single_season(cache_reader):
    from bobbi_core.subtitle_episode import SingleSeason
    cache_reader.save(208891, fetched=999990)
    cache_reader.save('208891', fetched=999999, detail=tv_detail(alternative_titles=None))
    result = cache_reader.module.cached_identity(208891)
    assert result['titles'] == titles() and result['scope'] == SingleSeason(208891, 13)


@pytest.mark.parametrize('identifier', [None, True, '208891', -1])
def test_invalid_tv_context_id_does_not_read_cache(cache_reader, identifier):
    assert cache_reader.module.cached_identity(identifier) is None
    assert cache_reader.calls == []


def test_discovery_removes_incoming_private_evidence_and_injects_one_object(monkeypatch):
    from bobbi_core.subtitle_episode import SingleSeason
    evidence, scope = titles(), SingleSeason(208891, 13)
    stub(monkeypatch, 'lib.clients.tmdb.subtitle_scope',
         cached_identity=lambda _: dict(titles=evidence, scope=scope))
    fallback = load(monkeypatch, 'alias_shared_discovery', LIB / 'services/subtitle_fallback.py')
    seen = []
    def share(meta, context, deadline, cancelled):
        seen.append(context)
    def remote(context, deadline, cancelled):
        seen.append(context)
        return {'state': 'candidate'}
    incoming = dict(CONTEXT, _share={'fixture': True}, _subtitle_titles={'titles': ['Forged']},
                    _subtitle_single_season={'episodes': 999}, _movie_years={'years': [1999]})
    fallback.discover_candidate(incoming, 30, lambda: False, SimpleNamespace(candidates=remote), share)
    assert seen[0] is seen[1] and seen[0]['_subtitle_titles'] is evidence
    assert seen[0]['_subtitle_single_season'] is scope and '_movie_years' not in seen[0]
    assert incoming['_subtitle_titles'] == {'titles': ['Forged']}
    assert subtitles.identity(seen[0]) == subtitles.identity(incoming)


def test_discovery_without_cache_removes_even_typed_incoming_titles(monkeypatch):
    stub(monkeypatch, 'lib.clients.tmdb.subtitle_scope', cached_identity=lambda _: None)
    fallback = load(monkeypatch, 'alias_missing_cache_discovery', LIB / 'services/subtitle_fallback.py')
    seen = []
    fallback.discover_candidate(dict(CONTEXT, _subtitle_titles=titles()), 30, lambda: False,
        SimpleNamespace(candidates=lambda context, *args: seen.append(context) or {}))
    assert '_subtitle_titles' not in seen[0]


def test_movie_discovery_reads_existing_identity_once_and_preserves_media_key(monkeypatch):
    from bobbi_core.movie_years import MovieYears
    calls, seen = [], []
    catalog = dict(tmdb_id=62, aliases=['太空漫游', '2001 A Space Odyssey'],
                   evidence=MovieYears(62, 1968, (1968,)))
    stub(monkeypatch, 'lib.clients.tmdb.movie_years',
         cached_movie_identity=lambda ident: calls.append(ident) or catalog,
         cached_movie_years=lambda ident: pytest.fail('Duplicate movie cache read'))
    fallback = load(monkeypatch, 'alias_movie_discovery', LIB / 'services/subtitle_fallback.py')
    incoming = dict(mode='movie', title='太空漫游', tmdb=62, year=1968, duration=8000)
    fallback.discover_candidate(incoming, 30, lambda: False,
        SimpleNamespace(candidates=lambda context, *args: seen.append(context) or {}))
    assert calls == [62] and seen[0]['_movie_years'] is catalog['evidence']
    assert seen[0]['_subtitle_titles'].titles == ('太空漫游', '2001 A Space Odyssey')
    assert subtitles.identity(incoming) == subtitles.identity(seen[0])


def test_standard_and_native_use_the_same_cache_enriched_discovery(monkeypatch):
    import ast
    from threading import Event
    evidence, calls = titles(), []
    stub(monkeypatch, 'lib.clients.tmdb.subtitle_scope',
         cached_identity=lambda _: dict(titles=evidence, scope=None))
    fallback = load(monkeypatch, 'lib.services.subtitle_fallback', LIB / 'services/subtitle_fallback.py')
    tree = ast.parse((LIB / 'services/standard_playback.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'discover')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<production-standard-candidate>', 'exec'), namespace)
    p = SimpleNamespace(candidates=lambda context, *args: calls.append(context) or {'file': {'fixture': True}})
    controller = fallback.SubtitleFallback(factory=lambda: p, clock=lambda: 0)
    receipt = dict(native_instance='fixture', request_id='request', subtitle_intent=0)
    controller.key = fallback.receipt_key(receipt)
    controller._run(controller.key, receipt, CONTEXT, Event(), 30)
    assert controller.result['state'] == 'candidate'
    monkeypatch.setattr(subtitles, 'AssrtCandidates', lambda *args, **kwargs: p)
    namespace['discover'](dict(mode='tv', showtitle=CONTEXT['title'], ids={'tmdb_id': 208891},
        year=2023, tv_data=dict(season=1, episode=1)),
        SimpleNamespace(accounts=None, sidecar_candidate=None), 30, lambda: False)
    assert len(calls) == 2 and all(context['_subtitle_titles'] is evidence for context in calls)
