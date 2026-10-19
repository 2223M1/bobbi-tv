"""Cache-only TV negative evidence. No fetch and no per-card cache reads."""
import json
from time import time

from bobbi_core.tv_ended_window import from_details


def cached_window(ids, tv_data, release_order=None):
    from lib.api.tmdbv3api.tmdb import TMDb
    from lib.db.cached import cache
    from lib.api.tmdbv3api.as_obj import AsObj
    if not isinstance(ids, dict) or not isinstance(tv_data, dict):
        return None
    try:
        identifier = ids.get('tmdb_id')
        if type(identifier) not in (int, str) or int(identifier) <= 0:
            return None
        identifier = int(identifier)
        records = []
        for key_id in (identifier, str(identifier)):
            key = 'am6b_details283|' + json.dumps(['tv_details', {'id': key_id}, TMDb().language], sort_keys=True)
            record = cache.get(key)
            if (type(record) is dict and type(record.get('fetched')) in (int, float)
                    and 0 <= time() - record['fetched'] < 24 * 3600):
                records.append(record)
        if not records:
            return None
        records.sort(key=lambda row: row['fetched'], reverse=True)
        # Do not copy credits, artwork, videos or the full detail response.
        fields = ('id', 'name', 'original_name', 'first_air_date', 'last_air_date', 'status',
            'in_production', 'next_episode_to_air', 'number_of_seasons', 'seasons',
            'translations', 'alternative_titles', 'error', 'errors', 'success')
        def relevant(raw):
            if not isinstance(raw, (dict, AsObj)):
                return None
            result = {key: raw.get(key) for key in fields if key in raw.keys()}
            for key, value in tuple(result.items()):
                if isinstance(value, AsObj):
                    result[key] = value.to_dict()
            return result
        details = relevant(records[0].get('data'))
        if details is None or any(relevant(row.get('data')) != details for row in records[1:]
                                  if row['fetched'] == records[0]['fetched']):
            return None
        saved_order = cache.get('bobi_episode_order_v1:' + str(identifier))
        if saved_order is not None and type(saved_order) is not dict:
            return None
        order = saved_order.get('order') if isinstance(saved_order, dict) else None
        return from_details(details, identifier, tv_data.get('season', 1), tv_data.get('episode', 1),
            order=order, release_order=release_order)
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        return None
