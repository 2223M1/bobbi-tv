"""Cache-only UI projection and bounded background TMDb enrichment."""
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode

from lib.cinema.frontend_contract import chinese, clean_title, image_url, integer, season_name, text, translations

PREFIX = 'bobi_frontend_v1:'
WAKE = 'Bobi.Metadata.WakeUntil'
_pending = {}


def _record(key):
    from lib.db.cached import cache
    try:
        value = cache.get(PREFIX + key)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _cached(key, urgent=False):
    record = _record(key)
    if record.get('refresh_after', 0) <= time.time():
        _pending[key] = _pending.get(key, False) or urgent
    return record.get('data') or {}


def source_window(info):
    from lib.cinema.source_presentation import window_fields
    ids = info.get('ids') or {}
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except ValueError:
            ids = {}
    ids = ids if isinstance(ids, dict) else {}
    identifier = integer(ids.get('tmdb_id') or info.get('tmdb_id'))
    mode = info.get('mode') or info.get('media_type')
    kind = 'movie' if mode in ('movies', 'movie') else 'tv' if mode in ('tv', 'tvshow', 'episode', 'anime') else ''
    details, season_details = {}, {}
    if identifier and kind:
        details = _cached('{}:{}'.format(kind, identifier), urgent=True)
        tv = info.get('tv_data') if isinstance(info.get('tv_data'), dict) else {}
        season = integer(tv.get('season'))
        if kind == 'tv' and season is not None:
            season_details = _cached('tv:{}:season:{}'.format(identifier, season), urgent=True)
    return window_fields(info, details, season_details)


def apply(item, identifier, mode, data=None, titles=None):
    """Set display metadata only; caller owns route/payload/search identity."""
    data, titles = data or {}, titles or {}
    identifier = integer(identifier)
    if mode not in ('movie', 'movies', 'tv', 'tvshow', 'season', 'episode'):
        return
    kind = 'movie' if mode in ('movie', 'movies') else 'tv'
    urgent = bool(data.get('continue_watching') or data.get('ready'))
    details = _cached('{}:{}'.format(kind, identifier), urgent=urgent) if identifier else {}
    verified = translations(details, kind) if details else {}
    zh = verified.get('zh') or chinese(clean_title(titles.get('zh')))
    en = verified.get('en') or clean_title(titles.get('en'))
    if identifier and (not zh or not en):
        from lib.db.cached import cache
        pair = cache.get('am6b_anime_titles_v1|{}|{}'.format(kind, identifier))
        if isinstance(pair, dict):
            zh = zh or chinese(clean_title(pair.get('zh')))
            en = en or clean_title(pair.get('en'))
    original = text(details.get('original_title') or details.get('original_name')
                    or data.get('original_title') or data.get('original_name'))
    work = zh or clean_title(data.get('show_title') or data.get('title') or data.get('name')) or en or original
    tag = item.getVideoInfoTag()
    dbtype = 'movie' if kind == 'movie' else mode if mode in ('season', 'episode') else 'tvshow'
    tag.setMediaType(dbtype)
    for language, value in (('zh', zh), ('en', en)):
        item.setProperty('Bobi.Title.' + language, value)
        item.setProperty('AM6B.Title.' + language, value)
    if original:
        tag.setOriginalTitle(original)
        item.setProperty('AM6B.Title.original', original)
    if en:
        item.setLabel2(en)
    if kind == 'tv':
        tag.setTvShowTitle(work)
    season = integer(data.get('season', data.get('season_number')))
    episode = integer(data.get('episode', data.get('episode_number')))
    season_data, ep_data = {}, {}
    if kind == 'tv' and season is not None:
        tag.setSeason(season)
        if identifier and dbtype in ('episode', 'season'):
            season_data = _cached('tv:{}:season:{}'.format(identifier, season), urgent=urgent)
        if episode is not None:
            tag.setEpisode(episode)
            ep_data = next((e for e in season_data.get('episodes', []) if e.get('episode_number') == episode), {})
        name = season_name(season_data.get('name') or data.get('season_name'))
        item.setProperty('Bobi.SeasonName', name)
    if dbtype == 'episode':
        title = text(ep_data.get('name') or data.get('episode_title') or data.get('name'))
        tag.setTitle(title)
        item.setLabel(work or title)
    elif dbtype == 'season':
        tag.setTitle(text(season_data.get('name') or data.get('name')) or work)
    else:
        tag.setTitle(work)
        item.setLabel(work)
    poster = image_url(season_data.get('poster_path') or details.get('poster_path') or data.get('poster_path') or data.get('poster'), 'w342')
    fanart = image_url(details.get('backdrop_path') or data.get('backdrop_path') or data.get('fanart'), 'w1280')
    still = image_url(ep_data.get('still_path') or data.get('still_path'), 'w780')
    art = {k: v for k, v in dict(poster=poster, fanart=fanart).items() if v}
    if dbtype == 'episode' or data.get('continue_watching'):
        art.update({k: v for k, v in dict(landscape=still or fanart, thumb=still or fanart).items() if v})
    elif poster:
        art['thumb'] = poster
    if art:
        item.setArt(art)
    overview = ep_data.get('overview') or details.get('overview') or data.get('overview')
    if overview:
        tag.setPlot(overview)
    release = details.get('release_date') or details.get('first_air_date') or data.get('release_date') or data.get('first_air_date') or ''
    year = integer(release[:4]) if release else integer(data.get('year'))
    if year:
        tag.setYear(year)
    genres = [g.get('name') for g in details.get('genres', []) if isinstance(g, dict) and g.get('name')]
    if genres:
        tag.setGenres(genres)
    if details.get('vote_average') is not None:
        tag.setRating(float(details['vote_average']), votes=int(details.get('vote_count') or 0))


def _root():
    import xbmcvfs
    path = Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/frontend-metadata'))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


@contextmanager
def _lock(name):
    from bobbi_platform.instance_lock import InstanceLock
    lease = InstanceLock(_root() / (name + '.lock'))
    try:
        lease.acquire()
    except (BlockingIOError, PermissionError):
        yield False
        return
    try:
        yield True
    finally:
        lease.close()


def _valid_key(key):
    import re
    return isinstance(key, str) and bool(re.fullmatch(r'(?:movie:[1-9]\d{0,8}|tv:[1-9]\d{0,8}(?::season:\d{1,3})?)', key))


def _queue(add=(), take=False, urgent=()):
    with _lock('queue') as locked:
        if not locked:
            return None
        path = _root() / 'pending.json'
        try:
            value = json.loads(path.read_text()) if path.stat().st_size < 32768 else []
        except (ValueError, OSError):
            value = []
        value = value if isinstance(value, list) else []
        pending = list(dict.fromkeys(k for k in list(urgent) + value + list(add) if _valid_key(k)))[:160]
        selected = pending.pop(0) if take and pending else None
        if add or selected:
            fd, temporary = tempfile.mkstemp(prefix='.queue-', dir=str(path.parent))
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(pending, stream)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {'selected': selected, 'pending': pending}


def _wake():
    import xbmc
    import xbmcgui
    window = xbmcgui.Window(10000)
    try:
        if float(window.getProperty(WAKE) or 0) > time.monotonic():
            return
    except ValueError:
        pass
    window.setProperty(WAKE, str(time.monotonic() + 45))
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.bobbi/?action=bobi_refresh_metadata)')


def flush():
    """One short queue transaction after a directory, no foreground HTTP."""
    try:
        if _pending:
            result = _queue(list(_pending), urgent=[k for k, value in _pending.items() if value])
            if result is not None:
                _pending.clear()
                _wake()
    except Exception:
        pass


def _fetch(key):
    from lib.api.tmdbv3api.tmdb import TMDb

    class Client(TMDb):
        _session = None
        REQUEST_TIMEOUT = (2, 4)
        MAX_GET_ATTEMPTS = 1

    parts = key.split(':')
    path = '/' + '/'.join(parts)
    # The stateless metadata transport owns/closes each HTTP connection in
    # fetch(). A TMDb subclass does not own a requests.Session to close here.
    result = Client(obj_cached=False)._request_obj(path, params=urlencode(dict(language='zh-CN', append_to_response='translations')), call_cached=False, add_lang=False)
    result = result.to_dict() if hasattr(result, 'to_dict') else result
    if not isinstance(result, dict) or (len(parts) == 2 and result.get('id') != int(parts[1])) or (len(parts) == 4 and result.get('season_number') != int(parts[3])):
        raise ValueError('METADATA_IDENTITY')
    return result


def hydrate(_params=None):
    import xbmc
    import xbmcgui
    from lib.db.cached import cache
    from lib.utils.tmdb_init import ensure_tmdb_init
    from lib.utils.kodi.logging import kodilog
    acquired = False
    completed = False
    updated = False
    try:
        with _lock('worker') as acquired:
            if not acquired:
                return False
            ensure_tmdb_init()
            deadline = time.monotonic() + 24
            for _ in range(20):
                if time.monotonic() + 6 > deadline:
                    break
                row = _queue(take=True)
                if not row or not row['selected']:
                    break
                key = row['selected']
                previous = _record(key)
                if previous.get('refresh_after', 0) > time.time():
                    continue
                try:
                    data = _fetch(key)
                    delay = 86400
                    updated = updated or data != previous.get('data')
                except Exception as error:
                    data, delay = previous.get('data'), 300
                    kodilog('Bobi metadata deferred {} {}'.format(key, type(error).__name__), xbmc.LOGWARNING)
                cache.set(PREFIX + key, dict(data=data, refresh_after=time.time() + delay), timedelta(days=7))
            completed = True
    finally:
        if acquired:
            window = xbmcgui.Window(10000)
            window.setProperty(WAKE, str(time.monotonic() + (0 if completed else 300)))
            remaining = _queue() if completed else None
            if remaining and remaining['pending']:
                _wake()
            elif updated and not xbmc.Player().isPlayingVideo() and xbmc.getCondVisibility('Window.IsActive(home)'):
                # No notification and no navigation; only the visible Home can refresh.
                xbmc.executebuiltin('Container.Refresh')
    return updated
