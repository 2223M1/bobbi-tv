"""Read existing Juku cache candidates only; never opens media or cloud tasks."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,sqlite3,time
path=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.jacktook/juku/catalog.sqlite3')
result={'mode':'readonly','catalog_exists':path.is_file(),'candidates':[]}
if path.is_file():
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0)
    end=time.monotonic()+10
    db.set_progress_handler(lambda:int(time.monotonic()>end),1000)
    try:
        result['tables']=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for title,words in QUERIES:
            rows=[]
            for word in words:
                for raw, in db.execute('SELECT payload FROM shared_rows WHERE payload LIKE ? LIMIT 12',('%'+word+'%',)):
                    row=json.loads(raw)
                    safe={key:row.get(key) for key in ('tmdb','kind','season','episode','name','size','work_title','work_year')}
                    if safe not in rows: rows.append(safe)
            result['candidates'].append({'title':title,'shared_rows':rows})
        result['first_episode_inventory']=[]
        for raw, in db.execute("SELECT payload FROM shared_rows WHERE kind='tv' AND season=1 AND episode=1 LIMIT 40"):
            row=json.loads(raw)
            result['first_episode_inventory'].append({key:row.get(key) for key in ('tmdb','kind','season','episode','name','size','work_title','work_year')})
    finally: db.close()
print(json.dumps(result,ensure_ascii=False))
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--query', action='append', required=True,
                        help='Title aliases separated by |; bounded read-only cache search')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    queries = [row.split('|') for row in args.query]
    if len(queries)>6 or any(not row or len(row)>5 or any(not q or len(q)>120 for q in row) for row in queries):
        parser.error('At most six works with five bounded aliases each')
    transport.REMOTE = 'QUERIES='+repr([(row[0],row) for row in queries])+'\n'+transport.REMOTE
    if args.output.exists(): raise FileExistsError('Keep previous trial evidence')
    transport.run(args.transport_source,args.output)
