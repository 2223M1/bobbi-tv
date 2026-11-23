"""Public catalogue pagination fields only; project key is never returned."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import sys,json,pathlib,time,urllib.parse
root=pathlib.Path('/storage/.kodi/addons/script.module.bobbi.core')
sys.path.insert(0,str(root/'lib'))
from bobbi_core.metadata_transport import fetch
key=json.loads((root/'resources/tmdb-project.json').read_text())['api_key']
out=[]
for query in ('Samurai Champloo','サムライチャンプルー'):
 started=time.monotonic()
 try:
  value=fetch('https://api.themoviedb.org/3/search/movie?'+urllib.parse.urlencode(dict(api_key=key,query=query,page=1,language='zh-CN')),started+12)
  body=json.loads(value['body'])
  out.append(dict(query=query,status=value['status'],route=value['route'],seconds=round(time.monotonic()-started,3),page=body.get('page'),total_results=body.get('total_results'),total_pages=body.get('total_pages'),count=len(body.get('results',[]))))
 except Exception as e:out.append(dict(query=query,error=type(e).__name__,seconds=round(time.monotonic()-started,3)))
print(json.dumps(out,ensure_ascii=False))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError('Keep earlier evidence')
    transport.run(a.transport_source,a.output)
