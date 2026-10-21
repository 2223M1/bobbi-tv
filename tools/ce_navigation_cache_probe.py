"""Read public navigation-cache evidence without invoking product fetch/load."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

REMOTE = r'''
import hashlib,io,json,pathlib,pickle,pickletools,sqlite3,time,urllib.parse,urllib.request
def rpc(method,params):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:return json.load(f)['result']
class PublicData(pickle.Unpickler):
 def find_class(self,*_):raise ValueError('NON_PUBLIC_PICKLE')
 def persistent_load(self,*_):raise ValueError('NON_PUBLIC_PICKLE')
def checked(blob):
 if len(blob)>16*1024*1024:raise ValueError('CACHE_LIMIT')
 forbidden={'GLOBAL','STACK_GLOBAL','REDUCE','BUILD','INST','OBJ','NEWOBJ','NEWOBJ_EX','EXT1','EXT2','EXT4','PERSID','BINPERSID'}
 for opcode,_,_ in pickletools.genops(blob):
  if opcode.name in forbidden:raise ValueError('CACHE_OBJECT')
 return PublicData(io.BytesIO(blob)).load()
labels=rpc('XBMC.GetInfoLabels',{'labels':['ListItem.FileNameAndPath','ListItem.Label','ListItem.DBType']})
url=urllib.parse.urlsplit(labels.pop('ListItem.FileNameAndPath',''))
fields=urllib.parse.parse_qs(url.query) if url.scheme=='plugin' and url.netloc=='plugin.video.bobbi' else {}
focus={k:v[0] for k,v in fields.items() if len(v)==1 and k in ('action','mode','id','ids','season')}
result=dict(timestamp=time.time(),focus=focus,labels=labels,gui=rpc('GUI.GetProperties',{'properties':['currentwindow']}),players=rpc('Player.GetActivePlayers',{}))
path=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/plugin.video.bobbi.cached.sqlite')
result['cache_present']=path.is_file()
if path.is_file():
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1) as db:
  db.execute('PRAGMA query_only=ON')
  row=db.execute('SELECT data,expires FROM cached WHERE key=?',('bobi_related_movies_v4:'+str(IDENTIFIER),)).fetchone()
 if row:
  blob,expires=row
  result['related']=dict(blob_sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob),expires=expires)
  try:
   value=checked(blob)
   if not isinstance(value,dict) or value.get('id')!=IDENTIFIER:raise ValueError('CACHE_ID')
   result['related'].update({k:value.get(k) for k in ('schema','id','time','complete','detail_after')})
   result['related']['movie_ids']=[v['id'] for v in value.get('movies',[]) if isinstance(v,dict) and type(v.get('id')) is int]
  except Exception as e:result['related']['decode_error']=type(e).__name__
print(json.dumps(result,ensure_ascii=False))
'''

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--id',type=int,required=True)
    a=p.parse_args()
    if not 0<a.id<10**9 or a.output.exists():p.error('Public ID and new output required')
    transport.REMOTE='IDENTIFIER='+repr(a.id)+'\n'+REMOTE
    transport.run(a.transport_source,a.output)
