"""Offline real SQLite/pickle + loopback HTTP, never a real media server."""
from copy import deepcopy
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_core.server_ref import resumable, parts
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from bobbi_platform.server_accounts import Accounts, PlexBinding
from bobbi_platform import server_plex, server_emby, server_http
from bobbi_platform.server_progress import inspect_progress, item_progress
from test_ce2097_file_history import database, history, playback
from test_media_library_index import command


@pytest.fixture
def wire():
    state = SimpleNamespace(calls=[], writes=0, position=42000, played=False, count=1,
        size=8, before=lambda path: None, omitted=False, updated='unchanged')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def dispatch(self):
            path = urlsplit(self.path).path
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            state.calls.append((self.command, self.path, body, dict(self.headers)))
            state.before(path)
            if path == '/drop':
                state.writes += 1
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            status, headers, raw = 200, {}, None
            if path == '/http204': status, raw = 204, b''
            elif path == '/httpempty': raw = b''
            elif path == '/badjson': raw = b'not json'
            elif path == '/redirect': status, raw, headers = 302, b'', {'Location': '/http204'}
            elif path == '/http201': status, raw = 201, b'{}'
            elif path == '/api/v2/user': value = {'id': 77}
            elif path == '/api/v2/resources':
                value = [dict(clientIdentifier='server1', accessToken='fixture-secret', provides='server')]
            elif path == '/identity': value = dict(MediaContainer=dict(machineIdentifier='server1'))
            elif path == '/library/sections':
                value = dict(MediaContainer=dict(Directory=[dict(key='1', title='Movies', type='movie')]))
            elif path == '/library/sections/1/all':
                value = dict(MediaContainer=dict(librarySectionID=1, totalSize=1, offset=0,
                    Metadata=[dict(ratingKey='9', title='Same title')]))
            elif path == '/library/metadata/9':
                item = dict(ratingKey='9', type='movie', title='Same title', duration=100000,
                    updatedAt=state.updated, Media=[dict(id=str(12+i), Part=[dict(id=str(123+i),
                        key='/library/parts/%d/456/file.mkv' % (123+i), size=state.size,
                        file='/movies/Same.title.mkv')]) for i in range(state.count)])
                if not state.omitted:
                    item.update(viewOffset=state.position, viewCount=1 if state.played else 0)
                value = dict(MediaContainer=dict(Metadata=[item]))
            elif path in ('/System/Info', '/System/Info/Public'): value = {'Id': 'server1'}
            elif path in ('/Users/Me', '/Users/user1'): value = {'Id': 'user1'}
            elif path == '/Users/user1/Views':
                value = dict(Items=[dict(Id='library1', Name='Movies', IsFolder=True)], TotalRecordCount=1)
            elif path == '/Users/user1/Items':
                value = dict(Items=[dict(Id='item1', Name='Same title', IsFolder=False)], TotalRecordCount=1)
            elif path == '/Users/user1/Items/item1':
                value = dict(Id='item1', Type='Movie', PartCount=1, Name='Same title', RunTimeTicks=1000000000,
                    Etag=state.updated, MediaSources=[dict(Id='version'+str(i+1), Protocol='File',
                        Path='/movies/Same.title.mkv', Size=state.size, SupportsDirectPlay=True)
                        for i in range(state.count)])
                if not state.omitted:
                    value['UserData'] = dict(PlaybackPositionTicks=state.position*10000, Played=state.played)
            else:
                status, raw = 404, b''
            if raw is None:
                raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(raw)))
            for key, value in headers.items(): self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = dispatch
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs=dict(poll_interval=.05), daemon=True)
    thread.start()
    state.base = 'http://127.0.0.1:%d' % server.server_port
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


@pytest.fixture(params=['plex', 'jellyfin', 'emby'])
def scene(request, tmp_path, database, wire):
    provider = request.param
    settings = dict(location=wire.base, token='fixture-secret', user_token='fixture-user-secret')
    binding = PlexBinding(lambda: deepcopy(settings), lambda: True) if provider == 'plex' else None
    accounts = Accounts(tmp_path, binding)
    class LocalPlex(server_plex.Client):
        def verify(self, cloud=None):
            # Only the account origin is redirected to this fixture. All
            # protocol parsing and actual urllib transport remain production.
            return super().verify(self.session)
    factory = lambda key, saved: LocalPlex(saved) if key == 'plex' else server_emby.Client(key, saved)
    expected = accounts.register(provider, provider, client_factory=factory,
        **({} if provider == 'plex' else dict(location=wire.base, secret='fixture-secret')))
    pans = PanService(tmp_path, AccountManager(tmp_path/'115.json'), servers=accounts, client_factory=factory)
    registry = Registry(tmp_path/'libraries.sqlite3')
    directory = registry.save_directory('Movies', expected, 'root')
    registry.close()
    live = [True]
    catalog = CatalogService(tmp_path, pans, profile_current=lambda: live[0])
    storage, _ = database
    db = storage.PickleDatabase(profile_root=tmp_path/'history')
    files = history.FileHistory(db)
    def scan():
        task = catalog.start_scan(expected, directory['id'])['task_id']
        catalog.worker.join(3)
        assert not catalog.worker.is_alive()
        assert catalog.index.jobs(expected, task=task)['items'][0]['state'] == 'completed'
    try:
        scan()
        parent = 'item:9' if provider == 'plex' else 'item:item1'
        rows = pans.list_files(expected, parent, 1)['items']
        ref = from_selected(expected, rows[0], parent)
        catalog.index.apply(expected, '1'*32, [command(ref, title='Existing mapping')])
        yield SimpleNamespace(provider=provider, expected=expected, accounts=accounts, pans=pans,
            catalog=catalog, ref=ref, files=files, db=db, root=tmp_path, wire=wire, live=live, scan=scan,
            storage=storage)
    finally:
        catalog.close()
        pans.close()


def inspect(scene):
    return inspect_progress(scene.catalog, scene.files, scene.expected, scene.ref['id'])


def saved(scene, position=42, reason='STOP'):
    context = scene.files.begin(scene.ref)
    assert scene.files.save(playback(context, position=position, reason=reason))
    return context


def test_exact_mapping_units_real_sqlite_and_no_history_or_remote_write(scene):
    saved(scene)
    before = (scene.root/'history/database.pickle').read_bytes()
    index_before = list(scene.catalog.index.db.iterdump())
    scene.wire.calls.clear()
    result = inspect(scene)
    assert result['disposition'] == 'item_only'
    assert result['mapping']['title'] == 'Existing mapping' and result['mapping_provenance'] == 'manual'
    assert result['remote'] == dict(scope='item', entry_id=parts(scene.ref['file_id'])[0],
        position=42., duration=100., played=False)
    assert result['target']['media_id'] == parts(scene.ref['file_id'])[1]
    assert result['target']['part_id'] == parts(scene.ref['file_id'])[2]
    assert result['local']['position'] == 42 and result['experimental'] is True
    assert result['resume_allowed'] is result['write_allowed'] is False
    assert not resumable(scene.ref)
    assert all(call[0]=='GET' and call[2]==b'' for call in scene.wire.calls)
    assert 2 <= len(scene.wire.calls) <= 3 and 'secret' not in json.dumps(result)
    assert (scene.root/'history/database.pickle').read_bytes() == before
    assert list(scene.catalog.index.db.iterdump()) == index_before
    assert scene.catalog.index.db.execute('PRAGMA user_version').fetchone()[0] == 4


@pytest.mark.parametrize('position,played,reason', [(30,False,'STOP'), (42,True,'STOP'), (42,False,'NATURAL_EOF')])
def test_conflicts_never_choose_max_or_overwrite_local(scene, position, played, reason):
    saved(scene, reason=reason)
    scene.wire.position, scene.wire.played = position * 1000, played
    before = scene.files.get(scene.ref['id'])
    result = inspect(scene)
    assert result['disposition'] == 'conflict'
    assert result['reason'] == 'LOCAL_AND_SERVER_PROGRESS_DIFFER'
    assert scene.files.get(scene.ref['id']) == before


def test_absent_server_progress_is_unknown_and_reservation_is_not_local_observation(scene):
    scene.files.begin(scene.ref)
    scene.wire.omitted = True
    result = inspect(scene)
    assert result['disposition'] == 'unavailable' and result['local'] is None
    assert result['remote']['position'] is result['remote']['played'] is None


def test_same_id_same_size_replacement_stays_start_only_and_other_version_has_no_history(scene):
    saved(scene)
    scene.wire.updated = 'different-revision-not-a-content-hash'
    assert inspect(scene)['disposition'] == 'item_only'
    scene.wire.count = 2
    scene.scan()
    rows = scene.pans.list_files(scene.expected, scene.ref['parent'], 1, refresh=True)['items']
    other = from_selected(scene.expected, rows[1], scene.ref['parent'])
    assert other['name'] == scene.ref['name'] and other['size'] == scene.ref['size']
    result = inspect_progress(scene.catalog, scene.files, scene.expected, other['id'])
    assert result['local'] is None and result['disposition'] == 'item_only'
    assert result['file_id'] != scene.ref['id'] and result['resume_allowed'] is False


def test_actual_file_change_is_rejected_not_transferred_by_title(scene):
    saved(scene)
    scene.wire.size += 1
    with pytest.raises(PanError, match='PAN_FILE_CHANGED'):
        inspect(scene)
    assert scene.files.get(scene.ref['id'])['file_ref'] == scene.ref


def test_rescanned_replacement_keeps_old_history_as_explicit_conflict(scene):
    saved(scene)
    scene.wire.size += 1
    scene.scan()
    result = inspect(scene)
    assert result['disposition'] == 'conflict' and result['reason'] == 'LOCAL_FILE_OBSERVATION_CHANGED'
    assert result['resume_allowed'] is False
    assert scene.files.get(scene.ref['id'])['file_ref'] == scene.ref


def test_unknown_object_and_revoked_profile_do_not_start_http(scene):
    scene.wire.calls.clear()
    with pytest.raises(ValueError, match='CATALOG_SOURCE_UNAVAILABLE'):
        inspect_progress(scene.catalog, scene.files, scene.expected, 'e'*64)
    assert scene.wire.calls == []
    scene.live[0] = False
    with pytest.raises(ValueError, match='CATALOG_PROFILE_CHANGED'):
        inspect(scene)
    assert scene.wire.calls == []


@pytest.mark.parametrize('when', ['before_http', 'during_http', 'during_history_read'])
def test_failed_pending_history_is_not_presented_or_flushed(scene, monkeypatch, when):
    context = saved(scene)
    before = (scene.root/'history/database.pickle').read_bytes()
    monkeypatch.setattr(scene.storage, '_atomic_save', lambda *a: (_ for _ in ()).throw(OSError('fixture disk failure')))
    failed = []
    def fail(*args):
        if not failed:
            failed.append(scene.files.save_result(playback(context, sequence=2, position=5)))
    if when == 'before_http': fail()
    elif when == 'during_http': scene.wire.before = fail
    else:
        original = scene.files.get
        def pending_get(identifier):
            fail()
            return original(identifier)
        monkeypatch.setattr(scene.files, 'get', pending_get)
    scene.wire.calls.clear()
    with pytest.raises(OSError, match='FILE_HISTORY_PENDING'):
        inspect(scene)
    assert failed == [dict(disposition='failed', receipt=None)]
    assert scene.db.has_pending() and (scene.root/'history/database.pickle').read_bytes() == before
    if when == 'before_http': assert scene.wire.calls == []


@pytest.mark.parametrize('change', ['account', 'profile', 'mapping'])
def test_changes_during_http_fail_closed_without_local_overwrite(scene, change):
    saved(scene)
    before = (scene.root/'history/database.pickle').read_bytes()
    fired = []
    def mutate(path):
        if fired: return
        fired.append(path)
        if change == 'profile': scene.live[0] = False
        elif change == 'mapping':
            scene.catalog.index.apply(scene.expected, '2'*32, [command(scene.ref, revision=1, title='Changed')])
        else:
            registry = Registry(scene.root/'libraries.sqlite3')
            try:
                old, _ = registry.source_snapshot(scene.expected['source_id'])
                registry.save(replace(old, name='Changed'))
                registry.save(old)  # A-B-A cannot revive the original scope.
            finally:
                registry.close()
    scene.wire.before = mutate
    with pytest.raises((PanError, ValueError)):
        inspect(scene)
    assert len(fired) == 1 and (scene.root/'history/database.pickle').read_bytes() == before


@pytest.mark.parametrize('provider', ['plex','jellyfin','emby'])
def test_parser_never_promotes_etag_or_accepts_invalid_numbers(provider):
    item = dict(viewOffset=1, duration=1000, viewCount=0) if provider=='plex' else dict(
        UserData=dict(PlaybackPositionTicks=1, Played=False), RunTimeTicks=10000000)
    item.update(Etag='SECRET', DateModified='SECRET', session='SECRET', token='SECRET')
    assert 'SECRET' not in json.dumps(item_progress(provider, 'item1', item))
    if provider == 'plex': item['viewOffset'] = True
    else: item['UserData']['PlaybackPositionTicks'] = True
    with pytest.raises(PanError, match='PAN_REPLY_INVALID'):
        item_progress(provider, 'item1', item)


@pytest.mark.parametrize('method', ['POST','PUT','PATCH','DELETE'])
def test_explicit_method_and_204_have_one_local_http_attempt(wire, method):
    session = server_http.Session('jellyfin', wire.base, 'fixture-secret')
    assert session.request('/http204', method=method, data={'position': 42},
        success_statuses=(204,), empty_response=True) is None
    assert len(wire.calls) == 1 and wire.calls[0][:3] == (method, '/http204', b'{"position": 42}')
    sent = {k.lower():v for k,v in wire.calls[0][3].items()}
    assert sent['authorization'] == 'MediaBrowser Token="fixture-secret"'
    assert 'x-emby-token' not in sent


def test_empty_json_contract_defaults_redirects_and_unknown_write_are_not_retried(wire):
    session = server_http.Session('plex', wire.base, 'fixture-secret')
    assert session.request('/httpempty', method='POST', empty_response=True) is None
    assert session.request('/http201', method='PUT', success_statuses=(201,)) == {}
    for path in ('/httpempty', '/http204', '/badjson', '/redirect'):
        count = len(wire.calls)
        with pytest.raises(PanError): session.request(path)
        assert len(wire.calls) == count+1
    count = len(wire.calls)
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        session.request('/drop', method='POST', data={'position':42}, success_statuses=(204,), empty_response=True)
    assert wire.writes == 1 and len(wire.calls) == count+1
    # A lost response can follow execution. This transport has no replay or ACK
    # interpretation and no server-progress writer is enabled by these options.


@pytest.mark.parametrize('kwargs', [dict(method='GET',data={}), dict(method='TRACE'),
    dict(success_statuses=(204,)), dict(success_statuses=(True,)), dict(success_statuses=(200,200)),
    dict(success_statuses=(302,)), dict(empty_response=1)])
def test_invalid_http_contract_rejected_before_network(wire, kwargs):
    session = server_http.Session('emby',wire.base,'fixture-secret')
    with pytest.raises(PanError): session.request('/http204', **kwargs)
    assert wire.calls == []
