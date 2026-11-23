"""Read-only CE parity evidence: existing torrent metadata and prior requests.

Never adds/preloads/removes torrents, opens media, changes accounts or runs plugins.
Private connection configuration stays on the device.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

REMOTE = r'''
import base64,ipaddress,json,pathlib,re,time,urllib.request,urllib.parse
root=pathlib.Path('/storage/.kodi')
config=json.loads((root/'userdata/addon_data/plugin.video.bobbi.torrent/backend.json').read_text())
p=urllib.parse.urlsplit(config['endpoint'])
if not (p.hostname=='localhost' or ipaddress.ip_address(p.hostname).is_loopback):raise ValueError('NOT_LOOPBACK')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def post(path,body):
 headers={'Content-Type':'application/json'}
 if config.get('auth'):
  value=config['auth']['username']+':'+config['auth']['password']
  headers['Authorization']='Basic '+base64.b64encode(value.encode()).decode()
 req=urllib.request.Request(config['endpoint'].rstrip('/')+path,json.dumps(body).encode(),headers)
 with opener.open(req,timeout=6) as response:
  raw=response.read(2*1024*1024+1)
 if len(raw)>2*1024*1024:raise ValueError('RESPONSE_LIMIT')
 return json.loads(raw)
out={'read_only':True,'time':time.time(),'torrent_list':[],'metadata':[],'prior_trials':[]}
rows=post('/torrents',{'action':'list'})
began=time.monotonic()
while WATCH and time.monotonic()-began<30:
 targets=[r for r in rows if re.search(r'flip.?flappers|フリップフラッパーズ',str(r.get('name',''))+' '+str(r.get('title','')),re.I)]
 if targets:break
 time.sleep(.25)
 rows=post('/torrents',{'action':'list'})
if not isinstance(rows,list):raise ValueError('LIST_SCHEMA')
for row in rows[:128]:
 safe={k:row[k] for k in ('hash','name','title','stat','stat_string') if k in row}
 out['torrent_list'].append(safe)
 title=str(row.get('name',''))+' '+str(row.get('title',''))
 if re.search(r'flip.?flappers|フリップフラッパーズ|haibane|灰羽',title,re.I):
  for attempt in range(55 if WATCH else 3):
   data=post('/torrents',{'action':'get','hash':row['hash']})
   if isinstance(data,list) and len(data)==1:data=data[0]
   safe={k:data[k] for k in ('hash','name','title','stat','stat_string','active_peers','total_peers','download_speed','preloaded_bytes','torrent_size','loaded_size') if k in data}
   files=data.get('file_stats')
   safe['file_stats']=[{k:v for k,v in f.items() if k in ('id','path','length')} for f in files] if isinstance(files,list) else files
   out['metadata'].append(safe)
   if files:break
   if WATCH and time.monotonic()-began>=35:break
   if attempt<(54 if WATCH else 2):time.sleep(.2 if WATCH else 1)
trials=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261019')
for path in sorted(p for p in trials.glob('trial-*.json') if 'flip' in p.name or 'haibane' in p.name):
 value=json.loads(path.read_text())
 out['prior_trials'].append({'file':path.name,'safe_fields':{k:v for k,v in value.items()
  if k in ('request_id','selection_identity','info_hash','season','episode','release_title','episode_binding','selected_at','state','title','source_title','failure','selected_card','selected_source','test')}})
log=(root/'temp/kodi.old.log').read_text(errors='replace').splitlines() if (root/'temp/kodi.old.log').is_file() else []
log+=(root/'temp/kodi.log').read_text(errors='replace').splitlines()
out['failure_stages']=[line[-600:] for line in log if any(k in line for k in ('BOBBI-TORRENT','target_unresolved','EXACT_FILE_UNRESOLVED','RELEASE_ENVELOPE_UNPROVEN'))
 and not any(s in line.lower() for s in ('http','magnet:','token','password','cookie','authorization'))][-35:]
print(json.dumps(out,ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--watch', action='store_true', help='Observe an operator-started Flip Flappers torrent for up to 35 seconds; never add one')
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError('Evidence already exists')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('parity_transport', args.transport_source / 'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    try:
        code, result, diagnostic = wire.readonly(client, ('WATCH='+repr(args.watch)+'\n'+REMOTE).encode(), deadline_seconds=45)
    finally:
        client.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False))
    if code or diagnostic:
        raise RuntimeError('Read-only probe failed')


if __name__ == '__main__':
    main()
