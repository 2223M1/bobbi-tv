"""Inspect exact transport prerequisites; optional nonce-bound fresh verification.

No player controls or cloud preparation submissions. --verify does create a
short-lived local verification job and reads existing cloud-file metadata.
"""
import argparse
from pathlib import Path
import re
import probe_ce_candidate as transport

transport.REMOTE = r'''
import ast,json,pathlib,sqlite3,sys,time,types,urllib.request,traceback
from copy import deepcopy
sys.dont_write_bytecode=True
root=pathlib.Path('/storage/.kodi')
sys.path.insert(0,str(root/'addons/script.module.bobbi.core/lib'))
sys.path.insert(0,str(root/'addons/script.module.bobbi.platform/lib'))
from bobbi_core.video_context import checked_video
cfg=json.loads((root/'userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
def host(action,body):
 q=urllib.request.Request('http://127.0.0.1:%d/control'%cfg['port'],json.dumps(dict(action=action,body=body)).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+cfg['token']})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=2) as f:r=json.load(f)
 if r.get('ok') is not True:raise RuntimeError('HOST_UNAVAILABLE')
 return r['result']
account=host('account_status',{})
snap=host('playback',{'operation':'snapshot'})
desired=snap.get('desired') or {};observed=snap.get('observed') or {}
if desired.get('request_id')!=RID or observed.get('request_id')!=RID:raise RuntimeError('OTHER_SELECTION')
state=root/'userdata/addon_data/plugin.video.bobbi/preparation'/(account['account_id'][4:]+'-'+str(account['epoch']))
with sqlite3.connect((state/'resources.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 row=db.execute('SELECT payload FROM preparation_intents WHERE id=?',(RID,)).fetchone()
 if row is None:raise RuntimeError('INTENT_ABSENT')
 intent=json.loads(row[0])
media=intent['media']
data=dict(request_id=RID,selection_policy='exact',is_torrent=True,
 ids={'tmdb_id':media['tmdb_id']},mode='tv' if media['kind']=='tv' else 'movies',
 tv_data={'season':media['season'],'episode':media['episode']},_account=account)
code=(root/'addons/plugin.video.bobbi/lib/utils/player/transport_recovery.py').read_text()
node=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='exact_context')
ns=dict(deepcopy=deepcopy)
exec(compile(ast.Module(body=[node],type_ignores=[]),'installed-exact-context','exec'),ns)
context=ns['exact_context'](data,intent,snap,observed.get('native_instance'))
out=dict(mode='read_only_prerequisites',request=RID,context_from_retained_intent=bool(context),
 real_monitor_memory_observed=False,desired={k:desired.get(k) for k in ('file_evidence','file_identity','selection_identity','cancelled')})
projection=json.loads((root/'userdata/addon_data/plugin.video.bobbi/bobi-prepared.json').read_text())
out['projection_scope_matches']=projection.get('account_scope')==account
out['projection_fields']=sorted(projection)
out['candidates']=[];matching=[]
for title in projection.get('titles',[]):
 for entry in title.get('sources',[]):
  if str(title.get('tmdb_id'))!=str(media['tmdb_id']):continue
  if media['kind']=='tv' and (entry.get('season'),entry.get('episode'))!=(media['season'],media['episode']):continue
  try:video=checked_video(entry.get('video_context'))
  except (ValueError,TypeError,KeyError):
   out['candidates'].append(dict(valid_video_context=False));continue
  out['candidates'].append(dict(state=entry.get('state'),video_media=video['media_id'],
   selected_equal=video['selected']==intent['selected'],
   source_hash_equal=entry.get('prepared_source_info_hash')==intent['selected']['source_info_hash'],
   bytes_equal=entry.get('bytes')==intent['selected']['torrent_file_bytes'],
   version_equal=entry.get('prepared_version_key')==video['release_key'],
   qualification_present=bool(entry.get('prepared_qualification'))))
  if (entry.get('state')=='qualified' and video['selected']==intent['selected']
      and entry.get('prepared_source_info_hash')==intent['selected']['source_info_hash']
      and entry.get('bytes')==intent['selected']['torrent_file_bytes']
      and entry.get('prepared_version_key')==video['release_key']):matching.append(entry)
if VERIFY:
 out['mode']='fresh_verification_no_playback_controls'
 out['local_verification_job_possible']=True
 stage='projection_load';began=time.monotonic()
 try:
  # Only adapt the Kodi path API; execute installed IPC and verifier unchanged.
  vfs=types.ModuleType('xbmcvfs')
  def translate(path):
   if not path.startswith('special://profile/'):raise ValueError('UNEXPECTED_PATH')
   return str(root/'userdata'/path[len('special://profile/'):])
  vfs.translatePath=translate;sys.modules['xbmcvfs']=vfs
  from bobbi_core.prepared_index import load
  projection=load(root/'userdata/addon_data/plugin.video.bobbi/bobi-prepared.json')
  visible={entry['key'] for title in projection.get('titles',[]) for entry in title.get('sources',[])}
  if not context or len(matching)!=1 or matching[0]['key'] not in visible:
   raise ValueError('EXACT_CANDIDATE_UNAVAILABLE')
  from bobbi_core.preparation_client import call,resolve_entry
  stage='service_status'
  status=call('status',{'request_id':RID},expected_account=account)
  versions={r['version_key'] for r in status.get('result',{}).get('tasks',[]) if r.get('media_id')==context['media_id']}
  out['service_status']=dict(state=status.get('state'),request_matches=status.get('request_id')==RID,
    versions_match=versions=={matching[0]['prepared_version_key']})
  stage='fresh_resolve'
  def cancelled():
   current=host('playback',{'operation':'snapshot'})
   return (any(current.get(k)!=snap.get(k) for k in ('boot_id','epoch'))
     or (current.get('desired') or {}).get('cancelled') is not False
     or (current.get('desired') or {}).get('request_id')!=RID
     or (current.get('observed') or {}).get('native_instance')!=observed.get('native_instance')
     or host('account_status',{})!=account)
  verified=resolve_entry(data,projection,matching[0],cancelled,return_verification=True)
  out['fresh_verification']=dict(ready=bool(verified),seconds=round(time.monotonic()-began,3))
 except Exception as error:
  out['fresh_verification']=dict(ready=False,stage=stage,error=type(error).__name__,
   seconds=round(time.monotonic()-began,3),frames=[dict(file=pathlib.Path(f.filename).name,function=f.name,line=f.lineno)
    for f in traceback.extract_tb(error.__traceback__)[-6:]])
print(json.dumps(out))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--verify', action='store_true', help='Create one local fresh-verification job; no playback control')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.request) or args.output.exists():
        parser.error('Exact current request and new output required')
    transport.REMOTE = 'RID='+repr(args.request)+'\nVERIFY='+repr(args.verify)+'\n'+transport.REMOTE
    transport.run(args.transport_source,args.output)
