"""Stage an isolated UI script; collect native receipts and screenshots."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--collect', help='Read a retained, already launched exact smoke run')
    args = parser.parse_args()
    sys.path.insert(0, str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ui_wire', args.transport_source/'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    if args.collect and not re.fullmatch(r'bobbi-ui-smoke-[0-9]+', args.collect):
        parser.error('Exact retained smoke name required')
    run = '/storage/.kodi/temp/'+(args.collect or 'bobbi-ui-smoke-'+str(time.time_ns()))
    output = ROOT/'review-evidence'/(Path(run).name+('-collection-'+str(time.time_ns()) if args.collect else ''))
    output.mkdir()
    script = r'''
import json,pathlib,subprocess,time,urllib.request
request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',data=b'{"jsonrpc":"2.0","id":1,"method":"Player.GetActivePlayers"}',headers={'Content-Type':'application/json'})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:
 if json.load(response)['result']: raise RuntimeError('PLAYBACK_ACTIVE')
if not COLLECT:subprocess.run(['kodi-send','--action=RunScript('+RUN+'/smoke.py)'],check=True,stdout=subprocess.DEVNULL)
path=pathlib.Path(RUN)/'result.json'
until=time.monotonic()+(0 if COLLECT else 40)
while not path.exists() and time.monotonic()<until: time.sleep(.3)
print(path.read_text() if path.exists() else json.dumps(dict(passed=False,error='UI_SMOKE_TIMEOUT')))
'''
    try:
        if not args.collect:
            with client.open_sftp() as sftp:
                sftp.mkdir(run, mode=0o700)
                sftp.put(str(ROOT/'tools/ce_ui_smoke_remote.py'), run+'/smoke.py')
                sftp.put(str(ROOT/'tools/ce_ui_preview_remote.py'), run+'/ce_ui_preview_remote.py')
        rc, result, diagnostic = wire.readonly(client, ('RUN='+repr(run)+'\nCOLLECT='+repr(bool(args.collect))+'\n'+script).encode(), deadline_seconds=48)
        (output/'result.json').write_text(json.dumps(dict(exit_code=rc,result=result,
            diagnostic_present=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with client.open_sftp() as sftp:
            for name in ('account','terminal','metadata','sources-before','sources-after'):
                try: sftp.get(run+'/'+name+'.png',str(output/(name+'.png')))
                except OSError: pass
            for name in ('smoke-stack.txt','progress.json'):
                try: sftp.get(run+'/'+name,str(output/name))
                except OSError: pass
    finally:
        client.close()
    print(json.dumps(dict(evidence=str(output),**result),ensure_ascii=False))
    return 1 if rc or diagnostic or not result.get('passed') else 0


if __name__ == '__main__': raise SystemExit(main())
