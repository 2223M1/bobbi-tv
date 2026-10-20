"""Attended real-source standard adapter trial on F9, not stock-hardware certification.

Only presentation uses test metadata/initial StartPercent. Real provider search,
selected-share resolution, next_data, StandardSession and Handoff are untouched.
Existing Runtime remains the sole account/stream owner; no credentials are read.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from uuid import uuid4

import xbmc
import xbmcaddon
import xbmcvfs

ROOT = Path(__file__).resolve().parent
config = json.loads((ROOT/'input.json').read_text())
addons = Path(xbmcvfs.translatePath('special://home/addons'))
for path in sorted(addons.glob('script.module.*/lib')): sys.path.insert(0, str(path))
sys.path.insert(0, str(addons/'plugin.video.bobbi'))
# RunScript(temp/path) has no implicit addon identity. Supply the same default
# that Kodi supplies to the real plugin interpreter, retaining all real APIs.
native_addon = xbmcaddon.Addon
xbmcaddon.Addon = lambda id=None: native_addon(id or 'plugin.video.bobbi')
sys.argv = ['plugin://plugin.video.bobbi/', '-1', '']
from bobbi_platform.runtime import call
from bobbi_platform.account_manager import validate_snapshot
from bobbi_platform.kodi import rpc, make_item, standard_handoff
from bobbi_platform.playback import selected_identity, Handoff
from lib.clients.juku_provider import find_sources
from lib.services.standard_playback import StandardPlayback, resolve_selected

result = dict(state='running', scope='real standard policy + real Juku/115 on existing F9',
              stock_hardware_certified=False, candidates=[], history=[], samples=[])
standard = None
try:
    # Runtime alone publishes the native subtitle ABI marker. Kodi profile-path
    # lookup already supplies this interpreter's paths; configure() here would
    # incorrectly overwrite a live F9 marker with the generic profile ABI.
    account = validate_snapshot(call('account_status', {}), authenticated=True)
    class Accounts:
        def snapshot(self): return validate_snapshot(call('account_status', {}))
        def is_current(self, value):
            try: return self.snapshot() == value
            except (OSError,ValueError,RuntimeError): return False
        def require_current(self, value, authenticated=False):
            validate_snapshot(value, authenticated)
            if not self.is_current(value): raise RuntimeError('ACCOUNT_CHANGED')
            return value
        def run_if_current(self, value, fn):
            self.require_current(value)
            answer = fn()
            self.require_current(value)
            return answer
    accounts = Accounts()
    cancelled = lambda: xbmc.Monitor().abortRequested() or not accounts.is_current(account)
    sources = find_sources({'tmdb_id':30991}, 'tv', 1, 1, 1998,
        ['Cowboy Bebop', '星际牛仔', 'カウボーイビバップ'], None, time.monotonic()+25, cancelled)
    result['candidates'] = [dict(guid=s.guid,title=s.title,bytes=s.size) for s in sources]
    if not config.get('guid'):
        result.update(state='lookup_complete', passed=bool(sources))
    elif config.get('probe_next'):
        from lib.utils.player.direct_continuity import next_direct_data
        source = next(s for s in sources if s.guid == config['guid'])
        data = dict(mode='tv',is_torrent=False,ids={'tmdb_id':30991},tv_data={'season':1,'episode':1},
            source_title=source.title,_account=account,
            direct_source=dict(provider='juku',guid=source.guid,locator=source.url,title=source.title,size=source.size))
        successor,reason = next_direct_data(data,{'titles':[]},cancelled)
        result.update(state='next_probe',reason=reason,passed=bool(successor),
            successor_title=(successor or {}).get('source_title'))
    else:
        matches = [s for s in sources if s.guid == config['guid']]
        if len(matches) != 1: raise RuntimeError('SELECTED_SOURCE_CHANGED')
        if xbmc.Player().isPlaying(): raise RuntimeError('PLAYBACK_ACTIVE')
        source = matches[0]
        prior = call('playback', {'operation':'snapshot'})
        desired = prior.get('desired') or {}
        if desired and not desired.get('cancelled'):
            call('playback', dict(operation='cancel',boot_id=prior['boot_id'],epoch=prior['epoch'],
                                 request_id=desired['request_id']))
        data = dict(request_id=uuid4().hex, _account=account, selection_policy='exact',
            title='Cowboy Bebop', query='Cowboy Bebop', year=1998, mode='tv', media_type='tv',
            ids={'tmdb_id':30991}, tv_data={'season':1,'episode':1}, is_torrent=False,
            source_title=source.title,size=source.size,cinema_continuity=True,_catalog_next=True,
            direct_source=dict(provider='juku',guid=source.guid,locator=source.url,title=source.title,size=source.size))
        data = resolve_selected(data, cancelled)
        reports = []
        view = SimpleNamespace(accounts=accounts,report=reports.append,bind_owner=lambda fn:None,
                               sidecar_candidate=None)
        standard = StandardPlayback(view)
        standard.session.history = lambda value: result['history'].append({k:value.get(k) for k in
            ('request_id','tv_data','terminal_reason','completed','current_time','total_time','lifecycle_evidence')})
        standard.dispatch(dict(operation='select',request_id=data['request_id'],account=account))
        if not standard.dispatch(dict(operation='register',request_id=data['request_id'],data=data))['accepted']:
            raise RuntimeError('REGISTRATION_FAILED')
        def first_item(url, payload):
            item = make_item(url,payload)
            item.setProperty('StartPercent',str(config['resume_percent']))
            return item
        import xbmcplugin
        identity = selected_identity(data['url'])
        Handoff(identity,-1,xbmcplugin.setResolvedUrl,xbmc.Player().play,first_item,
                lambda: not xbmc.Player().isPlaying() and not cancelled()).submit(identity,data)
        result.update(initial_request=data['request_id'],initial_source=source.title,
                      explicit_start_percent=config['resume_percent'],subtitle_backend='existing cache/Assrt; sidecar IO not injected')
        monitor, deadline, sampled = xbmc.Monitor(),time.monotonic()+180,0
        child_started = None
        while not monitor.waitForAbort(.1) and time.monotonic()<deadline:
            standard.tick()
            row = standard.session.current
            now = time.monotonic()
            if now-sampled >= 1:
                sampled=now
                sample=dict(at=now,request_id=row['request_id'],state=row['state'],
                    tv_data=(row['data'] or {}).get('tv_data'),position=row['position'],duration=row['duration'])
                result['samples'].append(sample)
            if row['request_id'] != data['request_id'] and row['state']=='playing':
                child_started = child_started or now
                if now-child_started >= 12: break
            if row['state']=='retired': break
        row=standard.session.current
        child=(row['data'] or {})
        result.update(state='complete',reports=reports,last_handoff=standard.last_handoff,
            successor_title=child.get('source_title'),successor_episode=child.get('tv_data'),
            passed=bool(child_started and row['state']=='playing' and child.get('tv_data')=={'season':1,'episode':2}
                and any(h['request_id']==data['request_id'] and h['terminal_reason']=='NATURAL_EOF' for h in result['history'])))
        # F9 is used solely for atomic teardown of this observed instance, never
        # for standard lifecycle evidence or successor delivery.
        if row['state']=='playing' and standard.player.getPlayingFile()==str(child.get('url','')).partition('|')[0]:
            native=rpc('Player.BobiState'); receipt=native.get('playback') or {}
            if receipt.get('phase')=='AV_STARTED':
                result['teardown']=rpc('Player.BobiControl',dict(native_instance=receipt['native_instance'],
                    user_intent=receipt['user_intent'],expected_sequence=receipt['sequence'],
                    selection_epoch=native['selection_epoch'],action='stop',command_id=uuid4().hex))
except Exception as error:
    result.update(state='failed',passed=False,error=type(error).__name__,
        frames=[dict(module=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
finally:
    if standard: standard.close()
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
