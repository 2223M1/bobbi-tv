"""Metadata candidates and review plans never manufacture playback authority."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def candidates(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/script.module.bobbi.core/lib'))
    path = ROOT / 'addons/plugin.video.bobbi/lib/clients/tmdb/catalog_candidates.py'
    spec = importlib.util.spec_from_file_location('candidate_fixture', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def raw(kind='tv', year='2020', identifier=123, **extra):
    return dict(media_type=kind, id=identifier, name='作品', title='作品', original_name='Original',
                original_title='Original', first_air_date=year+'-01-01', release_date=year+'-01-01',
                poster_path='/safe_poster.jpg', **extra)


def test_reuses_existing_search_shape_without_private_identifiers_and_keeps_remake_type_ambiguity(candidates):
    calls = []
    def fetch(action, params):
        calls.append((action, params))
        return [raw('movie', '1990'), raw('tv'), raw('person'), raw('movie')]
    value = candidates.search('作品', media_kind='tv', year=2020, fetch=fetch)
    assert calls == [('search_multi', {'query': '作品', 'page': 1})]
    assert len(value['items']) == 3
    assert value['items'][0]['media_kind'] == 'tv'
    assert any(row['media_kind'] == 'movie' and row['tmdb_id'] == 123 for row in value['items'])
    older = next(row for row in value['items'] if row['year'] == 1990)
    assert older['mismatch'] and '重制版本' in older['basis'] and '类型不同' in older['basis']
    assert set(older) == {'media_kind', 'tmdb_id', 'title', 'original_title', 'year', 'poster_path', 'basis', 'mismatch'}


@pytest.mark.parametrize('params', [{'query': '/private/folder'}, {'query': r'C:\private'},
    {'query': 'https://private.invalid'}, {'query': 'abc\x00'}, {'query': 'a'*121}, {'query': ' '},
    {'query': 'Example', 'file_id': 'private'}, {'query': 'Example', 'year': True},
    {'query': 'Example', 'media_kind': 'person'}])
def test_candidate_input_rejects_paths_authority_and_invalid_shapes(candidates, params):
    with pytest.raises(ValueError):
        candidates.parameters(params)


def test_constrained_poster_and_five_result_cap(candidates):
    entries = [dict(raw(identifier=index+1), poster_path='https://evil.invalid/image') for index in range(12)]
    result = candidates.search('作品', fetch=lambda *args: {'results': entries})
    assert len(result['items']) == 5 and all(row['poster_path'] is None for row in result['items'])


@pytest.mark.parametrize('when', ['before', 'after', 'deadline'])
def test_cancel_or_deadline_discards_search_results(candidates, when):
    state = {'canceled': when == 'before', 'calls': 0}
    def fetch(*args):
        state['calls'] += 1;state['canceled'] = True
        return [raw()]
    with pytest.raises(ValueError, match='CANCELED'):
        candidates.search('作品', fetch=fetch, cancelled=lambda: state['canceled'],
                          deadline=time.monotonic()-1 if when == 'deadline' else None)
    assert state['calls'] == (1 if when == 'after' else 0)


def test_search_transport_failure_is_sanitized_without_leaking_response(candidates):
    def fetch(*args):
        raise Exception('private response https://sensitive.invalid')
    with pytest.raises(ValueError, match='^CATALOG_CANDIDATE_UNAVAILABLE$'):
        candidates.search('作品', fetch=fetch)


def test_explicit_special_episode_preserved_and_ambiguous_episode_not_invented(candidates):
    candidate = dict(media_kind='tv', title='作品', tmdb_id=123)
    special = {'candidates': [{'season': 0, 'episode': 2}]}
    assert candidates.candidate_mapping(candidate, special)['season'] == 0
    with pytest.raises(ValueError):
        candidates.candidate_mapping(candidate, {'candidates': [{'season': None, 'episode': None}]})


def entry(index=0, title='作品', version=None):
    return dict(name='Original.%s.mkv'%index, command=dict(file_id='%064x'%(index+1), expected_revision=0,
        action='confirm', mapping=dict(kind='tv', title=title, tmdb_id=123, season=0, episode=index+1, version=version)))


def test_plan_12_items_5_5_2_fixed_ids_copied_commands_and_real_utf8_envelopes(candidates):
    entries = [entry(index, '影😀'*120, '版😀'*40) for index in range(12)]
    original = deepcopy(entries)
    chunks = candidates.plan(entries)
    assert [len(chunk['entries']) for chunk in chunks] == [5, 5, 2]
    assert len({chunk['request_id'] for chunk in chunks}) == 3
    for chunk in chunks:
        envelope = dict(action='catalog_apply', params=dict(request_id=chunk['request_id'],
                        commands=[item['command'] for item in chunk['entries']]))
        assert len(json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= 8192
    entries[0]['command']['mapping']['title'] = 'changed'
    assert chunks[0]['entries'][0] == original[0]
    assert all(item['command']['mapping']['season'] == 0 for chunk in chunks for item in chunk['entries'])


def test_plan_rejects_illegal_mapping_and_never_repairs_multi_episode_implicitly(candidates):
    invalid = entry();invalid['command']['mapping']['episode'] = [1, 2]
    with pytest.raises(ValueError):
        candidates.plan([invalid])
    with pytest.raises(ValueError):
        candidates.plan([entry()]*101)


def test_valid_large_unicode_envelopes_split_below_five_when_full_wire_budget_requires(candidates):
    # The existing revision schema permits arbitrary nonnegative integers.
    # This deliberately large (but valid) revision exercises the byte bound
    # separately from the normal five-item cap, without weakening field limits.
    entries=[entry(index,'😀'*240,'😀'*80) for index in range(12)]
    for item in entries:item['command']['expected_revision']=10**200
    chunks=candidates.plan(entries)
    assert [len(chunk['entries']) for chunk in chunks]==[4,4,4]
    for chunk in chunks:
        body=dict(action='catalog_apply',params=dict(request_id=chunk['request_id'],commands=[row['command'] for row in chunk['entries']]))
        assert len(json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8'))<=8192


def test_filename_query_is_editable_title_only(candidates):
    assert candidates.query_hint('/private/provider-id/Example.Show.2020.S00E01.1080p.mkv') == 'Example Show'
