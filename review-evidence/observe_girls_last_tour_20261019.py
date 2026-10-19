"""One-task read-only CE observation; never calls playback owner reconciliation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'ce-natural-girls-last-tour-20261019.json'
SOURCE = Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018')
REMOTE = r'''
import hashlib,json,re,socket,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
expected='be4e6f6c-f236-4e5b-b57a-2fbb4340c4b5'
opener=build_opener(ProxyHandler({}))
def rpc(method,params=None):
 req=Request('http://127.0.0.1:8080/jsonrpc',data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),headers={'Content-Type':'application/json'})
 with opener.open(req,timeout=3) as response: value=json.load(response)
 if 'error' in value: raise RuntimeError('RPC_'+str(value['error'].get('code')))
 return value['result']
def clean_native(row):
 if not isinstance(row,dict):return None
 result={k:row[k] for k in ('native_instance','request_id','phase','reason','sequence','user_intent','subtitle_intent','subtitle_auto_intent','paused','av_started') if k in row}
 for key in ('file_identity','url_sha256'):
  if isinstance(row.get(key),str):result[key+'_digest']=hashlib.sha256(row[key].encode()).hexdigest()
 return result
def seconds(value):
 return value['hours']*3600+value['minutes']*60+value['seconds']+value['milliseconds']/1000
def sample():
 out={'utc_epoch':time.time()}
 try:
  native=rpc('Player.BobiState')
  out['native']=clean_native(native.get('playback'))
  out['selection_epoch']=native.get('selection_epoch')
  active=rpc('Player.GetActivePlayers')
  video=[r for r in active if r.get('type')=='video']
  out['video_active']=bool(video)
  if video:
   player=video[0]['playerid']
   p=rpc('Player.GetProperties',dict(playerid=player,properties=['time','totaltime','speed','subtitleenabled','currentsubtitle','currentvideostream','currentaudiostream']))
   out['seconds'],out['duration']=seconds(p.pop('time')),seconds(p.pop('totaltime'))
   out['speed']=p.get('speed');out['subtitleenabled']=p.get('subtitleenabled')
   for field in ('currentsubtitle','currentvideostream','currentaudiostream'):
    out[field]={k:v for k,v in p.get(field,{}).items() if k in ('language','name','index','codec','width','height','channels','bitrate','samplerate')}
   out['item']=rpc('Player.GetItem',dict(playerid=player,properties=['title','showtitle','season','episode','uniqueid']))['item']
  out['window']=rpc('GUI.GetProperties',dict(properties=['currentwindow']))['currentwindow']
  out['booleans']=rpc('XBMC.GetInfoBooleans',dict(booleans=['Player.Caching','VideoPlayer.IsFullscreen','System.HasModalDialog']))
  labels=['VideoPlayer.Title','VideoPlayer.TVShowTitle','VideoPlayer.Season','VideoPlayer.Episode','Window(10000).Property(AM6B.SubtitleState)','Window.Property(playback_error)']
  out['labels']=rpc('XBMC.GetInfoLabels',dict(labels=labels))
 except Exception as error:out['error_type']=type(error).__name__
 return out
def logs():
 path=Path('/storage/.kodi/temp/kodi.log')
 with path.open('rb') as stream:
  stream.seek(max(0,path.stat().st_size-256*1024));text=stream.read(256*1024).decode('utf-8','replace')
 rows=[]
 for line in text.splitlines():
  if not re.search(r'CINEMA-(?:NEXT|CONTINU|HANDOFF)|NATURAL_EOF|Next episode|next episode|DIRECT_SAME_RELEASE|NEXT_MISSING|CVideoPlayer::OnExit',line):continue
  marker=re.search(r'\[(?:CINEMA|AM6B)[A-Za-z0-9_-]*\]',line)
  codes=re.findall(r'\b[A-Z][A-Z_]{4,70}\b',line)
  fields={k:v for k,v in re.findall(r'\b(stage|reason|phase|attempt|episode|season)=([A-Za-z0-9_-]{1,80})',line)}
  rows.append(dict(time=line[:23],marker=marker.group(0) if marker else '',codes=codes[:12],fields=fields,
    onexit='CVideoPlayer::OnExit' in line,native_expected=expected in line))
 return rows[-32:]
out={'samples':[sample()],'events':[],'read_only':True,'owner_snapshot_called':False}
connection=None
try:
 connection=socket.create_connection(('127.0.0.1',9090),timeout=2)
 connection.settimeout(.5)
 connection.sendall(b'{"jsonrpc":"2.0","id":1,"method":"JSONRPC.Ping"}')
 out['notification_socket']=True
except OSError:out['notification_socket']=False
end=time.monotonic()+BUDGET
next_sample=time.monotonic()+min(5,BUDGET)
buffer='';decoder=json.JSONDecoder()
while time.monotonic()<end:
 if connection is not None:
  try:
   chunk=connection.recv(65536)
   if not chunk:connection.close();connection=None
   else:buffer+=chunk.decode('utf-8','replace')
  except socket.timeout:pass
  if len(buffer)>1024*1024:out['notification_overflow']=True;break
  while buffer.strip():
   buffer=buffer.lstrip()
   try:value,used=decoder.raw_decode(buffer)
   except ValueError:break
   buffer=buffer[used:]
   method=value.get('method','')
   if method=='Player.OnBobiState':
    data=value.get('params',{}).get('data',{})
    clean=clean_native(data)
    if clean and len(out['events'])<256:out['events'].append(dict(utc_epoch=time.time(),method=method,native=clean))
   elif method in ('Player.OnStop','Player.OnPlay','Player.OnAVStart','Player.OnPause','Player.OnSeek'):
    data=value.get('params',{}).get('data',{})
    out['events'].append(dict(utc_epoch=time.time(),method=method,end=data.get('end')))
 else:time.sleep(min(.5,max(0,end-time.monotonic())))
 if time.monotonic()>=next_sample:
  out['samples'].append(sample());next_sample=time.monotonic()+5
if connection is not None:connection.close()
out['samples'].append(sample())
out['safe_log']=logs()
print(json.dumps(out,ensure_ascii=True))
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    assert 0 <= args.seconds <= 25
    sys.path.insert(0, str(SOURCE / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ce_natural_readonly_transport', SOURCE / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        code, result, diagnostic = wire.readonly(client, ('BUDGET=' + str(args.seconds) + '\n' + REMOTE).encode(), deadline_seconds=50)
    finally:
        client.close()
    record = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else dict(started=time.time(),expected_native='be4e6f6c-f236-4e5b-b57a-2fbb4340c4b5',batches=[])
    record['batches'].append(dict(exit_code=code,diagnostic_present=bool(diagnostic),result=result))
    OUTPUT.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    samples = result.get('samples', [])
    print(json.dumps(dict(evidence=str(OUTPUT),sample_count=len(samples),
        last=samples[-1] if samples else None,events=result.get('events'),
        safe_log=result.get('safe_log', [])[-4:]),ensure_ascii=False))

if __name__ == '__main__':
    main()
