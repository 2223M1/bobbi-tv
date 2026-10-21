"""Maintainer-only diagnostics for the serialized, idle lifecycle trial."""
import argparse
from pathlib import Path
import time
import probe_ce_candidate as probe

REMOTE = r'''
import json,pathlib,subprocess,urllib.request
root=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform')
runs=sorted(pathlib.Path('/storage/.kodi/temp').glob('bobbi-recovery-*'))
run=runs[-1]
state=json.loads((run/'progress.json').read_text())
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as r:v=json.load(r)
 if 'error' in v:raise RuntimeError('RPC_FAILED')
 return v['result']
result=dict(action=ACTION,run=str(run))
if ACTION=='snapshot':
 text=pathlib.Path('/storage/.kodi/temp/kodi.log').read_text(errors='replace')
 result.update(progress=state,lines=[x for x in text.splitlines() if any(k in x for k in ('RUNTIME_CLOSE_','SHUTDOWN_','BOBBI-SHUTDOWN','script didn'))][-100:])
 p=root/'shutdown-stack.txt'
 result['stack']=p.read_text() if p.exists() else None
 p=run/'trial-stack.txt'
 result['trial_stack']=p.read_text() if p.exists() else None
elif ACTION=='restart-stalled':
 if state['events'][-1] not in ('before_normal_quiesce','normal_quiesce_lease_acquired'):raise RuntimeError('NOT_IDLE_LIFECYCLE_STALL')
 try:
  if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 except (TimeoutError,OSError):pass
 subprocess.run(['systemctl','restart','--no-block','kodi.service'],check=True)
 result['restart_queued']=True
elif ACTION=='restore':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
 for name in ('plugin.video.bobbi.torrent','plugin.video.bobbi'):
  rpc('Addons.SetAddonEnabled',dict(addonid=name,enabled=name in state['enabled_before']))
 rpc('Settings.SetSettingValue',dict(setting='lookandfeel.skin',value=state['skin_before']))
 result['restored']=True
elif ACTION=='trace-on':
 (root/'shutdown-stack-enabled').touch()
 result['diagnostics_enabled']=True
elif ACTION=='trace-off':
 (root/'shutdown-stack-enabled').unlink(missing_ok=True)
 result['diagnostics_enabled']=False
elif ACTION=='native-stack':
 if state['events'][-1] not in ('before_normal_quiesce','normal_quiesce_lease_acquired'):raise RuntimeError('NOT_IDLE_LIFECYCLE_STALL')
 pids=subprocess.check_output(['pidof','kodi.bin']).decode().split()
 if len(pids)!=1:raise RuntimeError('KODI_PROCESS_AMBIGUOUS')
 trace=subprocess.run(['gdb','-q','-batch','-p',pids[0],'-ex','set pagination off',
   '-ex','set print frame-arguments none','-ex','thread apply all bt 14','-ex','detach'],capture_output=True,timeout=25)
 result.update(gdb_exit=trace.returncode,stack=trace.stdout.decode(errors='replace'),diagnostics=trace.stderr.decode(errors='replace'))
print(json.dumps(result))
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--action',choices=('snapshot','restart-stalled','restore','trace-on','trace-off','native-stack'),required=True)
    args=parser.parse_args()
    code='ACTION='+repr(args.action)+'\n'+REMOTE
    probe.REMOTE='import json,traceback\ntry:\n exec('+repr(code)+')\nexcept Exception as e:\n print(json.dumps(dict(passed=False,error=type(e).__name__,frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(e.__traceback__)])))'
    probe.run(args.transport_source,probe.ROOT/'review-evidence'/('ce-recovery-'+args.action+'-'+str(time.time_ns())+'.json'))
