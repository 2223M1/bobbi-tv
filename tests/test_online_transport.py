"""Real loopback TLS and HTTP framing; no mocked response.read or download."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import ssl
import json
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from bobbi_platform import online_updates as online, online_transport as transport
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import package, signing
from test_online_updates import offer_for


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    # This controlled fixture listens only on IPv4. Avoid spending the stage
    # budget on Windows' IPv6 refusal before reaching the intended HTTP phase.
    resolver = socket.getaddrinfo
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, port, family=0, kind=0:
        resolver(host, port, socket.AF_INET if host == 'localhost' else family, kind))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), False)
        .sign(key, hashes.SHA256()))
    certificate, private = tmp_path/'cert.pem', tmp_path/'key.pem'
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    state = SimpleNamespace(blob=b'a'*143360, stop=threading.Event(), requests=[], sni=[])
    original_context = ssl.create_default_context
    state.trusted = lambda: original_context(cafile=str(certificate))
    state.untrusted = original_context

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state.requests.append((self.path, dict(self.headers)))
            try:
                if self.path in ('/redirect', '/denied'):
                    self.send_response(302 if self.path == '/redirect' else 403)
                    self.send_header('Location', 'https://not-allowed.invalid/fixture')
                    self.send_header('Content-Length', '10000')
                    self.end_headers()
                    state.stop.wait(5)
                    return
                if self.path == '/headers':
                    state.stop.wait(5)
                    return
                self.send_response(200)
                if self.path.startswith('/chunk'):
                    self.send_header('Transfer-Encoding', 'chunked')
                elif self.path != '/unknown':
                    self.send_header('Content-Length', str(len(state.blob)))
                self.end_headers()
                if self.path == '/idle':
                    state.stop.wait(5)
                elif self.path in ('/drip', '/chunked'):
                    for start in range(0, len(state.blob), 128):
                        raw = state.blob[start:start+128]
                        if self.path == '/chunked':
                            raw = ('%x\r\n' % len(raw)).encode()+raw+b'\r\n'
                        self.wfile.write(raw)
                        self.wfile.flush()
                        if state.stop.wait(.025):
                            return
                    if self.path == '/chunked':
                        self.wfile.write(b'0\r\n\r\n')
                elif self.path == '/chunk-header':
                    self.wfile.write(b'10')  # No CRLF; parser must remain cancellable.
                    self.wfile.flush()
                    state.stop.wait(5)
                elif self.path == '/chunk-trailer':
                    self.wfile.write(b'1\r\na\r\n0\r\nX-Test: unfinished')
                    self.wfile.flush()
                    state.stop.wait(5)
                elif self.path == '/chunk-bad':
                    self.wfile.write(b'not-a-chunk\r\n')
                elif self.path == '/short':
                    self.wfile.write(state.blob[:16])
                else:
                    self.wfile.write(state.blob)
            except (OSError, ssl.SSLError):
                pass  # Expected peer close after cancellation.

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private)
    context.set_servername_callback(lambda sock, name, ctx: state.sni.append(name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02})
    thread.start()
    state.url = 'https://localhost:%d' % server.server_port
    monkeypatch.setattr(ssl, 'create_default_context', state.trusted)
    try:
        yield state
    finally:
        state.stop.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
        assert not thread.is_alive()


def transfer(url, cancelled=lambda: False, maximum=200000, expected=None):
    chunks = []
    online._transfer(url, maximum, chunks.append, cancelled, lambda _: None, expected)
    return b''.join(chunks)


@pytest.mark.parametrize('route', ['/drip', '/idle', '/headers', '/chunked',
                                    '/chunk-header', '/chunk-trailer'])
@pytest.mark.parametrize('end', ['cancel', 'deadline'])
def test_cancel_and_absolute_deadline_in_real_tls_stages(endpoint, monkeypatch, route, end):
    owners = []
    original = transport._Socket.__init__
    def track(owner, *args):
        original(owner, *args)
        owners.append(owner)
    monkeypatch.setattr(transport._Socket, '__init__', track)
    if end == 'deadline':
        monkeypatch.setattr(online, 'TRANSFER_SECONDS', .2)
    started = time.monotonic()
    callback_threads = []
    def cancelled():
        callback_threads.append(threading.get_ident())
        return end == 'cancel' and time.monotonic()-started >= .2
    with pytest.raises(UpdateError, match='^ONLINE_'+('CANCELLED' if end == 'cancel' else 'TIMEOUT')+'$'):
        transfer(endpoint.url+route, cancelled)
    assert time.monotonic()-started < 1.2
    assert set(callback_threads) == {threading.get_ident()}
    assert owners and all(owner.references == 0 and owner.raw.fileno() == -1 for owner in owners)
    assert endpoint.requests[0][0] == route  # Actually reached the intended phase.
    assert online._ACTIVE.get()() is None
    monkeypatch.setattr(online, 'TRANSFER_SECONDS', 600)
    assert transfer(endpoint.url+'/blob') == endpoint.blob


@pytest.mark.parametrize('end', ['cancel', 'deadline'])
def test_tls_handshake_stall_ends_and_closes_socket(monkeypatch, end):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)  # TCP succeeds, no TLS server consumes the ClientHello.
    opened = []
    original = transport._connect
    def track(*args):
        sock = original(*args)
        opened.append(sock)
        return sock
    monkeypatch.setattr(transport, '_connect', track)
    if end == 'deadline':
        monkeypatch.setattr(online, 'TRANSFER_SECONDS', .2)
    started = time.monotonic()
    try:
        with pytest.raises(UpdateError, match='ONLINE_'+('CANCELLED' if end == 'cancel' else 'TIMEOUT')):
            transfer('https://127.0.0.1:%d/' % listener.getsockname()[1],
                     lambda: end == 'cancel' and time.monotonic()-started >= .2)
        assert time.monotonic()-started < 1.2
        assert opened and all(sock.fileno() == -1 for sock in opened)
        peer, _ = listener.accept()
        peer.settimeout(1)
        try:
            while peer.recv(16384):
                pass
        finally:
            peer.close()
    finally:
        listener.close()


@pytest.mark.parametrize('end', ['cancel', 'deadline'])
def test_real_saturated_accept_queue_connect_is_interruptible(monkeypatch, end):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(0)
    fillers = []
    try:
        for _ in range(32):
            filler = socket.socket()
            filler.settimeout(.03)
            try:
                filler.connect(listener.getsockname())
            except TimeoutError:
                filler.close()
                break
            fillers.append(filler)
        else:
            pytest.skip('OS did not expose a saturated accept queue')
        if end == 'deadline':
            monkeypatch.setattr(online, 'TRANSFER_SECONDS', .2)
        # If this unexpectedly reaches TLS, this is not a connect-stage test.
        monkeypatch.setattr(ssl.SSLContext, 'wrap_socket', lambda *a, **kw: pytest.fail('Not stalled in connect'))
        started = time.monotonic()
        with pytest.raises(UpdateError, match='ONLINE_'+('CANCELLED' if end == 'cancel' else 'TIMEOUT')):
            transfer('https://127.0.0.1:%d/' % listener.getsockname()[1],
                     lambda: end == 'cancel' and time.monotonic()-started >= .2)
        assert time.monotonic()-started < 1.2
    finally:
        for sock in fillers:
            sock.close()
        listener.close()


def test_dns_boundary_is_synchronous_and_late_resolution_never_connects(monkeypatch):
    calls = []
    def resolver(*args):
        calls.append(threading.get_ident())
        time.sleep(.2)  # Explicit resolver double, not a real DNS timeout proof.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', resolver)
    monkeypatch.setattr(socket, 'socket', lambda *args: pytest.fail('Late DNS started a connection'))
    started = time.monotonic()
    with pytest.raises(online.Cancelled):
        transfer('https://localhost/', lambda: time.monotonic()-started >= .05)
    assert time.monotonic()-started >= .2
    assert calls == [threading.get_ident()]


@pytest.mark.parametrize('trust,host', [(False, 'localhost'), (True, '127.0.0.1')])
def test_certificate_and_hostname_validation_remain_enabled(endpoint, monkeypatch, trust, host):
    if not trust:
        monkeypatch.setattr(ssl, 'create_default_context', endpoint.untrusted)
    with pytest.raises(URLError) as error:
        transfer(endpoint.url.replace('localhost', host)+'/blob')
    assert isinstance(error.value.reason, ssl.SSLCertVerificationError)
    assert endpoint.requests == []


@pytest.mark.parametrize('route', ['/blob', '/unknown'])
def test_normal_tls_body_sni_and_no_proxy(endpoint, monkeypatch, route):
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    assert transfer(endpoint.url+route, expected=len(endpoint.blob)) == endpoint.blob
    assert endpoint.sni == ['localhost']
    headers = endpoint.requests[0][1]
    assert headers['Accept-Encoding'] == 'identity' and headers['User-Agent'] == 'BobbiTV-CE'


@pytest.mark.parametrize('route,maximum,error', [('/short', 200000, 'SHORT_READ'),
    ('/unknown', 20, 'LENGTH_INVALID'), ('/chunk-bad', 200000, 'RESPONSE_INVALID')])
def test_real_invalid_bodies_rejected(endpoint, route, maximum, error):
    with pytest.raises(UpdateError, match='^ONLINE_'+error+'$'):
        transfer(endpoint.url+route, maximum=maximum)


def test_actual_download_cancellation_owns_only_its_temp_and_next_request_works(endpoint, tmp_path, signing, monkeypatch):
    endpoint.blob = package(tmp_path/'input.zip', signing).read_bytes()
    work = tmp_path/'work'
    work.mkdir()
    preserved = ['previous-backup.zip', 'installation.json', 'account.db', 'watching.db']
    for name in preserved:
        (work/name).write_bytes(b'untouched')
    offer = offer_for(endpoint.blob)
    original_open = online._open
    route = ['/drip']
    def local_transport(url):
        assert url == offer['url']
        return original_open(endpoint.url + route[0])
    monkeypatch.setattr(online, '_open', local_transport)
    started = time.monotonic()
    delivered = []
    with pytest.raises(online.Cancelled):
        online.download(offer, work, signing[1], lambda: time.monotonic()-started >= .15,
                        delivered.append)
    assert time.monotonic()-started < 1.15
    assert {p.name: p.read_bytes() for p in work.iterdir()} == {name: b'untouched' for name in preserved}
    before = list(delivered)
    route[0] = '/blob'
    downloaded = online.download(offer, work, signing[1])
    assert downloaded.read_bytes() == endpoint.blob
    assert delivered == before
    assert all((work/name).read_bytes() == b'untouched' for name in preserved)


def test_concurrent_request_cancellation_cannot_close_other_response(endpoint):
    def cancelled_request():
        started = time.monotonic()
        with pytest.raises(online.Cancelled):
            transfer(endpoint.url+'/idle', lambda: time.monotonic()-started > .2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelled = pool.submit(cancelled_request)
        success = pool.submit(transfer, endpoint.url+'/blob')
        cancelled.result(timeout=2)
        assert success.result(timeout=2) == endpoint.blob


def test_query_uses_real_transport_and_can_cancel_before_headers(endpoint, monkeypatch):
    offer = offer_for(b'fixture')
    endpoint.blob = json.dumps(offer).encode()
    monkeypatch.setattr(online, 'OFFER_URL', endpoint.url+'/blob')
    assert online.latest() == offer
    monkeypatch.setattr(online, 'OFFER_URL', endpoint.url+'/headers')
    started = time.monotonic()
    with pytest.raises(online.Cancelled):
        online.latest(lambda: time.monotonic()-started > .2)
    assert time.monotonic()-started < 1.2


def test_idle_timeout_remains_distinct_from_total_budget(endpoint, monkeypatch):
    monkeypatch.setattr(transport, 'IDLE_SECONDS', .2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        transfer(endpoint.url+'/idle')
    assert .2 <= time.monotonic()-started < 1.2


@pytest.mark.parametrize('route,error', [('/redirect', UpdateError), ('/denied', HTTPError)])
def test_rejected_open_closes_response_before_exception_leaves_caller(endpoint, monkeypatch, route, error):
    owners = []
    original = transport._Socket.__init__
    def track(owner, *args):
        original(owner, *args)
        owners.append(owner)
    monkeypatch.setattr(transport._Socket, '__init__', track)
    with pytest.raises(error) as captured:
        transfer(endpoint.url+route)
    # Keep the exception/traceback alive: relying on GC is not request cleanup.
    assert captured.value
    assert owners and all(owner.references == 0 and owner.raw.fileno() == -1 for owner in owners)
