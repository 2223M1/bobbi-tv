"""Read-only diagnosis of one frozen maintenance upgrade, with safe categories."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '''
from pathlib import Path
import json,sys,traceback
sys.dont_write_bytecode=True
run=Path('/storage/.local/share/bobbi-private-deploy')/RUN
sys.path.insert(0,str(run))
import controller as c
result={}
receipt=run/'deployment.json'
result['receipt_exists']=receipt.exists()
if receipt.exists():
    result['receipt']=json.loads(receipt.read_text())
try:
    manifest=c.bootstrap(run)
    c.transition_boundary(run,manifest)
    c.require_clean_transaction()
    c.running_native_sha256()
    result['native']='passed'
    c.upgrade_profile_snapshot(check_stopped=False)
    result['profile']='passed'
    from bobbi_platform.offline_updates import SignedBundle,load_trust
    from contextlib import nullcontext
    with SignedBundle(run/'candidate.zip',load_trust(),'coreelec') as signed:
        engine=signed.engine(c.KODI/'addons',c.WORK,lambda:False,nullcontext)
        value=c.owned_generation(engine,engine.available())
        result['program_sequence']=value['sequence']
        c.upstream_preflight(run,engine)
        result['upstream']='passed'
    result['services']={}
    for unit in c.UNITS:
        for key in ('ActiveState','UnitFileState'):
            result['services'][unit+':'+key]=c.command('systemctl','show',unit,'--property='+key,'--value')
except Exception as error:
    result.update(error_type=type(error).__name__,reason=str(error),
        frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
print(json.dumps(result))
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    assert re.fullmatch('[0-9]{8}-[0-9]{6}',args.run)
    source=args.transport_source
    sys.path.insert(0,str(source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('wire',source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,('RUN='+repr(args.run)+'\n'+REMOTE).encode(),deadline_seconds=30)
    finally:client.close()
    value=dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic))
    (ROOT/'review-evidence'/('ce-upgrade-preflight-'+str(time.time_ns())+'.json')).write_text(
        json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value))
