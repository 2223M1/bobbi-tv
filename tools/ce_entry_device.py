"""Stage an audited entry reversibly, then drive its real Kodi dialogs.

Not a claim of Kodi's ZIP browser installation: staging is explicit maintenance.
The real packaged default.py/bootstrap, dialogs, Installer and KodiHost run.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import hashlib,json,os,pathlib,subprocess,time,urllib.request,zipfile
run=pathlib.Path(RUN)
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('KODI_RPC_FAILED')
 return r.get('result')
def builtin(action):
 subprocess.run(['kodi-send','--action='+action],check=True,stdout=subprocess.DEVNULL)
def view():
 out={'players':rpc('Player.GetActivePlayers'),'gui':rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol']})}
 labels=['Window.Property(playback_error)','Control.GetLabel(1)','Control.GetLabel(2)','Control.GetLabel(3)','Control.GetLabel(4)','Control.GetLabel(5)','Control.GetLabel(6)','Control.GetLabel(10)','Control.GetLabel(11)','Container(6).NumItems','Container(6).CurrentItem','Container(6).ListItem.Label']
 out['labels']=rpc('XBMC.GetInfoLabels',{'labels':labels})
 p=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json')
 if p.is_file():
  state=json.loads(p.read_text());out['installation']={k:state[k] for k in ('sequence','high_watermark','phase','host_pending','tx') if k in state}
 return out
if MODE=='stage':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 if rpc('GUI.GetProperties',{'properties':['currentwindow']})['currentwindow']['id']!=10000:raise RuntimeError('HOME_REQUIRED')
 archive=run/'entry.zip'
 if hashlib.sha256(archive.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('ENTRY_CHANGED')
 target=pathlib.Path('/storage/.kodi/addons/script.bobbi.start')
 backup=run/'previous-entry'
 stage=run/'staged'
 if target.is_symlink() or backup.exists() or stage.exists():raise RuntimeError('UNSAFE_ENTRY_STAGE')
 stage.mkdir()
 with zipfile.ZipFile(archive) as z:
  names=z.namelist()
  if len(set(names))!=len(names):raise RuntimeError('DUPLICATE_ENTRY')
  for item in z.infolist():
   n=item.filename
   if not n.startswith('script.bobbi.start/') or '..' in n.split('/') or '\\' in n or ':' in n or item.is_dir():raise RuntimeError('ENTRY_PATH')
   p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(item))
 os.replace(target,backup)
 try:os.replace(stage/'script.bobbi.start',target)
 except BaseException:
  os.replace(backup,target);raise
 (run/'stage.json').write_text(json.dumps(dict(entry_sha256=EXPECTED,previous_entry=str(backup),live=str(target))))
 builtin('UpdateLocalAddons')
elif MODE=='open':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 builtin('RunScript(script.bobbi.start)')
elif MODE=='choose':
 current=view()
 if current['players'] or current['gui']['currentwindow']['id']!=EXPECTED_WINDOW:raise RuntimeError('UI_CHANGED')
 if not any(EXPECTED_LABEL in str(value) for value in current['labels'].values()):raise RuntimeError('UI_LABEL_CHANGED')
 # Focus/index are chosen only from the immediately preceding real UI read.
 builtin('SetFocus(%d)'%CONTROL)
 if INDEX is not None:
  rpc('Input.ExecuteAction',{'action':'firstpage'})
  for _ in range(INDEX):rpc('Input.Down')
 rpc('Input.Select')
elif MODE=='back':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 rpc('Input.ExecuteAction',{'action':'back'})
time.sleep(.3)
print(json.dumps(view()))
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--mode',choices=('stage','open','view','choose','back'),required=True)
    p.add_argument('--run-id',required=True);p.add_argument('--entry',type=Path)
    p.add_argument('--window',type=int);p.add_argument('--label');p.add_argument('--control',type=int);p.add_argument('--index',type=int)
    a=p.parse_args()
    if not re.fullmatch('[0-9]{8}-[0-9]{6}',a.run_id):p.error('Exact timestamp required')
    if a.mode=='stage':
        from audit_ce_entry import audit
        audit(a.entry)
    if a.mode=='choose' and (a.window is None or not a.label or a.control is None):p.error('Observed dialog identity required')
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('entry_wire',a.transport_source/'ui-redesign/tools/device_transport.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    run='/storage/.kodi/temp/bobbi-ce-entry-'+a.run_id
    c,w=m.connect()
    try:
        if a.mode=='stage':
            with c.open_sftp() as s:
                s.mkdir(run,mode=0o700);s.put(str(a.entry),run+'/entry.zip')
        values=dict(RUN=run,MODE=a.mode,EXPECTED=hashlib.sha256(a.entry.read_bytes()).hexdigest() if a.entry else None,
                    EXPECTED_WINDOW=a.window,EXPECTED_LABEL=a.label,CONTROL=a.control,INDEX=a.index)
        code='\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'+REMOTE
        rc,result,diag=w.readonly(c,code.encode(),deadline_seconds=45)
    finally:c.close()
    out=ROOT/'review-evidence/ce2023'/('entry-device-'+a.mode+'-'+str(time.time_ns())+'.json')
    out.write_text(json.dumps(dict(run=run,mode=a.mode,transport_exit=rc,diagnostic_present=bool(diag),result=result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(out),result=result),ensure_ascii=False))
    return int(bool(rc or diag))


if __name__=='__main__':raise SystemExit(main())
