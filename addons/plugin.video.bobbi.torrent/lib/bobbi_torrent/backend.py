"""Explicit existing-service connection. Never starts or reconfigures an engine."""
import ipaddress
import json
from pathlib import Path
import time
from urllib.parse import quote, urlencode, urlsplit

from . import ADDON_ID

CONFIG_NAME = 'backend.json'
SUPPORTED_VERSIONS = ('MatriX.144.1', 'MatriX.147')
LEGACY_KEYS = frozenset(('service_host', 'service_port', 'ssl_connection',
    'service_login', 'service_password', 'metadata_timeout', 'buffer_timeout'))
MAX_RESPONSE = 2 * 1024 * 1024


class BackendError(RuntimeError):
    def __init__(self, code, category='torrserver_error', diagnostic=None):
        self.code, self.category = code, category
        self.diagnostic = diagnostic or {}
        super().__init__(code)


def validate_backend_config(value):
    keys = {'schema', 'endpoint', 'auth', 'metadata_seconds', 'buffering_seconds'}
    if (not isinstance(value, dict) or set(value) != keys
            or type(value['schema']) is not int or value['schema'] != 1):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    endpoint = value['endpoint']
    if not isinstance(endpoint, str) or len(endpoint) > 256:
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    try:
        p = urlsplit(endpoint)
        local = p.hostname == 'localhost' or ipaddress.ip_address(p.hostname).is_loopback
        valid = (local and p.scheme in ('http', 'https') and p.port and not p.username
            and not p.password and p.path in ('', '/') and not p.query and not p.fragment
            and not any(c.isspace() for c in endpoint))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    auth = value['auth']
    if auth is not None:
        if (not isinstance(auth, dict) or set(auth) != {'username', 'password'}
                or any(not isinstance(auth[k], str) or not 1 <= len(auth[k]) <= 256
                       or any(ord(c) < 32 or ord(c) == 127 for c in auth[k]) for k in auth)
                or ':' in auth['username']):
            raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
        auth = dict(auth)
    for key, maximum in (('metadata_seconds', 120), ('buffering_seconds', 300)):
        if type(value[key]) is not int or not 1 <= value[key] <= maximum:
            raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    return dict(value, endpoint=endpoint.rstrip('/'), auth=auth)


def from_legacy_settings(settings):
    """Pure explicit migration; ignores all engine controls and unrelated keys."""
    if not isinstance(settings, dict):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    host, port = settings.get('service_host', ''), settings.get('service_port', '')
    ssl = settings.get('ssl_connection', 'false')
    if not isinstance(host, str) or ssl not in ('true', 'false'):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    try:
        port = int(port)
        metadata = int(settings.get('metadata_timeout', '30') or '30')
        buffering = int(settings.get('buffer_timeout', '90') or '90')
    except (ValueError, TypeError):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID') from None
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    username, password = settings.get('service_login', ''), settings.get('service_password', '')
    auth = {'username': username, 'password': password} if username or password else None
    return validate_backend_config(dict(schema=1,
        endpoint=('https' if ssl == 'true' else 'http') + '://' + host + ':' + str(port),
        auth=auth, metadata_seconds=metadata, buffering_seconds=buffering))


def config_path():
    import xbmcaddon
    import xbmcvfs
    return Path(xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo('profile'))) / CONFIG_NAME


def load_config(path=None):
    path = Path(path) if path is not None else config_path()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    if not path.exists():
        raise BackendError('TORRENT_BACKEND_NOT_CONFIGURED')
    if not path.is_file() or path.stat().st_size > 8192:
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID')
    try:
        return validate_backend_config(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, UnicodeError):
        raise BackendError('TORRENT_BACKEND_CONFIG_INVALID') from None


def subtitle_connection():
    config = load_config()
    auth = config['auth']
    return config['endpoint'], ((auth['username'], auth['password']) if auth else None)


class Backend:
    """Only echo, exact add, metadata read and one selected-file preload."""
    def __init__(self, config, session=None, clock=time.monotonic):
        import requests
        self.config = validate_backend_config(config)
        self.session, self.clock = session or requests.Session(), clock
        self.session.trust_env = False
        self.auth = self.config['auth']
        self.auth = (self.auth['username'], self.auth['password']) if self.auth else None
        self.add_attempted = False
        self.add_reconciled = False
        self.preload_attempted = False

    def close(self):
        self.session.close()

    def request(self, method, path, deadline, active, body=None, files=None, preload=False):
        import requests
        active()
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise BackendError('TORRENT_CONTROL_DEADLINE')
        timeout = (min(3.05, remaining), min(8.0, remaining))
        kwargs = dict(timeout=timeout, stream=True, allow_redirects=False, auth=self.auth)
        if files is not None:
            kwargs.update(files=files, data=body)
        elif body is not None:
            kwargs['json'] = body
        try:
            with self.session.request(method, self.config['endpoint'] + path, **kwargs) as response:
                active()
                if response.status_code != 200:
                    raise BackendError('TORRENT_HTTP_REJECTED')
                if preload:
                    return None
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=4096):
                    active()
                    if self.clock() >= deadline:
                        raise BackendError('TORRENT_CONTROL_DEADLINE')
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise BackendError('TORRENT_RESPONSE_LIMIT')
                    chunks.append(chunk)
                raw = b''.join(chunks)
        except requests.exceptions.ReadTimeout:
            active()
            if preload:
                # The server can still be preloading. Poll; never submit again.
                return None
            raise BackendError('TORRENT_HTTP_TIMEOUT') from None
        except requests.exceptions.RequestException:
            raise BackendError('TORRENT_HTTP_UNAVAILABLE') from None
        active()
        if self.clock() >= deadline:
            raise BackendError('TORRENT_CONTROL_DEADLINE')
        return raw

    def ready(self, active):
        raw = self.request('GET', '/echo', self.clock() + 4, active)
        if raw.decode('ascii', errors='replace').strip() not in SUPPORTED_VERSIONS:
            raise BackendError('TORRENT_BACKEND_VERSION_UNSUPPORTED')

    @staticmethod
    def document(raw):
        try:
            value = json.loads(raw)
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError, UnicodeError):
            raise BackendError('TORRENT_RESPONSE_INVALID') from None

    def add(self, info_hash, magnet, raw, deadline, active):
        if self.add_attempted:
            raise BackendError('TORRENT_ADD_ALREADY_ATTEMPTED')
        active()
        self.add_attempted = True  # Even a lost reply may have accepted the add.
        try:
            if magnet:
                value = self.request('POST', '/torrents', deadline, active,
                    body={'action': 'add', 'link': magnet, 'save_to_db': False})
            else:
                value = self.request('POST', '/torrent/upload', deadline, active,
                    # MatriX tests form-field presence, not its boolean text.
                    # Even save='false' persists the torrent; omit it entirely.
                    body={}, files={'file': ('selected.torrent', raw)})
            result = self.document(value)
        except BackendError as error:
            if error.category in ('cancelled', 'aborted', 'superseded'):
                raise
            # A lost reply is not a failed submission. Query this hash once;
            # never add again or touch other torrents to manufacture recovery.
            active()
            try:
                result = self.status(info_hash, deadline, active)
            except BackendError as probe:
                if probe.category in ('cancelled', 'aborted', 'superseded'):
                    raise
                raise BackendError('TORRENT_ADD_UNCONFIRMED') from error
            self.add_reconciled = True
        if str(result.get('hash', '')).lower() != info_hash:
            raise BackendError('TORRENT_HASH_MISMATCH', 'source_identity_mismatch')

    def status(self, info_hash, deadline, active):
        value = self.document(self.request('POST', '/torrents', deadline, active,
            body={'action': 'get', 'hash': info_hash}))
        if str(value.get('hash', '')).lower() != info_hash:
            raise BackendError('TORRENT_HASH_MISMATCH', 'source_identity_mismatch')
        return value

    def preload(self, info_hash, file_id, deadline, active):
        if self.preload_attempted:
            raise BackendError('TORRENT_PRELOAD_ALREADY_ATTEMPTED', 'preload_error')
        active()
        self.preload_attempted = True
        self.request('GET', '/stream?' + urlencode({'link': info_hash, 'index': file_id,
            'stat': 'true', 'preload': 'true'}), deadline, active, preload=True)

    def stream_url(self, info_hash, file):
        # TorrServer's media endpoint deliberately does not use control auth.
        return self.config['endpoint'] + '/stream/' + quote(file['path']) + '?' + urlencode(
            {'link': info_hash, 'index': file['id']}) + '&play'
