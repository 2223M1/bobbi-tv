"""One pinned private Kodi overlay transition. Firmware and old overlay stay intact."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1]
OLD = '8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
CANDIDATE = 'd750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3'
OLD_LAUNCH = '8cae53ac635e5178c6c671a9f90dd90faeb26f702358b571de46fafe8d68d815'
OLD_CONF = '0175d071e2d5a15851625e890d982cc0c43ba6b80c05b3449124dd7eb6904842'
HANDOFF_CANDIDATE = '632758f5d1ca5494e9b049446d3908bead70589b4d18640bb5d06e830a2b57eb'
ENTRY_GENERATION_PATH = '/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json'
LEGACY_GENERATION_PATH = '/storage/.local/share/bobbi-private-updates/state.json'
PROFILES = {
    'schema2043': dict(candidate='ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991',
        sequence=2026102043, tag='2043', base='/storage/.local/share/bobbi-native/2026102043',
        layout=ROOT.parent/'ce2029-results-20261021/ce2043-native-predecessor8bb2.json',
        reports=ROOT.parent/'ce2029-results-20261021', deadline=330,
        generation_kind='entry_complete', generation_path=ENTRY_GENERATION_PATH,
        baseline_proof='/mnt/d/AM6B-Project/ce2035-native-handoff-20261022/run-1792601381159946071/build-result.json',
        baseline_proof_sha256='fa83d57af4b3d6e3bf47387a6789a645a9b452b24b968b5f91a5c882bc1c4d02',
        build_proof_sha256='30e1e3008b3a8fe86d7f2036039476c654237c9f5a93ced03418f0e327749074',
        predecessor_proof='/mnt/d/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431/build-result.json',
        predecessor_proof_sha256='0c6069fe71c83c491dd48f363ca44efb3c2dbd775aa8fd0aaccc944c6aca52c9',
        verification_sha256='db04c3a39dcdcd1e2732879ad71e235490cb86825a4fc6cdc013f8861ad172e0',
        predecessor=dict(binary='8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14',
            conf='0b00375d980005c9e382fc477e583389e96b36123a0f7a82789ce6683e8b17e4',
            launch='b878104fae9ae9a0f823a0888db9f49658609c1860ac4fe51c6fe512f2fdafba',
            binary_path='/storage/.local/share/bobbi-native/2026102038/kodi.bin',
            launch_path='/storage/.local/share/bobbi-native/2026102038/launch.py')),
    'directory1908': dict(candidate=CANDIDATE, sequence=2026101908, tag='1908',
        base='/storage/.local/share/bobbi-native/2026101908',
        layout=ROOT/'review-evidence/ce-native-layout-before1908.json',
        reports=ROOT/'review-evidence', deadline=110),
    'handoff2035': dict(candidate=HANDOFF_CANDIDATE, sequence=2026102035, tag='2035',
        base='/storage/.local/share/bobbi-native/2026102035',
        layout=ROOT.parent/'ce2029-results-20261021/ce2035-native-baseline-current.json',
        reports=ROOT.parent/'ce2029-results-20261021', deadline=330,
        generation_kind='entry_complete', generation_path=ENTRY_GENERATION_PATH,
        baseline_proof='/mnt/d/AM6B-Project/ce2035-native-handoff-20261022/run-1792601381159946071/build-result.json',
        baseline_proof_sha256='fa83d57af4b3d6e3bf47387a6789a645a9b452b24b968b5f91a5c882bc1c4d02'),
    'audio2038': dict(candidate='8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14',
        sequence=2026102038, tag='2038', base='/storage/.local/share/bobbi-native/2026102038',
        layout=ROOT.parent/'ce2029-results-20261021/ce2038-native-predecessor632.json',
        reports=ROOT.parent/'ce2029-results-20261021', deadline=330,
        generation_kind='entry_complete', generation_path=ENTRY_GENERATION_PATH,
        baseline_proof='/mnt/d/AM6B-Project/ce2035-native-handoff-20261022/run-1792601381159946071/build-result.json',
        baseline_proof_sha256='fa83d57af4b3d6e3bf47387a6789a645a9b452b24b968b5f91a5c882bc1c4d02',
        build_proof_sha256='0c6069fe71c83c491dd48f363ca44efb3c2dbd775aa8fd0aaccc944c6aca52c9',
        predecessor=dict(binary=HANDOFF_CANDIDATE,
            conf='c07176497c16359ea91eedc4534c2fed4e48e4a00c5d364a9f41a6402ccf1aaa',
            launch='5f0d942f9d79ee87f700601d4bb48d7d975b690024bdeb3f56518d3801abd51b',
            binary_path='/storage/.local/share/bobbi-native/2026102035/kodi.bin',
            launch_path='/storage/.local/share/bobbi-native/2026102035/launch.py')),
}
REMOTE = r'''
import hashlib,json,os,pathlib,subprocess,tempfile,time,urllib.request
REMOTE_STAGE='staged_files'
base=pathlib.Path(globals().get('BASE','/storage/.local/share/bobbi-native/2026101908'))
conf=pathlib.Path('/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as stream:
  for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def command(*args):return subprocess.check_output(args,timeout=30).decode().strip()
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as r:return json.load(r)['result']
def native_sha():
 pids=command('pidof','kodi.bin').split()
 assert len(pids)==1,'NATIVE_PROCESS_COUNT'
 return sha(pathlib.Path('/proc')/pids[0]/'exe')
def atomic(path,data):
 fd,name=tempfile.mkstemp(prefix=path.name+'.bobbi'+globals().get('PROFILE_TAG','1908')+'-',dir=str(path.parent))
 temp=pathlib.Path(name)
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()
def ready(expected):
 end=time.monotonic()+40
 while time.monotonic()<end:
  try:
   if native_sha()==expected and isinstance(rpc('Player.BobiState'),dict):return True
  except Exception:pass
  time.sleep(1)
 return False

def checked_record():
 record=json.loads(receipt.read_text())
 assert isinstance(record,dict) and isinstance(record.get('history',[]),list),'RECEIPT_INVALID'
 expected=dict(old_conf_sha256=OLD_CONF,new_conf_sha256=HASHES['next.conf'],old_sha256=OLD,new_sha256=HASHES['kodi.bin'])
 assert all(record.get(key)==value for key,value in expected.items()),'RECEIPT_PIN_MISMATCH'
 return record

def transition(record,state,**updates):
 # Retain every prior receipt state, including recovery failures; never erase
 # or lower program generation state to repeat a reviewed native transition.
 history=list(record.get('history',[]))
 if 'state' in record:history.append({key:value for key,value in record.items() if key!='history'})
 result={key:value for key,value in record.items() if key not in ('history','error','recovered')}
 result.update(state=state,history=history,recorded_at=time.time(),**updates)
 atomic(receipt,json.dumps(result).encode())
 return result
staged={}
staged_valid=None
if MODE!='rollback':
 for name,digest in HASHES.items():
  p=base/name
  item=dict(expected_sha256=digest,actual_sha256=None,valid=False)
  try:
   if p.is_symlink():item['error_type']='SymlinkRefused'
   elif not p.is_file():item['error_type']='NotRegularFile'
   else:
    item['actual_sha256']=sha(p)
    item['valid']=item['actual_sha256']==digest
  except Exception as error:item['error_type']=type(error).__name__
  staged[name]=item
 staged_valid=all(item['valid'] for item in staged.values())
if MODE in ('apply','reapply'):assert staged_valid,'STAGED_HASH_MISMATCH'
receipt=base/'receipt.json'
out={'action':MODE,'old_sha256':OLD,'new_sha256':HASHES['kodi.bin'],'staged':staged,'staged_valid':staged_valid}
if MODE=='rollback':out['staged_check']='not_required_for_rollback'
if MODE=='status':
 REMOTE_STAGE='status'
 try:out['conf_sha256']=sha(conf)
 except Exception as error:
  out['conf_sha256']=None
  out['conf_error_type']=type(error).__name__
 try:out['native_sha256']=native_sha()
 except Exception:out['native_sha256']=None
 if receipt.is_file():
  try:out['receipt']=json.loads(receipt.read_text())
  except Exception as error:out['receipt_error_type']=type(error).__name__
 out['candidate_ready']=False
 if staged_valid and out['conf_sha256']==HASHES['next.conf'] and out['native_sha256']==HASHES['kodi.bin']:
  try:out['candidate_ready']=isinstance(rpc('Player.BobiState'),dict)
  except Exception:pass
elif MODE in ('apply','reapply'):
 REMOTE_STAGE='receipt_preflight'
 if MODE=='apply':
  assert not receipt.exists(),'TRANSITION_ALREADY_STARTED'
  record=dict(old_conf_sha256=OLD_CONF,new_conf_sha256=HASHES['next.conf'],old_sha256=OLD,new_sha256=HASHES['kodi.bin'])
 else:
  record=checked_record()
  assert record['state']=='rolled_back' and record.get('recovered') is True,'REAPPLY_REQUIRES_CONFIRMED_ROLLBACK'
  assert sha(base/'previous.conf')==OLD_CONF,'PREVIOUS_CONFIGURATION_CHANGED'
 REMOTE_STAGE='baseline'
 assert native_sha()==OLD and sha(conf)==OLD_CONF,'BASELINE_CHANGED'
 assert sha(pathlib.Path(globals().get('OLD_LAUNCH_PATH','/storage/.am6b-repair284/native/launch.py')))==OLD_LAUNCH,'OLD_LAUNCH_CHANGED'
 assert sha(pathlib.Path(globals().get('OLD_BINARY_PATH','/storage/.am6b-repair284/native/kodi.bin')))==OLD,'OLD_BINARY_CHANGED'
 REMOTE_STAGE='generation'
 generation_path=pathlib.Path(globals().get('GENERATION_PATH','/storage/.local/share/bobbi-private-updates/state.json'))
 entry_generation=globals().get('GENERATION_KIND','legacy')=='entry_complete'
 if entry_generation:
  assert not generation_path.is_symlink() and generation_path.is_file() and generation_path.stat().st_size<=1024*1024,'ENTRY_INSTALLATION_UNSAFE'
 generation_bytes=generation_path.read_bytes()
 generation=json.loads(generation_bytes)
 required_sequence=globals().get('REQUIRED_SEQUENCE',2026101908)
 if entry_generation:
  assert isinstance(generation,dict) and type(generation.get('schema')) is int and generation['schema']==1,'ENTRY_INSTALLATION_INVALID'
  assert generation.get('phase')=='complete' and generation.get('host_pending') is None,'ENTRY_INSTALLATION_INCOMPLETE'
  assert type(generation.get('sequence')) is int and type(generation.get('high_watermark')) is int and generation['high_watermark']==generation['sequence'],'ENTRY_INSTALLATION_INVALID'
  tx=generation.get('tx')
  assert isinstance(tx,str) and len(tx)==32 and all(c in '0123456789abcdef' for c in tx),'ENTRY_INSTALLATION_INVALID'
  out['generation']=dict(source='entry_complete',sequence=generation['sequence'],high_watermark=generation['high_watermark'],phase='complete',tx=tx)
 assert type(generation.get('sequence')) is int and generation['sequence']>=required_sequence,'INSTALL_COMPATIBLE_ADDONS_FIRST'
 if MODE=='apply':assert generation['sequence']==required_sequence,'INITIAL_GENERATION_CHANGED'
 REMOTE_STAGE='addon_abi'
 sys_path='/storage/.kodi/addons/script.module.bobbi.core/lib'
 import sys
 sys.path.insert(0,sys_path)
 from bobbi_core.runtime_paths import known_ce_native
 assert known_ce_native(HASHES['kodi.bin']),'UNREVIEWED_NATIVE'
 REMOTE_STAGE='idle'
 assert rpc('Player.GetActivePlayers')==[],'STOP_PLAYBACK_BEFORE_NATIVE_MAINTENANCE'
 REMOTE_STAGE='backup'
 original=conf.read_bytes()
 if MODE=='apply':
  with (base/'previous.conf').open('xb') as f:
   f.write(original);f.flush();os.fsync(f.fileno())
 assert sha(base/'previous.conf')==OLD_CONF,'PREVIOUS_CONFIGURATION_CHANGED'
 record=transition(record,'prepared',action=MODE)
 try:
  REMOTE_STAGE='apply_stop'
  command('systemctl','stop','kodi.service')
  REMOTE_STAGE='apply_replace'
  assert sha(conf)==OLD_CONF,'CONCURRENT_CONFIGURATION_CHANGE'
  if entry_generation:assert sha(generation_path)==hashlib.sha256(generation_bytes).hexdigest(),'PROGRAM_GENERATION_CHANGED'
  next_conf=(base/'next.conf').read_bytes()
  assert hashlib.sha256(next_conf).hexdigest()==HASHES['next.conf'],'STAGED_HASH_MISMATCH'
  atomic(conf,next_conf)
  REMOTE_STAGE='apply_restart'
  command('systemctl','daemon-reload')
  command('systemctl','start','kodi.service')
  REMOTE_STAGE='apply_ready'
  assert ready(HASHES['kodi.bin']),'NEW_NATIVE_NOT_READY'
  record=transition(record,'applied',action=MODE)
 except Exception as error:
  REMOTE_STAGE='recovery_stop'
  command('systemctl','stop','kodi.service')
  REMOTE_STAGE='recovery_replace'
  assert sha(conf) in (OLD_CONF,HASHES['next.conf']),'CONCURRENT_CONFIGURATION_CHANGE'
  atomic(conf,original)
  REMOTE_STAGE='recovery_restart'
  command('systemctl','daemon-reload')
  command('systemctl','start','kodi.service')
  REMOTE_STAGE='recovery_ready'
  record=transition(record,'recovered_after_failure',action=MODE,recovered=ready(OLD),error=type(error).__name__)
  raise
 out['receipt']=record
elif MODE=='rollback':
 REMOTE_STAGE='rollback_preflight'
 record=checked_record()
 assert record['state'] in ('prepared','applied','rolled_back','recovered_after_failure','rollback_prepared','rollback_blocked'),'ROLLBACK_STATE_INVALID'
 observed_conf_sha=sha(conf)
 assert observed_conf_sha in (OLD_CONF,HASHES['next.conf']),'CONCURRENT_CONFIGURATION_CHANGE'
 previous_conf=(base/'previous.conf').read_bytes()
 assert hashlib.sha256(previous_conf).hexdigest()==OLD_CONF,'PREVIOUS_CONFIGURATION_CHANGED'
 assert sha(pathlib.Path(globals().get('OLD_LAUNCH_PATH','/storage/.am6b-repair284/native/launch.py')))==OLD_LAUNCH,'OLD_LAUNCH_CHANGED'
 assert sha(pathlib.Path(globals().get('OLD_BINARY_PATH','/storage/.am6b-repair284/native/kodi.bin')))==OLD,'OLD_BINARY_CHANGED'
 # An interrupted restart may have no Kodi process or responsive JSONRPC.
 # A responsive active playback must still be explicitly stopped first.
 try:players=rpc('Player.GetActivePlayers')
 except Exception:players=None
 assert not players,'STOP_PLAYBACK_BEFORE_NATIVE_MAINTENANCE'
 record=transition(record,'rollback_prepared',action='rollback')
 REMOTE_STAGE='rollback_stop'
 command('systemctl','stop','kodi.service')
 REMOTE_STAGE='rollback_replace'
 if sha(conf)!=observed_conf_sha:
  record=transition(record,'rollback_blocked',action='rollback',recovered=False,error='CONCURRENT_CONFIGURATION_CHANGE')
  raise AssertionError('CONCURRENT_CONFIGURATION_CHANGE')
 atomic(conf,previous_conf)
 REMOTE_STAGE='rollback_restart'
 command('systemctl','daemon-reload')
 command('systemctl','start','kodi.service')
 REMOTE_STAGE='rollback_ready'
 record=transition(record,'rolled_back',action='rollback',recovered=ready(OLD))
 assert record['recovered'],'OLD_NATIVE_NOT_READY'
 out['receipt']=record
print(json.dumps(out))
'''

REMOTE_ERROR_CODES = frozenset((
    'STAGED_HASH_MISMATCH', 'NATIVE_PROCESS_COUNT', 'RECEIPT_INVALID', 'RECEIPT_PIN_MISMATCH',
    'TRANSITION_ALREADY_STARTED', 'REAPPLY_REQUIRES_CONFIRMED_ROLLBACK', 'PREVIOUS_CONFIGURATION_CHANGED',
    'BASELINE_CHANGED', 'OLD_LAUNCH_CHANGED', 'OLD_BINARY_CHANGED', 'INSTALL_COMPATIBLE_ADDONS_FIRST',
    'INITIAL_GENERATION_CHANGED', 'ENTRY_INSTALLATION_UNSAFE', 'ENTRY_INSTALLATION_INVALID',
    'ENTRY_INSTALLATION_INCOMPLETE', 'PROGRAM_GENERATION_CHANGED', 'UNREVIEWED_NATIVE',
    'STOP_PLAYBACK_BEFORE_NATIVE_MAINTENANCE', 'NEW_NATIVE_NOT_READY',
    'CONCURRENT_CONFIGURATION_CHANGE', 'OLD_NATIVE_NOT_READY', 'ROLLBACK_STATE_INVALID'))


def remote_script(params):
    # Emit exactly one JSON result on failure. Never serialize arbitrary error
    # messages, stderr or traceback contents into maintenance receipts.
    values = '\n'.join(key+'='+repr(value) for key,value in params.items())
    wrapper = '\nimport json\nREMOTE_STAGE="bootstrap"\ntry:\n' + textwrap.indent(REMOTE, ' ')
    wrapper += '\nexcept Exception as error:\n'
    wrapper += ' allowed=' + repr(tuple(sorted(REMOTE_ERROR_CODES))) + '\n'
    wrapper += ' raw=error.args[0] if len(error.args)==1 and isinstance(error.args[0],str) else None\n'
    wrapper += ' code=raw if raw in allowed else "UNEXPECTED_REMOTE_FAILURE"\n'
    wrapper += ' print(json.dumps(dict(action=MODE,outcome="unconfirmed",next_action="status",stage=REMOTE_STAGE,code=code,error_type=type(error).__name__)))\n'
    wrapper += ' raise SystemExit(1) from None\n'
    return values + wrapper


def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def local_artifact_path(reference):
    # The reviewed builder runs in WSL; its recorded /mnt/<drive> artifacts are
    # the same files when this maintainer is invoked from Windows.
    if os.name == 'nt' and reference.startswith('/mnt/'):
        parts = reference.split('/')
        assert len(parts) > 3 and len(parts[2]) == 1 and parts[2].isalpha(), 'INVALID_ARTIFACT_REFERENCE'
        return Path(parts[2].upper() + ':/' + '/'.join(parts[3:]))
    return Path(reference)


def checked_build(build_result, profile):
    if 'build_proof_sha256' in profile:
        assert sha_file(build_result) == profile['build_proof_sha256'], 'BUILD_PROOF_CHANGED'
    result = json.loads(build_result.read_text())
    assert result['state'] == 'BUILT_NOT_DEPLOYED' and result['original_tree_unchanged'] is True
    assert result['baseline_sha256'] == OLD, 'BASELINE_PIN_CHANGED'
    assert result['candidate_sha256'] == profile['candidate'], 'CANDIDATE_PIN_CHANGED'
    binary = build_result.parent/'candidate.bin'
    assert sha_file(binary) == profile['candidate'], 'CANDIDATE_ARTIFACT_CHANGED'
    if 'baseline_proof' not in profile:
        assert result['control_sha256'] == OLD
    else:
        assert result.get('baseline_proof') == profile['baseline_proof'], 'BASELINE_REFERENCE_CHANGED'
        proof_path = local_artifact_path(result['baseline_proof'])
        assert sha_file(proof_path) == profile['baseline_proof_sha256'], 'BASELINE_PROOF_CHANGED'
        proof = json.loads(proof_path.read_text())
        assert proof['state'] == 'BUILT_NOT_DEPLOYED' and proof['original_tree_unchanged'] is True
        assert proof['baseline_sha256'] == OLD, 'BASELINE_PROOF_PIN_CHANGED'
        assert sha_file(proof_path.parent/'baseline.bin') == OLD, 'BASELINE_ARTIFACT_CHANGED'
        if 'build_proof_sha256' in profile:
            # An ABI-complete rebuild consumes more original units than the
            # old relink. Retain exact baseline provenance and pin the ENTIRE
            # new report; do not silently allow arbitrary additional inputs.
            inputs = result.get('inputs')
            baseline_inputs = result.get('baseline_inputs')
            abi_inputs = result.get('additional_inputs')
            expected_inputs = proof['inputs']
            if 'predecessor_proof' in profile:
                previous_path = local_artifact_path(profile['predecessor_proof'])
                assert sha_file(previous_path) == profile['predecessor_proof_sha256'], 'PREDECESSOR_PROOF_CHANGED'
                previous = json.loads(previous_path.read_text())
                assert previous.get('baseline_inputs') == proof['inputs'], 'PREDECESSOR_BASELINE_CHANGED'
                expected_inputs = previous.get('inputs')
                assert isinstance(expected_inputs, dict) and expected_inputs, 'PREDECESSOR_INPUTS_MISSING'
            assert baseline_inputs and baseline_inputs == expected_inputs, 'BASELINE_INPUTS_CHANGED'
            assert isinstance(inputs, dict) and isinstance(abi_inputs, dict) and abi_inputs, 'ABI_INPUTS_MISSING'
            assert not (set(baseline_inputs) & set(abi_inputs)), 'ABI_INPUTS_OVERLAP'
            assert inputs == dict(baseline_inputs, **abi_inputs), 'ABI_INPUTS_CHANGED'
        else:
            assert result.get('inputs') and result['inputs'] == proof['inputs'], 'BASELINE_INPUTS_CHANGED'
    if 'predecessor_proof' in profile:
        # The single-TU schema repair is pinned to the reviewed 8bb2 archive
        # generation, not merely to the older original-object baseline proof.
        expected = predecessor(profile)['binary']
        assert result.get('predecessor_proof') == profile['predecessor_proof'], 'PREDECESSOR_REFERENCE_CHANGED'
        previous_path = local_artifact_path(profile['predecessor_proof'])
        assert sha_file(previous_path) == profile['predecessor_proof_sha256'], 'PREDECESSOR_PROOF_CHANGED'
        previous = json.loads(previous_path.read_text())
        assert (previous.get('state') == 'BUILT_NOT_DEPLOYED' and previous.get('original_tree_unchanged') is True
                and previous.get('candidate_sha256') == expected
                and sha_file(previous_path.parent/'candidate.bin') == expected), 'PREDECESSOR_ARTIFACT_CHANGED'
        assert (result.get('predecessor_sha256') == expected
                and result.get('predecessor-relink_sha256') == expected
                and result.get('predecessor_unchanged') is True
                and result.get('recompiled_units') == ['xbmc/interfaces/json-rpc/JSONRPC.cpp']), 'PREDECESSOR_RELINK_CHANGED'
        verification_path = build_result.parent/'artifact-verification.json'
        assert sha_file(verification_path) == profile['verification_sha256'], 'VERIFICATION_PROOF_CHANGED'
        verification = json.loads(verification_path.read_text())
        assert (verification.get('state') == 'VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED'
                and verification.get('build_result_sha256') == profile['build_proof_sha256']
                and verification.get('candidate_sha256') == profile['candidate']
                and verification.get('predecessor_sha256') == expected
                and verification.get('rpc_methods_exact') is True), 'RPC_SCHEMA_NOT_VERIFIED'
    return result, binary


def predecessor(profile):
    """Installed predecessor is distinct from the original build/relink proof."""
    return profile.get('predecessor') or dict(binary=OLD, conf=OLD_CONF, launch=OLD_LAUNCH,
        binary_path='/storage/.am6b-repair284/native/kodi.bin',
        launch_path='/storage/.am6b-repair284/native/launch.py')


def staged_files(build_result, profile, layout_path):
    result, binary = checked_build(build_result, profile)
    layout = json.loads(layout_path.read_text())
    previous = predecessor(profile)
    launch = layout['files'][previous['launch_path']]['source'].encode()
    assert hashlib.sha256(launch).hexdigest() == previous['launch'] and launch.count(previous['binary'].encode()) == 1
    if profile['tag'] == '2035' or 'predecessor' in profile:
        assert layout['files'][previous['launch_path']]['sha256'] == previous['launch']
        assert layout['files'][previous['binary_path']]['sha256'] == previous['binary']
        assert layout['dropins']['/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf']['sha256'] == previous['conf']
        assert len(layout['running']) == 1 and layout['running'][0]['sha256'] == previous['binary']
    new_launch = launch.replace(previous['binary'].encode(), result['candidate_sha256'].encode())
    base = profile['base']
    conf = ('[Service]\nBindReadOnlyPaths='+base+'/kodi.bin:/usr/lib/kodi/kodi.bin\nExecStart=\n'
            'ExecStart=/usr/bin/python3 '+base+'/launch.py --standalone -fs $KODI_ARGS $KODI_DEBUG\n').encode()
    return {'kodi.bin': binary.read_bytes(), 'launch.py': new_launch, 'next.conf': conf}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--mode', choices=('stage','apply','reapply','status','rollback'), required=True)
    parser.add_argument('--build-result', type=Path, required=True)
    parser.add_argument('--profile', choices=tuple(PROFILES), default='directory1908')
    parser.add_argument('--baseline-layout', type=Path)
    parser.add_argument('--report-dir', type=Path)
    args = parser.parse_args()
    profile = PROFILES[args.profile]
    base = profile['base']
    files = staged_files(args.build_result, profile, args.baseline_layout or profile['layout'])
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    report_dir = args.report_dir or profile['reports']
    report_dir.mkdir(parents=True, exist_ok=True)
    path=report_dir/('ce-native'+profile['tag']+'-'+args.mode+'-'+str(time.time_ns())+'.json')
    report=dict(result=None,exit_code=None,diagnostic=False,outcome='unconfirmed',next_action='status',phase='connect')
    # Prove the local receipt is writable before any remote action. Transport
    # timeouts do not prove that the remote transaction stopped or rolled back.
    with path.open('x') as stream:json.dump(report,stream,indent=2)
    client=None
    try:
        sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
        spec=importlib.util.spec_from_file_location('native_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        client,wire=module.connect()
        if args.mode=='stage':
            report['phase']='stage'
            with client.open_sftp() as sftp:
                try:sftp.mkdir('/storage/.local/share/bobbi-native')
                except OSError:
                    if not sftp.stat('/storage/.local/share/bobbi-native'):raise
                sftp.mkdir(base)
                for name,data in files.items():
                    with sftp.open(base+'/'+name,'wx') as stream:stream.write(data)
                    sftp.chmod(base+'/'+name,0o755 if name=='kodi.bin' else 0o644)
        previous = predecessor(profile)
        params=dict(MODE='status' if args.mode=='stage' else args.mode,HASHES=hashes,
                    OLD=previous['binary'],OLD_CONF=previous['conf'],OLD_LAUNCH=previous['launch'],
                    OLD_BINARY_PATH=previous['binary_path'],OLD_LAUNCH_PATH=previous['launch_path'],
                    BASE=base,REQUIRED_SEQUENCE=profile['sequence'],PROFILE_TAG=profile['tag'],
                    GENERATION_KIND=profile.get('generation_kind','legacy'),
                    GENERATION_PATH=profile.get('generation_path',LEGACY_GENERATION_PATH))
        script=remote_script(params)
        report['phase']='remote'
        rc,value,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=profile['deadline'])
        report.update(result=value if isinstance(value,dict) else None,exit_code=rc,diagnostic=bool(diagnostic))
        if (rc or diagnostic or not isinstance(value,dict) or value.get('outcome') in ('unconfirmed','failed')
                or value.get('error_type') or value.get('transport_error')):report['error_type']='RemoteUnconfirmed'
        elif args.mode=='stage' and not value.get('staged_valid'):report['error_type']='StagedArtifactsUnconfirmed'
        else:report.update(outcome='confirmed',next_action=None)
    except Exception as error:
        report['error_type']=type(error).__name__
    finally:
        if client is not None:
            try:client.close()
            except Exception as error:
                report['close_error_type']=type(error).__name__
                report.setdefault('error_type',type(error).__name__)
        if report.get('error_type'):report.update(outcome='unconfirmed',next_action='status')
        path.write_text(json.dumps(report,indent=2))
    if report['outcome']!='confirmed':
        print(json.dumps(report))
        raise RuntimeError('NATIVE_TRANSITION_UNCONFIRMED_READ_STATUS') from None
    print(json.dumps(report['result']))


if __name__=='__main__':main()
