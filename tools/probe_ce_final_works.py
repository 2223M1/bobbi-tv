"""Authenticated direct metadata identity checks for fresh acceptance works."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json,pathlib,time,urllib.request,urllib.parse
key=pathlib.Path('/storage/.local/share/bobitv/preparation-private/tmdb-key').read_text().strip()
result=[]
for kind,title,year in [('movie','Burning',2018),('tv','Flip Flappers',2016)]:
    query=dict(api_key=key,query=title,language='en-US')
    query['primary_release_year' if kind=='movie' else 'first_air_date_year']=year
    began=time.monotonic()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('https://api.themoviedb.org/3/search/'+kind+'?'+urllib.parse.urlencode(query),timeout=8) as response:
            data=json.load(response)
        result.append(dict(kind=kind,query=title,year=year,seconds=time.monotonic()-began,
            results=[{k:row.get(k) for k in ('id','title','name','original_title','original_name','release_date','first_air_date','original_language')} for row in data.get('results',[])[:10]]))
    except Exception as error:
        result.append(dict(kind=kind,query=title,error=type(error).__name__))
print(json.dumps(dict(configured_proxy=False,queries=result),ensure_ascii=False))
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('final_works_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client,wire=module.connect()
    try:rc,result,diag=wire.readonly(client,REMOTE.encode(),deadline_seconds=25)
    finally:client.close()
    (ROOT/'review-evidence/ce-final-fresh-work-identities.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if rc or diag:raise RuntimeError('Identity query failed')

if __name__=='__main__':main()
