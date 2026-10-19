"""Optional raw anime-release search, not ANI-RSS subscription/episode selection.

These are untrusted BT candidates. The caller MUST run the ordinary catalogue,
season/episode, ranking and selected-file gates. A Bangumi subject ID or fansub
label is never promoted to TMDb identity, playable readiness or subtitle proof.
"""
import base64
import json
import math
import re
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit

import requests

from lib.cinema import _shared  # load the declared shared-core dependency
from bobbi_core.search_completion import SearchCompletion, SearchResults
from lib.domain.torrent import TorrentStream


ENDPOINT = 'https://api.animes.garden/resources'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 200
BUDGET_SECONDS = 4.0


def query_plan(anime_queries):
    """Two ID-bound catalogue aliases; no per-fansub slots or title guessing."""
    if not isinstance(anime_queries, (list, tuple)):
        return []
    slots = {}
    for entry in anime_queries[:4]:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            continue
        language, title = entry
        if (language not in ('zh-CN', 'zh-TW', 'native', 'en', 'unknown')
                or not isinstance(title, str) or not 2 <= len(title.strip()) <= 512
                or any(ord(char) < 32 or ord(char) == 127 for char in title)):
            continue
        slots.setdefault(language, title.strip())
    ordered = []
    # Chinese-group releases often carry a different Taiwan/HK title and a
    # romanised name, but no native Japanese string. Do not spend their second
    # bounded slot on the native name while a trusted Chinese alias is missing.
    for language in ('zh-CN', 'zh-TW', 'native', 'en', 'unknown'):
        title = slots.get(language)
        if title and title.casefold() not in [value.casefold() for value in ordered]:
            ordered.append(title)
    if not ordered:
        return []
    return [ENDPOINT + '?' + urlencode(dict(search=title, page=1,
            pageSize=MAX_ROWS, duplicate='true')) for title in ordered[:2]]


def _info_hash(magnet):
    if (not isinstance(magnet, str) or len(magnet) > 8192
            or any(ord(char) < 33 or ord(char) == 127 for char in magnet)):
        raise ValueError('Invalid magnet')
    parts = urlsplit(magnet)
    if (parts.scheme != 'magnet' or parts.netloc or parts.path or parts.fragment):
        raise ValueError('Invalid magnet')
    hashes = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True, max_num_fields=64):
        if key.lower() != 'xt' or not value.lower().startswith('urn:btih:'):
            continue
        raw = value[9:]
        if re.fullmatch('[0-9a-fA-F]{40}', raw):
            hashes.append(raw.lower())
        elif re.fullmatch('[A-Za-z2-7]{32}', raw):
            hashes.append(base64.b32decode(raw.upper()).hex())
        else:
            raise ValueError('Invalid BTIH')
    if not hashes or len(set(hashes)) != 1:
        raise ValueError('Missing or conflicting BTIH')
    return hashes[0]


def parse_page(content):
    """Return candidates, pagination completeness and malformed-row count."""
    if not isinstance(content, bytes) or len(content) > MAX_RESPONSE_BYTES:
        raise ValueError('Resource response exceeds byte budget')
    payload = json.loads(content.decode('utf-8'))
    if (not isinstance(payload, dict) or payload.get('status') != 'OK'
            or not isinstance(payload.get('resources'), list)
            or len(payload['resources']) > MAX_ROWS):
        raise ValueError('Invalid resource envelope')
    pagination = payload.get('pagination')
    if (not isinstance(pagination, dict) or type(pagination.get('page')) is not int
            or pagination['page'] != 1 or type(pagination.get('pageSize')) is not int
            or not 1 <= pagination['pageSize'] <= MAX_ROWS
            or type(pagination.get('complete')) is not bool):
        raise ValueError('Missing bounded pagination receipt')
    rows, rejected = [], 0
    for entry in payload['resources']:
        try:
            if not isinstance(entry, dict):
                raise ValueError('Invalid resource')
            # The upstream labels real anime season packs as 合集. Neither
            # category is identity/file proof: the common gates still decide.
            # Audio, manga, games and unclassified results stay out.
            if entry.get('type') not in ('动画', '合集'):
                continue
            title = entry.get('title')
            size = entry.get('size')
            origin = entry.get('provider')
            if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 2048
                    or any(ord(char) < 32 or ord(char) == 127 for char in title)
                    or type(size) is not int or not 0 <= size < 2 ** 63
                    or not isinstance(origin, str)
                    or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', origin)):
                raise ValueError('Invalid resource fields')
            info_hash = _info_hash(entry.get('magnet'))
            published = entry.get('createdAt', '')
            if not isinstance(published, str) or len(published) > 40:
                published = ''
            rows.append(TorrentStream(title=title.strip(), type='Torrent',
                indexer='AnimeGarden', subindexer=origin, provider='AnimeGarden',
                guid='animegarden:' + info_hash, infoHash=info_hash, size=size,
                url='magnet:?xt=urn:btih:' + info_hash, publishDate=published))
        except (ValueError, TypeError):
            rejected += 1
    return rows, pagination['complete'], rejected


def find_sources(ids, mode, anime_queries, deadline, cancelled):
    """Supplement an existing search, with a cancellable four-second ceiling.

    Only the catalogue's anime alias builder may supply anime_queries. This
    function never resolves an inferred BGM/TMDb mapping or bypasses normal
    admission. It neither downloads torrents/media nor creates cloud tasks.
    """
    from lib.clients.jackett_fanout import fetch_independent
    urls = query_plan(anime_queries)
    valid_id = (isinstance(ids, dict)
                and re.fullmatch('[1-9][0-9]{0,9}', str(ids.get('tmdb_id', ''))))
    if mode != 'tv' or not valid_id or not urls:
        return SearchResults([], SearchCompletion())
    cancelled_fn = cancelled.is_set
    if cancelled_fn():
        return SearchResults([], SearchCompletion(len(urls), skipped=len(urls)))
    if not isinstance(deadline, (float, int)) or not math.isfinite(deadline) or deadline <= monotonic():
        return SearchResults([], SearchCompletion(len(urls), timed_out=len(urls)))
    with requests.Session() as session:
        session.headers['User-Agent'] = 'AM6B-AnimeGarden/1.0'
        responses = fetch_independent(session, urls, budget=BUDGET_SECONDS,
            deadline=deadline, cancelled=cancelled_fn, mode='json',
            max_response_bytes=MAX_RESPONSE_BYTES, request_timeout=None)
    if not isinstance(responses, SearchResults) or responses.completion.succeeded != len(responses):
        # A custom/legacy transport without a receipt cannot claim completeness.
        return SearchResults([], SearchCompletion(len(urls), failed=len(urls)))
    if cancelled_fn():
        return SearchResults([], SearchCompletion(len(urls), skipped=len(urls)))
    rows, parse_failures, omitted_pages = [], 0, 0
    for response in responses:
        try:
            if response.status_code != 200:
                raise ValueError('Resource HTTP status changed')
            candidates, complete, malformed = parse_page(response.content)
            rows.extend(candidates)
            parse_failures += int(bool(malformed))
            # Record one discovered continuation deliberately outside this
            # bounded plan. A truncated page must never make a full cache.
            omitted_pages += int(not complete)
        except (ValueError, UnicodeError, TypeError, AttributeError, RecursionError):
            parse_failures += 1
    completion = responses.completion.with_parse_failures(parse_failures)
    if omitted_pages:
        completion = completion.combine(SearchCompletion(omitted_pages, skipped=omitted_pages))
    # Exact swarm equality only: different encodes/subtitle editions, groups,
    # repacks, single episodes and packs remain distinct for manual selection.
    unique = {}
    for row in rows:
        unique.setdefault(row.infoHash, row)
    return SearchResults(unique.values(), completion)
