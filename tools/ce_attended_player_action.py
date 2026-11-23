"""One attended remote-control action with before/after instance evidence.

This is a human-equivalent test input, not the production instance-bound handoff
API. The box must be reserved for the attended trial; ordinary Kodi GUI inputs
are not atomic compare-and-set operations. Never used by product auto-recovery.
"""
import argparse
import json
from pathlib import Path
import re
import probe_ce_candidate as transport

ACTIONS = ('stop', 'pause', 'stepforward', 'stepback', 'showsubtitles', 'nextsubtitle',
           'audionextlanguage', 'subtitledelayplus', 'subtitledelayminus',
           'audiodelayplus', 'audiodelayminus', 'osd', 'seek-percent', 'audio-index')
REMOTE = r'''
import json,time,urllib.request
from uuid import uuid4
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=3) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('RPC_REJECTED')
 return r['result']
def read():
 state=rpc('Player.BobiState');native=state.get('playback') or {}
 players=rpc('Player.GetActivePlayers')
 if (native.get('request_id')!=REQUEST or native.get('native_instance')!=INSTANCE
     or native.get('phase')!='AV_STARTED' or len(players)!=1 or players[0].get('type')!='video'):
  raise RuntimeError('EXPECTED_PLAYBACK_CHANGED')
 return dict(playerid=players[0]['playerid'],selection_epoch=state.get('selection_epoch'),native={k:native[k] for k in (
  'request_id','native_instance','phase','sequence','user_intent','audio_intent',
  'subtitle_intent','subtitle_auto_intent','subtitle_file_applied','subtitle_file_sha256','paused') if k in native},
  properties=rpc('Player.GetProperties',dict(playerid=players[0]['playerid'],properties=[
    'time','totaltime','speed','percentage','currentaudiostream','currentsubtitle','subtitleenabled'])),
  labels=rpc('XBMC.GetInfoLabels',dict(labels=['Player.SubtitleDelay','Player.AudioDelay'])))
before=read()
out=dict(mode='attended_human_equivalent_input',atomic_instance_bound=False,
 action=ACTION,percentage=PERCENT,before=before,state='unconfirmed')
try:
 if ACTION=='stop':
  out.update(mode='attended_native_instance_control',atomic_instance_bound=True)
  row=before['native']
  out['result']=rpc('Player.BobiControl',dict(native_instance=INSTANCE,
   user_intent=row['user_intent'],expected_sequence=row['sequence'],
   selection_epoch=before['selection_epoch'],action='stop',command_id=uuid4().hex))
  if out['result'].get('queued') is not True:raise RuntimeError('STOP_NOT_QUEUED')
 elif ACTION=='seek-percent':
  out['result']=rpc('Player.Seek',dict(playerid=before['playerid'],value={'percentage':PERCENT}))
 elif ACTION=='audio-index':
  out['audio_index']=AUDIO_INDEX
  streams=rpc('Player.GetProperties',dict(playerid=before['playerid'],properties=['audiostreams']))['audiostreams']
  if len([s for s in streams if type(s.get('index')) is int and s['index']==AUDIO_INDEX])!=1:
   raise RuntimeError('AUDIO_INDEX_NOT_AVAILABLE')
  read()  # Reconfirm the same attended instance immediately before the input.
  out['result']=rpc('Player.SetAudioStream',dict(playerid=before['playerid'],stream=AUDIO_INDEX))
 else:
  # Kodi validates its public Input.Action enum. No replay on a lost reply.
  out['result']=rpc('Input.ExecuteAction',{'action':ACTION})
 out['acknowledged']=True
except Exception as error:
 out['action_error']=type(error).__name__
if out.get('acknowledged'):
 try:
  if ACTION=='stop':
   until=time.monotonic()+8
   while time.monotonic()<until:
    state=rpc('Player.BobiState');row=state.get('playback') or {}
    if (row.get('request_id')!=REQUEST or row.get('native_instance')!=INSTANCE):
     out['new_instance_observed']=True;break
    if row.get('phase')=='TERMINAL':
     out['stop']=dict(confirmed=row.get('reason')=='STOP',reason=row.get('reason'))
     if out['stop']['confirmed']:out['state']='observed_after_action'
     break
    time.sleep(.25)
  else:
   time.sleep(.5)
   out['after']=read()
   if (ACTION=='audio-index' and
       (out['after']['properties'].get('currentaudiostream') or {}).get('index')!=AUDIO_INDEX):
    out['state']='action_acknowledged_pending'
   else:out['state']='observed_after_action'
 except Exception as error:out['after_error']=type(error).__name__
print(json.dumps(out))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--instance', required=True)
    parser.add_argument('--action', choices=ACTIONS, required=True)
    parser.add_argument('--percent', type=float)
    parser.add_argument('--audio-index', type=int, choices=range(64))
    args = parser.parse_args()
    if (not re.fullmatch('[0-9a-f]{32}', args.request)
            or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.instance)
            or args.output.exists()):
        parser.error('Exact current request/instance and new evidence path required')
    if ((args.action == 'seek-percent') != (args.percent is not None)
            or (args.percent is not None and not 0 <= args.percent < 100)):
        parser.error('seek-percent requires a finite value in [0,100) only')
    if (args.action == 'audio-index') != (args.audio_index is not None):
        parser.error('audio-index requires an observed index in [0,63] only')
    transport.REMOTE = '\n'.join(key+'='+repr(value) for key,value in dict(
        REQUEST=args.request,INSTANCE=args.instance,ACTION=args.action,PERCENT=args.percent,
        AUDIO_INDEX=args.audio_index).items())+'\n'+REMOTE
    # Persist before connecting: even transport loss must not invite blind replay
    # of toggle actions. This receipt is replaced only by the remote evidence.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(dict(state='unconfirmed',request=args.request,instance=args.instance,
                       action=args.action,percentage=args.percent,audio_index=args.audio_index,
                       retry_allowed=False),stream)
    try:
        transport.run(args.transport_source, args.output)
    except Exception as error:
        print(json.dumps(dict(evidence=str(args.output),state='unconfirmed',
                              error_type=type(error).__name__,retry_allowed=False)))
        raise SystemExit(1)
    if json.loads(args.output.read_text(encoding='utf-8')).get('state')!='observed_after_action':
        raise SystemExit(1)
