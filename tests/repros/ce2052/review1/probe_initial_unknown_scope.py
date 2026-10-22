#!/usr/bin/env python3
"""Real catalogue resolve then account switch after initial status IPC failure.

Real QQdocs search/selected/resolve/Cache, SQLite, AccountManager, Binding and
SourceListSession. Remote share API and the status IPC transport are doubles.
The initial account_status lookup alone is unavailable in the failing case.
There is no metadata contention, fabricated ShareState, or real account IO.
"""
import argparse
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Event
import time
from unittest.mock import patch


def load_class(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SourceListSession


def credentials(user):
    return dict(app='os_linux',cookies=dict(UID=user+'_fixture',CID='fixture-cid',SEID='fixture-seid'))


def run_case(root, Session, initial_unknown, transition, modules):
    qq, failure, runtime, AccountManager, ShareError, Binding, TorrentStream, ProgressiveSearch, rank_sources, source_preference = modules
    root.mkdir(parents=True)
    manager = AccountManager(root/'account.json')
    account_a = manager.install(credentials('123'), manager.snapshot())
    public, cache_path = root/'catalog.sqlite3', root/'cache.sqlite3'
    spec = dict(tmdb_id=101,mode='movies',year=2024,aliases=['Audit Fixture'],media_key='movies:101:0:0')
    title = 'Audit Fixture.2024.1080p.mkv'
    with closing(sqlite3.connect(public)) as db:
        db.executescript('CREATE TABLE entries(id INTEGER,text TEXT,norm TEXT,group_key TEXT,origin TEXT);'
            'CREATE TABLE terms(entry_id INTEGER,term TEXT); CREATE TABLE term_counts(term TEXT,n INTEGER);'
            'CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT);')
        db.execute('INSERT INTO entries VALUES(1,?,?,?,?)',('Audit Fixture 2024',qq.normalized('Audit Fixture 2024'),'g','audit'))
        for term in qq.terms('Audit Fixture'):
            db.execute('INSERT INTO terms VALUES(1,?)',(term,))
            db.execute('INSERT INTO term_counts VALUES(?,1)',(term,))
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
        db.commit()
    calls = []
    phase = ['initial_search']
    def ipc(action, body, timeout):
        assert action == 'account_status'
        calls.append(dict(phase=phase[0], timeout=timeout))
        if phase[0]=='initial_search' and initial_unknown:
            raise OSError('controlled initial status IPC unavailable')
        return manager.snapshot()
    class API:
        account_scope = account_a
        search_calls = 0
        resolve_calls = 0
        def search(self,*args):
            self.search_calls += 1
            return [dict(fid='123',name=title,size=2*1024**3)]
        def resolve(self,*args):
            self.resolve_calls += 1
            raise ShareError('share_revoked', http_status=403, api_code=4100010)
    api = API()
    with patch.object(runtime,'call',ipc):
        rows = qq.search(spec,time.monotonic()+5,Event(),catalogue=public,cache_path=cache_path,client=api)
        assert len(rows)==1
        source = TorrentStream(**rows[0])
        source.catalogIdentity = dict(tmdb_id='101',mode='movies',season=0,episode=0)
        context = dict(mode='movies',query='Audit Fixture',ids=dict(tmdb_id=101))
        session = Session(spec,lambda candidates:rank_sources(candidates,context))
        session.publish(session.epoch,'qqdocs',[source],'COMPLETE')
        key = session.key(source)
        session.focus(key,0)
        selected = session.capture(session.epoch,key)
        assert selected is not None
        # SourceSelect._handle_select_action calls this after locking selection.
        # No new provider is started; run the actual cancellation path to prove
        # that it stops queries without invalidating the reusable list session.
        pump = ProgressiveSearch(session, lambda manager:None, lambda rows:rows)
        pump.cancel()
        assert pump.cancelled.is_set() and session.cancelled is False
        identity = failure.card_tuple(rows[0],spec['media_key'])
        phase[0] = 'resolve'
        def resolve(body, account):
            return qq.resolve(**identity,catalogue=public,cache_path=cache_path,client=api)
        binding = Binding(dict(identity,request_id='a'*32),resolve,lambda url:True,account=manager,scope=account_a)
        try:
            binding.grant()
        except ShareError as error:
            assert error.code == 'share_revoked' and error.api_code == 4100010
            # CE2052 controller forwards the real Binding's scoped failure;
            # the original probe discarded it and passed only the code string.
            assert session.invalidate_share(session.epoch,selected,error.code,
                state=failure.failure_value(error).get('share_state'))
        else:
            raise AssertionError('Typed remote failure was not delivered')
        session.reopen()
        assert session.confirmed is None and session.cancelled is False
        before = session.snapshot()
        assert before['entries'][0][1].shareFailure == 'share_revoked'
        if transition == 'switch':
            manager.install(credentials('456'),manager.snapshot())
        else:
            manager.logout(manager.snapshot())
        phase[0] = 'after_transition'
        session.status()
        after = session.snapshot()
        with closing(sqlite3.connect(cache_path)) as db:
            old_db = failure.known_result(db,identity,account_a)
            new_db = failure.known_result(db,identity,manager.snapshot())
    code = after['entries'][0][1].shareFailure
    return dict(initial_status_unavailable=initial_unknown,transition=transition,
        initial_row_has_state=bool(rows[0].get('shareState')),
        before_failure=before['entries'][0][1].shareFailure,current_failure=code,
        recommended=after['recommended_key']==key,focus_preserved=session.focus_key==key,
        presentation=source_preference(after['entries'][0][1],context),
        card_count=len(after['entries']),old_account_database_code=old_db,
        current_account_database_code=new_db,status_calls=calls,
        after_transition_status_calls=sum(row['phase']=='after_transition' for row in calls),
        search_calls=api.search_calls,resolve_calls=api.resolve_calls,
        playback_address_granted=binding.address is not None,
        provider_queries_cancelled=pump.cancelled.is_set(),
        session_cancelled=session.cancelled,confirmed_after_reopen=session.confirmed,
        passed=not code and after['recommended_key']==key and session.focus_key==key and len(after['entries'])==1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--baseline-session',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for addon in ('script.module.bobbi.platform','script.module.bobbi.core','script.module.bobbi.catalog'):
        sys.path.insert(0,str(args.repo/'addons'/addon/'lib'))
    sys.path.insert(0,str(args.repo/'addons/plugin.video.bobbi'))
    from bobbi_platform import paths,runtime
    from bobbi_platform.account_manager import AccountManager
    from bobbi_core import share_failure as failure
    from bobbi_core.share_stream import Binding
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_catalog.api import ShareError
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.cinema_source_rank import rank_sources,source_preference
    with patch.object(paths,'profile',lambda *a,**k:Path('fixture-explicit-path-required')):
        qq=importlib.import_module('bobbi_catalog.catalog')
    path=args.repo/'addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py'
    versions=[('reviewed_source',path)]
    if args.baseline_session:
        versions.insert(0,('ce2049_session_only_control',args.baseline_session))
    result=[]
    with TemporaryDirectory(prefix='ce2051-unknown-scope-') as temporary:
        for label,source in versions:
            Session=load_class(source,'scope_probe_'+label)
            cases=[run_case(Path(temporary)/label/(str(unknown)+'-'+transition),Session,unknown,transition,
                (qq,failure,runtime,AccountManager,ShareError,Binding,TorrentStream,ProgressiveSearch,rank_sources,source_preference))
                for unknown in (False,True) for transition in ('switch','logout')]
            result.append(dict(label=label,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                passed=sum(row['passed'] for row in cases),total=len(cases),cases=cases))
    current=next(row for row in result if row['label']=='reviewed_source')
    receipt=dict(schema=1,passed=current['passed']==current['total'],results=result,
        scope=__doc__,baseline_scope='only SourceListSession is replaced by exact CE2049 bytes; other production modules are current',
        source_catalog_sha256=hashlib.sha256(Path(qq.__file__).read_bytes()).hexdigest(),
        source_failure_sha256=hashlib.sha256(Path(failure.__file__).read_bytes()).hexdigest(),
        real_device=False,real_external_network=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if receipt['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
