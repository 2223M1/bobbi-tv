"""Independent CE2014 combination checks. No devices or external network.

Product modules are exact Git-blob-verified files. Kodi/account/provider IO,
archive signature/parser and updater mutex are doubles as documented; OS lease,
threads, filesystem journal and rename are real. Two method excerpts retain
upstream control flow and have explicit provenance (not claimed full blobs).
"""
from __future__ import annotations
import argparse
import ast
import contextlib
import copy
import importlib
import importlib.util
import json
from pathlib import Path
from queue import Queue, Empty
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
ROWS=[]
spec=importlib.util.spec_from_file_location('review_legacy_support', Path(__file__).with_name('legacy_support.py'))
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
old.SOURCE=SOURCE
M=old.module
NS=types.SimpleNamespace
SCOPE=copy.deepcopy(old.SCOPE)

def add(name, passed, actual, expected, group):
    ROWS.append(dict(name=name,passed=bool(passed),actual=actual,expected=expected,group=group))

def check(name, group, fn):
    try:
        result=fn()
        add(name,*result,group)
    except BaseException as e:
        ROWS.append(dict(name=name,passed=False,error=type(e).__name__,traceback=traceback.format_exc(),group=group))

def packages():
    old.setup_packages()
    p=M('bobbi_core');p.__path__=[str(SOURCE/'bobbi_core')]

def excerpt(name, function, globals_):
    text=(SOURCE/'excerpts'/name).read_text(encoding='utf-8')
    namespace=dict(globals_)
    exec(compile(textwrap.dedent(text),name,'exec'),namespace)
    return namespace[function]

class Tag:
    def __init__(self):self.ids={}
    def setTitle(self,*a):pass
    def setSeason(self,*a):pass
    def setEpisode(self,*a):pass
    def setUniqueID(self,v,k):self.ids[k]=v
    def getUniqueID(self,k):return self.ids.get(k,'')
class Item:
    def __init__(self,label='',path='',**kw):self.tag=Tag();self.props={};self.label=label;self.path=path;self.subs=[]
    def setProperty(self,k,v):self.props[k]=v
    def getProperty(self,k):return self.props.get(k,'')
    def getVideoInfoTag(self):return self.tag
    def setArt(self,*a):pass
    def setSubtitles(self,value):self.subs=value
    def getLabel(self):return self.label
    def setLabel(self,value):self.label=value


def actor_fixture(real_history=False):
    state=NS(playing=False,video=False,item=Item(),url='',position=99.,duration=100.,
             opened=[],props={},history=[],reports=[],play_error=False,read_error=False)
    class Player:
        def isPlaying(self):return state.playing
        def isPlayingVideo(self):return state.playing and state.video
        def getPlayingFile(self):
            if state.read_error:raise RuntimeError('opening/seek')
            return state.url
        def getPlayingItem(self):return state.item
        def getVideoInfoTag(self):return state.item.tag
        def getTime(self):return state.position
        def getTotalTime(self):return state.duration
        def play(self,url,item):
            state.opened.append((url,item))
            if state.play_error:raise RuntimeError('injected play submission error')
        def setSubtitles(self, value):raise AssertionError('No unrequested subtitle mutation allowed')
    window=NS(getProperty=lambda k:state.props.get(k,''),setProperty=lambda k,v:state.props.update({k:v}),clearProperty=lambda k:state.props.pop(k,None))
    M('xbmc',Player=Player,Monitor=lambda:NS(waitForAbort=lambda _:True))
    M('xbmcgui',ListItem=Item,Window=lambda _:window)
    M('xbmcplugin',setResolvedUrl=lambda h,ok,item:state.opened.append((item.path,item)))
    actor_module=importlib.import_module('lib.services.standard_playback')
    original_history=actor_module.HistoryWriter
    if not real_history:
        actor_module.HistoryWriter=lambda report:NS(save=lambda d:state.history.append(copy.deepcopy(d)),close=lambda:None)
    accounts=old.Accounts()
    host=NS(accounts=accounts,report=state.reports.append,bind_owner=lambda fn:None,sidecar_candidate=None)
    actor=actor_module.StandardPlayback(host)
    actor_module.HistoryWriter=original_history
    clock=[100.]
    actor.session.clock=lambda:clock[0]
    actor.session.next_loader=None
    return NS(state=state,actor=actor,module=actor_module,host=host,clock=clock)

def start(f, letter='a', position=99., duration=100.):
    data=old.media(letter)
    data['subtitles_path']=['/fixture/zh.srt']
    f.actor.dispatch(dict(operation='select',request_id=data['request_id'],account=data['_account']))
    result=f.actor.dispatch(dict(operation='register',request_id=data['request_id'],data=data))
    assert result['accepted']
    from bobbi_platform.kodi import make_item
    f.state.item=make_item(data['url'],data)
    f.state.url=data['url'];f.state.playing=f.state.video=True
    f.state.position=position;f.state.duration=duration
    f.actor.tick()
    return data

def ended(f):
    f.state.playing=f.state.video=False
    f.actor.player.onPlayBackEnded();f.actor.tick()

def next_media():
    d=old.media('b');d['subtitles_path']=['/fixture/next.zh.srt'];return d

def lifecycle_group(tmp):
    packages()
    for kind,pos,want in [('ENDED',99,True),('STOPPED',99,False),('ERROR',99,False),('ENDED',25,False)]:
        def test(kind=kind,pos=pos,want=want):
            f=actor_fixture();start(f,position=pos);f.actor.session.current['next_data']=next_media()
            f.state.playing=False;f.actor.event(kind);f.actor.tick();f.clock[0]+=.3;f.actor.tick()
            actual=dict(opened=len(f.state.opened),reason=f.state.history[-1]['terminal_reason'])
            f.actor.close();return (bool(actual['opened'])==want,actual,{'opens_next':want})
        check('terminal_%s_%s'%(kind,pos),'lifecycle',test)
    for change in ('audio','video','account','selection','cancel'):
        def test(change=change):
            f=actor_fixture();data=start(f);f.actor.session.current['next_data']=next_media();ended(f)
            if change in ('audio','video'):
                f.state.playing=True;f.state.video=change=='video';f.state.url='https://other.invalid/item';f.state.item=Item()
                f.actor.tick();f.clock[0]+=1;f.state.playing=False;f.actor.player.onPlayBackEnded();f.actor.tick()
            elif change=='account':f.host.accounts.scope['epoch']+=1
            elif change=='selection':f.actor.session.select('c'*32,copy.deepcopy(SCOPE))
            else:f.actor.dispatch(dict(operation='cancel',request_id=data['request_id']))
            f.clock[0]+=.5;f.actor.tick()
            actual={'opened':len(f.state.opened),'state':f.actor.session.current['state']};f.actor.close()
            return (not actual['opened'],actual,'No stale automatic playback')
        check('takeover_'+change,'lifecycle',test)
    for kind in ('blank_path','read_error'):
        def test(kind=kind):
            f=actor_fixture();data=start(f,position=20)
            if kind=='blank_path':f.state.url=''
            else:f.state.read_error=True
            f.actor.tick();actual=f.actor.session.current_request(data['request_id']);f.actor.close()
            return actual,{'still_current':actual},'Temporary open/seek evidence gap does not retire request'
        check(kind+'_not_takeover','lifecycle',test)
    def invalid_progress():
        f=actor_fixture();data=start(f);f.clock[0]+=5;f.state.position=f.state.duration=0
        f.actor.tick();ended(f);v=f.actor.session.current
        result=(v['state']!='ended',{'state':v['state'],'position':v['position'],'progress_observed':v['progress_observed'],'now':f.clock[0]},'Invalid readings do not renew old EOF evidence')
        f.actor.close();return result
    check('invalid_progress_not_fresh_eof','lifecycle',invalid_progress)
    def play_failure():
        f=actor_fixture();start(f);f.actor.session.current['next_data']=next_media();ended(f)
        f.state.play_error=True;f.clock[0]+=.3
        f.actor.tick();f.actor.tick()
        status=f.actor.last_handoff;count=len(f.state.opened)
        ok=status['status']=='submission_unknown' and count==1
        f.state.play_error=False;start(f,'c',position=1);ok=ok and f.actor.session.current['state']=='playing'
        f.actor.close();return ok,{'handoff':status,'attempts':count,'later_selection_worked':ok},'One failed successor must not exit actor or auto resend'
    check('handoff_failure_isolated','lifecycle',play_failure)
    for late in (False,True):
        def retry(late=late):
            f=actor_fixture();count=[]
            f.actor.session.next_loader=lambda d,c:(count.append(1) or (None if late and len(count)==1 else next_media()))
            start(f,position=90,duration=200)
            f.actor.session.worker.join(1);f.actor.tick()
            if late:
                f.clock[0]+=6;f.actor.tick();f.actor.session.worker.join(1);f.actor.tick()
            f.state.position=199;f.actor.tick();ended(f);f.clock[0]+=.3;f.actor.tick()
            ok=len(f.state.opened)==1;actual={'lookups':len(count),'open_count':len(f.state.opened)};f.actor.close()
            return ok,actual,'Same-version result can arrive after first miss; one handoff'
        check('next_late' if late else 'next_initial','lifecycle',retry)
    for elapsed in (0,17.5,19.5):
        def budget(elapsed=elapsed):
            f=actor_fixture();current=start(f);ended(f);f.clock[0]+=elapsed
            original_next,original_discover=f.module.next_data,f.module.discover
            budgets=[]
            d=next_media();d.pop('subtitles_path')
            f.module.next_data=lambda *a:copy.deepcopy(d)
            def slow(data,host,deadline,cancelled):
                budget=max(0,deadline-time.monotonic());budgets.append(budget);f.clock[0]+=budget
                raise TimeoutError('optional subtitle')
            f.module.discover=slow
            try:
                result=f.actor.next_with_subtitle(current,lambda:f.clock[0]-100>=20)
                ok=bool(result) and all(b<=2.01 for b in budgets)
                actual={'candidate_retained':bool(result),'subtitle_budgets':budgets,'elapsed':f.clock[0]-100}
            finally:
                f.module.next_data=original_next;f.module.discover=original_discover;f.actor.close()
            return ok,actual,'Optional subtitle budget does not discard a resolved next video'
        check('subtitle_budget_'+str(elapsed),'lifecycle',budget)


def installer_group(tmp):
    packages();im=old.installer_module()
    M('bobbi_platform.paths',profile=lambda *a,**kw:tmp/'runtime.json')
    M('xbmc',Monitor=lambda:NS(waitForAbort=lambda _:False),Player=lambda:NS(isPlaying=lambda:False),executebuiltin=lambda *a:None,log=lambda *a:None,LOGERROR=4)
    ui=importlib.import_module('bobbi_platform.ce_install_ui')
    for action in ('rollback','exit','retry'):
        def test(action=action):
            ins,host,bundle=old.fixture_installer(tmp/action,im)
            def failed(*a):raise RuntimeError('persistent activation')
            activate=host.activate;host.activate=failed
            try:ins.apply(bundle)
            except RuntimeError:pass
            menus=[];responses=[1 if action=='rollback' else (0 if action=='retry' else 2)]
            def select(title,choices,**kw):
                menus.append(list(choices))
                if action=='retry':host.activate=activate
                return responses.pop(0) if responses else -1
            result=ui.recover_interactive(ins,NS(select=select))
            phase=ins._read()['phase']
            ok=(phase=='restored' and result) if action=='rollback' else ((phase=='complete' and result) if action=='retry' else (phase=='activation_pending' and not result))
            return ok,{'phase':phase,'returned':result,'menus':menus},'Persistent recover failure leaves rollback/exit reachable; retry can finish'
        check('recovery_ui_'+action,'installer',test)
    def restore_failure():
        ins,host,bundle=old.fixture_installer(tmp/'restore-repeat',im);ins.apply(bundle)
        def failed(*a):raise RuntimeError('persistent restore')
        host.restore=failed
        try:ins.rollback()
        except RuntimeError:pass
        menu=[]
        result=ui.recover_interactive(ins,NS(select=lambda title,choices,**kw:(menu.append(choices) or len(choices)-1)))
        state=ins._read()
        return not result and state.get('host_pending')=='restore',{'state':state['phase'],'pending':state.get('host_pending'),'menus':menu},'Failed restore stays pending and user can exit'
    check('persistent_restore_exit','installer',restore_failure)
    # Real OS lease; Kodi reads below are API doubles, not a real Kodi process.
    from bobbi_platform.instance_lock import InstanceLock
    for live in (True,False):
        def stale(live=live):
            path=tmp/('live' if live else 'stale')/'runtime.json';path.parent.mkdir();path.write_text('{}')
            ui.profile=lambda *a,**kw:path
            h=ui.KodiHost();h.details=lambda name:dict(version='1',enabled=False);h.skin=lambda:'skin.estuary';h.monitor=NS(waitForAbort=lambda _:True)
            owner=InstanceLock(str(path)+'.lock')
            if live:owner.acquire()
            result='acquired'
            try:h.quiesce()
            except RuntimeError:result='refused'
            finally:h.close();owner.close()
            ok=(result=='refused' and path.exists()) if live else (result=='acquired' and not path.exists())
            return ok,{'result':result,'registration_exists':path.exists()},'Live owner refuses replacement; dead registration is removable under real lease'
        check('lease_live_owner' if live else 'lease_dead_registration','installer',stale)
    def actual_entry_rollback():
        ins,host,bundle=old.fixture_installer(tmp/'main-entry',im)
        host.activate=lambda *a:(_ for _ in ()).throw(RuntimeError('activation down'))
        try:ins.apply(bundle)
        except RuntimeError:pass
        choices=[1,-1];calls=[]
        dialog=NS(select=lambda title,opts,**kw:(calls.append((title,list(opts))) or choices.pop(0)),ok=lambda *a:None,yesno=lambda *a:True)
        M('xbmcgui',Dialog=lambda:dialog);M('xbmcvfs',translatePath=lambda _:str(tmp/'unused'))
        host.details=lambda name:dict(enabled=True,version='old')
        old_factory,old_host=ui.Installer,ui.KodiHost
        ui.Installer=lambda *a:ins;ui.KodiHost=lambda:host
        try:ui.main()
        finally:ui.Installer,ui.KodiHost=old_factory,old_host
        phase=ins._read()['phase']
        return phase=='restored' and len(calls)==2,{'phase':phase,'menu_titles':[r[0] for r in calls]},'Real main reaches recovery rollback and returns to ordinary menu'
    check('real_main_recovery_rollback','installer',actual_entry_rollback)


def shutdown_group(tmp):
    packages()
    from bobbi_platform.instance_lock import InstanceLock
    close_host=excerpt('host_close.py.txt','close',{'Empty':Empty})
    for work in ('none','next','subtitle','history'):
        def test(work=work):
            f=actor_fixture(real_history=(work=='history'))
            started=threading.Event();release=threading.Event();exited=threading.Event()
            path=tmp/work/'runtime.json.lock';lease=InstanceLock(path);lease.acquire()
            host=f.host
            host.stopping=threading.Event();host.idle=True
            host.runtime=NS(lease=lease,close=lambda **kw:None)
            host.images=host.preparation=host.streams=host.engine=None
            host.engine_lock=threading.Lock();host.engine_worker=host.refresh_worker=None
            host.unsubscribe=lambda:None;host.calls=Queue();host.owner=None
            closed=threading.Event();errors=[]
            def task(*args,**kw):
                started.set();release.wait(3);exited.set();return None
            original_discover=f.module.discover
            if work=='next':
                f.actor.session.next_loader=task;start(f,position=90,duration=100)
            elif work=='subtitle':
                d=start(f,position=1,duration=1000);f.module.discover=task
                f.actor.dispatch(dict(operation='subtitle_start',request_id=d['request_id'],data=d))
            elif work=='history':
                M('lib.utils.general.utils',set_watched_file=task)
                start(f,position=1,duration=1000)
            else:
                exited.set();started.set()
            assert started.wait(1)
            def run_close():
                try:f.actor.close();close_host(host)
                except BaseException as e:errors.append(repr(e))
                finally:closed.set()
            thread=threading.Thread(target=run_close);thread.start()
            # Greater than the product's 0.1/0.3 join timeouts, below fixture IO deadline.
            closed.wait(.65)
            claimant=InstanceLock(path);acquired=False
            try:claimant.acquire();acquired=True
            except OSError:pass
            alive=not exited.is_set()
            actual={'task':work,'old_task_still_running':alive,'replacement_lease_acquired':acquired,'close_returned':closed.is_set(),'errors':errors}
            claimant.close();release.set();thread.join(3)
            for worker in (f.actor.session.worker,f.actor.subtitle_worker,getattr(f.actor.history,'worker',None)):
                if worker:worker.join(3)
            lease.close();f.module.discover=original_discover
            ok=(not (alive and acquired)) and not errors and closed.is_set()
            return ok,actual,'No replacement lease while any resident task still runs'
        check('shutdown_drain_'+work,'shutdown',test)
    def component_failure():
        path=tmp/'close-exception'/'runtime.json.lock';lease=InstanceLock(path);lease.acquire()
        entered=threading.Event();release=threading.Event()
        worker=threading.Thread(target=lambda:(entered.set(),release.wait(3)))
        worker.start();entered.wait(1)
        def fail():raise OSError('injected image-close failure')
        h=NS(stopping=threading.Event(),idle=True,runtime=NS(lease=lease,close=lambda **kw:None),
             images=NS(close=fail),unsubscribe=lambda:None,preparation=None,streams=None,
             engine_lock=threading.Lock(),engine=None,engine_worker=None,refresh_worker=worker,calls=Queue(),owner=None)
        error=None
        try:close_host(h)
        except OSError as e:error=type(e).__name__
        claimant=InstanceLock(path);acquired=False
        try:claimant.acquire();acquired=True
        except OSError:pass
        actual={'exception':error,'catalog_worker_alive':worker.is_alive(),'replacement_lease_acquired':acquired}
        ok=not(worker.is_alive() and acquired)
        claimant.close();release.set();worker.join(3);lease.close()
        return ok,actual,'One cleanup error must not release ownership over still-running consumers'
    check('shutdown_cleanup_exception','shutdown',component_failure)


class ListControl:
    def __init__(self):self.items=[];self.selected=0;self.resets=0;self.selects=0
    def reset(self):self.items=[];self.selected=0;self.resets+=1
    def addItems(self,items):self.items.extend(items)
    def getSelectedItem(self):return self.items[self.selected] if self.items else None
    def getSelectedPosition(self):return self.selected
    def selectItem(self,p):self.selected=p;self.selects+=1
    def removeItem(self,p):
        del self.items[p]
        self.selected=max(0,min(self.selected,len(self.items)-1))
class CardUpdate:
    def __init__(self,item):self.item=item
    def setProperty(self,k,v):
        if self.item.getProperty(k)!=v:self.item.setProperty(k,v)

def ui_group(tmp):
    packages()
    M('lib.utils.general.cinema_source_rank',source_preference=lambda *a:{'caution':False,'reason':''},chinese_subtitle_preference=lambda *a:(False,''))
    M('lib.cinema.subtitle_projection',source_card_label=lambda _: '',source_label=lambda _: '')
    M('lib.clients.catalog_providers',provider_for=lambda _:None)
    M('lib.cinema.source_presentation',recommendation_label=lambda *a:'')
    env=dict(contextlib=contextlib,cache=NS(get=lambda _:{}),STREMIO_ADDON_ALIASES_KEY='alias',
        _manual_source_limit=lambda s,n:s[:n],_CardUpdate=CardUpdate,xbmcgui=NS(ListItem=Item),
        _has_chinese_candidate=lambda _:False,parse_title_info=lambda title:dict(clean_title=title,codec='',audio='',badges='',release_group=''),
        _plain_source_badges=str,detect_chinese_subtitle_kind=lambda *a,**kw:'',_show_release_group=lambda *a:False,kodilog=lambda *a:None,
        IndexerType=NS(TORRENT='Torrent',DEBRID='Debrid',STREMIO_DEBRID='Stremio',DIRECT='Direct'),
        source_platform_label=lambda _: '',_get_source_indexer_label=lambda *a:'indexer',get_provider_color=str,get_random_color=str,
        source_site_label=lambda *a:'site',bytes_to_human_readable=str,get_colored_languages=lambda _:'',extract_publish_date=lambda _:'',
        _source_quality=lambda s:s.quality,_provider_display_name=str,_plain_source_label=str,get_source_status=lambda s:'Cached' if s.isCached else 'Download')
    populate=excerpt('source_populate.py.txt','populate_sources_list',env)
    def source(key,**kw):
        d=dict(title=key,guid=key,infoHash=key,type='Torrent',subindexer='',debridType='',addedToDebrid=False,isCached=False,
               size=100,seeders=10,peers=5,fullLanguages=[],publishDate='',quality='1080p',isPack=False)
        d.update(kw);return NS(**d)
    def window(sources,limit):
        return NS(sources=sources,filter_applied=False,filtered_sources=None,item_information={},
                  source_session=NS(limit=limit,key=lambda s:s.guid),display_list=ListControl(),setProperty=lambda *a:None)
    def append():
        a,b,c=source('a'),source('b'),source('c');w=window([a,b],10);populate(w);w.display_list.selected=1
        item=w.display_list.getSelectedItem();old_reset=w.display_list.resets;w.sources=[c,a,b];populate(w,True)
        actual=dict(keys=w._rendered_keys,selected=w.display_list.getSelectedItem().getProperty('source_key'),resets=w.display_list.resets-old_reset,selects=w.display_list.selects)
        return w.display_list.getSelectedItem() is item and actual['resets']==0 and actual['selects']==0,actual,'Unrelated arriving source retains visible objects and focused source'
    check('ui_append_below_cap','ui',append)
    # Use the actual upstream session: snapshot(full=True) still re-inserts
    # the focused source before the renderer applies its display limit.
    # A method-only fake session omitting this step produced a false suspicion.
    M('bobbi_core.playback_request', source_identity=lambda source: 'fixture:' + source.guid)
    from bobbi_core.source_list_session import SourceListSession
    def actual_session():
        return SourceListSession({'kind':'review'}, lambda rows: sorted(rows,
            key=lambda source: (source.guid != 'new-high-ranked', source.guid)), limit=100)
    def cap():
        rows=[source('old-%03d'%i) for i in range(100)]
        session=actual_session();session.publish(session.epoch,'initial',rows)
        w=window([value for _,value in session.snapshot(full=True)['entries']],100)
        w.source_session=session;populate(w);w.display_list.selected=99
        selected=w.display_list.getSelectedItem();key=selected.getProperty('source_key')
        session.focus(key,99)
        session.publish(session.epoch,'new-provider',[source('new-high-ranked')])
        w.sources=[value for _,value in session.snapshot(full=True)['entries']]
        populate(w,True)
        actual={'focused_key_before':key,'focused_key_after':w.display_list.getSelectedItem().getProperty('source_key'),
                'old_visible':key in w._rendered_keys,'rendered_count':len(w._rendered_keys),
                'real_session_used':True,'upstream_focus_reinserted':True,
                'reset_count':w.display_list.resets,'select_commands':w.display_list.selects}
        return key in w._rendered_keys and w.display_list.getSelectedItem() is selected,actual,'Full session preserves focus before renderer display cap; earlier simplified suspicion excluded'
    check('ui_actual_session_focused_card_at_cap','ui',cap)
    def retained_provider_metadata():
        session=actual_session();session.publish(session.epoch,'initial',[source('a',seeders=10,peers=5)])
        session.publish(session.epoch,'second',[source('a',seeders=0,peers=0,isCached=True)])
        row=session.snapshot(full=True)['entries'][0][1]
        actual={'seeders':row.seeders,'peers':row.peers,'cached':row.isCached}
        return actual=={'seeders':10,'peers':5,'cached':False},actual,'Actual publish retains first metadata: renderer-field scenarios below are conditional, not a proved complete provider path'
    check('ui_actual_session_retains_first_metadata','ui',retained_provider_metadata)
    for cached in (False,True):
        def fields(cached=cached):
            a=source('a');w=window([a],100);populate(w);item=w.display_list.getSelectedItem()
            w.sources=[source('a',seeders=0,peers=0,isCached=cached)];populate(w,True)
            props={k:item.getProperty(k) for k in ('seeders','peers','status_plain')}
            return props['seeders'] in ('','0') and props['peers'] in ('','0'),props,'Retained card must clear obsolete optional fields'
        check('ui_clear_peers_cached' if cached else 'ui_clear_peers_zero','ui',fields)
    def update():
        a=source('a');w=window([a],100);populate(w);item=w.display_list.getSelectedItem()
        w.sources=[source('a',seeders=7,peers=8)];populate(w,True)
        ok=item.getProperty('seeders')=='7' and item.getProperty('peers')=='8'
        return ok,{'seeders':item.getProperty('seeders'),'peers':item.getProperty('peers')},'Positive field updates retain object and change values'
    check('ui_update_present_fields','ui',update)


def resolution_group(tmp):
    packages();from bobbi_core.resolution import resolution_class
    for title,want in [('1440x1080',1080),('960x720',720),('1080p 1440x1080',1080),('720p 960x720',720),
                       ('1080x1440',0),('1000x1000',0),('720p 1440x1080',0),('2160p 960x720',0),
                       ('3840x1600',2160),('1922x1080',1080),('7680x4320',4320),('S01E02',0)]:
        actual=resolution_class(title);add('resolution_'+title,actual==want,actual,want,'resolution')


def main():
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['lifecycle','installer','shutdown','ui','resolution'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-root',type=Path);args=p.parse_args()
    global SOURCE
    if args.source_root is not None:
        SOURCE=args.source_root.resolve();old.SOURCE=SOURCE
    with tempfile.TemporaryDirectory(prefix='bobbi-review-') as directory:
        try:globals()[args.group+'_group'](Path(directory))
        except BaseException as e:ROWS.append(dict(name='GROUP_RUNTIME_ERROR',passed=False,error=repr(e),traceback=traceback.format_exc(),group=args.group))
    out=dict(group=args.group,total=len(ROWS),passed=sum(r['passed'] for r in ROWS),failed=sum(not r['passed'] for r in ROWS),errors=sum('error' in r for r in ROWS),cases=ROWS)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k!='cases'}))
    return 2 if out['errors'] else 1 if out['failed'] else 0
if __name__=='__main__':raise SystemExit(main())
