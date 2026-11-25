from copy import deepcopy
from time import monotonic

import xbmc

from lib.api.trakt.lists_cache import lists_cache
from lib.api.trakt.trakt import TraktAPI
from lib.api.trakt.trakt_cache import (
    clear_trakt_calendar,
    clear_trakt_favorites,
    clear_trakt_hidden_data,
    clear_trakt_list_contents_data,
    clear_trakt_list_data,
    clear_trakt_watchlist,
    default_activities,
    get_activity,
    set_activity,
    trakt_watched_cache,
)
from lib.utils.kodi.utils import get_property_no_fallback, get_setting, kodilog

PAUSE_SERVICES_PROP = "bobbi.pause_services"
DEFAULT_SYNC_INTERVAL_MINUTES = 15
WAIT_STEP_SECONDS = 5

_BUCKET_ACTIVITY_PATHS = {
    "watched_movies": (("movies", "watched_at"),),
    "watched_shows": (("episodes", "watched_at"),),
    "progress_movies": (("movies", "paused_at"),),
    "progress_episodes": (("episodes", "paused_at"),),
    "collection_movies": (("movies", "collected_at"),),
    "collection_shows": (("episodes", "collected_at"),),
    "watchlist_movies": (("movies", "watchlisted_at"),),
    "watchlist_shows": (("shows", "watchlisted_at"),),
    "favorites_movies": (("movies", "favorited_at"),),
    "favorites_shows": (("shows", "favorited_at"),),
    "recommendations_movies": (("movies", "recommendations_at"),),
    "recommendations_shows": (("shows", "recommendations_at"),),
    "lists": (("lists", "liked_at"), ("lists", "updated_at")),
    "hidden_movies": (("movies", "hidden_at"),),
    "hidden_shows": (("shows", "hidden_at"),),
}


class TraktSyncService:
    def __init__(self, api=None, monitor=None):
        self.api = api or TraktAPI()
        self.monitor = monitor or xbmc.Monitor()
        self._cycle_context = None

    def _format_buckets(self, buckets):
        if not buckets:
            return "none"
        return ",".join(sorted(buckets))

    def _get_cycle_context(self, force=False):
        if self._cycle_context:
            return self._cycle_context
        return "startup" if force else "periodic"

    def _log_sync_summary(
        self,
        cycle_context,
        force,
        outcome,
        detected_buckets,
        applied_buckets,
        forced_defaults,
        started_at,
    ):
        duration_ms = int((monotonic() - started_at) * 1000)
        kodilog(
            f"Trakt sync[{cycle_context}]: completed outcome={outcome} force={force} forced_defaults={forced_defaults} detected_buckets={self._format_buckets(detected_buckets)} applied_buckets={self._format_buckets(applied_buckets)} duration_ms={duration_ms}"
        )

    def _log_sync_failure(self, cycle_context, force, error):
        kodilog(
            f"Trakt sync[{cycle_context}]: failed force={force} error={error}",
            level=xbmc.LOGERROR,
        )

    def run(self):
        if not self._is_trakt_available():
            kodilog("Trakt sync[startup]: skipped because Trakt is disabled or unauthenticated")
            return

        kodilog(
            "Starting Trakt Sync service (interval=%s minutes)"
            % (self._get_sync_interval_seconds() // 60)
        )

        try:
            self._cycle_context = "startup"
            kodilog("Trakt sync[startup]: beginning initial sync (force=True)")
            try:
                self.sync_activities(force=True)
            except Exception as e:
                self._log_sync_failure("startup", True, e)

            while not self.monitor.abortRequested():
                if self._wait_for_next_cycle():
                    return
                if not self._is_trakt_available():
                    kodilog("Trakt sync[periodic]: skipped cycle because Trakt is unavailable")
                    continue
                if self._services_paused():
                    kodilog("Trakt sync[periodic]: skipped cycle because services are paused")
                    continue
                self._cycle_context = "periodic"
                kodilog("Trakt sync[periodic]: beginning cycle")
                try:
                    self.sync_activities()
                except Exception as e:
                    self._log_sync_failure("periodic", False, e)
        except Exception as e:
            kodilog(f"Error during Trakt Sync: {e}", level=xbmc.LOGERROR)
        finally:
            self._cycle_context = None

    def _is_trakt_available(self):
        return get_setting("trakt_enabled") and get_setting("is_trakt_auth")

    def _services_paused(self):
        return get_property_no_fallback(PAUSE_SERVICES_PROP) == "true"

    def _get_sync_interval_seconds(self):
        try:
            interval = int(get_setting("trakt_sync_interval", DEFAULT_SYNC_INTERVAL_MINUTES))
        except (TypeError, ValueError):
            interval = DEFAULT_SYNC_INTERVAL_MINUTES
        return max(interval, 1) * 60

    def _wait_for_next_cycle(self):
        remaining = self._get_sync_interval_seconds()
        while remaining > 0:
            if self.monitor.waitForAbort(min(WAIT_STEP_SECONDS, remaining)):
                return True
            remaining -= WAIT_STEP_SECONDS
        return False

    @staticmethod
    def _merge_committed_activities(previous, latest, failed_buckets):
        merged = deepcopy(latest)
        if not failed_buckets:
            return merged
        defaults = default_activities()
        prev_dict = previous if isinstance(previous, dict) else defaults
        for bucket in failed_buckets:
            for section, field in _BUCKET_ACTIVITY_PATHS.get(bucket, ()):
                prev_section = prev_dict.get(section)
                if not isinstance(prev_section, dict):
                    prev_section = defaults.get(section, {})
                if isinstance(merged.get(section), dict) and field in prev_section:
                    merged[section][field] = prev_section[field]
        merged["all"] = prev_dict.get("all", defaults["all"])
        return merged

    def sync_activities(self, force=False):
        cycle_context = self._get_cycle_context(force=force)
        started_at = monotonic()
        forced_defaults = False
        detected_buckets = set()
        applied_buckets = set()

        try:
            latest_activities = self.api.sync.get_last_activities()
            if not isinstance(latest_activities, dict) or not latest_activities:
                self._log_sync_summary(
                    cycle_context,
                    force,
                    "no_data",
                    detected_buckets,
                    applied_buckets,
                    forced_defaults,
                    started_at,
                )
                return set()

            previous_activities = get_activity()
            detected_buckets = self._get_changed_buckets(previous_activities, latest_activities)
            planned_buckets = set(detected_buckets)
            if force and not planned_buckets:
                planned_buckets = {
                    "watched_movies",
                    "watched_shows",
                    "progress_movies",
                    "progress_episodes",
                }
                forced_defaults = True

            if not planned_buckets:
                set_activity(latest_activities)
                self._log_sync_summary(
                    cycle_context,
                    force,
                    "no_changes",
                    detected_buckets,
                    applied_buckets,
                    forced_defaults,
                    started_at,
                )
                return applied_buckets

            kodilog("Trakt sync: changed buckets = {}".format(", ".join(sorted(planned_buckets))))
            succeeded_buckets, failed_buckets, first_error = self._apply_activity_changes(planned_buckets)
            applied_buckets = set(succeeded_buckets)

            if succeeded_buckets and not failed_buckets:
                set_activity(latest_activities)
            elif succeeded_buckets:
                set_activity(
                    self._merge_committed_activities(
                        previous_activities,
                        latest_activities,
                        failed_buckets,
                    )
                )

            if first_error is not None:
                raise first_error

            outcome = "applied_changes" if not failed_buckets else "partial_changes"
            self._log_sync_summary(
                cycle_context,
                force,
                outcome,
                detected_buckets,
                applied_buckets,
                forced_defaults,
                started_at,
            )
            return applied_buckets
        except Exception as e:
            self._log_sync_failure(cycle_context, force, e)
            raise

    def _activity_changed(self, previous, latest, *path):
        prev_value = previous
        latest_value = latest
        for key in path:
            if not isinstance(prev_value, dict) or not isinstance(latest_value, dict):
                return False
            prev_value = prev_value.get(key)
            latest_value = latest_value.get(key)
        return bool(latest_value) and prev_value != latest_value

    def _get_changed_buckets(self, previous, latest):
        changes = set()

        if self._activity_changed(previous, latest, "movies", "watched_at"):
            changes.add("watched_movies")
        if self._activity_changed(previous, latest, "episodes", "watched_at"):
            changes.add("watched_shows")
        if self._activity_changed(previous, latest, "movies", "paused_at"):
            changes.add("progress_movies")
        if self._activity_changed(previous, latest, "episodes", "paused_at"):
            changes.add("progress_episodes")
        if self._activity_changed(previous, latest, "movies", "collected_at"):
            changes.add("collection_movies")
        if self._activity_changed(previous, latest, "episodes", "collected_at"):
            changes.add("collection_shows")
        if self._activity_changed(previous, latest, "movies", "watchlisted_at"):
            changes.add("watchlist_movies")
        if self._activity_changed(previous, latest, "shows", "watchlisted_at"):
            changes.add("watchlist_shows")
        if self._activity_changed(previous, latest, "movies", "favorited_at"):
            changes.add("favorites_movies")
        if self._activity_changed(previous, latest, "shows", "favorited_at"):
            changes.add("favorites_shows")
        if self._activity_changed(previous, latest, "movies", "recommendations_at"):
            changes.add("recommendations_movies")
        if self._activity_changed(previous, latest, "shows", "recommendations_at"):
            changes.add("recommendations_shows")
        if self._activity_changed(previous, latest, "lists", "liked_at") or self._activity_changed(
            previous, latest, "lists", "updated_at"
        ):
            changes.add("lists")
        if self._activity_changed(previous, latest, "movies", "hidden_at"):
            changes.add("hidden_movies")
        if self._activity_changed(previous, latest, "shows", "hidden_at"):
            changes.add("hidden_shows")

        return changes

    def _apply_activity_changes(self, changes):
        succeeded = set()
        failed = set()
        first_error = None
        sync_dispatch = (
            ("watched_movies", self.sync_watched_movies),
            ("watched_shows", self.sync_watched_shows),
            ("progress_movies", self.sync_movie_progress),
            ("progress_episodes", self.sync_episode_progress),
        )
        for bucket, fn in sync_dispatch:
            if bucket not in changes:
                continue
            try:
                ok = fn()
            except Exception as exc:
                failed.add(bucket)
                if first_error is None:
                    first_error = exc
            else:
                if ok is False:
                    failed.add(bucket)
                else:
                    succeeded.add(bucket)

        invalidation_buckets = set(changes) - {b for b, _ in sync_dispatch}
        if invalidation_buckets:
            try:
                self.invalidate_cached_buckets(invalidation_buckets)
            except Exception as exc:
                failed.update(invalidation_buckets)
                if first_error is None:
                    first_error = exc
            else:
                succeeded.update(invalidation_buckets)

        return succeeded, failed, first_error

    def sync_watched_movies(self):
        movies = self.api.movies.get_watched_movies()
        if not isinstance(movies, list):
            kodilog("Trakt watched movies response unknown; preserving existing snapshot", level=xbmc.LOGWARNING)
            return False

        insert_list = []
        for item in movies:
            if not isinstance(item, dict) or not isinstance(item.get("movie"), dict):
                raise ValueError("Invalid Trakt watched movie entry")
            ids = item["movie"].get("ids")
            if not isinstance(ids, dict):
                raise ValueError("Invalid Trakt watched movie ids")
            tmdb_id = ids.get("tmdb")
            if not tmdb_id:
                continue
            insert_list.append(
                (
                    "movie",
                    str(tmdb_id),
                    None,
                    None,
                    item["last_watched_at"],
                    item["movie"]["title"],
                )
            )

        trakt_watched_cache.set_bulk_movie_watched(insert_list)
        kodilog(f"Synced {len(insert_list)} watched movies from Trakt")
        return True

    def sync_watched_shows(self):
        shows = self.api.tv.get_watched_shows()
        if not isinstance(shows, list):
            kodilog("Trakt watched shows response unknown; preserving existing snapshot", level=xbmc.LOGWARNING)
            return False

        insert_list = []
        for item in shows:
            if not isinstance(item, dict) or not isinstance(item.get("show"), dict):
                raise ValueError("Invalid Trakt watched show entry")
            ids = item["show"].get("ids")
            if not isinstance(ids, dict):
                raise ValueError("Invalid Trakt watched show ids")
            show_tmdb = ids.get("tmdb")
            if not show_tmdb:
                continue
            show_title = item["show"]["title"]
            seasons = item.get("seasons", [])
            if not isinstance(seasons, list):
                raise ValueError("Invalid Trakt watched show seasons")
            for season in seasons:
                if not isinstance(season, dict):
                    raise ValueError("Invalid Trakt watched season entry")
                season_num = season["number"]
                episodes = season.get("episodes", [])
                if not isinstance(episodes, list):
                    raise ValueError("Invalid Trakt watched episodes")
                for episode in episodes:
                    if not isinstance(episode, dict):
                        raise ValueError("Invalid Trakt watched episode entry")
                    insert_list.append(
                        (
                            "episode",
                            str(show_tmdb),
                            season_num,
                            episode["number"],
                            episode["last_watched_at"],
                            show_title,
                        )
                    )

        trakt_watched_cache.set_bulk_tvshow_watched(insert_list)
        kodilog(f"Synced {len(insert_list)} watched episodes from Trakt")
        return True

    def sync_movie_progress(self):
        paused_movies = self.api.scrobble.trakt_get_playback_progress("movies")
        if not isinstance(paused_movies, list):
            kodilog("Trakt movie progress response unknown; preserving existing snapshot", level=xbmc.LOGWARNING)
            return False

        insert_list = []
        for item in paused_movies:
            if not isinstance(item, dict) or not isinstance(item.get("movie"), dict):
                raise ValueError("Invalid Trakt movie progress entry")
            ids = item["movie"].get("ids")
            if not isinstance(ids, dict):
                raise ValueError("Invalid Trakt movie progress ids")
            tmdb_id = ids.get("tmdb")
            if not tmdb_id:
                continue
            insert_list.append(
                (
                    "movie",
                    str(tmdb_id),
                    None,
                    None,
                    str(item.get("progress", 0)),
                    "0",
                    item.get("paused_at"),
                    item.get("id"),
                    item["movie"]["title"],
                )
            )

        trakt_watched_cache.set_bulk_movie_progress(insert_list)
        kodilog(f"Synced {len(insert_list)} movie progress items from Trakt")
        return True

    def sync_episode_progress(self):
        paused_episodes = self.api.scrobble.trakt_get_playback_progress("episodes")
        if not isinstance(paused_episodes, list):
            kodilog("Trakt episode progress response unknown; preserving existing snapshot", level=xbmc.LOGWARNING)
            return False

        insert_list = []
        for item in paused_episodes:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("show"), dict)
                or not isinstance(item.get("episode"), dict)
            ):
                raise ValueError("Invalid Trakt episode progress entry")
            ids = item["show"].get("ids")
            if not isinstance(ids, dict):
                raise ValueError("Invalid Trakt episode progress ids")
            show_tmdb = ids.get("tmdb")
            if not show_tmdb:
                continue
            insert_list.append(
                (
                    "episode",
                    str(show_tmdb),
                    item["episode"]["season"],
                    item["episode"]["number"],
                    str(item.get("progress", 0)),
                    "0",
                    item.get("paused_at"),
                    item.get("id"),
                    f"{item['show']['title']} - {item['episode']['title']}",
                )
            )

        trakt_watched_cache.set_bulk_tvshow_progress(insert_list)
        kodilog(f"Synced {len(insert_list)} episode progress items from Trakt")
        return True

    def invalidate_cached_buckets(self, changes):
        if "collection_movies" in changes:
            lists_cache.delete_prefix("trakt_movies_collection_")
        if "collection_shows" in changes:
            lists_cache.delete_prefix("trakt_tv_collection_")
        if "watchlist_movies" in changes or "watchlist_shows" in changes:
            clear_trakt_watchlist()
            clear_trakt_calendar()
        if "favorites_movies" in changes or "favorites_shows" in changes:
            clear_trakt_favorites()
        if "recommendations_movies" in changes:
            lists_cache.delete_prefix("trakt_recommendations_movies")
        if "recommendations_shows" in changes:
            lists_cache.delete_prefix("trakt_recommendations_shows")
        if "lists" in changes:
            clear_trakt_list_data("my_lists")
            clear_trakt_list_data("liked_lists")
            clear_trakt_list_contents_data("my_lists")
            clear_trakt_list_contents_data("liked_lists")
        if "hidden_movies" in changes:
            clear_trakt_hidden_data("movies")
        if "hidden_shows" in changes:
            clear_trakt_hidden_data("shows")
