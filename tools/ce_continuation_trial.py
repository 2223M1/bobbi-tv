"""Read an attended EOF successor; stop only the explicitly named native instance."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,pathlib,re,time,urllib.request
from uuid import uuid4
record=json.loads(pathlib.Path(RECORD).read_text())
assert record['test']['kind']=='tv','EPISODE_TEST_ONLY'
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as response:value=json.load(response)
 assert 'error' not in value,'RPC_ERROR'
 return value['result']
def owner():
 cfg=json.loads(pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
 req=urllib.request.Request('http://127.0.0.1:%d/control'%cfg['port'],json.dumps(dict(action='playback',body=dict(operation='snapshot'))).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+cfg['token']})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as response:value=json.load(response)
 assert value.get('ok') is True,'OWNER_UNAVAILABLE'
 return value['result']
def sample():
 native=rpc('Player.BobiState');row=native.get('playback') or {}
 state=owner();terminal=state.get('terminal') or {};desired=state.get('desired') or {}
 out=dict(at=time.monotonic(),native=row,selection_epoch=native.get('selection_epoch'),terminal=terminal,
          desired=desired,window=rpc('GUI.GetProperties',dict(properties=['currentwindow'])))
 out['parent_eof_consumed']=(terminal.get('request_id')==record['request_id'] and terminal.get('native_instance')==record['native_instance'] and terminal.get('reason')=='NATURAL_EOF' and terminal.get('consumed') is True)
 if row.get('phase')=='AV_STARTED':
  out['properties']=rpc('Player.GetProperties',dict(playerid=1,properties=['time','totaltime','speed','subtitleenabled','currentsubtitle','currentaudiostream','currentvideostream']))
  out['item']=rpc('Player.GetItem',dict(playerid=1,properties=['title','showtitle','season','episode','uniqueid']))['item']
  out['caching']=rpc('XBMC.GetInfoBooleans',dict(booleans=['Player.Caching']))['Player.Caching']
  out['subtitle_state']=rpc('XBMC.GetInfoLabels',dict(labels=['Window(10000).Property(AM6B.SubtitleState)']))
  out['next_episode_owned']=(row.get('request_id')!=record['request_id'] and desired.get('request_id')==row.get('request_id') and desired.get('file_bound') is True and desired.get('file_evidence')=='AUTO_VERIFIED_FILE' and out['item'].get('season')==record['test']['season'] and out['item'].get('episode')==record['test']['episode']+1 and str(out['item'].get('uniqueid',{}).get('tmdb'))==str(record['test']['tmdb_id']))
  # The live actor retires the old terminal after successor start. Keep the
  # live-receipt field truthful; corroborate an attended transition with logs.
  lines=pathlib.Path('/storage/.kodi/temp/kodi.log').read_text(errors='replace').splitlines()
  parents=[i for i,line in enumerate(lines) if '[BOBBI-TERMINAL]' in line and record['request_id'] in line and record['native_instance'] in line and 'reason=NATURAL_EOF' in line]
  out['ordered_eof_handoff_log']=False
  if parents:
   tail=lines[parents[-1]+1:]
   starts=[i for i,line in enumerate(tail) if row.get('request_id','!') in line and 'SESSION_ACTIVATED' in line]
   if starts:
    segment=tail[:starts[0]]
    out['ordered_eof_handoff_log']=any('[CINEMA-NEXT] NATURAL_EOF_SAME_VERSION_HANDOFF' in line for line in segment) and not any('SESSION_ACTIVATED' in line for line in segment)
  out['successor_observed']=out['next_episode_owned'] and (out['parent_eof_consumed'] or out['ordered_eof_handoff_log'])
 return out
samples=[sample()]
if STOP_REQUEST:
 current=samples[0];row=current['native']
 assert current.get('successor_observed') and row.get('request_id')==STOP_REQUEST and row.get('native_instance')==STOP_INSTANCE,'SUCCESSOR_REPLACED_OR_UNPROVEN'
 result=rpc('Player.BobiControl',dict(native_instance=STOP_INSTANCE,user_intent=row['user_intent'],expected_sequence=row['sequence'],selection_epoch=current['selection_epoch'],action='stop',command_id=uuid4().hex))
 assert result.get('queued') is True,'STOP_NOT_QUEUED'
 deadline=time.monotonic()+12
 while time.monotonic()<deadline and rpc('Player.GetActivePlayers'):time.sleep(.25)
 print(json.dumps(dict(samples=samples,stop_result=result,stopped=not rpc('Player.GetActivePlayers')),ensure_ascii=False))
else:
 for _ in range(4):time.sleep(5);samples.append(sample())
 print(json.dumps(dict(samples=samples),ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('work', choices=('odd_taxi', 'flip_flappers', 'cowboy_bebop'))
    parser.add_argument('--attempt', type=int, required=True, choices=range(1, 11))
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--stop-request')
    parser.add_argument('--stop-instance')
    args = parser.parse_args()
    if bool(args.stop_request) != bool(args.stop_instance):
        parser.error('Name both observed request and instance for attended stop')
    record = '/storage/.local/share/bobbi-private-trials/20261020/trial-'+args.work+('' if args.attempt == 1 else '-'+str(args.attempt))+'.json'
    sys.path.insert(0, str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('continuation_transport', args.transport_source/'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    script = 'RECORD='+repr(record)+'\nSTOP_REQUEST='+repr(args.stop_request)+'\nSTOP_INSTANCE='+repr(args.stop_instance)+'\n'+REMOTE
    wrapped = 'import json\ntry:\n exec(compile('+repr(script)+',"ce-successor-probe","exec"))\nexcept Exception as e:\n print(json.dumps(dict(error=type(e).__name__,reason=str(e) if isinstance(e,AssertionError) else "PROBE_ERROR")))\n'
    client, wire = module.connect()
    try:
        code, result, diagnostic = wire.readonly(client, wrapped.encode(), deadline_seconds=40)
    finally:
        client.close()
    path = ROOT/'review-evidence'/('ce-continuation-'+args.work+'-'+str(time.time_ns())+'.json')
    path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(evidence=str(path),error=result.get('error'),reason=result.get('reason'),
        stopped=result.get('stopped'),last=(result.get('samples') or [None])[-1]),ensure_ascii=False))
    if code or diagnostic or result.get('error'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
