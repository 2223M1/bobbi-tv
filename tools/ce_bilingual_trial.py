"""Attended bilingual subtitle check on an already identified movie trial.

Uses the installed provider, immutable exporter and F9 conditional application.
No new video read, cloud task, subtitle timeline rewrite or manual-intent reset.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,pathlib,sys,time,urllib.request,uuid
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
from bobbi_core.subtitle_candidates import AssrtCandidates
from bobbi_core.runtime_paths import _subtitle_path
profile=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi')
export=pathlib.Path(_subtitle_path(profile))
record=json.loads(pathlib.Path(RECORD).read_text())
test=record['test']
assert test['kind']=='movie','MOVIE_TRIAL_REQUIRED'
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=3) as f:value=json.load(f)
 assert 'error' not in value,'RPC_FAILED'
 return value['result']
def state():
 value=rpc('Player.BobiState');row=value.get('playback') or {}
 assert row.get('native_instance')==record.get('native_instance') and row.get('request_id')==record.get('request_id'),'TRIAL_REPLACED'
 assert row.get('phase')=='AV_STARTED','NOT_PLAYING'
 return value,row
native,before=state()
if INSPECT:
 from bobbi_core.subtitle_cues import parse
 sha=before.get('subtitle_file_sha256')
 assert isinstance(sha,str) and len(sha)==64 and before.get('subtitle_file_applied'),'NO_APPLIED_FILE'
 files=[export/(sha[:32]+ext) for ext in ('.ass','.ssa','.srt','.vtt')]
 files=[p for p in files if p.is_file() and not p.is_symlink() and p.stat().st_size<=8*1024*1024]
 assert len(files)==1,'FILE_AMBIGUOUS'
 raw=files[0].read_bytes();assert hashlib.sha256(raw).hexdigest()==sha,'HASH_CHANGED'
 rows=parse(raw,files[0].suffix)
 print(json.dumps(dict(sha256=sha,cues=len(rows),samples=[r for r in rows if 80<=r['start']<180][:24]),ensure_ascii=True))
 raise SystemExit(0)
assert before['subtitle_intent']==before['subtitle_auto_intent'] and not before.get('subtitle_file_applied'),'MANUAL_OR_EXISTING_CANDIDATE'
properties=rpc('Player.GetProperties',dict(playerid=1,properties=['totaltime','currentsubtitle']))
t=properties['totaltime'];duration=t['hours']*3600+t['minutes']*60+t['seconds']+t['milliseconds']/1000
context=dict(mode='movie',title=test['title'],year=test['year'],tmdb=test['tmdb_id'],duration=duration,
 filename=record['selected_card']['Container(1000).ListItem.Label'])
def cancelled():
 try:
  current,row=state()
  return row['subtitle_intent']!=before['subtitle_intent'] or current['selection_epoch']!=native['selection_epoch']
 except Exception:return True
provider=AssrtCandidates(None,profile/'subtitle-cache283',token_file=profile/'assrt-token')
candidate=provider.candidates(context,time.monotonic()+27,cancelled,root=export)
assert candidate.get('bilingual') is True,'NO_BILINGUAL_CANDIDATE'
assert not cancelled(),'TRIAL_CHANGED'
file=candidate['file']
out=dict(scope='attended explicit bilingual test',source=candidate['source'],origin=candidate['origin'],
 bilingual=True,sync_verified=False,file_sha256=file['sha256'],file_bytes=file['bytes'],before_subtitle=properties['currentsubtitle'])
if APPLY:
 native,row=state()
 assert row['subtitle_intent']==before['subtitle_intent'],'MANUAL_INTENT_CHANGED'
 result=rpc('Player.BobiSubtitleFile',dict(native_instance=row['native_instance'],request_id=row['request_id'],
     selection_epoch=native['selection_epoch'],subtitle_intent=row['subtitle_intent'],
     path=file['path'],sha256=file['sha256'],bytes=file['bytes'],command_id=uuid.uuid4().hex))
 assert result.get('queued') is True,'NOT_QUEUED'
 until=time.monotonic()+8
 while True:
  _,row=state()
  if row.get('subtitle_file_applied') and row.get('subtitle_file_sha256')==file['sha256']:break
  if time.monotonic()>until or cancelled():raise AssertionError('APPLICATION_NOT_CONFIRMED')
  time.sleep(.2)
 out['applied']=True
 out['after_subtitle']=rpc('Player.GetProperties',dict(playerid=1,properties=['currentsubtitle']))['currentsubtitle']
print(json.dumps(out,ensure_ascii=True))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('work',choices=('arrival',))
    p.add_argument('--apply',action='store_true')
    p.add_argument('--inspect-applied',action='store_true')
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('bilingual_wire',a.transport_source/'ui-redesign/tools/device_transport.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    code=('from pathlib import Path\nRECORD='+repr('/storage/.local/share/bobbi-private-trials/20261020/trial-'+a.work+'.json')+
          '\nAPPLY='+repr(a.apply)+'\nINSPECT='+repr(a.inspect_applied)+'\n'+REMOTE)
    wrapped='import json,traceback\ntry:\n exec(compile('+repr(code)+',"bilingual-trial","exec"))\nexcept Exception as e:\n print(json.dumps(dict(error=type(e).__name__,reason=str(e) if isinstance(e,AssertionError) else "BILINGUAL_TRIAL_FAILED",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(e.__traceback__)])))\n'
    c,w=m.connect()
    try:rc,result,diag=w.readonly(c,wrapped.encode(),deadline_seconds=45)
    finally:c.close()
    a.output.mkdir(parents=True,exist_ok=True)
    dest=a.output/('bilingual-'+str(time.time_ns())+'.json')
    dest.write_text(json.dumps(dict(exit_code=rc,diagnostic_present=bool(diag),result=result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(dest),result=result),ensure_ascii=False))
    return int(bool(rc or diag or result.get('error')))


if __name__=='__main__':raise SystemExit(main())
