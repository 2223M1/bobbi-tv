"""Run an authorized, idle-only service recovery test, never restart Kodi."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--quiesce-only',action='store_true')
    parser.add_argument('--cycles',type=int,choices=range(1,5),default=1)
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('recovery_wire',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    run='/storage/.kodi/temp/bobbi-recovery-'+str(time.time_ns())
    code='''
import json,pathlib,subprocess,time
subprocess.run(['kodi-send','--action=RunScript('+RUN+'/trial.py)'],check=True,stdout=subprocess.DEVNULL)
path=pathlib.Path(RUN)/'result.json';until=time.monotonic()+52
while not path.exists() and time.monotonic()<until:time.sleep(.2)
print(path.read_text() if path.exists() else json.dumps(dict(state='pending',passed=None)))
'''
    try:
        with client.open_sftp() as sftp:
            sftp.mkdir(run,mode=0o700)
            payload='QUIESCE_ONLY='+repr(args.quiesce_only)+'\nCYCLES='+repr(args.cycles)+'\n'+(ROOT/'tools/ce_managed_recovery_remote.py').read_text(encoding='utf-8')
            with sftp.file(run+'/trial.py','wb') as script:
                script.write(payload.encode('utf-8'))
        rc,result,diagnostic=wire.readonly(client,('RUN='+repr(run)+'\n'+code).encode(),deadline_seconds=58)
    finally:client.close()
    from ce_standard_real import receipt_status
    value=dict(run=run,result=result,**receipt_status(result,rc,diagnostic))
    output=ROOT/'review-evidence'/('ce-managed-recovery-'+str(time.time_ns())+'.json')
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(output),**value),ensure_ascii=False))
    return value['exit_code']


if __name__=='__main__':raise SystemExit(main())
