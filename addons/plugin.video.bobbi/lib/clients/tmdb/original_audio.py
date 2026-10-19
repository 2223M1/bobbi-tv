"""Original-language evidence: cache-only on open, no work/language guesses."""
import json
from time import time

from bobbi_core.original_audio import fresh, from_record, from_successful_cache


def _fields(raw, kind):
    from lib.api.tmdbv3api.as_obj import AsObj
    if not isinstance(raw, (dict, AsObj)):
        return None
    keys = ('id', 'title' if kind == 'movie' else 'name', 'original_language', 'success', 'error', 'errors')
    return {key: raw.get(key) for key in keys if key in raw.keys()}


def cached_hint(data, request_id):
    try:
        from lib.api.tmdbv3api.tmdb import TMDb
        from lib.db.cached import cache
        if type(data) is not dict or data.get('selection_policy') != 'exact':
            return None
        kind = {'movie': 'movie', 'movies': 'movie', 'tv': 'tv', 'tvshows': 'tv'}.get(data.get('mode'))
        identifier = (data.get('ids') or {}).get('tmdb_id')
        if type(identifier) not in (int, str) or not str(identifier).isdigit() or int(identifier) < 1 or not kind:
            return None
        identifier, locale = int(identifier), TMDb().language
        if kind == 'movie':
            from lib.clients.tmdb.movie_details_guard import valid
            # get() enforces the existing configured cache expiry. Do not infer
            # a fetch time, renew it, or promote a legacy fallback into evidence.
            raw = cache.get(key='movie-years303|movie_details|{}|{}'.format(identifier, locale))
            if not valid({'id': identifier}, raw):
                return None
            return from_successful_cache(_fields(raw, kind), kind, identifier, request_id, time())
        records = []
        for key_id in (identifier, str(identifier)):
            key = 'am6b_details283|' + json.dumps(['tv_details', {'id': key_id}, locale], sort_keys=True)
            saved = cache.get(key=key)
            if type(saved) is dict:
                record = dict(fetched=saved.get('fetched'), data=_fields(saved.get('data'), kind))
                if fresh(record['fetched'], time()):
                    records.append(record)
        if not records:
            return None
        records.sort(key=lambda row: row['fetched'], reverse=True)
        if any(row != records[0] for row in records[1:] if row['fetched'] == records[0]['fetched']):
            return None
        return from_record(records[0], kind, identifier, request_id, time())
    except Exception:
        return None
