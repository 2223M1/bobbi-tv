"""Per-user device-local helper credentials, outside addons/update packages."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


class Pairing:
    def __init__(self, endpoint, username, password):
        if not isinstance(endpoint, str):
            raise ValueError('Invalid helper endpoint')
        parts = urlsplit(endpoint)
        if (parts.scheme != 'http' or parts.hostname != '127.0.0.1'
                or not parts.port or parts.username or parts.password
                or parts.path not in ('', '/') or parts.query or parts.fragment):
            raise ValueError('Helper must be an explicit device-local IPv4 endpoint')
        if (not isinstance(username, str) or not 1 <= len(username) <= 64
                or ':' in username or any(ord(c) < 33 or ord(c) > 126 for c in username)):
            raise ValueError('Invalid helper username')
        if (not isinstance(password, str) or not 16 <= len(password) <= 256
                or any(ord(c) < 33 or ord(c) > 126 for c in password)):
            raise ValueError('Invalid helper pairing code')
        self.endpoint = endpoint.rstrip('/')
        self.username, self.password = username, password

    def __repr__(self):
        return '<bobbi Pairing: credentials hidden>'


def save(path, pairing):
    if not isinstance(pairing, Pairing):
        raise ValueError('Validated pairing required')
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink credential path')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pairing-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 1, 'endpoint': pairing.endpoint,
                       'username': pairing.username, 'password': pairing.password}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('Invalid helper pairing storage')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or set(value) != {'schema', 'endpoint', 'username', 'password'}
                or type(value['schema']) is not int or value['schema'] != 1):
            raise ValueError('Invalid pairing schema')
        return Pairing(value['endpoint'], value['username'], value['password'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('Helper pairing could not be loaded') from None


def from_export(raw):
    """Read the helper's explicit user export, never guess another app's data."""
    from .torrserver import checked_pairing, TorrServerError
    try:
        value = checked_pairing(raw)
        return Pairing(value['url'], value['username'], value['password'])
    except (TorrServerError, ValueError, TypeError):
        raise ValueError('Not a supported bobbi helper pairing export') from None


def engine_document(pairing):
    """Validate stored credentials again at the pinned engine boundary."""
    from .torrserver import checked_pairing, ENGINE_VERSION
    if not isinstance(pairing, Pairing):
        raise ValueError('Helper pairing is required')
    return checked_pairing({'schema': 'bobbi-local-engine-v1', 'engine': 'TorrServer',
        'version': ENGINE_VERSION, 'url': pairing.endpoint,
        'username': pairing.username, 'password': pairing.password})
