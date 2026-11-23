"""Production search entry captures paths before any provider work or retry."""
import pytest
import ast
from datetime import timedelta
from pathlib import Path
import sqlite3
from threading import Event, Thread
from types import MethodType, SimpleNamespace
from test_ce2089_shared_search import shared
from test_runtime_profile_binding import profiles, original
from lib import search as production_search

SEARCH_SCOPE = production_search._build_search_cache_scope


@pytest.mark.parametrize('failure', [False, True])
def test_actual_search_entry_captures_once_and_never_recovers_in_worker(shared, profiles, monkeypatch, failure):
    from bobbi_platform import paths, source_libraries
    captures = []
    original_context = source_libraries.capture_context
    def context(binding=None):
        captures.append(binding)
        return original_context(binding=binding)
    monkeypatch.setattr(source_libraries, 'capture_context', context)
    def resolve(addon):
        if failure:
            raise ValueError('CAPTURE_UNAVAILABLE')
        return profiles.root.parent.parent / profiles.active[0] / addon
    monkeypatch.setattr(paths, '_translated_profile_root', resolve)
    search = shared.search
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    assert len(captures) == (0 if failure else 1)
    if not failure:
        assert pump.current.__self__ is captures[0]
        profiles.active[0] = 'B'
        assert not pump.scope_current()
    profiles.active[0] = 'A'
    monkeypatch.setattr(paths, '_translated_profile_root', lambda addon: profiles.other / addon)
    try:
        pump.start()
        pump.thread.join(2)
        assert not pump.thread.is_alive() and not shared.calls
        assert session.snapshot()['entries'] == []
        assert not pump.retry_failed()
        assert not (profiles.root / 'search-admission').exists()
        assert not profiles.other.exists()
    finally:
        pump.cancel()


def test_new_search_uses_b_not_import_time_a_cache(shared, tmp_path, monkeypatch):
    from bobbi_platform import paths
    search = shared.search
    imported = search.cache
    imported_path = Path(imported.db._conn.execute('PRAGMA database_list').fetchone()[2])
    assert 'am6b-kodi-tests-' in str(imported_path)
    profile_b = tmp_path / 'B'
    monkeypatch.setattr(paths, '_translated_profile_root', lambda addon: profile_b / addon)
    count = lambda: imported.db._conn.execute(
        "SELECT COUNT(*) FROM cached WHERE key LIKE 'cinema:provider-snapshot:v2:%'").fetchone()[0]
    before = count()
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    try:
        assert pump.current.__self__.root('plugin.video.bobbi') == profile_b / 'plugin.video.bobbi'
        pump.start()
        pump.thread.join(3)
        assert not pump.thread.is_alive()
        assert len(session.snapshot()['entries']) == 1
        assert count() == before
        backend = pump.query_result_cache.backend
        assert Path(backend.db._conn.execute('PRAGMA database_list').fetchone()[2]).parent == profile_b / 'plugin.video.bobbi'
        assert backend.memory._database != imported.memory._database
        assert backend.db._conn.execute('SELECT COUNT(*) FROM cached').fetchone()[0] > 0
    finally:
        pump.cancel()
    with pytest.raises(sqlite3.ProgrammingError):
        backend.db._conn.execute('SELECT 1')


def frozen_method(cls, name, namespace):
    source = original('addons/plugin.video.bobbi/lib/db/cached.py')
    tree = ast.parse(source)
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls)
    method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name)
    code = compile(ast.Module(body=[method], type_ignores=[]), '<frozen-original-cache>', 'exec')
    scope = dict(namespace)
    exec(code, scope)
    return scope[name]


@pytest.mark.parametrize('original_control', [False, True], ids=['fixed', 'original-control'])
@pytest.mark.parametrize('boundary', ['mutex', 'serialization', 'sqlite-begin', 'before-commit'])
def test_cache_rechecks_profile_at_real_write_boundaries(tmp_path, monkeypatch, boundary, original_control):
    from lib.db import cached
    database = tmp_path / 'captured-a.sqlite'
    active, observed = [True], Event()
    def current():
        observed.set()
        return active[0]
    backend = cached.HybridCache(str(database), current=current)
    backend.set('same', 'old')
    db = backend.db
    if original_control:
        monkeypatch.setattr(db, '_set_until', MethodType(frozen_method('SQLiteCache', '_set_until', vars(cached)), db))
    observed.clear()
    entered = Event()
    writer = Thread(target=lambda: backend.set('same', 'late'))
    blocker = None
    try:
        if boundary == 'mutex':
            with db._lock:
                writer.start()
                assert observed.wait(2)
                active[0] = False
        elif boundary == 'serialization':
            prepare = db._prepare
            def switch(data):
                value = prepare(data)
                active[0] = False
                return value
            monkeypatch.setattr(db, '_prepare', switch)
            writer.start()
        elif boundary == 'sqlite-begin':
            blocker = sqlite3.connect(database, isolation_level=None)
            blocker.execute('BEGIN IMMEDIATE')
            db._conn.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
            writer.start()
            assert entered.wait(2)
            active[0] = False
            blocker.rollback()
        else:
            def switch(sql):
                if sql.startswith('SELECT identity, revision'):
                    active[0] = False
            db._conn.set_trace_callback(switch)
            writer.start()
        writer.join(3)
        assert not writer.is_alive()
        assert not db._object_store
        with sqlite3.connect(database) as reader:
            value = cached.pickle.loads(reader.execute('SELECT data FROM cached WHERE key="same"').fetchone()[0])
        assert value == ('late' if original_control else 'old')
        active[0] = True
        assert backend.get('same') is None  # observation is monotonic, even after A returns
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        writer.join(3)
        backend.close()


@pytest.mark.parametrize('original_control', [False, True], ids=['fixed', 'original-control'])
def test_l1_serialization_cannot_publish_after_revocation(tmp_path, monkeypatch, original_control):
    from lib.db import cached
    active = [True]
    properties = {}
    window = SimpleNamespace(getProperty=lambda key: properties.get(key, ''),
        setProperty=properties.__setitem__, clearProperty=lambda key: properties.pop(key, None))
    monkeypatch.setattr(cached.xbmcgui, 'Window', lambda _: window)
    backend = cached.HybridCache(str(tmp_path / 'captured-a.sqlite'), current=lambda: active[0])
    if original_control:
        monkeypatch.setattr(backend.memory, '_set_until', MethodType(
            frozen_method('MemoryCache', '_set_until', vars(cached)), backend.memory))
    dumps = backend.memory._dump_func
    def switch(value):
        blob = dumps(value)
        active[0] = False
        return blob
    monkeypatch.setattr(backend.memory, '_dump_func', switch)
    try:
        backend.set('key', 'value')
        assert bool(window.getProperty(backend.memory._property_key('key'))) is original_control
        assert not backend.db._object_store
    finally:
        backend.close()


def test_configuration_unknown_preserves_local_rows_and_does_not_start_network(shared, monkeypatch):
    from lib.clients import mdsub_provider
    from lib.domain.torrent import TorrentStream
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a, **kw:
        [TorrentStream(title='Fixture S01E01', infoHash='f' * 40, indexer='Local')])
    def unavailable(*a, **kw):
        raise OSError('unavailable')
    monkeypatch.setattr(shared.search, 'HybridCache', unavailable)
    session, pump = shared.search._create_source_search({}, 'Fixture', {'tmdb_id':123}, 'tv', 'tv',
        {'season':1, 'episode':1}, False, '', shared.search.SearchVariant.DEFAULT,
        shared.search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    try:
        pump.start(); pump.thread.join(3)
        assert not pump.thread.is_alive() and shared.calls == []
        assert len(session.snapshot()['entries']) == 1
        assert session.status()['providers']['coordinator']['state'] == 'FAILED'
    finally:
        pump.cancel()


def test_strict_configuration_read_cannot_turn_unavailable_authority_into_empty(tmp_path, monkeypatch):
    from lib.db import cached
    backend = cached.HybridCache(str(tmp_path / 'a.sqlite'), strict_reads=True)
    try:
        backend.set('source_manager_selection', '[]')
        before = backend.db._conn.execute('SELECT data FROM cached').fetchall()
        monkeypatch.setattr(backend.db, '_revision', lambda: None)
        with pytest.raises(RuntimeError, match='CACHE_AUTHORITY_UNAVAILABLE'):
            backend.get('source_manager_selection')
        assert backend.db._conn.execute('SELECT data FROM cached').fetchall() == before
    finally:
        backend.close()


@pytest.mark.parametrize('key,value', [
    ('stremio_user_addons', {}), ('nuvio_user_addons', False),
    ('stremio_user_addons', [{'manifest': {'resources': [123]}}]),
    ('nuvio_user_addons', [{'manifest': {'resources': [123]}}]),
    ('stremio_addons', [123]), ('nuvio_addons', '["valid", {}]'),
    ('stremio_addon_aliases', []), ('source_manager_selection', '[123]'),
    ('source_manager_known_keys', {'wrong': 'collection'}),
])
def test_corrupt_configuration_fails_before_any_reconcile_write(shared, monkeypatch, key, value):
    from lib.db import cached
    from lib.utils import source_manager
    from lib.clients import mdsub_provider
    from lib.domain.torrent import TorrentStream
    writes = []
    monkeypatch.setattr(shared.search, 'reconcile_source_selection', source_manager.reconcile_source_selection)
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a, **kw:
        [TorrentStream(title='Fixture S01E01', infoHash='f' * 40, indexer='Local')])
    def factory(*args, **kwargs):
        backend = cached.HybridCache(*args, **kwargs)
        backend.set(key, value)
        saved_set = backend.set
        def record(k, *a, **kw):
            writes.append(k)
            return saved_set(k, *a, **kw)
        monkeypatch.setattr(backend, 'set', record)
        return backend
    monkeypatch.setattr(shared.search, 'HybridCache', factory)
    session, pump = shared.search._create_source_search({}, 'Fixture', {'tmdb_id':123}, 'tv', 'tv',
        {'season':1, 'episode':1}, False, '', shared.search.SearchVariant.DEFAULT,
        shared.search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    try:
        pump.start(); pump.thread.join(3)
        assert not pump.thread.is_alive() and shared.calls == [] and writes == []
        assert len(session.snapshot()['entries']) == 1
        assert session.status()['providers']['coordinator']['state'] == 'FAILED'
    finally:
        pump.cancel()


@pytest.mark.parametrize('origin', ['stremio', 'nuvio'])
def test_configuration_failure_after_successful_preflight_still_prevents_reconcile_write(shared, monkeypatch, origin):
    from lib.db import cached
    from lib.utils import source_manager
    writes, reads = [], []
    settings = shared.search.get_setting
    monkeypatch.setattr(shared.search, 'get_setting', lambda key, default=None:
        True if key == origin + '_enabled' else settings(key, default))
    monkeypatch.setattr(shared.search, 'reconcile_source_selection', source_manager.reconcile_source_selection)
    def factory(*args, **kwargs):
        backend = cached.HybridCache(*args, **kwargs)
        saved_get = backend.get
        def get(key):
            if key == origin + '_user_addons':
                reads.append(key)
                if len(reads) == 2:
                    raise OSError('fixture secret must never reach status')
            return saved_get(key)
        monkeypatch.setattr(backend, 'get', get)
        monkeypatch.setattr(backend, 'set', lambda key, *a, **kw: writes.append(key))
        return backend
    monkeypatch.setattr(shared.search, 'HybridCache', factory)
    session, pump = shared.search._create_source_search({}, 'Fixture', {'tmdb_id':123}, 'tv', 'tv',
        {'season':1, 'episode':1}, False, '', shared.search.SearchVariant.DEFAULT,
        shared.search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    try:
        pump.start(); pump.thread.join(3)
        assert not pump.thread.is_alive() and len(reads) == 2 and writes == [] and shared.calls == []
        assert session.status()['providers']['coordinator']['error'] == 'RuntimeError'
    finally:
        pump.cancel()


@pytest.mark.parametrize('original_control', [False, True], ids=['fixed', 'original-control'])
@pytest.mark.parametrize('origin', ['stremio', 'nuvio'])
def test_reconcile_manifest_failure_is_not_an_empty_configuration(origin, original_control):
    from lib.utils import source_manager
    writes = []
    def broken():
        raise ValueError('manifest could not load')
    reconcile = source_manager.reconcile_source_selection
    if original_control:
        tree = ast.parse(original('addons/plugin.video.bobbi/lib/utils/source_manager.py'))
        names = ('parse_source_selection', 'get_enabled_source_keys', 'reconcile_source_selection')
        scope = dict(vars(source_manager))
        exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                                     and node.name in names], type_ignores=[]), '<original-reconcile>', 'exec'), scope)
        reconcile = scope['reconcile_source_selection']
    kwargs = dict(cache_backend=SimpleNamespace(get=lambda key: None,
        set=lambda key, *a, **kw: writes.append(key)), settings_getter=lambda key: key == origin + '_enabled',
        stremio_addons_getter=broken, nuvio_addons_getter=broken)
    if original_control:
        assert reconcile(**kwargs) == []
        assert writes == ['source_manager_selection', 'source_manager_known_keys']
    else:
        with pytest.raises(ValueError, match='manifest could not load'):
            reconcile(**kwargs, strict=True)
        assert writes == []


@pytest.mark.parametrize('raw,expected', [(None, []), ([], []), ('[]', []),
    (['one', 'two'], ['one', 'two']), ('["one","two"]', ['one', 'two']),
    ('one,two', ['one', 'two']), ('123', ['123']), ('legacy|https://example.invalid/addon',
                                                  ['legacy|https://example.invalid/addon'])])
def test_strict_addon_selection_preserves_json_lists_and_legacy_csv(raw, expected):
    from lib.clients.stremio.constants import decode_selected_ids as stremio
    from lib.clients.nuvio.constants import decode_selected_ids as nuvio
    assert stremio(raw, strict=True) == nuvio(raw, strict=True) == expected


def test_repeated_user_retry_reuses_one_backend_and_closes_it_once(shared, monkeypatch):
    from lib.db import cached
    backends, closed = [], []
    def factory(*args, **kwargs):
        backend = cached.HybridCache(*args, **kwargs)
        backends.append(backend)
        close = backend.close
        def observed_close():
            closed.append(backend)
            close()
        monkeypatch.setattr(backend, 'close', observed_close)
        return backend
    monkeypatch.setattr(shared.search, 'HybridCache', factory)
    session, pump = shared.search._create_source_search({}, 'Fixture', {'tmdb_id':123}, 'tv', 'tv',
        {'season':1, 'episode':1}, False, '', shared.search.SearchVariant.DEFAULT,
        shared.search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    try:
        pump.start(); pump.thread.join(3)
        for _ in range(3):
            assert not pump.thread.is_alive() and pump.retry_failed()
            pump.thread.join(3)
            assert pump.query_result_cache.backend is backends[0]
        assert len(backends) == 1 and closed == []
    finally:
        pump.cancel(); pump.cancel()
    assert closed == backends and pump._pending == 0


def test_actual_search_settings_capture_b_and_retry_never_reloads_a_or_changed_xml(shared, tmp_path, monkeypatch):
    from bobbi_platform import paths
    from lib.utils.kodi import utils
    from lib.utils.clients import utils as clients
    from lib.clients.jackett import Jackett
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    root = tmp_path / 'B'
    profile = root / 'plugin.video.bobbi'
    profile.mkdir(parents=True)
    xml = profile / 'settings.xml'
    def settings(host, key, timeout, packs):
        return '<settings>' + ''.join('<setting id="{}">{}</setting>'.format(k, v) for k, v in {
            'jackett_enabled':'true', 'jackett_host':host, 'jackett_apikey':key,
            'jackett_port':'9117', 'jackett_timeout':timeout, 'include_season_packs':packs,
            'cache_enabled':'true', 'thread_number':'2', 'torrent_enable':'true',
            'prowlarr_enabled':'false', 'stremio_enabled':'false', 'nuvio_enabled':'false',
            'jackgram_enabled':'false', 'jacktookburst_enabled':'false', 'external_scraper_enabled':'false',
            'easynews_enabled':'false'}.items()) + '</settings>'
    xml.write_text(settings('http://b.invalid', 'fixture-b', 17, 'false'), encoding='utf-8')
    properties = {}
    window = SimpleNamespace(getProperty=lambda key: properties.get(key, ''),
        setProperty=properties.__setitem__, clearProperty=lambda key: properties.pop(key, None))
    monkeypatch.setattr(utils, 'Window', lambda _: window)
    window.setProperty('bobbi.settings', '{"jackett_host":"http://a.invalid","jackett_apikey":"fixture-a","jackett_port":"9117"}')
    monkeypatch.setattr(paths, '_translated_profile_root', lambda addon: root / addon)
    monkeypatch.setattr(shared.search, 'capture_settings', utils.capture_settings)
    # Original path through the Window snapshot demonstrably constructs A.
    old_source = ast.parse(original('addons/plugin.video.bobbi/lib/utils/clients/utils.py'))
    old_builder = next(n for n in old_source.body if isinstance(n, ast.FunctionDef) and n.name == 'build_jackett_client')
    space = dict(vars(clients))
    space['get_setting'] = utils.get_setting
    exec(compile(ast.Module(body=[old_builder], type_ignores=[]), '<original-settings-builder>', 'exec'), space)
    stale = space['build_jackett_client']()
    assert stale.host == 'http://a.invalid' and stale.apikey == 'fixture-a'
    stale.session.close()
    captured = []
    def provider(indexer, *args, **kwargs):
        getter = kwargs['settings_getter']
        client = clients.get_client(indexer, settings_getter=getter)
        assert isinstance(client, Jackett)
        captured.append((client.host, client.apikey, client._timeout(), client._setting('include_season_packs')))
        client.session.close()
        return SearchResults([], SearchCompletion(1, failed=1))
    monkeypatch.setattr(shared.search, '_perform_search', provider)
    session, pump = shared.search._create_source_search({}, 'Fixture', {'tmdb_id':123}, 'tv', 'tv',
        {'season':1, 'episode':1}, False, '', shared.search.SearchVariant.DEFAULT,
        shared.search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    # The settings file changes before worker launch; the entry's B snapshot wins.
    xml.write_text(settings('http://changed.invalid', 'fixture-changed', 2, 'true'), encoding='utf-8')
    try:
        pump.start(); pump.thread.join(3)
        assert not pump.thread.is_alive() and pump.retry_failed()
        pump.thread.join(3)
        assert captured == [('http://b.invalid', 'fixture-b', 17, False)] * 2
    finally:
        pump.cancel()
        window.clearProperty('bobbi.settings')


@pytest.mark.parametrize('value,expected', [('false', False), ('FALSE', False), ('true', True),
    ('0', '0'), ('', 'fallback'), (' false ', ' false ')])
@pytest.mark.parametrize('attribute', [False, True], ids=['text', 'value-attribute'])
def test_captured_settings_keep_legacy_value_normalization(tmp_path, value, expected, attribute):
    from lib.utils.kodi import utils
    import xml.etree.ElementTree as ET
    root = ET.Element('settings')
    row = ET.SubElement(root, 'setting', {'id':'fixture'})
    if attribute:
        row.set('value', value)
    else:
        row.text = value
    ET.ElementTree(root).write(tmp_path / 'settings.xml', encoding='utf-8')
    getter = utils.capture_settings(tmp_path, lambda: True)
    assert getter('fixture', 'fallback') == expected
    assert type(getter('fixture', 'fallback')) is type(expected)


def test_missing_profile_settings_uses_declared_defaults_and_bad_integer_stays_invalid(tmp_path):
    from lib.utils.kodi import utils
    getter = utils.capture_settings(tmp_path, lambda: True)
    assert {key:getter(key) for key in ('jackett_timeout','prowlarr_timeout','thread_number',
        'include_season_packs','cache_enabled','cache_expiration','stremio_bypass_addons')} == {
        'jackett_timeout':'30', 'prowlarr_timeout':'25', 'thread_number':'8',
        'include_season_packs':True, 'cache_enabled':True, 'cache_expiration':'24',
        'stremio_bypass_addons':False}
    (tmp_path / 'settings.xml').write_text('<settings><setting id="jackett_timeout">bad</setting></settings>')
    changed = utils.capture_settings(tmp_path, lambda: True)
    with pytest.raises(ValueError):
        int(changed('jackett_timeout'))
    assert getter('jackett_timeout') == '30'


@pytest.mark.parametrize('during_lookup', [False, True])
def test_shared_native_export_root_does_not_authorize_revoked_profile(profiles, during_lookup):
    from copy import deepcopy
    from test_subtitle_external_owner import setup
    owner, native, args, catalog, value, message = setup()
    owner.profile_current = profiles.binding.is_current
    shared_native_root = owner.subtitle_root
    if during_lookup:
        def lookup(_):
            profiles.revoke()
            return deepcopy(value)
        native.external_subtitle = lookup
    else:
        profiles.revoke()
    answer = owner.dispatch(message)
    assert answer['status'] in ('STALE', 'SUBTITLE_SERVICE_UNAVAILABLE')
    assert owner.subtitle_root == shared_native_root
    assert not native.commands
