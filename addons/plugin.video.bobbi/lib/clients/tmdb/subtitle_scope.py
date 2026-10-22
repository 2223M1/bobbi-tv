"""Read title and single-season evidence from one ID-checked cached TV detail."""
import json
import time


def cached_identity(identifier):
    if type(identifier) is not int or identifier <= 0:
        return None
    try:
        from bobbi_core.subtitle_episode import from_details
        from bobbi_core.episode_identity import catalog_identity
        from bobbi_core.subtitle_candidates import titles_from_catalog
        from lib.api.tmdbv3api.as_obj import AsObj
        from lib.api.tmdbv3api.tmdb import TMDb
        from lib.clients.tmdb.detail_cache import STALE, valid
        from lib.db.cached import cache
        records=[]
        now = time.time()
        for key_id in (identifier,str(identifier)):
            key='am6b_details283|'+json.dumps(['tv_details',{'id':key_id},TMDb().language],sort_keys=True)
            saved=cache.get(key=key)
            if not isinstance(saved,dict) or type(saved.get('fetched')) not in (int,float):
                continue
            # Compare before arithmetic: huge JSON integers cannot be safely
            # subtracted from a float clock. NaN/infinity also fail this window.
            if not now - STALE <= saved['fetched'] <= now:
                continue
            data=saved.get('data')
            if isinstance(data,AsObj):data=data.to_dict()
            if (isinstance(data, dict) and type(data.get('id')) is int and data['id'] == identifier
                    and valid('tv_details', {'id': identifier}, data)):
                alternatives = data.get('alternative_titles')
                # Match the existing BT cache producer: complete alternative-title
                # coverage first, then freshness; never merge different details.
                coverage = (2 if isinstance(alternatives, dict)
                    and isinstance(alternatives.get('results'), list) else
                    1 if saved.get('tv_aliases_requested') is True else 0)
                records.append((coverage, saved['fetched'], data))
        if not records:return None
        records.sort(key=lambda row: row[:2], reverse=True)
        if any(row[2] != records[0][2] for row in records[1:] if row[:2] == records[0][:2]):
            return None
        details = records[0][2]
        scope = from_details(details, identifier)
        # Alias coverage does not grant season authority over equally current
        # or newer details. Another valid cache may veto this one-season proof
        # without discarding the selected response's independent work names.
        if scope is not None and any(row[1] >= records[0][1]
                and from_details(row[2], identifier) != scope for row in records[1:]):
            scope = None
        return dict(titles=titles_from_catalog('tv', catalog_identity(details, identifier)),
                    scope=scope)
    except (ImportError,OSError,ValueError,TypeError,AttributeError):
        return None


def cached_scope(identifier):
    identity = cached_identity(identifier)
    return identity['scope'] if identity else None
