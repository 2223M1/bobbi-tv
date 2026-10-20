"""Attended same-native ShareStream A/B switch; never touches player quality."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,pathlib,subprocess,sys,time,urllib.request
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.platform/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
from bobbi_platform.transport_preferences import load,save
from bobbi_core.runtime_paths import native_executable_sha256,known_ce_native
root=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform')
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as r:value=json.load(r)
 assert 'error' not in value,'RPC_ERROR'
 return value['result']
def native():
 pids=subprocess.check_output(['pidof','kodi.bin'],timeout=3).decode().split()
 assert len(pids)==1,'NATIVE_PROCESS_COUNT'
 value=native_executable_sha256('/proc/'+pids[0]+'/exe')
 assert known_ce_native(value),'UNREVIEWED_NATIVE'
 return value
def account():
 cfg=json.loads((root/'runtime.json').read_text())
 req=urllib.request.Request('http://127.0.0.1:%d/control'%cfg['port'],json.dumps(dict(action='account_status',body={})).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+cfg['token']})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as r:value=json.load(r)
 assert value.get('ok') is True,'HOST_NOT_READY'
 return value['result']
def restart(expected):
 subprocess.run(['systemctl','restart','kodi.service'],check=True,timeout=35,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 deadline=time.monotonic()+35
 while time.monotonic()<deadline:
  try:
   if native()==expected and rpc('Player.GetActivePlayers')==[]:
    return account()
  except Exception:pass
  time.sleep(.5)
 raise RuntimeError('HOST_RESTART_NOT_READY')
generation=json.loads(pathlib.Path('/storage/.local/share/bobbi-private-updates/state.json').read_text())
assert generation['sequence']>=2026102001,'INSTALL_REMEDIATION_FIRST'
old=load(root); pin=native(); before=account()
out=dict(mode=MODE,before='progressive' if old else 'block',native_sha256=pin)
if MODE!='status':
 assert rpc('Player.GetActivePlayers')==[],'STOP_ATTENDED_TRIAL_FIRST'
 target=MODE=='progressive'
 receipt=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261020/transport-original.json')
 receipt.parent.mkdir(parents=True,exist_ok=True)
 if not receipt.exists():
  with receipt.open('x') as f:json.dump(dict(schema=1,mode=out['before'],native_sha256=pin,sequence=generation['sequence']),f)
 save(root,target)
 try:
  after=restart(pin)
  assert before==after,'ACCOUNT_SCOPE_CHANGED'
  assert load(root) is target,'MODE_NOT_SAVED'
  out.update(configured=MODE,account_scope_unchanged=True,restarted=True)
 except Exception:
  save(root,old)
  restart(pin)
  raise
print(json.dumps(out))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('status', 'block', 'progressive'))
    parser.add_argument('--transport-source', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('transport_mode_device', args.transport_source / 'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    try:
        code, result, diagnostic = wire.readonly(client, ('MODE='+repr(args.mode)+'\n'+REMOTE).encode(), deadline_seconds=100)
    finally:
        client.close()
    report = ROOT / 'review-evidence/ce-20261020' / ('transport-'+args.mode+'-'+str(time.time_ns())+'.json')
    report.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)), indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(evidence=str(report),result=result)))
    if code or diagnostic:
        raise RuntimeError('Inspect existing mode receipt before retry')


if __name__ == '__main__':
    main()
