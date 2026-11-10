"""Real loopback HTTP framing; no provider traffic or account credentials."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from bobbi_platform.cloud115 import CloudError, request
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session


RAW = b'{"ok":true}'


@pytest.fixture
def wire():
    observed = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def do_GET(self):
            observed.append(self.path)
            self.close_connection = True
            if self.path == '/drop':
                return  # A real EOF before any HTTP status line.
            if self.path == '/bad-status':
                self.connection.sendall(b'not-an-http-status\r\n\r\n')
                return
            self.send_response(200)
            self.send_header('Connection', 'close')
            if self.path in ('/chunked', '/short-chunk'):
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                extra = 3 if self.path == '/short-chunk' else 0
                self.wfile.write(('%x\r\n' % (len(RAW) + extra)).encode() + RAW)
                if not extra:
                    self.wfile.write(b'\r\n0\r\n\r\n')
                return
            body = b'invalid-json' if self.path == '/bad-json' else RAW
            self.send_header('Content-Length', str(len(body) + (self.path == '/short-length')))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield server.server_address[1], observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def local_request(provider, mode, wire):
    port, observed = wire
    local = build_opener(ProxyHandler({}))

    class Opener:
        def open(self, original, timeout):
            # Only this test seam redirects the validated provider request to
            # loopback, exercising urllib/http.client's real socket behavior.
            translated = Request('http://127.0.0.1:%d/%s' % (port, mode),
                                 data=original.data, headers=dict(original.header_items()))
            return local.open(translated, timeout=timeout)

    if provider == '115':
        return request('https://qrcodeapi.115.com/get/status/', opener=Opener())
    return Session('baidu', opener=Opener()).request('https://passport.baidu.com/channel/unicast')


@pytest.mark.parametrize('provider,error,code', [
    ('115', CloudError, 'NETWORK_ERROR'), ('baidu', PanError, 'PAN_NETWORK_ERROR')])
def test_connection_closed_before_response_is_network_error_without_transport_replay(wire, provider, error, code):
    with pytest.raises(error, match='^' + code + '$'):
        local_request(provider, 'drop', wire)
    assert wire[1] == ['/drop']


@pytest.mark.parametrize('provider', ['115', 'baidu'])
@pytest.mark.parametrize('mode', ['complete', 'chunked'])
def test_complete_real_http_framing_is_accepted(wire, provider, mode):
    assert local_request(provider, mode, wire) == {'ok': True}
    assert wire[1] == ['/' + mode]


@pytest.mark.parametrize('provider,error,code', [
    ('115', CloudError, 'INVALID_REPLY'), ('baidu', PanError, 'PAN_REPLY_INVALID')])
@pytest.mark.parametrize('mode', ['bad-status', 'short-chunk', 'short-length', 'bad-json'])
def test_invalid_status_body_or_json_remains_nonretryable(wire, provider, error, code, mode):
    with pytest.raises(error, match='^' + code + '$'):
        local_request(provider, mode, wire)
    assert wire[1] == ['/' + mode]
