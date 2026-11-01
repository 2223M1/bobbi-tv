"""User-added catalogue endpoint. No bundled server or legacy opt-in migration.

Only this new profile document enables network discovery. Credentials and
snapshots belong to the normalized endpoint, not a mutable global base URL.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit, urlunsplit


class SourceLibraryError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def profile():
    from bobbi_platform.paths import profile as path
    return path('plugin.video.bobbi')


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

    @property
    def name(self):
        return urlsplit(self.endpoint).netloc


def cache_path(endpoint):
    key = hashlib.sha256(normalize(endpoint).encode()).hexdigest()
    return profile() / 'source-libraries' / key


def current():
    try:
        path = profile() / 'source-library.json'
        with path.open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('schema') != 1
                or not re.fullmatch('[0-9a-f]{32}', str(value.get('generation', '')))):
            return None
        endpoint = normalize(value.get('endpoint'))
        return SourceLibrary(endpoint, value['generation'], cache_path(endpoint))
    except (OSError, ValueError, UnicodeError, ImportError, RuntimeError):
        return None  # Missing/corrupt/old settings never enable remote access.


def save(endpoint):
    from bobbi_core.juku_api import atomic_json
    endpoint = normalize(endpoint)
    previous = current()
    if previous and previous.endpoint == endpoint:
        return previous  # Checking the same connection does not revoke work.
    root = profile()
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / 'source-library.json', dict(schema=1, endpoint=endpoint,
                                                generation=secrets.token_hex(16)))
    return current()


def remove():
    # Preserve offline data for re-adding the URL, but withdraw network consent.
    try:
        (profile() / 'source-library.json').unlink()
    except FileNotFoundError:
        pass


def cancellation(source, cancelled=lambda: False):
    stopped = cancelled.is_set if hasattr(cancelled, 'is_set') else cancelled or (lambda: False)
    lock, due, revoked = Lock(), 0, False
    def check():
        nonlocal due, revoked
        if stopped():
            return True
        with lock:
            now = time.monotonic()
            if not revoked and now >= due:
                revoked = current() != source
                due = now + .25
            return revoked
    return check


def check(endpoint, deadline, cancelled=lambda: False):
    """Validate the actual public-directory protocol before publishing settings."""
    from bobbi_core.juku_api import Client, guard
    endpoint = normalize(endpoint)
    result = Client(endpoint=endpoint, cancelled=cancelled).get(
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
    from bobbi_core.juku_api import Client, EdgeHTTPSHandler, NoRedirect
    from bobbi_platform.libraries import import_catalog, MAX_CATALOG_BYTES
    url = normalize(url, document=True)
    request = Request(url, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'})
    request.juku_deadline, request.juku_cancelled = deadline, cancelled
    receiver = object.__new__(Client)
    receiver.cancelled = cancelled
    opener = build_opener(ProxyHandler({}), NoRedirect(),
        EdgeHTTPSHandler(None, ssl.create_default_context(), urlsplit(url).hostname))
    return import_catalog(receiver._receive(opener, request, deadline, MAX_CATALOG_BYTES, raw_document=True),
                          source_id=hashlib.sha256(('url-catalog\n' + url).encode()).hexdigest()[:32])


def refresh(deadline, cancelled):
    source = current()
    if source is None:
        return dict(state='DISABLED')
    from bobbi_core.juku_refresh import refresh as advance
    return advance(state=source.root, deadline=deadline,
                   cancelled=cancellation(source, cancelled))


def observe_host(host):
    """Called by the existing idle probe; adding/removing needs no Kodi restart."""
    source = current()
    previous = getattr(host, '_source_library', None)
    if source == previous:
        if source is None and getattr(host, 'refresh', None) is refresh and host.refresh_worker is None:
            host.refresh = None
        return
    host._source_library = source
    # Let an in-flight worker finish cancellation before removing its owner.
    host.refresh = refresh if source or host.refresh_worker is not None else None
    host.refresh_due = 0
