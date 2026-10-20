"""Attended idle-only Kodi restart with bounded, non-secret readiness receipt."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '''
import json,pathlib,subprocess,time,urllib.request
def rpc(method):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method)).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as r: v=json.load(r)
 if 'error' in v: raise RuntimeError('RPC_FAILED')
 return v['result']
if rpc('Player.GetActivePlayers'): raise RuntimeError('PLAYBACK_ACTIVE')
p=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/runtime-paths.json')
before=json.loads(p.read_text())
subprocess.run(['systemctl','restart','kodi.service'],check=True,timeout=35,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
until=time.monotonic()+40
while time.monotonic()<until:
 try:
  players=rpc('Player.GetActivePlayers')
  after=json.loads(p.read_text())
  if after.get('subtitle_abi')=='ce-f9': break
 except Exception: pass
 time.sleep(.5)
else: raise RuntimeError('RESTART_NOT_READY')
print(json.dumps(dict(before=before,after=after,active=players,restarted=True)))
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('restart_wire',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try: rc,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=85)
    finally: client.close()
    output=ROOT/'review-evidence'/('ce-idle-restart-'+str(time.time_ns())+'.json')
    value=dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic))
    output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(output),**value)))
    raise SystemExit(1 if rc or diagnostic else 0)
