"""Read-only title/ID check before new-work trials; never prints the app key."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,urllib.request,urllib.parse
path=pathlib.Path('/storage/.kodi/addons/script.module.bobbi.core/resources/tmdb-project.json')
key=json.loads(path.read_text())['api_key']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
rows=[]
for kind,title,year in QUERIES:
    params={'api_key':key,'query':title,'language':'en-US'}
    params['primary_release_year' if kind=='movie' else 'first_air_date_year']=year
    try:
        with opener.open('https://api.themoviedb.org/3/search/'+kind+'?'+urllib.parse.urlencode(params),timeout=8) as response:
            data=json.load(response)
        rows.append(dict(query=title,kind=kind,year=year,results=[{k:r.get(k) for k in
            ('id','title','name','original_name','original_title','release_date','first_air_date')}
            for r in data.get('results',[])[:8]]))
    except Exception as error:
        rows.append(dict(query=title,error=type(error).__name__))
print(json.dumps(dict(configured_proxy=False,queries=rows),ensure_ascii=False))
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--suite',choices=('ce2011','ce2012','ce2015','ce2021'),default='ce2011')
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Keep earlier identity evidence')
    queries=([('movie','12 Angry Men',1957),('tv','The Tatami Galaxy',2010)] if args.suite=='ce2011'
             else [('movie','Rashomon',1950),('tv','Cowboy Bebop',1998)])
    if args.suite=='ce2015':
        queries=[('movie','Amelie',2001),('tv','Barakamon',2014)]
    if args.suite=='ce2021':
        queries=[('tv','Ping Pong the Animation',2014)]
    transport.REMOTE='QUERIES='+repr(queries)+'\n'+transport.REMOTE
    transport.run(args.transport_source,args.output)
