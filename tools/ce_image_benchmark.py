"""Bounded GETs of displayed public posters; no video/account operations."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import concurrent.futures,hashlib,json,pathlib,re,time,urllib.parse,urllib.request
root=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform')
config=json.loads((root/'image-runtime.json').read_text())
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:return json.load(f)['result']
if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
labels=['Container(%d).ListItemAbsolute(%d).Art(poster)'%(cid,i) for cid in (9850,9860) for i in range(8)]
values=rpc('XBMC.GetInfoLabels',{'labels':labels})
items=[]
for key,url in values.items():
 p=urllib.parse.urlsplit(url)
 prefix='/art/'+config['token']+'/'
 if p.hostname!='127.0.0.1' or p.port!=config['port'] or not p.path.startswith(prefix):continue
 path='/t/p/'+p.path[len(prefix):]
 if not re.fullmatch(r'/t/p/w342/[A-Za-z0-9_-]{1,128}\.(jpg|jpeg|png|webp)',path):continue
 if any(row[1]==path for row in items):continue
 items.append((url,path,key))
items=items[:12]
def get(row):
 url,path,key=row
 digest=hashlib.sha256(path.encode()).hexdigest()
 record=dict(control=key,path_digest=digest,cached_before=(root/'images'/(digest+'.'+path.rsplit('.',1)[1])).is_file())
 started=time.monotonic()
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=12) as response:
   raw=response.read(2*1024*1024+1)
   record.update(status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 except Exception as error:record['error']=type(error).__name__
 record['seconds']=round(time.monotonic()-started,3)
 return record
started=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(get,items))
print(json.dumps(dict(scope='displayed original public TMDb w342 posters; same local runtime URL',count=len(rows),success=sum(row.get('status')==200 for row in rows),seconds=round(time.monotonic()-started,3),rows=rows)))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError('Keep previous measurement')
    transport.run(a.transport_source,a.output)
