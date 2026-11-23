"""Narrow browser query/receipt capabilities preserve the original write gate."""
import pytest
import importlib.util
from pathlib import Path
import sys

from test_ce2097_phone_management import phone, pair, invoke, http_server


def test_receipt_is_read_only_account_scoped_and_needs_no_fresh_preview(phone):
    pair(phone)
    phone.now += 121
    phone.result = dict(status='found', items=[dict(index=1, status='applied', revision=2,
        selected={'private': 'reference'}, account_id='private-account')])
    assert invoke(phone, 'catalog_receipt', dict(request_id='a'*32)) == dict(
        status='found', items=[dict(index=1, status='applied', revision=2)])
    assert [body for action, body in phone.calls if action == 'catalog_receipt'] == [
        dict(expected=phone.expected, request_id='a'*32)]
    assert not [action for action, _ in phone.calls if action == 'catalog_apply']


@pytest.mark.parametrize('params', [dict(request_id='a'*32, commands=[]), dict(request_id='A'*32),
                                  dict(request_id='a'*32, expected={}), {}])
def test_receipt_cannot_replay_mutation_or_supply_authority(phone, params):
    pair(phone)
    with pytest.raises(phone.module.PhoneError):
        invoke(phone, 'catalog_receipt', params)
    assert not [action for action, _ in phone.calls if action == 'catalog_receipt']


def test_query_has_its_own_read_budget_and_closed_summary_projection(phone):
    pair(phone)
    phone.manager.scopes = frozenset(('catalog_read',))
    card = dict(entity_id='a'*64, entity_kind='work', display_title='Example', media_kind='tv',
                season=None, episode=None, review_state='confirmed', availability='unverified',
                variant_count=2, available_count=0, source_count=1, truncated=False,
                ref={'url': 'private'}, selected={'private': 'reference'}, credentials='private')
    phone.result = dict(schema=1, items=[card]*32, next_cursor='b'*32,
                        projection_revision=12, truncated=False, token='private')
    result = invoke(phone, 'catalog_query', dict(query={'view': 'works'}, limit=32))
    assert len(result['items']) == 32 and result['projection_revision'] == 12
    assert result['next_cursor'] == 'b'*32
    assert not {'ref', 'selected', 'credentials'} & result['items'][0].keys()
    assert 'token' not in result
    with pytest.raises(phone.module.PhoneError):
        invoke(phone, 'catalog_apply', dict(commands=[], request_id='c'*32))


@pytest.mark.parametrize('params', [dict(query={'expected': {}}), dict(query={'view': 'seasons'}),
    dict(query={'text': 'a'*161}), dict(query={'text': 'hidden\x00text'}), dict(query={'media_kind': 'custom'}),
    dict(query={}, cursor='not-a-cursor'), dict(query={}, limit=33), dict(query={}, limit=True),
    dict(query={}, path='/private'), dict(query={}, selected={})])
def test_query_rejects_authority_paths_unbounded_pages_and_invalid_filters(phone, params):
    pair(phone)
    with pytest.raises(phone.module.PhoneError):
        invoke(phone, 'catalog_query', params)
    assert not [action for action, _ in phone.calls if action == 'catalog_query']


def test_query_read_limit_does_not_expand_original_review_projection(phone):
    pair(phone)
    phone.result = dict(items=[dict(status='ready')]*6)
    command = dict(file_id='a'*64, expected_revision=0, action='ignore', mapping=None)
    with pytest.raises(phone.module.PhoneError, match='INVALID_REPLY'):
        invoke(phone, 'catalog_preview', dict(commands=[command]))


@pytest.fixture
def metadata(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/clients/tmdb/catalog_candidates.py'
    spec = importlib.util.spec_from_file_location('lib.clients.tmdb.catalog_candidates',path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules,spec.name,module)
    return module


def test_candidate_search_uses_local_metadata_adapter_only_and_rechecks_current_account(phone,metadata,monkeypatch):
    pair(phone);seen=[]
    def search(**params):
        seen.append(params)
        return dict(items=[dict(media_kind='tv',tmdb_id=123,title='Show',year=2020,poster_path='/safe.jpg',
            basis='suggestion',original_title='Show',mismatch=False,url='https://private.invalid',account_id='private')])
    monkeypatch.setattr(metadata,'search',search)
    result=invoke(phone,'catalog_candidates',dict(query='Show',year=2020))
    assert set(seen[0])=={'query','media_kind','year','cancelled'}
    assert callable(seen[0]['cancelled']) and not seen[0]['cancelled']()
    assert 'url' not in result['items'][0] and 'account_id' not in result['items'][0]
    assert not [action for action,_ in phone.calls if action.startswith('catalog_')]
    assert [action for action,_ in phone.calls][-2:]==['pan_status','pan_status']


def test_account_change_during_candidate_search_discards_result(phone,metadata,monkeypatch):
    pair(phone)
    def search(**params):
        phone.expected=dict(phone.expected,epoch=phone.expected['epoch']+1)
        return dict(items=[dict(title='late')])
    monkeypatch.setattr(metadata,'search',search)
    with pytest.raises(phone.module.PhoneError,match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(phone,'catalog_candidates',dict(query='Show'))


def test_candidate_network_failure_does_not_revoke_a_valid_session(phone,metadata,monkeypatch):
    pair(phone)
    def search(**params):
        raise ValueError('CATALOG_CANDIDATE_UNAVAILABLE')
    monkeypatch.setattr(metadata,'search',search)
    with pytest.raises(phone.module.PhoneError,match='CATALOG_CANDIDATE_UNAVAILABLE'):
        invoke(phone,'catalog_candidates',dict(query='Show'))
    assert not phone.manager.revoked.is_set()
    assert invoke(phone,'catalog_items')==phone.result


@pytest.mark.parametrize('params',[dict(file_id='a'*64,parent='private'),dict(file_id='a'*64,limit=6),
    dict(file_id='a'*64,projection_revision=True),dict(file_id='a'*64,source_id='path'),dict(file_id='not-file-id')])
def test_group_accepts_opaque_anchor_only_not_browser_parent_authority(phone,params):
    pair(phone)
    with pytest.raises(phone.module.PhoneError):invoke(phone,'catalog_group',params)
    assert not [action for action,_ in phone.calls if action=='catalog_group']


def test_group_page_projects_revision_anchor_and_group_without_raw_source_authority(phone):
    pair(phone)
    phone.result=dict(items=[],next_offset=5,group_id='a'*64,anchor_id='b'*64,source_id='c'*32,
                      projection_revision=8,parent_private='secret',namespace='secret')
    result=invoke(phone,'catalog_group',dict(file_id='b'*64,source_id='c'*32,projection_revision=8))
    assert result=={key:value for key,value in phone.result.items() if key not in ('parent_private','namespace')}


def test_actual_http_candidate_search_stays_inside_existing_pair_csrf_and_projection(http_server,metadata,monkeypatch):
    import json
    request,phone=http_server
    monkeypatch.setattr(metadata,'search',lambda **params:dict(items=[dict(title='Show',media_kind='tv',tmdb_id=123,
        year=2020,poster_path='/safe.jpg',basis='suggestion',original_title='Show',mismatch=False,selected={'private':'no'})]))
    code=phone.manager.pairing_url.split('#')[1]
    status,headers,body=request('/manage/api/pair',dict(code=code))
    assert status==200
    auth={'Cookie':headers['Set-Cookie'].split(';')[0],'X-Bobbi-CSRF':json.loads(body)['csrf']}
    status,headers,body=request('/manage/api',dict(action='catalog_candidates',params={'query':'Show'}),auth)
    assert status==200 and 'selected' not in json.loads(body)['items'][0]
    assert "img-src 'self' https://image.tmdb.org;" in headers['Content-Security-Policy']
    status,_,_=request('/manage/api',dict(action='catalog_candidates',params={'query':'Show','expected':{}}),auth)
    assert status==403
    status,_,_=request('/manage/api',dict(action='catalog_apply',params={'commands':[dict(file_id='a'*64,expected_revision=0,
        action='ignore',mapping=None)],'request_id':'b'*32}),auth)
    assert status==409
