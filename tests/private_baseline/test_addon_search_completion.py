"""Stremio and Nuvio share terminal receipts, including partial/retry state."""
import json
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest
from requests.exceptions import ReadTimeout

from bobbi_core.search_completion import SearchCompletion, SearchResults, provider_failed
from lib.clients.stremio import addon_client
from lib import search


def addon(origin='stremio', supported=True):
    return SimpleNamespace(transport_name=origin, transport_url='',
        manifest=SimpleNamespace(id='org.fixture', name='Fixture'),
        isSupported=lambda *a: supported, url=lambda: 'https://fixture.invalid', key=lambda: 'fixture')


@pytest.fixture
def client(monkeypatch):
    state = SimpleNamespace(data=dict(streams=[]), status=200, error=None, cache=None,
                            calls=[], writes=[], parsed=[SimpleNamespace(title='good')])
    backend = SimpleNamespace(get=lambda *a: state.cache, set=lambda *a: state.writes.append(a))
    value = addon_client.StremioAddonClient(addon(), cache_backend=backend,
        settings_getter=lambda key, default=None: 1)
    value.addon, value.display_name = addon(), 'Fixture'
    def get(*args, **kwargs):
        state.calls.append(args)
        if state.error:
            raise state.error
        return SimpleNamespace(status_code=state.status, json=lambda: state.data, headers={})
    value.session = SimpleNamespace(get=get)
    value.parse_response = lambda data: state.parsed if data['streams'] else []
    state.value = value
    return state


@pytest.mark.parametrize('origin', ['stremio', 'nuvio'])
@pytest.mark.parametrize('failure,expected', [('http', 'FAILED'), ('json', 'FAILED'),
                                           ('schema', 'FAILED'), ('timeout', 'TIMEOUT')])
def test_transport_and_payload_failures_are_retryable_not_successful_empty(client, origin, failure, expected):
    client.value.addon = addon(origin)
    if failure == 'http': client.status = 503
    if failure == 'json': client.error = ValueError('private upstream payload')
    if failure == 'schema': client.data = {'streams': 'not a list'}
    if failure == 'timeout': client.error = ReadTimeout('private locator')
    result = client.value.search('tt42', 'movies', 'movie', None, None)
    assert isinstance(result, SearchResults) and not result
    assert result.completion.state == expected and result.completion.planned == 1
    assert provider_failed(dict(state=result.completion.state, completion=vars(result.completion)))
    assert client.writes == []


def test_successful_empty_is_distinct_from_failure_and_valid_success_can_be_cached(client):
    result = client.value.search('tt42', 'movies', 'movie', None, None)
    assert result == [] and result.completion == SearchCompletion(1, succeeded=1)
    assert len(client.writes) == 1
    client.data = dict(streams=[dict(url='https://fixture.invalid/one')])
    result = client.value.search('tt42', 'movies', 'movie', None, None)
    assert result == client.parsed and result.completion.complete


def test_corrupt_cached_payload_does_not_poison_successful_empty_cache(client):
    client.cache = {'broken': True}
    result = client.value.search('tt42', 'movies', 'movie', None, None)
    assert len(client.calls) == 1 and result.completion == SearchCompletion(1, succeeded=1)


def test_unsupported_addon_performs_no_query_and_fabricates_no_success(client):
    client.value.addon = addon(supported=False)
    result = client.value.search('tt42', 'movies', 'movie', None, None)
    assert result.completion == SearchCompletion() and client.calls == []


@pytest.mark.parametrize('fault', [OSError('failed'), ReadTimeout('timeout'),
    SearchResults([], SearchCompletion(1, failed=1))])
def test_coordinator_preserves_successful_siblings_and_partial_retry_receipt(monkeypatch, fault):
    good, bad = addon(), addon('nuvio')
    monkeypatch.setattr(search, 'get_selected_stream_addons', lambda: [good, bad])
    def make(value):
        def execute(*args):
            if value is bad:
                if isinstance(fault, Exception): raise fault
                return fault
            return SearchResults(['good'], SearchCompletion(1, succeeded=1))
        return SimpleNamespace(search=execute)
    monkeypatch.setattr(addon_client, 'StremioAddonClient', make)
    result = search._perform_search(search.Indexer.STREMIO, None,
        dict(imdb_id='tt42'), 'movies', 'movie', None, None, show_dialog=False)
    assert result == ['good'] and result.completion.state == 'PARTIAL'
    assert result.completion.planned == 2 and result.completion.succeeded == 1
    assert provider_failed(dict(state='PARTIAL', completion=vars(result.completion)))


def test_all_failed_and_no_addons_have_different_receipts(monkeypatch):
    monkeypatch.setattr(search, 'notification', lambda *a: None)
    monkeypatch.setattr(search, 'get_selected_stream_addons', lambda: [])
    params = (search.Indexer.STREMIO, None, dict(imdb_id='tt42'), 'movies', 'movie', None, None)
    assert search._perform_search(*params, show_dialog=False).completion == SearchCompletion()
    monkeypatch.setattr(search, 'get_selected_stream_addons', lambda: [addon()])
    monkeypatch.setattr(addon_client, 'StremioAddonClient', lambda *a:
        SimpleNamespace(search=lambda *a: SearchResults([], SearchCompletion(1, failed=1))))
    result = search._perform_search(*params, show_dialog=False)
    assert result.completion.state == 'FAILED' and result.completion.failed == 1


def test_real_coordinator_retry_skips_successful_sibling_and_keeps_its_card(monkeypatch, tmp_path):
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_core.search_admission import try_acquire
    from bobbi_core.source_list_session import SourceListSession
    from bobbi_core.provider_cache import ProviderResultCache
    from lib.domain.torrent import TorrentStream
    good, bad = addon(), addon('nuvio')
    calls, stored, failed = [], {}, [True]
    def make(value):
        def execute(*args):
            name = 'good' if value is good else 'bad'
            calls.append(name)
            if value is bad and failed[0]:
                return SearchResults([], SearchCompletion(1, failed=1))
            return SearchResults([TorrentStream(title=name, type='Direct', indexer='Stremio',
                url='https://fixture.invalid/' + name)], SearchCompletion(1, succeeded=1))
        return SimpleNamespace(search=execute)
    monkeypatch.setattr(addon_client, 'StremioAddonClient', make)
    def setup(manager):
        for name, value in [('good', good), ('bad', bad)]:
            manager.submit_task(name, search.Indexer.STREMIO, search._perform_search,
                search.Indexer.STREMIO, None, dict(imdb_id='tt42'), 'movies', 'movie', None, None,
                show_dialog=False, scoped_addon_url=value.url(), addon_override=value)
    result_cache = ProviderResultCache(SimpleNamespace(get=stored.get,
        set=lambda key, value, ttl: stored.__setitem__(key, value)), 'fixture', hours=1)
    session = SourceListSession({}, lambda rows: rows)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, budget=2, result_cache=result_cache,
                             admission=lambda: try_acquire(tmp_path / 'search-admission'))
    pump.start(); pump.thread.join(3)
    assert not pump.thread.is_alive()
    assert sorted(calls) == ['bad', 'good'] and len(session.entries) == 1
    assert len(pump.retry_candidates()) == 1
    retained_key = next(iter(session.entries))
    failed[0] = False
    assert pump.retry_failed()
    pump.thread.join(3)
    assert not pump.thread.is_alive()
    assert calls.count('good') == 1 and calls.count('bad') == 2
    assert len(session.entries) == 2 and retained_key in session.entries
    assert not pump.retry_candidates()
    assert all(row['state'] == 'COMPLETE' for row in session.status()['providers'].values())


@pytest.mark.parametrize('tv_data', [None, {}, {'season': 2}, {'episode': 1},
                                   {'season': -1, 'episode': 2}, {'season': 1, 'episode': 0}])
def test_general_tv_search_entry_redirects_before_quickplay_or_provider_queries(monkeypatch, tv_data):
    from lib.utils.kodi import utils
    commands = []
    monkeypatch.setattr(utils, 'execute_builtin', commands.append)
    monkeypatch.setattr(search, '_handle_super_quick_play', lambda *a: pytest.fail('no implicit S1E1'))
    monkeypatch.setattr(search, '_run_progressive_source_entry', lambda *a, **kw: pytest.fail('no source queries'))
    search.run_search_entry(dict(mode='tv', ids=json.dumps(dict(tmdb_id='42')), tv_data=json.dumps(tv_data)))
    command = commands[0]
    params = dict(parse_qsl(urlsplit(command.removeprefix('ActivateWindow(Videos,').removesuffix(',return)')).query))
    assert params['action'] == 'show_seasons_details'
    assert json.loads(params['ids']) == dict(tmdb_id='42')
