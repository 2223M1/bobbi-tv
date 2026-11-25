"""Subprocess-isolated bundled HTTP runtime regression suite for R06 (RB-03)."""
import datetime
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from threading import Event, Thread
import xml.etree.ElementTree as ET

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from bobbi_core.http_policy import read_bounded_http_body
from bobbi_platform.updates import UpdateError
from bobbi_platform.upstream_addons import UPSTREAM_COMPONENTS, check_dependencies

ROOT = Path(__file__).resolve().parents[1]

SUBPROCESS_PROBE = r"""
import gzip
import hashlib
import http.client
from io import BytesIO
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile

repo = Path(sys.argv[1]).resolve()
mode = sys.argv[2]

vendor_libs = [
    str(repo / 'third_party/addons/script.module.requests/lib'),
    str(repo / 'third_party/addons/script.module.urllib3/lib'),
    str(repo / 'third_party/addons/script.module.certifi/lib'),
    str(repo / 'third_party/addons/script.module.chardet/lib'),
    str(repo / 'third_party/addons/script.module.idna/lib'),
    str(repo / 'addons/script.module.bobbi.core/lib'),
    str(repo / 'addons/plugin.video.bobbi.torrent/lib'),
]
# Strip any site-packages directory holding pip requests/urllib3 so only shipped bytes can load
clean_path = []
for entry in sys.path:
    p = Path(entry) if entry else None
    if p and ((p / 'requests').exists() or (p / 'urllib3').exists()):
        continue
    clean_path.append(entry)
sys.path[:] = vendor_libs + clean_path

import requests
import urllib3
from urllib3.response import HTTPResponse

req_file = Path(requests.__file__).resolve()
u3_file = Path(urllib3.__file__).resolve()
assert (repo / 'third_party/addons/script.module.requests') in req_file.parents, req_file
assert (repo / 'third_party/addons/script.module.urllib3') in u3_file.parents, u3_file

if mode == 'import_and_offline_bounds':
    # R06-02: 4 MiB gzip sample, read(256) keeps internal decoded buffer bounded
    wire = gzip.compress(b'x' * (4 * 1024 * 1024), mtime=0)
    with HTTPResponse(body=BytesIO(wire), headers={'Content-Encoding': 'gzip'},
                      preload_content=False, decode_content=True) as resp:
        head = resp.read(256)
        decoded_buf = len(resp._decoded_buffer)

    # R06-03: 70003-byte chunk-size line rejected
    class MemorySocket:
        def __init__(self, raw):
            self.raw = raw
        def makefile(self, m):
            return BytesIO(self.raw)
    chunk_line = b'0' * 70000 + b'1\r\n'
    raw = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' + chunk_line + b'x\r\n0\r\n\r\n'
    origin = http.client.HTTPResponse(MemorySocket(raw), method='GET')
    origin.begin()
    chunk_accepted = True
    chunk_err = None
    try:
        with HTTPResponse(body=origin, headers=dict(origin.headers.items()), original_response=origin,
                          preload_content=False, decode_content=True) as resp:
            b''.join(resp.stream(amt=1))
    except Exception as exc:
        chunk_accepted = False
        chunk_err = type(exc).__name__

    # R06-04: synthetic .netrc cross-target URL isolation + trust_env=False
    old_netrc = os.environ.get('NETRC')
    with tempfile.TemporaryDirectory(prefix='bobbi-r06-netrc-') as tmp:
        netrc = Path(tmp) / 'synthetic.netrc'
        netrc.write_text('machine bobbi-trusted.invalid login syn-user password syn-pass\n')
        netrc.chmod(0o600)
        os.environ['NETRC'] = str(netrc)
        try:
            url = 'https://bobbi-trusted.invalid:443@bobbi-target.invalid/resource'
            synthetic_auth = requests.auth._basic_auth_str('syn-user', 'syn-pass')
            with requests.Session() as default_session:
                prep_default = default_session.prepare_request(requests.Request('GET', url))
            with requests.Session() as untrusted_session:
                untrusted_session.trust_env = False
                prep_untrusted = untrusted_session.prepare_request(requests.Request('GET', 'https://bobbi-trusted.invalid/resource'))
        finally:
            if old_netrc is None:
                os.environ.pop('NETRC', None)
            else:
                os.environ['NETRC'] = old_netrc

    print(json.dumps(dict(
        requests_version=requests.__version__,
        urllib3_version=urllib3.__version__,
        requests_file=str(req_file),
        urllib3_file=str(u3_file),
        read_len=len(head),
        decoded_buffer_bytes=decoded_buf,
        chunk_accepted=chunk_accepted,
        chunk_error=chunk_err,
        default_has_auth=(prep_default.headers.get('Authorization') == synthetic_auth),
        trust_env_false_has_auth=(prep_untrusted.headers.get('Authorization') == synthetic_auth),
    )))

elif mode == 'tls_pool_isolation':
    port = int(sys.argv[3])
    ca_path = sys.argv[4]
    urllib3.disable_warnings()
    with requests.Session() as session:
        session.trust_env = False
        r1 = session.get(f'https://127.0.0.1:{port}/ping', verify=False, timeout=5)
        assert r1.status_code == 200 and r1.text == 'ok'
        verified_rejected = False
        try:
            session.get(f'https://127.0.0.1:{port}/ping', verify=ca_path, timeout=5)
        except requests.exceptions.SSLError:
            verified_rejected = True
    print(json.dumps(dict(unverified_ok=True, verified_rejected=verified_rejected)))

elif mode == 'custom_adapter_contract':
    port = int(sys.argv[3])
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:9'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:9'
    from bobbi_torrent.http_io import RequestIO
    from bobbi_core.http_policy import request_with_safe_redirects, read_bounded_http_body

    cancelled = [False]
    def check():
        if cancelled[0]:
            raise RuntimeError('USER_CANCELLED')

    with requests.Session() as session:
        session.trust_env = False
        with RequestIO(session, check):
            r_range = session.get(f'http://127.0.0.1:{port}/media', headers={'Range': 'bytes=2-5'}, timeout=5)
            assert r_range.status_code == 206 and r_range.content == b'2345'

            r_redir = request_with_safe_redirects(
                session.get,
                f'http://127.0.0.1:{port}/redirect',
                validator=lambda u: u.startswith(f'http://127.0.0.1:{port}/'),
                timeout=5,
                stream=True,
            )
            body = read_bounded_http_body(r_redir, max_bytes=1024)
            r_redir.close()
            assert body == b'{"ok":true}'

            cancelled[0] = True
            cancel_caught = False
            try:
                session.get(f'http://127.0.0.1:{port}/media', timeout=5)
            except Exception as exc:
                cancel_caught = ('USER_CANCELLED' in str(exc)) or isinstance(exc, RuntimeError)
    print(json.dumps(dict(range_ok=True, redirect_ok=True, proxy_ignored=True, cancel_caught=cancel_caught)))
"""


def _run_probe(mode, *extra_args):
    res = subprocess.run(
        [sys.executable, '-B', '-c', SUBPROCESS_PROBE, str(ROOT), mode, *map(str, extra_args)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if res.returncode != 0:
        raise AssertionError(f'probe {mode} failed ({res.returncode}):\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}')
    return json.loads(res.stdout.strip())


def test_r06_01_02_03_04_vendored_import_decompression_chunked_and_netrc():
    data = _run_probe('import_and_offline_bounds')
    assert data['requests_version'] == '2.34.2'
    assert data['urllib3_version'] == '2.8.0'
    assert 'third_party' in data['requests_file']
    assert 'third_party' in data['urllib3_file']
    assert data['read_len'] == 256
    assert data['decoded_buffer_bytes'] <= 65536
    assert data['chunk_accepted'] is False
    assert data['chunk_error'] in ('ProtocolError', 'InvalidChunkLength', 'MaxRetryError')
    assert data['default_has_auth'] is False
    assert data['trust_env_false_has_auth'] is False

    locks = json.loads((ROOT / 'release/kodi-vendors.json').read_text(encoding='utf-8'))
    assert locks['script.module.requests']['version'] == '2.34.2'
    assert locks['script.module.urllib3']['version'] == '2.8.0'
    for addon in ('script.module.requests', 'script.module.urllib3'):
        base = ROOT / 'third_party/addons' / addon
        for rel, expected_sha in locks[addon]['files'].items():
            disk_rel = 'licenses/upstream-LICENSE.txt' if rel in ('LICENSE', 'LICENSE.txt') else rel
            assert hashlib.sha256((base / disk_rel).read_bytes()).hexdigest() == expected_sha


def test_r06_02_consumer_encoding_rejection_and_decompression_cap():
    class FakeResp:
        def __init__(self, wire: bytes, headers: dict):
            self.headers = headers
            self.raw = BytesIO(wire)

    # Reject abnormal / chained encodings before decoding
    for bad_enc in ('br', 'zstd', 'gzip, gzip', 'x-custom'):
        with pytest.raises(ValueError, match='unsupported content encoding'):
            read_bounded_http_body(FakeResp(b'{}', {'Content-Encoding': bad_enc}), max_bytes=1024)

    # Bounded valid gzip succeeds
    small_gz = gzip.compress(b'{"id":"ok"}', mtime=0)
    assert read_bounded_http_body(FakeResp(small_gz, {'Content-Encoding': 'gzip'}), max_bytes=1024) == b'{"id":"ok"}'

    # 4 MiB gzip bomb rejected at consumer cap
    bomb_gz = gzip.compress(b'A' * (4 * 1024 * 1024), mtime=0)
    with pytest.raises(ValueError, match='response too large'):
        read_bounded_http_body(FakeResp(bomb_gz, {'Content-Encoding': 'gzip'}), max_bytes=8192)


def _generate_cert_pair():
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
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_addr_loopback())]), critical=False)
        .sign(priv, hashes.SHA256())
    )
    return (
        priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def ip_addr_loopback():
    import ipaddress
    return ipaddress.ip_address('127.0.0.1')


def test_r06_05_tls_verify_state_pool_isolation(tmp_path):
    server_key, server_cert = _generate_cert_pair()
    _, unrelated_ca_cert = _generate_cert_pair()

    cert_file = tmp_path / 'server.pem'
    cert_file.write_bytes(server_key + server_cert)
    ca_file = tmp_path / 'other_ca.pem'
    ca_file.write_bytes(unrelated_ca_cert)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            return

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            self.wfile.write(b'ok')

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    httpd.daemon_threads = True
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_file))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    worker = Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    try:
        out = _run_probe('tls_pool_isolation', httpd.server_port, ca_file)
        assert out == {'unverified_ok': True, 'verified_rejected': True}
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)


def test_r06_06_custom_adapter_and_kodi_upstream_ownership_preservation(tmp_path):
    payload = b'0123456789'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/target')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if self.path == '/target':
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            rng = self.headers.get('Range')
            if rng == 'bytes=2-5':
                part = payload[2:6]
                self.send_response(206)
                self.send_header('Content-Range', f'bytes 2-5/{len(payload)}')
                self.send_header('Content-Length', str(len(part)))
                self.end_headers()
                self.wfile.write(part)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    httpd = HTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    try:
        out = _run_probe('custom_adapter_contract', httpd.server_port)
        assert out == {'range_ok': True, 'redirect_ok': True, 'proxy_ignored': True, 'cancel_caught': True}
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)

    # Verify installed Kodi upstream addons are preserved when >= minimum (2.31.0 / 2.2.3), and rejected via Kodi upgrade path when outdated
    addons_dir = tmp_path / 'addons'
    for name in UPSTREAM_COMPONENTS:
        ver = '2.31.0' if name == 'script.module.requests' else '2.2.3' if name == 'script.module.urllib3' else '99.0.0'
        comp = addons_dir / name
        comp.mkdir(parents=True)
        (comp / 'addon.xml').write_text(f'<addon id="{name}" version="{ver}"/>', encoding='utf-8')
        (comp / 'kodi-origin-marker').write_text('kodi-owned', encoding='utf-8')

    minimums = check_dependencies(addons_dir, ROOT / 'addons')
    assert minimums['script.module.requests'] == '2.31.0'
    assert minimums['script.module.urllib3'] == '2.2.3'
    assert (addons_dir / 'script.module.requests/kodi-origin-marker').read_text(encoding='utf-8') == 'kodi-owned'

    # Higher third-party installed Kodi addons (>= 2.31.0 / >= 2.2.3) are also accepted without overwriting
    (addons_dir / 'script.module.requests/addon.xml').write_text(
        '<addon id="script.module.requests" version="2.35.0+matrix.1"/>', encoding='utf-8'
    )
    (addons_dir / 'script.module.urllib3/addon.xml').write_text(
        '<addon id="script.module.urllib3" version="2.9.1+matrix.1"/>', encoding='utf-8'
    )
    assert check_dependencies(addons_dir, ROOT / 'addons')['script.module.urllib3'] == '2.2.3'
    assert (addons_dir / 'script.module.requests/kodi-origin-marker').read_text(encoding='utf-8') == 'kodi-owned'

    # Below-floor installed Kodi addons fail closed with Kodi upgrade instruction without overwriting
    (addons_dir / 'script.module.requests/addon.xml').write_text(
        '<addon id="script.module.requests" version="2.30.0"/>', encoding='utf-8'
    )
    with pytest.raises(UpdateError, match='script.module.requests requires 2.31.0; install/update it in Kodi'):
        check_dependencies(addons_dir, ROOT / 'addons')
    assert (addons_dir / 'script.module.requests/kodi-origin-marker').read_text(encoding='utf-8') == 'kodi-owned'

    (addons_dir / 'script.module.requests/addon.xml').write_text(
        '<addon id="script.module.requests" version="2.31.0"/>', encoding='utf-8'
    )
    (addons_dir / 'script.module.urllib3/addon.xml').write_text(
        '<addon id="script.module.urllib3" version="2.2.2"/>', encoding='utf-8'
    )
    with pytest.raises(UpdateError, match='script.module.urllib3 requires 2.2.3; install/update it in Kodi'):
        check_dependencies(addons_dir, ROOT / 'addons')
    assert (addons_dir / 'script.module.urllib3/kodi-origin-marker').read_text(encoding='utf-8') == 'kodi-owned'
