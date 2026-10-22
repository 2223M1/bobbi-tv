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
import textwrap

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
 labels+=['Container(3).NumItems','Container(3).CurrentItem']+['Container(3).ListItemAbsolute(%d).Label'%i for i in range(12)]
 try:out['labels']=rpc('XBMC.GetInfoLabels',{'labels':labels})
 except Exception as e:out['labels_error']=type(e).__name__
 p=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json')
 if p.is_file():
  state=json.loads(p.read_text());out['installation']={k:state[k] for k in ('sequence','high_watermark','phase','host_pending','tx') if k in state}
 return out
if MODE=='restore-cinema-skin':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 if rpc('GUI.GetProperties',{'properties':['currentwindow']})['currentwindow']['id']!=10000:raise RuntimeError('HOME_REQUIRED')
 before=rpc('Settings.GetSettingValue',{'setting':'lookandfeel.skin'})['value']
 if before!='skin.bobbi.cinema':
  rpc('Settings.SetSettingValue',{'setting':'lookandfeel.skin','value':'skin.bobbi.cinema'})
  until=time.monotonic()+8
  accepted=False
  while time.monotonic()<until:
   labels=rpc('XBMC.GetInfoLabels',{'labels':['Control.GetLabel(1)','Control.GetLabel(11)']})
   active=rpc('XBMC.GetInfoBooleans',{'booleans':['Window.IsActive(10100)']})
   if active.get('Window.IsActive(10100)') and labels['Control.GetLabel(1)'] in ('保持皮肤？','Keep skin?') and labels['Control.GetLabel(11)'] in ('是','Yes'):
    builtin('SendClick(10100,11)');accepted=True;break
   time.sleep(.1)
  if not accepted:raise RuntimeError('SKIN_CONFIRMATION_NOT_OBSERVED')
  time.sleep(2)
 if rpc('Settings.GetSettingValue',{'setting':'lookandfeel.skin'})['value']!='skin.bobbi.cinema':raise RuntimeError('SKIN_NOT_RETAINED')
elif MODE=='stop-smoke':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 if not re.fullmatch(r'bobbi-ui-smoke-[0-9]+',SMOKE_RUN or ''):raise RuntimeError('INVALID_SMOKE_RUN')
 builtin('StopScript(/storage/.kodi/temp/'+SMOKE_RUN+'/smoke.py)')
elif MODE=='trace-on':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 trace=run/'entry-stack.txt'
 (run/'trace.py').write_text('import faulthandler,xbmc\nf=open('+repr(str(trace))+',"w")\nfaulthandler.dump_traceback_later(10,file=f)\nxbmc.Monitor().waitForAbort(35)\nfaulthandler.cancel_dump_traceback_later()\nf.close()\n')
 builtin('RunScript('+str(run/'trace.py')+')')
 print(json.dumps(dict(trace=str(trace))));raise SystemExit(0)
elif MODE=='trace-read':
 p=run/'entry-stack.txt'
 print(json.dumps(dict(stack=p.read_text() if p.exists() else None)));raise SystemExit(0)
elif MODE=='native-stack':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 state=json.loads(pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json').read_text())
 if state.get('phase') not in ('switching','restoring','activation_pending','restored'):raise RuntimeError('NO_PENDING_INSTALL')
 pids=subprocess.check_output(['pidof','kodi.bin']).decode().split()
 if len(pids)!=1:raise RuntimeError('KODI_PROCESS_AMBIGUOUS')
 trace=subprocess.run(['gdb','-q','-batch','-p',pids[0],'-ex','set pagination off','-ex','set print frame-arguments none','-ex','thread apply all bt 14','-ex','thread 1','-ex','info registers pc lr sp r0 r1 r2 r3','-ex','x/48a $sp','-ex','detach'],capture_output=True,timeout=25)
 print(json.dumps(dict(exit=trace.returncode,stack=trace.stdout.decode(errors='replace'),diagnostic_bytes=len(trace.stderr))));raise SystemExit(0)
elif MODE=='diagnose':
 out={}
 for name in ('installation.json','entry-boot.json'):
  p=pathlib.Path('/storage/.kodi/userdata/addon_data/script.bobbi.start')/name
  if p.is_file():
   state=json.loads(p.read_text());out[name]={k:state[k] for k in ('sequence','high_watermark','phase','host_pending','tx','moved','installed','previous_skin','previous_enabled') if k in state}
 p=pathlib.Path('/storage/.kodi/temp/kodi.log')
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-500000));lines=f.read().decode('utf-8','replace').splitlines()
 out['events']=[s[:500] for s in lines if re.search('bobbi|CPython|Python|CService|skin.estuary|OnSettingsChanged|Error Type|Error Contents|Traceback|File "',s,re.I) and not re.search('https?://|Cookie|Authorization|token|password|magnet:|CAddonMgr::FindAddons',s,re.I)][-100:]
 print(json.dumps(out));raise SystemExit(0)
elif MODE=='stage':
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
elif MODE=='wait-install':
 until=time.monotonic()+25
 while True:
  observed=view()
  installation=observed.get('installation',{})
  complete=(installation.get('sequence')==EXPECTED_SEQUENCE and installation.get('phase')=='complete'
    and not installation.get('host_pending'))
  if complete or time.monotonic()>=until:break
  time.sleep(.5)
 observed['installation_complete']=complete
 observed['expected_sequence']=EXPECTED_SEQUENCE
 print(json.dumps(observed));raise SystemExit(0)
elif MODE=='choose':
 current=view()
 if current['players'] or current['gui']['currentwindow']['id']!=EXPECTED_WINDOW:raise RuntimeError('UI_CHANGED')
 if not any(EXPECTED_LABEL in str(value) for value in current['labels'].values()):raise RuntimeError('UI_LABEL_CHANGED')
 if DWELL_SECONDS:time.sleep(DWELL_SECONDS)
 current=view()
 if current['players'] or current['gui']['currentwindow']['id']!=EXPECTED_WINDOW:raise RuntimeError('UI_CHANGED_AFTER_DWELL')
 if not any(EXPECTED_LABEL in str(value) for value in current['labels'].values()):raise RuntimeError('UI_LABEL_CHANGED_AFTER_DWELL')
 # Focus/index are chosen only from the immediately preceding real UI read.
 builtin('SetFocus(%d)'%CONTROL)
 time.sleep(.25)
 if INDEX is not None:
  rpc('Input.ExecuteAction',{'action':'firstpage'})
  time.sleep(.2)
  for _ in range(INDEX):
   rpc('Input.Down');time.sleep(.2)
  focused=view()
  if focused['gui']['currentcontrol']['label']!=CHOICE_LABEL:raise RuntimeError('LIST_CHOICE_NOT_CONFIRMED')
 else:
  focused=view()
  if (not CHOICE_LABEL or focused['gui']['currentcontrol']['label']!=CHOICE_LABEL
      or focused['labels'].get('Control.GetLabel(%d)'%CONTROL)!=CHOICE_LABEL):raise RuntimeError('FOCUS_NOT_CONFIRMED')
 if (focused['players'] or focused['gui']['currentwindow']['id']!=EXPECTED_WINDOW
     or not any(EXPECTED_LABEL in str(value) for value in focused['labels'].values())):
  raise RuntimeError('DIALOG_CHANGED_BEFORE_SELECT')
 rpc('Input.Select')
elif MODE=='back':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 rpc('Input.ExecuteAction',{'action':'back'})
elif MODE=='restart-idle':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 subprocess.run(['systemctl','restart','--no-block','kodi.service'],check=True,timeout=5)
 time.sleep(2)
 until=time.monotonic()+25
 while True:
  try:rpc('Player.GetActivePlayers');break
  except Exception:
   if time.monotonic()>=until:raise
   time.sleep(.5)
time.sleep(.3)
result=view()
if MODE=='choose':
 result['input_receipt']=dict(state='action_acknowledged',installation_completion_proved=False,
  window=EXPECTED_WINDOW,heading=EXPECTED_LABEL,control=CONTROL,index=INDEX,choice=CHOICE_LABEL,dwell_seconds=DWELL_SECONDS)
print(json.dumps(result))
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--mode',choices=('stage','open','view','choose','wait-install','back','restart-idle','restore-cinema-skin','diagnose','native-stack','trace-on','trace-read','stop-smoke'),required=True)
    p.add_argument('--smoke-run')
    p.add_argument('--run-id',required=True);p.add_argument('--entry',type=Path)
    p.add_argument('--window',type=int);p.add_argument('--label');p.add_argument('--control',type=int);p.add_argument('--index',type=int);p.add_argument('--choice-label')
    p.add_argument('--expect-sequence',type=int)
    p.add_argument('--dwell-seconds',type=int,choices=range(0,41),default=0)
    a=p.parse_args()
    if not re.fullmatch('[0-9]{8}-[0-9]{6}',a.run_id):p.error('Exact timestamp required')
    if a.mode=='stage':
        from audit_ce_entry import audit
        audit(a.entry)
    if a.mode=='choose' and (a.window is None or not a.label or a.control is None):p.error('Observed dialog identity required')
    if a.mode=='choose' and not a.choice_label:p.error('Observed choice label required')
    if a.mode=='wait-install' and (a.expect_sequence is None or a.expect_sequence<1):p.error('Expected installation sequence required')
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('entry_wire',a.transport_source/'ui-redesign/tools/device_transport.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    run='/storage/.kodi/temp/bobbi-ce-entry-'+a.run_id
    c,w=m.connect()
    try:
        if a.mode=='stage':
            with c.open_sftp() as s:
                s.mkdir(run,mode=0o700);s.put(str(a.entry),run+'/entry.zip')
        values=dict(RUN=run,MODE=a.mode,EXPECTED=hashlib.sha256(a.entry.read_bytes()).hexdigest() if a.entry else None,
                    EXPECTED_WINDOW=a.window,EXPECTED_LABEL=a.label,CONTROL=a.control,INDEX=a.index,CHOICE_LABEL=a.choice_label,SMOKE_RUN=a.smoke_run,EXPECTED_SEQUENCE=a.expect_sequence,DWELL_SECONDS=a.dwell_seconds)
        code='\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'
        code+='import traceback\ntry:\n'+textwrap.indent(REMOTE,' ')+'\n'
        code+='except Exception as e:\n print(json.dumps(dict(error_type=type(e).__name__,error_code=str(e) if re.fullmatch("[A-Z_0-9]{1,80}",str(e)) else None,frames=[dict(file=pathlib.Path(f.filename).name,line=f.lineno,function=f.name) for f in traceback.extract_tb(e.__traceback__)])))\n'
        # Keep exception diagnostics structured; the transport intentionally
        # does not return arbitrary remote stderr or response bodies.
        code='import re,pathlib,json\n'+code
        try:
            rc,result,diag=w.readonly(c,code.encode(),deadline_seconds=45)
        except Exception as exc:
            rc,result,diag=1,dict(transport_error=type(exc).__name__),False
    finally:c.close()
    out=ROOT/'review-evidence/ce2023'/('entry-device-'+a.mode+'-'+str(time.time_ns())+'.json')
    out.write_text(json.dumps(dict(run=run,mode=a.mode,transport_exit=rc,diagnostic_present=bool(diag),result=result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    display=dict(result)
    if 'stack' in display:display['stack_bytes']=len(display.pop('stack') or '')
    print(json.dumps(dict(evidence=str(out),result=display),ensure_ascii=False))
    if rc or diag or result.get('error_type') or result.get('transport_error'):return 1
    return 2 if a.mode=='wait-install' and result.get('installation_complete') is not True else 0


if __name__=='__main__':raise SystemExit(main())
