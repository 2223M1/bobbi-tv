"""Entry-owned filter settings; debrid is stubbed at this filter-only boundary."""
from frozen_history import source_bytes
import ast
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
import requests


ROOT = Path(__file__).resolve().parents[2]
BASE = 'f3c2e7771529a916c154c5beee1f101c5cd2d857'
ENTRY_BASE = '18161f7355082637c280dd8fc4e0ced0d3a5c862'
LIB = 'addons/plugin.video.bobbi/lib/'


class AmbientSettingsRead(AssertionError):
    pass


def forbidden_setting(key, default=None):
    raise AmbientSettingsRead(key)


def snapshot(values):
    frozen, calls = dict(values), []

    def read(key, default=None):
        calls.append((key, default))
        return frozen.get(key, default)

    return read, calls


@pytest.fixture
def pipeline(monkeypatch):
    from lib import search
    from lib.domain.torrent import TorrentStream
    from lib.utils.general import processors, utils
    from lib.utils.kodi import settings, utils as kodi

    for module in (search, utils, processors, kodi, settings):
        monkeypatch.setattr(module, 'get_setting', forbidden_setting)

    def no_io(*args, **kwargs):
        pytest.fail('Pure filtering must not perform HTTP or manipulate Kodi UI')

    monkeypatch.setattr(requests.sessions.Session, 'request', no_io)
    monkeypatch.setattr(search, 'close_busy_dialog', no_io)
    debrid_calls = []

    def debrid(*args, **kwargs):
        # This boundary is intentionally outside the filter-only slice.
        debrid_calls.append(args)
        return []

    monkeypatch.setattr(search, 'check_debrid_cached', debrid)

    def row(token, title='Fixture 1080p WEB-DL H264', **kwargs):
        return TorrentStream(title=title, infoHash=token * 40, indexer='Jackett',
                             type='Torrent', **kwargs)

    def run(rows, getter=None, **kwargs):
        options = dict(mode='movies', ep_name='', episode=1, season=1,
                       scoped_addon_url='', query='Fixture', media_type='movies',
                       rescrape=False, suppress_debrid_dialog=True,
                       suppress_busy_dialog=True)
        options.update(kwargs)
        if getter is not None:
            options['settings_getter'] = getter
        return search._process_search_results(rows, **options)

    return SimpleNamespace(search=search, general=utils, processors=processors,
                           row=row, run=run, debrid_calls=debrid_calls)


def configuration(**values):
    return dict(torrent_enable=True, stremio_bypass_addons=False,
                indexers_total_results='100', **values)


def tokens(rows):
    return [row.infoHash[0] for row in rows]


def test_real_pipeline_keeps_opposite_snapshots_independent(pipeline):
    a = configuration(codec_hevc_enabled=False, indexers_sort_by='seeders')
    a['indexers_total_results'] = '1'
    b = configuration(codec_hevc_enabled=True, indexers_sort_by='SIZE')
    b['indexers_total_results'] = '2'
    read_a, calls_a = snapshot(a)
    read_b, calls_b = snapshot(b)
    # A later configuration edit is not a reason to recapture this dependency.
    a.update(b)
    b['codec_hevc_enabled'] = False

    def rows():
        return [pipeline.row('a', 'Fixture 1080p HEVC', size=300, seeders=30),
                pipeline.row('b', size=200, seeders=20),
                pipeline.row('c', 'Fixture 1080p AV1', size=400, seeders=10)]

    assert tokens(pipeline.run(rows(), read_a)) == ['b']
    assert tokens(pipeline.run(rows(), read_b)) == ['c', 'a']
    assert tokens(pipeline.run(rows(), read_a)) == ['b']
    assert ('codec_hevc_enabled', True) in calls_a
    assert ('indexers_sort_by', None) in calls_b
    assert len(pipeline.debrid_calls) == 3
    assert all(len(args) == 7 for args in pipeline.debrid_calls)


@pytest.mark.parametrize('key,title', [
    ('unknown_quality_enabled', 'Fixture WEB-DL'),
    ('bluray_hd_enabled', 'Fixture 1080p BluRay'),
    ('web_hd_enabled', 'Fixture 1080p WEB-DL'),
    ('dvd_tv_enabled', 'Fixture 1080p HDTV'),
    ('cam_screener_enabled', 'Fixture 1080p CAM'),
    ('unknown_enabled', 'Fixture 1080p'),
    ('codec_hevc_enabled', 'Fixture 1080p HEVC'),
    ('codec_av1_enabled', 'Fixture 1080p AV1'),
    ('codec_h264_enabled', 'Fixture 1080p H264'),
    ('dolby_vision_enabled', 'Fixture 1080p DV release'),
    ('hdr10_enabled', 'Fixture 1080p HDR10+'),
    ('hdr_enabled', 'Fixture 1080p HDR'),
])
def test_each_filter_reads_explicit_boolean_and_preserves_true_default(pipeline, key, title):
    for value, expected in ((False, []), (True, ['a'])):
        read, calls = snapshot(configuration(**{key: value}))
        assert tokens(pipeline.run([pipeline.row('a', title)], read)) == expected
        assert (key, True) in calls


@pytest.mark.parametrize('include', [False, True])
def test_season_pack_setting_never_relaxes_catalog_identity(pipeline, include):
    read, calls = snapshot(configuration(include_season_packs=include))
    rows = [pipeline.row('a', 'Fixture S01 1080p'),
            pipeline.row('b', 'Fixture S01E01 1080p'),
            pipeline.row('c', 'Fixture S01E02 1080p'),
            pipeline.row('d', 'Other Show S01E01 1080p'),
            pipeline.row('e', 'Fixture S02 1080p')]
    kept = pipeline.search._cinema_filter_catalog_candidates(
        rows, ['Fixture'], 'tv', 1, 1, settings_getter=read)
    assert tokens(kept) == (['a', 'b'] if include else ['b'])
    result = pipeline.run(kept, read, mode='tv', media_type='tv')
    assert set(tokens(result)) == ({'a', 'b'} if include else {'b'})
    assert ('include_season_packs', None) in calls


@pytest.mark.parametrize('enabled', [False, True])
def test_bypass_and_torrent_switch_are_injected_without_changing_debrid_call(pipeline, enabled):
    read, calls = snapshot(dict(torrent_enable=False, stremio_bypass_addons=enabled,
                                stremio_bypass_addon_list=' chosen ', codec_hevc_enabled=False))
    rows = [pipeline.row('a', 'Fixture 1080p HEVC', addonKey='chosen'),
            pipeline.row('b')]
    assert tokens(pipeline.run(rows, read)) == (['a'] if enabled else [])
    assert ('torrent_enable', None) in calls
    assert not any(key == 'indexers_total_results' for key, _ in calls)
    assert tokens(pipeline.debrid_calls[0][1]) == ['b']


def test_explicit_episode_conflict_precedes_bypass(pipeline):
    read, _ = snapshot(dict(stremio_bypass_addons=True, stremio_bypass_addon_list='chosen'))
    rows = [pipeline.row('a', 'Fixture S01E02 1080p', addonKey='chosen'),
            pipeline.row('b', 'Fixture S01E01 1080p', addonKey='chosen')]
    assert tokens(pipeline.run(rows, read, mode='tv', recommendation_context={})) == ['b']
    assert not pipeline.debrid_calls


@pytest.mark.parametrize('maximum,expected', [(None, ['a']), ('', ['a']), (False, ['a']),
                                               (0, ['a']), ('0', []), ('1', ['a'])])
def test_size_filter_preserves_original_or_and_int_semantics(pipeline, maximum, expected):
    read, calls = snapshot(configuration(filter_size_enabled=True, minimum_size='', maximum_size=maximum))
    assert tokens(pipeline.run([pipeline.row('a', size=1024 * 1024)], read)) == expected
    assert ('minimum_size', None) in calls and ('maximum_size', None) in calls


def test_disabled_size_filter_never_reads_size_bounds(pipeline):
    read, calls = snapshot(configuration(filter_size_enabled=False, minimum_size='invalid', maximum_size='invalid'))
    assert tokens(pipeline.run([pipeline.row('a', size=1024)], read)) == ['a']
    assert not {'minimum_size', 'maximum_size'} & {key for key, _ in calls}


def test_size_bounds_are_inclusive_and_unknown_size_is_retained(pipeline):
    read, _ = snapshot(configuration(filter_size_enabled=True, minimum_size='2', maximum_size='3'))
    rows = [pipeline.row(token, size=size * 1024 * 1024)
            for token, size in zip('abcde', (1, 2, 3, 4, 0))]
    assert tokens(pipeline.run(rows, read)) == ['b', 'c', 'e']


@pytest.mark.parametrize('key,value,error', [('minimum_size', 'bad', ValueError),
                                           ('maximum_size', object(), TypeError),
                                           ('indexers_total_results', 'bad', ValueError),
                                           ('indexers_total_results', None, TypeError)])
def test_invalid_numbers_still_raise(pipeline, key, value, error):
    values = configuration(filter_size_enabled=True)
    values[key] = value
    read, _ = snapshot(values)
    with pytest.raises(error):
        pipeline.run([pipeline.row('a', size=1024)], read)


@pytest.mark.parametrize('limit,expected', [('0', []), ('2', ['c', 'b']), (-1, ['c', 'b'])])
def test_post_builder_keeps_sort_and_slice_semantics(pipeline, limit, expected):
    read, _ = snapshot(dict(indexers_sort_by='SEEDS', indexers_total_results=limit))
    rows = [pipeline.row(token, seeders=index) for index, token in enumerate('abc')]
    assert tokens(pipeline.general.post_process(rows, settings_getter=read)) == expected


def test_recommendation_ranking_still_ignores_user_sort_but_obeys_limit(pipeline):
    from lib.utils.general.cinema_source_rank import rank_sources
    rows = [pipeline.row('a', seeders=100), pipeline.row('b', 'Fixture 2160p WEB-DL', seeders=1)]
    context = dict(mode='movies', query='Fixture')
    expected = rank_sources(deepcopy(rows), context)[:1]

    def read(key, default=None):
        assert key != 'indexers_sort_by'
        return {'indexers_total_results': '1', 'torrent_enable': True}.get(key, default)

    result = pipeline.general.post_process(deepcopy(rows), recommendation_context=context, settings_getter=read)
    assert tokens(result) == tokens(expected)
    assert tokens(pipeline.run(deepcopy(rows), read, recommendation_context=context)) == tokens(expected)


def test_getter_failure_in_builder_propagates_without_ambient_fallback(pipeline):
    read, _ = snapshot(configuration())

    def revoked(key, default=None):
        if key == 'unknown_quality_enabled':
            raise ValueError('SEARCH_SETTINGS_PROFILE_CHANGED')
        return read(key, default)

    with pytest.raises(ValueError, match='SEARCH_SETTINGS_PROFILE_CHANGED'):
        pipeline.run([pipeline.row('a')], revoked)
    assert not pipeline.debrid_calls


def test_missing_values_keep_callsite_defaults_and_falsey_getter_is_not_ambient(pipeline):
    read, calls = snapshot({'torrent_enable': True})

    class FalseyGetter:
        def __bool__(self):
            return False

        def __call__(self, key, default=None):
            return read(key, default)

    assert tokens(pipeline.run([pipeline.row('a')], FalseyGetter())) == ['a']
    assert ('stremio_bypass_addons', True) in calls
    assert ('stremio_bypass_addon_list', '') in calls
    assert ('filter_size_enabled', None) in calls
    assert ('indexers_total_results', 10) in calls


def test_omitted_getter_preserves_legacy_entry_behavior(pipeline, monkeypatch):
    read, _ = snapshot(configuration(codec_hevc_enabled=False, indexers_sort_by='SIZE'))
    for module in (pipeline.search, pipeline.general, pipeline.processors):
        monkeypatch.setattr(module, 'get_setting', read)
    rows = [pipeline.row('a', 'Fixture 1080p HEVC'), pipeline.row('b')]
    assert tokens(pipeline.run(deepcopy(rows))) == tokens(pipeline.run(deepcopy(rows), read)) == ['b']


@lru_cache(maxsize=None)
def original_tree(path, revision=BASE):
    source = source_bytes(revision, path).decode('utf-8')
    return ast.parse(source)


def original_definitions(path, names, namespace, revision=BASE):
    definitions = [node for node in original_tree(path, revision).body
                   if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert len(definitions) == len(names)
    scope = dict(namespace)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<frozen-filter-baseline>', 'exec'), scope)
    return scope


def test_fixed_original_chain_observes_ambient_b_instead_of_requested_a(pipeline):
    read_a, _ = snapshot(configuration(codec_hevc_enabled=False))
    read_b, _ = snapshot(configuration(codec_hevc_enabled=True))
    builder_scope = original_definitions(LIB + 'utils/general/processors.py',
        {'BaseProcessBuilder', 'PreProcessBuilder', 'PostProcessBuilder'},
        dict(vars(pipeline.processors), get_setting=read_b))
    general_scope = original_definitions(LIB + 'utils/general/utils.py', {'pre_process', 'post_process'},
        dict(vars(pipeline.general), get_setting=read_b,
             PreProcessBuilder=builder_scope['PreProcessBuilder'], PostProcessBuilder=builder_scope['PostProcessBuilder']))
    search_scope = original_definitions(LIB + 'search.py',
        {'_process_search_results', 'pre_process_results', 'process_results'},
        dict(vars(pipeline.search), get_setting=read_b,
             pre_process=general_scope['pre_process'], post_process=general_scope['post_process']))
    rows = [pipeline.row('a', 'Fixture 1080p HEVC'), pipeline.row('b')]
    original = search_scope['_process_search_results'](deepcopy(rows), 'movies', '', 1, 1,
        '', 'Fixture', 'movies', False, suppress_debrid_dialog=True, suppress_busy_dialog=True)
    assert tokens(original) == ['b', 'a']  # Existing WEB bucket precedes unknown source.
    assert tokens(pipeline.run(deepcopy(rows), read_a)) == ['b']
    # The same old function fails when ambient access is forbidden, while the
    # injected live pipeline above succeeds with all ambient getters trapped.
    search_scope['get_setting'] = forbidden_setting
    with pytest.raises(AmbientSettingsRead):
        search_scope['_process_search_results'](deepcopy(rows), 'movies', '', 1, 1,
            '', 'Fixture', 'movies', False, suppress_debrid_dialog=True, suppress_busy_dialog=True)


@pytest.fixture
def entry_filters(pipeline, tmp_path, monkeypatch):
    """Real entry capture/transform, without provider or account operations.

    Calling the returned transform directly isolates this wiring from the
    coordinator's separately tested publication/admission/cache lifecycle.
    """
    from bobbi_core import search_trace
    from bobbi_platform import paths, source_libraries
    from lib.clients.tmdb import episode_order

    search, active, captures, getters, pumps = pipeline.search, ['A'], [], [], []
    monkeypatch.setattr(paths, '_translated_profile_root', lambda addon: tmp_path / active[0] / addon)
    monkeypatch.setattr(source_libraries, 'capture_context', lambda binding=None: None)
    monkeypatch.setattr(episode_order, 'release_pair', lambda *args: None)
    monkeypatch.setattr(search, '_movie_catalog_context', lambda *args: {})
    monkeypatch.setattr(search, '_tv_completed_context', lambda *args: {})
    monkeypatch.setattr(search_trace, 'configure', lambda *args: None)
    monkeypatch.setattr(search_trace, 'observe', lambda *args, **kwargs: None)
    capture = search.capture_settings

    def observed_capture(root, current):
        # Observe the existing real XML snapshot, not a substitute settings map.
        read, calls = capture(root, current), []

        def observed_read(key, default=None):
            calls.append((key, default))
            return read(key, default)

        captures.append((root, calls))
        getters.append(observed_read)
        return observed_read

    monkeypatch.setattr(search, 'capture_settings', observed_capture)

    def write(profile, values):
        root = tmp_path / profile / 'plugin.video.bobbi'
        root.mkdir(parents=True, exist_ok=True)
        document = ET.Element('settings', version='2')
        for key, value in values.items():
            ET.SubElement(document, 'setting', id=key).text = (
                str(value).lower() if isinstance(value, bool) else str(value))
        (root / 'settings.xml').write_text(ET.tostring(document, encoding='unicode'), encoding='utf-8')

    def create(mode='tv', original_control=False):
        factory = search._create_source_search
        if original_control:
            factory = original_definitions(LIB + 'search.py', {'_create_source_search'},
                vars(search), ENTRY_BASE)['_create_source_search']
        session, pump = factory({}, 'Fixture', {}, mode, mode, {'season': 1, 'episode': 1},
            False, '', search.SearchVariant.DEFAULT, search.TITLE_LANGUAGE_LOCALIZED_FIRST,
            2020, True, {}, [])
        # Filter-only tests call transform directly without running providers.
        # Model a started round explicitly; production obtains this at admission.
        pump.deadline = monotonic() + 30
        pumps.append(pump)
        return session, pump

    def rows():
        return [pipeline.row('a', 'Fixture S01 1080p WEB-DL H264'),
                pipeline.row('b', 'Fixture S01E01 1080p WEB-DL H264'),
                pipeline.row('c', 'Fixture S01E01 2160p WEB-DL HEVC'),
                pipeline.row('d', 'Other Show S01E01 1080p WEB-DL H264'),
                pipeline.row('e', 'Fixture S01E02 1080p WEB-DL H264'),
                pipeline.row('f', 'Fixture S02 1080p WEB-DL H264')]

    yield SimpleNamespace(write=write, create=create, rows=rows, active=active, captures=captures,
                          getters=getters, root=tmp_path, pipeline=pipeline)
    for pump in pumps:
        pump.cancel()


def test_actual_entry_filters_keep_xml_snapshot_and_revoke_observed_profile_switch(entry_filters):
    fixture = entry_filters
    a = configuration(codec_hevc_enabled=False, include_season_packs=False)
    b = configuration(codec_hevc_enabled=True, include_season_packs=True)
    fixture.write('A', a)
    fixture.write('B', b)
    _, old_a = fixture.create()
    fixture.write('A', b)
    assert tokens(old_a.transform(fixture.rows())) == ['b']
    root, calls = fixture.captures[0]
    assert root == fixture.root / 'A' / 'plugin.video.bobbi'
    # Catalog screening and pre-process must both use this one captured getter.
    assert calls.count(('include_season_packs', None)) == 2
    # Entry list limit and the real post builder share the same snapshot too.
    assert calls.count(('indexers_total_results', 10)) == 2
    assert ('codec_hevc_enabled', True) in calls
    assert len(fixture.captures) == 1

    fixture.active[0] = 'B'
    with pytest.raises(ValueError, match='SEARCH_SETTINGS_PROFILE_CHANGED'):
        old_a.transform(fixture.rows())
    _, new_b = fixture.create()
    assert set(tokens(new_b.transform(fixture.rows()))) == {'a', 'b', 'c'}
    fixture.active[0] = 'A'
    with pytest.raises(ValueError, match='SEARCH_SETTINGS_PROFILE_CHANGED'):
        old_a.transform(fixture.rows())
    _, new_a = fixture.create()
    assert set(tokens(new_a.transform(fixture.rows()))) == {'a', 'b', 'c'}
    assert len(fixture.captures) == 3
    assert len(fixture.pipeline.debrid_calls) == 3


def test_actual_entry_passes_snapshot_limit_to_real_post_builder(entry_filters):
    fixture = entry_filters
    values = configuration(codec_hevc_enabled=True, include_season_packs=True)
    values['indexers_total_results'] = '1'
    fixture.write('A', values)
    _, pump = fixture.create()
    values['indexers_total_results'] = '100'
    fixture.write('A', values)
    assert tokens(pump.transform(fixture.rows())) == ['c']
    assert set(tokens(fixture.pipeline.debrid_calls[0][1])) == {'a', 'b', 'c'}
    assert len(fixture.captures) == 1


@pytest.mark.parametrize('mode,missing_key', [('tv', 'include_season_packs'),
                                             ('movies', 'stremio_bypass_addons')])
@pytest.mark.parametrize('original_control', [False, True], ids=['connected', 'original-control'])
def test_actual_entry_transform_wiring_against_fixed_unconnected_baseline(
        entry_filters, mode, missing_key, original_control):
    fixture = entry_filters
    fixture.write('A', configuration(codec_hevc_enabled=False, include_season_packs=False))
    _, pump = fixture.create(mode=mode, original_control=original_control)
    rows = ([fixture.pipeline.row('b', 'Fixture S01E01 1080p WEB-DL H264')] if mode == 'tv'
            else [fixture.pipeline.row('b')])
    if original_control:
        with pytest.raises(AmbientSettingsRead, match=missing_key):
            pump.transform(rows)
        assert not fixture.pipeline.debrid_calls
    else:
        assert tokens(pump.transform(rows)) == ['b']
        assert len(fixture.pipeline.debrid_calls) == 1
    assert len(fixture.captures) == 1


@pytest.fixture
def fallback_filters(entry_filters, monkeypatch):
    """Real managed submission/fallback/filtering with an inert provider boundary.

    The getter comes from a real entry, but setup and coordinator execution are
    not started here. Independent provider filtering and debrid remain isolated.
    """
    from bobbi_core.search_completion import SearchCompletion, SearchResults

    fixture, search = entry_filters, entry_filters.pipeline.search
    state = SimpleNamespace(queries=['Fixture'], branch='single', streamed=[], provider_calls=[],
                            client_getters=[], completion=SearchCompletion(2, succeeded=1, failed=1))
    monkeypatch.setattr(search.xbmc, 'getSkinDir', lambda: 'skin.bobbi.cinema')
    monkeypatch.setattr(search, '_build_title_fallback_queries', lambda *a, **kw: state.queries)
    monkeypatch.setattr(search, '_cinema_catalog_aliases', lambda *a, **kw: ['Fixture'])
    monkeypatch.setattr(search, '_cinema_anime_queries', lambda *a, **kw: [])
    monkeypatch.setattr(search, '_anime_absolute_query', lambda *a, **kw: '')
    monkeypatch.setattr(search, '_anime_release_query', lambda *a, **kw: '')

    def provider(*args, **kwargs):
        state.provider_calls.append((args, kwargs))
        assert args == ('Fixture', 'tv', 1, 1)
        assert kwargs.get('title_queries') == (state.queries if state.branch == 'multi' else None)
        rows = SearchResults(fixture.rows(), state.completion)
        if state.branch == 'publish':
            kwargs['publish'](SearchResults(fixture.rows(), state.completion))
        return rows

    def client(indexer, settings_getter=None):
        assert indexer == search.Indexer.JACKETT
        state.client_getters.append(settings_getter)
        return SimpleNamespace(search=provider)

    monkeypatch.setattr(search, 'get_client', client)

    def prepare(branch, include):
        state.branch = branch
        state.queries = ['Fixture', 'Fixture Alias'] if branch == 'multi' else ['Fixture']
        values = configuration(include_season_packs=include, codec_hevc_enabled=True,
            jackett_enabled=True, prowlarr_enabled=False, jackgram_enabled=False,
            jacktookburst_enabled=False, easynews_enabled=False, stremio_enabled=False,
            nuvio_enabled=False, external_scraper_enabled=False)
        fixture.write('A', values)
        _, state.pump = fixture.create()
        state.getter = fixture.getters[-1]
        values['include_season_packs'] = not include
        fixture.write('A', values)
        tasks = []
        manager = SimpleNamespace(submit_task=lambda *args, **kwargs: tasks.append((args, kwargs)))
        backend = SimpleNamespace(get=lambda key: ['Jackett'] if key == 'source_manager_selection' else None)
        search._submit_search_tasks_managed(manager, None, 'Fixture', 'tv', 'tv', 1, 1,
            {'tmdb_id': 123}, '', 123, None, cache_backend=backend, settings_getter=state.getter)
        assert len(tasks) == 1
        state.task_args, state.task_kwargs = tasks[0]
        assert state.task_args[2] is search._perform_search_with_title_fallback
        assert state.task_kwargs['settings_getter'] is state.getter

    def run(original_control=False, omit_getter=False):
        function, args = state.task_args[2], state.task_args[3:]
        if original_control:
            function = original_definitions(LIB + 'search.py', {'_perform_search_with_title_fallback'},
                vars(search), ENTRY_BASE)['_perform_search_with_title_fallback']
        kwargs = dict(state.task_kwargs)
        if omit_getter:
            kwargs.pop('settings_getter')
        if state.branch == 'publish':
            kwargs['publish'] = state.streamed.append
        return function(*args, **kwargs)

    return SimpleNamespace(prepare=prepare, run=run, state=state, entry=fixture)


@pytest.mark.parametrize('branch', ['publish', 'multi', 'single'])
@pytest.mark.parametrize('include', [False, True])
@pytest.mark.parametrize('original_control', [False, True], ids=['connected', 'original-control'])
def test_fallback_catalog_screening_uses_entry_snapshot_before_transform(
        fallback_filters, monkeypatch, branch, include, original_control):
    fixture = fallback_filters
    fixture.prepare(branch, include)
    ambient_calls = []

    def ambient_opposite(key, default=None):
        assert key == 'include_season_packs'
        ambient_calls.append((key, default))
        return not include

    monkeypatch.setattr(fixture.entry.pipeline.processors, 'get_setting', ambient_opposite)
    result = fixture.run(original_control=original_control)
    screened = fixture.state.streamed + [result]
    expected = {'a', 'b', 'c'} if (not include if original_control else include) else {'b', 'c'}
    assert len(screened) == (2 if branch == 'publish' else 1)
    assert all(set(tokens(rows)) == expected for rows in screened)
    assert all(rows.completion == fixture.state.completion for rows in screened)
    assert len(ambient_calls) == (len(screened) if original_control else 0)
    assert fixture.state.client_getters == [fixture.state.getter]
    assert len(fixture.state.provider_calls) == 1
    # A connected transform cannot recover a pack discarded by old screening.
    final = fixture.state.pump.transform(result)
    assert set(tokens(final)) == ({'a', 'b', 'c'} if include and not original_control else {'b', 'c'})
    assert len(fixture.entry.captures) == 1
    assert len(fixture.entry.pipeline.debrid_calls) == 1


@pytest.mark.parametrize('branch', ['publish', 'multi', 'single'])
def test_fallback_catalog_screening_never_falls_back_on_revoked_snapshot(fallback_filters, branch):
    fixture = fallback_filters
    fixture.prepare(branch, True)
    fixture.entry.active[0] = 'B'
    with pytest.raises(ValueError, match='SEARCH_SETTINGS_PROFILE_CHANGED'):
        fixture.run()
    assert fixture.state.client_getters == [fixture.state.getter]
    assert not fixture.state.streamed
    assert not fixture.entry.pipeline.debrid_calls


@pytest.mark.parametrize('branch', ['publish', 'multi', 'single'])
def test_fallback_catalog_screening_omitted_getter_keeps_legacy_default(fallback_filters, monkeypatch, branch):
    fixture = fallback_filters
    fixture.prepare(branch, False)
    read, calls = snapshot({'include_season_packs': True})
    monkeypatch.setattr(fixture.entry.pipeline.processors, 'get_setting', read)
    result = fixture.run(omit_getter=True)
    assert set(tokens(result)) == {'a', 'b', 'c'}
    assert all(set(tokens(rows)) == {'a', 'b', 'c'} for rows in fixture.state.streamed)
    assert calls == [('include_season_packs', None)] * (2 if branch == 'publish' else 1)
    assert fixture.state.client_getters == [None]
    assert result.completion == fixture.state.completion
    assert not fixture.entry.pipeline.debrid_calls
