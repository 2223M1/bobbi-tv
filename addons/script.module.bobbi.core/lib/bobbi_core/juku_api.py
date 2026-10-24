"""Authorised catalogue-only client; no daemon, pan account or player.

Protocol independently implemented from version 0.80 auth/proxy disassembly.
Each installation generates its OWN P-256 key. No bundled key or other app's
session is imported. TLS verification and the remote's access checks stay on.
"""
import base64
from contextlib import contextmanager
from datetime import datetime
import errno
import hashlib
import http.client
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import ssl
import socket
import sys
import sysconfig
import time
from threading import Event, Lock, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

BASE = ''  # No upstream endpoint is supplied by the public application.
STATE = None  # Resolved lazily from the active Kodi profile, never the author's host.
APP_VERSION = '1.0.0'  # Wire protocol version found in 0.80, not Bobi's version.
MAX_JSON = 8 * 1024 * 1024
MAX_SNAPSHOT_JSON = 64 * 1024 * 1024
MAX_STATE_JSON = 64 * 1024
AUTH_RETRY_SECONDS = 30
# 0.80 cfdialer.DefaultCloudflareIPs, reduced to two bounded alternatives.
# These are transport destinations, never replacements for TLS hostname checks.
EDGES = ('162.159.153.1', '172.64.150.1')
PATH = re.compile(r'^/(?:videos/search|videos/[0-9]+(?:/cloud-files)?|shared-libraries/public|shared-libraries/(?:preview|detail)/[A-Za-z0-9_-]+)$')
_CRYPTO_LOAD_LOCK = Lock()
_CRYPTO_NAMESPACE = None


class JukuError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def state_path(state=None):
    if state is not None:
        return Path(state)
    from bobbi_platform.paths import profile
    return profile('plugin.video.bobbi', 'juku')


def guard(deadline, cancelled=lambda: False):
    if cancelled():
        raise JukuError('CANCELLED')
    if time.monotonic() >= deadline:
        raise JukuError('DEADLINE')


def canonical_query(params):
    if params is not None and (not isinstance(params, dict) or any(
            not isinstance(k, str) or not isinstance(v, (str, int, float))
            or isinstance(v, bool) or (isinstance(v, float) and not math.isfinite(v))
            for k, v in params.items())):
        raise JukuError('QUERY_SCHEMA')
    # 0.80 EscapeQueryParam explicitly uses RFC3986 escapes, not QueryEscape's '+'.
    return '&'.join(quote(str(k), safe='-._~') + '=' + quote(str(v), safe='-._~')
                    for k, v in sorted((params or {}).items()))


def signing_string(method, path, query, body, timestamp, nonce, device, token):
    return '\n'.join((method.upper(), path, query, hashlib.sha256(body).hexdigest(),
                      timestamp, nonce, device, token)).encode('utf-8')


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            os.chmod(str(temporary), 0o600)
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_STATE_JSON + 1)
    except FileNotFoundError:
        return {}
    except OSError:
        raise JukuError('STATE_IO') from None
    try:
        if len(raw) > MAX_STATE_JSON:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        # A corrupt saved identity is not permission to create another device.
        raise JukuError('STATE_SCHEMA') from None


@contextmanager
def state_lock(root, deadline, cancelled):
    """Cross-process lease using OS locks; a killed owner cannot strand a lock."""
    root.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        os.chmod(str(root), 0o700)
    with (root / 'auth.lock').open('a+b') as stream:
        if os.name != 'nt':
            os.chmod(str(root / 'auth.lock'), 0o600)
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            if not stream.read(1):
                stream.write(b'0')
                stream.flush()
            def acquire():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        while True:
            guard(deadline, cancelled)
            try:
                acquire()
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                    raise JukuError('STATE_LOCK') from None
                time.sleep(min(.05, max(0, deadline-time.monotonic())))
        try:
            yield
        finally:
            release()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Signed headers and tokens must never follow a redirect to another host.
        raise JukuError('REDIRECT')


class EdgeConnection(http.client.HTTPSConnection):
    """IP transport with original TLS hostname and an absolute socket deadline.

    Socket timeouts alone are inactivity limits: slow header/body trickles can
    otherwise run forever. The one request watcher only shuts down this socket;
    response.close/connection.close always stops it. It never touches playback.
    """
    def __init__(self, host, edge_ip, deadline, cancelled, **kwargs):
        super().__init__(host, **kwargs)
        self.edge_ip = edge_ip
        self.deadline, self.cancelled = deadline, cancelled
        self._watch_stop = Event()
        self._watch_socket = None

    def _watch(self):
        while not self._watch_stop.wait(.05):
            if self.cancelled() or time.monotonic() >= self.deadline:
                target = self._watch_socket
                if target is not None:
                    try:
                        target.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return

    def connect(self):
        server_name = self._tunnel_host or self.host
        if not BASE or server_name != urlsplit(BASE).hostname or (self.edge_ip and (self.port != 443 or self._tunnel_host)):
            raise JukuError('EDGE_HOST')
        # With no edge this is the explicitly configured numeric loopback proxy.
        if not self.edge_ip and self.host != '127.0.0.1':
            raise JukuError('LOCAL_PROXY_REQUIRED')
        guard(self.deadline, self.cancelled)
        destination = (self.edge_ip, 443) if self.edge_ip else (self.host, self.port)
        raw = socket.create_connection(destination, min(3, self.timeout, self.deadline-time.monotonic()))
        self.sock = self._watch_socket = raw
        Thread(target=self._watch, name='JukuRequestDeadline', daemon=True).start()
        try:
            if self._tunnel_host:
                self._tunnel()
            guard(self.deadline, self.cancelled)
            raw.settimeout(max(.001, min(3, self.deadline-time.monotonic())))
            self.sock = self._watch_socket = self._context.wrap_socket(raw, server_hostname=server_name)
            self.sock.settimeout(max(.001, self.deadline-time.monotonic()))
            guard(self.deadline, self.cancelled)
        except BaseException:
            self.close()
            raise

    def getresponse(self):
        self._receiving_response = True
        try:
            response = super().getresponse()
        except BaseException:
            self._watch_stop.set()
            raise
        finally:
            self._receiving_response = False
        original_close = response.close
        def close():
            self._watch_stop.set()
            original_close()
        response.close = close
        return response

    def close(self):
        # HTTPConnection closes its own socket reference for Connection: close
        # before the response body is consumed. The response's file still owns
        # the fd: retain its deadline until response.close, not merely headers.
        if not getattr(self, '_receiving_response', False):
            self._watch_stop.set()
        super().close()


class EdgeHTTPSHandler(HTTPSHandler):
    def __init__(self, edge_ip, context):
        super().__init__(context=context)
        self.edge_ip = edge_ip

    def https_open(self, request):
        def connection(host, **kwargs):
            return EdgeConnection(host, self.edge_ip, request.juku_deadline,
                                  request.juku_cancelled, **kwargs)
        return self.do_open(connection, request, context=self._context)


def expires(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.timestamp() if parsed.tzinfo is not None else 0
        except (ValueError, OverflowError, OSError):
            return 0
    return 0


def checked_session(value, device=None, fresh=False):
    limits = {'deviceId': 256, 'accessToken': 16384, 'refreshToken': 16384}
    if not isinstance(value, dict) or any(
            not isinstance(value.get(name), str) or not 1 <= len(value[name]) <= limit
            or any(ord(char) < 33 or ord(char) > 126 for char in value[name])
            for name, limit in limits.items()):
        raise JukuError('AUTH_SCHEMA')
    access, refresh = expires(value.get('accessExpiresAt')), expires(value.get('refreshExpiresAt'))
    if (access <= 0 or refresh <= 0 or (device is not None and value['deviceId'] != device)
            or (fresh and (access <= time.time()+1 or refresh <= time.time()+1))):
        raise JukuError('AUTH_SCHEMA')
    return {name: value[name] for name in (*limits, 'accessExpiresAt', 'refreshExpiresAt')}


def _load_crypto_module(namespace, suffix):
    """Expose only this exact platform package, never widen all site-packages."""
    requested = namespace + '.' + suffix
    try:
        return importlib.import_module(requested)
    except ImportError:
        if namespace in sys.modules:
            raise JukuError('CRYPTO_UNAVAILABLE') from None
    for location in dict.fromkeys((sysconfig.get_path('purelib'), sysconfig.get_path('platlib'))):
        if not location:
            continue
        package = Path(location) / namespace
        for filename in ('__init__.py', '__init__.pyc'):
            entry = package / filename
            if not entry.is_file():
                continue
            module = None
            try:
                spec = importlib.util.spec_from_file_location(namespace, entry,
                    submodule_search_locations=[str(package)])
                module = importlib.util.module_from_spec(spec)
                sys.modules[namespace] = module
                spec.loader.exec_module(module)
                return importlib.import_module(requested)
            except (ImportError, OSError, ValueError):
                if sys.modules.get(namespace) is module:
                    del sys.modules[namespace]
                raise JukuError('CRYPTO_UNAVAILABLE') from None
    raise JukuError('CRYPTO_UNAVAILABLE')


def _probe_crypto_namespace(namespace):
    """One in-memory P-256 probe detects incompatible CE namespace aliases.

    Some CE packages expose Cryptodome.ECC but their Cryptodome.DSS expects a
    Crypto.EccKey. Import success alone is therefore insufficient. This key is
    ephemeral, never an installation identity and never written or sent.
    """
    ECC = _load_crypto_module(namespace, 'PublicKey.ECC')
    DSS = _load_crypto_module(namespace, 'Signature.DSS')
    SHA256 = _load_crypto_module(namespace, 'Hash.SHA256')
    key = ECC.generate(curve='P-256')
    digest = SHA256.new(b'bobbi-juku-p256-capability-v1')
    signature = DSS.new(key, 'fips-186-3', encoding='binary').sign(digest)
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise ValueError('Unsupported P-256 signature encoding')
    DSS.new(key.public_key(), 'fips-186-3', encoding='binary').verify(digest, signature)


def crypto_module(name):
    """Select one usable namespace once; never mix objects across namespaces."""
    global _CRYPTO_NAMESPACE
    if not isinstance(name, str) or not name.startswith(('Crypto.', 'Cryptodome.')):
        raise JukuError('CRYPTO_UNAVAILABLE')
    suffix = name.split('.', 1)[1]
    with _CRYPTO_LOAD_LOCK:
        if _CRYPTO_NAMESPACE is None:
            for namespace in ('Cryptodome', 'Crypto'):
                try:
                    _probe_crypto_namespace(namespace)
                except (ImportError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
                    continue
                _CRYPTO_NAMESPACE = namespace
                break
            if _CRYPTO_NAMESPACE is None:
                raise JukuError('CRYPTO_UNAVAILABLE')
        try:
            return _load_crypto_module(_CRYPTO_NAMESPACE, suffix)
        except (ImportError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
            # A later missing module cannot switch the namespace after callers
            # already hold a key from the selected suite.
            raise JukuError('CRYPTO_UNAVAILABLE') from None


def sign_payload(key, payload):
    SHA256 = crypto_module('Crypto.Hash.SHA256')
    DSS = crypto_module('Crypto.Signature.DSS')
    return DSS.new(key, 'fips-186-3', encoding='binary').sign(SHA256.new(payload))


class Client:
    def __init__(self, state=STATE, cancelled=lambda: False, opener=None, proxy=None, edge_ip=None):
        # Fail before configuration, keys, sessions or transport are touched.
        # Retained protocol tests inject an offline fixture endpoint explicitly.
        if not BASE:
            raise JukuError('CATALOGUE_DISABLED')
        self.root = state_path(state)
        self.cancelled = cancelled
        config = load_json(self.root / 'config.json')
        if proxy is None:
            proxy = config.get('proxy', '')
        if edge_ip is None:
            edge_ip = config.get('edge_ip', '')
        if (not isinstance(proxy, str) or (proxy and (
                not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', proxy)
                or not 1 <= int(proxy.rsplit(':', 1)[1]) <= 65535))):
            raise JukuError('LOCAL_PROXY_REQUIRED')
        if not isinstance(edge_ip, str) or (edge_ip and (edge_ip not in EDGES or proxy)):
            raise JukuError('EDGE_CONFIG')
        # Fixed, observed 0.80 edge candidates avoid an unbounded DNS resolver
        # and retain the endpoint host for Host/SNI/certificate validation. Never
        # bypass an explicitly selected local proxy on fallback.
        edges = (None,) if proxy else tuple(dict.fromkeys((edge_ip or EDGES[0], *EDGES)))[:2]
        self.openers = [opener] if opener is not None else [
            build_opener(ProxyHandler({'https': proxy} if proxy else {}), NoRedirect(),
                         EdgeHTTPSHandler(edge, ssl.create_default_context())) for edge in edges]
        self.opener = self.openers[0]  # Kept for callers inspecting the first transport.
        self.requests = 0

    def _key(self):
        ECC = crypto_module('Crypto.PublicKey.ECC')
        path = self.root / 'device.pem'
        if path.exists():
            try:
                raw = path.read_bytes()
                if len(raw) > 8192:
                    raise ValueError()
                key = ECC.import_key(raw)
                if not key.has_private() or key.curve not in ('NIST P-256', 'P-256'):
                    raise ValueError()
                return key
            except (ValueError, TypeError, OSError):
                raise JukuError('AUTH_KEY_INVALID') from None
        if (self.root / 'session.json').exists():
            raise JukuError('AUTH_KEY_MISSING')
        key = ECC.generate(curve='P-256')
        # Caller holds the cross-process state lock.
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write(key.export_key(format='PEM'))
            stream.flush()
            os.fsync(stream.fileno())
        return key

    def _request(self, method, path, params, body, session, key, deadline, max_bytes=MAX_JSON, destination=None):
        guard(deadline, self.cancelled)
        query = canonical_query(params)
        if len(query.encode()) > 8192:
            raise JukuError('QUERY_LIMIT')
        for index, opener in enumerate(self.openers):
            guard(deadline, self.cancelled)
            # Connect/TLS attempts have their own short bound. Once receiving,
            # use the caller's absolute budget; never discard a healthy large
            # body merely to reserve half the time for an unused second edge.
            attempt_deadline = deadline
            headers = {'Accept': 'application/json', 'Content-Type': 'application/json',
                       'Accept-Encoding': 'identity', 'User-Agent': 'BobiTV-JukuCatalog/0.1 (authorised integration)'}
            if session is not None:
                stamp, nonce = str(int(time.time()*1000)), secrets.token_hex(16)
                device, token = session['deviceId'], session['accessToken']
                payload = signing_string(method, path, query, body, stamp, nonce, device, token)
                signature = sign_payload(key, payload)
                headers.update({'X-Device-Id': device, 'X-App-Version': APP_VERSION,
                                'X-Timestamp': stamp, 'X-Nonce': nonce,
                                'X-Body-Hash': hashlib.sha256(body).hexdigest(),
                                'X-Access-Token': token,
                                'X-Signature': base64.b64encode(signature).decode('ascii')})
            request = Request(BASE + path + ('?' + query if query else ''),
                              data=body if method == 'POST' else None, headers=headers, method=method)
            request.juku_deadline, request.juku_cancelled = attempt_deadline, self.cancelled
            self.requests += 1
            try:
                if destination is not None:
                    return self._receive(opener, request, attempt_deadline, max_bytes, destination)
                return self._receive(opener, request, attempt_deadline, max_bytes)
            except JukuError as error:
                guard(deadline, self.cancelled)
                retryable = (error.code.startswith('NETWORK_') or error.code == 'DEADLINE'
                             or error.code in {'HTTP_502', 'HTTP_503', 'HTTP_504',
                                               'HTTP_520', 'HTTP_521', 'HTTP_522', 'HTTP_523',
                                               'HTTP_524', 'HTTP_525', 'HTTP_526'})
                if not retryable or index + 1 == len(self.openers):
                    raise

    def _receive(self, opener, request, deadline, max_bytes, destination=None):
        target = Path(destination) if destination is not None else None
        temporary = target.with_name(target.name + '.part') if target is not None else None
        sink = None
        try:
            with opener.open(request, timeout=max(.001, deadline-time.monotonic())) as response:
                if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                    raise JukuError('ENCODING')
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isdigit() or int(length) > max_bytes):
                    raise JukuError('RESPONSE_LIMIT')
                raw = bytearray()
                received, digest = 0, hashlib.sha256()
                if temporary is not None:
                    sink = temporary.open('wb')
                read = getattr(response, 'read1', response.read)
                while True:
                    guard(deadline, self.cancelled)
                    chunk = read(min(65536, max_bytes + 1 - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        raise JukuError('RESPONSE_LIMIT')
                    digest.update(chunk)
                    if sink is not None:
                        sink.write(chunk)
                    else:
                        raw.extend(chunk)
                guard(deadline, self.cancelled)
                if length is not None and received != int(length):
                    raise JukuError('NETWORK_SHORT_READ')
                if sink is not None:
                    sink.flush()
                    os.fsync(sink.fileno())
                    sink.close()
                    sink = None
                    guard(deadline, self.cancelled)
                    os.replace(str(temporary), str(target))
                    return dict(bytes=received, sha256=digest.hexdigest())
                data = json.loads(raw)
        except HTTPError as error:
            error.close()
            raise JukuError('HTTP_' + str(error.code)) from None
        except URLError as error:
            raise JukuError('NETWORK_' + type(error.reason).__name__) from None
        except (OSError, http.client.HTTPException) as error:
            raise JukuError('NETWORK_' + type(error).__name__) from None
        except ValueError:
            raise JukuError('RESPONSE_SCHEMA') from None
        finally:
            if sink is not None:
                sink.close()
            if temporary is not None and temporary.exists():
                temporary.unlink()
        guard(deadline, self.cancelled)
        if not isinstance(data, dict) or data.get('success') is not True or 'data' not in data:
            raise JukuError('API_REJECTED')
        return data['data']

    def _auth_attempt(self, action):
        path = self.root / 'auth-attempt.json'
        previous = load_json(path)
        at = previous.get('at')
        if (isinstance(at, (float, int)) and not isinstance(at, bool) and math.isfinite(at)
                and previous.get('status') in ('pending', 'failed')
                and 0 <= time.time()-at < AUTH_RETRY_SECONDS):
            raise JukuError('AUTH_RETRY_LATER')
        atomic_json(path, dict(action=action, at=time.time(), status='pending'))

    def _authenticate(self, action, body, key, deadline, device=None):
        self._auth_attempt(action)
        try:
            current = self._request('POST', '/auth/device/' + action, {}, body, None, key, deadline)
            current = checked_session(current, device=device, fresh=True)
            atomic_json(self.root / 'session.json', current)
            atomic_json(self.root / 'auth-attempt.json', dict(action=action, at=time.time(), status='success'))
            return key, current
        except Exception:
            # No exception text, tokens or opaque API body in persisted diagnostics.
            atomic_json(self.root / 'auth-attempt.json', dict(action=action, at=time.time(), status='failed'))
            raise

    def _session(self, deadline, rejected_token=None):
        with state_lock(self.root, deadline, self.cancelled):
            key = self._key()
            current = load_json(self.root / 'session.json')
            if current:
                current = checked_session(current)
                changed = rejected_token is not None and current['accessToken'] != rejected_token
                if expires(current['accessExpiresAt']) > time.time()+30 and (rejected_token is None or changed):
                    return key, current
                if expires(current['refreshExpiresAt']) > time.time()+30:
                    body = json.dumps({'deviceId': current['deviceId'], 'refreshToken': current['refreshToken']},
                                      separators=(',', ':')).encode()
                    # 0.80 refresh is an unsigned session POST, not pan login.
                    return self._authenticate('refresh', body, key, deadline, device=current['deviceId'])
                if rejected_token is not None:
                    raise JukuError('AUTH_REAUTHORIZE')
            elif (self.root / 'session.json').exists():
                raise JukuError('AUTH_SCHEMA')
            install = load_json(self.root / 'installation.json')
            if not install:
                if current or (self.root / 'installation.json').exists():
                    raise JukuError('AUTH_SCHEMA')
                install = {'installId': 'bobitv-' + secrets.token_hex(16)}
                atomic_json(self.root / 'installation.json', install)
            if not isinstance(install.get('installId'), str) or not re.fullmatch(r'bobitv-[0-9a-f]{32}', install['installId']):
                raise JukuError('AUTH_SCHEMA')
            body = json.dumps(dict(publicKey=base64.b64encode(key.public_key().export_key(format='DER')).decode(),
                                   platform='linux', appVersion=APP_VERSION, installId=install['installId']),
                              separators=(',', ':')).encode()
            return self._authenticate('register', body, key, deadline)

    def get(self, path, params=None, deadline=None, *, max_bytes=MAX_JSON, destination=None):
        if not isinstance(path, str) or not PATH.fullmatch(path):
            raise JukuError('CATALOGUE_PATH_ONLY')
        large = path.startswith('/shared-libraries/detail/')
        if destination is not None and not large:
            raise JukuError('SNAPSHOT_PATH_ONLY')
        if type(max_bytes) is not int or not 1 <= max_bytes <= (MAX_SNAPSHOT_JSON if large else MAX_JSON):
            raise JukuError('RESPONSE_LIMIT_CONFIG')
        now = time.monotonic()
        deadline = now+12 if deadline is None else deadline
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise JukuError('DEADLINE_CONFIG')
        deadline = min(deadline, now+(60 if large and max_bytes > MAX_JSON else 30))
        guard(deadline, self.cancelled)
        if len(canonical_query(params).encode()) > 8192:
            raise JukuError('QUERY_LIMIT')  # Before creating any installation identity.
        key, session = self._session(deadline)
        try:
            if destination is not None:
                return self._request('GET', path, params, b'', session, key, deadline, max_bytes, destination)
            return self._request('GET', path, params, b'', session, key, deadline, max_bytes)
        except JukuError as error:
            if error.code != 'HTTP_401':
                raise
        # At most one refresh + retry. A concurrent process that already rotated
        # this token is reused under the same lock; 403/429 never register again.
        key, session = self._session(deadline, rejected_token=session['accessToken'])
        try:
            if destination is not None:
                return self._request('GET', path, params, b'', session, key, deadline, max_bytes, destination)
            return self._request('GET', path, params, b'', session, key, deadline, max_bytes)
        except JukuError as error:
            if error.code == 'HTTP_401':
                with state_lock(self.root, deadline, self.cancelled):
                    atomic_json(self.root / 'auth-attempt.json', dict(
                        action='refresh', at=time.time(), status='failed'))
            raise
