"""Read-only preparation dependency health, no credentials or cloud mutations."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,socket,subprocess,time,urllib.parse,xml.etree.ElementTree as ET
path=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/preparation.json')
out=dict(timestamp=time.time(),configuration=path.is_file(),endpoints={},services={})
if path.is_file():
 config=json.loads(path.read_text())
 for key in ('cd2_endpoint','torrserver_endpoint','tmdb_proxy'):
  if key not in config:continue
  p=urllib.parse.urlsplit(config[key])
  if p.hostname!='127.0.0.1' or p.scheme!='http' or not p.port:raise ValueError('LOCAL_ENDPOINT_REQUIRED')
  value=dict(host=p.hostname,port=p.port)
  try:
   with socket.create_connection((p.hostname,p.port),timeout=2):value['tcp']=True
  except OSError as e:value.update(tcp=False,error=type(e).__name__,errno=e.errno)
  out['endpoints'][key]=value
 for key in ('ffprobe','cd2_token_file','cd2_login_file'):
  out[key+'_present']=pathlib.Path(config[key]).is_file() if key in config else None
units=subprocess.check_output(['systemctl','list-units','--all','--plain','--no-legend','--type=service'],timeout=5).decode(errors='replace')
for line in units.splitlines():
 fields=line.split()
 if len(fields)>=4 and any(word in fields[0].lower() for word in ('cloud','cd2','bobi','bobbi')):
  out['services'][fields[0]]=fields[1:4]
out['mounts']=[dict(target=f[1],filesystem=f[2]) for line in pathlib.Path('/proc/mounts').read_text().splitlines()
              for f in [line.split()] if len(f)>2 and ('cloud' in f[1].lower() or f[2]=='fuse.clouddrive')]
out['cloud_unit_files']=[]
units=subprocess.check_output(['systemctl','list-unit-files','--no-legend','--type=service'],timeout=5).decode(errors='replace')
for line in units.splitlines():
 fields=line.split()
 if fields and any(word in fields[0].lower() for word in ('cloud','cd2','docker')):out['cloud_unit_files'].append(fields[:2])
out['cloud_addons']=[]
for path in list(pathlib.Path('/storage/.kodi/addons').glob('*/addon.xml'))+list(pathlib.Path('/usr/share/kodi/addons').glob('*/addon.xml')):
 try:
  doc=ET.parse(path).getroot()
  if any(word in (doc.get('id','')+' '+doc.get('name','')).lower() for word in ('cloud','cd2','docker')):
   out['cloud_addons'].append(dict(path=str(path),id=doc.get('id'),version=doc.get('version'),extensions=[{k:n.get(k) for k in ('point','library')} for n in doc.findall('extension')]))
 except (OSError,ET.ParseError):pass
out['cloud_processes']=[]
for path in pathlib.Path('/proc').glob('[0-9]*/exe'):
 try:
  target=path.resolve()
  if any(word in target.name.lower() for word in ('clouddrive','cd2','docker')):out['cloud_processes'].append(dict(pid=path.parent.name,executable=str(target)))
 except OSError:pass
out['docker_paths']={path:pathlib.Path(path).exists() for path in (
 '/storage/.config/system.d/service.system.docker.service',
 '/storage/.kodi/addons/service.system.docker/bin/dockerd',
 '/storage/.kodi/userdata/addon_data/service.system.docker/docker')}
out['docker_status']=subprocess.check_output(['systemctl','show','service.system.docker.service',
 '-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','LoadState',
 '-p','PartOf','-p','BindsTo','-p','StopWhenUnneeded','-p','Requires','-p','After'],timeout=5).decode().splitlines()
out['cd2_paths']={path:dict(exists=pathlib.Path(path).exists(),symlink=pathlib.Path(path).is_symlink()) for path in (
 '/storage/.kodi/addons/plugin.clouddrive2','/usr/share/kodi/addons/plugin.clouddrive2',
 '/storage/.kodi/userdata/addon_data/plugin.clouddrive2')}
out['containers']=[]
base=pathlib.Path('/storage/.kodi/userdata/addon_data/service.system.docker/docker/containers')
for path in sorted(base.glob('*/config.v2.json'))[:24]:
 value=json.loads(path.read_text())
 hostfile=path.parent/'hostconfig.json'
 host=json.loads(hostfile.read_text()) if hostfile.is_file() else {}
 state=value.get('State') or {}
 out['containers'].append(dict(id=path.parent.name,name=value.get('Name'),
  image=(value.get('Config') or {}).get('Image'),image_id=value.get('Image'),
  executable=value.get('Path'),running=state.get('Running'),exit_code=state.get('ExitCode'),
  restart_policy=(host.get('RestartPolicy') or {}).get('Name'),network=host.get('NetworkMode')))
out['cloud_named_paths']=subprocess.check_output(['find','/storage/.local','/storage/.config','/storage/.kodi/addons',
 '-maxdepth','5','-iname','*clouddrive*'],timeout=8).decode(errors='replace').splitlines()[:60]
out['docker_launcher_sources']={}
for path in ('/storage/.kodi/addons/service.system.docker/default.py','/usr/share/kodi/addons/service.system.docker/default.py'):
 launcher=pathlib.Path(path)
 if launcher.is_file() and launcher.stat().st_size<12000:out['docker_launcher_sources'][path]=launcher.read_text()
print(json.dumps(out))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Keep prior evidence')
    transport.run(a.transport_source,a.output)
