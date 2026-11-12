"""Public timestamps do not establish a file edition or automatic playback authority."""
from copy import deepcopy

import pytest
from bobbi_core.media_segments import normalize, current


def ranges():
    return {'intro': {'start_ms': 1000, 'end_ms': 9000, 'start_sec': 1, 'end_sec': 9}}


@pytest.mark.parametrize('start,end', [(True, 9000), (-1,9000), (9000,1000),
    (1000,1000), (float('nan'),9000), (0,float('inf')), ('1000',9000), (0,901000)])
def test_bad_range_rejects_whole_response(start, end):
    assert normalize({'intro':dict(start_ms=start,end_ms=end)}, 'file-a', 1000, 1) == []


def test_milliseconds_seconds_overlap_and_unknown_fields_fail_closed():
    raw=ranges();raw['intro']['end_sec']=10
    assert normalize(raw,'file-a',100,1)==[]
    raw=ranges();raw['recap']=dict(start_ms=2000,end_ms=10000)
    assert normalize(raw,'file-a',100,1)==[]
    raw=ranges();raw['auto_allowed']=True
    assert normalize(raw,'file-a',100,1)==[]
    assert normalize(ranges(),'file-a',8,1)==[]


def test_current_suggestion_is_bound_to_exact_file_position_duration_and_ttl():
    result=normalize(ranges(),'file-a',100,10)
    assert len(result)==1 and result[0]['evidence']=='public_episode'
    assert current(result,2000,100000,'file-a',20)
    for position,duration,file,now in [(0,100000,'file-a',20),(9000,100000,'file-a',20),
        (2000,8000,'file-a',20),(2000,100000,'file-b',20),(2000,100000,'file-a',86411),
        (2000,100000,'file-a',9)]:
        assert current(result,position,duration,file,now) is None
    assert normalize(ranges(),'file-a',100,10)[0]['segment_id'] != normalize(ranges(),'file-b',100,10)[0]['segment_id']


def test_absurd_response_does_not_enter_cache_projection():
    raw=ranges();raw['intro']['metadata']='x'*8192
    assert normalize(raw,'file-a',100,1)==[]


def test_unavailable_auto_setting_is_hidden_but_its_stored_boolean_contract_remains():
    from pathlib import Path
    from xml.etree import ElementTree
    path=Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/resources/settings.xml'
    settings=ElementTree.parse(path)
    auto=settings.find(".//setting[@id='skip_intro_auto']")
    assert auto is not None and auto.get('type')=='boolean'
    assert auto.findtext('visible')=='false' and auto.findtext('default')=='false'
    assert auto.find('dependencies') is None
    enabled=settings.find(".//setting[@id='skip_intro_enabled']")
    assert enabled is not None and enabled.findtext('visible')!='false'
