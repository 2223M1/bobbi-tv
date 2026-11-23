"""Real shipped HTTP/TLS stack, connect stalls and independent session reuse."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import sys
import tempfile
from threading import Thread, enumerate as threads
import time

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT/'third_party/addons').glob('*/lib'):
    sys.path.insert(0, str(path))
for name in ('plugin.video.bobbi.torrent', 'script.module.bobbi.core'):
    sys.path.insert(0, str(ROOT/'addons'/name/'lib'))
from bobbi_torrent.backend import Backend, BackendError


def config(endpoint):
    return dict(schema=1, endpoint=endpoint, auth=None, metadata_seconds=2, buffering_seconds=2)


def no_workers():
    assert not [t.name for t in threads() if t.name in ('bobbi-control-io', 'bobbi-file-choice-status')]


def connect_stall():
    listeners, fillers = [], []
    try:
        ipv4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ipv4.bind(('127.0.0.1', 0)); ipv4.listen(0); listeners.append(ipv4)
        port = ipv4.getsockname()[1]
        addresses = socket.getaddrinfo('localhost', port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, kind, protocol, _, address in addresses:
            assert ipaddress.ip_address(address[0]).is_loopback
            if family != socket.AF_INET:
                sock = socket.socket(family, kind, protocol)
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                sock.bind(address); sock.listen(0); listeners.append(sock)
            for _ in range(16):
                sock = socket.socket(family, kind, protocol); sock.settimeout(.03)
                try: sock.connect(address); fillers.append(sock)
                except socket.timeout: sock.close(); break
            else: raise AssertionError('Accept queue not saturated')
        backend = Backend(config('http://localhost:'+str(port)))
        began = time.monotonic()
        try:
            backend.request('GET', '/echo', began+.35, lambda:None)
        except BackendError as error:
            assert error.code == 'TORRENT_CONTROL_DEADLINE', error.code
        else: raise AssertionError('Expected deadline')
        finally: backend.close()
        elapsed = time.monotonic()-began
        assert elapsed < .8, elapsed
        no_workers()
        return dict(case='connect_deadline_no_back', seconds=elapsed, addresses=len(addresses))
    finally:
        for sock in fillers+listeners: sock.close()


def normal_and_tls(directory):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
        .sign(key, hashes.SHA256()))
    certificate, private_key = directory/'cert.pem', directory/'key.pem'
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    observations = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            observations.append(dict(host=self.headers['Host'], path=self.path))
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers()
            self.wfile.write(b'ok')
    results = []
    for address in ('127.0.0.1', '::1'):
        class Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6 if ':' in address else socket.AF_INET
        try: server = Server((address, 0), Handler)
        except OSError:
            results.append(dict(case='ipv6', state='unavailable')); continue
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval':.05}); thread.start()
        endpoint = ('['+address+']') if ':' in address else address
        backend = Backend(config('http://'+endpoint+':'+str(server.server_port)))
        try:
            for _ in range(2):
                assert backend.request('GET', '/echo', time.monotonic()+2, lambda:None) == b'ok'
            no_workers(); results.append(dict(case=address, repeated_requests=2))
        finally:
            backend.close(); server.shutdown(); server.server_close(); thread.join()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(certificate, private_key)
    sni = []
    context.set_servername_callback(lambda sock, name, ctx:sni.append(name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval':.05}); thread.start()
    try:
        for host, trusted, allowed in [('localhost',True,True), ('localhost',False,False), ('127.0.0.1',True,False)]:
            backend = Backend(config('https://'+host+':'+str(server.server_port)))
            if trusted: backend.session.verify = str(certificate)
            try:
                try: value = backend.request('GET','/echo',time.monotonic()+2,lambda:None)
                except BackendError:
                    assert not allowed
                else:
                    assert allowed and value == b'ok'
                results.append(dict(case='TLS', host=host, trusted=trusted, accepted=allowed))
                no_workers()
            finally: backend.close()
        assert 'localhost' in sni
        assert any(row['host'].startswith('localhost:') for row in observations)
    finally:
        server.shutdown(); server.server_close(); thread.join()
    return results


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='ce2050-connect-') as temporary:
        print(json.dumps(dict(cases=[connect_stall()]+normal_and_tls(Path(temporary)))))
