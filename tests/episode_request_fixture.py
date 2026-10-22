"""Synthetic cached TMDb detail -> real producer -> parsed request fixture.

This does not hand-author an episode envelope. The production cache reader,
detail validator, catalogue extractor, request producer and plugin parser run.
Only local environment/cache/ownership/backend readiness are supplied by tests;
no provider or device is contacted.
"""
import ast
import builtins
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _producer_code():
    source = ROOT / 'addons/plugin.video.bobbi/lib/utils/player/utils.py'
    definitions = [n for n in ast.parse(source.read_text(encoding='utf-8')).body
        if isinstance(n, ast.FunctionDef) and n.name in ('_jacktorr_cached_tv_identity', 'get_jacktorr_url')]
    return compile(ast.Module(body=definitions, type_ignores=[]), str(source), 'exec')


@lru_cache(maxsize=1)
def _detail_cache():
    source = ROOT / 'addons/plugin.video.bobbi/lib/clients/tmdb/detail_cache.py'
    spec = importlib.util.spec_from_file_location('episode_fixture_detail_cache', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def produced_request(request_id, info_hash, season, episode, release_title,
                     locator=None, action='play_magnet', details=None):
    from bobbi_core import episode_identity
    from bobbi_core.playback_request import digest
    from bobbi_torrent.entry import parse_request
    details = details or dict(id=1, name='Series', original_name='Series', first_air_date='2020-01-01',
                             seasons=[dict(season_number=int(season), air_date='2020-01-01')])
    identifier = details['id']
    locator = locator or 'magnet:?xt=urn:btih:' + info_hash
    selection = 'bt:' + info_hash if action == 'play_magnet' else 'transport:' + digest(locator)
    cache_keys = {'am6b_details283|' + json.dumps(['tv_details', {'id': value}, 'zh-CN'], sort_keys=True)
                  for value in (identifier, str(identifier))}
    cache_reads = []
    def cached(key):
        assert key in cache_keys
        cache_reads.append(key)
        return dict(fetched=time.time(), data=details, tv_aliases_requested=True)
    def owned(request):
        assert request == request_id
        return {'desired': {'selection_identity': selection}}
    namespace = dict(Optional=Optional, Dict=Dict, Any=Any, json=json, re=re, quote=quote,
        cache=SimpleNamespace(get=cached), kodilog=lambda *a, **k: None, LOGDEBUG=0,
        summarize_locator_for_log=lambda value: '[synthetic fixture locator]',
        is_bobbi_torrent_addon=lambda: True, TorrentException=RuntimeError,
        _jacktorr_movie_binding=lambda data: '', _save_jacktorr_playback_metadata=lambda *a: None,
        _get_jacktorr_category=lambda mode: 'tv', _log_jacktorr_episode_binding=lambda *a: None)
    modules = {
        'bobbi_torrent.backend': SimpleNamespace(load_config=lambda: {}),
        'lib.clients.tmdb.detail_cache': _detail_cache(),
        'lib.api.tmdbv3api.as_obj': SimpleNamespace(AsObj=type('FixtureAsObj', (), {})),
        'lib.api.tmdbv3api.tmdb': SimpleNamespace(TMDb=lambda: SimpleNamespace(language='zh-CN')),
        'lib.clients.tmdb.episode_order': SimpleNamespace(selected_release_binding=lambda *a: None),
        'lib.utils.player.episode_identity': episode_identity,
        'lib.cinema.playback_request': SimpleNamespace(owned_state=owned),
    }
    data = dict(selection_policy='exact', request_id=request_id, mode='tv', title=details['name'],
        ids={'tmdb_id': identifier}, tv_data=dict(season=season, episode=episode),
        info_hash=info_hash if action == 'play_magnet' else '', source_title=release_title)
    def fixture_import(name, globals=None, locals=None, fromlist=(), level=0):
        return modules[name] if name in modules else builtins.__import__(name, globals, locals, fromlist, level)
    # Limit injection to these compiled functions; concurrent lifecycle tests
    # keep their own imports and backend objects untouched.
    namespace['__builtins__'] = dict(vars(builtins), __import__=fixture_import)
    exec(_producer_code(), namespace)
    url = namespace['get_jacktorr_url'](locator if action == 'play_magnet' else '',
                                        locator if action != 'play_magnet' else '', data)
    assert len(cache_reads) == 2
    request = parse_request([url.split('?', 1)[0], '1', '?' + url.split('?', 1)[1]])
    assert json.loads(request['episode_binding'])['version'] == 2
    return request
