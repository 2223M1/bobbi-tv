import json
import time
from contextlib import closing
from types import SimpleNamespace

import pytest

from bobbi_core import library_labels as labels, sharelib_catalog as cat, sharelib_refresh as refresh
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform.paths import ProfileBinding
from lib.cinema.source_filters import Preferences, catalog_options
from lib.domain.torrent import TorrentStream
from test_source_incremental_ui import window


def fixture_row(origin):
    work = dict(tmdbId=1, typeId=1, year=2020, title='Movie')
    return cat._row(work, dict(url='https://115.com/s/sfixture', fileId='7',
        fileName='Movie.2020.2160p.mkv',fileSize=10000000), origin)


def directory(cache, items):
    client = SimpleNamespace(get=lambda *a:dict(items=items))
    refresh._page(cache, client, time.monotonic()+5, lambda:False, cat)


def test_real_directory_projection_multi_membership_legacy_and_stable_renames(tmp_path):
    a,b = 'libraryAudit01','libraryAudit02'
    raw = lambda code,name: dict(shareCode=code,version=1,isPublic=True,name=name)
    spec = cat._spec(dict(tmdb_id=1,mode='movies',year=2020,aliases=['Movie']))
    for service in ('one','two'):
        with closing(cat.Cache(tmp_path/service)) as cache:
            directory(cache,[raw(a,'原盘馆'),raw(b,'原盘馆')])
            rows = cat._finish(cache,[fixture_row('shared:'+a),fixture_row('shared:'+b)],spec)
            fields=cat.fields(rows[0])
            assert len(fields['sourceLibraries'])==2 and len(set(fields['sourceLibraries'].values()))==2
            assert all(n.startswith('原盘馆 · ') for n in fields['sourceLibraries'].values())
            saved=cache.select(rows[0]['key'],spec['media_key'])
            assert not {'sourceLibraries','_libraries','subindexer'}.intersection(saved)
            assert sorted(saved['origins'])==['shared:'+a,'shared:'+b]
            if service=='one':
                original=fields
            else:
                assert not set(fields['sourceLibraries']).intersection(original['sourceLibraries'])
        with closing(cat.Cache(tmp_path/service)) as cache:
            directory(cache,[raw(a,'改名后的片库'),raw(b,'https://private.invalid/share')])
            options=labels.memberships(['shared:'+a,'shared:'+b,'main:1','main:2'],labels.directory(cache))
            assert set(fields['sourceLibraries']) <= options.keys()
            assert len(options)==3 and '自选服务主库' in options.values()
            assert '改名后的片库' in options.values() and '未返回名称' in str(options)
            assert 'private' not in str(options) and a not in str(options)
            assert cat.fields(cat._finish(cache,[fixture_row('shared:'+a)],spec)[0])['url']==original['url']


def test_legacy_cache_does_not_claim_unknown_names_and_other_libraries_remain_selectable(tmp_path):
    obj=SimpleNamespace(root=tmp_path)
    obj.owner=SimpleNamespace(current=lambda:obj)
    with closing(cat.Cache(tmp_path)) as cache:
        directory(cache,[dict(shareCode='notShownInMenu',version=1),dict(shareCode='disappeared',version=1,isPublic=False)])
    opts=catalog_options(obj)
    assert len(opts)==2 and '自选服务主库' in opts.values()
    assert '未返回名称' in str(opts) and 'notShownInMenu' not in str(opts)


def stream(title,libs):
    return TorrentStream(type='Direct',indexer=cat.SITE,title=title,guid='sharelib:'+('a'*63+title[-1]),
                         url='am6bsharelib://'+title,size=1234,sourceLibraries=libs,subindexer='、'.join(libs.values()))


def test_filter_survives_other_titles_empty_results_profile_change_and_quality_toggle(tmp_path,window):
    root = [tmp_path/'first']
    def bind(): return ProfileBinding(lambda addon:root[0]/addon)
    binding=bind(); window._preferences=Preferences(binding)
    window.setFocusId=lambda i:None;window.set_default_focus=lambda *a,**k:None
    a,b='a'*32,'b'*32
    first, overlap = stream('Movie A1',{a:'影院甲'}),stream('Movie B2',{a:'影院甲',b:'影院乙'})
    outside = stream('Movie C3',{b:'影院乙'})
    window.sources=[outside,first,overlap]; window._filters={}
    window._change_filter('library',a,'影院甲')
    assert window.list_sources==[first,overlap]
    assert window._quality_items['__all__'].getLabel()=='全部 (2)'
    assert window.display_list.items[1].props['type_plain']=='影院甲、影院乙'
    assert window.display_list.items[1].props['source_site']=='115 网盘'
    assert window.display_list.items[0].props['recommendation_status'] in ('推荐','需核实')
    window._change_filter('quality_tab','4k')
    assert window.list_sources==[]
    assert window._quality_items['4k'].getLabel()=='4K (0)'
    assert window._quality_items['__all__'].getLabel()=='全部 (2)'
    window._change_filter('quality_tab','__all__')
    assert window.list_sources==[first,overlap]
    fresh=Preferences(bind())
    window._filters=fresh.read()
    assert window._filtered_rows([outside])==[]
    renamed=stream('Another Title4',{a:'影院甲改名'})
    assert window._filtered_rows([outside,renamed])==[renamed] and '影院甲改名' in window._filter_summary
    root[0]=tmp_path/'other'; other=Preferences(bind())
    assert other.read()=={}
    with pytest.raises(ValueError,match='PROFILE_CHANGED'):fresh.write({})
    root[0]=tmp_path/'first';window._preferences=Preferences(bind())
    assert window._preferences.read()['source'][1]==a
    window._change_filter('reset')
    assert window._quality_items['__all__'].getLabel()=='全部 (3)'
    assert window.list_sources==window.sources and Preferences(bind()).read()=={}


def test_late_second_claim_updates_existing_file_without_changing_its_key():
    s=SourceListSession({},lambda rows:rows)
    one=stream('Title1',{'a'*32:'甲库'})
    both=stream('Title1',{'a'*32:'甲库','b'*32:'乙库'})
    s.publish(s.epoch,'catalog',[one],state='RUNNING')
    rev=s.content_revision
    s.publish(s.epoch,'catalog',[both])
    data=s.snapshot(full=True,after_content_revision=rev)
    assert len(data['entries'])==1
    key,row=data['entries'][0]
    assert row.sourceLibraries==both.sourceLibraries
    assert s.capture(s.epoch,key).guid==one.guid
