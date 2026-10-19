"""Bounded new-work metadata lookup; no playback or cloud preparation."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,urllib.request,urllib.parse,time
key=pathlib.Path('/storage/.local/share/bobitv/preparation-private/tmdb-key').read_text().strip()
out=[]
for title in ('Haibane Renmei','Kino\'s Journey'):
 q=urllib.parse.urlencode(dict(api_key=key,query=title,language='en-US'))
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('https://api.themoviedb.org/3/search/tv?'+q,timeout=8) as r:data=json.load(r)
  out.append(dict(query=title,results=[{k:row.get(k) for k in ('id','name','original_name','first_air_date')} for row in data.get('results',[])[:8]]))
 except Exception as e:out.append(dict(query=title,error=type(e).__name__))
print(json.dumps(out))
'''
if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--transport-source',type=Path,required=True)
 args=parser.parse_args()
 transport.run(args.transport_source,Path(__file__).resolve().parents[1]/'review-evidence/ce1908-new-anime-metadata.json')
