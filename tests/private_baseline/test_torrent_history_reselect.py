"""Run the real history entry without Kodi/import/network side effects."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def navigation(monkeypatch):
    source = ROOT / 'addons/plugin.video.bobbi/lib/navigation.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    names = {'_resume_search_params', '_open_resume_picker', '_reselect_cached_torrent',
             '_resume_failure_still_current', 'play_media'}
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    calls = SimpleNamespace(searches=[], notices=[], reservations=[])
    namespace = dict(json=json, notification=calls.notices.append)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), 'exec'), namespace)
    # Execute the actual progress parser rather than a fixture's guessed value.
    contract = ROOT / 'addons/plugin.video.bobbi/lib/cinema/frontend_contract.py'
    module = ModuleType('lib.cinema.frontend_contract')
    exec(compile(contract.read_text(encoding='utf-8'), str(contract), 'exec'), module.__dict__)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    search = ModuleType('lib.search')
    search.run_search_entry = calls.searches.append
    monkeypatch.setitem(sys.modules, search.__name__, search)
    request = ModuleType('lib.cinema.playback_request')
    def reserve(data):
        calls.reservations.append(data)
        raise AssertionError('A stored one-use child URL must never be reserved or opened')
    request.reserve_ui_entry = reserve
    monkeypatch.setitem(sys.modules, request.__name__, request)
    ipc = ModuleType('lib.cinema.playback_ipc')
    ipc.call = lambda message: (_ for _ in ()).throw(AssertionError('Unexpected authority mutation/read'))
    monkeypatch.setitem(sys.modules, ipc.__name__, ipc)
    return namespace, calls


def stored(**changes):
    data = dict(url='plugin://plugin.video.bobbi.torrent/play_magnet?request_id=old&movie_binding=old',
                selection_policy='exact', request_id='a' * 32, title='Original work',
                mode='movies', ids={'tmdb_id': 60243}, progress=37.25)
    data.update(changes)
    return data


@pytest.mark.parametrize('continuing', [True, False])
@pytest.mark.parametrize('addon', ['plugin.video.bobbi.torrent', 'plugin.video.jacktorr'])
def test_cached_child_reselects_without_replaying_or_mutating_history(navigation, continuing, addon):
    api, calls = navigation
    data = stored(url='plugin://' + addon + '/play_url?url=https%3A%2F%2Fexample.test%2Fa.torrent&movie_binding=old')
    original = deepcopy(data)
    params = dict(data=json.dumps(data), continue_watching='true' if continuing else 'false')
    api['play_media'](params)
    assert not calls.reservations and not calls.notices
    assert len(calls.searches) == 1
    search = calls.searches[0]
    assert search['force_select'] is True and search['rescrape'] is True
    assert search['_bobi_resume_percent'] == 37.25
    assert json.loads(search['ids']) == data['ids']
    assert not {'url', 'request_id', 'movie_binding', 'episode_binding'}.intersection(search)
    assert data == original and json.loads(params['data']) == original


def test_tv_identity_and_explicit_start_over_are_preserved(navigation):
    api, calls = navigation
    data = stored(mode='tv', tv_data={'season': 0, 'episode': 2})
    api['play_media'](dict(data=json.dumps(data), continue_watching='true', start_over='true'))
    search = calls.searches[0]
    assert json.loads(search['tv_data']) == {'season': 0, 'episode': 2}
    assert search['_bobi_start_over'] is True and '_bobi_resume_percent' not in search
    assert data['progress'] == 37.25


@pytest.mark.parametrize('changes', [
    {'ids': {}}, {'ids': {'tmdb_id': True}}, {'ids': {'tmdb_id': '0'}},
    {'ids': {'imdb_id': 'tt1832382'}}, {'title': ''}, {'mode': ''},
    {'mode': 'tv'}, {'mode': 'tv', 'tv_data': {'season': 1, 'episode': False}},
    {'mode': 'tv', 'tv_data': {'season': 1, 'episode': 0}},
])
def test_incomplete_identity_reports_without_guessing_or_reserving(navigation, changes):
    api, calls = navigation
    data = stored(**changes)
    api['play_media'](dict(data=json.dumps(data), continue_watching='true'))
    assert len(calls.notices) == 1
    assert not calls.searches and not calls.reservations


@pytest.mark.parametrize('url', ['https://example.test/video.mkv',
    'plugin://plugin.video.youtube/play?video_id=example', 'plugin://plugin.video.bobbi.torrent.other/play'])
def test_unrelated_playback_routes_are_not_intercepted(navigation, url):
    api, calls = navigation
    assert api['_reselect_cached_torrent'](stored(url=url), {}) is False
    assert not calls.notices and not calls.searches


@pytest.mark.parametrize('same', [True, False])
def test_bt_failure_recheck_uses_read_only_helper_not_incomplete_parent_context(navigation, same):
    api, _ = navigation
    receipt = {'request_id': 'a' * 32, 'file_identity': 'bound-file'}
    original = dict(boot_id='boot', epoch=2, request_id='a' * 32)
    reads = []
    player = SimpleNamespace(_startup_failed_for_reselect=True, _start_notified=False,
        _was_superseded=False, _startup_failure_receipt=receipt, _owner_context=deepcopy(original),
        _read_startup_failure=lambda: reads.append(True) or (receipt if same else None))
    assert api['_resume_failure_still_current'](player, stored()) is same
    assert reads == [True] and player._owner_context == original


def test_superseded_failure_never_reopens_picker(navigation):
    api, _ = navigation
    player = SimpleNamespace(_startup_failed_for_reselect=True, _start_notified=False,
        _was_superseded=True, _read_startup_failure=lambda: pytest.fail('Superseded read'))
    assert api['_resume_failure_still_current'](player, stored()) is False
