"""Start the verified existing CD2 owner; never pull/recreate/reconfigure it."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import hashlib,json,pathlib,socket,subprocess,time,urllib.request
PIN='sha256:0ba81f52d9b024acfe465707ff8afd14978b2064aae978f68d56dd6346f7d35a'
base=pathlib.Path('/storage/.kodi/userdata/addon_data/service.system.docker/docker/containers')
paths=list(base.glob('*/config.v2.json'))
if len(paths)!=1:raise RuntimeError('UNEXPECTED_CONTAINER_SET')
path=paths[0];before=json.loads(path.read_text());host=json.loads((path.parent/'hostconfig.json').read_text())
if before.get('Name')!='/clouddrive' or before.get('Image')!=PIN or host.get('NetworkMode')!='host' or host.get('RestartPolicy',{}).get('Name')!='always':raise RuntimeError('CD2_IDENTITY_CHANGED')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=3) as f:return json.load(f)['result']
if rpc('Player.GetActivePlayers'):raise RuntimeError('IDLE_REQUIRED')
backup=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261022/cd2-existing-owner')
backup.mkdir(parents=True,exist_ok=True)
for name,raw in (('config.v2.json',path.read_bytes()),('hostconfig.json',(path.parent/'hostconfig.json').read_bytes())):
 with (backup/name).open('xb') as f:f.write(raw)
subprocess.run(['systemctl','start','service.system.docker.service'],check=True,timeout=25,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
until=time.monotonic()+15
ready=False
while time.monotonic()<until:
 try:
  with socket.create_connection(('127.0.0.1',19798),timeout=.5):ready=True;break
 except OSError:time.sleep(.5)
docker='/storage/.kodi/addons/service.system.docker/bin/docker'
raw=subprocess.check_output([docker,'inspect','clouddrive'],timeout=4)
value=json.loads(raw)[0]
if value.get('Image')!=PIN:raise RuntimeError('LIVE_IMAGE_CHANGED')
result=dict(timestamp=time.time(),container=value['Id'],image=value['Image'],running=value['State']['Running'],
 local_port_ready=ready,pulled=False,recreated=False,config_preserved=digest(value['Config'])==digest(before['Config']),
 host_config_preserved=digest(value['HostConfig'])==digest(host),backup=str(backup),
 mounts=[dict(source=m.get('Source'),destination=m.get('Destination'),propagation=m.get('Propagation')) for m in value.get('Mounts',[])])
result['docker_addon']=rpc('Addons.GetAddonDetails',{'addonid':'service.system.docker','properties':['enabled','version']})
print(json.dumps(result))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Keep previous restore receipt')
    transport.run(a.transport_source,a.output)
