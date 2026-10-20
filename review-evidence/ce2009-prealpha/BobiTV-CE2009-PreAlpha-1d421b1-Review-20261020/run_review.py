#!/usr/bin/env python3
"""Offline fault probes over frozen production modules. No device or external IO.

Kodi, account persistence, signature/archive parser and maintenance lock are
explicit boundary doubles. Real Installer rename/journal/recovery, real standard
lifecycle/handoff/runtime code execute; this is NOT a signature or device test.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
SCOPE = {'account_id': 'uid:review-test', 'authenticated': True, 'epoch': 1}
OWNED = frozenset(('plugin.video.bobbi','plugin.video.bobbi.library','plugin.video.bobbi.torrent',
 'repository.bobbi','resource.uisounds.bobbi-modern','script.bobbi.opensubtitles','script.bobbi.setup',
 'script.bobbi.start','script.module.bobbi.catalog','script.module.bobbi.core','script.module.bobbi.mdsub',
 'script.module.bobbi.platform','skin.bobbi.cinema'))
UPSTREAM = frozenset(('script.module.certifi','script.module.chardet','script.module.idna',
 'script.module.infotagger','script.module.jurialmunkey','script.module.requests','script.module.routing',
 'script.module.urllib3','script.skinvariables'))
ROWS = []


def module(name, **attrs):
    obj=types.ModuleType(name)
    obj.__dict__.update(attrs)
    sys.modules[name]=obj
    return obj


def setup_packages():
    for name, path in [('bobbi_platform',SOURCE/'bobbi_platform'), ('lib',SOURCE/'lib'),
                       ('lib.services',SOURCE/'lib/services')]:
        obj=module(name);obj.__path__=[str(path)]


def emit(name, passed, actual, expected, group):
    ROWS.append(dict(name=name, group=group, passed=bool(passed), expected=expected, actual=actual))


def atomic(path, value):
    path=Path(path); temp=path.with_suffix('.review-tmp')
    with temp.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    if os.environ.get('REVIEW_CRASH')=='before_activation' and value.get('phase')=='complete':
        # Abrupt process loss, not a catchable Python exception.
        os._exit(73)


class FaultHost:
    def __init__(self, root):
        self.path=Path(root)/'host.json'
        self.fail_restore=False
        if not self.path.exists():
            self.write(dict(enabled=list(sorted(OWNED-{'script.bobbi.start'})), skin='skin.before',
                            restores=0, activations=0, ticks=0))
    def read(self):return json.loads(self.path.read_text())
    def write(self,state):self.path.write_text(json.dumps(state,sort_keys=True))
    def dependencies(self, stage):pass
    def skin(self):return self.read()['skin']
    def enabled(self):return self.read()['enabled']
    def quiesce(self):
        s=self.read();s.update(enabled=[],skin='skin.estuary');self.write(s)
    def refresh(self):pass
    def verify(self,versions):pass
    def activate(self,versions):
        s=self.read();s['activations']+=1
        for i,name in enumerate(versions):
            if name not in s['enabled']:s['enabled'].append(name)
            self.write(s)
            if i==0 and os.environ.get('REVIEW_CRASH')=='during_activation':os._exit(74)
    def restore(self,skin,enabled):
        s=self.read();s['restores']+=1;self.write(s)
        if self.fail_restore:
            self.fail_restore=False
            raise RuntimeError('injected transient Kodi restore failure')
        s.update(skin=skin,enabled=list(enabled));self.write(s)


def installer_module():
    class UpdateError(RuntimeError):pass
    class Bundle:
        def __init__(self,path,*args):self.manifest=json.loads(Path(path).read_text())
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def check_all(self):return self.manifest
        def read(self,name,size):return b'validated fixture bytes'
    class Engine:
        def __init__(self,*args,**kwargs):pass
        def _extract(self,blob,row,stage):
            d=Path(stage)/row['id'];d.mkdir()
            (d/'addon.xml').write_text('<addon id="%s" version="%s"/>'%(row['id'],row['version']))
    module('bobbi_platform.offline_updates',SignedBundle=Bundle,load_trust=lambda:{'components':sorted(OWNED|UPSTREAM)})
    module('bobbi_platform.updates',UpdateEngine=Engine,UpdateError=UpdateError,_safe_path=lambda p:Path(p),
           _Lock=lambda p:contextlib.nullcontext(),_atomic=atomic,_json=json.loads)
    module('bobbi_platform.upstream_addons',OWNED_COMPONENTS=OWNED,UPSTREAM_COMPONENTS=UPSTREAM,
           compare_versions=lambda a,b:0)
    return importlib.import_module('bobbi_platform.ce_installer')


def fixture_installer(root,im):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    host=FaultHost(root)
    ins=im.Installer(root/'addons',root/'work',host)
    for name in im.MANAGED:
        p=ins.addons/name;p.mkdir(exist_ok=True);(p/'addon.xml').write_text('original')
    bundle=root/'manifest.json'
    bundle.write_text(json.dumps(dict(sequence=2,components=[dict(id=n,version='2.0.0',file=n+'.zip',size=100)
        for n in sorted(OWNED|UPSTREAM)])))
    return ins,host,bundle


def installer_cases(temp):
    im=installer_module()
    for fail in (False,True):
        ins,host,bundle=fixture_installer(temp/('restore-fail' if fail else 'restore-control'),im)
        original=host.read();ins.apply(bundle)
        host.fail_restore=fail
        error=None
        try:ins.rollback()
        except RuntimeError as exc:error=str(exc)
        before=dict(phase=ins._read()['phase'],blocked=im.blocked(ins.work),host=host.read(),error=error)
        resumed=ins.recover()
        after=host.read()
        restored=(sorted(after['enabled'])==sorted(original['enabled']) and after['skin']==original['skin'])
        files=all((ins.addons/n/'addon.xml').read_text()=='original' for n in im.MANAGED)
        emit('rollback_restore_rpc_retry' if fail else 'rollback_normal',restored and files,
             dict(before_reopen=before,recover_return=resumed,host_after_reopen=after,files_restored=files),
             'Old files AND enable/skin state restored; a transient restore failure remains recoverable','installer')
    for mode in ('before_activation','during_activation'):
        path=temp/mode
        proc=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--child',mode,'--work',str(path)],
                            capture_output=True,text=True,timeout=10)
        host=FaultHost(path);ins=im.Installer(path/'addons',path/'work',host)
        before=ins._read();ret=ins.recover();after=host.read()
        enabled=set(after['enabled'])
        usable=enabled==im.MANAGED
        emit('crash_'+mode,usable,dict(child_exit=proc.returncode,phase=before['phase'],
             blocked=im.blocked(ins.work),enabled_count=len(enabled),wanted_count=len(im.MANAGED),
             recovery_return=ret),
             'Reopen resumes activation or restores old generation; no prematurely complete partial state','installer')
    ins,host,bundle=fixture_installer(temp/'install-control',im);ins.apply(bundle)
    emit('install_no_failure',set(host.enabled())==im.MANAGED and not im.blocked(ins.work),
         dict(phase=ins._read()['phase'],enabled=len(host.enabled())),
         'All managed components activated after complete install','installer')


class Accounts:
    def __init__(self):self.scope=copy.deepcopy(SCOPE)
    def is_current(self,value):return value==self.scope
    def require_current(self,value,authenticated=False):
        if not self.is_current(value):raise ValueError('account changed')


def media(letter='a'):
    return dict(request_id=letter*32,_account=copy.deepcopy(SCOPE),selection_policy='exact',
                mode='tv',title='Review fixture',url='https://fixture.invalid/'+letter+'.mkv',
                tv_data={'season':1,'episode':1 if letter=='a' else 2},file_evidence='AUTO_VERIFIED_FILE')


def lifecycle_cases():
    from bobbi_platform.standard_session import StandardSession
    for kind,pos,expect in [('ENDED',99,True),('STOPPED',99,False),('ERROR',99,False),('ENDED',20,False)]:
        a=Accounts();clock=[100.];opened=[];hist=[]
        ss=StandardSession(a,hist.append,open_next=opened.append,clock=lambda:clock[0])
        d=media();ss.select(d['request_id'],d['_account']);ss.register(d['request_id'],d)
        ss.observe(d['request_id'],d['url'],pos,100)
        ss.current['next_data']=media('b');ss.terminal(d['request_id'],kind)
        clock[0]+=.3;ss.tick()
        emit('terminal_%s_%s'%(kind,pos),bool(opened)==expect,
             dict(open_count=len(opened),history_reason=hist[-1]['terminal_reason']),
             {'opens_next':expect},'standard_lifecycle');ss.close()
    # Same request, candidate unavailable on first scan and available later.
    for initially_ready in (False,True):
        a=Accounts();clock=[100.];ready=[initially_ready];calls=[];opened=[]
        def loader(data,cancelled):
            calls.append(ready[0]);return media('b') if ready[0] else None
        ss=StandardSession(a,next_loader=loader,open_next=opened.append,clock=lambda:clock[0])
        d=media();ss.select(d['request_id'],d['_account']);ss.register(d['request_id'],d)
        ss.observe(d['request_id'],d['url'],90,200);ss.tick(playing=True)
        ss.worker.join(1);ss.tick(playing=True)
        ready[0]=True
        for p in (120,150,180,199):
            clock[0]=100. + (p-90);ss.observe(d['request_id'],d['url'],p,200);ss.tick(playing=True)
        ss.terminal(d['request_id'],'ENDED');clock[0]+=.3;ss.tick()
        emit('next_ready_initially' if initially_ready else 'next_becomes_ready_later',len(opened)==1,
             dict(lookup_count=len(calls),lookup_ready_values=calls,open_count=len(opened),state=ss.current['state']),
             'Eligible same-release successor can be discovered before EOF after initial miss','standard_lifecycle')
        ss.close()
    for change in ('account','selection'):
        a=Accounts();clock=[100.];opened=[];ss=StandardSession(a,open_next=opened.append,clock=lambda:clock[0])
        d=media();ss.select(d['request_id'],d['_account']);ss.register(d['request_id'],d)
        ss.observe(d['request_id'],d['url'],99,100);ss.current['next_data']=media('b')
        if change=='account':a.scope['epoch']=2
        else:ss.select('c'*32,copy.deepcopy(SCOPE))
        ss.terminal(d['request_id'],'ENDED');clock[0]+=.3;ss.tick()
        emit(change+'_invalidates_old_next',not opened,dict(open_count=len(opened)),
             'No old-request continuation','standard_lifecycle');ss.close()


def resident_failure_case():
    # Real session -> real StandardPlayback -> real Handoff -> injected Player API
    # error -> real portable_runtime finally. Only Kodi/account/IO boundaries double.
    state=types.SimpleNamespace(playing=False,item=None,url='',position=99.,total=100.,
        opened=[],props={},saved=[],reports=[],ticks=0,abort=False,closed=False)
    class Tag:
        def __init__(self):self.ids={}
        def setTitle(self,*a):pass
        def setSeason(self,*a):pass
        def setEpisode(self,*a):pass
        def setUniqueID(self,v,k):self.ids[k]=v
        def getUniqueID(self,k):return self.ids.get(k,'')
    class Item:
        def __init__(self,**kw):self.tag=Tag();self.props={}
        def setProperty(self,k,v):self.props[k]=v
        def getProperty(self,k):return self.props.get(k,'')
        def getVideoInfoTag(self):return self.tag
        def setArt(self,*a):pass
        def setSubtitles(self,*a):pass
    class Player:
        def isPlaying(self):return state.playing
        def isPlayingVideo(self):return state.playing
        def getPlayingFile(self):return state.url
        def getTime(self):return state.position
        def getTotalTime(self):return state.total
        def getPlayingItem(self):return state.item
        def play(self,url,item):
            state.opened.append(url)
            raise RuntimeError('injected transient Player.play error')
    class Monitor:
        def waitForAbort(self,seconds):
            if state.ticks>=2:state.abort=True
            return state.abort
    module('xbmc',Player=Player,Monitor=Monitor,LOGINFO=1,log=lambda *a:None,getGlobalIdleTime=lambda:60)
    window=types.SimpleNamespace(getProperty=lambda k:state.props.get(k,''),
        setProperty=lambda k,v:state.props.update({k:v}),clearProperty=lambda k:state.props.pop(k,None))
    module('xbmcgui',ListItem=Item,Window=lambda _:window)
    module('xbmcplugin',setResolvedUrl=lambda *a:None)
    module('bobbi_platform.standard_subtitle_ui',request_id=lambda p:p.getPlayingItem().getProperty('bobbi.standard.request'))
    accounts=Accounts()
    host=types.SimpleNamespace(accounts=accounts,report=state.reports.append,bind_owner=lambda fn:None,
        sidecar_candidate=None,start=lambda:None,configure_preparation=lambda *a:None,
        configure_catalog_refresh=lambda *a:None,playing=False)
    def tick():state.ticks+=1
    def close():state.closed=True
    host.tick,host.close=tick,close
    module('bobbi_platform.host',Host=lambda *a,**k:host)
    module('bobbi_platform.paths',profile=lambda *a,**k:'/fixture-profile')
    module('bobbi_core',__path__=[])
    module('bobbi_core.runtime_paths',configure=lambda *a,**k:None,native_subtitle_abi=lambda *a:None)
    sp=importlib.import_module('lib.services.standard_playback')
    history=types.SimpleNamespace(save=state.saved.append,close=lambda:None)
    original_history=sp.HistoryWriter;sp.HistoryWriter=lambda report:history
    real_cls=sp.StandardPlayback
    def actor_factory(h):
        actor=real_cls(h);clock=[100.]
        actor.session.clock=lambda:clock[0];actor.session.next_loader=None
        d=media();actor.session.select(d['request_id'],d['_account']);actor.session.register(d['request_id'],d)
        actor.session.observe(d['request_id'],d['url'],99,100)
        actor.session.current['next_data']=media('b');actor.session.terminal(d['request_id'],'ENDED')
        clock[0]=100.3
        return actor
    sp.StandardPlayback=actor_factory
    err=None
    try:importlib.import_module('lib.portable_runtime').main({'native_contract_available':False})
    except RuntimeError as exc:err=str(exc)
    finally:sp.StandardPlayback=real_cls;sp.HistoryWriter=original_history
    emit('successor_open_failure_keeps_resident_host',err is None and state.abort and state.ticks>=2,
         dict(escaped_error=err,resident_ticks=state.ticks,normal_monitor_abort=state.abort,
              host_closed=state.closed,open_attempts=len(state.opened)),
         'Single failed successor must be recorded locally; host keeps processing until normal shutdown','standard_lifecycle')


def external_playback_case():
    state=types.SimpleNamespace(playing=False,item=None,url='',pos=99.,props={},opened=[],saved=[])
    class Tag:
        def setTitle(self,*a):pass
        def setSeason(self,*a):pass
        def setEpisode(self,*a):pass
        def setUniqueID(self,*a):pass
    class Item:
        def __init__(self,**kwargs):self.props={};self.tag=Tag()
        def setProperty(self,k,v):self.props[k]=v
        def getProperty(self,k):return self.props.get(k,'')
        def getVideoInfoTag(self):return self.tag
        def setArt(self,*a):pass
        def setSubtitles(self,*a):pass
    class Player:
        def isPlaying(self):return state.playing
        def isPlayingVideo(self):return state.playing
        def getPlayingFile(self):return state.url
        def getPlayingItem(self):return state.item
        def getTime(self):return state.pos
        def getTotalTime(self):return 100.
        def play(self,url,item):state.opened.append(url)
    module('xbmc',Player=Player)
    window=types.SimpleNamespace(getProperty=lambda k:state.props.get(k,''),
        setProperty=lambda k,v:state.props.update({k:v}),clearProperty=lambda k:state.props.pop(k,None))
    module('xbmcgui',ListItem=Item,Window=lambda _:window)
    module('xbmcplugin',setResolvedUrl=lambda *a:None)
    module('bobbi_platform.standard_subtitle_ui',request_id=lambda p:p.getPlayingItem().getProperty('bobbi.standard.request'))
    host=types.SimpleNamespace(accounts=Accounts(),report=lambda *a:None,bind_owner=lambda *a:None)
    sp=importlib.import_module('lib.services.standard_playback')
    original=sp.HistoryWriter;sp.HistoryWriter=lambda report:types.SimpleNamespace(save=state.saved.append,close=lambda:None)
    actor=sp.StandardPlayback(host);clock=[100.];actor.session.clock=lambda:clock[0];actor.session.next_loader=None
    a=media();actor.dispatch(dict(operation='select',request_id=a['request_id'],account=a['_account']))
    actor.dispatch(dict(operation='register',request_id=a['request_id'],data=a))
    state.item=Item();state.item.setProperty('bobbi.standard.request',a['request_id'])
    state.url=a['url'];state.playing=True;actor.tick()
    actor.session.current['next_data']=media('b')
    state.playing=False;actor.player.onPlayBackEnded();actor.tick()
    # Before pending auto-handoff, the user starts a different item outside Bobbi.
    clock[0]=100.1;state.item=Item();state.url='https://fixture.invalid/user-other-video.mkv';state.playing=True
    actor.tick();state_while_other=actor.session.current['state']
    clock[0]=160.;state.playing=False;actor.player.onPlayBackStopped();actor.tick()
    emit('unrelated_user_video_cancels_pending_old_successor',not state.opened,
         dict(state_while_unrelated_played=state_while_other,old_successor_opened=state.opened,
              elapsed_since_parent_end=60.),
         'Playing/stopping an unrelated user video must not resurrect the old pending successor','standard_lifecycle')
    actor.close();sp.HistoryWriter=original


def verify_frozen_sources():
    provenance = json.loads((ROOT / 'SOURCE-PROVENANCE.json').read_text(encoding='utf-8'))
    for row in provenance['files']:
        raw = (ROOT / row['local']).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if (blob != row['git_blob_sha1'] or len(raw) != row['bytes']
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('FROZEN_SOURCE_MISMATCH:' + row['local'])


def main():
    verify_frozen_sources()
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'result-new')
    p.add_argument('--child',choices=['before_activation','during_activation']);p.add_argument('--work',type=Path)
    a=p.parse_args();setup_packages()
    if a.child:
        im=installer_module();ins,host,bundle=fixture_installer(a.work,im)
        os.environ['REVIEW_CRASH']=a.child;ins.apply(bundle);return 0
    a.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='bobbi-ce2009-review-') as name:
        installer_cases(Path(name))
    lifecycle_cases();resident_failure_case();external_playback_case()
    result=dict(scope='Offline production control-flow probes with explicit IO/Kodi boundary doubles',
                count=len(ROWS),passed=sum(x['passed'] for x in ROWS),failed=sum(not x['passed'] for x in ROWS),
                errors=0,device_operations=False,results=ROWS)
    (a.output/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False))
    for r in ROWS:print(('PASS' if r['passed'] else 'FAIL'),r['name'])
    return 1 if result['failed'] else 0

if __name__=='__main__':raise SystemExit(main())
