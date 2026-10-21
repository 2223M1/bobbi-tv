"""Cache-only canonical single-season evidence for unseasoned subtitle names."""
import json
import time


def cached_scope(identifier):
    if type(identifier) is not int or identifier <= 0:
        return None
    try:
        from bobbi_core.subtitle_episode import from_details
        from lib.api.tmdbv3api.as_obj import AsObj
        from lib.api.tmdbv3api.tmdb import TMDb
        from lib.clients.tmdb.detail_cache import STALE, valid
        from lib.db.cached import cache
        records=[]
        for key_id in (identifier,str(identifier)):
            key='am6b_details283|'+json.dumps(['tv_details',{'id':key_id},TMDb().language],sort_keys=True)
            saved=cache.get(key=key)
            if not isinstance(saved,dict) or type(saved.get('fetched')) not in (int,float):
                continue
            if not 0 <= time.time()-saved['fetched'] <= STALE:
                continue
            data=saved.get('data')
            if isinstance(data,AsObj):data=data.to_dict()
            if valid('tv_details',{'id':identifier},data):records.append((saved['fetched'],data))
        if not records:return None
        records.sort(key=lambda row:row[0],reverse=True)
        if any(row[1]!=records[0][1] for row in records[1:] if row[0]==records[0][0]):return None
        return from_details(records[0][1],identifier)
    except (ImportError,OSError,ValueError,TypeError,AttributeError):
        return None
