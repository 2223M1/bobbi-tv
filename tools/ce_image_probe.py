"""Bounded read-only artwork diagnostics; never emit image-service tokens."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import collections,json,pathlib,re,sqlite3,time,urllib.parse,urllib.request
root=pathlib.Path('/storage/.kodi')
profile=root/'userdata/addon_data/script.module.bobbi.platform'
runtime=profile/'image-runtime.json'
config=json.loads(runtime.read_text()) if runtime.is_file() else {}
result=dict(runtime_present=bool(config),port=config.get('port'),texture_origins={},old_local_ports={},current_local_rows=0)
def rpc(method,params):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:return json.load(f).get('result',{})
labels=['Container(%d).ListItemAbsolute(%d).Art(poster)'%(cid,i) for cid in (50,9810,9830,9840,9850,9860) for i in range(8)]
art=rpc('XBMC.GetInfoLabels',{'labels':labels})
result['displayed_art']=[]
for label,url in art.items():
 if not url:continue
 try:p=urllib.parse.urlsplit(url)
 except ValueError:continue
 result['displayed_art'].append(dict(control=label,host=p.hostname,port=p.port,size=(re.findall('/(?:t/p|art/[a-f0-9]{64})/([^/]+)/',p.path) or [''])[0],current_endpoint=p.port==config.get('port') and p.path.startswith('/art/'+config.get('token','')+'/')))
dbfile=root/'userdata/Database/Textures13.db'
if dbfile.is_file():
 with sqlite3.connect(dbfile.as_uri()+'?mode=ro',uri=True,timeout=1) as db:
  rows=db.execute('SELECT url,cachedurl FROM texture').fetchall()
 counts,old=collections.Counter(),collections.Counter()
 for url,cached in rows:
  try:p=urllib.parse.urlsplit(url)
  except ValueError:continue
  if p.scheme=='image':continue
  counts[p.hostname or 'local']+=1
  if p.hostname=='127.0.0.1' and p.path.startswith('/art/'):
   if p.port==config.get('port') and p.path.startswith('/art/'+config.get('token','')+'/'):
    result['current_local_rows']+=1
   else:old[str(p.port)]+=1
 result['texture_origins']=dict(counts)
 result['old_local_ports']=dict(old)
images=profile/'images'
if images.is_dir():
 sizes=[p.stat().st_size for p in images.iterdir() if p.is_file() and re.fullmatch('[a-f0-9]{64}\\.(jpg|jpeg|png|webp)',p.name)]
 result['image_files'],result['image_bytes']=len(sizes),sum(sizes)
log=root/'temp/kodi.log'
if log.is_file():
 lines=log.read_text(errors='replace').splitlines()[-15000:]
 result['image_failure_stages']=dict(collections.Counter(stage for line in lines for stage in re.findall(r'IMAGE_(?:TIMEOUT|CONNECT|DNS|HEADERS|BODY|IO|HTTP_[0-9]+|COOLDOWN|FORMAT|UNAVAILABLE)',line)))
 result['kodi_image_errors']=sum('CCurlFile' in line and ('image.tmdb.org' in line or '/art/' in line) for line in lines)
 result['warm_events']=[line[line.find('Navigation warm'):][:220] for line in lines if 'Navigation warm:' in line][-12:]
 result['navigation_events']=[line[line.find('Navigation preparation'):][:220] for line in lines if 'Navigation preparation finished:' in line][-12:]
result['timestamp']=time.time()
print(json.dumps(result))
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Keep previous evidence')
    transport.run(args.transport_source,args.output)
