"""Read-only upstream ownership inventory; never refresh repos or play media."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,pathlib,sqlite3,urllib.request,xml.etree.ElementTree as ET
root=pathlib.Path('/storage/.kodi')
names=('script.module.certifi','script.module.chardet','script.module.idna',
 'script.module.infotagger','script.module.jurialmunkey','script.module.requests',
 'script.module.routing','script.module.urllib3','script.skinvariables',
 'plugin.video.jacktorr','repository.jacktook','repository.jurialmunkey',
 'repository.xbmc.org')
result={'schema':1,'read_only':True,'addons':{},'engine_processes':[]}
database=root/'userdata/Database/Addons33.db'
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
 for name in names:
  value={}
  row=db.execute('SELECT enabled,origin,disabledReason FROM installed WHERE addonID=?',(name,)).fetchone()
  if row:value.update(enabled=bool(row[0]),origin=row[1],disabled_reason=row[2])
  for base in (root/'addons',pathlib.Path('/usr/share/kodi/addons')):
   path=base/name/'addon.xml'
   if path.is_file():
    data=path.read_bytes(); meta=ET.fromstring(data)
    value.update(version=meta.get('version'),id=meta.get('id'),addon_xml_sha256=hashlib.sha256(data).hexdigest())
    files={item.relative_to(path.parent).as_posix():hashlib.sha256(item.read_bytes()).hexdigest()
      for item in sorted(path.parent.rglob('*')) if item.is_file()
      and '__pycache__' not in item.parts and item.suffix not in ('.pyc','.pyo')}
    value['installed_content_sha256']=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    value['installed_content_files']=len(files)
    if name=='plugin.video.jacktorr':
     value['service_sha256']={rel:hashlib.sha256((path.parent/rel).read_bytes()).hexdigest()
       for rel in ('service.py','lib/service.py','lib/settings.py','lib/os_platform.py') if (path.parent/rel).is_file()}
    break
  result['addons'][name]=value
for path in pathlib.Path('/proc').iterdir():
 if not path.name.isdigit():continue
 try:
  name=(path/'comm').read_text().strip()
  if 'torrserver' not in name.lower():continue
  status=(path/'status').read_text().splitlines()
  parent=next((line.split(':',1)[1].strip() for line in status if line.startswith('PPid:')),None)
  result['engine_processes'].append({'pid':int(path.name),'name':name,'parent_pid':parent,
   'cgroup':(path/'cgroup').read_text().strip()})
 except (OSError,ValueError):pass
try:
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
  json.dumps({'jsonrpc':'2.0','id':1,'method':'Player.GetActivePlayers'}).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as response:
  data=json.load(response)
 result['playing']=bool(data['result']) if 'result' in data else None
except Exception as error:result['playback_status_error']=type(error).__name__
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Do not replace earlier evidence')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('upstream_transport', args.transport_source / 'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    try:
        code, result, diagnostic = wire.readonly(client, REMOTE.encode(), deadline_seconds=20)
        if code or diagnostic:
            raise RuntimeError('Read-only upstream inspection failed')
    finally:
        client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
