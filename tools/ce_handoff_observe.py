"""Bounded read-only native transport-handoff trace; never starts/stops media."""
import argparse
from pathlib import Path
import re
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,time,urllib.request
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=2) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('RPC_UNAVAILABLE')
 return r['result']
rows=[];began=time.monotonic();child=None;last=None
for n in range(SECONDS*2):
 try:
  native=rpc('Player.BobiState');p=native.get('playback') or {};h=native.get('handoff') or {}
  if h.get('parent_request_id')==PARENT:child=h.get('child_request_id') or child
  request=p.get('request_id')
  if request and request not in (PARENT,child):
   rows.append(dict(seconds=round(time.monotonic()-began,3),state='OTHER_SELECTION'));break
  row=dict(seconds=round(time.monotonic()-began,3),selection_epoch=native.get('selection_epoch'),
   playback={k:p[k] for k in ('request_id','native_instance','file_identity','url_sha256','phase','reason','paused',
     'sequence','user_intent','subtitle_intent','subtitle_auto_intent','audio_intent','handoff_restored',
     'handoff_parent_instance','handoff_position_ms') if k in p})
  if h.get('parent_request_id')==PARENT:
   row['handoff']={k:h[k] for k in ('phase','restorable','reason','position_ms','parent_native_instance',
    'parent_request_id','child_request_id','expected_child_epoch','user_intent','subtitle_intent','audio_intent','restored') if k in h}
  players=rpc('Player.GetActivePlayers')
  video=[x for x in players if x.get('type')=='video']
  if len(video)==1:
   row['properties']=rpc('Player.GetProperties',dict(playerid=video[0]['playerid'],properties=
    ['time','totaltime','speed','currentaudiostream','currentsubtitle','subtitleenabled','percentage','canseek']))
   row['caching']=rpc('XBMC.GetInfoBooleans',{'booleans':['Player.Caching','Player.Seeking','Player.Paused']})
  # Keep first/last and transitions; sample steady AV every two seconds.
  fingerprint=json.dumps([row.get('playback'),row.get('handoff'),row.get('caching')],sort_keys=True)
  if fingerprint!=last or n%4==0:
   rows.append(row);last=fingerprint
 except Exception as error:rows.append(dict(seconds=round(time.monotonic()-began,3),error=type(error).__name__))
 remaining=SECONDS-(time.monotonic()-began)
 if remaining<=0:break
 time.sleep(min(.5,remaining))
print(json.dumps(dict(parent_request=PARENT,child_request=child,mode='read_only',samples=rows)))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--seconds', type=int, default=25)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.request) or not 1 <= args.seconds <= 30 or args.output.exists():
        parser.error('Exact parent, new output and 1..30 seconds required')
    transport.REMOTE = 'PARENT=' + repr(args.request) + '\nSECONDS=' + str(args.seconds) + '\n' + transport.REMOTE
    transport.run(args.transport_source, args.output)
