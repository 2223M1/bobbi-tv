"""Cached season-card artwork with one bounded, background-only metadata worker.

Cards never fetch details while rendering. This is presentation data only: no
playback route, library identity, search title or episode order is rewritten.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Lock
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from bobbi_core.image_cache import image_url as tmdb_image_url

from lib.clients.tmdb.season_card import latest_season, poster_path, title_for

MAX_QUEUE = 80
MAX_BATCH = 20
WORK_SECONDS = 24
WAKE_PROPERTY = 'AM6B.SeasonCards.WakeUntil'


def _id(value):
    if isinstance(value, bool):
        return 0
    text = str(value)
    return int(text) if text.isdecimal() and 0 < len(text) <= 9 and int(text) > 0 else 0


def _record(identifier):
    from lib.db.cached import cache
    try:
        value = cache.get('am6b_season_card_v1:' + str(identifier))
        if isinstance(value, dict) and value.get('schema') == 1 and value.get('tmdb_id') == identifier:
            return value
    except Exception:
        pass  # An optional presentation cache cannot make a catalogue fail.
    return {}


def cached_view(identifier):
    identifier = _id(identifier)
    record = _record(identifier) if identifier else {}
    try:
        if not 0 <= time.time() - float(record.get('observed_at', 0)) <= 7 * 86400:
            return None
    except (TypeError, ValueError):
        return None
    view = record.get('view')
    return view if (isinstance(view, dict) and view.get('tmdb_id') == identifier
                    and type(view.get('season')) is int and 0 < view['season'] <= 100) else None


def _fresh(identifier):
    try:
        return float(_record(identifier).get('refresh_after', 0)) > time.time()
    except (ValueError, TypeError):
        return False


def apply(item, identifier, series_title, english_title='', chinese_title=''):
    """Project cached art/title only. The caller retains its original URL."""
    view = cached_view(identifier)
    if not view:
        return False
    chinese_title = item.getProperty('Bobi.Title.zh') or chinese_title
    english_title = item.getProperty('Bobi.Title.en') or english_title
    series_title = chinese_title or series_title
    label = series_title
    item.setLabel(label)
    tag = item.getVideoInfoTag()
    tag.setTitle(label)
    tag.setTvShowTitle(series_title)
    tag.setSeason(view['season'])
    from lib.cinema.frontend_contract import season_name
    item.setProperty('Bobi.SeasonName', season_name(view.get('season_name')))
    if chinese_title:
        item.setProperty('AM6B.Title.zh', chinese_title)
        item.setProperty('Bobi.Title.zh', chinese_title)
    item.setProperty('AM6B.SeriesTitle', series_title)
    item.setProperty('AM6B.Season.number', str(view['season']))
    item.setProperty('AM6B.Season.poster_origin', view.get('poster_origin', 'series_fallback'))
    if english_title:
        secondary = english_title
        item.setLabel2(secondary)
        item.setProperty('AM6B.Title.en', secondary)
        item.setProperty('Bobi.Title.en', secondary)
    try:
        started = date.fromisoformat(view.get('air_date', ''))
    except (TypeError, ValueError):
        started = None
    if started:
        tag.setYear(started.year)
        tag.setFirstAired(started.isoformat())
    art = poster_path(view.get('poster_path'))
    if art:
        item.setArt(dict(poster=tmdb_image_url(art, 'w342'),
                         thumb=tmdb_image_url(art, 'w185'),
                         icon=tmdb_image_url(art, 'w185')))
    # Keep series synopsis/fanart and identity, rather than mixing a later
    # season plot into the series detail/search contract.
    return True


def _root():
    import xbmcvfs
    root = Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/season-cards'))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


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


def _queue(add=(), origin='', take=False):
    """Short, non-blocking queue transaction; never hold its lock over HTTP."""
    with _lock('queue') as acquired:
        if not acquired:
            return None
        path = _root() / 'pending.json'
        value = {}
        try:
            if path.stat().st_size <= 16384:
                value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if not isinstance(value, dict):
            value = {}
        queued_ids, queued_origins = value.get('ids', []), value.get('origins', [])
        pending = [_id(v) for v in queued_ids[:MAX_QUEUE] if _id(v)] if isinstance(queued_ids, list) else []
        origins = ([v for v in queued_origins[:8] if isinstance(v, str) and len(v) <= 64]
                   if isinstance(queued_origins, list) else [])
        pending = list(dict.fromkeys(pending + list(add)))[:MAX_QUEUE]
        if origin:
            origins = list(dict.fromkeys(origins + [origin]))[-8:]
        selected = pending.pop(0) if take and pending else None
        changed = bool(add or origin or selected)
        if changed:
            fd, temporary = tempfile.mkstemp(prefix='.queue-', dir=str(path.parent))
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(dict(ids=pending, origins=origins if pending else []), stream)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return dict(selected=selected, pending=pending, origins=origins)


def _origin(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'plugin' or parsed.netloc != 'plugin.video.bobbi':
        return ''
    query = parse_qs(parsed.query)
    return hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()


def _playing():
    import xbmc
    return bool(xbmc.Player().isPlayingVideo())


def _wake():
    import xbmc
    import xbmcgui
    if _playing():
        return False
    window = xbmcgui.Window(10000)
    try:
        if float(window.getProperty(WAKE_PROPERTY) or 0) > time.monotonic():
            return False
    except ValueError:
        pass
    window.setProperty(WAKE_PROPERTY, str(time.monotonic() + WORK_SECONDS + 12))
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.bobbi/?action=am6b_refresh_season_cards)')
    return True


def enqueue_directory(items, home=False):
    """Queue only IDs already returned as TV-series cards by this directory."""
    try:
        identifiers = []
        for url, _item, folder in items[:100]:
            query = parse_qs(urlsplit(url).query)
            identifier = _id((query.get('id') or [''])[0])
            if (folder and query.get('action') == ['am6b_open_streaming_item']
                    and query.get('mode') == ['tv'] and identifier and not _fresh(identifier)):
                identifiers.append(identifier)
        if not identifiers:
            return False
        origin = 'home' if home else _origin(str(sys.argv[0]).rstrip('/') + '/' + str(sys.argv[2]))
        result = _queue(list(dict.fromkeys(identifiers))[:MAX_BATCH], origin=origin)
        if result is not None:
            _wake()
            return True
    except Exception:
        pass  # Metadata enrichment is never a prerequisite for usable cards.
    return False


def _prepare_fetch():
    # Compatibility aliases replace sys.modules while importing. Resolve them
    # on the owning thread BEFORE two workers can import the same alias.
    from importlib import import_module
    import_module('lib.api.tmdbv3api.objs.anime')
    import_module('lib.cinema.episode_order')
    import_module('lib.clients.tmdb.episode_order')


def _fetch(identifier, deadline):
    from lib.api.tmdbv3api.tmdb import TMDb
    from lib.api.tmdbv3api.objs.anime import _am6b_tokyo_today
    from lib.cinema.episode_order import validate_group

    class CardClient(TMDb):
        _session = None
        REQUEST_TIMEOUT = (2, 4)
        MAX_GET_ATTEMPTS = 1

    client = CardClient(obj_cached=False)
    def request(path, append=''):
        if time.monotonic() + 6 > deadline or _playing():
            raise TimeoutError('SEASON_CARD_BUDGET')
        params = dict(language='zh-CN')
        if append:
            params['append_to_response'] = append
        value = client._request_obj(path, params=urlencode(params), call_cached=False, add_lang=False)
        return value.to_dict() if hasattr(value, 'to_dict') else value
    # metadata_transport.fetch owns and closes every connection. There is no
    # per-subclass requests.Session lifetime to close after a successful fetch.
    details = request('/tv/' + str(identifier), 'episode_groups')
    if not isinstance(details, dict) or details.get('id') != identifier:
        raise ValueError('SEASON_CARD_IDENTITY')
    order = None
    if details.get('number_of_seasons') == 1:
        from lib.clients.tmdb.episode_order import get_order
        order = get_order(identifier, fetch=False)
        if not latest_season(details, _am6b_tokyo_today(), order):
            listing = dict(details.get('episode_groups') or {}, id=identifier)
            candidates = [row for row in listing.get('results', []) if row.get('type') in (6, 7)
                          and 1 < row.get('group_count', 0) <= 100]
            orders = {}
            if 0 < len(candidates) <= 2:
                for row in candidates:
                    try:
                        found = validate_group(identifier, listing, request('/tv/episode_group/' + row['id']))
                        orders[found['digest']] = found
                    except ValueError:
                        continue
            if len(orders) == 1:
                order = next(iter(orders.values()))
    return latest_season(details, _am6b_tokyo_today(), order)


def hydrate(_params=None):
    """One cross-process worker, two requests at a time, at most 20 TV IDs."""
    import xbmcgui
    acquired = completed = False
    try:
        with _lock('worker') as acquired:
            if not acquired:
                return False
            result = _hydrate_owned()
            completed = True
            return result
    except Exception as error:
        import xbmc
        from lib.utils.kodi.logging import kodilog
        kodilog('AM6B season-card worker deferred: ' + type(error).__name__, xbmc.LOGWARNING)
        return False
    finally:
        # Release the worker lock BEFORE dispatching a successor. Otherwise a
        # fast new Kodi invocation could exit on the old lock and lose its wake.
        if acquired:
            window = xbmcgui.Window(10000)
            if completed:
                window.clearProperty(WAKE_PROPERTY)
                remaining = _queue()
                if remaining and remaining['pending'] and not _playing():
                    _wake()
            else:
                # A missing dependency/database cannot trigger a respawn loop.
                # Keep pending IDs and let a later directory retry after cooling.
                window.setProperty(WAKE_PROPERTY, str(time.monotonic() + 300))


def _hydrate_owned():
    import xbmc
    from lib.db.cached import cache
    from lib.utils.tmdb_init import ensure_tmdb_init
    from lib.utils.kodi.logging import kodilog
    updated, origins = [], set()
    guard, count = Lock(), [0]
    deadline = time.monotonic() + WORK_SECONDS
    if _playing():
        return False
    ensure_tmdb_init()
    _prepare_fetch()

    def worker():
        while time.monotonic() + 6 < deadline and not _playing():
            with guard:
                if count[0] >= MAX_BATCH:
                    return
                row = _queue(take=True)
                if not row or not row['selected']:
                    return
                identifier = row['selected']
                count[0] += 1
                origins.update(row['origins'])
            if _fresh(identifier):
                continue
            previous = _record(identifier)
            try:
                view = _fetch(identifier, deadline)
                delay = 6 * 3600
                observed = time.time()
            except Exception as error:
                view = previous.get('view')
                delay = 5 * 60
                observed = previous.get('observed_at', 0)
                # Module/function/line only: exception text may contain keys
                # or provider URLs. Keep a bounded, useful failure stage.
                frames, frame = [], error.__traceback__
                while frame:
                    frames.append('{}:{}:{}'.format(os.path.basename(frame.tb_frame.f_code.co_filename),
                        frame.tb_frame.f_code.co_name, frame.tb_lineno))
                    frame = frame.tb_next
                kodilog('AM6B season-card metadata unavailable: {} id={} stage={}'.format(
                    type(error).__name__, identifier, ' > '.join(frames[-4:])), xbmc.LOGWARNING)
            cache.set('am6b_season_card_v1:' + str(identifier), dict(schema=1, tmdb_id=identifier,
                view=view, observed_at=observed, refresh_after=time.time() + delay), timedelta(days=7))
            if view and view != previous.get('view'):
                with guard:
                    updated.append(identifier)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        for future in futures:
            future.result()
    # Cache enrichment is consumed on the next directory visit. Even a result
    # for the same page can interrupt scrolling or race a pending page change.
    if updated and not _playing():
        home = xbmc.getCondVisibility('Window.IsActive(home)')
        if 'home' in origins and home:
            xbmc.executebuiltin('Container.Refresh')
    return bool(updated)
