"""Data-only STRM: a document and its target are distinct observations."""
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from .library_contract import LibraryError, direct_url

LIMIT = 16384


def parse(raw):
    if not isinstance(raw, bytes) or len(raw) > LIMIT:
        raise LibraryError('POINTER_INVALID')
    try:
        value = raw.decode('utf-8-sig').rstrip(' \t\r\n')
    except UnicodeError:
        raise LibraryError('POINTER_INVALID') from None
    if value.startswith('#KODIPROP'):
        raise LibraryError('POINTER_PROPERTY_UNSUPPORTED')
    target = direct_url(value)
    if unquote(urlsplit(target).path).lower().endswith(('.m3u', '.m3u8', '.mpd', '.pls')):
        raise LibraryError('MEDIA_NOT_FINITE')
    return target, sha256(raw).hexdigest()
