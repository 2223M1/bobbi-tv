#!/usr/bin/env python3
"""Portable in-flight query contract derived from the frozen CE2049 repro.

--expect current-bug: exit 0 means the known defect was reproduced on CE2049.
--expect fixed: permits a new revision; exit 0 means old-scope failure is no
longer presented by the current session (or that session was revoked), and
new queries retain correct isolation. This mode intentionally fails on CE2049.

Production AccountManager, Host dispatch/account-change callback, SQLite,
catalogue search/resolve, ProgressiveSearch, OS admission lease, TorrentStream,
ranking and SourceListSession are used. Only remote APIs and runtime transport
are substituted. This exercises a query already in progress, not a new query
started after the account changed, and it does not run the Kodi renderer.
"""
import argparse
from contextlib import closing
import importlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit


HEAD = "43e3a296f5982a6b235421cbffb61c3eae65a84e"
SPEC = dict(tmdb_id=101, mode="movies", year=2024, aliases=["Audit Fixture"], media_key="movies:101:0:0")
TITLE = "Audit Fixture.2024.1080p.WEB-DL.x264.mkv"
SIZE = 1024**3


def credential(user):
    return dict(app="os_linux", cookies=dict(UID=user+"_fixture", CID="fixture-cid", SEID="fixture-seid"))


def run_case(root, provider, modules):
    qq, juku, failure, runtime, Host, AccountManager, ShareError, Client, ProgressiveSearch, SourceListSession, TorrentStream, rank_sources, try_acquire = modules
    root.mkdir()
    account = AccountManager(root / "account.json")
    scope_a = account.install(credential("123"), account.snapshot())
    host = Host(root / "host")
    host.runtime.close()  # No HTTP listener is started.
    host.accounts = account
    unsubscribe = account.subscribe(host._account_changed)
    public, cachedb, state = root/"public.sqlite", root/"qq-cache.sqlite", root/"juku"
    with closing(sqlite3.connect(str(public))) as db:
        db.executescript("""
            CREATE TABLE entries(id INTEGER,text TEXT,norm TEXT,group_key TEXT,origin TEXT);
            CREATE TABLE terms(entry_id INTEGER,term TEXT);
            CREATE TABLE term_counts(term TEXT,n INTEGER);
            CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT);
        """)
        db.execute("INSERT INTO entries VALUES(1,?,?,?,?)", ("Audit Fixture 2024",qq.normalized("Audit Fixture 2024"),"g","audit"))
        for term in qq.terms("Audit Fixture"):
            db.execute("INSERT INTO terms VALUES(1,?)", (term,))
            db.execute("INSERT INTO term_counts VALUES(?,1)", (term,))
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
        db.commit()
    row = juku._bound(juku._row(dict(tmdbId=101,typeId=1,year=2024,title="Audit Fixture",id=1,vodId=1),
        dict(url="https://115.com/s/sfixture",fileId="123",fileName=TITLE,fileSize=SIZE,parentFolderId="8"),
        "shared:fixture"), juku._spec(SPEC))
    with closing(juku.Cache(state)) as cache:
        cache.replace_library("fixture",1,[row])
        cache.remember([row],juku._spec(SPEC))
    transition = {"enabled": False, "done": False}
    events = []
    final_catalogue_rows = []
    context = dict(mode="movies", query="Audit Fixture", ids=dict(tmdb_id=101))
    session = SourceListSession(SPEC, lambda rows:rank_sources(rows, context))
    pump_holder = []

    def switch_in_remote_io():
        if transition["enabled"] and not transition["done"]:
            before = session.snapshot()
            scope_b = account.install(credential("456"), account.snapshot())
            transition.update(done=True, current_epoch=scope_b["epoch"])
            events.append(dict(stage="switch_during_remote_io", old_epoch=scope_a["epoch"],
                current_epoch=scope_b["epoch"], host_account_change_seen=host.account_changes.is_set(),
                provider_cancelled=pump_holder[0].cancelled.is_set(), session_cancelled=session.cancelled,
                already_published_failures=[s.shareFailure for _,s in before["entries"]]))

    class API:
        account_scope = scope_a
        def search(self,*args):
            switch_in_remote_io()
            return [dict(fid="123",name=TITLE,size=SIZE)]
        def get(self,*args):
            switch_in_remote_io()
            return dict(items=[],pagination=dict(total=0))
        def resolve(self,*args):
            raise ShareError("share_revoked",api_code=4100010)
    class Response(io.BytesIO):
        def __init__(self, value):
            raw=json.dumps(value).encode()
            super().__init__(raw)
            self.headers={"Content-Length":str(len(raw))}
    class Opener:
        def open(self, request, timeout):
            path=urlsplit(request.full_url).path
            if path=="/share/search":
                switch_in_remote_io()
                return Response(dict(state=True,data=dict(list=[dict(fid="123",n=TITLE,s=SIZE)])))
            assert path=="/os_linux/2.0/share/downurl", path
            return Response(dict(state=False,errno=4100010))
    api = (Client(session=dict(credential("123"),user_agent="offline-audit"),opener=Opener())
           if provider=="qqdocs" else API())
    resolve_api = (Client(session=dict(credential("123"),user_agent="offline-audit"),
                          account_scope=scope_a,opener=Opener()) if provider=="qqdocs" else api)

    def query(deadline, cancelled, publish=None):
        if provider == "qqdocs":
            return qq.search(SPEC,deadline,cancelled,catalogue=public,cache_path=cachedb,client=api)
        result = juku.search(SPEC,deadline,cancelled,state=state,client=api,publish=publish)
        return result

    def fields(row):
        return juku.fields(row) if provider=="juku" else row

    def convert(rows):
        result=[]
        for row in rows:
            source=TorrentStream(**fields(row))
            source.catalogIdentity=dict(tmdb_id="101",mode="movies",season=0,episode=0)
            if provider=="juku": source.verifiedShareFile=juku.verified(row)
            result.append(source)
        return result

    ipc = lambda action,body,timeout:host.dispatch(action,body)
    try:
        with patch.object(runtime,"call",ipc):
            initial = query(time.monotonic()+5,Event())
            card = fields(initial[0])
            identity = failure.card_tuple(card,SPEC["media_key"])
            args=[identity[k] for k in failure.TUPLE_FIELDS]
            try:
                if provider=="qqdocs": qq.resolve(*args,catalogue=public,cache_path=cachedb,client=resolve_api)
                else: juku.resolve(*args,state=state,client=api)
            except ShareError as error:
                assert error.code=="share_revoked"
            else:
                raise AssertionError("Controlled permanent failure not delivered")
            before_switch_query_failure=fields(query(time.monotonic()+5,Event())[0]).get("shareFailure","")
            assert before_switch_query_failure=="share_revoked"
            if provider=="qqdocs":
                with closing(sqlite3.connect(str(cachedb))) as db:
                    db.execute("UPDATE searches SET expires=0")
                    db.commit()
            else:
                with closing(juku.Cache(state)) as cache:
                    cache.db.execute("DELETE FROM raw_cache")
                    cache.db.commit()
            transition["enabled"]=True
            def task(deadline,cancelled,publish=None):
                rows=query(deadline,cancelled,publish)
                final_catalogue_rows.extend([fields(r) for r in rows])
                return rows
            def setup(manager):
                manager.submit_task(provider,provider,task,manager.deadline,manager.cancelled,
                                    _progressive=provider=="juku")
            pump=ProgressiveSearch(session,setup,convert,workers=1,budget=5,
                                   admission=lambda:try_acquire(root/"admission"))
            pump_holder.append(pump)
            pump.start()
            pump.thread.join(6)
            assert not pump.thread.is_alive(), "Coordinator did not settle"
            if pump.pool is not None: pump.pool.shutdown(wait=True)
            assert transition["done"], "Required in-flight transition did not execute"
            snapshot=session.snapshot()
            visible=[s for _,s in snapshot["entries"]]
            current_scope=account.snapshot()
            new_query=[fields(r) for r in query(time.monotonic()+5,Event())]
            assert len(new_query)==1, "Control query after the switch must retain the matching candidate"
            return dict(provider=provider,events=events,
                current_epoch=current_scope["epoch"],
                before_switch_query_failure=before_switch_query_failure,
                finished_catalogue_failure=final_catalogue_rows[0].get("shareFailure","") if final_catalogue_rows else None,
                existing_session_failure=visible[0].shareFailure if visible else None,
                existing_session_failure_count=sum(bool(s.shareFailure) for s in visible),
                existing_session_cancelled=snapshot["cancelled"],
                existing_session_visible_count=len(visible),
                existing_session_recommended=bool(snapshot["recommended_key"]),
                existing_session_caution=bool(__import__("lib.utils.general.cinema_source_rank",fromlist=["source_preference"]).source_preference(visible[0],context)["caution"]) if visible else None,
                provider_final_states={k:v["state"] for k,v in snapshot["providers"].items()},
                fresh_query_after_switch_failure=new_query[0].get("shareFailure",""),
                playback_was_started=False,
                effect="stale failure presentation/recommendation only; playback authorization bypass not demonstrated")
    finally:
        unsubscribe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--expect",required=True,choices=("current-bug","fixed"))
    args=parser.parse_args()
    repo=args.repo.resolve()
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    if args.expect=="current-bug" and sha != HEAD:
        raise SystemExit("current-bug mode requires the frozen CE2049 source; use --expect fixed for a changed revision: "+sha)
    for addon in ("script.module.bobbi.platform","script.module.bobbi.core","script.module.bobbi.catalog"):
        sys.path.insert(0,str(repo/"addons"/addon/"lib"))
    sys.path.insert(0,str(repo/"addons/plugin.video.bobbi"))
    from bobbi_platform import paths,runtime
    from bobbi_platform.host import Host
    from bobbi_platform.account_manager import AccountManager
    from bobbi_core import juku_catalog as juku,share_failure as failure
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_core.source_list_session import SourceListSession
    from bobbi_core.search_admission import try_acquire
    from bobbi_catalog.api import ShareError,Client
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.cinema_source_rank import rank_sources
    with TemporaryDirectory(prefix="ce2049-epoch-") as directory:
        root=Path(directory)
        with patch.object(paths,"profile",lambda addon="platform",name="":root/addon/name):
            qq=importlib.import_module("bobbi_catalog.catalog")
        modules=(qq,juku,failure,runtime,Host,AccountManager,ShareError,Client,ProgressiveSearch,SourceListSession,TorrentStream,rank_sources,try_acquire)
        results=[run_case(root/provider,provider,modules) for provider in ("qqdocs","juku")]
    violations=[]
    for row in results:
        label=row["provider"]
        if row["before_switch_query_failure"]!="share_revoked":
            violations.append(label+": failure-before-switch control did not execute")
        if row["fresh_query_after_switch_failure"]:
            violations.append(label+": new account/new query inherited the old failure")
        if args.expect=="current-bug":
            if row["existing_session_failure"]!="share_revoked" or row["existing_session_recommended"]:
                violations.append(label+": expected stale current-session failure was not reproduced")
        else:
            if not row["existing_session_cancelled"] and row["existing_session_failure_count"]:
                violations.append(label+": live session still presents an old-account failure")
            if not row["existing_session_cancelled"] and row["existing_session_visible_count"] != 1:
                violations.append(label+": a live completed query must retain its matching candidate")
            if not row["existing_session_cancelled"] and row["existing_session_visible_count"] and not row["existing_session_recommended"]:
                violations.append(label+": refreshed eligible candidate is still excluded from recommendation")
    result=dict(source_sha=sha,expect=args.expect,contract_passed=not violations,violations=violations,
        zero_exit_means="known defect reproduced" if args.expect=="current-bug" else "fixed contract satisfied",
        new_device_execution=False,real_external_network=False,
        scope="real AccountManager, Host dispatch/callback, catalogue, SQLite, ProgressiveSearch, OS lease, ranking and UI session; QQdocs uses real Client.get/search/resolve with only opener-response double; Juku public metadata API and IPC transport doubles; no Kodi renderer",
        observations=results)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    args.output.write_text(raw,encoding="utf-8")
    print(raw,end="")
    raise SystemExit(1 if violations else 0)


if __name__=="__main__": main()
