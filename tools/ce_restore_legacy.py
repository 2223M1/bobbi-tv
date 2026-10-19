"""Owner-requested return to the retained pre-migration personal CE stack.

Not an update-engine downgrade. Keep candidate programs/profile/history intact;
switch back to preserved old programs and their old native/owner only.
"""
import argparse
import importlib.util
import json
import hashlib
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,os,pathlib,shutil,sqlite3,subprocess,time,urllib.request,xml.etree.ElementTree as ET
KODI=pathlib.Path('/storage/.kodi')
FIRST=pathlib.Path('/storage/.local/share/bobbi-private-deploy/20261019-174118')
JACK=pathlib.Path('/storage/.local/share/bobbi-upstream-restore/20261019-jacktorr')
OLD=('plugin.video.jacktook','script.am6b.opensubtitles','skin.am6b.cinema')
NATIVE='8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
UNITS=('kodi.service','bobitv-preparation.service')
def command(*args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 if p.returncode:raise RuntimeError('COMMAND_FAILED_'+args[0])
 return p.stdout.decode().strip()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as r:v=json.load(r)
 assert 'error' not in v,'RPC_ERROR'
 return v['result']
def tree(path):
 result={}
 assert path.is_dir() and not path.is_symlink(),'TREE_MISSING'
 for p in sorted(path.rglob('*')):
  assert not p.is_symlink(),'TREE_SYMLINK'
  if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':result[p.relative_to(path).as_posix()]=sha(p)
 return result
def inspect():
 first=json.loads((FIRST/'deployment.json').read_text())
 out={'first_state':{k:first.get(k) for k in ('gui','services','flags')},'addons':{},'services':{},'jack_backup':{},'native_sha256':None}
 with sqlite3.connect((KODI/'userdata/Database/Addons33.db').as_uri()+'?mode=ro',uri=True) as db:
  for path in sorted((KODI/'addons').glob('*/addon.xml')):
   root=ET.parse(path).getroot();name=root.get('id','')
   if any(s in name for s in ('bobbi','am6b','jacktook','jacktorr','bobi-modern')):
    row=db.execute('SELECT enabled,disabledReason,origin FROM installed WHERE addonID=?',(name,)).fetchone()
    row=list(row) if row is not None else None
    out['addons'][name]={'version':root.get('version'),'state':row,'requires':[n.attrib for n in root.findall('requires/import')],'sha256':sha(path)}
 for unit in UNITS:
  out['services'][unit]={k:command('systemctl','show',unit,'--property='+k,'--value') for k in ('ActiveState','UnitFileState','MainPID','ExecStart','FragmentPath')}
 pids=command('pidof','kodi.bin').split()
 if len(pids)==1:out['native_sha256']=sha(pathlib.Path('/proc')/pids[0]/'exe')
 if (JACK/'addon/addon.xml').is_file():
  out['jack_backup']={'version':ET.parse(JACK/'addon/addon.xml').getroot().get('version'),'content':tree(JACK/'addon')}
 for name in ('resource.uisounds.am6b-modern','resource.uisounds.bobi-modern'):
  p=KODI/'addons'/name/'addon.xml'
  if p.is_file():out.setdefault('sound_addons',{})[name]=ET.parse(p).getroot().attrib
 out['players']=rpc('Player.GetActivePlayers')
 out['gui']=rpc('GUI.GetProperties',{'properties':['currentwindow','skin']})
 out['pending_update_journal']=pathlib.Path('/storage/.local/share/bobbi-private-updates/journal.json').exists()
 out['restore_receipts']=[{'run':p.parent.name,'state':json.loads(p.read_text()).get('state')} for p in sorted(pathlib.Path('/storage/.local/share/bobbi-legacy-restore').glob('*/receipt.json'))]
 config=json.loads(pathlib.Path('/storage/.local/share/bobitv/preparation-runtime/r3-20260922/config.json').read_text())
 state=pathlib.Path(config['state_directory'])
 out['legacy_pending']={}
 for file,tables in (('resources.sqlite',('tasks','preparation_intents','next_discovery')),('direct.sqlite3',('direct_jobs',))):
  path=state/file
  if path.is_file():
   with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
    present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in tables:
     if table in present and 'state' in {r[1] for r in db.execute('PRAGMA table_info('+table+')')}:
      out['legacy_pending'][table]=dict(db.execute('SELECT state,COUNT(*) FROM '+table+' GROUP BY state'))
 return out
def atomic(path,data):
 tmp=path.with_suffix(path.suffix+'.restore-tmp')
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def write_record(run,record):
 atomic(run/'receipt.json',json.dumps(record,ensure_ascii=False,indent=2).encode())
def stopped():
 for unit in UNITS:
  p=pathlib.Path('/run/systemd/system')/unit
  assert p.is_symlink() and os.readlink(str(p))=='/dev/null','OWNER_NOT_MASKED'
  assert command('systemctl','show',unit,'--property=MainPID','--value')=='0','OWNER_NOT_STOPPED'
def sentinels():
 result={}
 for name in ('plugin.video.jacktook','plugin.video.bobbi','plugin.video.jacktorr','script.module.bobbi.platform','skin.am6b.cinema','skin.bobbi.cinema'):
  path=KODI/'userdata/addon_data'/name
  if path.is_dir():
   for p in path.iterdir():
    if p.is_file() and p.suffix not in ('.log','.db','.sqlite','.sqlite3'):
     result[name+'/'+p.name]=sha(p)
 return result
def restore():
 current=inspect()
 assert current['players']==[] and current['native_sha256']==NATIVE,'RESTORE_PRECONDITION'
 assert not current['pending_update_journal'],'UPDATE_IN_PROGRESS'
 assert current['jack_backup']==EXPECTED['jack_backup'],'JACK_BACKUP_CHANGED'
 assert current['addons']==EXPECTED['addons'],'ADDON_STATE_CHANGED'
 assert current['first_state']==EXPECTED['first_state'],'ORIGINAL_RECEIPT_CHANGED'
 assert current['legacy_pending'].get('tasks',{}).keys()<={'ready','mapping','downloading'},'OLD_UNSENT_TASKS_REQUIRE_REVIEW'
 assert current['legacy_pending'].get('direct_jobs',{}).keys()<={'ready','failed'},'OLD_DIRECT_TASKS_REQUIRE_REVIEW'
 assert current['legacy_pending'].get('preparation_intents',{}).keys()<={'accepted','failed'},'OLD_PENDING_INTENTS_REQUIRE_REVIEW'
 for unit in UNITS:
  p=pathlib.Path('/run/systemd/system')/unit
  assert not p.exists() and not p.is_symlink(),'EXISTING_RUNTIME_MASK'
 assert ET.parse(KODI/'addons/plugin.video.jacktook/addon.xml').getroot().get('version')=='1.20.0+am6b.317'
 assert current['jack_backup']['version']=='1.2.2+am6b.317'
 for name in OLD+('script.module.am6b.core','script.module.am6b.qqdocs','script.module.am6b.mdsub','resource.uisounds.am6b-modern'):
  assert (KODI/'addons'/name/'addon.xml').is_file(),'OLD_COMPONENT_MISSING'
 run=pathlib.Path('/storage/.local/share/bobbi-legacy-restore')/RUN_ID
 assert run.parent.resolve()==pathlib.Path('/storage/.local/share/bobbi-legacy-restore'),'RESTORE_PATH'
 run.parent.mkdir(mode=0o700,parents=True,exist_ok=True);run.mkdir(mode=0o700)
 record={'schema':1,'state':'prepared','run':str(run),'before':current,'profiles_preserved':True,'playback_tested':False}
 write_record(run,record)
 target=KODI/'addons/plugin.video.jacktorr'
 staged=run/'jacktorr-legacy';saved=run/'jacktorr-upstream-before'
 shutil.copytree(JACK/'addon',staged,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 assert tree(staged)==current['jack_backup']['content'],'STAGED_JACK_MISMATCH'
 names=[n for n in current['addons'] if 'bobbi' in n]+list(OLD)+['plugin.video.jacktorr','repository.jacktook']
 database=KODI/'userdata/Database/Addons33.db';settings=KODI/'userdata/guisettings.xml'
 held=[];changed=False;swapped=False;success=False;recovered=False
 try:
  for unit in UNITS:
   held.append(unit);command('systemctl','mask','--runtime',unit);command('systemctl','stop',unit)
  stopped()
  before_data=sentinels()
  with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(str(run/'Addons33.before.db')) as backup:old.backup(backup)
  shutil.copy2(settings,run/'guisettings.before.xml')
  with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
   rows={n:db.execute('SELECT enabled,disabledReason,origin FROM installed WHERE addonID=?',(n,)).fetchone() for n in names}
  assert all(v is not None for v in rows.values()),'INSTALLED_ROW_MISSING'
  record['before_rows']=rows;record['state']='stopped';write_record(run,record)
  stopped();target.rename(saved);swapped=True;staged.rename(target)
  with sqlite3.connect((FIRST/'Addons33.before.db').as_uri()+'?mode=ro',uri=True) as db:
   jack_origin=db.execute('SELECT origin FROM installed WHERE addonID=?',('plugin.video.jacktorr',)).fetchone()[0]
  with sqlite3.connect(database) as db:
   changed=True
   for name in names:
    if 'bobbi' in name or name=='repository.jacktook':db.execute('UPDATE installed SET enabled=0,disabledReason=1 WHERE addonID=?',(name,))
   for name in OLD+('plugin.video.jacktorr',):db.execute('UPDATE installed SET enabled=1,disabledReason=0 WHERE addonID=?',(name,))
   db.execute('UPDATE installed SET origin=? WHERE addonID=?',(jack_origin,'plugin.video.jacktorr'))
  doc=ET.parse(settings)
  for node in doc.findall('setting'):
   if node.get('id') in current['first_state']['gui']:
    node.text=current['first_state']['gui'][node.get('id')];node.attrib.pop('default',None)
  atomic(settings,ET.tostring(doc.getroot(),encoding='utf-8',xml_declaration=True))
  assert sentinels()==before_data,'USER_DATA_CHANGED_DURING_SWITCH'
  assert tree(target)==current['jack_backup']['content'],'RESTORED_JACK_MISMATCH'
  record.update(state='programs_switched',profile_sentinels_unchanged=True,disabled_candidate_components=[n for n in names if 'bobbi' in n]);write_record(run,record)
  success=True
 except Exception as error:
  record['failure']=type(error).__name__;record['state']='recovering'
  try:write_record(run,record)
  except Exception:pass
  try:
   if changed or swapped:stopped()
   if changed:
    with sqlite3.connect(database) as db:
     for name,row in rows.items():db.execute('UPDATE installed SET enabled=?,disabledReason=?,origin=? WHERE addonID=?',(*row,name))
    atomic(settings,(run/'guisettings.before.xml').read_bytes())
   if swapped:
    if target.exists():target.rename(run/'jacktorr-legacy-failed')
    saved.rename(target)
   record['state']='candidate_recovered';write_record(run,record);recovered=True
  except Exception as rollback_error:
   record.update(state='recovery_required_owners_held_stopped',recovery_error=type(rollback_error).__name__)
   try:write_record(run,record)
   except Exception:pass
  raise
 finally:
  if success or recovered:
   for unit in reversed(held):command('systemctl','unmask','--runtime',unit)
   if success:
    command('systemctl','enable','bobitv-preparation.service');command('systemctl','start','bobitv-preparation.service');command('systemctl','start','kodi.service')
   else:
    if current['services']['bobitv-preparation.service']['ActiveState']=='active':command('systemctl','start','bobitv-preparation.service')
    command('systemctl','start','kodi.service')
 if success:
  deadline=time.monotonic()+45
  while time.monotonic()<deadline:
   try:
    gui=rpc('GUI.GetProperties',{'properties':['skin','currentwindow']})
    if gui['skin']['id']=='skin.am6b.cinema':break
   except Exception:pass
   time.sleep(.5)
  else:raise RuntimeError('LEGACY_STARTUP_UNCONFIRMED')
  record.update(state='legacy_restored',startup_gui=gui,players=rpc('Player.GetActivePlayers'),restored_native_sha256=sha(pathlib.Path('/proc')/command('pidof','kodi.bin').split()[0]/'exe'))
  record['services_after']={u:{k:command('systemctl','show',u,'--property='+k,'--value') for k in ('ActiveState','UnitFileState','MainPID')} for u in UNITS}
  write_record(run,record)
  return {k:record[k] for k in ('state','run','profiles_preserved','profile_sentinels_unchanged','playback_tested','startup_gui','players','restored_native_sha256','services_after','disabled_candidate_components')}
print(json.dumps(restore() if MODE=='restore' else inspect(),ensure_ascii=False))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--mode',choices=('inspect','restore'),default='inspect')
    parser.add_argument('--expected',type=Path)
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('legacy_restore_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
    if args.mode=='restore' and not args.expected:parser.error('restore requires a saved inspected state')
    expected=json.loads(args.expected.read_text(encoding='utf-8'))['result'] if args.expected else None
    run_id=time.strftime('%Y%m%d-%H%M%S')
    body='MODE='+repr(args.mode)+'\nEXPECTED='+repr(expected)+'\nRUN_ID='+repr(run_id)+'\n'+REMOTE
    script='import json,traceback,sys\nsys.dont_write_bytecode=True\ntry:\n exec('+repr(body)+')\nexcept Exception as e:\n print(json.dumps(dict(error=type(e).__name__,reason=str(e) if isinstance(e,AssertionError) else "RESTORE_UNCONFIRMED",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(e.__traceback__)])))\n raise SystemExit(1)\n'
    client,wire=transport.connect()
    try:rc,result,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=180 if args.mode=='restore' else 55)
    finally:client.close()
    path=ROOT/'review-evidence'/('ce-legacy-'+args.mode+'-'+str(time.time_ns())+'.json')
    path.write_text(json.dumps(dict(result=result,exit_code=rc,diagnostic=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(path),result=result),ensure_ascii=False))
    if rc or diagnostic:raise RuntimeError('LEGACY_STATE_UNCONFIRMED')


if __name__=='__main__':main()
