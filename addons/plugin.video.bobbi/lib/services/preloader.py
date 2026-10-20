from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from time import monotonic

import xbmc
import xbmcgui

from lib.api.tmdbv3api.objs.anime import TmdbAnime
from lib.api.tmdbv3api.tmdb import TMDb
from lib.clients.tmdb.anime_fast_catalog import (
    AM6B_ANIME_CATALOG_CACHE_TTL,
    AM6B_ANIME_CATALOG_LANGUAGES,
    AM6B_DEFERRED_HYDRATION_SLOTS,
    AM6B_HYDRATION_PENDING_PREFIX,
    AM6B_REFRESH_PENDING_PROPERTY,
    _am6b_anime_catalog_cache_key,
    warm_am6b_primary_catalogs,
)
from lib.db.cached import cache
from lib.utils.kodi.utils import get_setting, kodilog

AM6B_HOME_ANIME_CATALOGS = (
    ("Anime_Current_Quarter", "tv", "anime_current_quarter"),
    ("Anime_Movies_New", "movies", "anime_movies_new"),
)
AM6B_CATALOG_REFRESH_INTERVAL_SECONDS = 6 * 60 * 60
AM6B_PRELOAD_STARTUP_GRACE_SECONDS = 20
AM6B_PRELOAD_REQUIRED_IDLE_SECONDS = 12
AM6B_PENDING_REFRESH_POLL_SECONDS = 2
AM6B_ALLOWED_DEFERRED_PREFIXES = (
    "plugin://plugin.video.bobbi/?action=am6b_refresh_anime_catalog",
    "plugin://plugin.video.bobbi/?action=am6b_refresh_anime_search",
)


class StartupPreloader:
    """Low-priority cache warmer and deferred visible-metadata refresher.

    Only the four page-one Chinese home rows are warmed.  Trend/detail/season
    speculation was deliberately removed: it generated many requests and
    SQLite writes for items the user might never open.  Every catalog cycle is
    gated by network, playback, and remote-control idle state.  The same single
    daemon thread consumes a lightweight pending-refresh marker so metadata
    hydrated during playback or another window appears automatically after the
    user returns, without a second provider request or a manual refresh.
    """

    def run(self):
        Thread(
            target=self._preload,
            name="AM6BPrimaryCatalogWarmup",
            daemon=True,
        ).start()

    def _preload(self):
        from lib.utils.tmdb_init import ensure_tmdb_init
        ensure_tmdb_init()
        monitor = xbmc.Monitor()
        player = xbmc.Player()

        if monitor.waitForAbort(AM6B_PRELOAD_STARTUP_GRACE_SECONDS):
            return
        if not self._wait_until_safe(monitor, player):
            return
        self._preload_am6b_primary_catalogs(refresh_existing=False)
        next_catalog_refresh = monotonic() + AM6B_CATALOG_REFRESH_INTERVAL_SECONDS

        while not monitor.abortRequested():
            self._run_deferred_hydration(player)
            self._refresh_pending_view(player)
            now = monotonic()
            if now >= next_catalog_refresh and self._safe_for_catalog_work(player):
                self._preload_am6b_primary_catalogs(refresh_existing=True)
                next_catalog_refresh = monotonic() + AM6B_CATALOG_REFRESH_INTERVAL_SECONDS
            if monitor.waitForAbort(AM6B_PENDING_REFRESH_POLL_SECONDS):
                return

    def _wait_until_safe(self, monitor, player):
        while not monitor.abortRequested():
            self._run_deferred_hydration(player)
            self._refresh_pending_view(player)
            if self._safe_for_catalog_work(player):
                return True
            if monitor.waitForAbort(1):
                return False
        return False

    @staticmethod
    def _safe_for_catalog_work(player):
        try:
            has_network = bool(xbmc.getCondVisibility("System.HasNetwork"))
        except Exception:
            has_network = False
        try:
            playing_video = bool(player.isPlayingVideo())
        except Exception:
            playing_video = False
        try:
            idle_seconds = int(xbmc.getGlobalIdleTime())
        except Exception:
            idle_seconds = 0
        return has_network and not playing_video and idle_seconds >= AM6B_PRELOAD_REQUIRED_IDLE_SECONDS

    @staticmethod
    def _run_deferred_hydration(player):
        """Launch one queued metadata job only after playback and network recover."""
        try:
            if player.isPlayingVideo():
                return False
            if not xbmc.getCondVisibility("System.HasNetwork"):
                return False
            window = xbmcgui.Window(10000)
            for index in range(AM6B_DEFERRED_HYDRATION_SLOTS):
                key = "{}{}".format(AM6B_HYDRATION_PENDING_PREFIX, index)
                plugin_url = window.getProperty(key) or ""
                if not plugin_url:
                    continue
                if not plugin_url.startswith(AM6B_ALLOWED_DEFERRED_PREFIXES):
                    window.clearProperty(key)
                    kodilog("[StartupPreloader] rejected invalid deferred hydration URL")
                    continue
                window.clearProperty(key)
                try:
                    xbmc.executebuiltin("RunPlugin({})".format(plugin_url))
                except Exception:
                    # A transient Kodi dispatch failure must not silently lose the
                    # only queued secondary-title completion job.
                    window.setProperty(key, plugin_url)
                    raise
                return True
        except Exception:
            kodilog("[StartupPreloader] deferred hydration launch failed")
        return False

    @staticmethod
    def _refresh_pending_view(player):
        """Consume hydrated metadata on Home, never reload a browsing directory."""
        try:
            window = xbmcgui.Window(10000)
            if window.getProperty(AM6B_REFRESH_PENDING_PROPERTY) != "true":
                return False
            if player.isPlayingVideo():
                return False
            home_active = xbmc.getCondVisibility("Window.IsActive(home)")
            if not home_active:
                return False
            xbmc.executebuiltin("Container.Refresh")
            window.clearProperty(AM6B_REFRESH_PENDING_PROPERTY)
            return True
        except Exception:
            kodilog("[StartupPreloader] deferred metadata refresh failed")
            return False

    @staticmethod
    def _preload_am6b_primary_catalogs(refresh_existing=False):
        try:
            return warm_am6b_primary_catalogs(refresh_existing=refresh_existing)
        except Exception:
            kodilog("[StartupPreloader] AM6B primary catalog warmup failed")
            return 0

    @staticmethod
    def _preload_am6b_home_catalogs(refresh_existing=False):
        """Compatibility entry point retained for existing tests/manual tools.

        The scheduled runtime path above never invokes this legacy six-locale
        method.  It remains callable so downstream integrations are not broken
        by the performance refactor.
        """
        monitor = xbmc.Monitor()
        for _ in range(60):
            if monitor.abortRequested():
                return
            if xbmc.getCondVisibility("System.HasNetwork"):
                break
            monitor.waitForAbort(0.5)
        else:
            kodilog("[StartupPreloader] AM6B catalog warmup skipped: no network")
            return

        pending = []
        for category, mode, method_name in AM6B_HOME_ANIME_CATALOGS:
            for language in AM6B_ANIME_CATALOG_LANGUAGES:
                cache_key = _am6b_anime_catalog_cache_key(category, mode, 1, language)
                cached = cache.get(cache_key)
                if refresh_existing or cached is None:
                    pending.append((cache_key, method_name, mode, language))

        if not pending:
            return

        def fetch_catalog(cache_key, method_name, mode, language):
            try:
                client = TmdbAnime()
                if method_name == "anime_current_quarter":
                    data = client.anime_current_quarter(mode, 1, language=language)
                elif method_name == "anime_movies_new":
                    data = client.anime_movies_new(1, language=language)
                else:
                    return
            except Exception:
                kodilog("[StartupPreloader] AM6B direct catalog warmup failed")
                return
            if data is not None:
                cache.set(cache_key, data, AM6B_ANIME_CATALOG_CACHE_TTL)

        with ThreadPoolExecutor(max_workers=min(6, len(pending))) as executor:
            futures = [executor.submit(fetch_catalog, *request) for request in pending]
            for future in futures:
                future.result()
