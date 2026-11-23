"""Read only bounded installed generation/player state, never credentials."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

REMOTE = '''
import json,pathlib,sys,urllib.request,time
sys.dont_write_bytecode=True
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as r:return json.load(r).get('result')
out=dict(time=time.time(),players=rpc('Player.GetActivePlayers'),window=rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol']}))
root=pathlib.Path('/storage/.local/share/bobbi-private-updates')
out['program_state']={}
for name in ('state.json','journal.json','installed.json'):
 p=root/name
 if p.is_file():
  v=json.loads(p.read_text());out['program_state'][name]={k:v[k] for k in ('sequence','high_watermark','phase','state','active_sequence','previous_sequence') if k in v}
p=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json')
if p.is_file():
 v=json.loads(p.read_text());out['installer_state']={k:v[k] for k in ('sequence','high_watermark','phase','host_pending') if k in v}
out['versions']={}
for addon in ('script.bobbi.start','script.module.bobbi.platform','script.module.bobbi.core','plugin.video.bobbi'):
 out['versions'][addon]=rpc('Addons.GetAddonDetails',{'addonid':addon,'properties':['version','enabled']})
print(json.dumps(out))
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--transport-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('state_wire',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try:code,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=25)
    finally:client.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(transport_exit=code,diagnostic_present=bool(diagnostic),result=result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return 1 if code or diagnostic else 0


if __name__=='__main__':raise SystemExit(main())
