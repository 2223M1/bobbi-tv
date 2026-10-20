"""Read-only device evidence for the general CE implementation round."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,urllib.request,pathlib,platform,struct
def rpc(method, params=None):
    request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:
        value=json.load(response)
    return value.get('result', {'error':True})
addons={}
for name in ('plugin.video.bobbi','script.module.bobbi.core','script.module.bobbi.platform'):
    value=rpc('Addons.GetAddonDetails', {'addonid':name,'properties':['version','enabled']})
    addons[name]=value.get('addon',value)
print(json.dumps(dict(active=rpc('Player.GetActivePlayers'),
    window=rpc('GUI.GetProperties',{'properties':['currentwindow']}),
    kodi=rpc('Application.GetProperties',{'properties':['version']}),addons=addons,
    remote_python_bits=struct.calcsize('P')*8,kernel=platform.machine())))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_probe_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,wire=transport.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=20)
    finally:
        client.close()
    output=ROOT/'review-evidence'/('ce-general-probe-'+str(time.time_ns())+'.json')
    value=dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic))
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(output),**value),ensure_ascii=False))
    if rc or diagnostic:
        raise SystemExit(1)


if __name__=='__main__':
    main()
