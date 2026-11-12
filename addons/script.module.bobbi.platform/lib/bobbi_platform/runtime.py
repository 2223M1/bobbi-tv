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

MAX_MESSAGE_BYTES = 16384
LOGIN_ERROR_PHASES = frozenset(('qr', 'confirm', 'exchange', 'identity'))
LOGIN_ERROR_ACTIONS = frozenset(('pan_login_begin', 'pan_login_poll'))
CATALOG_ERRORS = frozenset(('CATALOG_ACCOUNT_MISMATCH', 'CATALOG_ACTION_INVALID', 'CATALOG_SCAN_BUSY',
    'CATALOG_SERVICE_CLOSED', 'CATALOG_PAGE_INVALID', 'CATALOG_REVIEW_STATE', 'CATALOG_TASK_NOT_FOUND',
    'CATALOG_FILE_NOT_FOUND', 'CATALOG_TASK_STATE', 'CATALOG_TASK_TERMINAL', 'CATALOG_BATCH_LIMIT',
    'CATALOG_ID_INVALID', 'CATALOG_MAPPING_INVALID', 'CATALOG_REVIEW_INVALID', 'CATALOG_METADATA_INVALID',
    'CATALOG_SCHEMA_UNSUPPORTED', 'CATALOG_STORAGE_UNSAFE', 'CATALOG_REPLY_LIMIT',
    'CATALOG_QUERY_INVALID', 'CATALOG_CURSOR_STALE', 'CATALOG_RECHECK_INCOMPLETE',
    'CATALOG_SOURCE_UNAVAILABLE', 'CATALOG_REQUEST_REUSED', 'CATALOG_GROUP_AMBIGUOUS',
    'CATALOG_REFERENCE_INVALID', 'CATALOG_SOURCE_UNSUPPORTED', 'CATALOG_AUTHORITY_CHANGED',
    'CATALOG_FILE_CHANGED', 'CATALOG_SELECTION_CANCELLED', 'CATALOG_PLAY_EXPIRED'))


def encode_message(value):
    """The wire budget counts UTF-8 bytes, not characters or ASCII escapes."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Local service redirect rejected')


class ServiceRejected(ValueError):
    """A fixed local category, never exception text from a remote service."""
    code = 'SELECTION_UNVERIFIED'


def _registration(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4096:
        raise OSError('bobbi runtime is not ready')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (set(data) != {'port', 'token'} or type(data['port']) is not int or not 1024 <= data['port'] <= 65535
            or not isinstance(data['token'], str) or len(data['token']) != 64):
        raise ValueError('Invalid local runtime configuration')
    return data


def bind_call(path):
    """Bind an existing session to one runtime, never to a later profile/host."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Absolute runtime path required')
    token = _registration(path)['token']
    revoked = False
    def bound(action, body, timeout=3):
        nonlocal revoked
        if revoked:
            raise OSError('RUNTIME_INSTANCE_CHANGED')
        try:
            return call(action, body, timeout=timeout, path=path, expected_token=token)
        except OSError as error:
            if str(error) == 'RUNTIME_INSTANCE_CHANGED':
                revoked = True
            raise
    return bound


def _bound_registration(path, token):
    try:
        data = _registration(path)
        if not hmac.compare_digest(data['token'].encode('utf-8'), token.encode('utf-8')):
            raise ValueError('changed')
        return data
    except (OSError, ValueError, TypeError, KeyError):
        raise OSError('RUNTIME_INSTANCE_CHANGED') from None


def call(action, body, timeout=3, *, path=None, expected_token=None):
    if (path is None) != (expected_token is None):
        raise ValueError('Runtime binding requires path and token')
    if path is None:
        path = profile(name='runtime.json')
    elif (not Path(path).is_absolute() or type(expected_token) is not str
            or len(expected_token) != 64):
        raise ValueError('Invalid runtime binding')
    data = (_bound_registration(path, expected_token) if expected_token is not None
            else _registration(path))
    raw = encode_message({'action': action, 'body': body})
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError('Local request too large')
    request = Request('http://127.0.0.1:%d/control' % data['port'], data=raw,
        headers={'Authorization': 'Bearer ' + data['token'], 'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        reply = response.read(MAX_MESSAGE_BYTES + 1)
    if expected_token is not None:
        _bound_registration(path, expected_token)
    if len(reply) > MAX_MESSAGE_BYTES:
        raise ValueError('Local reply too large')
    result = json.loads(reply)
    if result.get('ok') is not True:
        if result.get('error') == 'pan':
            from .pan_accounts import PanError, PUBLIC_ERRORS
            if (isinstance(action, str) and action.startswith(('pan_', 'catalog_'))
                    and type(result.get('code')) is str and result['code'] in PUBLIC_ERRORS):
                error = PanError(result['code'])
                phase = result.get('phase')
                if action in LOGIN_ERROR_ACTIONS and type(phase) is str and phase in LOGIN_ERROR_PHASES:
                    error.login_phase = phase
                raise error
        if (result.get('error') == 'catalog' and isinstance(action, str) and action.startswith('catalog_')
                and type(result.get('code')) is str and result['code'] in CATALOG_ERRORS):
            raise ValueError(result['code'])
        if result.get('error') == 'unavailable':
            raise OSError('Local service temporarily unavailable')
        if result.get('error') == 'selection_unverified':
            raise ServiceRejected('Selected file is not eligible for automatic preparation')
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
        request = None
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_MESSAGE_BYTES:
                raise ValueError
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict) or set(request) != {'action', 'body'}:
                raise ValueError
            response = {'ok': True, 'result': self.server.dispatch(request['action'], request['body'])}
        except OSError:
            # Fixed category only. Preserve unavailable vs explicit rejection
            # so read-only callers may retry; never send exception text/URLs.
            response = {'ok': False, 'error': 'unavailable'}
        except Exception as error:
            response = {'ok': False}
            from .pan_accounts import PanError, PUBLIC_ERRORS
            if (isinstance(error, PanError) and str(error) in PUBLIC_ERRORS
                    and type(request) is dict and isinstance(request.get('action'), str)
                    and request['action'].startswith(('pan_', 'catalog_'))):
                response.update(error='pan', code=str(error))
                phase = getattr(error, 'login_phase', None)
                if (request['action'] in LOGIN_ERROR_ACTIONS
                        and type(phase) is str and phase in LOGIN_ERROR_PHASES):
                    response['phase'] = phase
            if (isinstance(error, ValueError) and str(error) in CATALOG_ERRORS and type(request) is dict
                    and isinstance(request.get('action'), str) and request['action'].startswith('catalog_')):
                response.update(error='catalog', code=str(error))
            if isinstance(error, ValueError) and str(error) == 'PREPARATION_CURRENT_VERIFIED_SELECTION_REQUIRED':
                response['error'] = 'selection_unverified'
        try:
            raw = encode_message(response)
            if len(raw) > MAX_MESSAGE_BYTES:
                raise ValueError('Reply too large')
        except (ValueError, TypeError):
            raw = b'{"ok":false,"error":"message_too_large"}'
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
