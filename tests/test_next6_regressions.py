"""Contracts exercised by the AM6B review and read-model benchmarks."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

from bobbi_core.startup_failure import startup_message, failure_domain
from bobbi_platform import home_preferences, emby_dynamic

ROOT = Path(__file__).resolve().parents[1]


def test_home_save_stops_before_writing_into_a_new_profile():
    changed = []
    def write(*args): changed.append(args)
    assert not home_preferences._save_current(home_preferences.apply_home_space_prefs,
        list(home_preferences.HOME_SPACE_KEYS), {'home'}, (write, write, write), lambda: not changed)
    assert len(changed) == 1
    from bobbi_platform import glass_settings
    assert glass_settings.manage_home_rails is home_preferences.manage_home_rails


def test_scoped_emby_cards_preserve_folder_version_and_source_boundaries():
    from bobbi_platform.emby_session import TICKS_PER_SECOND as ticks
    def card(ident,kind,versions=1,seconds=20,source='a',rev='1'):
        row=dict(Id=ident,Name='Same title',Type=kind,RunTimeTicks=100*ticks,
                 UserData=dict(PlaybackPositionTicks=seconds*ticks), MediaSources=[{'Id':str(i)} for i in range(versions)])
        projected=emby_dynamic.projection(row)
        return emby_dynamic._card_playback(row,projected,SimpleNamespace(id=source,name='server'),rev,'a'*64,resume_on_open=True)
    url,_,props,allowed,*_=card('42','Movie')
    q=parse_qs(urlsplit(url).query);assert allowed and q['resume_mode']==['resume'] and q['source']==['a'] and q['profile']==['a'*64] and props['ResumeTime']=='20'
    for tup in [card('42','Series'),card('42','Movie',2),card('42','Movie',0),card('42','Episode',seconds=101)]:
        path,label,props,allowed,*_=tup
        assert not allowed and 'resume_mode' not in path and 'ResumeTime' not in props and 'PercentPlayed' not in props
    assert 'folder%3A42' in card('42','Season')[0]
    assert '00:20' in card('42','Movie',2)[1] and card('42','Series')[1]==''
    assert card('42','Movie',source='b',rev='2')[0]!=url


def test_emby_display_requests_all_cuts_and_falls_back_only_when_the_reply_is_too_large():
    from bobbi_platform.server_emby import Client
    from bobbi_platform.server_http import ReplyTooLarge
    client = Client('emby', dict(location='https://fixture.example', token='fixture', user_id='u'))
    calls = []
    def request(path, query):
        assert path == '/Users/u/Items'
        fields = set(query['Fields'].split(',')); calls.append(fields)
        if 'MediaSources' in fields:
            assert 'AlternateMediaSources' in fields
            raise ReplyTooLarge('PAN_REPLY_INVALID')
        return {'Items':[{'Id':'same','MediaSources':[{'Id':'primary'}]}], 'TotalRecordCount':1}
    client.session.request = request
    rows, count = client.page_rows('view:recent',1,20,display=True)
    assert count == 1 and rows == [{'Id':'same'}] and len(calls) == 2
    assert 'AlternateMediaSources' not in calls[1] and 'MediaSources' not in calls[1]


def test_failure_stages_do_not_claim_a_file_output_or_episode_without_evidence():
    assert '集数' not in startup_message('target_unresolved') and '集数' in startup_message('target_unresolved',episode=True)
    assert failure_domain('share_revoked')=='source' and failure_domain('buffer_timeout')=='file_buffer'
    assert failure_domain('fullscreen_denied')=='player_output' and failure_domain('selected_file_missing')=='file_selection'
    assert '缓冲' not in startup_message('startup_timeout') and failure_domain('unclassified') is None


def test_file_page_does_not_visit_all_files_before_returning_the_first_two_pages(tmp_path):
    spec=importlib.util.spec_from_file_location('bench_catalog',ROOT/'tools/benchmark_catalog_pages.py')
    bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
    from bobbi_core.catalog_query import CatalogQuery
    path=tmp_path/'index.db';bench.seed(path,3000,10);index=bench.Reader(path)
    try:
        steps=[]
        index.db.set_progress_handler(lambda: (steps.append(1) or len(steps)>80),1000)
        reader=CatalogQuery(index);one=reader.query(bench.SCOPE,{'view':'files'})
        two=reader.query(bench.SCOPE,{'view':'files'},cursor=one['next_cursor'])
        ids=[r['entity_id'] for r in one['items']+two['items']]
        assert len(ids)==len(set(ids))==40 and ids==sorted(ids)
    finally:index.db.close()
