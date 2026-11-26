"""Kodi directory callbacks against a real HTTP Emby fixture and production Host."""
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, parse_qsl, urlsplit

import pytest

from bobbi_core.library_contract import Source
from bobbi_platform.libraries import Registry
from bobbi_platform.host import Host
from test_library_plugin import plugin


def params(url):
    return dict(parse_qsl(urlsplit(url).query))


@pytest.fixture
def online(plugin, tmp_path, monkeypatch):
    state = SimpleNamespace(calls=[], active_title='Server title', public=True, dialogs=[], prompts=[], reject_auth=False,
                            media_auth=[], pick=1,
                            existing_video_databases=set())
    data = [dict(Id=v, Name=n, Protocol='File', Path='/remote/'+v+'.mp4', SupportsDirectPlay=True,
                 Size=5) for v, n in [('one','Theatrical'), ('two','Director')]]
    def record(key='episode', **more):
        return dict(Id=key, Type='Episode', Name=state.active_title, Overview='Description from server',
                    ParentIndexNumber=2, IndexNumber=3, SeriesName='The show', **more)
    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def handle_api(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            path = url.path
            assert 'fixture-token' not in self.path
            state.calls.append((self.command, path, query))
            if path.startswith('/Videos/'):
                auth = self.headers.get('X-Emby-Token')
                state.media_auth.append(auth is not None)
                if auth is not None:
                    assert not state.public and auth == 'fixture-token'
                    if state.reject_auth:
                        self.send_error(403)
                        return
                if not state.public and not auth:
                    self.send_error(401)
                    return
                assert self.headers['Range'] == 'bytes=0-0'
                self.send_response(206)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Content-Range', 'bytes 0-0/5')
                self.send_header('Content-Length', '1')
                self.end_headers()
                self.wfile.write(b'x')
                return
            assert self.headers['X-Emby-Token'] == 'fixture-token'
            if path == '/Users/u/Views':
                rows = [dict(Id='tv', Name='TV', Type='CollectionFolder', IsFolder=True)]
                obj = dict(Items=rows, TotalRecordCount=1)
            elif path in ('/Users/u/Items','/Users/u/Items/Resume'):
                parent = query.get('ParentId', [None])[0]
                assert query['Limit'] == ['20'] and 'Overview' in query['Fields'][0]
                start = int(query['StartIndex'][0])
                if parent in ('tv','series'):
                    ident, kind = ('series','Series') if parent == 'tv' else ('season','Season')
                    rows = [dict(Id=ident, Name=kind, Type=kind, IsFolder=True)]
                    count = 1
                elif parent == 'season':
                    rows = [record('ep%d' % i) for i in range(start, min(start+20, 21))]
                    count = 21
                else:
                    rows, count = [record()], 1
                obj = dict(Items=rows, TotalRecordCount=count)
            elif path == '/System/Info/Public':
                obj = dict(Id='s')
            elif path == '/Users/u':
                obj = dict(Id='u')
            elif path == '/Users/u/Items/ep20':
                obj = record('ep20', MediaSources=data)
            elif path == '/Items/ep20/PlaybackInfo':
                chosen = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert chosen['MediaSourceId'] == 'two' and chosen['UserId'] == 'u' and not chosen['EnableTranscoding']
                obj = dict(MediaSources=[data[1]])
            else:
                self.send_error(404)
                return
            raw = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = handle_api
    server = ThreadingHTTPServer(('127.0.0.1', 0), API)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval':.05})
    worker.start()
    base = 'http://127.0.0.1:%d' % server.server_port
    store = Registry(plugin.path)
    source = Source('b'*32, 'My Emby', 'media_server', base, password='fixture-token',
                    metadata={'schema':1,'provider':'emby','server_id':'s','user_id':'u'})
    store.save(source)
    state.gen = store.source_snapshot(source.id)[1]
    store.close()
    def ask(*args, **kwargs):
        state.prompts.append((args, kwargs))
        pytest.fail('playback must not open a permission dialog')
    dialog = SimpleNamespace(select=lambda *a: state.pick, input=lambda *a:'searchword',
                             ok=lambda *a:state.dialogs.append(a), yesno=ask)
    monkeypatch.setattr(plugin.module.xbmcgui, 'Dialog', lambda:dialog)
    host = Host(tmp_path)
    host.start()
    try:
        state.src, state.base = source, base
        yield state
        assert host.catalog is None
        assert host.pans is None or host.pans.streams is None
        assert set(tmp_path.rglob('MyVideos*.db')) == state.existing_video_databases
        assert not (tmp_path/'media-index.sqlite3').exists()
    finally:
        host.close()
        server.shutdown()
        server.server_close()
        worker.join()


def test_from_root_to_episodes_pagination_refresh_search_and_direct_handoff(plugin, online):
    def visit(p):
        plugin.rows.clear()
        plugin.module.execute(17, p)
        assert plugin.ended[-1][1] == {'succeeded':True, 'cacheToDisc':False}
        assert all('fixture-token' not in target for target, _, _ in plugin.rows)
        return [(params(t), row, folder) for t, row, folder in plugin.rows]
    plugin.module.execute(17, {})
    start = next((params(t), f) for t, row, f in plugin.rows if row.label == 'My Emby')
    assert start[1] is True
    top = visit(start[0])
    assert [r.label for _, r, _ in top] == ['最近新增','服务器的继续观看','搜索 Emby','TV']
    assert len(visit(top[1][0])) == 1 and online.calls[-1][1].endswith('/Items/Resume')
    assert len(visit(top[2][0])) == 1 and online.calls[-1][2]['SearchTerm'] == ['searchword']
    rows = visit(visit(visit(top[-1][0])[0][0])[0][0])
    assert len(rows) == 21 and rows[-1][1].label == '下一页'
    p, row, folder = visit(rows[-1][0])[0]
    assert online.calls[-1][2]['StartIndex'] == ['20'] and not folder and p['id'] == 'ep20'
    assert (row.info['plot'], row.info['season'], row.info['episode']) == ('Description from server', 2, 3)
    online.active_title = 'Updated on server'
    assert visit(rows[-1][0])[0][1].label == 'Updated on server'
    plugin.module.execute(17, p)
    assert len(plugin.resolved) == 1 and plugin.resolved[0][:2] == (17, True)
    played = plugin.resolved[0][2]
    assert played.path == online.base+'/Videos/ep20/stream?Static=true&MediaSourceId=two|redirect-limit=0'
    assert played.mime == 'video/mp4' and played.lookup is False
    assert not online.dialogs and not any('Scan' in path for _, path, _ in online.calls)


def test_cancel_private_only_and_stale_connections_never_submit_alternate(plugin, online):
    p = dict(action='emby_play', source=online.src.id, revision=online.gen, id='ep20')
    online.pick = -1
    plugin.module.execute(17, p)
    assert not any(path.endswith('PlaybackInfo') for _, path, _ in online.calls)
    online.pick, online.public, online.reject_auth = 1, False, True
    plugin.module.execute(17, p)
    assert not online.prompts and online.dialogs and online.media_auth == [False, True]
    count = len(online.calls)
    store = Registry(plugin.path)
    store.remove(online.src.id)
    store.save(online.src)
    store.close()
    plugin.module.execute(17, p)
    assert len(online.calls) == count and [ok for _, ok, _ in plugin.resolved] == [False, False, False]


def test_private_playback_uses_active_account_without_a_prompt_or_auth_route(plugin, online):
    p = dict(action='emby_play', source=online.src.id, revision=online.gen, id='ep20')
    online.public = False
    plugin.module.execute(17, dict(p, authenticated='true'))
    assert not online.calls and not online.prompts and not plugin.resolved[-1][1]
    plugin.module.execute(17, p)
    assert not online.prompts
    assert [ok for _, ok, _ in plugin.resolved] == [False, True]
    path, options = plugin.resolved[-1][2].path.split('|')
    assert path == online.base+'/Videos/ep20/stream?Static=true&MediaSourceId=two'
    assert parse_qs(options) == {'redirect-limit':['0'], '!X-Emby-Token':['fixture-token']}
    assert online.media_auth == [False, True]
    plugin.module.execute(17, p)
    assert plugin.resolved[-1][1] and not online.prompts and online.media_auth == [False, True, False, True]


@pytest.mark.parametrize('replace', ['different-origin', 'other-version', 'options'])
def test_private_header_never_attached_to_unexpected_reply(plugin, online, monkeypatch, replace):
    from bobbi_platform import runtime
    original = runtime.bind_call
    def bind(path):
        call = original(path)
        def invoke(action, body, timeout):
            value = call(action, body, timeout)
            if body.get('authenticated'):
                url = value['url']
                value['url'] = {'different-origin': 'http://unrelated.invalid/film.mp4',
                                'other-version': url.replace('=two', '=one'),
                                'options': url+'|redirect-limit=4'}[replace]
            return value
        return invoke
    monkeypatch.setattr(runtime, 'bind_call', bind)
    online.public = False
    plugin.module.execute(17, dict(action='emby_play', source=online.src.id, revision=online.gen, id='ep20'))
    assert online.media_auth == [False, True] and [ok for _, ok, _ in plugin.resolved] == [False]


def test_page_read_does_not_write_registry_or_touch_existing_kodi_library(plugin, online, tmp_path, monkeypatch):
    """Observe every new SQLite connection made by the Python plugin on entry/refresh."""
    from hashlib import sha256
    kodi_video = tmp_path/'Database'/'MyVideos131.db'
    kodi_video.parent.mkdir()
    db = sqlite3.connect(kodi_video)
    db.execute('CREATE TABLE existing_movie(title TEXT)')
    db.execute("INSERT INTO existing_movie VALUES ('Keep me')")
    db.commit()
    db.close()
    online.existing_video_databases.add(kodi_video)
    initial = sha256(kodi_video.read_bytes()).digest()
    observed, signalled = [], []
    original = sqlite3.connect
    def trace(path, *a, **kw):
        observed.append(str(path))
        conn = original(path, *a, **kw)
        conn.set_trace_callback(lambda sql: signalled.append(sql.split()[0].upper()))
        return conn
    monkeypatch.setattr(sqlite3, 'connect', trace)
    p = dict(action='emby_page', source=online.src.id, revision=online.gen, parent='recent')
    for _ in range(2):
        plugin.module.execute(17, p)
        assert plugin.ended[-1][1] == dict(succeeded=True, cacheToDisc=False)
    assert observed and all('libraries.sqlite3' in path for path in observed)
    assert not {'INSERT','UPDATE','DELETE','CREATE','ATTACH','REPLACE','DROP'}.intersection(signalled)
    assert sha256(kodi_video.read_bytes()).digest() == initial


def test_account_rotated_while_fetching_never_publishes_old_directory(plugin, online, monkeypatch):
    from bobbi_platform.server_emby import Client
    old = Client.page_rows
    def switch(*args, **kw):
        page = old(*args, **kw)
        store = Registry(plugin.path)
        try:
            store.remove(online.src.id)
            store.save(online.src)
        finally:
            store.close()
        return page
    monkeypatch.setattr(Client, 'page_rows', switch)
    plugin.module.execute(17, dict(action='emby_page', source=online.src.id, revision=online.gen, parent='recent'))
    assert len(plugin.ended) == 1 and not plugin.ended[0][1]['succeeded']
    assert not plugin.rows and not plugin.resolved


def test_browse_account_switch_preserves_same_credential_epoch_routes_until_rotated(plugin, online):
    """Infuse / EmbyCon / Juku continuity: switching default browse account (A <-> B)
    never invalidates already-rendered Home shelf / folder / play URLs of unchanged A,
    while credential rotation or source removal immediately revokes them.
    """
    old_rev_a = online.gen
    store = Registry(plugin.path)
    try:
        src_b = Source(
            'c' * 32, 'Second Emby', 'media_server', online.base, password='fixture-token-b',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's', 'user_id': 'u2'},
        )
        store.save(src_b, activate_emby=store.emby_binding()[1])
        store.save(online.src, activate_emby=store.emby_binding()[1])
        _, latest_rev_a = store.source_snapshot(online.src.id)
        assert latest_rev_a != old_rev_a
    finally:
        store.close()

    # Pre-switch folder & play links for A remain valid because A's credential epoch is unbroken!
    plugin.rows.clear()
    plugin.ended.clear()
    plugin.module.execute(17, dict(action='emby_page', source=online.src.id, revision=old_rev_a, parent='recent'))
    assert plugin.ended[-1][1] == dict(succeeded=True, cacheToDisc=False)
    # Outgoing child routes carry the latest revision
    child_params = params(plugin.rows[0][0])
    assert child_params['revision'] == latest_rev_a

    plugin.resolved.clear()
    plugin.module.execute(17, dict(action='emby_play', source=online.src.id, revision=old_rev_a, id='ep20'))
    assert len(plugin.resolved) == 1 and plugin.resolved[-1][:2] == (17, True)

    # Rotating A's token immediately invalidates both old_rev_a and latest_rev_a!
    store = Registry(plugin.path)
    try:
        rotated_a = Source(
            online.src.id, online.src.name, online.src.kind, online.src.location,
            password='rotated-token-value', metadata=dict(online.src.metadata),
        )
        store.save(rotated_a)
    finally:
        store.close()

    plugin.resolved.clear()
    online.dialogs.clear()
    plugin.module.execute(17, dict(action='emby_play', source=online.src.id, revision=old_rev_a, id='ep20'))
    assert [ok for _, ok, _ in plugin.resolved] == [False]
    assert online.dialogs
