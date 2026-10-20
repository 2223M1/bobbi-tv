"""One pinned private Kodi overlay transition. Firmware and old overlay stay intact."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OLD = '8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
CANDIDATE = 'd750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3'
OLD_LAUNCH = '8cae53ac635e5178c6c671a9f90dd90faeb26f702358b571de46fafe8d68d815'
OLD_CONF = '0175d071e2d5a15851625e890d982cc0c43ba6b80c05b3449124dd7eb6904842'
REMOTE = r'''
import hashlib,json,os,pathlib,subprocess,tempfile,time,urllib.request
base=pathlib.Path('/storage/.local/share/bobbi-native/2026101908')
conf=pathlib.Path('/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as stream:
  for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def command(*args):return subprocess.check_output(args,timeout=30).decode().strip()
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as r:return json.load(r)['result']
def native_sha():
 pids=command('pidof','kodi.bin').split()
 assert len(pids)==1,'NATIVE_PROCESS_COUNT'
 return sha(pathlib.Path('/proc')/pids[0]/'exe')
def atomic(path,data):
 fd,name=tempfile.mkstemp(prefix=path.name+'.bobbi1908-',dir=str(path.parent))
 temp=pathlib.Path(name)
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()
def ready(expected):
 end=time.monotonic()+40
 while time.monotonic()<end:
  try:
   if native_sha()==expected and isinstance(rpc('Player.BobiState'),dict):return True
  except Exception:pass
  time.sleep(1)
 return False

def checked_record():
 record=json.loads(receipt.read_text())
 assert isinstance(record,dict) and isinstance(record.get('history',[]),list),'RECEIPT_INVALID'
 expected=dict(old_conf_sha256=OLD_CONF,new_conf_sha256=HASHES['next.conf'],old_sha256=OLD,new_sha256=HASHES['kodi.bin'])
 assert all(record.get(key)==value for key,value in expected.items()),'RECEIPT_PIN_MISMATCH'
 return record

def transition(record,state,**updates):
 # Retain every prior receipt state, including recovery failures; never erase
 # or lower program generation state to repeat a reviewed native transition.
 history=list(record.get('history',[]))
 if 'state' in record:history.append({key:value for key,value in record.items() if key!='history'})
 result={key:value for key,value in record.items() if key not in ('history','error','recovered')}
 result.update(state=state,history=history,recorded_at=time.time(),**updates)
 atomic(receipt,json.dumps(result).encode())
 return result
for name,digest in HASHES.items():
 p=base/name
 assert not p.is_symlink() and sha(p)==digest,'STAGED_HASH_MISMATCH'
receipt=base/'receipt.json'
out={'action':MODE,'old_sha256':OLD,'new_sha256':HASHES['kodi.bin']}
if MODE=='status':
 out['conf_sha256']=sha(conf)
 try:out['native_sha256']=native_sha()
 except Exception:out['native_sha256']=None
 if receipt.is_file():out['receipt']=json.loads(receipt.read_text())
elif MODE in ('apply','reapply'):
 if MODE=='apply':
  assert not receipt.exists(),'TRANSITION_ALREADY_STARTED'
  record=dict(old_conf_sha256=OLD_CONF,new_conf_sha256=HASHES['next.conf'],old_sha256=OLD,new_sha256=HASHES['kodi.bin'])
 else:
  record=checked_record()
  assert record['state']=='rolled_back' and record.get('recovered') is True,'REAPPLY_REQUIRES_CONFIRMED_ROLLBACK'
  assert sha(base/'previous.conf')==OLD_CONF,'PREVIOUS_CONFIGURATION_CHANGED'
 assert native_sha()==OLD and sha(conf)==OLD_CONF,'BASELINE_CHANGED'
 assert sha(pathlib.Path('/storage/.am6b-repair284/native/launch.py'))==OLD_LAUNCH,'OLD_LAUNCH_CHANGED'
 assert sha(pathlib.Path('/storage/.am6b-repair284/native/kodi.bin'))==OLD,'OLD_BINARY_CHANGED'
 generation=json.loads(pathlib.Path('/storage/.local/share/bobbi-private-updates/state.json').read_text())
 assert type(generation.get('sequence')) is int and generation['sequence']>=2026101908,'INSTALL_COMPATIBLE_ADDONS_FIRST'
 if MODE=='apply':assert generation['sequence']==2026101908,'INITIAL_GENERATION_CHANGED'
 sys_path='/storage/.kodi/addons/script.module.bobbi.core/lib'
 import sys
 sys.path.insert(0,sys_path)
 from bobbi_core.runtime_paths import known_ce_native
 assert known_ce_native(HASHES['kodi.bin']),'UNREVIEWED_NATIVE'
 assert rpc('Player.GetActivePlayers')==[],'STOP_PLAYBACK_BEFORE_NATIVE_MAINTENANCE'
 original=conf.read_bytes()
 if MODE=='apply':
  with (base/'previous.conf').open('xb') as f:
   f.write(original);f.flush();os.fsync(f.fileno())
 assert sha(base/'previous.conf')==OLD_CONF
 record=transition(record,'prepared',action=MODE)
 try:
  command('systemctl','stop','kodi.service')
  assert sha(conf)==OLD_CONF
  atomic(conf,(base/'next.conf').read_bytes())
  command('systemctl','daemon-reload')
  command('systemctl','start','kodi.service')
  assert ready(HASHES['kodi.bin']),'NEW_NATIVE_NOT_READY'
  record=transition(record,'applied',action=MODE)
 except Exception as error:
  command('systemctl','stop','kodi.service')
  assert sha(conf) in (OLD_CONF,HASHES['next.conf']),'CONCURRENT_CONFIGURATION_CHANGE'
  atomic(conf,original)
  command('systemctl','daemon-reload')
  command('systemctl','start','kodi.service')
  record=transition(record,'recovered_after_failure',action=MODE,recovered=ready(OLD),error=type(error).__name__)
  raise
 out['receipt']=record
elif MODE=='rollback':
 record=checked_record()
 assert record['state'] in ('prepared','applied','rolled_back','recovered_after_failure')
 assert sha(conf) in (OLD_CONF,HASHES['next.conf']),'CONCURRENT_CONFIGURATION_CHANGE'
 assert sha(base/'previous.conf')==OLD_CONF
 assert sha(pathlib.Path('/storage/.am6b-repair284/native/launch.py'))==OLD_LAUNCH
 assert sha(pathlib.Path('/storage/.am6b-repair284/native/kodi.bin'))==OLD
 # An interrupted restart may have no Kodi process or responsive JSONRPC.
 # A responsive active playback must still be explicitly stopped first.
 try:players=rpc('Player.GetActivePlayers')
 except Exception:players=None
 assert not players,'STOP_PLAYBACK_BEFORE_NATIVE_MAINTENANCE'
 record=transition(record,record['state'],action='rollback')
 command('systemctl','stop','kodi.service')
 atomic(conf,(base/'previous.conf').read_bytes())
 command('systemctl','daemon-reload')
 command('systemctl','start','kodi.service')
 record=transition(record,'rolled_back',action='rollback',recovered=ready(OLD))
 assert record['recovered'],'OLD_NATIVE_NOT_READY'
 out['receipt']=record
print(json.dumps(out))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--mode', choices=('stage','apply','reapply','status','rollback'), required=True)
    parser.add_argument('--build-result', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.build_result.read_text())
    assert result['state']=='BUILT_NOT_DEPLOYED' and result['original_tree_unchanged']
    assert result['baseline_sha256']==result['control_sha256']==OLD
    assert result['candidate_sha256']==CANDIDATE,'CANDIDATE_PIN_CHANGED'
    binary=args.build_result.parent/'candidate.bin'
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==result['candidate_sha256']
    layout=json.loads((ROOT/'review-evidence/ce-native-layout-before1908.json').read_text())
    launch=layout['files']['/storage/.am6b-repair284/native/launch.py']['source'].encode()
    assert hashlib.sha256(launch).hexdigest()==OLD_LAUNCH and launch.count(OLD.encode())==1
    new_launch=launch.replace(OLD.encode(),result['candidate_sha256'].encode())
    base='/storage/.local/share/bobbi-native/2026101908'
    conf=('[Service]\nBindReadOnlyPaths='+base+'/kodi.bin:/usr/lib/kodi/kodi.bin\nExecStart=\n'
          'ExecStart=/usr/bin/python3 '+base+'/launch.py --standalone -fs $KODI_ARGS $KODI_DEBUG\n').encode()
    files={'kodi.bin':binary.read_bytes(),'launch.py':new_launch,'next.conf':conf}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('native_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try:
        if args.mode=='stage':
            with client.open_sftp() as sftp:
                try:sftp.mkdir('/storage/.local/share/bobbi-native')
                except OSError:
                    if not sftp.stat('/storage/.local/share/bobbi-native'):raise
                sftp.mkdir(base)
                for name,data in files.items():
                    with sftp.open(base+'/'+name,'wx') as stream:stream.write(data)
                    sftp.chmod(base+'/'+name,0o755 if name=='kodi.bin' else 0o644)
        params=dict(MODE='status' if args.mode=='stage' else args.mode,HASHES=hashes,
                    OLD=OLD,OLD_CONF=OLD_CONF,OLD_LAUNCH=OLD_LAUNCH)
        script='\n'.join(k+'='+repr(v) for k,v in params.items())+'\n'+REMOTE
        rc,value,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=110)
    finally:client.close()
    path=ROOT/'review-evidence'/('ce-native1908-'+args.mode+'-'+str(time.time_ns())+'.json')
    path.write_text(json.dumps(dict(result=value,exit_code=rc,diagnostic=bool(diagnostic)),indent=2))
    print(json.dumps(value))
    if rc or diagnostic:raise RuntimeError('NATIVE_TRANSITION_UNCONFIRMED_READ_STATUS')


if __name__=='__main__':main()
