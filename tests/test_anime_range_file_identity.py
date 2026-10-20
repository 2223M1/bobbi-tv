"""Closed technical-tail grammar and the real range producer/selector chain.

The file list below reproduces the public filenames, IDs and lengths captured
in ce-torrent-flip1908-live2.json for 12733bd6... . Catalogue details are an
explicit test fixture, not a claim to replay the device's cached response.
No torrent fetch, backend or native playback runs in these tests.
"""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in ('addons/script.module.bobbi.core/lib', 'addons/plugin.video.bobbi.torrent/lib'):
    sys.path.insert(0, str(ROOT / path))

from bobbi_core import episode_identity
from bobbi_core.anime_range_candidates import check_file_tail, context, eligible
from bobbi_torrent.backend import BackendError
from bobbi_torrent.entry import parse_request
from bobbi_torrent.resolver import select_file

HASH = '12733bd6fadad8406d4cad55606e8734aefa0ef7'
RID = 'd311d0e008d84500b8d87a42e22e68fb'
TITLE = '[SweetSub&LoliHouse][Flip Flappers][01-13][HEVC 10bit][1080P][MKV][CHS&CHT]'
PREFIX = '[SweetSub&LoliHouse] Flip Flappers'
TECH = '[WebRip 1920x1080 HEVC-yuv420p10 AAC]'
LENGTHS = (
    417001, 416918, 411570230, 418861, 418862, 463040960,
    418774, 418715, 544020808, 419507, 419458, 405539241,
    422748, 422722, 437851582, 422914, 422873, 450015376,
    426461, 426432, 351433042, 423338, 423291, 511895100,
    420954, 420882, 440710281, 425258, 425275, 322952272,
    422762, 422767, 348641989, 422951, 422950, 474074532,
    425268, 425275, 433723536, 47296835,
)


def observed_files():
    paths = [f'{PREFIX} {TECH}/{PREFIX} - {episode:02} {TECH}{suffix}'
             for episode in range(1, 14)
             for suffix in ('.SweetSub-SC.ass', '.SweetSub-TC.ass', '.mkv')]
    paths.append(f'{PREFIX} {TECH}/{PREFIX} - fonts(必装字体).rar')
    return [dict(id=index, path=path, length=length)
            for index, (path, length) in enumerate(zip(paths, LENGTHS), 1)]


def producer_request(monkeypatch, selection='bt'):
    # Retain the actual shipped ID/regular episode mapping, not a guessed S1.
    details = dict(id=68272, name='Flip Flappers', original_name='フリップフラッパーズ',
                   first_air_date='2016-10-06', genres=[{'id': 16}])
    range_context = context(details, 68272, 1, 1, 1)
    assert episode_identity.load_mappings()['tmdb_show:68272:s1'] == {
        'anidb:12007:R': {'1-13': '1-13'}}
    assert eligible(TITLE, range_context, 1, 1)
    locator = ('magnet:?xt=urn:btih:' + HASH if selection == 'bt'
               else 'https://example.test/selected.torrent')
    from bobbi_core.playback_request import digest
    identity = 'bt:' + HASH if selection == 'bt' else 'transport:' + digest(locator)
    source = ROOT / 'addons/plugin.video.bobbi/lib/utils/player/utils.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'get_jacktorr_url')
    namespace = dict(Optional=Optional, Dict=Dict, Any=Any, json=json, quote=quote,
        kodilog=lambda *args, **kwargs: None, LOGDEBUG=0,
        summarize_locator_for_log=lambda value: '[locator]',
        is_bobbi_torrent_addon=lambda: True, TorrentException=RuntimeError,
        _jacktorr_movie_binding=lambda data: '',
        _save_jacktorr_playback_metadata=lambda *args: None,
        _get_jacktorr_category=lambda value: 'tv',
        _jacktorr_cached_tv_identity=lambda *args, **kwargs: range_context['catalog'],
        _log_jacktorr_episode_binding=lambda *args: None)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    monkeypatch.setattr('bobbi_torrent.backend.load_config', lambda: {})
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.episode_order',
                        SimpleNamespace(selected_release_binding=lambda *args: None))
    monkeypatch.setitem(sys.modules, 'lib.utils.player.episode_identity', episode_identity)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request',
                        SimpleNamespace(owned_state=lambda rid: {
                            'desired': {'selection_identity': identity}}))
    data = dict(selection_policy='exact', request_id=RID, mode='tv',
        ids={'tmdb_id': 68272}, tv_data={'season': 1, 'episode': 1},
        title='Flip Flappers', source_title=TITLE,
        info_hash=HASH if selection == 'bt' else '',
        require_catalog_episode_binding=True)
    # A pre-existing legacy hash proof must not bypass the range suffix check.
    data['episode_binding'] = episode_identity.bind_selected_episode(data['ids'], data['tv_data'], HASH)
    make = namespace['get_jacktorr_url']
    url = make(locator if selection == 'bt' else '', locator if selection != 'bt' else '', data)
    request = parse_request([url.split('?', 1)[0], '1', '?' + url.split('?', 1)[1]])
    binding = json.loads(request['episode_binding'])
    assert binding['candidate_scope'] == 'unscoped-range-v1'
    assert binding['media_id'] == 'tmdb:68272'
    assert binding['selection_identity'] == identity
    assert request['release_title'] == TITLE
    return request, SimpleNamespace(validate_torrent_resolution=lambda *args: identity)


@pytest.mark.parametrize('selection', ['bt', 'transport'])
def test_observed_40_file_pack_through_actual_range_producer_and_selector(monkeypatch, selection):
    request, protocol = producer_request(monkeypatch, selection)
    files = observed_files()
    assert len(files) == 40 and sum(row['path'].endswith('.mkv') for row in files) == 13
    info = dict(hash=HASH, name=f'{PREFIX} {TECH}', title=TITLE, file_stats=files)
    selected = select_file(info, request, HASH, {}, protocol)
    assert selected == files[2]
    assert selected['id'] == 3 and selected['length'] == 411570230


@pytest.mark.parametrize('token', ['HEVC-yuv420p10', 'AVC-yuv422p10le', 'HEVC-yuv444p12be',
    'yuv420p', 'yuv422p9le', 'yuv444p16be', 'HEVC-10bit', 'AVC-8bits'])
def test_closed_pixel_format_tags_are_technical_metadata(token):
    check_file_tail('[Group] Series - 01 [1080p ' + token + ' AAC].mkv', 2016)


@pytest.mark.parametrize('token', ['HEVC-yuv420p01', 'HEVC-yuv420p11', 'HEVC-yuv999p10',
    'HEVC-yuv420p10E02', 'HEVC-yuv420p10-S02E01', 'HEVC-yuv420p10-Movie',
    'HEVC-yuv420p10-OtherTitle', 'HEVC-yuv420p10-2017', 'yuv420p10leX',
    'HEVC-yuv420p10 OVA', 'HEVC-yuv420p10 Another Work', 'HEVC-yuv420p10 2017'])
def test_pixel_format_never_consumes_unknown_title_episode_year_or_bonus(token):
    with pytest.raises(ValueError):
        check_file_tail('[Group] Series - 01 [1080p ' + token + ' AAC].mkv', 2016)


@pytest.mark.parametrize('mutation,stage', [
    ('wrong_work', 'filename_identity'), ('wrong_year', 'filename_identity'),
    ('unknown_title_tail', 'filename_identity'), ('bonus_directory', 'filename_identity'),
    ('wrong_episode', 'selector'), ('multi_episode', 'selector'), ('duplicate', 'selector')])
def test_observed_pixel_tag_does_not_relax_exact_identity(monkeypatch, mutation, stage):
    request, protocol = producer_request(monkeypatch)
    files = observed_files()
    target = files[2]
    if mutation == 'wrong_work':
        target['path'] = target['path'].replace('Flip Flappers -', 'Another Work -')
    elif mutation == 'wrong_year':
        target['path'] = target['path'].replace('Flappers -', 'Flappers 2017 -')
    elif mutation == 'unknown_title_tail':
        target['path'] = target['path'].replace('AAC]', 'AAC Another Work]')
    elif mutation == 'bonus_directory':
        target['path'] = 'Extras/' + target['path']
    elif mutation == 'wrong_episode':
        target['path'] = target['path'].replace(' - 01 ', ' - 02 ')
    elif mutation == 'multi_episode':
        target['path'] = target['path'].replace(' - 01 ', ' - 01-02 ')
    elif mutation == 'duplicate':
        files.append(dict(target, id=41, path='Copy/' + target['path']))
    with pytest.raises(BackendError) as error:
        select_file(dict(hash=HASH, name=TITLE, file_stats=files), request, HASH, {}, protocol)
    assert error.value.diagnostic['stage'] == stage
