from copy import deepcopy
from types import SimpleNamespace
import pytest

from bobbi_core.library_labels import bt_station
from bobbi_core.search_completion import SearchCompletion
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform.emby_dynamic import version_labels, menu_account
from lib.cinema.source_presentation import search_status, recommendation_label
from lib.domain.torrent import TorrentStream
from lib.utils.parsers.title_parser import parse_title_info
from test_source_incremental_ui import window

def test_multiple_stations_are_evidence_for_filters_not_playback_identity(window):
    a, b = bt_station('nyaasi'), bt_station('knaben')
    s = SourceListSession({}, lambda rows: rows)
    row = TorrentStream(title='Film.DTS-HD.MA.5.1-FGT.mkv', type='Torrent',indexer='Jackett',
                        infoHash='b'*40,url='https://one.invalid/selected',sourceStations=a)
    other = deepcopy(row);other.url='https://two.invalid/different-transport';other.sourceStations=b
    s.publish(s.epoch,'jackett',[row],state='RUNNING');key=s.key(row)
    s.publish(s.epoch,'jackett',[other]);card=s.inspect(s.epoch,key)
    assert card.sourceStations == {**a, **b} and card.url == row.url
    for station in (*a,*b):assert window._apply_source_filter('station',station,[card]) == [card]
    assert window._apply_source_filter('indexer','BT种子',[card]) == [card]
    assert not bt_station('','', 'FGT') and parse_title_info(row.title)['release_group']=='FGT'
    assert parse_title_info('Film.TrueHD.7.1.Atmos-FGT.mkv')['release_group']=='FGT'
    assert parse_title_info('Example.1080p-Erai-Raws.mkv')['release_group']=='Erai-Raws'

def test_failures_are_separate_from_av_and_only_attributed_to_known_station():
    from dataclasses import asdict
    states = {'sharelib':dict(count=2,state='PARTIAL',completion=asdict(SearchCompletion(2,succeeded=1,failed=1,stale=1))),
              'jackett':dict(count=4,state='PARTIAL',completion=asdict(SearchCompletion(2,succeeded=1,timed_out=1,failed_stations=('mikan',))))}
    _,err,note=search_status(states,True)
    assert not err and '共享目录更新失败，显示上次结果' in note and 'Mikan' in note and '超时' in note
    states['sharelib']['count']=0
    _,err,note=search_status(states,False)
    assert '共享目录' in err and '上次结果' not in err and not note
    assert recommendation_label(False,False,'分享已失效 · 可手动重试')=='分享已失效'

def test_account_safe_names_and_duplicate_server_versions(monkeypatch):
    from bobbi_platform import emby_dynamic as dy
    monkeypatch.setattr(dy,'is_english',lambda:False)
    def src(i, alias):return SimpleNamespace(id='connection-number-'+str(i),name=alias,kind='media_server',password='test',
            metadata={'provider':'emby','server_id':'fake-server','user_id':'user-'+str(i)})
    a,b=src(1,'客厅账号'),src(2,'private@example.invalid')
    store=SimpleNamespace(sources=lambda:[a,b])
    assert menu_account(store,a)=='客厅账号' and menu_account(store,b)=='账号 2'
    assert menu_account(SimpleNamespace(sources=lambda:[a]),a)==''
    b.name=a.name
    assert menu_account(store,a)!=menu_account(store,b)
    film=lambda w,h:dict(Container='MKV',MediaStreams=[dict(Type='Video',Width=w,Height=h)])
    result=version_labels([film(3840,2160),film(1920,1080),dict(Name='导演剪辑版')])
    assert result==['1 · MKV · 3840×2160','2 · MKV · 1920×1080','3 · 导演剪辑版']
    assert version_labels([{},{}])==['1 · 原片','2 · 原片']

def test_clear_library_only_keeps_other_axes(window):
    window._filters={'source':('library','a'*32,'同名库'),'quality':('quality_tab','4k','4K'),
                     'subtitle':('chinese_subtitles',None,'标注中文字幕')}
    window.sources=[];window.setFocusId=lambda *_:None
    assert ('library','a'*32,'同名库') in window._library_options()
    window._change_filter('clear_source')
    assert set(window._filters)=={'quality','subtitle'}
