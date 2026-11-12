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
    'homefocus2116': dict(build_kind='home_focus',
        candidate='591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032',
        sequence=2026102116, tag='2116', base='/storage/.local/share/bobbi-native/2026102116',
        layout=ROOT.parent/'ce-native-home-focus-20261112/current-overlay2114.json',
        reports=ROOT.parent/'ce-native-home-focus-20261112', deadline=390,
        generation_kind='private_complete', generation_path=LEGACY_GENERATION_PATH,
        minimum_versions={'plugin.video.bobbi':'0.1.59','script.module.bobbi.core':'0.1.60',
                          'script.module.bobbi.platform':'0.1.67'},
        build_proof_sha256='e67b4d8b108157428286a93a74bb0407a0133621753785681257133d0829f90f',
        predecessor_proof_sha256='0b54e0b6b3e982dd9e02f2867cdbc6fc3df36afd7709e7cf4c368ec655651f7c',
        canonical_patch_sha256='7db7a5def0a7570b015be298fba2a124930a1afd832fc6df20f666b2a0b442a3',
        predecessor=dict(binary='4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a',
            conf='e0bd0d8cb53480a06f9996d2abe4ad0374cbdecb244e9b9f8c6810bcf01cfbba',
            launch='d5e79b1b33053cdb811246fa4108ffdcb885b20657d8c4ce17951a60e0cf4195',
            binary_path='/storage/.local/share/bobbi-native/2026102114/kodi.bin',
            launch_path='/storage/.local/share/bobbi-native/2026102114/launch.py')),
    'completion2114': dict(build_kind='completion',
        candidate='4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a',
        sequence=2026102114, tag='2114', base='/storage/.local/share/bobbi-native/2026102114',
        layout=ROOT.parent/'ce-native-completion-20261112/current-overlay.json',
        reports=ROOT.parent/'ce-native-completion-20261112', deadline=390,
        generation_kind='private_complete', generation_path=LEGACY_GENERATION_PATH,
        minimum_versions={'plugin.video.bobbi':'0.1.58','script.module.bobbi.core':'0.1.59',
                          'script.module.bobbi.platform':'0.1.67'},
        build_proof_sha256='0b54e0b6b3e982dd9e02f2867cdbc6fc3df36afd7709e7cf4c368ec655651f7c',
        canonical_patch_sha256='c7647dcbb94a4f2bc6e19f4deff3f3677e835a95b8a6771d10aa42860244fe2a',
        predecessor=dict(binary='ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991',
            conf='0501d0f0c6dbdc71c0ebcaa0082a3f23aac696a92d6a913a352fbda850127191',
            launch='8ef01e1eb6882f550e229b2791e285459fcfecafe0a13a0bfb4813afa976f42d',
            binary_path='/storage/.local/share/bobbi-native/2026102043/kodi.bin',
            launch_path='/storage/.local/share/bobbi-native/2026102043/launch.py')),
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
def command(*args):
 timeout=120 if args[:2]==('systemctl','stop') else 30
 return subprocess.check_output(args,timeout=timeout).decode().strip()
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
 private_generation=globals().get('GENERATION_KIND','legacy')=='private_complete'
 if entry_generation or private_generation:
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
 generation_guards={generation_path:hashlib.sha256(generation_bytes).hexdigest()}
 if private_generation:
  import re,xml.etree.ElementTree as ET
  pending=generation_path.parent/'journal.json'
  assert not pending.exists() and not pending.is_symlink(),'PROGRAM_UPDATE_PENDING'
  assert (isinstance(generation,dict) and set(generation)=={'sequence','versions'}
   and type(generation.get('sequence')) is int and isinstance(generation.get('versions'),dict)
   and all(isinstance(k,str) and isinstance(v,str) for k,v in generation['versions'].items())),'PRIVATE_GENERATION_INVALID'
  minimum=globals().get('MINIMUM_VERSIONS',{})
  assert set(minimum)=={'plugin.video.bobbi','script.module.bobbi.core','script.module.bobbi.platform'},'PRIVATE_COMPONENTS_INVALID'
  for ident,version in minimum.items():
   installed=generation['versions'].get(ident)
   assert isinstance(installed,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}',installed),'PRIVATE_COMPONENTS_INVALID'
   def parts(value):return tuple((list(map(int,value.split('.')))+[0]*4)[:4])
   assert parts(installed)>=parts(version),'INSTALL_COMPATIBLE_ADDONS_FIRST'
   manifest=pathlib.Path('/storage/.kodi/addons')/ident/'addon.xml'
   assert not manifest.is_symlink() and manifest.is_file() and manifest.stat().st_size<=1024*1024,'PRIVATE_COMPONENTS_INVALID'
   body=manifest.read_bytes()
   addon=ET.fromstring(body)
   assert addon.tag=='addon' and addon.get('id')==ident and addon.get('version')==installed,'PRIVATE_COMPONENTS_INVALID'
   generation_guards[manifest]=hashlib.sha256(body).hexdigest()
  entry=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json')
  assert not entry.is_symlink(),'ENTRY_INSTALLATION_UNSAFE'
  if entry.exists():
   assert entry.is_file() and entry.stat().st_size<=1024*1024,'ENTRY_INSTALLATION_UNSAFE'
   entry_bytes=entry.read_bytes()
   prior=json.loads(entry_bytes)
   assert (isinstance(prior,dict) and type(prior.get('schema')) is int and prior['schema']==1
    and prior.get('phase')=='complete' and prior.get('host_pending') is None),'ENTRY_INSTALLATION_INCOMPLETE'
   generation_guards[entry]=hashlib.sha256(entry_bytes).hexdigest()
  out['generation']=dict(source='private_complete',sequence=generation['sequence'],
   state_sha256=hashlib.sha256(generation_bytes).hexdigest(),components={k:generation['versions'][k] for k in minimum})
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
  if entry_generation or private_generation:
   assert all(not p.is_symlink() and sha(p)==digest for p,digest in generation_guards.items()),'PROGRAM_GENERATION_CHANGED'
  if private_generation:assert not pending.exists() and not pending.is_symlink(),'PROGRAM_UPDATE_PENDING'
  next_conf=(base/'next.conf').read_bytes()
  assert hashlib.sha256(next_conf).hexdigest()==HASHES['next.conf'],'STAGED_HASH_MISMATCH'
  atomic(conf,next_conf)
  REMOTE_STAGE='apply_restart'
  command('systemctl','daemon-reload')
  command('systemctl','start','kodi.service')
  REMOTE_STAGE='apply_ready'
  assert ready(HASHES['kodi.bin']),'NEW_NATIVE_NOT_READY'
  if private_generation:
   assert all(not p.is_symlink() and sha(p)==digest for p,digest in generation_guards.items()),'PROGRAM_GENERATION_CHANGED'
   assert not pending.exists() and not pending.is_symlink(),'PROGRAM_UPDATE_PENDING'
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
    'PROGRAM_UPDATE_PENDING', 'PRIVATE_GENERATION_INVALID', 'PRIVATE_COMPONENTS_INVALID',
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
    if profile.get('build_kind') in ('completion', 'home_focus'):
        # This successor inherits the already verified schema host, not a
        # reconstruction from the historical pre-handoff runtime generation.
        assert sha_file(build_result) == profile['build_proof_sha256'], 'BUILD_PROOF_CHANGED'
        result = json.loads(build_result.read_text())
        previous = predecessor(profile)['binary']
        assert (result.get('state') == 'BUILT_NOT_DEPLOYED'
                and result.get('original_tree_unchanged') is True
                and result.get('predecessor_sha256') == previous
                and result.get('predecessor-relink_sha256') == previous), 'PREDECESSOR_RELINK_CHANGED'
        assert (result.get('architecture_and_dependencies_unchanged') is True
                and result.get('binary_bobicontrol_schema_unchanged') is True
                and result.get('canonical_patch_sha256') == profile['canonical_patch_sha256']), 'NATIVE_ABI_NOT_VERIFIED'
        if profile['build_kind'] == 'home_focus':
            units = {'xbmc/guilib/listproviders/DirectoryProvider.cpp'}
            assert (result.get('build_kind') == 'home_focus'
                    and result.get('predecessor_unchanged') is True
                    and result.get('predecessor_proof_sha256') == profile['predecessor_proof_sha256']
                    and result.get('completion_archives_unchanged') is True
                    and result.get('recompiled_units') == sorted(units)), 'FOCUS_PREDECESSOR_CHANGED'
            evidence = result.get('production_tests', {})
            assert (isinstance(evidence, dict) and evidence.get('candidate_passed') is True
                    and evidence.get('negative_control_failed') is True
                    and evidence.get('interleaved_control_failed') is True), 'FOCUS_PRODUCTION_TESTS_MISSING'
            relative = evidence.get('path', '')
            assert (isinstance(relative, str) and relative
                    and not Path(relative).is_absolute() and '\\' not in relative
                    and ':' not in relative and '..' not in relative.split('/')), 'FOCUS_TEST_PATH_INVALID'
            test_path = build_result.parent/relative
            assert sha_file(test_path) == evidence.get('sha256'), 'FOCUS_TEST_PROOF_CHANGED'
            tests = json.loads(test_path.read_text())
            assert (tests.get('passed') is True and isinstance(tests.get('tests'), list)
                    and len(tests['tests']) == 3), 'FOCUS_TEST_PROOF_INVALID'
            controls = ('candidate', 'pre_fix_negative_control', 'update_only_negative_control')
            for row, name, code in zip(tests['tests'], controls, (0, 1, 1)):
                assert (row.get('name') == name and row.get('passed') is True
                        and type(row.get('exit_code')) is int
                        and row.get('exit_code') == code), 'FOCUS_TEST_CONTROL_INVALID'
                for filename, field in (('actual_directory_visibility.inc', 'extracted_sha256'),
                                        ('directory-visibility-test', 'binary_sha256')):
                    assert sha_file(test_path.parent/name/filename) == row.get(field), 'FOCUS_TEST_ARTIFACT_CHANGED'
        else:
            units = {'xbmc/cores/VideoPlayer/VideoPlayer.cpp', 'xbmc/application/ApplicationPlayer.cpp',
                     'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp'}
        assert set(result.get('objects', {})) == units, 'NATIVE_LAYOUT_CONSUMERS_CHANGED'
        for source, item in result['objects'].items():
            obj = build_result.parent / (Path(source).name + '.o')
            assert sha_file(obj) == item['sha256'], 'NATIVE_OBJECT_CHANGED'
            assert sha_file(Path(str(obj) + '.d')) == item['depfile_sha256'], 'NATIVE_DEPENDENCIES_CHANGED'
        snapshot = build_result.parent / 'source-candidate'
        assert {str(p.relative_to(snapshot)).replace('\\', '/'): sha_file(p)
                for p in snapshot.rglob('*') if p.is_file()} == result['source_sha256'], 'NATIVE_SOURCE_CHANGED'
        binary = build_result.parent / 'candidate.bin'
        assert result['candidate_sha256'] == profile['candidate'] == sha_file(binary), 'CANDIDATE_ARTIFACT_CHANGED'
        return result, binary
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
                    GENERATION_PATH=profile.get('generation_path',LEGACY_GENERATION_PATH),
                    MINIMUM_VERSIONS=profile.get('minimum_versions',{}))
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
