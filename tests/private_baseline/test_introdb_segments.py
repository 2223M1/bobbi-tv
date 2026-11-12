import json
from types import SimpleNamespace

import pytest
from lib.clients import introdb


@pytest.fixture
def source(monkeypatch):
    cache={};logs=[];calls=[];closed=[]
    monkeypatch.setattr(introdb,'_cache',SimpleNamespace(get=cache.get,set=lambda k,v,**kw:cache.update({k:v})))
    monkeypatch.setattr(introdb,'kodilog',logs.append)
    raw=dict(intro=dict(start_ms=1000,end_ms=9000),imdb_id='tt1',metadata='not segment authority')
    def request(url,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200,iter_content=lambda size:iter([json.dumps(raw).encode()]),close=lambda:closed.append(True))
    monkeypatch.setattr(introdb.requests,'get',request)
    return raw,calls,closed,logs


def test_provider_metadata_is_projected_before_exact_file_owner_validation(source):
    raw,calls,closed,logs=source
    assert introdb.get_segments('tt1',0,1)=={'intro':raw['intro']}
    assert calls[0]['stream'] is True and closed==[True]
    assert introdb.get_segments('tt1',0,1)=={'intro':raw['intro']} and len(calls)==1
    assert not any('not segment authority' in line for line in logs)


def test_oversized_response_is_closed_without_caching_or_body_logging(source):
    raw,calls,closed,logs=source;raw['metadata']='x'*17000
    assert introdb.get_segments('tt1',1,1) is None
    assert introdb.get_segments('tt1',1,1) is None
    assert len(calls)==len(closed)==2
    assert all(len(line)<300 for line in logs)


@pytest.mark.parametrize('raw', [[],True,'not an object'])
def test_non_object_json_unavailable(monkeypatch,source,raw):
    monkeypatch.setattr(introdb.requests,'get',lambda *a,**kw:SimpleNamespace(status_code=200,
        iter_content=lambda size:iter([json.dumps(raw).encode()]),close=lambda:None))
    assert introdb.get_segments('tt1',1,1) is None
