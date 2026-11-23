"""Read a known preparation request through the live account-scoped host."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r"""
import json,math,pathlib,re,sqlite3,sys,time,urllib.request
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
from bobbi_core.capabilities import IPC_PROTOCOL
cfg=json.loads(pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
def host(action,body):
 q=urllib.request.Request('http://127.0.0.1:%d/control'%cfg['port'],json.dumps(dict(action=action,body=body)).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+cfg['token']})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=2) as f:r=json.load(f)
 if r.get('ok') is not True:raise RuntimeError('HOST_UNAVAILABLE')
 return r['result']
account=host('account_status',{})
out=dict(timestamp=time.time(),authenticated=account.get('authenticated'),account_epoch=account.get('epoch'))
for method,body in (('ping',{}),('status',{'request_id':RID})):
 try:
  result=host('preparation',dict(method=method,body=body,account=account,protocol=IPC_PROTOCOL))
  safe={k:result[k] for k in ('ok','state','request_id') if k in result}
  if isinstance(result.get('result'),dict):
   details=result['result']
   safe['result']={k:details[k] for k in ('error','stage','reason') if k in details}
   safe['tasks']=[{k:row[k] for k in ('task_id','media_id','version_key','state') if k in row} for row in details.get('tasks',[]) if isinstance(row,dict)]
   proof=details.get('source_proof')
   if isinstance(proof,dict):
    safe['source_proof']=dict(present=True,next_present=isinstance(proof.get('next'),dict),
      request_id=proof.get('request_id'),anchor_media=(proof.get('anchor') or {}).get('media_id'))
  out[method]=safe
 except Exception as e:out[method]=dict(error=type(e).__name__)
if account.get('authenticated') is True:
 try:
  state=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/preparation')/(account['account_id'][4:]+'-'+str(account['epoch']))
  with sqlite3.connect((state/'resources.sqlite').as_uri()+'?mode=ro',uri=True) as db:
   row=db.execute('SELECT payload FROM preparation_intents WHERE id=?',(RID,)).fetchone()
   if row:
    source=json.loads(row[0])['selected']['source_info_hash']
    out['ledger_tasks']=[dict(task_id=r[0],state=r[1],targets=r[2],bindings=r[3]) for r in db.execute('''SELECT t.id,t.state,
      (SELECT COUNT(*) FROM preparation_targets p WHERE p.task=t.id),
      (SELECT COUNT(*) FROM prepared_bindings b WHERE b.task=t.id)
      FROM tasks t WHERE t.source_hash=?''',(source,)).fetchall()]
    task_ids={task['task_id'] for task in out['ledger_tasks']}
    out['qualified_targets']=[]
    for task in sorted(task_ids):
     for media_id,payload in db.execute('''SELECT b.media_id,r.payload FROM prepared_bindings b
       JOIN resources r ON r.id=b.resource WHERE b.task=? ORDER BY b.media_id LIMIT 12''',(task,)):
      if len(out['qualified_targets'])>=12:break
      if not isinstance(payload,str) or len(payload)>131072:continue
      resource=json.loads(payload);proof=resource.get('qualification') or {}
      if not isinstance(proof,dict) or not re.fullmatch(r'tmdb:(movie:[1-9]\d*|tv:[1-9]\d*:s\d+:e[1-9]\d*)',media_id):continue
      row=dict(task_id=task,media_id=media_id,ready=resource.get('state')=='ready',
        media_profile_present=isinstance(proof.get('media_profile'),dict))
      for key in ('probe_method','probe_coverage','video_codec'):
       if isinstance(proof.get(key),str) and re.fullmatch('[a-z][a-z0-9_]{0,63}',proof[key]):row[key]=proof[key]
      for key in ('read_bytes','duration'):
       value=proof.get(key)
       if type(value) in (int,float) and 0<=value<=16777216 and math.isfinite(value):row[key]=value
      out['qualified_targets'].append(row)
    out['recent_audit']=[]
    for timestamp,action,detail in db.execute('SELECT at,action,detail FROM audit ORDER BY seq DESC LIMIT 256'):
     if not isinstance(detail,str) or len(detail)>8192:continue
     parsed=json.loads(detail)
     if not isinstance(parsed,dict) or parsed.get('task') not in task_ids:continue
     if not isinstance(action,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}',action):continue
     safe={key:parsed[key] for key in ('kind','error','code') if isinstance(parsed.get(key),str)
       and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}',parsed[key])}
     metrics=parsed.get('probe')
     if isinstance(metrics,dict):
      probe={key:metrics[key] for key,limit in (('read_bytes',16777216),('requests',33))
        if type(metrics.get(key)) is int and 0<=metrics[key]<=limit}
      seconds=metrics.get('seconds')
      if type(seconds) in (int,float) and 0<=seconds<=120 and math.isfinite(seconds):
       probe['seconds']=round(seconds,3)
      if probe:safe['probe']=probe
     out['recent_audit'].append(dict(at=timestamp,action=action,task_id=parsed['task'],**safe))
     if len(out['recent_audit'])>=12:break
    out['discovery_jobs']=[]
    for job in db.execute('SELECT media_id,state,attempts,next_poll,payload,result FROM next_discovery_jobs LIMIT 512'):
     payload=json.loads(job[4]);anchor=payload.get('anchor') or {}
     if (anchor.get('selected') or {}).get('source_info_hash')!=source:continue
     result=json.loads(job[5])
     out['discovery_jobs'].append(dict(media_id=job[0],state=job[1],attempts=job[2],
       next_poll=job[3],anchor_request=anchor.get('request_id'),target_offset=payload.get('target_offset',1),
       reason=result.get('reason'),result_fields=sorted(result)))
 except Exception as e:out['ledger_error']=type(e).__name__
print(json.dumps(out))
"""

if __name__=='__main__':
    import re
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--request',required=True)
    a=p.parse_args()
    if not re.fullmatch('[0-9a-f]{32}',a.request) or a.output.exists():p.error('Known request/new output required')
    transport.REMOTE='RID='+repr(a.request)+'\n'+transport.REMOTE
    transport.run(a.transport_source,a.output)
