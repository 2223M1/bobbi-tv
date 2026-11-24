"""UI and protocol regression tests, not live-server certification."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sys
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform import runtime, server_emby, server_ui
from bobbi_platform.host import Host
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService, MAX_REQUESTS
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from bobbi_platform.server_accounts import Accounts
from test_media_servers import BASE, EmbyWire


def fixture_client(wire):
    return server_emby.Client('emby', dict(location=BASE, token='fixture-secret',
                              server_id='server1', user_id='user1'), wire)


def test_one_bad_media_source_does_not_hide_or_redirect_exact_original():
    wire = EmbyWire('emby')
    other = dict(wire.media[0], Id='unopened', RequiresOpening=True)
    wire.media = [other, wire.media[0], dict(other, Id='bad-size', Size=None, RequiresOpening=False)]
    client = fixture_client(wire)
    result = client.list_files('item:item1')
    assert result['excluded_versions'] == {'unsupported': 1, 'unverified': 1}
    assert len(result['items']) == 1
    selected = result['items'][0]
    assert 'version1' in selected['file_id']
    assert client.read_progress(selected)['entry_id'] == 'item1'
    assert client.resolve_original(selected)['original']


def test_version_id_collisions_remain_a_hard_error():
    wire = EmbyWire('emby')
    wire.media.append(dict(wire.media[0], RequiresOpening=True))
    with pytest.raises(PanError, match='PAN_REPLY_INVALID'):
        fixture_client(wire).list_files('item:item1')


def test_two_emby_connections_switch_atomically_do_not_revive_or_fall_back(tmp_path):
    from contextlib import nullcontext
    from bobbi_core.library_contract import LibraryError
    saved = Accounts(tmp_path)
    factory = lambda key, values: SimpleNamespace(session=SimpleNamespace(budget=lambda _: nullcontext()),
        verify=lambda: ('same-server', values['token'].split('-')[-1]))
    a = saved.register('emby', 'A', BASE, 'fixture-a', client_factory=factory)
    b = saved.register('emby', 'B', BASE, 'fixture-b', client_factory=factory)
    assert a['account_id'] != b['account_id']
    assert not saved.is_current(a) and saved.is_current(b)
    with pytest.raises(LibraryError):
        saved.register('emby', 'Duplicate', BASE, 'fixture-b', client_factory=factory)
    store = Registry(saved.path)
    try:
        assert len(store.sources()) == 2
        rev = store.source_snapshot(a['source_id'])[1]
        assert a['generation'] != rev
        assert Accounts(tmp_path).snapshot('emby') == b
        with pytest.raises(PanError):
            saved.activate_emby(a['source_id'], a['generation'], b)
        fresh = saved.activate_emby(a['source_id'], rev, b)
        assert fresh['account_id'] == a['account_id'] and fresh['generation'] not in (a['generation'], rev)
        assert not saved.is_current(a) and not saved.is_current(b)
        store.remove(fresh['source_id'])
        assert len(store.sources()) == 1 and not saved.snapshot('emby')['authenticated']
    finally:
        store.close()


@pytest.mark.parametrize('count,mixed', [(1000, False), (3, True)])
def test_optional_scan_preserves_good_versions_and_stays_within_wire_budget(tmp_path, count, mixed):
    class Wire(EmbyWire):
        def request(self, path, **kwargs):
            if path not in ('/Users/user1/Items',) and not path.startswith('/Users/user1/Items/movie'):
                return super().request(path, **kwargs)
            self.calls.append((path, kwargs))
            self.operation.consume_request()
            if path.endswith('/Items'):
                start, limit = (kwargs['query'][key] for key in ('StartIndex', 'Limit'))
                return dict(Items=[dict(Id='movie%d' % n, Name='Film %d' % n, IsFolder=False)
                                   for n in range(start, min(start + limit, count))], TotalRecordCount=count)
            item = path.rsplit('/', 1)[1]
            versions = [dict(Id=item, Protocol='File', Path='/movies/' + item + '.mkv', Size=1024)]
            if mixed:
                versions.append(dict(Id='unopened', Protocol='File', RequiresOpening=True))
            return dict(Id=item, Name=item, Type='Movie', MediaSources=versions)
    wire = Wire('emby')
    factory = lambda key, values: server_emby.Client(key, values, wire)
    accounts = Accounts(tmp_path)
    expected = accounts.register('emby', 'Emby', BASE, 'fixture-secret', client_factory=factory)
    pans = PanService(tmp_path, AccountManager(tmp_path / '115.json'), servers=accounts, client_factory=factory)
    store = Registry(accounts.path)
    directory = store.save_directory('Movies', expected, 'root')
    store.close()
    catalog = CatalogService(tmp_path, pans)
    try:
        task = catalog.start_scan(expected, directory['id'])['task_id']
        catalog.worker.join(120)
        assert not catalog.worker.is_alive()
        source = catalog.source_observation(expected, directory['id'])
        assert source['indexed_count'] == count
        assert source['coverage'] == ('partial' if mixed else 'complete')
        observed = [path for path, _ in wire.calls]
        assert observed.count('/Users/user1') == 1  # Verified once per operation.
        assert observed.count('/System/Info/Public') >= count  # Still checks every page.
        assert len(observed) <= MAX_REQUESTS
        job = catalog.index.jobs(expected, task=task)['items'][0]
        assert job['state'] == ('interrupted' if mixed else 'completed')
    finally:
        catalog.close()
        pans.close()


def test_tv_password_login_through_runtime_online_views_and_failed_reauth(tmp_path, monkeypatch):
    """Actual loopback transport on both sides of the unmodified Host; no real credentials."""
    requests, ids = [], []
    media = dict(Id='version1', Protocol='File', Path='/private-server/movies/film.mkv', SupportsDirectPlay=True)
    media_status = [206]
    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def handle_api(self):
            url = urlsplit(self.path)
            requests.append(url.path)
            assert url.path.startswith('/prefix/')
            path = url.path[len('/prefix'):]
            assert 'fixture' not in url.query
            status, value = 200, {}
            if path == '/Users/AuthenticateByName':
                login = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                ids.append(re.fullmatch(r'MediaBrowser Client="BobbiTV", Device="Kodi", DeviceId="([a-f0-9]{32})", Version="1"',
                                        self.headers['X-Emby-Authorization']).group(1))
                assert login['Username'] == 'member' and self.command == 'POST' and not self.headers.get('X-Emby-Token')
                if login['Pw'] == 'fixture-password':
                    value = dict(ServerId='server1', User=dict(Id='user1'), AccessToken='fixture-token')
                else:
                    status = 401
            elif path in ('/Videos/item1/stream', '/media/movie.mkv'):
                assert self.command == 'GET' and self.headers.get('Range') == 'bytes=0-0'
                assert all(not self.headers.get(h) for h in ('Cookie', 'Authorization', 'X-Emby-Token'))
                self.send_response(media_status[0])
                if media_status[0] == 302:
                    self.send_header('Location', '/prefix/must-not-follow')
                self.send_header('Content-Type', 'video/x-matroska')
                self.send_header('Content-Range', 'bytes 0-0/1024')
                self.send_header('Content-Length', '1')
                self.end_headers()
                self.wfile.write(b'x')
                return
            elif path == '/Items/item1/PlaybackInfo':
                assert self.command == 'POST' and self.headers['X-Emby-Token'] == 'fixture-token'
                args = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert args['MediaSourceId'] == 'version1' and args['EnableTranscoding'] is False
                assert args['IsPlayback'] is False and args['AutoOpenLiveStream'] is False
                value = dict(MediaSources=[media])
            else:
                assert self.headers['X-Emby-Token'] == 'fixture-token' and self.command == 'GET'
                if path == '/System/Info/Public':
                    value = dict(Id='server1')
                elif path == '/Users/user1':
                    value = dict(Id='user1')
                elif path == '/Users/user1/Items/item1':
                    value = dict(Id='item1', PartCount=1, MediaSources=[media])
                elif path in ('/Users/user1/Items', '/Users/user1/Items/Resume'):
                    query = parse_qs(url.query)
                    assert query['Limit'] == ['10'] and query['StartIndex'] == ['0']
                    if path.endswith('/Items'):
                        assert query.get('SearchTerm') == ['电影'] or query.get('SortBy') == ['DateCreated,SortName']
                    value = dict(Items=[dict(Id='item1', Name='Film', IsFolder=False)], TotalRecordCount=1)
                else:
                    status = 404
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = handle_api
    http = ThreadingHTTPServer(('127.0.0.1', 0), API)
    worker = Thread(target=http.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    worker.start()
    host = Host(tmp_path)
    store = Registry(tmp_path / 'libraries.sqlite3')
    base = 'http://127.0.0.1:%d/prefix' % http.server_port
    try:
        host.start()
        def call(action, body, **kwargs):
            return runtime.call(action, body, path=host.runtime.path, expected_token=host.runtime.server.token, **kwargs)
        monkeypatch.setattr(server_ui, 'call', call)
        monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ALPHANUM_HIDE_INPUT=1))
        choices, inputs = iter((2, 0)), iter(('Test', base, 'member', 'fixture-password'))
        dialog = SimpleNamespace(select=lambda *a, **kw: next(choices), input=lambda *a, **kw: next(inputs),
                                 yesno=lambda *a, **kw: True, ok=lambda *a, **kw: None)
        assert server_ui.add(dialog, store)
        saved, revision = store.source_snapshot(store.sources()[0].id)
        assert saved.password == 'fixture-token' and saved.metadata['user_id'] == 'user1'
        assert 'fixture-password' not in repr(list(store.db.iterdump()))
        expected = host.pans.accounts.snapshot('emby')
        for parent in ('view:recent', 'view:resume', 'view:search:电影'):
            result = call('pan_list_files', dict(expected=expected, parent=parent, page=1))
            assert result['items'][0]['file_id'] == 'item:item1'
        play = lambda: call('pan_emby_direct', dict(expected=expected, item_id='item1', media_id='version1'))
        assert play() == dict(url=base + '/Videos/item1/stream?Static=true&MediaSourceId=version1', mime='video/x-matroska')
        media.update(Protocol='Http', Path=base + '/media/movie.mkv')
        assert play() == dict(url=media['Path'], mime='video/x-matroska')
        media_status[0] = 401
        with pytest.raises(PanError, match='PAN_EMBY_DIRECT_AUTH_REQUIRED'):
            play()
        media_status[0] = 302
        with pytest.raises(PanError, match='PAN_REDIRECT_REJECTED'):
            play()
        assert '/prefix/must-not-follow' not in requests
        media_status[0] = 206
        media.update(Size=7)
        with pytest.raises(PanError, match='PAN_FILE_CHANGED'):
            play()
        media.update(Path=base + '/media/movie.mkv?api_key=never')
        with pytest.raises(PanError, match='PAN_EMBY_DIRECT_AUTH_REQUIRED'):
            play()
        assert host.pans.streams is host.catalog is None
        with pytest.raises(PanError, match='PAN_SERVER_UNAUTHORIZED'):
            call('pan_server_register', dict(provider='emby', name='Test', location=base,
                 expected_source=saved.id, username='member', password='wrong'))
        assert store.source_snapshot(saved.id) == (saved, revision)
        assert len(ids) == 2 and ids[0] == ids[1] and '/prefix/Users/Me' not in requests
        assert not (tmp_path / 'media-index.sqlite3').exists()
    finally:
        host.close()
        store.close()
        http.shutdown()
        http.server_close()
        worker.join()
