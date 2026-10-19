"""Bounded v1 torrent identity, hashing the original bencoded info bytes."""
import base64
import hashlib
import logging
import re
from urllib.parse import parse_qs, urlsplit, urljoin

MAX_TORRENT_BYTES = 16 * 1024 * 1024
_STAGES = frozenset(('transport', 'request', 'http', 'redirect', 'body', 'bencode'))
_VALUE_REASONS = {
    'Invalid BT hash': 'INVALID_BT_HASH',
    'Missing or ambiguous BT hash': 'MISSING_OR_AMBIGUOUS_BT_HASH',
    'Invalid torrent size': 'INVALID_SIZE',
    'Invalid torrent structure': 'INVALID_STRUCTURE',
    'Invalid torrent integer': 'INVALID_INTEGER',
    'Invalid torrent dictionary': 'INVALID_DICTIONARY',
    'Invalid torrent info': 'INVALID_INFO',
    'Truncated torrent': 'TRUNCATED',
    'Invalid torrent string': 'INVALID_STRING',
    'Truncated torrent string': 'TRUNCATED_STRING',
    'Missing torrent info': 'MISSING_INFO',
}
_NETWORK_REASONS = {
    name: name.upper() for name in (
        'ConnectTimeout', 'ReadTimeout', 'Timeout', 'ConnectionError', 'SSLError',
        'ProxyError', 'InvalidURL', 'InvalidSchema', 'MissingSchema', 'HTTPError',
        'TooManyRedirects', 'ChunkedEncodingError', 'ContentDecodingError',
        'StreamConsumedError', 'RequestException')
}
_REASONS = frozenset(_VALUE_REASONS.values()) | frozenset(_NETWORK_REASONS.values()) | frozenset((
    'UNKNOWN', 'NETWORK_EXCEPTION', 'DEADLINE', 'SIZE_LIMIT', 'URL_INVALID',
    'SCHEME_INVALID', 'LOCATION_INVALID', 'HOP_LIMIT', 'HTTP_STATUS', 'BODY_UNAVAILABLE'))


def _diagnostic(stage, reason, http_status=None):
    """Finite labels only. Diagnostic failure must not alter playback behavior."""
    try:
        stage = stage if stage in _STAGES else 'unknown'
        reason = reason if reason in _REASONS else 'UNKNOWN'
        status = http_status if type(http_status) is int and 100 <= http_status <= 599 else 'none'
        logging.getLogger('plugin.video.bobbi.torrent').warning(
            'bobbi torrent download diagnostic: stage=%s reason=%s http_status=%s',
            stage, reason, status)
    except Exception:
        pass


def _observed_get(get, locator, **kwargs):
    try:
        return get(locator, **kwargs)
    except Exception as error:
        _diagnostic('request', _NETWORK_REASONS.get(type(error).__name__, 'NETWORK_EXCEPTION'))
        raise


def _observed_chunks(response):
    try:
        yield from response.iter_content(chunk_size=65536)
    except Exception as error:
        _diagnostic('body', _NETWORK_REASONS.get(type(error).__name__, 'NETWORK_EXCEPTION'))
        raise


def magnet_hash(locator):
    values = []
    for value in parse_qs(urlsplit(locator).query).get('xt', []):
        if value.lower().startswith('urn:btih:'):
            value = value[9:]
            if re.fullmatch('[a-fA-F0-9]{40}', value):
                values.append(value.lower())
            elif re.fullmatch('[A-Z2-7a-z]{32}', value):
                values.append(base64.b32decode(value.upper()).hex())
            else:
                raise ValueError('Invalid BT hash')
    if not values or len(set(values)) != 1:
        raise ValueError('Missing or ambiguous BT hash')
    return values[0]


def torrent_hash(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_TORRENT_BYTES:
        raise ValueError('Invalid torrent size')
    info_span = None
    nodes = 0

    def parse(offset, depth=0):
        nonlocal info_span, nodes
        nodes += 1
        if depth > 64 or nodes > 200000 or offset >= len(raw):
            raise ValueError('Invalid torrent structure')
        token = raw[offset:offset + 1]
        if token == b'i':
            end = raw.find(b'e', offset + 1)
            value = raw[offset + 1:end]
            if end < 0 or not re.fullmatch(b'0|-?[1-9][0-9]{0,19}', value):
                raise ValueError('Invalid torrent integer')
            return end + 1, None
        if token in (b'd', b'l'):
            pos = offset + 1
            keys = set()
            while pos < len(raw) and raw[pos:pos + 1] != b'e':
                key = None
                if token == b'd':
                    pos, key = parse(pos, depth + 1)
                    if not isinstance(key, bytes) or key in keys:
                        raise ValueError('Invalid torrent dictionary')
                    keys.add(key)
                start = pos
                pos, _ = parse(pos, depth + 1)
                if depth == 0 and key == b'info':
                    if raw[start:start + 1] != b'd' or pos == start + 2:
                        raise ValueError('Invalid torrent info')
                    info_span = (start, pos)
            if pos >= len(raw):
                raise ValueError('Truncated torrent')
            return pos + 1, None
        colon = raw.find(b':', offset, offset + 12)
        size = raw[offset:colon]
        if colon < 0 or not re.fullmatch(b'0|[1-9][0-9]{0,9}', size):
            raise ValueError('Invalid torrent string')
        end = colon + 1 + int(size)
        if end > len(raw):
            raise ValueError('Truncated torrent string')
        return end, raw[colon + 1:end]

    end, _ = parse(0)
    if raw[:1] != b'd' or end != len(raw) or info_span is None:
        raise ValueError('Missing torrent info')
    return hashlib.sha1(raw[info_span[0]:info_span[1]]).hexdigest()


def download_torrent(response, active, monotonic, deadline):
    chunks, length = [], 0
    for chunk in _observed_chunks(response):
        active()
        if monotonic() >= deadline:
            _diagnostic('body', 'DEADLINE')
            raise TimeoutError('Torrent download deadline reached')
        length += len(chunk)
        if length > MAX_TORRENT_BYTES:
            _diagnostic('body', 'SIZE_LIMIT')
            raise ValueError('Torrent download size exceeded')
        chunks.append(chunk)
    active()
    if monotonic() >= deadline:
        _diagnostic('body', 'DEADLINE')
        raise TimeoutError('Torrent download deadline reached')
    raw = b''.join(chunks)
    try:
        return raw, torrent_hash(raw)
    except ValueError as error:
        _diagnostic('bencode', _VALUE_REASONS.get(str(error), 'UNKNOWN'))
        raise


def resolve_http(locator, get, active, monotonic, deadline):
    """Resolve a bounded redirect chain without replacing the chosen locator."""
    current = locator
    for _ in range(6):
        active()
        remaining = deadline - monotonic()
        if remaining <= 0:
            _diagnostic('request', 'DEADLINE')
            raise TimeoutError('Torrent download deadline reached')
        try:
            scheme = urlsplit(current).scheme
        except ValueError:
            _diagnostic('transport', 'URL_INVALID')
            raise
        if scheme not in ('http', 'https'):
            _diagnostic('transport', 'SCHEME_INVALID')
            raise ValueError('Invalid torrent transport')
        with _observed_get(get, current, stream=True, allow_redirects=False,
                 timeout=(min(3.05, remaining), min(8.0, remaining))) as response:
            active()
            if monotonic() >= deadline:
                _diagnostic('request', 'DEADLINE')
                raise TimeoutError('Torrent download deadline reached')
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location', '')
                if not location or len(location) > 16384:
                    _diagnostic('redirect', 'LOCATION_INVALID', response.status_code)
                    raise ValueError('Invalid torrent redirect')
                try:
                    current = urljoin(current, location)
                except ValueError:
                    _diagnostic('redirect', 'URL_INVALID', response.status_code)
                    raise
                if current.startswith('magnet:?'):
                    try:
                        return None, magnet_hash(current), current
                    except ValueError as error:
                        _diagnostic('redirect', _VALUE_REASONS.get(str(error), 'UNKNOWN'), response.status_code)
                        raise
                continue
            try:
                response.raise_for_status()
            except Exception:
                _diagnostic('http', 'HTTP_STATUS', response.status_code)
                raise
            if response.status_code != 200:
                _diagnostic('http', 'BODY_UNAVAILABLE', response.status_code)
                raise ValueError('Torrent body unavailable')
            raw, info_hash = download_torrent(response, active, monotonic, deadline)
            return raw, info_hash, ''
    _diagnostic('redirect', 'HOP_LIMIT')
    raise ValueError('Torrent redirect limit reached')

