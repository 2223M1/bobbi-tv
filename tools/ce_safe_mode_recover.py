"""Preserve the temporary SAFE profile, then use CE's normal exit-safe path.

Pinned to this attended incident. Never edits account data, boot.status, firmware,
or Kodi's recovery script; never manually deletes or swaps either profile.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import hashlib,json,pathlib,shutil,subprocess,time,urllib.request
P=pathlib.Path
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def generation(root):
 p=root/'userdata/addon_data/script.bobbi.start/installation.json'
 return json.loads(p.read_text()) if p.is_file() else {}
live=P('/storage/.kodi');failed=P('/storage/.kodi.FAILED')
assert live.resolve()==live and failed.resolve()==failed,'PROFILE_PATH_CHANGED'
assert live.is_dir() and failed.is_dir(),'PROFILE_MISSING'
assert P('/storage/.config/boot.status').read_text().strip()=='SAFE','NOT_SAFE_MODE'
expected=dict(sequence=2026102031,phase='complete',tx='983fc4fac73c4744a44cb6ac2c5ab470')
assert all(generation(failed).get(k)==v for k,v in expected.items()),'FAILED_GENERATION_CHANGED'
assert not generation(live),'CURRENT_PROFILE_IS_INSTALLED'
pids=subprocess.check_output(['pidof','kodi.bin']).decode().split()
assert len(pids)==1,'NATIVE_PROCESS_AMBIGUOUS'
native_sha=sha(P('/proc')/pids[0]/'exe')
assert native_sha=='8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b','NATIVE_CHANGED'
sentinels=('userdata/guisettings.xml','userdata/addon_data/plugin.video.bobbi/database.pickle',
 'userdata/addon_data/script.bobbi.start/installation.json','addons/plugin.video.bobbi/addon.xml')
before={n:sha(failed/n) for n in sentinels}
files=[p for p in live.rglob('*') if p.is_file() and not p.is_symlink()]
size=sum(p.stat().st_size for p in files)
assert size<128*1024*1024,'SAFE_PROFILE_NOT_SMALL'
base=P('/storage/.local/share/bobbi-safe-recovery')/STAMP
base.mkdir(parents=True,exist_ok=False)
backup=base/'temporary-safe-profile'
# copytree preserves links without following them outside this selected profile.
shutil.copytree(live,backup,symlinks=True)
record=dict(stage='backed_up',sequence=expected['sequence'],backup=str(backup),
 temporary_profile_bytes=size,temporary_profile_files=len(files),native_sha256=native_sha,
 original_profile_sentinels=before,scope='CoreELEC standard SAFE exit; no program or account rewrite')
(base/'receipt.json').write_text(json.dumps(record,indent=2))
assert P('/storage/.config/boot.status').read_text().strip()=='SAFE' and not generation(live),'STATE_CHANGED'
assert all(sha(failed/n)==v for n,v in before.items()),'ORIGINAL_PROFILE_CHANGED'
# ExecStopPost=/usr/lib/kodi/kodi-safe-mode is the inspected vendor recovery:
# it retires the temporary SAFE profile and restores .kodi.FAILED, then marks OK.
# The temporary profile is now recoverable from the explicit backup above.
subprocess.run(['systemctl','restart','--no-block','kodi.service'],check=True,timeout=5)
deadline=time.monotonic()+45
ready=False
while time.monotonic()<deadline:
 try:
  query=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',b'{"jsonrpc":"2.0","id":1,"method":"Player.GetActivePlayers"}',{'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(query,timeout=2) as f:response=json.load(f)
  if 'result' in response and all(generation(live).get(k)==v for k,v in expected.items()):ready=True;break
 except Exception:pass
 time.sleep(.5)
record.update(stage='restored' if ready else 'not_ready',ready=ready,
 boot_status=P('/storage/.config/boot.status').read_text().strip(),failed_directory_exists=failed.exists())
if ready:
 record['program_and_history_unchanged']=all(sha(live/n)==v for n,v in before.items() if n!='userdata/guisettings.xml')
 # Kodi may persist its own normal settings on startup. Record rather than
 # overwrite that file just to force a byte-identical whole-profile rollback.
 record['settings_unchanged']=sha(live/'userdata/guisettings.xml')==before['userdata/guisettings.xml']
(base/'receipt.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('safe_wire',a.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    c,w=module.connect();stamp=str(time.time_ns())
    code='STAMP='+repr(stamp)+'\n'+REMOTE
    wrapped='import json,traceback\ntry:\n exec(compile('+repr(code)+',"safe-recovery","exec"))\nexcept Exception as error:\n print(json.dumps(dict(error=type(error).__name__,code=str(error) if isinstance(error,AssertionError) else "RECOVERY_STOPPED",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])))'
    try:rc,value,diag=w.readonly(c,wrapped.encode(),deadline_seconds=60)
    finally:c.close()
    a.output.mkdir(parents=True,exist_ok=True)
    record=a.output/('safe-recovery-'+stamp+'.json')
    record.write_text(json.dumps(dict(exit_code=rc,diagnostic_present=bool(diag),result=value),indent=2),encoding='utf-8')
    print(json.dumps(dict(evidence=str(record),**value)))
    return int(bool(rc or diag or value.get('error') or not value.get('ready')))


if __name__=='__main__':raise SystemExit(main())
