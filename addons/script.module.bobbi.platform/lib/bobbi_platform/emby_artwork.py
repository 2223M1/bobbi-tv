"""Scoped, on-demand Emby Primary thumbnails. No remote URL, token or private disk cache."""
from collections import OrderedDict
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import re
import struct
from threading import Lock
import time
from urllib.parse import urlencode
from urllib.request import Request
import zlib

from bobbi_core.image_cache import _configuration, media_type
from .libraries import Registry
from .server_http import Session, address

MAX_BYTES = 2 * 1024 * 1024
KEY = re.compile(r'[A-Za-z0-9_-]{1,128}')
PATH = re.compile(r'/emby-art/([a-f0-9]{32})/([a-f0-9]{64})/([A-Za-z0-9_-]{1,128})/([A-Za-z0-9_-]{1,128})/([a-f0-9]{64})')
VERIFIED_TAG_TTL_SECONDS = 60.0
VERIFIED_TAG_LIMIT = 512
_VERIFIED_TAGS_LOCK = Lock()
_VERIFIED_TAGS: OrderedDict[tuple[str, str, str, str, str], float] = OrderedDict()


def _tag_scope_key(location: str, token: str, user_id: str, item: str, tag: str) -> tuple[str, str, str, str, str]:
    tok_digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    return (location.rstrip('/'), tok_digest, user_id, item, tag)


def note_verified_primary_tag(location: str, token: str, user_id: str, item: str, tag: str) -> None:
    """Record a short-lived in-memory lease for a user-scoped Primary tag just verified by a page read."""
    if any(not isinstance(v, str) or not v for v in (location, token, user_id, item, tag)):
        return
    if not KEY.fullmatch(item) or not KEY.fullmatch(tag):
        return
    key = _tag_scope_key(location, token, user_id, item, tag)
    expires = time.monotonic() + VERIFIED_TAG_TTL_SECONDS
    with _VERIFIED_TAGS_LOCK:
        _VERIFIED_TAGS[key] = expires
        _VERIFIED_TAGS.move_to_end(key)
        while len(_VERIFIED_TAGS) > VERIFIED_TAG_LIMIT:
            _VERIFIED_TAGS.popitem(last=False)


def _has_verified_primary_tag(source, item: str, tag: str) -> bool:
    uid = source.metadata.get('user_id', '') if isinstance(getattr(source, 'metadata', None), dict) else ''
    if not source.location or not source.password or not uid:
        return False
    key = _tag_scope_key(source.location, source.password, uid, item, tag)
    now = time.monotonic()
    with _VERIFIED_TAGS_LOCK:
        exp = _VERIFIED_TAGS.get(key)
        if exp is None:
            return False
        if now >= exp:
            _VERIFIED_TAGS.pop(key, None)
            return False
        return True


def clear_verified_primary_tags() -> None:
    with _VERIFIED_TAGS_LOCK:
        _VERIFIED_TAGS.clear()


def _signer(token):
    # The public TMDb listener token already appears in Kodi image URLs; it
    # must NOT authorize authenticated requests. Derive a separate purpose key.
    secret = hmac.digest(bytes.fromhex(token), b'bobbi/emby-primary/v1', 'sha256')
    return lambda text: hmac.new(secret, text.encode('ascii'), hashlib.sha256).hexdigest()


def poster_factory(root, source_id, generation, store):
    """A tagged page reads one local key; Kodi can reuse its own textures after restart."""
    if (not isinstance(source_id, str) or not re.fullmatch('[0-9a-f]{32}', source_id)
            or not isinstance(generation, str) or not re.fullmatch('[0-9a-f]{64}', generation)):
        return lambda *_: ''
    try:
        root = Path(root)
        art = _configuration(root / 'image-runtime.json')
        if art is None:
            return lambda *_: ''
        origin = 'http://127.0.0.1:%d' % art['port']
    except (OSError, TypeError, ValueError):
        return lambda *_: ''
    sign = None
    def poster(item_id, tag):
        nonlocal sign
        if any(not isinstance(s, str) or not KEY.fullmatch(s) for s in (item_id, tag)):
            return ''
        if sign is None:
            try:
                sign = _signer(store.emby_art_key())
            except (OSError, ValueError):
                sign = False
        if not sign:
            return ''
        path = '/emby-art/%s/%s/%s/%s' % (source_id, generation, item_id, tag)
        return origin + path + '/' + sign(path)
    return poster


def _dimensions(width, height):
    if not (1 <= width <= 4096 and 1 <= height <= 4096 and width * height <= 8_000_000):
        raise ValueError('IMAGE_DIMENSIONS')


def thumbnail_type(raw, declared):
    """Check declared type, container structure, bounded raster dimensions and payload."""
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('IMAGE_LENGTH')
    kind = media_type(raw)
    if kind != declared:
        raise ValueError('IMAGE_FORMAT')
    if kind == 'image/png':
        off, pixels = 8, False
        while off + 12 <= len(raw):
            length, chunk = struct.unpack_from('>I4s', raw, off)
            end = off + 8 + length
            if end + 4 > len(raw) or zlib.crc32(raw[off+4:end]) != int.from_bytes(raw[end:end+4], 'big'):
                raise ValueError('IMAGE_FORMAT')
            if off == 8:
                if chunk != b'IHDR' or length != 13:
                    raise ValueError('IMAGE_FORMAT')
                _dimensions(*struct.unpack_from('>II', raw, off+8))
            if chunk == b'IDAT' and length:
                pixels = True
            off = end + 4
            if chunk == b'IEND':
                if pixels and length == 0 and off == len(raw):
                    return kind
                break
    elif kind == 'image/jpeg':
        off, sized = 2, False
        while off + 4 <= len(raw) and raw[off] == 0xff:
            marker = raw[off+1]
            if marker == 0xff:
                off += 1
                continue
            length = int.from_bytes(raw[off+2:off+4], 'big')
            if length < 2 or off + 2 + length > len(raw):
                break
            if marker in (0xc0, 0xc1, 0xc2) and length >= 8:
                height, width = struct.unpack_from('>HH', raw, off+5)
                _dimensions(width, height)
                sized = True
            if marker == 0xda and sized and length >= 6 and off + 2 + length < len(raw)-2:
                return kind
            off += 2 + length
    elif kind == 'image/webp':
        off, image = 12, False
        while off + 8 <= len(raw):
            chunk, length = struct.unpack_from('<4sI', raw, off)
            start, end = off + 8, off + 8 + length
            if end > len(raw):
                break
            if chunk == b'VP8X' and length == 10:
                if raw[start] & 2:  # animated private thumbnails not admitted
                    break
                _dimensions(1 + int.from_bytes(raw[start+4:start+7], 'little'),
                            1 + int.from_bytes(raw[start+7:start+10], 'little'))
            if chunk == b'VP8 ' and length > 10 and raw[start+3:start+6] == b'\x9d\x01\x2a':
                _dimensions(*(size & 0x3fff for size in struct.unpack_from('<HH', raw, start+6)))
                image = True
            if chunk == b'VP8L' and length > 5 and raw[start] == 0x2f:
                bits = int.from_bytes(raw[start+1:start+5], 'little')
                _dimensions(1+(bits & 0x3fff), 1+((bits >> 14) & 0x3fff))
                image = True
            off = end + (length & 1)
        if image and off == len(raw):
            return kind
    raise ValueError('IMAGE_FORMAT')


def fetch_primary(source, item, tag, deadline, current):
    """Verify the user-scoped item still advertises this tag, then GET the fixed image route."""
    session = Session('emby', source.location, source.password)
    if not _has_verified_primary_tag(source, item, tag):
        with session.budget(max(.01, deadline-time.monotonic())):
            data = session.request('/Users/' + source.metadata['user_id'] + '/Items/' + item,
                                   query={'EnableImageTypes':'Primary', 'ImageTypeLimit':1})
        if (not isinstance(data, dict) or data.get('Id') != item or type(data.get('ImageTags')) is not dict
                or data['ImageTags'].get('Primary') != tag or not current()):
            raise ValueError('IMAGE_CHANGED')
        note_verified_primary_tag(source.location, source.password, source.metadata['user_id'], item, tag)
    elif not current():
        raise ValueError('IMAGE_CHANGED')
    url = address(session.base, '/Items/' + item + '/Images/Primary') + '?' + urlencode({
        'tag':tag, 'MaxWidth':440, 'MaxHeight':660})
    req = Request(url, headers=dict(session.headers(), Accept='image/jpeg, image/png, image/webp',
                  **{'Accept-Encoding':'identity', 'Cache-Control':'no-store'}))
    with session.opener.open(req, timeout=min(4, max(.01, deadline - time.monotonic()))) as reply:
        if (reply.status != 200 or reply.geturl() != url or
                any(len(reply.headers.get_all(k, [])) > 1 for k in ('Content-Length', 'Content-Type', 'Content-Encoding'))
                or reply.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise ValueError('IMAGE_RESPONSE')
        declared = reply.headers.get('Content-Length')
        if declared is not None and (not re.fullmatch('[0-9]{1,8}', declared) or not 0 < int(declared) <= MAX_BYTES):
            raise ValueError('IMAGE_LENGTH')
        raw = bytearray()
        while time.monotonic() < deadline and len(raw) <= MAX_BYTES:
            chunk = reply.read1(min(65536, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                if declared and int(declared) != len(raw):
                    break
                data = bytes(raw)
                return data, thumbnail_type(data, reply.headers.get('Content-Type', '').split(';')[0].strip().lower())
            raw.extend(chunk)
    raise ValueError('IMAGE_LENGTH')


def reader(root, current, fetch=fetch_primary):
    root = Path(root)
    def get(path, deadline):
        match = PATH.fullmatch(path)
        if not match or not current():
            raise ValueError('IMAGE_SCOPE')
        source_id, generation, item, tag, _ = match.groups()
        def snapshot():
            if not current() or time.monotonic() >= deadline:
                raise ValueError('IMAGE_SCOPE')
            with closing(Registry(root / 'libraries.sqlite3', read_only=True)) as store:
                if not hmac.compare_digest(match[5], _signer(store.emby_art_key())(path.rsplit('/', 1)[0])):
                    raise ValueError('IMAGE_SCOPE')
                source, (_, sid, rev) = store.emby_binding()
            if (source is None or (sid, rev) != (source_id, generation) or source.kind != 'media_server'
                    or source.metadata['provider'] != 'emby'):
                raise ValueError('IMAGE_SCOPE')
            return source
        source = snapshot()
        payload = fetch(source, item, tag, deadline, lambda:snapshot() == source)
        if snapshot() != source:
            raise ValueError('IMAGE_SCOPE')
        return payload
    return get
