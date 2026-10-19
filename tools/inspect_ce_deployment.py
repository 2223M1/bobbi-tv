"""Read a deployment receipt and bounded state without replaying any mutation."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,pathlib,subprocess,sys
run=pathlib.Path('/storage/.local/share/bobbi-private-deploy')/RUN_ID
receipt=run/'deployment.json'
out={'receipt_exists':receipt.is_file()}
if receipt.is_file():
    value=json.loads(receipt.read_text())
    out['receipt']={k:v for k,v in value.items() if k not in ('flags',)}
out['units']={name:{k:subprocess.check_output(['systemctl','show',name,'--property='+k,'--value'],timeout=4).decode().strip() for k in ('ActiveState','MainPID','UnitFileState')} for name in ('kodi.service','bobitv-preparation.service')}
out['new_profiles']={name:(pathlib.Path('/storage/.kodi/userdata/addon_data')/name).exists() for name in ('plugin.video.bobbi','script.module.bobbi.platform','skin.bobbi.cinema')}
if not receipt.is_file():
    # Repeat only read-only preconditions, not main/deploy.
    try:
        sys.dont_write_bytecode=True
        sys.path.insert(0,str(run))
        for name,expected in HASHES.items():
            path=run/name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('DEPLOY_INPUT_HASH')
        import controller
        if not (run/'bootstrap/addons').is_dir():
            raise ValueError('DEPLOY_BOOTSTRAP_NOT_STAGED')
        manifest=controller.bootstrap(run)
        if hasattr(controller,'transition_boundary'):
            controller.transition_boundary(run,manifest)
        out['profile_sentinels_checked']=sorted(controller.upgrade_profile_snapshot(check_stopped=False))
        out['pending_program_journal']=(controller.WORK/'journal.json').exists()
        from bobbi_core.runtime_paths import CE_F9_SHA256, known_ce_native
        pids=controller.command('pidof','kodi.bin').split()
        out['native_pids_count']=len(pids)
        if len(pids)==1:
            out['native_proc_sha256']=controller.running_native_sha256()
            out['native_expected']=known_ce_native(out['native_proc_sha256'])
            out['pin_sha256']=CE_F9_SHA256
        out['masks']={unit:(pathlib.Path('/run/systemd/system')/unit).is_symlink() for unit in controller.UNITS}
    except Exception as error:
        text=str(error)
        out['precondition_error']={'type':type(error).__name__,'code':text if re_safe(text) else 'see_local_trace'}
print(json.dumps(out,ensure_ascii=False))
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if not re.fullmatch('[0-9]{8}-[0-9]{6}',args.run_id):parser.error('timestamp required')
    frozen=json.loads((ROOT/'review-evidence/ce-deploy-runs'/(args.run_id+'.json')).read_text())
    if frozen['run']!='/storage/.local/share/bobbi-private-deploy/'+args.run_id:
        raise ValueError('Deployment run identity changed')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('inspect_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,wire=transport.connect()
    try:
        script='RUN_ID='+repr(args.run_id)+'\nHASHES='+repr(frozen['hashes'])+'\nimport re\ndef re_safe(v):return bool(re.fullmatch("[A-Z0-9_]{1,100}",v))\n'+REMOTE
        code,result,diag=wire.readonly(client,script.encode(),deadline_seconds=45)
    finally:client.close()
    path=ROOT/'review-evidence'/('ce-'+args.run_id+'-inspect.json')
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if code or diag:raise RuntimeError('inspection failed')

if __name__=='__main__':main()
