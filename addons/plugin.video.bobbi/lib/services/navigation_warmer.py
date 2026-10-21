"""Idle selected-work/recent-work metadata on the existing preload thread.

This never resolves a playable URL, starts a cloud task, fetches media bytes,
or refreshes a GUI container. Only public catalogue IDs enter the work plan.
"""
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit


def target(data):
    if not isinstance(data, dict):
        return None
    ids = data.get('ids') or {}
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except (ValueError, TypeError):
            return None
    if not isinstance(ids, dict):
        return None
    identifier = ids.get('tmdb_id') or data.get('tmdb_id') or data.get('id')
    if type(identifier) not in (int, str) or not str(identifier).isdecimal() or not 0 < int(identifier) < 10**9:
        return None
    mode = data.get('mode') or data.get('media_type')
    if mode in ('movie', 'movies'):
        return ('movies', int(identifier), None)
    if mode not in ('tv', 'episode', 'season'):
        return None
    tv = data.get('tv_data') or {}
    if isinstance(tv, str):
        try:
            tv = json.loads(tv)
        except (ValueError, TypeError):
            return None
    if not isinstance(tv, dict):
        return None
    season = tv.get('season', data.get('season'))
    if type(season) in (int, str) and str(season).isdecimal() and 0 <= int(season) <= 100:
        season = int(season)
    else:
        season = None
    return ('tv', int(identifier), season)


def target_from_url(url):
    if not isinstance(url, str) or len(url) > 32768:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme != 'plugin' or parsed.netloc != 'plugin.video.bobbi':
        return None
    fields = {key: values[0] for key, values in parse_qs(parsed.query).items() if len(values) == 1}
    action = fields.get('action')
    if action in ('am6b_open_streaming_item', 'show_tmdb_item', 'show_episodes_details',
                  'show_seasons_details', 'search'):
        return target(fields)
    if action == 'play_media' and fields.get('continue_watching') == 'true':
        try:
            return target(json.loads(fields.get('data', '{}')))
        except (ValueError, TypeError):
            return None
    return None


def focused_target():
    import xbmc
    return target_from_url(xbmc.getInfoLabel('ListItem.FileNameAndPath'))


def recent_targets():
    from lib.db.pickle_db import PickleDatabase
    from lib.cinema.frontend_contract import history_rows
    from lib.utils.views.last_files import parse_time
    rows = history_rows(PickleDatabase().get_key('jt:lfh').items(), parse_time)
    found = []
    # Reuse the product's unfinished/dedup rules, not another progress policy.
    for _, data, _ in rows[:10]:
        value = target(data)
        if value and value not in found:
            found.append(value)
        if len(found) == 3:
            break
    return found


def resources_available():
    """Headroom, not a model whitelist. Preparation has at most eight IO calls."""
    from bobbi_core.image_cache import visible_images_busy
    if visible_images_busy():
        return False
    if os.name != 'posix':
        return True
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:') and int(line.split()[1]) < 256 * 1024:
                return False
        thermal = Path('/sys/class/thermal/thermal_zone0/temp')
        if thermal.exists() and int(thermal.read_text().strip()) >= 80000:
            return False
        if hasattr(os, 'getloadavg') and os.getloadavg()[0] > max(2, os.cpu_count() or 2) * 1.5:
            return False
    except (OSError, ValueError):
        # Unavailable optional telemetry must not become a hardware gate.
        pass
    return True


def ready(player):
    import xbmc
    try:
        return (not player.isPlaying() and xbmc.getCondVisibility('System.HasNetwork')
                and not xbmc.getCondVisibility('System.HasModalDialog')
                and (xbmc.getCondVisibility('Window.IsActive(home)')
                     or xbmc.getCondVisibility('Window.IsActive(videos)'))
                and resources_available())
    except Exception:
        return False


def warm(value, deadline, cancelled):
    from bobbi_core.metadata_transport import request_budget
    from lib.clients.tmdb.utils.utils import get_tmdb_media_details
    from lib.clients.tmdb.navigation import prepare, regular_seasons
    from lib.utils.general.utils import build_media_metadata
    mode, identifier, season = value
    with request_budget(deadline, cancelled, quiet=True):
        details = get_tmdb_media_details(identifier, mode)
        if details is None or cancelled():
            return False
        ids = {'tmdb_id': identifier}
        external = details.get('external_ids') or {}
        ids.update({key: external.get(key) for key in ('imdb_id', 'tvdb_id') if external.get(key)})
        # Art is optional and public. It is never part of source-search setup.
        def artwork():
            if not cancelled() and time.monotonic() + 1 < deadline:
                build_media_metadata(ids, mode, details=details)
        if mode == 'tv':
            result = prepare(details, {'tmdb_id': identifier}, deadline=deadline,
                             cancelled=cancelled, preferred_season=season, quiet=True)
            seasons = regular_seasons(details)
            wanted = ([season] if season in seasons else seasons if len(seasons) <= 2
                      else [seasons[0], seasons[-1]])
            artwork()
            return bool(result.get('movies') and result['movies'].get('complete')
                        and wanted and all(number in result['pages'] for number in wanted))
        artwork()
        return True


class NavigationWarmer:
    def __init__(self):
        self.focus = None
        self.since = 0
        self.next_recent = 0
        self.recent = []
        self.cooldown = {}
        self.epoch = object()

    def tick(self, monitor, player):
        from lib.utils.kodi.utils import kodilog
        try:
            return self._tick(monitor, player)
        except Exception as error:
            # Optional metadata must not terminate the existing preload loop.
            kodilog('Navigation warm preflight unavailable: ' + type(error).__name__)
            return False

    def _tick(self, monitor, player):
        import xbmc
        from lib.db.cached import cache
        from lib.utils.kodi.utils import kodilog
        if monitor.abortRequested() or not ready(player):
            return False
        epoch = cache.get('bobi_metadata_epoch')
        if epoch != self.epoch:
            self.epoch = epoch
            self.cooldown.clear()
            self.recent, self.next_recent = [], 0
        now = time.monotonic()
        focused = focused_target()
        if focused != self.focus:
            self.focus, self.since = focused, now
            return False  # Debounce scrolling: do not fan out for every card.
        if now - self.since < 2:
            return False
        chosen = focused if focused and self.cooldown.get(focused, 0) <= now else None
        if chosen is None and int(xbmc.getGlobalIdleTime()) >= 12:
            if now >= self.next_recent:
                self.recent, self.next_recent = recent_targets(), now + 60
            chosen = next((row for row in self.recent if self.cooldown.get(row, 0) <= now), None)
        if chosen is None:
            return False
        stopped = [False]
        def cancelled():
            if not stopped[0] and (monitor.abortRequested() or not ready(player)
                    or focused_target() != focused or cache.get('bobi_metadata_epoch') != epoch):
                stopped[0] = True
            return stopped[0]
        # Keep bounded cooldown state; no credentials, locators or playback
        # data are retained, including for recent-history work.
        if len(self.cooldown) >= 64:
            self.cooldown.pop(next(iter(self.cooldown)))
        self.cooldown[chosen] = now + 60
        try:
            complete = warm(chosen, now + 8, cancelled)
            complete = bool(complete and not cancelled())
            if complete:
                self.cooldown[chosen] = time.monotonic() + 3600
            kodilog('Navigation warm: mode={} id={} complete={} elapsed_ms={}'.format(
                chosen[0], chosen[1], bool(complete), round((time.monotonic() - now) * 1000)))
            return bool(complete)
        except Exception as error:
            kodilog('Navigation warm deferred: ' + type(error).__name__)
            return False
