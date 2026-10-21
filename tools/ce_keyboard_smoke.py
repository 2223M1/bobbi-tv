"""Stage and run the attended real keyboard probe; does not change accounts."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--probe',choices=('keyboard','library','personal'),default='keyboard')
    args=parser.parse_args()
    if args.probe=='personal':
        parser.error('Personal probe suspended after native-control lifetime crash; use ce_ui_preview screenshot --window personal for read-only visual acceptance')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('keyboard_wire',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    run='/storage/.kodi/temp/bobbi-'+args.probe+'-'+str(time.time_ns())
    probe='ce_'+args.probe+'_smoke_remote.py'
    destination=args.output/Path(run).name
    destination.mkdir(parents=True)
    try:
        with client.open_sftp() as sftp:
            sftp.mkdir(run,mode=0o700)
            for name in (probe,'ce_ui_preview_remote.py'):
                sftp.put(str(Path(__file__).with_name(name)),run+'/'+name)
        remote='''import json,subprocess,time,pathlib
from urllib.request import Request,build_opener,ProxyHandler
def rpc(method):
 q=Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method)).encode(),{'Content-Type':'application/json'})
 with build_opener(ProxyHandler({})).open(q,timeout=4) as f:return json.load(f)['result']
if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
subprocess.run(['kodi-send','--action=RunScript('+RUN+'/'+PROBE+')'],check=True,stdout=subprocess.DEVNULL)
deadline=time.monotonic()+50
p=pathlib.Path(RUN)/'result.json'
value=None
while time.monotonic()<deadline:
 try:value=json.loads(p.read_text())
 except (FileNotFoundError,ValueError):time.sleep(.2);continue
 if isinstance(value,dict):break
 value=None;time.sleep(.2)
print(json.dumps(value if value is not None else dict(passed=False,code='PROBE_TIMEOUT')))
'''
        rc,result,diag=wire.readonly(client,('RUN='+repr(run)+'\nPROBE='+repr(probe)+'\n'+remote).encode(),deadline_seconds=55)
        with client.open_sftp() as sftp:
            for name in ('keyboard-candidates.png','keyboard-selected.png','library-root.png','library-file.png','library-next.png',
                         'personal-directory.png','personal-page.png'):
                try:sftp.get(run+'/'+name,str(destination/name))
                except OSError:pass
            try:sftp.get(run+'/progress.json',str(destination/'progress.json'))
            except OSError:pass
        value=dict(exit_code=rc,diagnostic_present=bool(diag),run=run,result=result)
        (destination/'receipt.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(evidence=str(destination),**value),ensure_ascii=False))
        return int(bool(rc or diag or result.get('passed') is not True))
    finally:client.close()


if __name__=='__main__':raise SystemExit(main())
