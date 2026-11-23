"""User-added catalogue endpoint. No bundled server or legacy opt-in migration.

Only this new profile document enables network discovery. Credentials and
snapshots belong to the normalized endpoint, not a mutable global base URL.
"""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import secrets
from threading import Lock
from urllib.parse import urlsplit, urlunsplit


class SourceLibraryError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def normalize(value, *, document=False):
    if not isinstance(value, str):
        raise SourceLibraryError('SOURCE_URL')
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    try:
        parts = urlsplit(value)
        if (len(value) > 2048 or parts.scheme != 'https' or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.fragment or parts.query or '\\' in value
                or any(ord(c) <= 32 or ord(c) == 127 for c in value)):
            raise ValueError()
        host = parts.hostname.encode('idna').decode('ascii').lower()
        if ':' in host:
            host = '[' + host + ']'
        if parts.port and parts.port != 443:
            host += ':' + str(parts.port)
        path = parts.path.rstrip('/')
        if path == '/shared-libraries/public':
            path = ''
        if not document and path:
            raise ValueError()
        return urlunsplit(('https', host, path, '', ''))
    except (ValueError, UnicodeError):
        raise SourceLibraryError('SOURCE_URL') from None


@dataclass(frozen=True)
class SourceLibrary:
    endpoint: str
    generation: str
    root: Path
    owner: object = field(repr=False, compare=False)

    @property
    def profile(self):
        return self.owner.root

    @property
    def settings(self):
        return self.owner.settings

    @property
    def name(self):
        return urlsplit(self.endpoint).netloc

    def client(self, cancelled=lambda: False, **options):
        from bobbi_core.sharelib_api import Client, ShareLibError
        check = cancellation(self, cancelled)
        if check():
            raise ShareLibError('SOURCE_CHANGED')
        return Client(state=self.root, endpoint=self.endpoint, cancelled=check, **options)


class Store:
    """One captured profile's consent, cache and refresh owner; never a locator."""
    def __init__(self, root, active=lambda: True):
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError('Absolute source-library profile required')
        self.root = self.root.resolve()
        self.settings = self.root / 'source-library.json'
        self._active, self._revoked = active, False

    def is_current(self):
        if not self._revoked:
            try:
                if not self._active():
                    self._revoked = True
            except (OSError, ValueError, RuntimeError):
                self._revoked = True
        return not self._revoked

    def require_current(self):
        if not self.is_current():
            raise SourceLibraryError('SOURCE_CHANGED')

    def cache_path(self, endpoint):
        key = hashlib.sha256(normalize(endpoint).encode()).hexdigest()
        return self.root / 'source-libraries' / key

    def current(self):
        if not self.is_current():
            return None
        try:
            with self.settings.open('rb') as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                return None
            value = json.loads(raw)
            if (not isinstance(value, dict) or value.get('schema') != 1
                    or not re.fullmatch('[0-9a-f]{32}', str(value.get('generation', '')))):
                return None
            endpoint = normalize(value.get('endpoint'))
            if not self.is_current():
                return None
            return SourceLibrary(endpoint, value['generation'], self.cache_path(endpoint), self)
        except (OSError, ValueError, UnicodeError, RuntimeError):
            return None  # Missing/corrupt/old settings never enable remote access.

    def save(self, endpoint):
        from bobbi_core.sharelib_api import atomic_json
        endpoint = normalize(endpoint)
        self.require_current()
        previous = self.current()
        if previous and previous.endpoint == endpoint:
            return previous
        self.root.mkdir(parents=True, exist_ok=True)
        self.require_current()
        atomic_json(self.settings, dict(schema=1, endpoint=endpoint, generation=secrets.token_hex(16)))
        self.require_current()
        return self.current()

    def remove(self):
        # Preserve offline data, but withdraw this profile's network consent.
        self.require_current()
        try:
            self.settings.unlink()
        except FileNotFoundError:
            pass

    def cancelled(self, cancelled=lambda: False):
        stopped = cancelled.is_set if hasattr(cancelled, 'is_set') else cancelled or (lambda: False)
        return lambda: stopped() or not self.is_current()

    def check(self, endpoint, deadline, cancelled=lambda: False):
        return check(endpoint, deadline, self.cancelled(cancelled), state=self.cache_path(endpoint))

    def refresh(self, deadline, cancelled):
        source = self.current()
        if source is None:
            return dict(state='DISABLED')
        from bobbi_core.sharelib_refresh import refresh
        check = cancellation(source, cancelled)
        return refresh(state=source.root, deadline=deadline, cancelled=check,
                       client=source.client(check))

    def observe_host(self, host):
        source = self.current()
        previous = getattr(host, '_source_library', None)
        if source == previous:
            if source is None and host.refresh == self.refresh and host.refresh_worker is None:
                host.refresh = None
            return
        host._source_library = source
        host.refresh = self.refresh if source or host.refresh_worker is not None else None
        host.refresh_due = 0


def cancellation(source, cancelled=lambda: False):
    stopped = cancelled.is_set if hasattr(cancelled, 'is_set') else cancelled or (lambda: False)
    lock, revoked = Lock(), False
    def check():
        nonlocal revoked
        if stopped():
            return True
        with lock:
            if not revoked:
                revoked = source.owner.current() != source
            return revoked
    return check


def check(endpoint, deadline, cancelled=lambda: False, *, state):
    """Validate the actual public-directory protocol before publishing settings."""
    from bobbi_core.sharelib_api import Client, guard
    endpoint = normalize(endpoint)
    result = Client(state=state, endpoint=endpoint, cancelled=cancelled).get(
        '/shared-libraries/public', dict(page=1, pageSize=100), deadline)
    guard(deadline, cancelled)
    if (not isinstance(result, dict) or not isinstance(result.get('items'), list)
            or len(result['items']) > 100):
        raise SourceLibraryError('SOURCE_FORMAT')
    for row in result['items']:
        if (not isinstance(row, dict)
                or not re.fullmatch('[A-Za-z0-9_-]{1,64}', str(row.get('shareCode', '')))
                or type(row.get('version')) not in (str, int)
                or not 1 <= len(str(row['version'])) <= 128):
            raise SourceLibraryError('SOURCE_FORMAT')
    return endpoint


def read_document(url, deadline, cancelled=lambda: False):
    """Download only a bounded JSON document, never scrape pages or run plugins."""
    import ssl
    from urllib.request import Request, build_opener, ProxyHandler
    from bobbi_core.sharelib_api import Client, EdgeHTTPSHandler, NoRedirect
    from bobbi_core.library_contract import import_catalog, MAX_CATALOG_BYTES
    url = normalize(url, document=True)
    request = Request(url, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'})
    request.sharelib_deadline, request.sharelib_cancelled = deadline, cancelled
    receiver = object.__new__(Client)
    receiver.cancelled = cancelled
    opener = build_opener(ProxyHandler({}), NoRedirect(),
        EdgeHTTPSHandler(None, ssl.create_default_context(), urlsplit(url).hostname))
    return import_catalog(receiver._receive(opener, request, deadline, MAX_CATALOG_BYTES, raw_document=True),
                          source_id=hashlib.sha256(('url-catalog\n' + url).encode()).hexdigest()[:32])
