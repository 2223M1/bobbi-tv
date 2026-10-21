"""TMDb artwork only: asynchronous Kodi image URLs + bounded local success cache.

No API key, cloud credential, arbitrary URL relay, or GUI-thread download.
The read-only image server is separate from authenticated player control.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
from socketserver import ThreadingMixIn
import tempfile
from threading import BoundedSemaphore, Event, Lock, Thread
import time
from urllib.parse import urlsplit

from bobbi_core.metadata_transport import fetch, MetadataError, MAX_BYTES

ART = re.compile(r'/t/p/(original|[wh][1-9][0-9]{1,3})/([A-Za-z0-9_-]{1,128}\.(?:jpg|jpeg|png|webp))')
CACHE_NAME = re.compile(r'[a-f0-9]{64}\.(?:jpg|jpeg|png|webp)')
MAX_CACHE = 128 * 1024 * 1024
MAX_FILES = 2048


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
    try:
        path = image_path(value, size)
    except (TypeError, ValueError):
        return value  # Non-TMDb artwork remains its existing independent source.
    original = 'https://image.tmdb.org' + path
    try:
        if root is None:
            from bobbi_platform.paths import profile
            root = profile()
        location = Path(root) / 'image-runtime.json'
        if location.is_symlink() or location.stat().st_size > 512:
            return original
        config = json.loads(location.read_text(encoding='utf-8'))
        if (set(config) != {'port', 'token'} or type(config['port']) is not int
                or not 1024 <= config['port'] <= 65535
                or not isinstance(config['token'], str) or not re.fullmatch('[a-f0-9]{64}', config['token'])):
            return original
        return 'http://127.0.0.1:{}/art/{}/{}'.format(config['port'], config['token'], path[5:])
    except (OSError, ValueError, TypeError, ImportError):
        return original


def media_type(raw):
    if raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'):
        return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and raw.endswith(b'IEND\xaeB`\x82'):
        return 'image/png'
    if (len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'
            and int.from_bytes(raw[4:8], 'little') + 8 == len(raw)):
        return 'image/webp'
    raise MetadataError('IMAGE_FORMAT')


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

    def _file(self, path):
        return self.root / (hashlib.sha256(path.encode()).hexdigest() + '.' + path.rsplit('.', 1)[1])

    def _cached(self, target):
        try:
            if target.is_symlink() or not 0 < target.stat().st_size <= MAX_BYTES:
                return None
            raw = target.read_bytes()
            kind = media_type(raw)
            target.touch()
            return raw, kind
        except (OSError, MetadataError):
            return None

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
                wait = self.inflight[path] = Event()
        if not owner:
            while not wait.wait(.05):
                self._guard(deadline)
            self._guard(deadline)
            cached = self._cached(target)
            if cached:
                return cached
            raise MetadataError('IMAGE_UNAVAILABLE')
        temporary = None
        try:
            result = self.transport('https://image.tmdb.org' + path, deadline, self.stopped.is_set)
            self._guard(deadline)
            if result['status'] != 200:
                raise MetadataError('HTTP_' + str(result['status']))
            raw = result['body']
            if not isinstance(raw, bytes) or not 0 < len(raw) <= min(MAX_BYTES, self.max_bytes):
                raise MetadataError('LIMIT')
            kind = media_type(raw)
            fd, temporary = tempfile.mkstemp(dir=str(self.root), prefix='.image-')
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._guard(deadline)
            with self.lock:
                os.replace(temporary, target)
                temporary = None
                self._prune(target)
                self.failures.pop(path, None)
            return raw, kind
        except (OSError, ValueError, RuntimeError) as error:
            with self.lock:
                if len(self.failures) >= 512:
                    self.failures.pop(next(iter(self.failures)))
                self.failures[path] = time.monotonic() + 30
            self.report('IMAGE_' + getattr(error, 'stage', 'IO'))
            raise
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            with self.lock:
                self.inflight.pop(path, None)
                wait.set()

    def _prune(self, preserve):
        files = []
        for item in self.root.iterdir():
            if CACHE_NAME.fullmatch(item.name) and not item.is_symlink() and item.is_file():
                info = item.stat()
                files.append((info.st_mtime, item, info.st_size))
        total, count = sum(row[2] for row in files), len(files)
        for _, item, size in sorted(files):
            if total <= self.max_bytes and count <= self.max_files:
                break
            if item != preserve:
                item.unlink(missing_ok=True)
                total, count = total-size, count-1


class _Server(ThreadingMixIn, HTTPServer):
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
        self.cache = ImageCache(self.root / 'images', self.stop, transport, report)
        self.server = _Server(('127.0.0.1', 0), _Handler)
        self.server.token, self.server.cache, self.server.slots = secrets.token_hex(32), self.cache, BoundedSemaphore(4)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval':.1}, daemon=True)
        self.started, self.closed = False, False
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
            if json.loads(self.path.read_text())['token'] == self.server.token:
                self.path.unlink()
        except (OSError, ValueError, KeyError):
            pass
        self.closed = True
