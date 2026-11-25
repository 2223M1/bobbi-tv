"""Real socket tests for the shared Stremio/Nuvio GET deadline and ownership."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import time

import pytest
import requests

from bobbi_core.http_policy import is_safe_http_url, request_with_safe_redirects, response_json


@pytest.fixture
def server():
    stopped = Event()
    requests_seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests_seen.append((self.path, dict(self.headers)))
            try:
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', 'http://localhost:%d/normal' % self.server.server_port)
                    self.end_headers()
                    return
                if self.path == '/unavailable':
                    self.send_response(503)
                    self.send_header('Content-Length', '2')
                    self.end_headers()
                    self.wfile.write(b'{}')
                    return
                if self.path == '/headers':
                    for octet in b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}':
                        if stopped.wait(.025):
                            return
                        self.connection.sendall(bytes([octet]))
                    return
                body = b'{"answer":12345678901234567890}'
                self.send_response(200)
                if self.path == '/chunked':
                    self.send_header('Transfer-Encoding', 'chunked')
                else:
                    self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if self.path == '/chunked':
                    # The chunk extension is part of framing, before read1 can return.
                    for octet in b'1;slowextension=abcdefghijklmnopqrstuvwxyz\r\n':
                        if stopped.wait(.025):
                            return
                        self.wfile.write(bytes([octet]))
                        self.wfile.flush()
                    self.wfile.write(b'x\r\n0\r\n\r\n')
                elif self.path == '/normal':
                    self.wfile.write(body)
                else:
                    for octet in body:
                        if stopped.wait(.025):
                            return
                        self.wfile.write(bytes([octet]))
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    yield 'http://127.0.0.1:%d' % httpd.server_port, requests_seen
    stopped.set()
    httpd.shutdown()
    httpd.server_close()
    worker.join(2)


@pytest.mark.parametrize('path', ['/headers', '/body', '/chunked'])
def test_absolute_deadline_interrupts_real_trickling_headers_body_and_chunk_framing(server, path):
    base, _ = server
    started = time.monotonic()
    deadline = started + .15
    with requests.Session() as session:
        session.trust_env = False
        with pytest.raises((TimeoutError, requests.RequestException, OSError)):
            response = request_with_safe_redirects(
                session.get, base + path, lambda _url: True,
                deadline=deadline, stream=True, timeout=2,
            )
            response_json(response, deadline=deadline)
    assert time.monotonic() - started < .6


def test_cancel_interrupts_real_trickling_headers_before_response_exists(server):
    base, _ = server
    started = time.monotonic()
    with requests.Session() as session:
        session.trust_env = False
        with pytest.raises((TimeoutError, requests.RequestException, OSError)):
            request_with_safe_redirects(
                session.get, base + '/headers', lambda _url: True,
                deadline=started + 3, cancelled=lambda: time.monotonic() - started > .1,
                stream=True, timeout=2,
            )
    assert time.monotonic() - started < .6


def test_shared_deadline_positive_real_get_preserves_explicit_headers_and_decodes_json(server):
    base, seen = server
    deadline = time.monotonic() + 2
    with requests.Session() as session:
        session.trust_env = False
        session.headers['X-Test-Session'] = 'session'
        response = request_with_safe_redirects(
            session.get, base + '/normal', lambda _url: True,
            headers={'X-Test-Request': 'request'}, deadline=deadline, stream=True, timeout=2,
        )
        assert response_json(response, deadline=deadline) == {'answer': 12345678901234567890}
    assert seen[0][1]['X-Test-Session'] == 'session'
    assert seen[0][1]['X-Test-Request'] == 'request'


def test_dns_validation_uses_the_existing_bounded_resolver_deadline(monkeypatch):
    from bobbi_core import http_policy
    release = Event()
    entered = Event()

    def stalled_dns(*_args):
        entered.set()
        release.wait(2)
        return []

    monkeypatch.setattr(http_policy.socket, 'getaddrinfo', stalled_dns)
    started = time.monotonic()
    try:
        with requests.Session() as session:
            with pytest.raises(TimeoutError):
                request_with_safe_redirects(
                    session.get, 'https://drip.invalid/manifest.json', is_safe_http_url,
                    deadline=started + .1, stream=True, timeout=2,
                )
        assert entered.is_set()
        assert time.monotonic() - started < .5
    finally:
        release.set()


def test_cross_origin_hop_does_not_reintroduce_session_auth_or_sensitive_headers(server):
    base, seen = server
    deadline = time.monotonic() + 2
    with requests.Session() as session:
        session.auth = ('alice', 'synthetic-password')
        session.headers.update({'Cookie': 'private=synthetic', 'X-Api-Key': 'synthetic-key'})
        response = request_with_safe_redirects(
            session.get, base + '/redirect', lambda _url: True,
            deadline=deadline, stream=True, timeout=2,
        )
        assert response_json(response, deadline=deadline)['answer'] == 12345678901234567890
    assert 'Authorization' in seen[0][1]
    assert len(seen) == 2
    for header in ('Authorization', 'Cookie', 'X-Api-Key'):
        assert header not in seen[1][1]


def test_request_adapter_retries_cannot_start_independent_budgets(server):
    base, seen = server
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    deadline = time.monotonic() + 2
    with requests.Session() as session:
        session.mount('http://', HTTPAdapter(max_retries=Retry(total=2, status_forcelist=[503])))
        response = request_with_safe_redirects(
            session.get, base + '/unavailable', lambda _url: True,
            deadline=deadline, stream=True, timeout=2,
        )
        assert response.status_code == 503
        response.close()
    assert len(seen) == 1
