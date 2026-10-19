"""Bounded file-list recovery for an already registered MatriX.144.1 hash.

The upstream `get` action can reactivate a saved torrent asynchronously. Its
first response may therefore contain no file_stats. Poll that same identity;
never add, preload, drop, remove, stream or rewrite settings here. Reactivation
can contact BT peers, so this is metadata preparation, NOT a read-only device
audit operation. Call only from the preparation IO lane.
"""
import json
import re
import time
from urllib.parse import urlsplit

from bobbi_core.metadata_cache import BACKEND, LIMIT, normalized


def registered_metadata(session, endpoint, info_hash, cancelled=lambda: False,
                        clock=time.monotonic, sleep=time.sleep, budget=8.0):
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Explicit loopback TorrServer endpoint required')
    if not isinstance(info_hash, str) or not re.fullmatch('[0-9a-f]{40}', info_hash):
        raise ValueError('Normalized existing torrent identity required')
    if type(budget) not in (int, float) or not 0 < budget <= 8:
        raise ValueError('Metadata deadline may not be extended')
    endpoint = endpoint.rstrip('/')
    deadline, total = clock() + budget, 0

    def remaining():
        value = deadline - clock()
        if cancelled() or value <= 0:
            raise TimeoutError('Metadata recovery cancelled or expired')
        return value

    def read(response, limit):
        nonlocal total
        if response.status_code != 200:
            raise ValueError('Registered torrent/backend unavailable')
        raw = bytearray()
        for chunk in response.iter_content(16384):
            remaining()
            total += len(chunk)
            if len(raw) + len(chunk) > limit or total > LIMIT + 128:
                raise ValueError('Metadata recovery response budget exceeded')
            raw.extend(chunk)
        remaining()
        return bytes(raw)

    timeout = min(3.05, remaining())
    with session.get(endpoint + '/echo', timeout=(timeout, timeout), stream=True,
                     allow_redirects=False) as response:
        if read(response, 128).decode('utf-8').strip() != BACKEND:
            raise ValueError('TorrServer file-ID backend changed')
    # Finite calls as well as a monotonic deadline. A closed saved torrent is
    # given time to supply its real file list, not replaced by a partial ledger.
    for _ in range(16):
        timeout = min(3.05, remaining())
        with session.post(endpoint + '/torrents', json={'action': 'get', 'hash': info_hash},
                          timeout=(timeout, timeout), stream=True, allow_redirects=False) as response:
            result = json.loads(read(response, LIMIT))
        if isinstance(result, list) and len(result) == 1:
            result = result[0]
        if not isinstance(result, dict) or result.get('hash') != info_hash:
            raise ValueError('Torrent metadata identity mismatch')
        if result.get('file_stats'):
            # MatriX.144.1 Status returns exactly id/path/length per file. Strip
            # unrelated top-level state/URLs; retain the strict tuple contract.
            value, _ = normalized(result)
            remaining()
            return value
        if 'file_stats' in result and result['file_stats'] not in (None, []):
            raise ValueError('Malformed torrent file list')
        sleep(min(0.25, remaining()))
    raise TimeoutError('No complete registered torrent metadata within budget')
