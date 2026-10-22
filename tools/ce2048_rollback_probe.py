"""Attended reversible backup-missing experiment; never edits live programs.

Only one named backed-up addon.xml is held outside its transaction backup.
The actual rollback must be attempted through the ordinary entry UI. Restore
the held file before attempting a valid rollback. All receipt values are safe.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

REMOTE = r'''
import hashlib,json,os,pathlib,sys,urllib.request,subprocess,tempfile
root=pathlib.Path('/storage/.kodi/addons')
sys.path.insert(0,str(root/'script.bobbi.start/bootstrap'))
from bobbi_platform.ce_installer import program_tree,MANAGED
from bobbi_platform.updates import UpdateError
run=pathlib.Path('/storage/.kodi/temp/bobbi-ce-entry-20261022-220000')
journal=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json')
state=json.loads(journal.read_text())
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('RPC_FAILED')
 return r['result']
assert not rpc('Player.GetActivePlayers'),'PLAYBACK_ACTIVE'
vector={name:program_tree(root/name) for name in sorted(MANAGED)}
target=journal.parent/state['tx']/'backup/plugin.video.bobbi/addon.xml'
held=run/'held-addon.xml'
receipt=run/'held-backup.json'
if ACTION=='hold':
 assert state['sequence']==2026102048 and state['phase']=='complete'
 assert not held.exists() and not receipt.exists() and target.is_file() and not target.is_symlink()
 data=dict(tx=state['tx'],target=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
  vector=vector,journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest())
 receipt.write_text(json.dumps(data))
 os.replace(target,held)
 result=dict(action='hold',target_missing=not target.exists(),file_recoverable=held.is_file(),tx=state['tx'])
elif ACTION=='restore':
 data=json.loads(receipt.read_text())
 assert data['tx']==state['tx'] and data['target']==str(target)
 assert not target.exists() and held.is_file() and hashlib.sha256(held.read_bytes()).hexdigest()==data['sha256']
 unchanged=data['vector']==vector and data['journal_sha256']==hashlib.sha256(journal.read_bytes()).hexdigest()
 os.replace(held,target)
 result=dict(action='restore',backup_restored=target.is_file(),live_and_journal_unchanged=unchanged,tx=state['tx'])
elif ACTION=='snapshot':
 result=dict(action='snapshot',phase=state['phase'],sequence=state['sequence'],tx=state['tx'],
  host_pending=state.get('host_pending'),vector=vector,skin=rpc('Settings.GetSettingValue',{'setting':'lookandfeel.skin'}),
  kodi=subprocess.check_output(['systemctl','show','kodi','-p','ActiveState','-p','NRestarts']).decode().strip().splitlines(),
  matches_previous_vector=all(vector.get(row['id'])==row.get('old_tree') for row in state['items'] if row['had_old']),
  torrent_processes=[line.strip() for line in subprocess.check_output(['ps','-eo','pid,comm']).decode().splitlines() if 'torrserver' in line.lower()])
elif ACTION=='posix':
 with tempfile.TemporaryDirectory(prefix='bobbi-rollback-posix-',dir=str(run)) as temp:
  p=pathlib.Path(temp);(p/'code.py').write_text('fixture=1\n');before=program_tree(p)
  (p/'code.py').chmod(0o755);mode_detected=program_tree(p)!=before
  (p/'link').symlink_to(p/'code.py')
  try:program_tree(p);link_rejected=False
  except (UpdateError,ValueError):link_rejected=True
 result=dict(action='posix',mode_detected=mode_detected,link_rejected=link_rejected,live_untouched=True)
print(json.dumps(result))
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('hold','restore','snapshot','posix'))
    p.add_argument('--transport-source',type=Path,required=True);a=p.parse_args()
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce2048_wire',a.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try: rc,result,diag=wire.readonly(client,('ACTION='+repr(a.action)+'\n'+REMOTE).encode(),deadline_seconds=45)
    finally:client.close()
    out=Path(__file__).resolve().parents[1]/'review-evidence/ce2048'
    out.mkdir(exist_ok=True)
    value=dict(action=a.action,exit_code=rc,diagnostic_present=bool(diag),result=result)
    dest=out/('device-rollback-'+a.action+'-'+str(time.time_ns())+'.json')
    dest.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(dest),**value),ensure_ascii=False))
    return 1 if rc or diag else 0


if __name__=='__main__':raise SystemExit(main())
