#!/usr/bin/env python3
"""CE2051: clear A overlay -> B manual retry fails -> switch/logout again.

Real AccountManager, Host callback/dispatch, QQdocs Client search/resolve,
SQLite, Binding, TorrentStream, ranking, SourceListSession, and the unmodified
SourceSelect.doModal method execute. GUI/native transport and remote HTTP
responses are doubles. No real account, device, or external request is used.
--expect current-bug returns zero only when the documented residual reproduces.
--expect fixed returns zero only when old-account annotations clear while the
candidate, adjacent BT card, focus, and current-account failure are retained.
"""
import argparse
import ast
from contextlib import closing
import hashlib
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
from types import SimpleNamespace, ModuleType
from unittest.mock import patch
from urllib.parse import urlsplit


SPEC = dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Fixture'], media_key='movies:101:0:0')
TITLE = 'Audit Fixture.2024.1080p.WEB-DL.x264.mkv'
SIZE = 1024 ** 3


def credential(user):
    return dict(app='os_linux', cookies=dict(UID=user+'_fixture', CID='fixture-cid', SEID='fixture-seid'))


def run_case(repo, root, transition, modules):
    qq, failure, runtime, Host, AccountManager, ShareError, Client, Binding, SourceListSession, TorrentStream, rank_sources = modules
    root.mkdir()
    manager = AccountManager(root/'account.json')
    scope_a = manager.install(credential('123'), manager.snapshot())
    host = Host(root/'host')
    host.runtime.close()
    host.accounts = manager
    unsubscribe = manager.subscribe(host._account_changed)
    public, cachedb = root/'public.sqlite', root/'cache.sqlite'
    with closing(sqlite3.connect(public)) as db:
        db.executescript('CREATE TABLE entries(id INTEGER,text TEXT,norm TEXT,group_key TEXT,origin TEXT);'
                        'CREATE TABLE terms(entry_id INTEGER,term TEXT);'
                        'CREATE TABLE term_counts(term TEXT,n INTEGER);'
                        'CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT);')
        db.execute('INSERT INTO entries VALUES(1,?,?,?,?)', ('Audit Fixture 2024', qq.normalized('Audit Fixture 2024'), 'g', 'audit'))
        for term in qq.terms('Audit Fixture'):
            db.execute('INSERT INTO terms VALUES(1,?)', (term,))
            db.execute('INSERT INTO term_counts VALUES(?,1)', (term,))
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
        db.commit()
    calls = []
    class Response(io.BytesIO):
        def __init__(self, value):
            raw = json.dumps(value).encode()
            super().__init__(raw)
            self.headers = {'Content-Length': str(len(raw))}
    class Opener:
        def open(self, request, timeout):
            path = urlsplit(request.full_url).path
            calls.append(dict(path=path, account_epoch=manager.snapshot()['epoch']))
            if path == '/share/search':
                return Response(dict(state=True, data=dict(list=[dict(fid='123', n=TITLE, s=SIZE)])))
            assert path == '/os_linux/2.0/share/downurl', path
            return Response(dict(state=False, errno=4100010))
    def client(scope):
        return Client(session=dict(manager.credentials(scope), user_agent='offline-audit'), account_scope=scope, opener=Opener())
    def query():
        rows = qq.search(SPEC, time.monotonic()+5, Event(), catalogue=public, cache_path=cachedb,
                         client=client(manager.snapshot()))
        assert len(rows) == 1
        source = TorrentStream(**rows[0])
        source.catalogIdentity = dict(tmdb_id='101', mode='movies', season=0, episode=0)
        return source
    def grant(source, request):
        scope = manager.snapshot()
        body = dict(locator=source.url, guid=source.guid, title=source.title, size=source.size,
                    media=SPEC['media_key'], request_id=request)
        def resolve(payload, expected):
            assert manager.is_current(expected)
            return qq.resolve(*(payload[key] for key in failure.TUPLE_FIELDS), catalogue=public,
                              cache_path=cachedb, client=client(expected))
        binding = Binding(body, resolve, lambda url:True, account=manager, scope=scope)
        try:
            binding.grant()
        except ShareError as error:
            assert error.code == 'share_revoked'
        else:
            raise AssertionError('Controlled remote revocation must be delivered')
        result = binding.grant_outcome()
        assert result['state'] == 'failed' and result['failure']['code'] == 'share_revoked'
        assert binding.address is None
        return result['failure']
    try:
        with patch.object(runtime, 'call', lambda action, body, timeout:host.dispatch(action, body)):
            grant(query(), 'a'*32)
            source = query()
            context = dict(mode='movies', query='Audit Fixture', ids=dict(tmdb_id=101))
            session = SourceListSession(SPEC, lambda rows:rank_sources(rows, context))
            session.publish(session.epoch, '115', [source])
            bt = TorrentStream(title=TITLE, type='Torrent', indexer='fixture-bt', infoHash='b'*40)
            session.publish(session.epoch, 'BT', [bt])
            key, bt_key = session.key(source), session.key(bt)
            session.focus(key, 0)
            def state():
                snapshot = session.snapshot(full=True)
                row = next(value for candidate, value in snapshot['entries'] if candidate == key)
                return dict(failure=row.shareFailure, share_state_present=bool(row.shareState),
                            state_epoch=row.shareState.get('epoch'), session_scope_epoch=session.share_scope[0],
                            recommended=snapshot['recommended_key']==key,
                            count=len(snapshot['entries']), keys=sorted(candidate for candidate, _ in snapshot['entries']),
                            focus_unchanged=session.focus_key==key, cancelled=snapshot['cancelled'])
            before = state()
            scope_b = manager.install(credential('456'), manager.snapshot())
            session.status()
            first_clear = state()
            assert first_clear['failure'] == '' and first_clear['recommended']
            # Execute the production GUI controller method; only its widget,
            # resolver window shell, and native snapshot transport are replaced.
            gui_path = repo/'addons/plugin.video.bobbi/lib/gui/source_select.py'
            tree = ast.parse(gui_path.read_text(encoding='utf-8'))
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name=='SourceSelect')
            method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name=='doModal')
            records = {}
            class ResolverWindow:
                def __init__(self, *args, source, **kwargs):
                    self.source = source
                    self.error_message = 'fixture revoked'
                    self.user_cancelled = False
                    self.startup_failure_category = ''
                    self.playback_info = None
                    self.resolution_answered = False
                def doModal(self, *args):
                    self.share_failure = grant(self.source, 'c'*32)
                    records['binding_failure'] = self.share_failure
                    return False
            namespace = dict(ResolverWindow=ResolverWindow, ADDON_PATH='fixture',
                             get_property=lambda name:'c'*32, notification=lambda *a, **k:None)
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(gui_path), 'exec'), namespace)
            native = ModuleType('lib.native_support'); native.available = lambda:True
            snapshot_module = ModuleType('lib.cinema.playback_request'); snapshot_module.read_snapshot = lambda:{}
            obj = SimpleNamespace(source_session=session, source_pump=None, item_information={'request_id':'c'*32},
                                  _resolution_answered=False, position=0, resolved=False,
                                  setProperty=lambda *args:None)
            passes = []
            def window():
                if not passes:
                    passes.append(1)
                    captured = session.capture(session.epoch, key)
                    assert captured is not None
                    obj._pending_selection = (captured, {})
                    return
                records['after_retry_before_transition'] = state()
                assert not session.confirmed, 'The real doModal method must reopen after failure'
                time.sleep(1.05)  # Observe the actual 1-second throttle; no clock/session mutation.
                session.status()
                records['same_account_poll'] = state()
                if transition == 'switch':
                    manager.install(credential('789'), scope_b)
                else:
                    manager.logout(scope_b)
                time.sleep(1.05)
                session.status()
                records['after_second_transition'] = state()
                obj._pending_selection = None
            obj._run_progressive_window = window
            with patch.dict(sys.modules, {'lib.native_support':native, 'lib.cinema.playback_request':snapshot_module}):
                result = namespace['doModal'](obj)
            fresh = query() if manager.snapshot()['authenticated'] else None
            final = records['after_second_transition']
            expected_keys = sorted([key, bt_key])
            return dict(transition=transition, source_select_doModal_executed=True, doModal_result=result,
                        old_epoch=scope_a['epoch'], intermediate_epoch=scope_b['epoch'], current_epoch=manager.snapshot()['epoch'],
                        host_account_callback_seen=host.account_changes.is_set(), before=before, first_clear=first_clear,
                        **records, fresh_query_failure=fresh.shareFailure if fresh else None,
                        fresh_query_applicable=fresh is not None,
                        candidates_and_focus_retained=final['keys']==expected_keys and final['focus_unchanged'],
                        remote_calls=calls, new_device_execution=False, external_network=False,
                        failure_scope='presentation and recommendation only; no playback grant issued')
    finally:
        unsubscribe()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect', choices=['current-bug', 'fixed'], required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    for addon in ('script.module.bobbi.platform','script.module.bobbi.core','script.module.bobbi.catalog'):
        sys.path.insert(0, str(repo/'addons'/addon/'lib'))
    sys.path.insert(0, str(repo/'addons/plugin.video.bobbi'))
    from bobbi_platform import paths, runtime
    from bobbi_platform.account_manager import AccountManager
    from bobbi_platform.host import Host
    from bobbi_catalog.api import ShareError, Client
    from bobbi_core import share_failure as failure
    from bobbi_core.share_stream import Binding
    from bobbi_core.source_list_session import SourceListSession
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.cinema_source_rank import rank_sources
    with TemporaryDirectory(prefix='ce2051-retry-scope-') as directory:
        root = Path(directory)
        with patch.object(paths, 'profile', lambda addon='platform',name='':root/addon/name):
            qq = importlib.import_module('bobbi_catalog.catalog')
        modules = (qq,failure,runtime,Host,AccountManager,ShareError,Client,Binding,SourceListSession,TorrentStream,rank_sources)
        cases = [run_case(repo, root/kind, kind, modules) for kind in ('switch','logout')]
    violations = []
    for row in cases:
        end = row['after_second_transition']
        if row['same_account_poll']['failure'] != 'share_revoked':
            violations.append(row['transition']+': current-account failure was erased')
        if row['fresh_query_failure'] or not row['candidates_and_focus_retained']:
            violations.append(row['transition']+': candidate/focus/isolation control failed')
        observed = (end['failure']=='share_revoked' and not end['recommended']
                    and end['session_scope_epoch']==row['current_epoch'])
        fixed = not end['failure'] and end['recommended'] and not end['cancelled']
        if not (observed if args.expect=='current-bug' else fixed):
            violations.append(row['transition']+': expected '+args.expect+' contract not satisfied')
    paths = ['addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py',
             'addons/plugin.video.bobbi/lib/gui/source_select.py']
    receipt = dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
                   source_sha256={path:hashlib.sha256((repo/path).read_bytes()).hexdigest() for path in paths},
                   expect=args.expect, contract_passed=not violations, violations=violations,
                   zero_exit_means='defect reproduced' if args.expect=='current-bug' else 'fixed contract satisfied',
                   scope=__doc__, cases=cases)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    raise SystemExit(1 if violations else 0)


if __name__ == '__main__':
    main()
