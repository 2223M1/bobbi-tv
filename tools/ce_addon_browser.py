"""One-off upstream maintenance through Kodi's native UI, never media playback.

No database writes, generic builtins, player commands or automatic UI selections.
The maintainer observes the returned labels between each input.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPO_SHA = '2ab25bbed089accf3d837d8de68ff0113358ba71c4d6a28430ceda24acac4e78'
AUTHOR_SHA = 'bd8b3851bf4f887b9e60c95187402ec4510eea37695e709c8ba444881e40b280'
REMOTE = r'''
import hashlib,json,pathlib,shutil,sqlite3,subprocess,time,urllib.request,xml.etree.ElementTree as ET
root=pathlib.Path('/storage/.kodi')
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as response:value=json.load(response)
 if 'error' in value:raise RuntimeError('KODI_RPC_'+str(value['error']['code']))
 return value['result']
out={'action':ACTION}
if ACTION=='crash_stack':
 path=root/'temp/kodi_crashlog_20261019200619.log'
 lines=path.read_text(errors='replace').splitlines()
 starts=[i for i,line in enumerate(lines) if line.startswith('Thread 1 (')]
 out['crashed_thread']=lines[starts[0]:starts[0]+35] if starts else []
 out['registers']=[line for line in lines if re.match(r'^(?:r(?:[0-9]|1[0-5])|pc|sp|lr|cpsr|fault address|si_addr|siginfo)\s',line,re.I)]
 print(json.dumps(out,ensure_ascii=False))
 raise SystemExit(0)
if ACTION=='diagnostic':
 out['service']={key:subprocess.check_output(['systemctl','show','kodi.service','--property='+key,'--value']).decode().strip()
  for key in ('ActiveState','MainPID','ExecMainCode','ExecMainStatus','NRestarts')}
 out['log_evidence']=[]
 for name in ('kodi.old.log','kodi.log'):
  path=root/'temp'/name
  if path.is_file():
   for line in path.read_text(errors='replace').splitlines()[-2200:]:
    if any(marker in line for marker in ('repository.jacktook','Segmentation fault','Application stopped','CRepositoryUpdateJob')):
     if not any(word in line.lower() for word in ('token','password','cookie','authorization','api_key','apikey')):
      out['log_evidence'].append({'file':name,'line':line[:600]})
 out['journal']=subprocess.check_output(['journalctl','-u','kodi.service','-n','25','--no-pager','-o','cat']).decode(errors='replace')
 crash=root/'temp/kodi_crashlog_20261019200619.log'
 if crash.is_file():
  lines=crash.read_text(errors='replace').splitlines()
  out['crash_backtrace']=[line[:400] for line in lines if line.startswith(('#','Thread ','Program terminated','Core was generated'))][:60]
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('https://raw.githubusercontent.com/Sam-Max/repository.jacktook/master/repo/zips/addons.xml.md5',timeout=5) as response:
   out['repository_direct_check']={'status':response.status,'bytes':len(response.read(256))}
 except Exception as error:out['repository_direct_check']={'error':type(error).__name__}
 print(json.dumps(out,ensure_ascii=False))
 raise SystemExit(0)
if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE_NO_MAINTENANCE')
if ACTION=='cache_author_package':
 package=root/'addons/packages/plugin.video.jacktorr-1.2.2.zip'
 assert hashlib.sha256(package.read_bytes()).hexdigest()==AUTHOR_SHA
 out['author_package_sha256']=AUTHOR_SHA
if ACTION=='disable_unreachable_repo':
 rpc('Addons.SetAddonEnabled',{'addonid':'repository.jacktook','enabled':False})
if ACTION=='enable_author_repo':
 source=pathlib.Path('/storage/repository.jacktook-0.0.5.zip')
 if hashlib.sha256(source.read_bytes()).hexdigest()!=REPO_SHA:raise RuntimeError('REPO_HASH_CHANGED')
 rpc('Addons.SetAddonEnabled',{'addonid':'repository.jacktook','enabled':True})
if ACTION=='stage':
 source=pathlib.Path('/storage/repository.jacktook-0.0.5.zip')
 if hashlib.sha256(source.read_bytes()).hexdigest()!=REPO_SHA:raise RuntimeError('REPO_HASH_CHANGED')
 backup=pathlib.Path('/storage/.local/share/bobbi-upstream-restore/20261019-jacktorr')
 backup.mkdir(mode=0o700,parents=True,exist_ok=False)
 shutil.copytree(root/'addons/plugin.video.jacktorr',backup/'addon')
 profile=root/'userdata/addon_data/plugin.video.jacktorr'
 if profile.is_dir():shutil.copytree(profile,backup/'profile')
 shutil.copy2(root/'userdata/addon_data/plugin.video.bobbi.torrent/backend.json',backup/'backend.json')
 out['backup']=str(backup)
elif ACTION=='window':
 rpc('GUI.ActivateWindow',{'window':'addonbrowser','parameters':[TARGET,'return']})
elif ACTION=='key':
 gui=rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol']})
 if gui['currentwindow']['id']!=EXPECT_WINDOW:raise RuntimeError('WINDOW_CHANGED')
 if KEY in ('FirstPage','LastPage'):
  rpc('Input.ExecuteAction',{'action':KEY.lower()})
 else:rpc('Input.'+KEY)
if ACTION!='status':time.sleep(.4)
out['gui']=rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol']})
labels=['System.CurrentWindow','System.CurrentControl','Container.FolderPath','Container.NumItems','ListItem.Label','ListItem.AddonID','ListItem.AddonName','ListItem.AddonVersion']
labels+=['Control.GetLabel(%d)'%i for i in (2,3,6,7,8,9,10,11,12,13,14,416)]
for cid in (50,450,6):
 labels+=['Container(%d).NumItems'%cid,'Container(%d).Position'%cid]
 labels+=['Container(%d).ListItemPosition(%d).Label'%(cid,i) for i in range(120)]
out['labels']={k:v for k,v in rpc('XBMC.GetInfoLabels',{'labels':labels}).items() if v}
path=root/'userdata/addon_data/plugin.video.jacktorr/settings.xml'
if path.is_file():
 values={n.get('id'):n.get('value',n.text or '') for n in ET.parse(path).getroot()}
 out['safe_settings']={k:values.get(k) for k in ('service_enabled','apply_settings_to_torrserver','migrated')}
 out['settings_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
out['engine_pid']=subprocess.check_output(['systemctl','show','bobitv-torrserver.service','--property=MainPID','--value']).decode().strip()
out['installed']={}
with sqlite3.connect((root/'userdata/Database/Addons33.db').as_uri()+'?mode=ro',uri=True) as db:
 for name in ('plugin.video.jacktorr','repository.jacktook'):
  row=db.execute('SELECT enabled,origin FROM installed WHERE addonID=?',(name,)).fetchone()
  path=root/'addons'/name/'addon.xml'
  out['installed'][name]={'enabled':bool(row[0]),'origin':row[1]} if row else {}
  if path.is_file():out['installed'][name]['version']=ET.parse(path).getroot().get('version')
print(json.dumps(out,ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--action', choices=('status', 'stage', 'window', 'key', 'diagnostic', 'crash_stack', 'disable_unreachable_repo', 'enable_author_repo', 'cache_author_package'), default='status')
    parser.add_argument('--repo-zip', type=Path)
    parser.add_argument('--author-package', type=Path)
    parser.add_argument('--target', choices=('addons://', 'addons://user/all/', 'addons://repository.jacktook/'))
    parser.add_argument('--key', choices=('Up', 'Down', 'Left', 'Right', 'Select', 'Back', 'Info', 'Home', 'FirstPage', 'LastPage'))
    parser.add_argument('--expect-window', type=int)
    args = parser.parse_args()
    if args.action=='cache_author_package' and (not args.author_package or hashlib.sha256(args.author_package.read_bytes()).hexdigest()!=AUTHOR_SHA):
        parser.error('Requires unchanged, verified upstream 1.2.2 package')
    if args.action == 'key' and (not args.key or args.expect_window is None):
        parser.error('Input requires an observed window and key')
    if args.action == 'window' and not args.target:
        parser.error('Window requires a fixed target')
    if args.action == 'stage' and (not args.repo_zip or hashlib.sha256(args.repo_zip.read_bytes()).hexdigest() != REPO_SHA):
        parser.error('Stage requires the reviewed author repository ZIP')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('addon_ui_transport', args.transport_source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        if args.action=='cache_author_package':
            target='/storage/.kodi/addons/packages/plugin.video.jacktorr-1.2.2.zip'
            with client.open_sftp() as sftp:
                try:
                    with sftp.open(target,'rb') as stream:data=stream.read(16*1024*1024)
                except FileNotFoundError:
                    with sftp.open(target,'wx') as stream:stream.write(args.author_package.read_bytes())
                else:
                    if hashlib.sha256(data).hexdigest()!=AUTHOR_SHA:
                        raise RuntimeError('EXISTING_PACKAGE_DIFFERS_NOT_OVERWRITTEN')
        if args.action == 'stage':
            with client.open_sftp() as sftp:
                # No replacement of an existing package, including partial uploads.
                with sftp.open('/storage/repository.jacktook-0.0.5.zip', 'wx') as stream:
                    stream.write(args.repo_zip.read_bytes())
        params = dict(ACTION=args.action, TARGET=args.target, KEY=args.key,
                      EXPECT_WINDOW=args.expect_window, REPO_SHA=REPO_SHA, AUTHOR_SHA=AUTHOR_SHA)
        script = '\n'.join(k + '=' + repr(v) for k, v in params.items())
        script += '\nimport json,re\ntry:\n' + '\n'.join(' ' + line for line in REMOTE.splitlines())
        script += '''
except Exception as error:
 print(json.dumps(dict(action=ACTION,state='unconfirmed',error=type(error).__name__,
  code=str(error) if re.fullmatch('[A-Z0-9_-]{1,80}',str(error)) else 'READ_CURRENT_STATE_BEFORE_RETRY')))
 raise SystemExit(1)
'''
        code, result, diagnostic = wire.readonly(client, script.encode(), deadline_seconds=30)
    finally:
        client.close()
    output = ROOT / 'review-evidence' / ('ce-upstream-ui-' + str(time.time_ns()) + '.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if code or diagnostic:
        raise RuntimeError('Maintenance UI did not complete; inspect state before further actions')


if __name__ == '__main__':
    main()
