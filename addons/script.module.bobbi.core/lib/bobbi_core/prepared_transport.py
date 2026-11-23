"""Ephemeral verified CD2 addresses, independent of filesystem mounting."""
from urllib.parse import urlsplit


def checked_url(value, endpoint=None):
    if not isinstance(value, str) or len(value) > 16384 or any(ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('PREPARED_PLAYBACK_ADDRESS')
    p = urlsplit(value)
    if (p.scheme != 'http' or p.hostname != '127.0.0.1' or not p.port or
            p.username or p.password or p.fragment or not p.path.startswith('/') or '|' in value):
        raise ValueError('PREPARED_PLAYBACK_ADDRESS')
    if endpoint is not None and p.netloc != urlsplit(endpoint).netloc:
        raise ValueError('PREPARED_PLAYBACK_ENDPOINT')
    return value


def resolve_address(provider, item, qualifier):
    # Called only on the existing IO lane, after file identity is revalidated.
    return checked_url(qualifier.download_url(provider, item), qualifier.endpoint)


def playback_path(root, entry):
    if entry.get('_playback_url'):
        return checked_url(entry['_playback_url'])
    if (root != '/storage/videos/Clouddrive/CloudDrive' or not isinstance(entry.get('path'), str)
            or not entry['path'].startswith('/115open/') or '\x00' in entry['path']
            or any(p in {'.', '..'} for p in entry['path'].split('/'))):
        raise ValueError('PREPARED_PLAYBACK_PATH')
    return root + entry['path']
