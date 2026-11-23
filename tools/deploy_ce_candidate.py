"""Pinned CE deployment driver; on-device accounts never enter local artifacts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SEQUENCE = 2026101905
# Frozen from the signed 1905 CE generation, not from the incoming bundle.
# The inventory grows once; the public verification key must not change.
BASELINE_COMPONENTS = (
    'plugin.video.bobbi', 'plugin.video.bobbi.library', 'repository.bobbi',
    'resource.uisounds.bobbi-modern', 'script.bobbi.opensubtitles',
    'script.bobbi.setup', 'script.bobbi.start', 'script.module.bobbi.catalog',
    'script.module.bobbi.core', 'script.module.bobbi.mdsub', 'script.module.bobbi.platform',
    'script.module.certifi', 'script.module.chardet', 'script.module.idna',
    'script.module.infotagger', 'script.module.jurialmunkey', 'script.module.requests',
    'script.module.routing', 'script.module.urllib3', 'script.skinvariables', 'skin.bobbi.cinema',
)
ADDED_COMPONENT = 'plugin.video.bobbi.torrent'
TRANSITION_COMPONENTS = tuple(sorted(BASELINE_COMPONENTS + (ADDED_COMPONENT,)))
BASELINE_KEY_SHA256 = '96e4adef8fa6b3a4cba6f4ea096672e4080f4a292afb0b50b75b95b4400577fc'


def _key_digest(key):
    if (not isinstance(key, dict) or set(key) != {'algorithm', 'n', 'e'}
            or key['algorithm'] != 'RSA3072-SHA256' or type(key['e']) is not int
            or key['e'] != 65537 or not isinstance(key['n'], str)
            or re.fullmatch('[a-f0-9]{768}', key['n']) is None):
        raise ValueError('CE_TRANSITION_KEY_FIELDS')
    return hashlib.sha256(json.dumps(key, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_transition(value, candidate_sha256, manifest, trust):
    """Validate the exact one-component migration, never a new trust grant.

    The remote controller checks the same document against its externally
    frozen input hash. This maintainer-side entry additionally pins the 1905
    inventory and public-key fingerprint independently of candidate content.
    """
    if (not isinstance(value, dict) or set(value) != {
            'schema', 'baseline_sequence', 'from_components', 'to_components', 'key',
            'candidate_sha256', 'candidate_sequence'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['baseline_sequence']) is not int
            or value['baseline_sequence'] != BASELINE_SEQUENCE
            or type(value['from_components']) is not list
            or value['from_components'] != list(BASELINE_COMPONENTS)
            or type(value['to_components']) is not list
            or value['to_components'] != list(TRANSITION_COMPONENTS)
            or not isinstance(candidate_sha256, str)
            or re.fullmatch('[a-f0-9]{64}', candidate_sha256) is None
            or value['candidate_sha256'] != candidate_sha256
            or type(value['candidate_sequence']) is not int
            or value['candidate_sequence'] <= BASELINE_SEQUENCE):
        raise ValueError('CE_TRANSITION_FIELDS')
    if (_key_digest(value['key']) != BASELINE_KEY_SHA256
            or not isinstance(trust, dict) or set(trust) != {'schema', 'key', 'components'}
            or type(trust['schema']) is not int or trust['schema'] != 1
            or type(trust['components']) is not list
            or trust['components'] != list(TRANSITION_COMPONENTS)
            or trust['key'] != value['key']):
        raise ValueError('CE_TRANSITION_TRUST_CHANGED')
    if (not isinstance(manifest, dict)
            or set(manifest) != {'schema', 'channel', 'profile', 'sequence', 'components'}
            or type(manifest['schema']) is not int or manifest['schema'] != 2
            or manifest['channel'] != 'private-candidate' or manifest['profile'] != 'coreelec'
            or type(manifest['sequence']) is not int
            or manifest['sequence'] != value['candidate_sequence']
            or type(manifest['components']) is not list
            or len(manifest['components']) != len(TRANSITION_COMPONENTS)
            or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                   for row in manifest['components'])
            or sorted(row['id'] for row in manifest['components']) != list(TRANSITION_COMPONENTS)):
        raise ValueError('CE_TRANSITION_MANIFEST_CHANGED')
    return value


def _stream_sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def _file_sha256(path):
    with path.open('rb') as stream:
        return _stream_sha256(stream)


def transition_baseline(bundle):
    """Check the complete signed 22-component generation before connecting."""
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
    from bobbi_platform.offline_updates import SignedBundle, load_trust
    trust = load_trust(ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/release_trust.json')
    # Validate the key and inventory before accepting any candidate code/data.
    if (_key_digest(trust['key']) != BASELINE_KEY_SHA256
            or trust['components'] != list(TRANSITION_COMPONENTS)):
        raise ValueError('CE_TRANSITION_TRUST_CHANGED')
    with SignedBundle(bundle, trust, 'coreelec') as source:
        manifest = source.check_all()
        stream = source.archive.fp
        position = stream.tell()
        try:
            stream.seek(0)
            digest = _stream_sha256(stream)
        finally:
            stream.seek(position)
        value = dict(schema=1, baseline_sequence=BASELINE_SEQUENCE,
            from_components=list(BASELINE_COMPONENTS), to_components=list(TRANSITION_COMPONENTS),
            key=trust['key'], candidate_sha256=digest, candidate_sequence=manifest['sequence'])
        validate_transition(value, digest, manifest, trust)
    if _file_sha256(bundle) != digest:
        raise ValueError('CE_TRANSITION_BUNDLE_CHANGED')
    return value


def capacity_inputs(bundle, digest):
    """Trusted metadata/code only; no candidate program is imported locally."""
    from bobbi_platform.offline_updates import SignedBundle, load_trust
    from bobbi_platform.ce_storage import bundle_layout
    root = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform'
    trust = load_trust(root/'release_trust.json')
    with SignedBundle(bundle, trust, 'coreelec') as source:
        layout = bundle_layout(source)
    if _file_sha256(bundle) != digest:
        raise ValueError('CE_TRANSITION_BUNDLE_CHANGED')
    modules = []
    for name in ('updates', 'upstream_addons', 'signatures', 'offline_updates', 'ce_storage'):
        raw = (root/(name+'.py')).read_text(encoding='utf-8')
        modules.append(dict(name=name, source=raw, sha256=hashlib.sha256(raw.encode()).hexdigest()))
    return dict(layout=layout, runtime=dict(modules=modules, trust=trust), candidate_sha256=digest)


RUNTIME_LOADER = '''
import types
package=types.ModuleType('_bobbi_capacity')
package.__path__=[]
sys.modules[package.__name__]=package
for row in CAPACITY['runtime']['modules']:
    if hashlib.sha256(row['source'].encode()).hexdigest()!=row['sha256']:
        raise ValueError('DEPLOY_CAPACITY_INPUT_HASH')
    name=package.__name__+'.'+row['name']
    module=types.ModuleType(name)
    module.__file__='/trusted-memory/'+row['name']+'.py'
    module.__package__=package.__name__
    sys.modules[name]=module
    exec(compile(row['source'],module.__file__,'exec'),module.__dict__)
    setattr(package,row['name'],module)
package.trust=CAPACITY['runtime']['trust']
'''


def upload_preflight(client, wire, run, capacity, inputs, hashes, receipt_path=None):
    """Runs before SFTP open/mkdir/put. The remote side writes no helper files."""
    controller = inputs['controller.py'].read_text(encoding='utf-8')
    if (capacity['candidate_sha256'] != hashes['candidate.zip']
            or any(_file_sha256(path) != hashes[name] for name, path in inputs.items())):
        raise ValueError('DEPLOY_INPUT_HASH')
    sizes = [path.stat().st_size for path in inputs.values()]
    script = ('import hashlib,json,pathlib,re,sys\nsys.dont_write_bytecode=True\nCAPACITY='+repr(capacity)+'\n'
              +RUNTIME_LOADER+'\ncontroller=types.ModuleType("trusted_controller")\n'
              +'exec(compile('+repr(controller)+',"<trusted-controller>","exec"),controller.__dict__)\n'
              +'controller.PREFLIGHT=package\n'
              +'try:\n    report=controller.preupload_space(pathlib.Path('+repr(run)+'),CAPACITY["layout"],'+repr(sizes)+')\n'
              +'    print(json.dumps(dict(state="space-ready",space=report)))\n'
              +'except Exception as error:\n    print(json.dumps(dict(state="failed",error=type(error).__name__,reason=str(error) if re.fullmatch("[A-Z_]{1,80}",str(error)) else None,space=getattr(error,"space",None))))\n    sys.exit(1)\n').encode()
    try:
        code, result, diagnostic = wire.readonly(client, script, deadline_seconds=55)
    except Exception as error:
        if receipt_path is not None:
            with receipt_path.open('x', encoding='utf-8') as stream:
                json.dump(dict(state='unconfirmed', error=type(error).__name__, remote_writes=False), stream)
        raise
    if receipt_path is not None:
        # Only generated numeric capacity fields and bounded classifications;
        # never remote diagnostics, paths, database contents or account data.
        report = result.get('space')
        safe = None
        if isinstance(report, dict):
            safe = {key: report[key] for key in ('schema','complete','fits','required_bytes','free_bytes')
                    if key in report and (type(report[key]) in (int, bool))}
            if re.fullmatch('[a-z-]{1,64}', str(report.get('phase',''))):
                safe['phase'] = report['phase']
            for group, fields in (('parts', ('bytes','inodes','device')),
                                  ('filesystems', ('device','unit','free_bytes','free_inodes','required_bytes','required_inodes'))):
                safe[group] = []
                rows = report.get(group)
                for row in (rows[:256] if isinstance(rows, list) else []):
                    if not isinstance(row, dict):
                        continue
                    value = {key:row[key] for key in fields if key in row and
                             (type(row[key]) is int or row[key] is None)}
                    if group == 'parts' and re.fullmatch('[a-z-]{1,64}', str(row.get('kind',''))):
                        value['kind'] = row['kind']
                    safe[group].append(value)
        with receipt_path.open('x', encoding='utf-8') as stream:
            json.dump(dict(state='space-ready' if result.get('state') == 'space-ready' else 'failed',
                           exit_code=code, diagnostic_present=bool(diagnostic), space=safe,
                           error=str(result.get('error',''))[:64] if re.fullmatch('[A-Za-z_]{0,64}', str(result.get('error',''))) else 'UnknownError',
                           reason=result.get('reason') if re.fullmatch('[A-Z_]{1,80}', str(result.get('reason',''))) else None,
                           remote_writes=False), stream, indent=2)
    if code or diagnostic or result.get('state') != 'space-ready':
        raise RuntimeError('CE_UPLOAD_SPACE_UNPROVEN')
    return result['space']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--mode', choices=('stage', 'deploy', 'upgrade', 'clean-install', 'rollback', 'status'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'dist/private-releases/bobbi-private-2026101903-coreelec.bobbi-update.zip')
    args = parser.parse_args()
    if not re.fullmatch('[0-9]{8}-[0-9]{6}', args.run_id):
        parser.error('Use a timestamp run ID')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('pinned_deploy', args.transport_source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    run = '/storage/.local/share/bobbi-private-deploy/' + args.run_id
    input_record = ROOT / 'review-evidence/ce-deploy-runs' / (args.run_id + '.json')
    if args.mode == 'stage':
        if input_record.exists():
            raise FileExistsError('Deployment run already frozen')
        transition = transition_baseline(args.bundle)
        capacity = capacity_inputs(args.bundle, transition['candidate_sha256'])
        transition_path = input_record.with_suffix('.transition-baseline.json')
        input_record.parent.mkdir(parents=True, exist_ok=True)
        with transition_path.open('x', encoding='utf-8') as stream:
            json.dump(transition, stream, indent=2)
        inputs = {'candidate.zip': args.bundle, 'controller.py': ROOT / 'tools/deploy_ce_remote.py',
                  'ce_state_migration.py': ROOT / 'tools/ce_state_migration.py',
                  'transition-baseline.json': transition_path}
        hashes = {name: _file_sha256(path) for name, path in inputs.items()}
        if hashes['candidate.zip'] != transition['candidate_sha256']:
            raise ValueError('CE_TRANSITION_BUNDLE_CHANGED')
        with input_record.open('x', encoding='utf-8') as stream:
            json.dump(dict(run=run, hashes=hashes, capacity=capacity), stream, indent=2)
    else:
        frozen = json.loads(input_record.read_text(encoding='utf-8'))
        if frozen['run'] != run:
            raise ValueError('Deployment run identity changed')
        hashes = frozen['hashes']
        capacity = frozen.get('capacity')
    client, wire = transport.connect()
    try:
        if args.mode == 'stage':
            upload_preflight(client, wire, run, capacity, inputs, hashes,
                             input_record.with_suffix('.capacity.json'))
            with client.open_sftp() as sftp:
                current = ''
                for part in run.split('/')[1:-1]:
                    current += '/' + part
                    try:
                        sftp.mkdir(current, mode=0o700)
                    except IOError:
                        if not sftp.stat(current).st_mode & 0o040000:
                            raise
                sftp.mkdir(run, mode=0o700)  # A run is immutable; never reuse it.
                for name, path in inputs.items():
                    if _file_sha256(path) != hashes[name]:
                        raise ValueError('DEPLOY_INPUT_HASH')
                    sftp.put(str(path), run + '/' + name)
                    sftp.chmod(run + '/' + name, 0o600)
        payload = '''
import hashlib,json,pathlib,re,sys
sys.dont_write_bytecode=True
run=pathlib.Path(RUN)
try:
    for name,expected in HASHES.items():
        path=run/name
        if path.is_symlink():
            raise ValueError('DEPLOY_INPUT_HASH')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                digest.update(block)
        if digest.hexdigest()!=expected:
            raise ValueError('DEPLOY_INPUT_HASH')
    sys.path.insert(0,str(run))
    import controller
    if CAPACITY is not None:
        exec(RUNTIME_LOADER)
        controller.PREFLIGHT=package
    print(json.dumps(controller.main(run,MODE),ensure_ascii=False))
except Exception as error:
    print(json.dumps(dict(state='failed',error=type(error).__name__,receipt=str(run/'deployment.json'),
        reason=str(error) if re.fullmatch('[A-Z_]{1,80}',str(error)) else None,space=getattr(error,'space',None))))
    sys.exit(1)
'''
        script = ('RUN=' + repr(run) + '\nMODE=' + repr(args.mode) + '\nHASHES=' + repr(hashes)
                  + '\nCAPACITY=' + repr(capacity) + '\nRUNTIME_LOADER=' + repr(RUNTIME_LOADER) + '\n' + payload).encode()
        output = ROOT / 'review-evidence' / ('ce-' + args.run_id + '-' + args.mode + '.json')
        output.parent.mkdir(exist_ok=True)
        try:
            code, result, diagnostic = wire.readonly(client, script, deadline_seconds=550 if args.mode in ('deploy','upgrade','clean-install','rollback') else 55)
        except Exception as error:
            output.write_text(json.dumps(dict(state='unconfirmed', error=type(error).__name__,
                run=run, instruction='Inspect the existing run before any retry; transport loss does not prove remote failure.'), indent=2) + '\n', encoding='utf-8')
            raise
        output.write_text(json.dumps(dict(exit_code=code, result=result, diagnostic_present=bool(diagnostic)), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        if code or diagnostic or result.get('state') == 'failed':
            raise RuntimeError('CE operation failed; inspect bounded deployment receipt')
    finally:
        client.close()


if __name__ == '__main__':
    main()
