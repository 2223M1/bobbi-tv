"""Device-local service control, authenticated and independent of native IPC."""
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
from socketserver import ThreadingMixIn
import tempfile
from threading import BoundedSemaphore, Thread
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .paths import profile


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Local service redirect rejected')


def call(action, body, timeout=3):
    path = profile(name='runtime.json')
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4096:
        raise OSError('bobbi runtime is not ready')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (set(data) != {'port', 'token'} or type(data['port']) is not int or not 1024 <= data['port'] <= 65535
            or not isinstance(data['token'], str) or len(data['token']) != 64):
        raise ValueError('Invalid local runtime configuration')
    raw = json.dumps({'action': action, 'body': body}).encode()
    if len(raw) > 16384:
        raise ValueError('Local request too large')
    request = Request('http://127.0.0.1:%d/control' % data['port'], data=raw,
        headers={'Authorization': 'Bearer ' + data['token'], 'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        reply = response.read(16385)
    if len(reply) > 16384:
        raise ValueError('Local reply too large')
    result = json.loads(reply)
    if result.get('ok') is not True:
        if result.get('error') == 'unavailable':
            raise OSError('Local service temporarily unavailable')
        raise ValueError('Local service rejected request')
    return result['result']


class Server(ThreadingMixIn, HTTPServer):
    # A disabled addon is not quiescent until its admitted requests finish.
    # Socket reads and dispatch IO already have finite deadlines. The installer
    # keeps its own bounded wait and refuses replacement while this lease lives.
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, *args):
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def do_POST(self):
        if self.path != '/control' or not hmac.compare_digest(
                self.headers.get('Authorization', ''), 'Bearer ' + self.server.token):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict) or set(request) != {'action', 'body'}:
                raise ValueError
            response = {'ok': True, 'result': self.server.dispatch(request['action'], request['body'])}
        except OSError:
            # Fixed category only. Preserve unavailable vs explicit rejection
            # so read-only callers may retry; never send exception text/URLs.
            response = {'ok': False, 'error': 'unavailable'}
        except Exception:
            response = {'ok': False}
        try:
            raw = json.dumps(response).encode()
            if len(raw) > 16384:
                raise ValueError('Reply too large')
        except (ValueError, TypeError):
            raw = b'{"ok":false}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)


class Runtime:
    def __init__(self, dispatch, path=None):
        from .instance_lock import InstanceLock
        self.path = Path(path) if path else profile(name='runtime.json')
        self.lease = InstanceLock(str(self.path) + '.lock')
        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.token = secrets.token_hex(32)
        self.server.dispatch, self.server.slots = dispatch, BoundedSemaphore(4)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.started = False
        self.closed = False

    def start(self, prepare=None):
        if self.started or self.closed:
            raise RuntimeError('Runtime is not restartable')
        self.lease.acquire()
        name = None
        try:
            if prepare is not None:
                prepare()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=str(self.path.parent), prefix='.runtime-')
            with os.fdopen(fd, 'w') as stream:
                json.dump({'port': self.server.server_port, 'token': self.server.token}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            self.thread.start()
            self.started = True
            os.replace(name, self.path)
        except BaseException:
            self.close()
            raise
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def close(self, release_lease=True):
        if self.closed:
            return
        def report(code):
            try:
                getattr(self, 'report', lambda value: None)(code)
            except Exception:
                pass  # Never skip a drain because optional logging failed.
        if self.started:
            report('RUNTIME_CLOSE_SHUTDOWN_BEGIN')
            self.server.shutdown()
            report('RUNTIME_CLOSE_SHUTDOWN_END')
        report('RUNTIME_CLOSE_REQUEST_DRAIN_BEGIN')
        self.server.server_close()
        report('RUNTIME_CLOSE_REQUEST_DRAIN_END')
        if self.started:
            self.thread.join()
        report('RUNTIME_CLOSE_LOOP_JOINED')
        # A newer service instance must not lose its own registration.
        try:
            if json.loads(self.path.read_text())['token'] == self.server.token:
                self.path.unlink()
        except (OSError, ValueError, KeyError):
            pass
        if release_lease:
            self.lease.close()
        self.closed = True
