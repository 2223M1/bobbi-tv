"""A real Kodi-side image listener talking to an authenticated synthetic Emby server."""
from contextlib import closing, contextmanager, ExitStack
import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import struct
import socket
from threading import Thread
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import urlopen
import zlib

import pytest

from bobbi_core.image_cache import ImageService
from bobbi_core.library_contract import Source
from bobbi_platform.emby_artwork import reader, poster_factory, thumbnail_type
from bobbi_platform.libraries import Registry
from bobbi_platform.runtime import Runtime


def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))


PNG = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>II5B',1,1,8,2,0,0,0))
       +chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b''))


@contextmanager
def remote():
    calls, mode = [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self):
            calls.append((self.path, self.headers.get('X-Emby-Token')))
            if '/Users/u1/Items/movie' in self.path:
                body = json.dumps({'Id':'movie','ImageTags':{'Primary':'tag1'}}).encode()
                kind = 'application/json'
            elif '/Items/movie/Images/Primary?' in self.path:
                body, kind = PNG, 'image/png'
                if mode == ['corrupt']:
                    body = body[:-13] + b'fake' + body[-10:]
                if mode == ['html']:
                    kind = 'text/html'
                if mode == ['redirect']:
                    self.send_response(302)
                    self.send_header('Location','/credential-trap')
                    self.end_headers()
                    return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%s/libraries/emby' % server.server_port, calls, mode
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_selected_profile_tag_signature_no_store_and_revoke(tmp_path):
    runtime = Runtime(lambda *_:None, tmp_path / 'runtime.json')
    runtime.start()
    images = ImageService(tmp_path, private_art=reader(tmp_path, lambda:True))
    try:
        images.start()
        with remote() as (base, calls, mode), closing(Registry(tmp_path / 'libraries.sqlite3')) as registry:
            source = Source('a'*32,'Server','media_server',base,password='test-auth-secret',metadata={
                'schema':1,'provider':'emby','server_id':'server1','user_id':'u1'})
            registry.save(source)
            _, generation = registry.source_snapshot(source.id)
            make = poster_factory(tmp_path, source.id, generation, registry)
            assert make('movie', '') == make('../movie','tag1') == ''
            url = make('movie','tag1')
            assert url and runtime.server.token not in url and images.server.token not in url and 'test-auth-secret' not in url
            assert not calls  # Rendering cards is a local projection; no speculative request.
            with urlopen(url, timeout=4) as reply:
                assert reply.read() == PNG and 'no-store' in reply.headers['Cache-Control']
            assert len(calls) == 2 and all(h == 'test-auth-secret' and 'secret' not in path for path,h in calls)
            assert not list((tmp_path/'images').rglob('*'))
            for changed in (url.replace('tag1', 'tag2'), url.replace('/movie/','/other/')):
                with pytest.raises(HTTPError):
                    urlopen(changed,timeout=4)
            # The public TMDb token is deliberately visible to Kodi, but grants
            # no capability to forge Emby paths, even with the tag and item ID.
            path = url.split(str(images.server.server_port),1)[1].rsplit('/',1)[0]
            wrong = hmac.digest(bytes.fromhex(images.server.token), b'bobbi/emby-primary/v1', 'sha256')
            forged = url.rsplit('/',1)[0]+'/'+hmac.digest(wrong,path.encode(),'sha256').hex()
            with pytest.raises(HTTPError):
                urlopen(forged,timeout=4)
            assert len(calls) == 2
            for failure in ('html', 'corrupt', 'redirect'):
                mode[:] = [failure]
                with pytest.raises(HTTPError):
                    urlopen(url, timeout=4)
            assert all('credential-trap' not in path for path,_ in calls)
            before = len(calls)
            registry.remove(source.id)
            registry.save(source)
            with pytest.raises(HTTPError):
                urlopen(url, timeout=4)
            assert len(calls) == before
    finally:
        images.close()
        runtime.close()


def test_revoke_during_fetch_drops_bytes(tmp_path):
    live = [True]
    registry = Registry(tmp_path / 'libraries.sqlite3')
    source = Source('b'*32,'Server','media_server','https://server.test',password='test-only',
                    metadata={'schema':1,'provider':'emby','server_id':'s1','user_id':'u1'})
    registry.save(source)
    _, generation = registry.source_snapshot(source.id)
    runtime = Runtime(lambda *_:None, tmp_path/'runtime.json')
    runtime.start()
    def fetch(*args):
        live[0] = False
        return PNG, 'image/png'
    service = ImageService(tmp_path, private_art=reader(tmp_path,lambda:live[0],fetch))
    try:
        service.start()
        url = poster_factory(tmp_path,source.id,generation,registry)('movie','tag1')
        with pytest.raises(HTTPError):
            urlopen(url,timeout=4)
    finally:
        service.close()
        runtime.close()
        registry.close()


def test_poster_survives_host_restart_and_moves_only_on_port_conflict(tmp_path):
    from bobbi_platform.host import Host
    with remote() as (base, calls, _), closing(Registry(tmp_path/'libraries.sqlite3')) as store:
        source = Source('a'*32,'Server','media_server',base,password='test-auth-secret',metadata={
            'schema':1,'provider':'emby','server_id':'server1','user_id':'u1'})
        store.save(source)
        _, rev = store.source_snapshot(source.id)
        def cycle():
            host = Host(tmp_path)
            host.start()
            try:
                stamp = store.db.total_changes
                factory = poster_factory(tmp_path, source.id, rev, store)
                assert not factory('movie','') and store.db.total_changes == stamp
                art = factory('movie','tag1')
                after = store.db.total_changes
                for _ in range(5):
                    assert factory('movie','tag1') == art
                assert store.db.total_changes == after
                with urlopen(art, timeout=3) as reply:
                    assert reply.read() == PNG
                return urlsplit(art), host.runtime.server.token, after - stamp
            finally:
                host.close()
        first, token1, writes = cycle()
        second, token2, again = cycle()
        assert first == second and token1 != token2 and (writes,again) == (1,0)
        with socket.socket() as occupied:
            if os.name == 'posix':
                # Match the real listener's restart semantics: stale HTTP
                # TIME_WAIT sockets may be reused, a live listener may not.
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(('127.0.0.1', second.port))
            occupied.listen(1)
            moved, _, writes = cycle()
            assert moved.hostname == '127.0.0.1' and moved.port != second.port
            assert moved.path == first.path and writes == 0
        persisted, _, _ = cycle()
        assert persisted == moved


def test_private_keys_are_profile_bound_and_switching_back_does_not_revive_art(tmp_path):
    with remote() as (base, calls, _), ExitStack() as cleanup:
        handles = []
        source = Source('a'*32,'A','media_server',base,password='test-auth-secret',metadata={
            'schema':1,'provider':'emby','server_id':'server1','user_id':'u1'})
        for name in ('first','second'):
            root = tmp_path/name
            store = cleanup.enter_context(closing(Registry(root/'libraries.sqlite3')))
            store.save(source)
            # Deliberate public-scope collision; isolation must come from private state.
            with store.db:
                store.db.execute('UPDATE metadata SET value=? WHERE key=?', ('f'*64, 'source_revision:'+source.id))
            service = ImageService(root, private_art=reader(root,lambda:True))
            service.start()
            cleanup.callback(service.close)
            art = poster_factory(root,source.id,'f'*64,store)('movie','tag1')
            handles.append((root,store,urlsplit(art)))
        (_,_,left),(root,store,right) = handles
        assert left.path != right.path
        with pytest.raises(HTTPError):
            urlopen(left._replace(netloc=right.netloc).geturl(),timeout=3)
        assert calls == []
        with urlopen(right.geturl(),timeout=3) as reply:
            assert reply.read() == PNG
        before = len(calls)
        other = Source('b'*32,'B','media_server',base,password='different',metadata={
            'schema':1,'provider':'emby','server_id':'server1','user_id':'u2'})
        for selected in (other, source):
            store.save(selected, activate_emby=store.emby_binding()[1])
            with pytest.raises(HTTPError):
                urlopen(right.geturl(),timeout=3)
        assert len(calls) == before
        _,rev = store.source_snapshot(source.id)
        assert rev != 'f'*64 and poster_factory(root,source.id,rev,store)('movie','tag1') != right.geturl()


def test_thumbnail_envelope_and_matching_mime():
    assert thumbnail_type(PNG,'image/png') == 'image/png'
    jpg = Path(__file__).resolve().parents[1]/'addons/skin.bobbi.cinema/media/bg/Movie.jpg'
    assert thumbnail_type(jpg.read_bytes(),'image/jpeg') == 'image/jpeg'
    # 2x2 synthetic cyan WebP encoded by ffmpeg/libwebp; no codec dependency for tests.
    webp = base64.b64decode('UklGRhwAAABXRUJQVlA4TBAAAAAvAUAAAAfQ/+x//wMR0f8A')
    assert thumbnail_type(webp,'image/webp') == 'image/webp'
    for raw,kind in [(PNG,'text/html'),(PNG[:10]+PNG[-12:], 'image/png'),(b'\xff\xd8\xffbad\xff\xd9','image/jpeg'),
                     (b'RIFF\x04\0\0\0WEBP','image/webp')]:
        with pytest.raises((ValueError,RuntimeError)):
            thumbnail_type(raw,kind)
