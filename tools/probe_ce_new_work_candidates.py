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
        for title,words in [('荒蛮故事',['荒蛮故事','Wild Tales','Relatos salvajes']),('少女终末旅行',['少女终末旅行','Girls Last Tour','Shoujo Shuumatsu']),('一次别离',['一次别离','A Separation']),('灰羽联盟',['灰羽联盟','Haibane']),('虫师',['虫师','Mushishi']),('醉乡民谣',['醉乡民谣','Llewyn'])]:
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
    args=parser.parse_args()
    transport.run(args.transport_source,Path(__file__).resolve().parents[1]/'review-evidence/ce-new-work-candidates.json')
