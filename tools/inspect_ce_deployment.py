"""Read a deployment receipt and bounded state without replaying any mutation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,os,pathlib,re,subprocess,sys,types,zipfile
sys.dont_write_bytecode=True

def plain(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('DEPLOY_INPUT_PATH')
    return path

def input_bytes(path, expected, keep=False):
    plain(path)
    if not path.is_file():
        raise ValueError('DEPLOY_INPUT_MISSING')
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    before=stamp(path.stat())
    digest=hashlib.sha256()
    saved=bytearray()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
            if keep:
                saved.extend(block)
                if len(saved)>2*1024*1024:
                    raise ValueError('DEPLOY_INSPECTION_SOURCE_LIMIT')
        during=stamp(os.fstat(stream.fileno()))
    plain(path)
    if before!=stamp(path.stat()) or before[:4]!=during[:4]:
        raise ValueError('DEPLOY_INPUT_CHANGED')
    if digest.hexdigest()!=expected:
        raise ValueError('DEPLOY_INPUT_HASH')
    return bytes(saved)

def verified_inputs(run):
    required={'candidate.zip','controller.py'}
    allowed=required|{'ce_state_migration.py','transition-baseline.json'}
    if (type(HASHES) is not dict or not required<=set(HASHES)<=allowed
            or any(type(v) is not str or not re.fullmatch('[a-f0-9]{64}',v) for v in HASHES.values())):
        raise ValueError('DEPLOY_INPUT_FIELDS')
    controller_source=None
    for name,expected in HASHES.items():
        keep=CAPACITY is not None and name=='controller.py'
        raw=input_bytes(run/name,expected,keep)
        if keep:
            controller_source=raw.decode('utf-8')
    return controller_source

def manifest_summary(value):
    # Bounded display fields only, not another manifest admission policy.
    if (type(value) is not dict or type(value.get('schema')) is not int
            or type(value.get('sequence')) is not int
            or not 0<=value['sequence']<2**63
            or type(value.get('components')) is not list or len(value['components'])>256):
        raise ValueError('DEPLOY_INSPECTION_MANIFEST')
    ids=[]
    for row in value['components']:
        if (type(row) is not dict or type(row.get('id')) is not str
                or not re.fullmatch('[a-z0-9][a-z0-9._-]{0,127}',row['id'])):
            raise ValueError('DEPLOY_INSPECTION_MANIFEST')
        ids.append(row['id'])
    return dict(schema=value['schema'],sequence=value['sequence'],component_ids=ids)

def historical_manifest(run):
    # Hash-only historical diagnostics never import the old controller or any
    # candidate module and never claim to have re-verified its signature.
    with zipfile.ZipFile(plain(run/'candidate.zip')) as source:
        matches=[row for row in source.infolist() if row.filename=='release.json']
        if len(matches)!=1 or matches[0].file_size>1024*1024:
            raise ValueError('DEPLOY_INSPECTION_MANIFEST_LIMIT')
        with source.open(matches[0]) as stream:
            raw=stream.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError('DEPLOY_INSPECTION_MANIFEST_LIMIT')
    return json.loads(raw)

run=plain(pathlib.Path(RUN))
receipt=plain(run/'deployment.json')
out={'receipt_exists':receipt.is_file()}
if receipt.is_file():
    value=json.loads(receipt.read_text())
    out['receipt']={k:v for k,v in value.items() if k not in ('flags',)}
out['units']={name:{k:subprocess.check_output(['systemctl','show',name,'--property='+k,'--value'],timeout=4).decode().strip() for k in ('ActiveState','MainPID','UnitFileState')} for name in ('kodi.service','bobitv-preparation.service')}
out['new_profiles']={name:(pathlib.Path('/storage/.kodi/userdata/addon_data')/name).exists() for name in ('plugin.video.bobbi','script.module.bobbi.platform','skin.bobbi.cinema')}
if not receipt.is_file():
    out['diagnostic_scope']='signed-bundle-read-only' if CAPACITY is not None else 'frozen-input-hash-only'
    out['current_signature_verified']=False
    out['not_checked']=['account_state','native_binary','deployment_preconditions']
    try:
        source=verified_inputs(run)
        if CAPACITY is None:
            manifest=historical_manifest(run)
        else:
            if type(CAPACITY) is not dict or CAPACITY.get('candidate_sha256')!=HASHES['candidate.zip']:
                raise ValueError('DEPLOY_CAPACITY_INPUT_HASH')
            exec(RUNTIME_LOADER)
            controller=types.ModuleType('inspection_controller')
            controller.__file__=str(run/'controller.py')
            exec(compile(source,controller.__file__,'exec'),controller.__dict__)
            controller.PREFLIGHT=package
            # This is the only controller call: no bootstrap, engine, lease,
            # recovery, profile migration or service-control path is entered.
            manifest=controller.inspect_bundle(run)
        summary=manifest_summary(manifest)
        verified_inputs(run)  # Bind the displayed manifest to unchanged inputs.
        out['manifest']=summary
        out['input_hashes_verified']=True
        out['current_signature_verified']=CAPACITY is not None
    except Exception as error:
        text=str(error)
        out['precondition_error']={'type':type(error).__name__,'code':text if re_safe(text) else 'see_local_trace'}
print(json.dumps(out,ensure_ascii=False))
'''


def runtime_loader():
    """Reuse the driver's reviewed in-memory runtime without candidate imports."""
    spec=importlib.util.spec_from_file_location('inspection_driver',ROOT/'tools/deploy_ce_candidate.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RUNTIME_LOADER


def script_for(run_id, frozen):
    if not re.fullmatch('[0-9]{8}-[0-9]{6}',run_id):
        raise ValueError('DEPLOY_RUN_ID')
    run='/storage/.local/share/bobbi-private-deploy/'+run_id
    if type(frozen) is not dict or frozen.get('run')!=run:
        raise ValueError('Deployment run identity changed')
    capacity=frozen.get('capacity')
    return ('RUN='+repr(run)+'\nHASHES='+repr(frozen['hashes'])+'\nCAPACITY='+repr(capacity)
            +'\nRUNTIME_LOADER='+repr(runtime_loader() if capacity is not None else '')
            +'\ndef re_safe(v):return bool(re.fullmatch("[A-Z0-9_]{1,100}",v))\n'+REMOTE)

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if not re.fullmatch('[0-9]{8}-[0-9]{6}',args.run_id):parser.error('timestamp required')
    frozen=json.loads((ROOT/'review-evidence/ce-deploy-runs'/(args.run_id+'.json')).read_text())
    script=script_for(args.run_id,frozen)
    path=args.output or ROOT/'review-evidence'/('ce-'+args.run_id+'-inspect.json')
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or not path.parent.is_dir():
        raise ValueError('DEPLOY_INSPECTION_OUTPUT_PATH')
    # Reserve before loading transport or connecting. An unknown attempt remains
    # visible, and an existing inspection can never be overwritten by a retry.
    with path.open('x',encoding='utf-8') as stream:
        json.dump(dict(state='unconfirmed',operation='deployment-inspection'),stream)
        stream.flush()
        os.fsync(stream.fileno())
        sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
        spec=importlib.util.spec_from_file_location('inspect_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
        transport=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transport)
        client,wire=transport.connect()
        try:
            code,result,diag=wire.readonly(client,script.encode(),deadline_seconds=45)
        finally:client.close()
        stream.seek(0)
        stream.truncate()
        json.dump(result,stream,indent=2,ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(result,ensure_ascii=False))
    if code or diag:raise RuntimeError('inspection failed')

if __name__=='__main__':main()
