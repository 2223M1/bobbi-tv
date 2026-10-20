"""Launch/poll a finite real-source standard-adapter trial. No global stop."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--guid')
    parser.add_argument('--probe-next', action='store_true', help='Read-only same-release next-file diagnosis; no playback')
    parser.add_argument('--resume-percent',type=float,default=97)
    parser.add_argument('--poll',help='Exact earlier temporary trial directory')
    args=parser.parse_args()
    if not 90<=args.resume_percent<100: parser.error('Tail trial percent must be 90..100 exclusive')
    if args.poll and not re.fullmatch('/storage/.kodi/temp/bobbi-standard-real-[0-9]+',args.poll): parser.error('Invalid run path')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('standard_wire',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    run=args.poll or '/storage/.kodi/temp/bobbi-standard-real-'+str(time.time_ns())
    try:
        if not args.poll:
            with client.open_sftp() as sftp:
                sftp.mkdir(run,mode=0o700)
                sftp.put(str(ROOT/'tools/ce_standard_real_remote.py'),run+'/trial.py')
                with sftp.open(run+'/input.json','wx') as stream:
                    stream.write(json.dumps(dict(guid=args.guid,resume_percent=args.resume_percent,probe_next=args.probe_next)).encode())
        code='''
import json,pathlib,subprocess,time
if START: subprocess.run(['kodi-send','--action=RunScript('+RUN+'/trial.py)'],check=True,stdout=subprocess.DEVNULL)
path=pathlib.Path(RUN)/'result.json';until=time.monotonic()+40
while not path.exists() and time.monotonic()<until:time.sleep(.3)
print(path.read_text() if path.exists() else json.dumps(dict(state='running',passed=None)))
'''
        rc,result,diagnostic=wire.readonly(client,('RUN='+repr(run)+'\nSTART='+repr(not args.poll)+'\n'+code).encode(),deadline_seconds=48)
    finally:client.close()
    output=ROOT/'review-evidence'/('ce-standard-real-'+str(time.time_ns())+'.json')
    value=dict(run=run,result=result,exit_code=rc,diagnostic_present=bool(diagnostic))
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(output),**value),ensure_ascii=False))
    return 1 if rc or diagnostic or result.get('passed') is False else 0


if __name__=='__main__':raise SystemExit(main())
