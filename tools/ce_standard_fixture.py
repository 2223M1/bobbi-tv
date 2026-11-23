"""Attended standard-adapter fixture runner; never modifies installed addons."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--clip',type=Path,required=True)
    args=parser.parse_args()
    source=args.transport_source
    sys.path.insert(0,str(source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('wire',source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    run='/storage/.kodi/temp/bobbi-standard-fixture-'+str(time.time_ns())
    try:
        with client.open_sftp() as sftp:
            sftp.mkdir(run,mode=0o700)
            sftp.put(str(ROOT/'tools/ce_standard_fixture_remote.py'),run+'/fixture.py')
            for name in ('a.mp4','b.mp4'):sftp.put(str(args.clip),run+'/'+name)
            sftp.put(str(ROOT/'tests/fixtures/standard-fixture.zh.srt'),run+'/fixture.zh.srt')
        code='''
import json,pathlib,subprocess,time,urllib.request
request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',data=b'{"jsonrpc":"2.0","id":1,"method":"Player.GetActivePlayers"}',headers={'Content-Type':'application/json'})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:
    assert json.load(response)['result']==[], 'PLAYBACK_ACTIVE'
subprocess.run(['kodi-send','--action=RunScript('+RUN+'/fixture.py)'],check=True,stdout=subprocess.DEVNULL)
path=pathlib.Path(RUN)/'result.json'
until=time.monotonic()+48
while not path.exists() and time.monotonic()<until:time.sleep(.3)
print(path.read_text() if path.exists() else json.dumps({'passed':False,'error':'FIXTURE_TIMEOUT'}))
'''
        rc,result,diagnostic=wire.readonly(client,('RUN='+repr(run)+'\n'+code).encode(),deadline_seconds=55)
    finally:client.close()
    value=dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic),temporary_device_directory=run)
    path=ROOT/'review-evidence'/('ce-standard-device-fixture-'+str(time.time_ns())+'.json')
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(path),**value)))
    if rc or diagnostic or not result.get('passed'):raise SystemExit(1)
