"""Read-only live metadata audit of trial fixtures; never starts playback."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.project_metadata import tmdb_key
from bobbi_core.metadata_transport import fetch


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--works',nargs='+')
    a=p.parse_args();key=tmdb_key(a.config)
    if not key:raise ValueError('APPLICATION_CONFIG_REQUIRED')
    tree=ast.parse((ROOT/'tools/ce_trial_remote.py').read_text(encoding='utf-8'))
    tests=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TESTS' for t in n.targets))
    if a.works:tests={k:v for k,v in tests.items() if k in a.works}
    def fields(v):return {k:v.get(k) for k in ('id','name','title','original_name','original_title','original_language','first_air_date','release_date') if k in v}
    def get(path,**params):
        result=fetch('https://api.themoviedb.org/3/'+path+'?'+urlencode(dict(api_key=key,language='en-US',**params)),time.monotonic()+12)
        if result['status']!=200:raise ValueError('METADATA_HTTP')
        return json.loads(result['body'])
    def inspect(pair):
        name,test=pair
        row=dict(name=name,expected=test)
        try:
            row['by_id']=fields(get(test['kind']+'/'+str(test['tmdb_id'])))
            row['by_title']=[fields(v) for v in get('search/'+test['kind'],query=test['title']).get('results',[])[:5]]
        except Exception as error:row.update(error=type(error).__name__,stage=getattr(error,'stage',None))
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(inspect,tests.items()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(time=time.time(),read_only=True,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(a.output),rows=rows)))


if __name__=='__main__':main()
