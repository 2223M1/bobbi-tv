"""A one-shot media probe is not a media owner: exercise socket, Registry and actual HTTP."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_core.library_contract import Source
from bobbi_platform import runtime
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.server_accounts import Accounts
from bobbi_platform.server_emby import Client


@pytest.fixture
def private(tmp_path):
    secret = 'fixture-private-user-token'
    state = SimpleNamespace(status=206, mime='video/mp4', calls=[], during_probe=lambda: None,
        media=dict(Id='v2', Path='/srv/private/film.mp4', Protocol='File', SupportsDirectPlay=True, Size=8))
    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            path, query = urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)
            auth = self.headers.get('X-Emby-Token')
            state.calls.append((self.command, path, query, auth == secret))
            if path == '/api/Videos/i/stream':
                assert query == {'Static': ['true'], 'MediaSourceId': ['v2']}
                assert self.command == 'GET' and self.headers.get('Range') == 'bytes=0-0'
                assert 'Cookie' not in self.headers and 'Authorization' not in self.headers
                state.during_probe()
                status = 401 if auth != secret else state.status
                self.send_response(status)
                if status == 302:
                    self.send_header('Location', '/api/never-follow')
                self.send_header('Content-Length', '1')
                self.send_header('Content-Range', 'bytes 0-0/8')
                self.send_header('Content-Type', state.mime)
                self.end_headers()
                self.wfile.write(b'x')
                return
            assert auth == secret
            if path == '/api/System/Info/Public':
                value = dict(Id='s')
            elif path == '/api/Users/u':
                value = dict(Id='u')
            elif path == '/api/Users/u/Items/i':
                value = dict(Id='i', MediaSources=[dict(state.media, Id='not-first'), state.media])
            elif path == '/api/Items/i/PlaybackInfo':
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert data['MediaSourceId'] == 'v2' and data['UserId'] == 'u'
                assert all(data[k] is False for k in ('IsPlayback', 'AutoOpenLiveStream', 'EnableTranscoding'))
                value = dict(MediaSources=[state.media])
            else:
                self.send_error(404)
                return
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = dispatch
    server = ThreadingHTTPServer(('127.0.0.1', 0), API)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval':.05})
    worker.start()
    host = Host(tmp_path)
    base = 'http://127.0.0.1:%d/api' % server.server_port
    source = Source('b'*32, 'Emby', 'media_server', base, password=secret,
                    metadata=dict(schema=1, provider='emby', server_id='s', user_id='u'))
    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        store.save(source)
        expected = Accounts(tmp_path).snapshot('emby')
        host.start()
        def play(**more):
            return runtime.call('pan_emby_direct', dict(expected=expected, item_id='i', media_id='v2', **more),
                                path=host.runtime.path, expected_token=host.runtime.server.token)
        def revoke():
            # Each thread owns its own connection to the same on-disk Registry.
            changed = Registry(tmp_path / 'libraries.sqlite3')
            try:
                changed.remove(source.id)
            finally:
                changed.close()
        state.play, state.base, state.revoke = play, base, revoke
        yield state
        assert all('/Sessions/' not in path and path != '/api/never-follow' for _, path, _, _ in state.calls)
        assert host.catalog is None and (not host.pans or host.pans.streams is None)
        assert not (tmp_path / 'media-index.sqlite3').exists()
    finally:
        host.close()
        store.close()
        server.shutdown()
        server.server_close()
        worker.join()


def test_media_headers_are_per_request_exact_non_redirecting_and_not_returned(private):
    def anonymous(**fields):
        with pytest.raises(PanError, match='PAN_EMBY_DIRECT_AUTH_REQUIRED'):
            private.play(**fields)
    anonymous()
    assert private.play(authenticated=True) == dict(
        url=private.base+'/Videos/i/stream?Static=true&MediaSourceId=v2', mime='video/mp4')
    anonymous(authenticated=False)
    anonymous()
    assert [auth for _, p, _, auth in private.calls if p.endswith('/stream')] == [False,True,False,False]
    for invalid in (1, 0, 'true', None):
        count = len(private.calls)
        with pytest.raises(PanError):
            private.play(authenticated=invalid)
        assert len(private.calls) == count


@pytest.mark.parametrize('status,err', [(401,'PAN_SERVER_UNAUTHORIZED'), (403,'PAN_SERVER_FORBIDDEN'),
    (302,'PAN_REDIRECT_REJECTED'), (200,'PAN_MEDIA_UNSUPPORTED')])
def test_private_probe_fails_closed(private, status, err):
    private.status = status
    with pytest.raises(PanError, match=err):
        private.play(authenticated=True)


@pytest.mark.parametrize('change', [dict(Protocol='Http', Path='https://elsewhere.example/remote'),
    dict(Protocol='File', Path='https://elsewhere.example/not-a-local-file'),
    dict(RequiredHttpHeaders={'Authorization':'untrusted'}), dict(IsInfiniteStream=True), dict(RequiresOpening=True),
    dict(SupportsDirectPlay=False)])
def test_private_probe_never_accepts_arbitrary_media_targets_or_modes(private, change):
    private.media.update(change)
    with pytest.raises(PanError, match='PAN_MEDIA_UNSUPPORTED'):
        private.play(authenticated=True)
    assert not any(p.endswith('/stream') for _,p,_,_ in private.calls)


def test_size_and_mime_must_prove_a_finite_selected_original(private):
    private.media['Size'] = 9
    with pytest.raises(PanError, match='PAN_FILE_CHANGED'):
        private.play(authenticated=True)
    private.media['Size'] = 8
    private.mime = 'text/html'
    with pytest.raises(PanError, match='PAN_MEDIA_UNSUPPORTED'):
        private.play(authenticated=True)


def test_bind_and_final_check_when_removed_during_probe(private):
    private.during_probe = private.revoke
    with pytest.raises(PanError, match='PAN_ACCOUNT_CHANGED'):
        private.play(authenticated=True)
    count = len(private.calls)
    with pytest.raises(PanError, match='PAN_ACCOUNT_CHANGED'):
        private.play(authenticated=True)
    assert len(private.calls) == count


def test_file_url_containing_credential_never_requests_consent_or_probes(monkeypatch):
    token = 'synthetic-user-token'
    media = dict(Id=token, Protocol='File', Path='/media/test.mp4', SupportsDirectPlay=True)
    client = Client('emby', dict(location='https://emby.example', token=token))
    monkeypatch.setattr(client, '_identity', lambda: None)
    monkeypatch.setattr(client, '_item', lambda entry:dict(MediaSources=[media]))
    monkeypatch.setattr(client, '_playback_source', lambda entry, mid:media)
    monkeypatch.setattr(client.session, 'probe_media', lambda *args, **kwargs:pytest.fail('unexpected HTTP'))
    for auth in (False,True):
        with pytest.raises(PanError, match='PAN_MEDIA_UNSUPPORTED'):
            client.direct_original('i', token, authenticated=auth)
