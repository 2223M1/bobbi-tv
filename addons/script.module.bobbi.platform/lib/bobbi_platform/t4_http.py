"""Bounded JSON transport for explicitly approved T4 origins; no redirects/cookies/proxy."""
from http.client import HTTPException
import hashlib
import re
import socket
import time
from urllib.parse import urlsplit

from bobbi_core.library_contract import MAX_CATALOG_BYTES, LibraryError
from bobbi_core import t4
from .source_media_http import connection as source_connection


def connection(url, remaining):
    return source_connection(url, remaining, invalid='T4_URL', unavailable='T4_NETWORK')


def read(url, deadline, cancelled):
    def remaining():
        if cancelled():
            raise LibraryError('T4_CANCELLED')
        value = deadline - time.monotonic()
        if value <= 0:
            raise LibraryError('T4_TIMEOUT')
        return min(value, 6)

    conn, target = connection(url, remaining)
    try:
        conn.request('GET', target, headers={
            'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'})
        reply = conn.getresponse()
        if reply.status in (401, 403):
            raise LibraryError('T4_AUTH')
        if 300 <= reply.status < 400:
            raise LibraryError('T4_REDIRECT')
        if reply.status != 200 or reply.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise LibraryError('T4_NETWORK')
        raw = bytearray()
        while True:
            remaining()
            chunk = reply.read1(min(65536, MAX_CATALOG_BYTES + 1 - len(raw)))
            if not chunk:
                return bytes(raw)
            raw.extend(chunk)
            if len(raw) > MAX_CATALOG_BYTES:
                raise LibraryError('T4_LIMIT')
    except (TimeoutError, socket.timeout):
        raise LibraryError('T4_TIMEOUT') from None
    except (HTTPException, OSError, UnicodeError):
        raise LibraryError('T4_NETWORK') from None
    finally:
        conn.close()


def _origin(url):
    u = urlsplit(url)
    return u.scheme, u.hostname, u.port or (443 if u.scheme == 'https' else 80)


def _opaque(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _item_id(value):
    # Never put URL-shaped IDs, credentials or command strings in playback IPC or history.
    if not isinstance(value, str) or not re.fullmatch(r'[\w.:-]{1,256}', value):
        raise LibraryError('T4_PLAY_UNSUPPORTED')
    return value


def selection(site, item_id, line, episode):
    return dict(kind='t4', site=_opaque(site['key']), item=_item_id(item_id), line=_opaque(line), episode=_opaque(episode))


def resolve_selected(source, choice, *, deadline=None, cancelled=lambda: False, fetch=None):
    """Host-only exact re-resolution. Never accepts a client-supplied URL, header or title."""
    if (source.kind != 't4' or not isinstance(choice, dict) or
            set(choice) != {'kind', 'site', 'item', 'line', 'episode'} or choice['kind'] != 't4' or
            any(not isinstance(choice[k], str) or not re.fullmatch('[0-9a-f]{64}', choice[k])
                for k in ('site', 'line', 'episode'))):
        raise LibraryError('T4_CHANGED')
    item_id = _item_id(choice['item'])
    sites = [s for s in source.metadata['sites'] if _opaque(s['key']) == choice['site']]
    if len(sites) != 1:
        raise LibraryError('T4_CHANGED')
    end = deadline if deadline is not None else time.monotonic() + 15
    site = sites[0]
    client = t4.Client(site, fetch or (lambda url: read(url, end, cancelled)))
    for name, episodes in client.detail(item_id):
        if _opaque(name) != choice['line']:
            continue
        for title, episode in episodes:
            if _opaque(episode) == choice['episode']:
                url, headers = client.play(name, episode)
                if _origin(url) != _origin(site['api']):
                    raise LibraryError('T4_MEDIA_ORIGIN')
                return url, headers, title
    raise LibraryError('T4_CHANGED')
