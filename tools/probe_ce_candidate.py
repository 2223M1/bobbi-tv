"""Read-only pinned CE capability/network evidence. No credential values emitted."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib, json, pathlib, struct, subprocess, time, urllib.request, urllib.error, socket
def rpc(method, params=None):
    req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as reply:
        return json.load(reply).get('result')
pids=subprocess.check_output(['pidof','kodi.bin']).decode().split()
result={'schema':1,'mode':'readonly','timestamp':time.time(),'kodi_processes':len(pids)}
if len(pids)==1:
    exe=pathlib.Path('/proc')/pids[0]/'exe'
    with exe.open('rb') as stream: raw=stream.read(20)
    result['kodi_elf']={'class':raw[4], 'machine':struct.unpack('<H',raw[18:20])[0]}
    digest=hashlib.sha256()
    with exe.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    result['kodi_elf']['sha256']=digest.hexdigest()
result['application']=rpc('Application.GetProperties',{'properties':['version','name']})
result['players']=rpc('Player.GetActivePlayers')
methods=rpc('JSONRPC.Introspect',{'getdescriptions':False,'getmetadata':False})['methods']
result['native_methods']=sorted(m for m in methods if m.startswith('Player.Bobi'))
result['network']={}
for name,url in [('tmdb','https://api.themoviedb.org/3/configuration'),('image','https://image.tmdb.org/t/p/w92/invalid.jpg')]:
    began=time.monotonic()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=5) as reply:
            code=reply.status
        result['network'][name]={'http':code,'configured_proxy':False}
    except urllib.error.HTTPError as e:
        result['network'][name]={'http':e.code,'configured_proxy':False}
    except Exception as e:
        result['network'][name]={'error':type(e).__name__,'configured_proxy':False}
    result['network'][name]['seconds']=round(time.monotonic()-began,3)
result['network']['qualification']='API authentication and nontransparent routing are not proved by these unauthenticated reads.'
print(json.dumps(result))
'''


def run(source, output):
    sys.path.insert(0, str(source/'ui-redesign/runtime/ssh-python'))
    path=source/'ui-redesign/tools/device_transport.py'
    spec=importlib.util.spec_from_file_location('pinned_bobbi_ce',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client,wire=module.connect()
    try:
        code,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=40)
        if code or diagnostic:
            raise RuntimeError('Readonly capability probe failed')
    finally:
        client.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'review-evidence/ce-readonly-preflight.json')
    args=parser.parse_args()
    run(args.transport_source,args.output)
