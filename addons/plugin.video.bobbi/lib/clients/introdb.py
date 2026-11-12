from datetime import timedelta
import json
import re

import requests

from lib.db.cached import MemoryCache
from lib.utils.kodi.utils import kodilog

INTRODB_BASE_URL = "http://api.introdb.app"
INTRODB_TIMEOUT = 5
INTRODB_CACHE_EXPIRY = timedelta(hours=24)
MAX_RESPONSE = 16384

_cache = MemoryCache(database="introdb")
_SENTINEL = "__introdb_none__"


def _segments(data):
    if type(data) is not dict:
        return None
    # Metadata is not version proof and is outside the owner segment contract.
    return {key: data[key] for key in ('intro', 'recap', 'outro') if key in data}


def get_segments(imdb_id, season, episode):
    """
    Fetch intro/recap/outro segment timestamps from IntroDB for a given episode.

    Results are cached in memory for 24 hours to avoid redundant API calls.

    Args:
        imdb_id: IMDb ID string (e.g., "tt0944947")
        season: Season number (int)
        episode: Episode number (int)

    Returns:
        dict with keys 'intro', 'recap', 'outro' (each a dict or None),
        or None if the request fails or no data is available.
    """
    if (type(imdb_id) is not str or not re.fullmatch(r'tt[0-9]{1,12}', imdb_id)
            or type(season) is not int or not 0 <= season <= 10000
            or type(episode) is not int or not 1 <= episode <= 100000):
        return None

    cache_key = f"{imdb_id}.S{season}E{episode}"
    request_params = {
        "imdb_id": imdb_id,
        "season": int(season),
        "episode": int(episode),
    }

    kodilog(f"IntroDB: get_segments called for {imdb_id} S{season}E{episode}")

    # Check cache first
    cached = _cache.get(cache_key)
    if cached is not None:
        if cached == _SENTINEL:
            kodilog(f"IntroDB: Cache hit (no data) for {imdb_id} S{season}E{episode}")
            return None
        return _segments(cached)

    response = None
    try:
        kodilog(
            f"IntroDB: Requesting /segments for {imdb_id} S{season}E{episode} with params {request_params}"
        )
        response = requests.get(
            f"{INTRODB_BASE_URL}/segments",
            params=request_params,
            timeout=INTRODB_TIMEOUT,
            stream=True,
        )
        kodilog(
            f"IntroDB: Response status {response.status_code} for {imdb_id} S{season}E{episode}"
        )

        if response.status_code == 404:
            kodilog(f"IntroDB: No segments found for {imdb_id} S{season}E{episode}")
            _cache.set(cache_key, _SENTINEL, expires=INTRODB_CACHE_EXPIRY)
            return None

        if response.status_code != 200:
            kodilog(
                f"IntroDB: Unexpected status {response.status_code} for {imdb_id} S{season}E{episode}"
            )
            return None

        body = bytearray()
        for chunk in response.iter_content(4096):
            if len(body) + len(chunk) > MAX_RESPONSE:
                return None
            body.extend(chunk)
        data = _segments(json.loads(body))
        if data is None:
            return None
        kodilog(
            f"IntroDB: Got segments for {imdb_id} S{season}E{episode}: "
            f"intro={'yes' if data.get('intro') else 'no'}, "
            f"recap={'yes' if data.get('recap') else 'no'}, "
            f"outro={'yes' if data.get('outro') else 'no'}"
        )
        _cache.set(cache_key, data, expires=INTRODB_CACHE_EXPIRY)
        return data

    except requests.exceptions.Timeout:
        kodilog(f"IntroDB: Request timed out for {imdb_id} S{season}E{episode}")
        return None
    except requests.exceptions.RequestException:
        kodilog("IntroDB: public segment request unavailable")
        return None
    except (ValueError, KeyError, TypeError):
        kodilog("IntroDB: invalid public segment response")
        return None
    finally:
        if response is not None:
            response.close()
