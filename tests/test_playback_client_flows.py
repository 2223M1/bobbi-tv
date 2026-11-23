"""Real compatibility operations and entry-to-resolution binding propagation."""
import ast
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from bobbi_core import playback_request
from bobbi_platform import playback_client

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons/plugin.video.bobbi'


def functions(relative, names, namespace):
    path = PLUGIN / relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in body} == set(names)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('order', ['legacy-first', 'core-first'])
def test_legacy_operations_capture_once_and_do_not_replace_core_in_either_import_order(order):
    script = '''
import importlib, sys
from types import SimpleNamespace
sys.path[:0] = sys.argv[1:4]
names = ['lib.cinema.playback_request', 'bobbi_core.playback_request']
if sys.argv[4] == 'core-first': names.reverse()
for name in names: importlib.import_module(name)
legacy = importlib.import_module('lib.cinema.playback_request')
core = importlib.import_module('bobbi_core.playback_request')
platform = importlib.import_module('bobbi_platform.playback_client')
assert legacy is not core and legacy.SelectionChanged is core.SelectionChanged
assert legacy.context is core.context and legacy.torrent_file_identity is core.torrent_file_identity
def forbidden(*args, **kwargs): raise AssertionError('escaped to default core transport')
core.call = forbidden
captures, operations, receipt = [], [], {}
request = 'a'*32
snapshot = dict(boot_id='b'*32, epoch=3, desired=dict(request_id=request, cancelled=False, selection_identity='bt:'+'c'*40))
def wire(body, timeout=.3):
    operation = body['operation']
    operations.append(operation)
    if operation == 'snapshot': return snapshot
    if operation == 'select':
        return dict(snapshot, desired=dict(request_id=body['request_id'], cancelled=False))
    if operation == 'bind_file': return dict(bound=True)
    if operation == 'claim_start':
        receipt.update({key: body[key] for key in ('boot_id','epoch','request_id','claim_id','route')})
        receipt.update(file_identity=identity, url_sha256=core.digest(url))
        raise OSError('lost acknowledgement')
    if operation == 'claim_status': return dict(status='CLAIMED', receipt=receipt)
    raise AssertionError(body)
client = core.Client(wire)
def capture():
    captures.append(True)
    return client
platform.capture = capture
identity = core.torrent_file_identity('c'*40, 1, 'movie.mkv', 100)
url = 'http://127.0.0.1:18090/movie'
result = legacy.bind_and_claim(request, identity, url, lambda:False, 'resolved_url')
assert result == dict(boot_id=snapshot['boot_id'],epoch=3,request_id=request,file_identity=identity)
assert captures == [True] and operations == ['snapshot','bind_file','claim_start','claim_status']
operations.clear()
legacy.reserve_ui_entry(dict(selection_policy='exact', url=url))
assert len(captures) == 2 and operations == ['snapshot','select']
operations.clear()
legacy.read_snapshot()
assert len(captures) == 3 and operations == ['snapshot']
ipc = importlib.import_module('lib.cinema.playback_ipc')
assert ipc is not importlib.import_module('bobbi_core.playback_ipc')
assert ipc.call({'operation':'snapshot'}) == snapshot and len(captures) == 4
assert core.call is forbidden
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(PLUGIN),
        str(ROOT / 'addons/script.module.bobbi.core/lib'),
        str(ROOT / 'addons/script.module.bobbi.platform/lib'), order],
        text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_legacy_protection_lane_binds_before_worker_and_never_recaptures(monkeypatch):
    monkeypatch.syspath_prepend(str(PLUGIN))
    legacy = importlib.import_module('lib.cinema.prepared_protection')
    core = importlib.import_module('bobbi_core.prepared_protection')
    calls, captures, observations = [], [], []
    client = playback_request.Client(lambda body, **kw: calls.append(body) or {'protocol': 1, 'playback': None})
    monkeypatch.setattr(playback_client, 'capture', lambda: captures.append(True) or client)
    protection = SimpleNamespace(observe=lambda value, **kw: observations.append(value))
    with pytest.raises(TypeError):
        core.ProtectionLane(protection)
    lane = legacy.ProtectionLane(protection)
    assert captures == [True]
    monkeypatch.setattr(playback_client, 'capture', lambda: pytest.fail('worker recaptured'))
    try:
        lane.tick()
        lane.future.result(timeout=2)
        lane.tick()
        assert calls == [{'operation': 'resource_snapshot'}]
        assert observations == [{'protocol': 1, 'playback': None}]
    finally:
        lane.close()
    assert observations[-1] is None


@pytest.mark.parametrize('entry', ['play_media', 'play_from_pack'])
def test_manual_navigation_entry_passes_one_binding_through_resolve_and_player(monkeypatch, entry):
    monkeypatch.syspath_prepend(str(PLUGIN))
    client, captures, events = object(), [], []
    client = SimpleNamespace(reserve_ui_entry=lambda data: events.append('reserve') or data)
    monkeypatch.setattr(playback_client, 'capture_transport', lambda: captures.append(True) or
        (None, client, lambda action, body, **kw: {'playback_adapter': 'native'}))
    def resolve(data, *, playback_client):
        assert playback_client is client
        json.dumps(data)  # The callable transport must not enter serializable data.
        events.append('resolve')
        return data
    def player(*, playback_client, playback_adapter):
        assert playback_client is client
        assert playback_adapter == 'native'
        return SimpleNamespace(run=lambda **kw: events.append('play'))
    namespace = dict(json=json, notification=lambda *a: pytest.fail('unexpected notification'),
        _reselect_cached_torrent=lambda *a: False, resolve_stremio_playback_url=resolve,
        JacktookPLayer=player)
    functions('lib/navigation.py', [entry], namespace)[entry]({'data': json.dumps({'url': 'fixture'})})
    assert captures == [True] and events == ['reserve', 'resolve', 'play']


def test_stremio_to_torrent_resolution_keeps_client_outside_payload(monkeypatch):
    client, seen = object(), []
    def final(magnet, url, data, *, playback_client):
        assert playback_client is client
        json.dumps(data)
        seen.append((magnet, url))
        return 'plugin://fixture'
    namespace = dict(Any=Any, Dict=Dict, Optional=Optional,
        IndexerType=SimpleNamespace(DIRECT='direct', STREMIO_DEBRID='debrid'),
        Players=SimpleNamespace(JACKTORR='jacktorr', ELEMENTUM='elementum', TORREST='torrest'),
        is_supported_debrid_type=lambda _: False,
        get_setting=lambda key: 'jacktorr' if key == 'torrent_client' else True,
        get_jacktorr_url=final)
    functions('lib/utils/player/utils.py',
        ['resolve_playback_url', 'get_torrent_url', 'get_torrent_url_for_client'], namespace)
    monkeypatch.setitem(sys.modules, 'lib.utils.player.utils', SimpleNamespace(
        resolve_playback_url=namespace['resolve_playback_url']))
    stremio = dict(Any=Any, Dict=Dict, Optional=Optional, canonicalize_stremio_playback_payload=lambda data: data)
    functions('lib/clients/stremio/playback.py', ['resolve_stremio_playback_url'], stremio)
    data = dict(magnet='magnet:?xt=urn:btih:'+'a'*40, url='', selection_policy='exact')
    result = stremio['resolve_stremio_playback_url'](data, playback_client=client)
    assert result['url'] == 'plugin://fixture' and seen == [(data['magnet'], '')]
    assert 'playback_client' not in result


def test_failed_resolution_fallback_keeps_the_original_entry_binding(monkeypatch):
    monkeypatch.syspath_prepend(str(PLUGIN))
    captures, events = [], []
    client = SimpleNamespace(reserve_ui_entry=lambda data: events.append('reserve') or data)
    monkeypatch.setattr(playback_client, 'capture_transport', lambda: captures.append(True) or
        (None, client, lambda action, body, **kw: {'playback_adapter': 'native'}))
    def search(params, *, playback_client):
        assert playback_client is client
        events.append('fallback')
    monkeypatch.setitem(sys.modules, 'lib.search', SimpleNamespace(run_search_entry=search))
    namespace = dict(json=json, notification=lambda *a: None, kodilog=lambda *a: None,
        _reselect_cached_torrent=lambda *a: False,
        _resume_search_params=lambda *a: dict(query='Movie', ids='{"tmdb_id":1}'),
        resolve_stremio_playback_url=lambda data, **kw: None)
    functions('lib/navigation.py', ['play_media'], namespace)['play_media']({'data': '{"url":"fixture"}'})
    assert captures == [True] and events == ['reserve', 'fallback']


@pytest.mark.parametrize('inherited', [None, 'bound-client'])
def test_resume_picker_and_search_entry_do_not_recapture_inherited_failure(monkeypatch, inherited):
    monkeypatch.setattr(playback_client, 'capture', lambda: pytest.fail('inherited entry recaptured'))
    seen = []
    monkeypatch.setitem(sys.modules, 'lib.clients.cinema_ui', SimpleNamespace(is_ui_action=lambda: False))
    namespace = dict(json=json, _CAPTURE_PLAYBACK=object(),
        xbmc=SimpleNamespace(getSkinDir=lambda: 'skin.bobbi.cinema'),
        normalize_tv_data=lambda value: value, safe_json_loads=lambda value: json.loads(value or '{}'),
        _normalize_search_variant=lambda value: value, SearchVariant=SimpleNamespace(DEFAULT='default'),
        _normalize_title_language_mode=lambda value: value, TITLE_LANGUAGE_LOCALIZED_FIRST='localized',
        get_setting=lambda key, default=None: default, set_content_type=lambda *a: None,
        set_watched_title=lambda *a, **kw: None, _preferred_stremio_results=lambda values: [],
        _run_progressive_source_entry=lambda *a, **kw: seen.append(kw['playback_client']))
    functions('lib/search.py', ['run_search_entry'], namespace)
    monkeypatch.setitem(sys.modules, 'lib.search', SimpleNamespace(run_search_entry=namespace['run_search_entry']))
    navigation = dict(json=json, _CAPTURE_PLAYBACK=object(),
        _resume_search_params=lambda *a: dict(query='Movie', ids='{"tmdb_id":1}', mode='movies'))
    functions('lib/navigation.py', ['_open_resume_picker'], navigation)
    assert navigation['_open_resume_picker']({}, {}, playback_client=inherited) is True
    assert seen == [inherited]
