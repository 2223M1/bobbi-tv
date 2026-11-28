"""Measure public CatalogQuery pages against an isolated synthetic read model (no media)."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
import sys
from threading import RLock
import time

SCOPE = {'provider': '115', 'account_id': 'bench', 'epoch': 1}
SOURCE = 'a' * 32

def seed(path, movies, episodes):
    from bobbi_core.media_library_index import MediaIndex
    if path.exists() or not (1 <= movies <= 30000 and 10 <= episodes <= 350000):
        raise ValueError('Use a new fixture database; expected 1..30000 films and 10..350000 episodes')
    owner = MediaIndex(path)
    owner.close()
    with closing(sqlite3.connect(str(path))) as db, db:
        db.execute('CREATE TABLE bench_fixture(movies INTEGER, episodes INTEGER)')
        db.execute('INSERT INTO bench_fixture VALUES(?,?)', (movies, episodes))
        db.execute('INSERT INTO catalog_sources VALUES(?,1)', (SOURCE,))
        db.execute('CREATE TEMP TABLE seed(n INTEGER PRIMARY KEY, movie INTEGER, work INTEGER, s INTEGER, ep INTEGER)')
        db.execute('WITH RECURSIVE seq(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM seq WHERE n<?) '
                   'INSERT INTO seed SELECT n,n<=?,CASE WHEN n<=? THEN n ELSE ?+1+(n-?-1)/100 END,'
                   'CASE WHEN n>? THEN 1+((n-?-1)%100)/10 END,CASE WHEN n>? THEN 1+((n-?-1)%10) END FROM seq',
                   (movies+episodes, movies,movies,movies,movies,movies,movies,movies,movies))
        db.execute("""WITH data AS (SELECT printf('%064x',n) id, printf('%064x',10000000+work) wid,
                   CASE WHEN NOT movie THEN printf('%064x',20000000+work*10+s) END sid,
                   CASE WHEN NOT movie THEN printf('%064x',30000000+n) END eid,
                   printf('Work %06d',work) title, printf('File %06d.mkv',n) filename, * FROM seed)
                   INSERT INTO catalog_rows SELECT id,'115','bench',wid,sid,eid,title,filename,lower(title),lower(title||' '||filename),
                   CASE WHEN movie THEN 'movie' ELSE 'tv' END,s,ep,'confirmed',n,n,id,'','',NULL,2020,lower(filename) FROM data""")
        db.execute("INSERT INTO memberships SELECT ?,id,'gen',1 FROM catalog_rows", (SOURCE,))
        db.execute("""INSERT INTO objects SELECT id,provider,account,'{"provider":"115","id":"'||id||'","size":1024,"name":"'||filename||'"}' FROM catalog_rows""")
        db.execute("INSERT INTO reviews SELECT id,'confirmed','','[]',1,NULL,'manual' FROM catalog_rows")

class Reader:
    def __init__(self, path):
        self.db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.15)
        self.db.row_factory = sqlite3.Row
        self.lock, self.file_facts = RLock(), None
    def scope_revision(self, expected):
        from bobbi_core.media_library_index import MediaIndex
        return MediaIndex.scope_revision(self, expected)

def measure(path, repeats):
    from bobbi_core.catalog_query import CatalogQuery, wire, parameters
    from contextlib import closing
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        movies,episodes=db.execute('SELECT movies, episodes FROM bench_fixture').fetchone()
    cases={'movies':{'view':'works','media_kind':'movie'}, 'files':{'view':'files'},
           'episodes':{'view':'episodes','parent_entity_id':format(20000000+(movies+1)*10+1,'064x')},
           'search':{'view':'works','text':'Work 000123'}}
    result={}
    for name,query in cases.items():
        index=Reader(path);reader=CatalogQuery(index);sql,args=reader._sql(SCOPE,parameters(query),None,21)
        try:
            plan=[r[3] for r in index.db.execute('EXPLAIN QUERY PLAN '+sql,args)]
            counts=[];elapsed=[];digests=[];bytes_out=[];sqls=[0]
            index.db.set_trace_callback(lambda stmt:sqls.__setitem__(0,sqls[0]+1))
            for page in range(repeats+1):
                sqls[0]=0;t=time.perf_counter();out=reader.query(SCOPE,query);ms=(time.perf_counter()-t)*1000
                elapsed.append(round(ms,3));counts.append(sqls[0]);digests.append(hashlib.sha256(wire(out['items'])).hexdigest());bytes_out.append(len(wire(out)))
            assert len(set(digests))==1
            follow=None
            if out['next_cursor']:
                sqls[0]=0;t=time.perf_counter();nxt=reader.query(SCOPE,query,cursor=out['next_cursor']);follow={'ms':round((time.perf_counter()-t)*1000,3),'sql_calls':sqls[0],'digest':hashlib.sha256(wire(nxt['items'])).hexdigest(),'bytes':len(wire(nxt))}
            ordered=sorted(elapsed[1:]);result[name]=dict(first_connection_ms=elapsed[0],warm_ms=elapsed[1:],p50_ms=statistics.median(ordered),p95_ms=ordered[math.ceil(.95*len(ordered))-1],sql_calls=counts,rows=len(out['items']),digest=digests[0],bytes=max(bytes_out),second_page=follow,plan=plan)
        finally:index.db.close()
    return dict(sqlite=sqlite3.sqlite_version,synthetic=True,movies=movies,episodes=episodes,measured='local projection query and serialization, OS cache not flushed',cases=result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database',type=Path);p.add_argument('--create',action='store_true');p.add_argument('--movies',type=int,default=30000);p.add_argument('--episodes',type=int,default=350000);p.add_argument('--repeat',type=int,default=5);p.add_argument('--core-lib',type=Path,default=Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib');argv=p.parse_args()
    if not 1<=argv.repeat<=50:p.error('repeat must be 1..50')
    sys.path.insert(0,str(argv.core_lib));
    if argv.create:seed(argv.database,argv.movies,argv.episodes)
    print(json.dumps(measure(argv.database,argv.repeat),ensure_ascii=False,indent=2))
