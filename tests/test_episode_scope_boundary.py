"""Synthetic scope regressions: no provider, torrent or playback calls."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'plugin.video.bobbi.torrent'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))
from bobbi_core import episode_identity
from bobbi_core.candidate_titles import matches
from bobbi_torrent.backend import BackendError
from bobbi_torrent.entry import parse_request
from bobbi_torrent.resolver import select_file, manual_candidates

HASH, RID = 'a' * 40, 'b' * 32
CATALOG = dict(tmdb_id=1429, aliases=['进击的巨人', '進擊的巨人', 'Shingeki no Kyojin', 'Attack on Titan'], year=2013)


@pytest.mark.parametrize('packaging', ['BD Remux', 'BDREMUX', 'Remux'])
def test_remux_is_packaging_not_an_unrecognized_work_qualifier(packaging):
    from bobbi_core.episode_scope import release_scope
    from episode_request_fixture import produced_request
    title = ('[Flugel] Heavenly Delusion S01 (%s 1080p AVC FLAC) '
             '[Multi Audio] | Tengoku Daimakyou') % packaging
    details = dict(id=208891, name='Heavenly Delusion', original_name='天国大魔境',
        first_air_date='2023-04-01', seasons=[dict(season_number=1, air_date='2023-04-01')],
        alternative_titles={'results': [dict(title='Tengoku Daimakyou', type='Romaji')]})
    query = produced_request(RID, HASH, 1, 1, title, details=details)
    file = dict(id=1, path='Heavenly Delusion S01E01.mkv', length=1000000)
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    assert release_scope(title, ['Heavenly Delusion', 'Tengoku Daimakyou'], 1, 2023) == 'matched'
    assert select_file(dict(name=title, file_stats=[file]), query, HASH, {}, protocol) == file


@pytest.mark.parametrize('suffix,expected', [
    ('RemuxUnknown', 'unknown'), ('Remux Unknown Arc', 'unknown'),
    ('Remux OVA', 'conflict'), ('BDRemux S02', 'conflict'),
    ('Remux 2024', 'conflict'),
])
def test_remux_grammar_does_not_consume_unknown_work_or_season(suffix, expected):
    from bobbi_core.episode_scope import release_scope
    assert release_scope('Heavenly Delusion S01 ' + suffix,
                         ['Heavenly Delusion'], 1, 2023) == expected


@pytest.mark.parametrize('base,suffix,season,expected', [
    ('Example Show', ' The Final Season', 1, 'unknown'),
    ('Example Show', ' Season 2', 1, 'conflict'),
    ('Example Show', ' Season 2', 2, 'matched'),
    ('Example Show', ' OVA', 1, 'conflict'),
    ('Example Show', ' OVA', 0, 'matched'),
    ('示例作品', '最终季', 1, 'unknown'),
])
def test_work_alias_does_not_erase_a_more_specific_season_or_type(base, suffix, season, expected):
    from bobbi_core.episode_scope import release_scope
    assert release_scope(base + suffix + ' - 01 [1080p]', [base, base + suffix], season) == expected


def test_punctuation_alias_is_not_work_and_named_canonical_special_remains_work():
    from bobbi_core.episode_scope import release_scope
    assert release_scope('S01E01 [1080p]', ['!!!'], 1) != 'matched'
    assert release_scope('The Special Show S01E01', ['The Special Show'], 1) == 'matched'
    assert release_scope('Example Story S01E01', ['Example', 'Example Story'], 1) == 'matched'


def request(season=1, episode=1, style='catalog', numbering=None):
    ids, tv = {'tmdb_id': 1429}, dict(season=season, episode=episode)
    identity = 'bt:' + HASH
    if style == 'v1':
        locator = 'https://fixture.invalid/selected.torrent'
        identity = 'transport:' + hashlib.sha256(locator.encode()).hexdigest()
        proof = episode_identity.bind_transport_episode(ids, tv, RID, identity, locator, catalog=CATALOG)
    else:
        legacy = numbering or episode_identity.bind_selected_episode(ids, tv, HASH)
        proof = legacy if style == 'legacy' else episode_identity.bind_catalog_episode(
            ids, tv, RID, identity, HASH, CATALOG, legacy)
    return dict(request_id=RID, season=str(season), episode=str(episode),
                episode_binding=json.dumps(proof) if proof else ''), SimpleNamespace(
                    validate_torrent_resolution=lambda *args: identity)


def choose(title, paths, season=1, episode=1, style='catalog', numbering=None):
    query, protocol = request(season, episode, style, numbering)
    query['release_title'] = title
    info = dict(name=title, file_stats=[dict(id=i, path=p, length=1000000) for i, p in enumerate(paths, 1)])
    return select_file(info, query, HASH, {}, protocol)


@pytest.mark.parametrize('style', ['catalog', 'v1', 'legacy'])
@pytest.mark.parametrize('suffix', ['The Final Season', 'Kuinaki Sentaku', 'Unknown Arc', '最终季', 'OVA'])
@pytest.mark.parametrize('location', ['release', 'directory', 'basename'])
def test_unknown_or_bonus_scope_never_automatically_becomes_regular_s1(style, suffix, location):
    title = 'Shingeki no Kyojin - 01 [1080p]'
    path = '[Group] Shingeki no Kyojin - 01 [1080p].mkv'
    scoped = 'Shingeki no Kyojin ' + suffix
    if location == 'release':
        title = '进击的巨人 / ' + scoped + ' - 01 [1080p]'
    elif location == 'directory':
        path = scoped + '/' + path
    else:
        path = path.replace('Shingeki no Kyojin', scoped)
    with pytest.raises(BackendError):
        choose(title, [path], style=style)


@pytest.mark.parametrize('style', ['catalog', 'v1'])
def test_catalogue_proved_first_season_weak_number_remains_automatic(style):
    path = '[Group] Shingeki no Kyojin - 01 [1080p].mkv'
    assert choose('进击的巨人 / Shingeki no Kyojin - 01 [1080p]', [path], style=style)['path'] == path


def test_legacy_mapping_is_only_manual_and_retains_no_automatic_authority():
    query, protocol = request(style='legacy')
    path = '[Group] Shingeki no Kyojin - 01 [1080p].mkv'
    query['release_title'] = 'Shingeki no Kyojin - 01'
    file = dict(id=1, path=path, length=1000000)
    info = dict(name=query['release_title'], file_stats=[file])
    with pytest.raises(BackendError) as result:
        select_file(info, query, HASH, {}, protocol)
    assert result.value.category == 'target_unresolved'
    assert manual_candidates(info, query, HASH, {}, protocol) == [file]


@pytest.mark.parametrize('season', [2, 3, 4])
def test_explicit_later_seasons_remain_automatic_without_an_s1_mapping(season):
    path = 'Shingeki no Kyojin S%02dE01 [1080p].mkv' % season
    assert choose('Shingeki no Kyojin S%02d' % season, [path], season=season)['path'] == path


def test_existing_continuous_number_mapper_survives_catalogue_envelope():
    numbering = dict(media_id='tmdb:1429', season=2, episode=1, absolute_episode=26,
                     source_info_hash=HASH, provenance='tmdb-continuous-order:fixture')
    path = 'Shingeki no Kyojin S02/Shingeki no Kyojin - 26 [1080p].mkv'
    assert choose('Shingeki no Kyojin S02', [path], season=2, numbering=numbering)['path'] == path


def test_covering_multiseason_bonus_pack_selects_the_regular_branch():
    title = 'Shingeki no Kyojin S01-S04 + OVA [1080p]'
    root = title + '/'
    valid = root + 'S01/Shingeki no Kyojin - 01 [1080p].mkv'
    files = [root + 'OVA/Shingeki no Kyojin - 01 [1080p].mkv', valid,
             root + 'S02/Shingeki no Kyojin - 01 [1080p].mkv']
    assert choose(title, files)['path'] == valid
    assert matches(title, CATALOG['aliases'], 'tv', 1)


def test_ordinary_strong_episode_with_technical_group_suffix_remains_automatic():
    title = 'Shingeki.no.Kyojin.S02E01.1080p.WEB-DL.H264-Group'
    assert choose(title, [title + '.mkv'], season=2)['path'] == title + '.mkv'


def test_explicitly_targeted_special_remains_selectable():
    path = 'Shingeki no Kyojin OVA S00E01 [1080p].mkv'
    assert choose('Shingeki no Kyojin S00E01', [path], season=0)['path'] == path


@pytest.mark.parametrize('suffix', ['The Final Season', 'Kuinaki Sentaku', 'Unlisted Arc', 'OVA'])
def test_bilingual_alias_segment_does_not_hide_conflicting_scope_on_a_card(suffix):
    assert not matches('进击的巨人 / Shingeki no Kyojin ' + suffix + ' - 01 [1080p]', CATALOG['aliases'], 'tv', 1)


def test_existing_chinese_episode_grammar_still_checks_the_complete_marker():
    assert matches('[Group] 进击的巨人 S01E01[第01话][1080p]', CATALOG['aliases'], 'tv', 1)
    assert not matches('[Group] 进击的巨人 S01E01[第02话][1080p]', CATALOG['aliases'], 'tv', 1)


def test_catalogue_punctuation_is_not_an_unrecognized_work_suffix():
    assert matches('[Group] Keep Your Hands Off Eizouken! S01E01 [1080p]',
                   ['Keep Your Hands Off Eizouken!'], 'tv', 1)


def test_actual_cached_season_air_date_supplies_independent_later_year_context():
    from episode_request_fixture import produced_request
    query = produced_request(RID, HASH, 2, 1, 'Series S02', details=dict(id=1, name='Series',
        original_name='Series', first_air_date='2013-01-01', seasons=[
            dict(season_number=1, air_date='2013-01-01'), dict(season_number=2, air_date='2017-01-01')]))
    proof = json.loads(query['episode_binding'])
    assert proof['catalog_year'] == 2013 and proof['catalog_season_year'] == 2017
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *a: 'bt:' + HASH)
    file = dict(id=1, path='Series.2017.S02E01.1080p.mkv', length=1000000)
    assert select_file(dict(name='Series S02', file_stats=[file]), query, HASH, {}, protocol) == file
    with pytest.raises(BackendError):
        select_file(dict(name='Series S02', file_stats=[dict(file, path=file['path'].replace('2017', '2018'))]),
                    query, HASH, {}, protocol)


@pytest.mark.parametrize('catalog,season,title', [
    (CATALOG, 1, 'Shingeki no Kyojin - 01 [1080p]'),
    (CATALOG, 2, 'Shingeki no Kyojin S02E01 [1080p]'),
    (dict(tmdb_id=987654, aliases=['Ordinary Drama'], year=2026), 3, 'Ordinary Drama S03E01 [1080p]')])
def test_real_producer_upgrades_existing_hash_numbering_using_cached_catalogue(monkeypatch, catalog, season, title):
    source = ROOT / 'addons/plugin.video.bobbi/lib/utils/player/utils.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_jacktorr_url')
    calls = []
    namespace = dict(Optional=Optional, Dict=Dict, Any=Any, json=json, quote=quote,
        kodilog=lambda *a, **k: None, LOGDEBUG=0, summarize_locator_for_log=lambda x: '[locator]',
        is_bobbi_torrent_addon=lambda: True, TorrentException=RuntimeError,
        _jacktorr_movie_binding=lambda data: '', _save_jacktorr_playback_metadata=lambda *a: None,
        _get_jacktorr_category=lambda mode: 'tv', _log_jacktorr_episode_binding=lambda *a: None,
        _jacktorr_cached_tv_identity=lambda *a, **k: calls.append('cache') or catalog)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    monkeypatch.setattr('bobbi_torrent.backend.load_config', lambda: {})
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.episode_order', SimpleNamespace(selected_release_binding=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'lib.utils.player.episode_identity', episode_identity)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', SimpleNamespace(
        owned_state=lambda rid: {'desired': {'selection_identity': 'bt:' + HASH}}))
    ids, tv = {'tmdb_id': catalog['tmdb_id']}, dict(season=season, episode=1)
    data = dict(ids=ids, tv_data=tv, selection_policy='exact', request_id=RID, mode='tv',
        info_hash=HASH, source_title=title,
        episode_binding=episode_identity.bind_selected_episode(ids, tv, HASH))
    url = namespace['get_jacktorr_url']('magnet:?xt=urn:btih:' + HASH, '', data)
    query = parse_request([url.split('?', 1)[0], '1', '?' + url.split('?', 1)[1]])
    proof = json.loads(query['episode_binding'])
    assert calls == ['cache'] and proof['version'] == 2
    assert proof['numbering'] == data['episode_binding']
    assert proof['selection_identity'] == 'bt:' + HASH
    file = dict(id=1, path=title + '.mkv', length=1000000)
    assert select_file(dict(name=data['source_title'], file_stats=[file]), query, HASH, {},
        SimpleNamespace(validate_torrent_resolution=lambda *a: 'bt:' + HASH)) == file


@pytest.mark.parametrize('field,value', [('request_id', 'c'*32), ('selection_identity', 'bt:'+'c'*40),
    ('season', 2), ('episode', 2), ('catalog_aliases', []), ('media_id', 'tmdb:999')])
def test_catalogue_envelope_cannot_cross_request_selection_or_episode(field, value):
    query, protocol = request()
    proof = json.loads(query['episode_binding'])
    proof[field] = value
    query['episode_binding'] = json.dumps(proof)
    with pytest.raises(BackendError) as result:
        select_file(dict(file_stats=[dict(id=1, path='Shingeki no Kyojin - 01.mkv', length=1000)]),
                    query, HASH, {}, protocol)
    assert result.value.category == 'invalid_binding'


@pytest.mark.parametrize('style,evidence', [('catalog', 'AUTO_VERIFIED_FILE'), ('legacy', 'USER_CONFIRMED_FILE')])
def test_real_resolver_only_automatic_catalogue_scope_can_seed_preparation(style, evidence):
    from bobbi_torrent.resolver import Resolver
    from bobbi_torrent.backend import Backend
    from test_bobbi_torrent_adapter import Clock, FakeOwner, Session, Response, config
    clock = Clock()
    owner = FakeOwner(clock, selected='bt:' + HASH)
    owner.request_id = RID
    def resolved(request_id, locator, info_hash, verified):
        assert request_id == RID and info_hash == verified == HASH
        return dict(selection_identity='bt:' + HASH, info_hash=HASH)
    owner.protocol.resolve_torrent = resolved
    choices = []
    owner.choose_file = lambda rows: choices.append(rows) or rows[0]
    query, _ = request(style=style)
    query.update(action='play_magnet', selection_policy='exact', magnet='magnet:?xt=urn:btih:' + HASH,
                 release_title='Shingeki no Kyojin - 01 [1080p]')
    file = dict(id=1, path='Shingeki no Kyojin - 01 [1080p].mkv', length=1000000)
    info = dict(hash=HASH, name=query['release_title'], file_stats=[file], preloaded_bytes=100, preload_size=100)
    responses = [Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(info)]
    if style == 'legacy':
        responses.append(Response(info))
    responses += [Response(b''), Response(info)]
    session = Session(responses)
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(query)
    assert result['file'] == file and result['file_evidence'] == evidence
    assert bool(owner.targets) == (style == 'catalog')
    assert bool(choices) == (style == 'legacy')


@pytest.mark.parametrize('catalog,evidence', [(CATALOG, 'AUTO_VERIFIED_FILE'), (None, 'USER_CONFIRMED_FILE')])
def test_portable_boundary_uses_the_same_cached_catalogue_scope(monkeypatch, catalog, evidence):
    source_path = ROOT / 'addons/plugin.video.bobbi/lib/portable.py'
    tree = ast.parse(source_path.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'resolve_torrent')
    file = SimpleNamespace(id=1, path='Shingeki no Kyojin - 01 [1080p].mkv', size=1000000)
    choices = []
    class Client:
        def select_source(self, info_hash, choose_file, **kwargs):
            assert info_hash == HASH
            assert choose_file([file]) == file
            return dict(info_hash=HASH, file_id=1, file_path=file.path, url='http://127.0.0.1/fixture')
    progress = SimpleNamespace(create=lambda *a: None, close=lambda: None, iscanceled=lambda: False)
    namespace = dict(local_client=Client,
        selected_magnet=lambda *a: (HASH, 'magnet:?xt=urn:btih:' + HASH),
        selected_identity=lambda value: value,
        xbmcgui=SimpleNamespace(DialogProgress=lambda: progress,
            Dialog=lambda: SimpleNamespace(select=lambda *a: choices.append(a) or 0)))
    monkeypatch.setitem(sys.modules, 'lib.utils.player.utils', SimpleNamespace(
        _jacktorr_cached_tv_identity=lambda *a: catalog))
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), 'exec'), namespace)
    ids, tv = {'tmdb_id': 1429}, dict(season=1, episode=1)
    info = dict(ids=ids, tv_data=tv, request_id=RID, mode='tv',
                episode_binding=episode_identity.bind_selected_episode(ids, tv, HASH))
    source = SimpleNamespace(infoHash=HASH, title='Shingeki no Kyojin - 01 [1080p]', url='', guid='')
    _, result = namespace['resolve_torrent'](source, lambda: True, info)
    assert result['file_evidence'] == evidence
    assert bool(choices) == (catalog is None)
