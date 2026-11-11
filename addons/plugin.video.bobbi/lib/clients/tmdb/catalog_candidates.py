"""Descriptive catalog suggestions using the existing TMDb cache/transport.

No provider locator, account, URL resolution, transfer or playback crosses this
boundary. A suggestion must still go through the ordinary review CAS contract.
"""
from copy import deepcopy
import json
import re
import time
from uuid import uuid4

MAX_GROUP = 100


def parameters(value):
    if type(value) is not dict or set(value) - {'query', 'media_kind', 'year'}:
        raise ValueError('CATALOG_CANDIDATE_INVALID')
    query = value.get('query')
    kind, year = value.get('media_kind'), value.get('year')
    if (type(query) is not str or not 1 <= len(query.strip()) <= 120 or
            re.search(r'[\x00-\x1f\x7f/\\]', query) or '://' in query or
            kind not in (None, 'movie', 'tv') or
            year is not None and (type(year) is not int or not 1870 <= year <= 2200)):
        raise ValueError('CATALOG_CANDIDATE_INVALID')
    return dict(query=query.strip(), media_kind=kind, year=year)


def query_hint(name):
    """A local editable title hint, never a confirmed work identity."""
    from bobbi_core.filename_semantics import parse_filename
    name = str(name or '').replace('\\', '/').rsplit('/', 1)[-1]
    parsed = parse_filename(name)
    stops = [match.start() for match in parsed.markers] + [span[0] for span in parsed.technical_spans]
    if stops:
        name = name[:min(stops)]
    name = re.sub(r'\.[a-zA-Z0-9]{2,5}$', '', name)
    name = re.sub(r'(?<!\d)(?:19|20)\d{2}(?!\d)', '', name)
    name = re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', name)
    return re.sub(r'[._\s-]+', ' ', name).strip()[:120]


def search(query, media_kind=None, year=None, *, deadline=None, cancelled=lambda: False, fetch=None):
    from bobbi_core.metadata_transport import request_budget
    params = parameters(dict(query=query, media_kind=media_kind, year=year))
    deadline = min(deadline, time.monotonic() + 6) if deadline is not None else time.monotonic() + 6
    if cancelled() or time.monotonic() >= deadline:
        raise ValueError('CATALOG_CANDIDATE_CANCELED')
    if fetch is None:
        from lib.clients.tmdb.utils.utils import tmdb_get
        fetch = tmdb_get
    # Search all types once: movie/tv with an identical numeric ID stay distinct.
    try:
        with request_budget(deadline, cancelled, quiet=True):
            response = fetch('search_multi', {'query': params['query'], 'page': 1})
    except Exception:
        raise ValueError('CATALOG_CANDIDATE_UNAVAILABLE') from None
    if cancelled() or time.monotonic() >= deadline:
        raise ValueError('CATALOG_CANDIDATE_CANCELED')
    if hasattr(response, 'to_dict'):
        response = response.to_dict()
    rows = response.get('results', []) if isinstance(response, dict) else response or []
    candidates = []
    for raw in list(rows)[:20]:
        if hasattr(raw, 'to_dict'):
            raw = raw.to_dict()
        if not isinstance(raw, dict):
            continue
        kind, identifier = raw.get('media_type'), raw.get('id')
        if kind not in ('movie', 'tv') or type(identifier) is not int or not 0 < identifier < 2**31:
            continue
        title = raw.get('title') if kind == 'movie' else raw.get('name')
        original = raw.get('original_title') if kind == 'movie' else raw.get('original_name')
        if not isinstance(title, str) or not title.strip() or len(title) > 240 or '://' in title:
            continue
        original = original if isinstance(original, str) and len(original) <= 240 and '://' not in original else ''
        date = raw.get('release_date' if kind == 'movie' else 'first_air_date') or ''
        found_year = int(date[:4]) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(date)) else None
        reasons = ['TMDb 搜索建议，尚未确认']
        mismatch = False
        if year is not None and year != found_year:
            reasons.append('年份不同或未知，请核对重制版本');mismatch = True
        if media_kind is not None and media_kind != kind:
            reasons.append('作品类型不同，请核对电影 / 剧集');mismatch = True
        poster = raw.get('poster_path')
        poster = poster if isinstance(poster, str) and re.fullmatch(r'/[A-Za-z0-9_-]{1,100}\.(?:jpg|png)', poster) else None
        candidates.append(dict(media_kind=kind, tmdb_id=identifier, title=title.strip(), original_title=original,
            year=found_year, poster_path=poster, basis='；'.join(reasons), mismatch=mismatch))
    candidates.sort(key=lambda candidate: candidate['mismatch'])
    return dict(items=candidates[:5])


def candidate_mapping(candidate, item):
    """Return a manual proposal; unknown/multi episodes stay unselected."""
    from bobbi_core.catalog_review import mapping
    evidence = (item.get('candidates') or [{}])[0]
    kind = candidate['media_kind']
    value = dict(kind=kind, title=candidate['title'], tmdb_id=candidate['tmdb_id'],
                 season=evidence.get('season') if kind == 'tv' else None,
                 episode=evidence.get('episode') if kind == 'tv' else None, version=None)
    return mapping(value)


def plan(entries):
    """Independent immutable-by-copy chunks, including the complete HTTP envelope."""
    from bobbi_core.catalog_review import command
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_GROUP:
        raise ValueError('CATALOG_BATCH_LIMIT')
    chunks, current = [], None
    for entry in entries:
        item = dict(name=entry['name'], command=command(entry['command']))
        if current is None:
            current = dict(request_id=uuid4().hex, entries=[])
        trial = current['entries'] + [item]
        envelope = dict(action='catalog_apply', params=dict(request_id=current['request_id'],
                        commands=[row['command'] for row in trial]))
        size = len(json.dumps(envelope, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        if len(trial) > 5 or size > 8192:
            if not current['entries']:
                raise ValueError('CATALOG_BATCH_LIMIT')
            chunks.append(current);current = dict(request_id=uuid4().hex, entries=[])
            # A single entry is bounded by the mapping schema, but validate the
            # exact envelope again instead of relying on that implementation detail.
            envelope['params'] = dict(request_id=current['request_id'], commands=[item['command']])
            if len(json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 8192:
                raise ValueError('CATALOG_BATCH_LIMIT')
        current['entries'].append(deepcopy(item))
    if current:
        chunks.append(current)
    return deepcopy(chunks)
