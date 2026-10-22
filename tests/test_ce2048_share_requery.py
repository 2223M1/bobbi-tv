"""Real catalogs + SQLite + AccountManager/Host/ShareStream; remote API double."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
for name in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT/'addons'/name/'lib'))
with patch('bobbi_platform.paths.profile', lambda *args, **kwargs: Path('unused-explicit-fixture-required')):
    from bobbi_catalog import catalog as qq
from bobbi_catalog.api import ShareError
from bobbi_core import juku_catalog as juku, share_failure as failure
from bobbi_core.share_stream import ShareStream
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform.host import Host
from bobbi_platform import runtime
from test_share_failure_contracts import logged_in, credential


@pytest.mark.parametrize('provider', ['qqdocs', 'juku'])
@pytest.mark.parametrize('code', ['share_revoked', 'identity_changed', 'network_timeout', 'login_required', 'cancelled'])
def test_real_host_resolve_requery_and_explicit_retry(tmp_path, monkeypatch, provider, code):
    manager, scope = logged_in(tmp_path/'account')
    host = Host(tmp_path/'platform'); host.runtime.close(); host.accounts = manager
    monkeypatch.setattr(runtime, 'call', lambda action, body, timeout: host.dispatch(action, body))
    state, public, cache = tmp_path/'juku', tmp_path/'catalog.sqlite3', tmp_path/'cache.sqlite3'
    spec = dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Fixture'], media_key='movies:101:0:0')
    title = 'Audit Fixture.2024.1080p.mkv'
    with closing(sqlite3.connect(public)) as db:
        db.executescript('CREATE TABLE entries(id INTEGER,text TEXT,norm TEXT,group_key TEXT,origin TEXT);'
            'CREATE TABLE terms(entry_id INTEGER,term TEXT); CREATE TABLE term_counts(term TEXT,n INTEGER);'
            'CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT);')
        db.execute('INSERT INTO entries VALUES(1,?,?,?,?)',('Audit Fixture 2024',qq.normalized('Audit Fixture 2024'),'g','audit'))
        for term in qq.terms('Audit Fixture'):
            db.execute('INSERT INTO terms VALUES(1,?)',(term,)); db.execute('INSERT INTO term_counts VALUES(?,1)',(term,))
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')"); db.commit()
    bound = juku._bound(juku._row(dict(tmdbId=101,typeId=1,year=2024,title='Audit Fixture',id=1,vodId=1),
        dict(url='https://115.com/s/sfixture',fileId='123',fileName=title,fileSize=1024,parentFolderId='8'),
        'shared:fixture'), juku._spec(spec))
    with closing(juku.Cache(state)) as db:
        db.replace_library('fixture',1,[bound]); db.remember([bound],juku._spec(spec))
    mode = [code]
    class API:
        account_scope = scope
        calls = 0
        def search(self,*args):
            self.calls += 1
            return [dict(fid='123',name=title,size=1024)]
        def get(self,*args): return dict(items=[],pagination=dict(total=0))
        def resolve(self,*args):
            if mode[0]: raise ShareError(mode[0],api_code=4100010)
            return 'https://cdn.115.com/video.mkv|User-Agent=fixture'
    api = API()
    def query():
        if provider == 'qqdocs':
            return qq.search(spec,time.monotonic()+5,Event(),catalogue=public,cache_path=cache,client=api)
        return [juku.fields(row) for row in juku.search(spec,time.monotonic()+5,Event(),state=state,client=api)]
    initial = query(); assert len(initial) == 1
    identity = failure.card_tuple(initial[0],spec['media_key'])
    def resolve(body, account):
        args = [body[key] for key in failure.TUPLE_FIELDS]
        if provider == 'qqdocs': return qq.resolve(*args,catalogue=public,cache_path=cache,client=api)
        return juku.resolve(*args,state=state,client=api)
    streams = ShareStream(lambda body:None,resolve,lambda url:True,account=manager)
    host.streams = streams
    try:
        streams.register(dict(identity,request_id='a'*32),scope)
        entry = streams.records['a'*32]
        with pytest.raises(ShareError,match=code): entry.grant()
        assert entry.grant_outcome()['failure']['code'] == code
        # Production provider search reuses a successful query cache. The
        # per-account overlay must survive that fast path, not just refresh.
        again = query(); assert len(again) == 1
        expected = code if code in failure.PERMANENT else ''
        assert again[0].get('shareFailure','') == expected
        session = SourceListSession({'tmdb':101},lambda rows:rows)
        source = SimpleNamespace(**again[0])
        session.publish(session.epoch,provider,[source])
        assert bool(session.snapshot()['recommended_key']) == (not expected)
        key = session.snapshot()['entries'][0][0]
        assert session.capture(session.epoch,key) is not None  # manual retry stays usable
        mode[0] = ''
        streams.register(dict(identity,request_id='b'*32),scope)
        assert streams.records['b'*32].grant().startswith('https://')
        assert not query()[0].get('shareFailure')
        # Old account's persisted outcomes never become the next account's.
        mode[0] = code
        streams.register(dict(identity,request_id='c'*32),scope)
        with pytest.raises(ShareError): streams.records['c'*32].grant()
        manager.install(credential('456'),scope)
        assert not query()[0].get('shareFailure')
    finally:
        streams.close()


def test_overlay_is_bounded_ttl_exact_tuple_and_late_failure_safe():
    scope = dict(account_id='test',epoch=1,authenticated=True)
    selected = dict(locator='am6bqqdocs://A1/1',guid='qqdocs:A1:1',title='test.mkv',size=1024,media='movies:1:0:0')
    with closing(sqlite3.connect(':memory:')) as db:
        failure.record_result(db,selected,scope,10,'share_revoked')
        assert failure.known_result(db,selected,scope)=='share_revoked'
        for key,value in [('locator','am6bqqdocs://B1/1'),('title','new.mkv'),('size',2048),('media','movies:2:0:0')]:
            assert not failure.known_result(db,dict(selected,**{key:value}),scope)
        assert not failure.known_result(db,selected,dict(scope,epoch=2))
        failure.record_result(db,selected,scope,20,'')
        failure.record_result(db,selected,scope,15,'identity_changed')
        assert not failure.known_result(db,selected,scope)
        for number in range(1030):
            failure.record_result(db,dict(selected,size=number),scope,number+30,'share_revoked')
        assert db.execute('SELECT COUNT(*) FROM share_outcomes').fetchone()[0] == 1024
        db.execute('UPDATE share_outcomes SET expires=0')
        assert not failure.known_result(db,dict(selected,size=1029),scope)
