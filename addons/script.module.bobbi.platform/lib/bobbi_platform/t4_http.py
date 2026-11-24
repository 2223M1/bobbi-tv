"""Bounded JSON transport for explicitly approved T4 origins; no redirects/cookies/proxy."""
from http.client import HTTPException
import hashlib
import re
import socket
import time
from urllib.parse import urlsplit

from bobbi_core.bounded_http import AttemptCancelled, AttemptHandle, bind_connection
from bobbi_core.library_contract import MAX_CATALOG_BYTES, LibraryError
from bobbi_core import t4
from .source_media_http import connection as source_connection


def connection(url, remaining, *, attempt=None, ssl_context=None):
    return source_connection(
        url,
        remaining,
        invalid='T4_URL',
        unavailable='T4_NETWORK',
        attempt=attempt,
        ssl_context=ssl_context,
    )


def _origin(url):
    u = urlsplit(url)
    return u.scheme.lower(), (u.hostname or '').lower(), u.port or (443 if u.scheme.lower() == 'https' else 80)


def read(url, deadline, cancelled, *, headers=None, expected_origin=None, ssl_context=None):
    def remaining():
        if cancelled():
            raise LibraryError('T4_CANCELLED')
        value = deadline - time.monotonic()
        if value <= 0:
            raise LibraryError('T4_TIMEOUT')
        return min(value, 6)

    req_headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'identity',
        'Connection': 'close',
    }
    if headers:
        # Custom site headers may ONLY be sent to the site's own API origin (R13-03).
        if expected_origin is not None and _origin(url) == _origin(expected_origin):
            cleaned = t4.validate_headers(headers, allowed_hosts=(urlsplit(expected_origin).netloc,))
            req_headers.update(cleaned)

    with AttemptHandle(deadline=deadline, cancelled=cancelled) as attempt:
        if connection is _DEFAULT_CONNECTION:
            conn, target = connection(url, remaining, attempt=attempt, ssl_context=ssl_context)
        else:
            conn, target = connection(url, remaining)
        bind_connection(conn, attempt)
        try:
            conn.request('GET', target, headers=req_headers)
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
                    attempt.finish()
                    return bytes(raw)
                raw.extend(chunk)
                if len(raw) > MAX_CATALOG_BYTES:
                    raise LibraryError('T4_LIMIT')
        except LibraryError:
            raise
        except AttemptCancelled:
            raise LibraryError('T4_CANCELLED') from None
        except (TimeoutError, socket.timeout):
            raise LibraryError('T4_TIMEOUT') from None
        except (HTTPException, OSError, UnicodeError):
            if cancelled():
                raise LibraryError('T4_CANCELLED') from None
            if time.monotonic() >= deadline:
                raise LibraryError('T4_TIMEOUT') from None
            raise LibraryError('T4_NETWORK') from None
        finally:
            conn.close()


_DEFAULT_CONNECTION = connection


def _opaque(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _item_id(value):
    # Direct selection without T4TokenStore rejects URL-shaped/arbitrary IDs.
    if not isinstance(value, str) or not re.fullmatch(r'[\w.:-]{1,256}', value):
        raise LibraryError('T4_PLAY_UNSUPPORTED')
    return value


def selection(site, item_id, line, episode):
    return dict(
        kind='t4',
        site=_opaque(site['key']),
        item=_item_id(item_id),
        line=_opaque(line),
        episode=_opaque(episode),
    )


def selection_with_token(site, item_token, line_hash_or_name, episode_hash_or_id, *, prehashed=False):
    if not isinstance(item_token, str) or not re.fullmatch(r'[0-9a-f]{32}', item_token):
        raise LibraryError('T4_TOKEN_EXPIRED')
    lh = line_hash_or_name if prehashed else _opaque(line_hash_or_name)
    eh = episode_hash_or_id if prehashed else _opaque(episode_hash_or_id)
    if not re.fullmatch(r'[0-9a-f]{64}', lh) or not re.fullmatch(r'[0-9a-f]{64}', eh):
        raise LibraryError('T4_CHANGED')
    return dict(
        kind='t4',
        site=_opaque(site['key']),
        item_token=item_token,
        line=lh,
        episode=eh,
    )


def _media_origin_allowed(url: str, site: dict, approved_origins: set[str]) -> bool:
    u_orig = _origin(url)
    api_orig = _origin(site['api'])
    if u_orig == api_orig:
        return True
    u_parts = urlsplit(url)
    api_parts = urlsplit(site['api'])
    u_host = (u_parts.hostname or '').lower()
    api_host = (api_parts.hostname or '').lower()
    if u_parts.scheme.lower() == 'https' and api_host and u_host.endswith('.' + api_host):
        return True
    canonical = f'{u_parts.scheme.lower()}://{u_parts.netloc.lower()}'
    return canonical in approved_origins


def resolve_selected(
    source,
    choice,
    *,
    generation: str = '',
    token_store=None,
    deadline=None,
    cancelled=lambda: False,
    fetch=None,
):
    """Host-only exact re-resolution. Never accepts a client-supplied URL, header or title."""
    if source.kind != 't4' or not isinstance(choice, dict) or choice.get('kind') != 't4':
        raise LibraryError('T4_CHANGED')
    keys = set(choice)
    if keys == {'kind', 'site', 'item', 'line', 'episode'}:
        use_token = False
    elif keys == {'kind', 'site', 'item_token', 'line', 'episode'}:
        use_token = True
    else:
        raise LibraryError('T4_CHANGED')

    if any(
        not isinstance(choice[k], str) or not re.fullmatch('[0-9a-f]{64}', choice[k])
        for k in ('site', 'line', 'episode')
    ):
        raise LibraryError('T4_CHANGED')

    if use_token:
        if token_store is None or not generation:
            raise LibraryError('T4_TOKEN_EXPIRED')
        item_id = token_store.get_item(source.id, generation, choice['site'], choice['item_token'])
    else:
        item_id = _item_id(choice['item'])

    sites = [s for s in source.metadata['sites'] if _opaque(s['key']) == choice['site']]
    if len(sites) != 1:
        raise LibraryError('T4_CHANGED')
    end = deadline if deadline is not None else time.monotonic() + 15
    site = sites[0]
    site_headers = site.get('headers')
    default_fetch = (
        (lambda u: read(u, end, cancelled, headers=site_headers, expected_origin=site['api']))
        if site_headers
        else (lambda u: read(u, end, cancelled))
    )
    client = t4.Client(site, fetch or default_fetch)
    approved = token_store.approved_origins(source.id, generation) if (token_store and generation) else set()
    for name, episodes in client.detail(item_id):
        if _opaque(name) != choice['line']:
            continue
        for title, episode in episodes:
            if _opaque(episode) == choice['episode']:
                url, play_headers = client.play(name, episode)
                if not _media_origin_allowed(url, site, approved):
                    raise LibraryError('T4_MEDIA_ORIGIN')
                if _origin(url) != _origin(site['api']):
                    # Cross-origin approved CDN never receives Referer pointing at private T4 API
                    play_headers = {
                        k: v for k, v in play_headers.items() if k.lower() != 'referer'
                    }
                return url, play_headers, title
    raise LibraryError('T4_CHANGED')
