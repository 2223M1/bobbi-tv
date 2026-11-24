"""Real Registry, host control HTTP, stream listener and upstream HTTP; Kodi UI is simulated."""
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from bobbi_core import media_pointer
from bobbi_core.library_contract import LibraryError
from bobbi_platform import source_media_http
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.runtime import bind_call
from test_library_plugin import plugin


@pytest.fixture
def upstream(monkeypatch):
    state = SimpleNamespace(tag='"version-one"', mode='ok', calls=[], body=b'0123456789')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state.calls.append((self.path, self.headers['Range'], self.headers.get('If-Match')))
            start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers['Range']).groups())
            mode = state.mode
            data = state.body[start:end+1]
            if mode == 'short':
                data = b''
            if mode == 'long':
                data += b'x'
            self.send_response({'ignore': 200, 'invalid': 416, 'redirect': 302, 'auth': 401}.get(mode, 206))
            self.send_header('Content-Type', 'text/html' if mode == 'html' else 'video/mp4')
            self.send_header('Content-Range', 'bytes %d-%d/%s' % (
                start + (mode == 'wrong_start'), end, '*' if mode == 'unknown' else len(state.body)))
            if mode != 'long':
                self.send_header('Content-Length', str(len(data)))
            self.send_header('ETag', state.tag if mode != 'weak' else 'W/"v"')
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    thread.start()
    # Model an explicitly selected household origin without exposing a test
    # listener to the LAN. All HTTP headers/framing/bytes are real.
    def endpoint(url, remaining):
        from urllib.parse import urlsplit
        assert urlsplit(url).hostname == 'media.lan'
        u = urlsplit(url)
        return HTTPConnection('127.0.0.1', server.server_port, timeout=remaining()), u.path + '?' + u.query
    monkeypatch.setattr(source_media_http, 'connection', endpoint)
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('mode,code', [('ignore', 'MEDIA_RANGE_UNSUPPORTED'), ('invalid', 'MEDIA_RANGE_UNSUPPORTED'),
    ('wrong_start', 'MEDIA_RANGE_INVALID'), ('unknown', 'MEDIA_RANGE_INVALID'), ('short', 'MEDIA_RANGE_INVALID'),
    ('long', 'MEDIA_RANGE_INVALID'), ('html', 'MEDIA_TYPE_UNSUPPORTED'), ('weak', 'MEDIA_IDENTITY_UNVERIFIED'),
    ('redirect', 'MEDIA_REDIRECT'), ('auth', 'MEDIA_AUTH')])
def test_probe_rejects_unsupported_finite_media(upstream, mode, code):
    upstream.mode = mode
    with pytest.raises(LibraryError, match=code):
        source_media_http.probe('http://media.lan/original.mp4', {})
    assert len(upstream.calls) == 1


@pytest.mark.parametrize('doc', [b'#KODIPROP:foo=bar\nhttps://a/a.mp4', b'http://a/a.mp4\nhttp://a/b.mp4',
    b'plugin://a', b'http://a/a.strm', b'http://a/a.m3u8', b'a'*16385, b'\xff', b'http://a/a|x=y'])
def test_pointer_not_interpreted_as_kodi_input(doc):
    with pytest.raises(LibraryError):
        media_pointer.parse(doc)


@pytest.mark.parametrize('change', ['pointer', 'etag', 'remove_readd', 'profile'])
def test_plugin_to_host_to_actual_range_then_revoke(plugin, tmp_path, monkeypatch, upstream, change):
    from bobbi_platform.source_streams import local_media_url
    media = tmp_path / 'media'
    media.mkdir()
    pointer = media / 'Sample.strm'
    pointer.write_bytes(b'\xef\xbb\xbfhttp://media.lan/film.mp4?private=test-only\r\n')
    src = vfs_source('Local', str(media))
    store = Registry(plugin.path)
    store.save(src)
    store.close()
    prompts = []
    monkeypatch.setattr(plugin.module.xbmcgui, 'Dialog', lambda: SimpleNamespace(
        yesno=lambda *a: prompts.append(a) or True))
    live = [True]
    host = Host(tmp_path, profile_current=lambda: live[0])
    host.start()
    try:
        plugin.module.execute(17, dict(action='play_pointer', source=src.id, relative='Sample.strm'))
        row = plugin.resolved[0][2]
        assert plugin.resolved[0][:2] == (17, True) and row.properties['StartOffset'] == '0'
        assert 'private' not in repr(prompts) and 'http://media.lan' in repr(prompts)
        local_media_url(dict(size=10, url=row.path))
        with urlopen(Request(row.path, headers={'Range': 'bytes=4-7'}), timeout=3) as reply:
            assert reply.status == 206 and reply.read() == b'4567'
        assert [call[1:] for call in upstream.calls] == [('bytes=0-0', None), ('bytes=4-7', '"version-one"')]
        if change == 'pointer':
            pointer.write_bytes(b'http://media.lan/different.mp4')
        elif change == 'etag':
            upstream.tag = '"version-two"'
        elif change == 'profile':
            live[0] = False
        else:
            store = Registry(plugin.path)
            store.remove(src.id)
            store.save(src)
            store.close()
        with pytest.raises((HTTPError, OSError)):
            urlopen(Request(row.path, headers={'Range': 'bytes=0-3'}), timeout=3).read()
        assert len(upstream.calls) == (3 if change == 'etag' else 2)
    finally:
        host.close()
