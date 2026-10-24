"""TMDb artwork only: asynchronous Kodi image URLs + bounded local success cache.

No API key, cloud credential, arbitrary URL relay, or GUI-thread download.
The read-only image server is separate from authenticated player control.
"""
import hashlib
import hmac
from contextlib import contextmanager
from contextvars import ContextVar
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
from socketserver import ThreadingMixIn
import tempfile
from threading import BoundedSemaphore, Event, Lock, Thread
import time
from urllib.parse import urlsplit
from weakref import WeakSet

from bobbi_core.metadata_transport import fetch, MetadataError, MAX_BYTES

ART = re.compile(r'/t/p/(original|[wh][1-9][0-9]{1,3})/([A-Za-z0-9_-]{1,128}\.(?:jpg|jpeg|png|webp))')
CACHE_NAME = re.compile(r'[a-f0-9]{64}\.(?:jpg|jpeg|png|webp)')
MAX_CACHE = 128 * 1024 * 1024
MAX_FILES = 2048
_services = WeakSet()
_services_lock = Lock()
_presentation = ContextVar('bobbi_artwork_presentation', default=None)


@contextmanager
def image_batch():
    """Share one lazy endpoint snapshot during synchronous page/card projection.

    No HTTP, worker lifetime or cross-page cache belongs in this scope. Nested
    projections reuse it; exceptions release it. Explicit roots stay fresh.
    """
    if _presentation.get() is not None:
        yield
        return
    token = _presentation.set({})
    try:
        yield
    finally:
        _presentation.reset(token)


def _endpoint(root):
    try:
        if root is None:
            from bobbi_platform.paths import profile
            root = profile()
        config = _configuration(Path(root) / 'image-runtime.json')
        if config is not None:
            return 'http://127.0.0.1:{}/art/{}/'.format(config['port'], config['token'])
    except (OSError, ValueError, TypeError, ImportError):
        pass
    return None


def _presentation_endpoint(root):
    snapshot = _presentation.get() if root is None else None
    if snapshot is None:
        return _endpoint(root)
    if 'endpoint' not in snapshot:
        snapshot['endpoint'] = _endpoint(root)
    return snapshot['endpoint']


def visible_images_busy():
    """Same-host idle work yields to visible texture misses, without disk IPC."""
    with _services_lock:
        services = list(_services)
    return any(service.started and not service.closed and service.cache.busy() for service in services)


def _configuration(location):
    try:
        if location.is_symlink() or location.stat().st_size > 512:
            return None
        config = json.loads(location.read_text(encoding='utf-8'))
        if (set(config) == {'port', 'token'} and type(config['port']) is int
                and 1024 <= config['port'] <= 65535 and isinstance(config['token'], str)
                and re.fullmatch('[a-f0-9]{64}', config['token'])):
            return config
    except (OSError, ValueError, TypeError):
        pass
    return None


def image_path(value, size=None):
    if not isinstance(value, str) or not 1 <= len(value) <= 1024:
        raise ValueError('IMAGE_PATH')
    if value.startswith('/') and not value.startswith('//'):
        path = '/t/p/' + (size or 'original') + value
    else:
        parts = urlsplit(value)
        if (parts.scheme not in ('http', 'https') or parts.hostname != 'image.tmdb.org'
                or parts.port not in (None, 80, 443) or parts.username or parts.password
                or parts.query or parts.fragment):
            raise ValueError('IMAGE_ORIGIN')
        path = parts.path
        if size is not None and ART.fullmatch(path):
            path = '/t/p/' + size + '/' + path.rsplit('/', 1)[1]
    if not ART.fullmatch(path):
        raise ValueError('IMAGE_PATH')
    return path


def image_url(value, size=None, root=None):
    """Cheap presentation helper. Kodi's texture worker performs the GET later."""
    if not value:
        return ''
    if not isinstance(value, str):
        return value
    try:
        # Rebind old presentation-only local URLs when rendering stored resume
        # metadata. This permits only our exact public TMDb image path grammar.
        parsed = urlsplit(value)
        if (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                and not parsed.query and not parsed.fragment and not parsed.username
                and re.fullmatch(r'/art/[a-f0-9]{64}/(?:original|[wh][1-9][0-9]{1,3})/[A-Za-z0-9_-]{1,128}\.(?:jpg|jpeg|png|webp)', parsed.path)):
            value = 'https://image.tmdb.org/t/p/' + parsed.path.split('/', 3)[3]
        path = image_path(value, size)
    except (TypeError, ValueError):
        return value  # Non-TMDb artwork remains its existing independent source.
    original = 'https://image.tmdb.org' + path
    endpoint = _presentation_endpoint(root)
    return endpoint + path[5:] if endpoint else original


def media_type(raw):
    if raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'):
        return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and raw.endswith(b'IEND\xaeB`\x82'):
        return 'image/png'
    if (len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'
            and int.from_bytes(raw[4:8], 'little') + 8 == len(raw)):
        return 'image/webp'
    raise MetadataError('IMAGE_FORMAT')


class _Flight:
    """One transient result for existing subscribers, not another image cache."""
    def __init__(self):
        self.done, self.result = Event(), None


class ImageCache:
    def __init__(self, root, stopped=None, transport=fetch, report=lambda code: None,
                 max_bytes=MAX_CACHE, max_files=MAX_FILES):
        self.root, self.stopped = Path(root), stopped or Event()
        self.transport, self.report = transport, report
        self.max_bytes, self.max_files = max_bytes, max_files
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('IMAGE_CACHE_PATH')
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock, self.inflight, self.failures = Lock(), {}, {}
        # The Kodi owner calls busy(). Never hold its state lock across file IO.
        self.storage_lock = Lock()
        self.downloads = BoundedSemaphore(6)
        self.last_activity = 0

    def busy(self):
        with self.lock:
            return bool(self.inflight) or time.monotonic() - self.last_activity < 1

    def _file(self, path):
        return self.root / (hashlib.sha256(path.encode()).hexdigest() + '.' + path.rsplit('.', 1)[1])

    def _cached(self, target):
        try:
            if target.is_symlink() or not 0 < target.stat().st_size <= MAX_BYTES:
                return None
            raw = target.read_bytes()
            kind = media_type(raw)
        except (OSError, MetadataError):
            return None
        try:
            target.touch()
        except OSError:
            pass  # Valid bytes remain readable even on a read-only cache.
        return raw, kind

    def _guard(self, deadline):
        if self.stopped.is_set():
            raise MetadataError('CANCELLED')
        if time.monotonic() >= deadline:
            raise MetadataError('TIMEOUT')

    def get(self, path, deadline):
        if not ART.fullmatch(path):
            raise MetadataError('ORIGIN')
        self._guard(deadline)
        target = self._file(path)
        cached = self._cached(target)
        if cached:
            return cached
        with self.lock:
            if self.failures.get(path, 0) > time.monotonic():
                raise MetadataError('IMAGE_COOLDOWN')
            wait = self.inflight.get(path)
            owner = wait is None
            if owner:
                wait = self.inflight[path] = _Flight()
                self.last_activity = time.monotonic()
        if not owner:
            while not wait.done.wait(.05):
                self._guard(deadline)
            self._guard(deadline)
            if wait.result is not None:
                return wait.result
            cached = self._cached(target)
            if cached:
                return cached
            raise MetadataError('IMAGE_UNAVAILABLE')
        downloading = False
        try:
            while not self.downloads.acquire(timeout=.05):
                self._guard(deadline)
            downloading = True
            self._guard(deadline)
            result = self.transport('https://image.tmdb.org' + path, deadline, self.stopped.is_set)
            self._guard(deadline)
            if result['status'] != 200:
                raise MetadataError('HTTP_' + str(result['status']))
            raw = result['body']
            if not isinstance(raw, bytes) or not 0 < len(raw) <= min(MAX_BYTES, self.max_bytes):
                raise MetadataError('LIMIT')
            kind = media_type(raw)
            try:
                self._store(target, raw, deadline)
            except OSError:
                # Persistence is optional; do not turn a valid network image
                # into a 503 or poison its network failure cooldown.
                self.report('IMAGE_CACHE_IO')
            self._guard(deadline)
            with self.lock:
                self.failures.pop(path, None)
                wait.result = (raw, kind)
            return wait.result
        except (OSError, ValueError, RuntimeError) as error:
            with self.lock:
                if len(self.failures) >= 512:
                    self.failures.pop(next(iter(self.failures)))
                self.failures[path] = time.monotonic() + 30
            self.report('IMAGE_' + getattr(error, 'stage', 'IO'))
            raise
        finally:
            if downloading:
                self.downloads.release()
            with self.lock:
                self.inflight.pop(path, None)
                self.last_activity = time.monotonic()
                wait.done.set()

    def _store(self, target, raw, deadline):
        temporary, acquired = None, False
        try:
            fd, temporary = tempfile.mkstemp(dir=str(self.root), prefix='.image-')
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            while not self.storage_lock.acquire(timeout=.05):
                self._guard(deadline)
            acquired = True
            self._guard(deadline)
            # Make room before publication: a failed eviction must not admit
            # another persistent file above quota. Only rebuildable art moves.
            self._prune(target, deadline, len(raw))
            self._guard(deadline)
            os.replace(temporary, target)
            temporary = None
        finally:
            if acquired:
                self.storage_lock.release()
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass  # Never delete unknown paths to compensate for IO failure.

    def _prune(self, preserve, deadline, incoming_bytes):
        files = []
        with os.scandir(self.root) as entries:
            for entry in entries:
                self._guard(deadline)
                item = Path(entry.path)
                if (item != preserve and CACHE_NAME.fullmatch(entry.name)
                        and entry.is_file(follow_symlinks=False)):
                    info = entry.stat(follow_symlinks=False)
                    files.append((info.st_mtime, item, info.st_size))
        total, count = incoming_bytes+sum(row[2] for row in files), len(files)+1
        for _, item, size in sorted(files):
            if total <= self.max_bytes and count <= self.max_files:
                break
            self._guard(deadline)
            item.unlink(missing_ok=True)
            total, count = total-size, count-1


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = os.name != 'nt'
    request_queue_size = 32
    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()
    def process_request(self, request, address):
        if not self.slots.acquire(False):
            # Bounded HTTP admission is distinct from expensive upstream IO.
            # Never silently reset a cached texture's connection at slot five.
            try:
                request.settimeout(.1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nRetry-After: 1\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            finally:
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


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def setup(self):
        super().setup()
        self.connection.settimeout(12)
    def do_GET(self):
        self._respond(False)
    def do_HEAD(self):
        self._respond(True)
    def _respond(self, head):
        prefix = '/art/' + self.server.token + '/'
        if (self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port)
                or len(self.path) > 512 or not hmac.compare_digest(self.path[:len(prefix)], prefix)):
            self.send_error(403)
            return
        path = '/t/p/' + self.path[len(prefix):]
        try:
            raw, kind = self.server.cache.get(path, time.monotonic()+10)
        except (OSError, ValueError, RuntimeError):
            self.send_response(503)
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Retry-After', '1')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'private, max-age=86400')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        if not head:
            self.wfile.write(raw)


class ImageService:
    def __init__(self, root, report=lambda code:None, transport=fetch):
        self.root, self.stop = Path(root), Event()
        self.path = self.root / 'image-runtime.json'
        self.endpoint = self.root / 'image-endpoint.json'
        self.cache = ImageCache(self.root / 'images', self.stop, transport, report)
        if self.endpoint.is_symlink():
            raise ValueError('IMAGE_ENDPOINT_PATH')
        config = _configuration(self.endpoint) or _configuration(self.path)
        # Public read-only artwork keeps a stable endpoint across ordinary host
        # restarts; account/control capabilities still have separate lifetimes.
        try:
            self.server = _Server(('127.0.0.1', config['port'] if config else 0), _Handler)
        except OSError:
            self.server = _Server(('127.0.0.1', 0), _Handler)
            report('IMAGE_ENDPOINT_RELOCATED')
        self.server.token = config['token'] if config else secrets.token_hex(32)
        self.server.cache, self.server.slots = self.cache, BoundedSemaphore(32)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval':.1}, daemon=True)
        self.started, self.closed = False, False
        with _services_lock:
            _services.add(self)
    def start(self):
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(dir=str(self.root), prefix='.image-runtime-')
            with os.fdopen(fd, 'w') as stream:
                json.dump(dict(port=self.server.server_port, token=self.server.token), stream)
                stream.flush()
                os.fsync(stream.fileno())
            self.thread.start()
            self.started = True
            os.replace(temporary, self.path)
            fd, temporary = tempfile.mkstemp(dir=str(self.root), prefix='.image-endpoint-')
            with os.fdopen(fd, 'wb') as stream:
                stream.write(self.path.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.endpoint)
        except BaseException:
            self.close()
            raise
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    def close(self):
        if self.closed:
            return
        self.stop.set()
        if self.started:
            self.server.shutdown()
        self.server.server_close()
        if self.started:
            self.thread.join()
        try:
            config = json.loads(self.path.read_text())
            if config.get('token') == self.server.token and config.get('port') == self.server.server_port:
                self.path.unlink()
        except (OSError, ValueError, KeyError):
            pass
        self.closed = True
        with _services_lock:
            _services.discard(self)
