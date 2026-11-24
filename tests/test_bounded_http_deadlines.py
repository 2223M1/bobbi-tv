"""Loopback TCP/TLS regression suite for R12 (SRC-R2-06 & REV-06)."""
import datetime
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import ipaddress
import socket
import ssl
from threading import Event, Thread
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from bobbi_core.bounded_http import AttemptCancelled, AttemptHandle, resolve_addresses
from bobbi_core.library_contract import LibraryError
from bobbi_platform import server_http, source_media_http, t4_http
from bobbi_platform.pan_accounts import PanError, empty_scope
from bobbi_platform.pan_http import Session as PanSession
from bobbi_platform.pan_request_policy import Cooldowns, MAX_COOLDOWN, Operation, RateLimited


def _make_cert():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(priv.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                x509.DNSName('localhost'),
            ]),
            critical=False,
        )
        .sign(priv, hashes.SHA256())
    )
    return (
        priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def _start_drip_server(phase: str, *, media_probe: bool = False):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(2)
    srv.settimeout(3)
    stop = Event()

    def serve():
        try:
            conn, _ = srv.accept()
            with conn:
                conn.settimeout(2)
                req = b''
                while b'\r\n\r\n' not in req:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    req += chunk
                if media_probe:
                    status = b'HTTP/1.1 206 Partial Content\r\n'
                    suffix = (
                        b'\r\nContent-Type: video/x-matroska\r\nContent-Range: bytes 0-0/1024\r\n'
                        b'Content-Length: 1\r\nETag: "strong-v1"\r\nConnection: close\r\n\r\nx'
                    )
                    body = b''
                else:
                    status = b'HTTP/1.1 200 OK\r\n'
                    body = b'{"value":"1234567890123456789012345678901234567890"}'
                    suffix = (
                        b'\r\nContent-Type: application/json\r\nContent-Length: '
                        + str(len(body)).encode()
                        + b'\r\nConnection: close\r\n\r\n'
                    )
                conn.sendall(status + b'X-Drip: ')
                if phase == 'headers':
                    for b in b'a' * 60:
                        if stop.wait(0.02):
                            return
                        conn.sendall(bytes((b,)))
                    conn.sendall(suffix + body)
                else:
                    conn.sendall(b'ok' + suffix)
                    for b in body:
                        if stop.wait(0.02):
                            return
                        conn.sendall(bytes((b,)))
        except (OSError, TimeoutError):
            pass
        finally:
            srv.close()

    worker = Thread(target=serve, daemon=True)
    worker.start()
    return f'http://127.0.0.1:{srv.getsockname()[1]}', stop, worker, srv


@pytest.mark.parametrize('phase', ['headers', 'body'])
def test_r12_01_02_drip_headers_and_body_respect_150ms_overall_budget(phase, monkeypatch):
    # T4 JSON transport
    url, stop, worker, srv = _start_drip_server(phase)
    try:
        def local_conn(address, remaining, **kw):
            u = urlsplit(address)
            return HTTPConnection(u.hostname, u.port, timeout=remaining()), u.path or '/'

        monkeypatch.setattr(t4_http, 'connection', local_conn)
        t0 = time.monotonic()
        with pytest.raises(LibraryError, match='^T4_TIMEOUT$'):
            t4_http.read(url + '/t4', t0 + 0.15, lambda: False)
        elapsed_t4 = time.monotonic() - t0
        assert elapsed_t4 < 0.45
    finally:
        stop.set()
        srv.close()
        worker.join(2)

    # Emby JSON transport
    url2, stop2, worker2, srv2 = _start_drip_server(phase)
    try:
        session = server_http.Session('emby', url2, 'synthetic-token')
        t0 = time.monotonic()
        with pytest.raises(PanError, match='^PAN_BUDGET_EXHAUSTED$'):
            with session.budget(0.15):
                session.request('/System/Info/Public')
        elapsed_emby = time.monotonic() - t0
        assert elapsed_emby < 0.45
    finally:
        stop2.set()
        srv2.close()
        worker2.join(2)


def test_r12_03_slow_media_probe_never_returns_success_past_budget(monkeypatch):
    # Emby probe_media
    url, stop, worker, srv = _start_drip_server('headers', media_probe=True)
    try:
        session = server_http.Session('emby', url, 'synthetic-token')
        t0 = time.monotonic()
        with pytest.raises(PanError, match='^PAN_BUDGET_EXHAUSTED$'):
            with session.budget(0.15):
                session.probe_media(url + '/Videos/movie/stream?Static=true&MediaSourceId=ver1')
        assert (time.monotonic() - t0) < 0.45
    finally:
        stop.set()
        srv.close()
        worker.join(2)

    # source_media_http.probe (loopback allowed via monkeypatched connection validator for local test)
    url2, stop2, worker2, srv2 = _start_drip_server('headers', media_probe=True)
    try:
        t0 = time.monotonic()
        monkeypatch.setattr(
            source_media_http,
            'connection',
            lambda u, rem, **kw: (HTTPConnection(urlsplit(u).hostname, urlsplit(u).port, timeout=rem()), urlsplit(u).path or '/'),
        )
        with pytest.raises(LibraryError, match='^MEDIA_TIMEOUT$'):
            source_media_http.probe(url2 + '/video.mkv', {}, deadline=t0 + 0.15)
        assert (time.monotonic() - t0) < 0.45
    finally:
        stop2.set()
        srv2.close()
        worker2.join(2)


def test_r12_04_cancel_and_account_revocation_close_socket_and_isolate_attempts():
    # Mid-read account revocation closes socket promptly and discards partial data
    url, stop, worker, srv = _start_drip_server('body')
    revoked = Event()
    entered = Event()

    def current_guard(_expected):
        entered.set()
        if revoked.is_set():
            raise PanError('PAN_ACCOUNT_CHANGED')

    try:
        session = server_http.Session('emby', url, 'synthetic-token')
        op = Operation(empty_scope('quark'), 'b' * 32, 'directory', seconds=5, current=current_guard)
        session.operation = op
        outcome = []

        def run_req():
            try:
                outcome.append(('ok', session.request('/System/Info/Public')))
            except PanError as exc:
                outcome.append(('err', str(exc)))

        t = Thread(target=run_req, daemon=True)
        t0 = time.monotonic()
        t.start()
        assert entered.wait(1.0)
        time.sleep(0.05)
        revoked.set()
        t.join(1.0)
        assert not t.is_alive()
        assert (time.monotonic() - t0) < 0.45
        assert outcome == [('err', 'PAN_ACCOUNT_CHANGED')]
    finally:
        stop.set()
        srv.close()
        worker.join(2)

    # AttemptHandle isolation: aborting attempt 1 never affects attempt 2's socket
    s1_a, s1_b = socket.socketpair()
    s2_a, s2_b = socket.socketpair()
    try:
        with AttemptHandle(deadline=time.monotonic() + 5) as a1, AttemptHandle(deadline=time.monotonic() + 5) as a2:
            a1.attach_tcp(s1_a)
            a2.attach_tcp(s2_a)
            a1.abort(AttemptCancelled('old attempt cancelled'))
            s2_b.sendall(b'ping')
            assert s2_a.recv(4) == b'ping'
    finally:
        for s in (s1_a, s1_b, s2_a, s2_b):
            s.close()

    # Slow DNS worker respects deadline and discards late answer
    late_gate = Event()

    def slow_resolver(host, port, family, socktype):
        late_gate.wait(0.5)
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1', port or 80))]

    t0 = time.monotonic()
    with AttemptHandle(deadline=t0 + 0.12) as dns_attempt:
        with pytest.raises(TimeoutError):
            resolve_addresses('slow-fixture.invalid', 443, dns_attempt, resolver=slow_resolver)
    assert (time.monotonic() - t0) < 0.35
    late_gate.set()


def test_r12_05_verified_tls_passes_and_invalid_or_unverified_tls_rejected(tmp_path):
    srv_key, srv_cert = _make_cert()
    _, wrong_ca = _make_cert()
    cert_path = tmp_path / 'srv.pem'
    cert_path.write_bytes(srv_key + srv_cert)
    trusted_ca_path = tmp_path / 'trusted_ca.pem'
    trusted_ca_path.write_bytes(srv_cert)
    wrong_ca_path = tmp_path / 'wrong_ca.pem'
    wrong_ca_path.write_bytes(wrong_ca)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            if self.path.startswith('/Videos/'):
                self.send_response(206)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Content-Range', 'bytes 0-0/4096')
                self.send_header('Content-Length', '1')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(b'M')
                return
            body = b'{"ServerName":"LocalTLS"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    httpd.daemon_threads = True
    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.load_cert_chain(certfile=str(cert_path))
    httpd.socket = srv_ctx.wrap_socket(httpd.socket, server_side=True)
    worker = Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    base = f'https://127.0.0.1:{httpd.server_port}'
    try:
        good_ctx = ssl.create_default_context(cafile=str(trusted_ca_path))
        good_session = server_http.Session('emby', base, 'synthetic-token', ssl_context=good_ctx)
        assert good_session.request('/System/Info/Public') == {'ServerName': 'LocalTLS'}
        assert good_session.probe_media(base + '/Videos/m1/stream?Static=true&MediaSourceId=s1') == (4096, 'video/mp4')

        # Wrong CA certificate is rejected, never silently downgraded
        bad_ctx = ssl.create_default_context(cafile=str(wrong_ca_path))
        bad_session = server_http.Session('emby', base, 'synthetic-token', ssl_context=bad_ctx)
        with pytest.raises(PanError, match='^PAN_NETWORK_ERROR$'):
            bad_session.request('/System/Info/Public')

        # Unverified SSLContext (CERT_NONE) is explicitly forbidden by AttemptHandle.handoff_tls
        unverified_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        unverified_ctx.check_hostname = False
        unverified_ctx.verify_mode = ssl.CERT_NONE
        s_a, s_b = socket.socketpair()
        try:
            with AttemptHandle(deadline=time.monotonic() + 2) as att:
                att.attach_tcp(s_a)
                with pytest.raises(ssl.SSLError, match='Unverified TLS context is forbidden'):
                    att.handoff_tls(s_a, unverified_ctx, server_hostname='127.0.0.1')
        finally:
            s_a.close()
            s_b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)


def test_rev06_retry_after_exceeding_remaining_budget_fails_immediately_without_clamped_retry():
    clock = [100.0]
    calls = []

    def open_429(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, 'Too Many Requests', {'Retry-After': '30'}, BytesIO(b'{}'))

    cooldowns = Cooldowns(clock=lambda: clock[0])
    expected = empty_scope('aliyun')
    op = Operation(expected, 'c' * 32, 'directory', clock=lambda: clock[0], seconds=10, cooldowns=cooldowns)
    session = PanSession('aliyun', opener=SimpleNamespace(open=open_429), clock=lambda: clock[0])
    session.operation = op

    with pytest.raises(RateLimited) as exc_info:
        session.request('https://api.alipan.com/adrive/v3/file/list', body={})

    # Must NOT have clamped 30s -> 5s and retried a second time!
    assert len(calls) == 1
    assert exc_info.value.raw_delay == 30.0
    assert exc_info.value.delay == MAX_COOLDOWN
    assert exc_info.value.retry_at == 130.0
    # Shared cooldown stays capped at MAX_COOLDOWN so malformed/large Retry-After cannot stall future ops
    assert cooldowns.remaining(expected) == MAX_COOLDOWN
