"""Explicit peer-metadata admission for one discovered public info hash.

This MAY add/reactivate a torrent in box memory. It does not preload/stream any
video, persist to the TorrServer library, drop another torrent or submit to 115.
The MatriX.144.1 AddTorrent/NewTorrent implementation deduplicates by info hash.
The caller must use the one preparation IO lane, not an audit/UI request.
"""
import json
import re
import time
from urllib.parse import urlsplit

from bobbi_core.metadata_cache import BACKEND, LIMIT, normalized
from bobbi_core.torrent_metadata import registered_metadata


def candidate_metadata(session, endpoint, source, cancelled=lambda: False, budget=8.0):
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source)):
        raise ValueError('Exact loopback provider and info hash required')
    if type(budget) not in (int, float) or not 0 < budget <= 8:
        raise ValueError('Fixed metadata budget required')
    endpoint, deadline = endpoint.rstrip('/'), time.monotonic() + budget
    def remaining():
        left = deadline - time.monotonic()
        if cancelled() or left <= 0: raise TimeoutError('Candidate metadata cancelled/deadline')
        return left
    def read(response, limit):
        if response.status_code != 200: raise ValueError('Candidate metadata HTTP status')
        data = bytearray()
        for chunk in response.iter_content(16384):
            remaining()
            if len(data) + len(chunk) > limit: raise ValueError('Candidate metadata byte budget')
            data.extend(chunk)
        remaining()
        return bytes(data)
    timeout = min(3.05, remaining())
    with session.get(endpoint + '/echo', timeout=(timeout, timeout), stream=True, allow_redirects=False) as response:
        if read(response, 128).decode().strip() != BACKEND:
            raise ValueError('Unreviewed backend cannot admit metadata')
    timeout = min(3.05, remaining())
    with session.post(endpoint + '/settings', json={'action': 'get'}, timeout=(timeout, timeout), stream=True,
                      allow_redirects=False) as response:
        settings = json.loads(read(response, 65536))
    # Upstream add refreshes DLNA when enabled. Never take that side path or
    # allocate a disk video cache while discovering a future candidate.
    if (not isinstance(settings, dict) or settings.get('EnableDLNA') is not False
            or settings.get('UseDisk') is not False or settings.get('DisableUPNP') is not True
            or type(settings.get('TorrentDisconnectTimeout')) is not int
            or not 1 <= settings['TorrentDisconnectTimeout'] <= 60):
        raise ValueError('Torrent side-effect profile changed; no add')
    timeout = min(3.05, remaining())
    try:
        with session.post(endpoint + '/torrents', json={'action': 'add', 'link': 'magnet:?xt=urn:btih:' + source,
                           'save_to_db': False}, timeout=(timeout, timeout), stream=True, allow_redirects=False) as response:
            metadata = json.loads(read(response, LIMIT))
        if not isinstance(metadata, dict) or metadata.get('hash') != source:
            raise ValueError('Added candidate returned a different identity')
        if metadata.get('file_stats'):
            result, _ = normalized(metadata)
            remaining()
            return result
    except OSError:
        # Possibly added already. Do not replay add on timeout: inspect the
        # same hash within the remaining budget. This is not cloud submission.
        remaining()
    return registered_metadata(session, endpoint, source, cancelled, budget=remaining())
