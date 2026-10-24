import contextlib
import hashlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlencode
from bobbi_core.image_cache import image_batch, image_url as tmdb_image_url

import xbmc
import xbmcgui
import xbmcplugin

from lib.api.tmdbv3api.objs.anime import TmdbAnime, _am6b_quarter_bounds, _am6b_tokyo_today
from lib.api.tmdbv3api.tmdb import TMDb
from lib.clients.tmdb.anime_metadata import (
    _am6b_apply_anime_title_properties,  # compatibility export for existing tests/callers
    _am6b_build_catalog_title_map,
    _am6b_catalog_localized_title,
    _am6b_catalog_title,
    _am6b_value,
)
from lib.db.cached import cache
from lib.utils.kodi.logging import kodilog
from lib.utils.tmdb_init import ensure_tmdb_init

# A short last-known-good window protects the always-on box from transient
# provider outages without turning a week-old page into the normal result.
AM6B_ANIME_CATALOG_CACHE_TTL = timedelta(days=2)
AM6B_ANIME_SEARCH_CACHE_TTL = timedelta(hours=4)
AM6B_STREAMING_CATALOG_CACHE_TTL = timedelta(hours=24)
AM6B_STREAMING_SEARCH_CACHE_TTL = timedelta(hours=1)
AM6B_ANIME_CATALOG_LANGUAGES = ("zh-CN", "zh-TW", "en-US")
AM6B_HYDRATION_LEASE_SECONDS = 45
AM6B_HYDRATION_PLAYBACK_DEFER_SECONDS = 10
AM6B_HYDRATION_FAILURE_COOLDOWN_SECONDS = 5 * 60
AM6B_MAX_BACKGROUND_REQUESTS = 2
AM6B_REFRESH_PENDING_PROPERTY = "AM6B.FastPath.RefreshPending"
AM6B_HYDRATION_PENDING_PREFIX = "AM6B.FastPath.HydrationPending."
AM6B_DEFERRED_HYDRATION_SLOTS = 2

AM6B_FAST_CATALOGS = {
    "Anime_Current_Quarter": ("tv", "本季度动漫"),
    "Anime_Movies_New": ("movies", "动漫电影"),
}
AM6B_STREAMING_CATALOGS = {
    "tv": ("tv", "/tv/on_the_air", "电视剧"),
    "movie": ("movies", "/movie/now_playing", "电影"),
}
AM6B_SEARCH_SECTIONS = frozenset(("tv", "movie", "multi", "anime_tv", "anime_movie"))


def _am6b_anime_catalog_cache_key(category, submode, page, language, today=None):
    if category == "Anime_Current_Quarter":
        # Do not reuse the old first-season-only pages or last quarter's rows.
        # All foreground, hydration and preloader callers share this key.
        start, _end = _am6b_quarter_bounds(today or _am6b_tokyo_today())
        return "am6b_anime_catalog_v2|{}|{}|{}|{}|{}".format(
            category, submode, page, language, start.isoformat())
    return "am6b_anime_catalog_v1|{}|{}|{}|{}".format(
        category,
        submode,
        page,
        language,
    )


def _am6b_anime_search_cache_key(query, submode, page, language):
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return "am6b_anime_search_v1|{}|{}|{}|{}".format(
        submode,
        page,
        language,
        digest,
    )


def _am6b_streaming_cache_key(kind, section, page, query=""):
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest() if query else "catalog"
    return "am6b_streaming_{}_v1|{}|{}|{}".format(kind, section, page, digest)


def _am6b_load_anime_catalog_page(category, submode, page, language, fetcher):
    """Return a persistent catalog page, fetching it only on cache miss."""
    cache_key = _am6b_anime_catalog_cache_key(category, submode, page, language)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = fetcher()
    if data is not None:
        cache.set(cache_key, data, AM6B_ANIME_CATALOG_CACHE_TTL)
    return data


def _positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _plugin_handle():
    try:
        return int(sys.argv[1])
    except (IndexError, TypeError, ValueError):
        return 0


def _plugin_base_url():
    try:
        return sys.argv[0]
    except (IndexError, TypeError):
        return "plugin://plugin.video.bobbi/"


def _build_url(action, **params):
    query = {"action": action}
    query.update({key: value for key, value in params.items() if value is not None})
    return "{}?{}".format(_plugin_base_url(), urlencode(query))


def _ensure_tmdb_key():
    ensure_tmdb_init()


def _fetch_catalog(category, submode, page, language):
    client = TmdbAnime()
    if category == "Anime_Current_Quarter":
        return client.anime_current_quarter(submode, page, language=language)
    if category == "Anime_Movies_New":
        return client.anime_movies_new(page, language=language)
    return None


def _fetch_anime_search(query, submode, page, language):
    return TmdbAnime().anime_search(query, submode, page, language=language)


def _safe_fetch(label, fetcher):
    try:
        return fetcher()
    except Exception as error:
        # Provider exceptions can contain authenticated URLs.  Log only a
        # stable operation label and class, never the exception body. Keep
        # failures visible at normal logging levels without error popups.
        kodilog("AM6B fast metadata request failed: {} ({})".format(
            label, type(error).__name__), xbmc.LOGWARNING)
        return None


def _window():
    return xbmcgui.Window(10000)


def _lease_key(kind, *parts):
    raw = "|".join([kind] + [str(part) for part in parts])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return "AM6B.FastPath.Lease.{}".format(digest)


def _lease_active(window, key, now=None):
    now = time.monotonic() if now is None else now
    try:
        return float(window.getProperty(key) or 0) > now
    except (TypeError, ValueError):
        return False


def _set_lease(window, key, seconds):
    window.setProperty(key, str(time.monotonic() + seconds))


def _clear_lease(window, key):
    with contextlib.suppress(Exception):
        window.clearProperty(key)


def _schedule_plugin_call(action, lease_key, **params):
    """Start one non-blocking hydration invocation per catalog/search page."""
    try:
        window = _window()
        if _lease_active(window, lease_key):
            return False
        _set_lease(window, lease_key, AM6B_HYDRATION_LEASE_SECONDS)
        xbmc.executebuiltin("RunPlugin({})".format(_build_url(action, **params)))
        return True
    except Exception:
        with contextlib.suppress(Exception):
            _clear_lease(window, lease_key)
        kodilog("AM6B metadata hydration could not be scheduled")
        return False


def _playback_active():
    try:
        return bool(xbmc.Player().isPlayingVideo())
    except Exception:
        return False


def _queue_deferred_plugin_call(action, lease, **params):
    """Persist at most two user-visible hydration jobs until playback ends."""
    try:
        window = _window()
        plugin_url = _build_url(action, **params)
        empty_slot = None
        for index in range(AM6B_DEFERRED_HYDRATION_SLOTS):
            key = "{}{}".format(AM6B_HYDRATION_PENDING_PREFIX, index)
            queued = window.getProperty(key) or ""
            if queued == plugin_url:
                _set_lease(window, lease, AM6B_HYDRATION_LEASE_SECONDS)
                return True
            if not queued and empty_slot is None:
                empty_slot = key
        if empty_slot is None:
            kodilog("AM6B deferred hydration queue is full")
            return False
        window.setProperty(empty_slot, plugin_url)
        _set_lease(window, lease, AM6B_HYDRATION_LEASE_SECONDS)
        return True
    except Exception:
        kodilog("AM6B metadata hydration could not be deferred")
        return False


def _refresh_visible_container():
    """Refresh Home only; a background completion must not reload a directory.

Directory results consume the enriched cache on their next explicit visit.
Never apply a late result for page N to a newer page, season or source list.
"""
    window = None
    try:
        window = _window()
        window.setProperty(AM6B_REFRESH_PENDING_PROPERTY, "true")
        if _playback_active():
            return False
        home_active = xbmc.getCondVisibility("Window.IsActive(home)")
        if home_active:
            xbmc.executebuiltin("Container.Refresh")
            window.clearProperty(AM6B_REFRESH_PENDING_PROPERTY)
            return True
    except Exception:
        kodilog("AM6B metadata hydration completed without a visible refresh")
    return False


def _cached_anime_catalogs(category, submode, page):
    return {
        language: cache.get(_am6b_anime_catalog_cache_key(category, submode, page, language))
        for language in AM6B_ANIME_CATALOG_LANGUAGES
    }


def _localized_catalogs(category, submode, page, schedule_hydration=True):
    """Return a usable localized page after at most one foreground request.

    Cached zh-CN is used immediately.  A cold page requests zh-CN only; zh-TW
    and en-US are deferred to a bounded RunPlugin hydration.  Fallback locales
    are requested synchronously only when the preceding primary request failed,
    so a normal first screen never waits for three providers.
    """
    localized = _cached_anime_catalogs(category, submode, page)

    if localized.get("zh-CN") is None:
        localized["zh-CN"] = _safe_fetch(
            "{} zh-CN".format(category),
            lambda: _am6b_load_anime_catalog_page(
                category,
                submode,
                page,
                "zh-CN",
                lambda: _fetch_catalog(category, submode, page, "zh-CN"),
            ),
        )

    if localized.get("zh-CN") is None and localized.get("zh-TW") is None:
        localized["zh-TW"] = _safe_fetch(
            "{} zh-TW fallback".format(category),
            lambda: _am6b_load_anime_catalog_page(
                category,
                submode,
                page,
                "zh-TW",
                lambda: _fetch_catalog(category, submode, page, "zh-TW"),
            ),
        )

    if not (localized.get("zh-CN") or localized.get("zh-TW")) and localized.get("en-US") is None:
        localized["en-US"] = _safe_fetch(
            "{} en-US fallback".format(category),
            lambda: _am6b_load_anime_catalog_page(
                category,
                submode,
                page,
                "en-US",
                lambda: _fetch_catalog(category, submode, page, "en-US"),
            ),
        )

    if schedule_hydration:
        _schedule_missing_catalog_locales(category, submode, page, localized)
    return localized


def _schedule_missing_catalog_locales(category, submode, page, localized):
    missing = [language for language in AM6B_ANIME_CATALOG_LANGUAGES if localized.get(language) is None]
    if not missing:
        return False
    lease = _lease_key("catalog", category, submode, page)
    return _schedule_plugin_call(
        "am6b_refresh_anime_catalog",
        lease,
        category=category,
        submode=submode,
        page=page,
        languages=",".join(missing[:AM6B_MAX_BACKGROUND_REQUESTS]),
    )


def _cached_anime_searches(query, submode, page):
    return {
        language: cache.get(_am6b_anime_search_cache_key(query, submode, page, language))
        for language in AM6B_ANIME_CATALOG_LANGUAGES
    }


def _localized_anime_search(query, submode, page, schedule_hydration=True):
    localized = _cached_anime_searches(query, submode, page)

    if localized.get("zh-CN") is None:
        localized["zh-CN"] = _safe_fetch(
            "anime search zh-CN",
            lambda: _load_anime_search_page(query, submode, page, "zh-CN"),
        )
    if localized.get("zh-CN") is None and localized.get("zh-TW") is None:
        localized["zh-TW"] = _safe_fetch(
            "anime search zh-TW fallback",
            lambda: _load_anime_search_page(query, submode, page, "zh-TW"),
        )
    if not (localized.get("zh-CN") or localized.get("zh-TW")) and localized.get("en-US") is None:
        localized["en-US"] = _safe_fetch(
            "anime search en-US fallback",
            lambda: _load_anime_search_page(query, submode, page, "en-US"),
        )

    if schedule_hydration:
        _schedule_missing_search_locales(query, submode, page, localized)
    return localized


def _schedule_missing_search_locales(query, submode, page, localized):
    missing = [language for language in AM6B_ANIME_CATALOG_LANGUAGES if localized.get(language) is None]
    if not missing:
        return False
    lease = _lease_key("search", query, submode, page)
    return _schedule_plugin_call(
        "am6b_refresh_anime_search",
        lease,
        query=query,
        submode=submode,
        page=page,
        languages=",".join(missing[:AM6B_MAX_BACKGROUND_REQUESTS]),
    )


def _load_anime_search_page(query, submode, page, language, refresh=False):
    cache_key = _am6b_anime_search_cache_key(query, submode, page, language)
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    data = _fetch_anime_search(query, submode, page, language)
    if data is not None:
        cache.set(cache_key, data, AM6B_ANIME_SEARCH_CACHE_TTL)
    return data


def _allowed_languages(raw):
    requested = [value.strip() for value in str(raw or "").split(",") if value.strip()]
    return [
        language
        for language in requested
        if language in AM6B_ANIME_CATALOG_LANGUAGES
    ][:AM6B_MAX_BACKGROUND_REQUESTS]


def _hydrate_requests(lease, requests_to_run, deferred_call=None):
    """Run at most two metadata calls and hold a cooldown after failures."""
    requests_to_run = list(requests_to_run)[:AM6B_MAX_BACKGROUND_REQUESTS]
    window = None
    successes = 0
    failures = 0
    preserve_lease = False
    try:
        window = _window()
        if not requests_to_run:
            _clear_lease(window, lease)
            return False
        if _playback_active():
            if deferred_call is not None:
                preserve_lease = bool(deferred_call())
            if not preserve_lease:
                _set_lease(window, lease, AM6B_HYDRATION_PLAYBACK_DEFER_SECONDS)
                preserve_lease = True
            return False

        with ThreadPoolExecutor(max_workers=min(AM6B_MAX_BACKGROUND_REQUESTS, len(requests_to_run))) as executor:
            futures = [executor.submit(fetcher) for fetcher in requests_to_run]
            for future in futures:
                try:
                    if future.result() is not None:
                        successes += 1
                    else:
                        failures += 1
                except Exception:
                    failures += 1
                    kodilog("AM6B bounded metadata hydration request failed")

        if failures:
            _set_lease(window, lease, AM6B_HYDRATION_FAILURE_COOLDOWN_SECONDS)
        else:
            _clear_lease(window, lease)
        if successes:
            _refresh_visible_container()
        return successes > 0
    finally:
        if window is not None and not preserve_lease and not failures and successes == 0:
            _clear_lease(window, lease)


def hydrate_am6b_anime_catalog(params):
    category = params.get("category", "")
    contract = AM6B_FAST_CATALOGS.get(category)
    if not contract:
        return False
    expected_mode = contract[0]
    submode = params.get("submode") or expected_mode
    if submode != expected_mode:
        return False
    page = _positive_int(params.get("page"), 1)
    languages = _allowed_languages(params.get("languages"))
    lease = _lease_key("catalog", category, submode, page)
    _ensure_tmdb_key()

    requests_to_run = []
    for language in languages:
        def fetch(current_language=language):
            data = _fetch_catalog(category, submode, page, current_language)
            if data is not None:
                cache.set(
                    _am6b_anime_catalog_cache_key(category, submode, page, current_language),
                    data,
                    AM6B_ANIME_CATALOG_CACHE_TTL,
                )
            return data

        requests_to_run.append(fetch)
    _hydrate_requests(
        lease,
        requests_to_run,
        deferred_call=lambda: _queue_deferred_plugin_call(
            "am6b_refresh_anime_catalog",
            lease,
            category=category,
            submode=submode,
            page=page,
            languages=",".join(languages),
        ),
    )
    return True


def hydrate_am6b_anime_search(params):
    query = str(params.get("query") or "").strip()
    submode = params.get("submode") or "tv"
    if not query or submode not in ("tv", "movies"):
        return False
    page = _positive_int(params.get("page"), 1)
    languages = _allowed_languages(params.get("languages"))
    lease = _lease_key("search", query, submode, page)
    _ensure_tmdb_key()
    requests_to_run = [
        (lambda current_language=language: _load_anime_search_page(
            query,
            submode,
            page,
            current_language,
            refresh=True,
        ))
        for language in languages
    ]
    _hydrate_requests(
        lease,
        requests_to_run,
        deferred_call=lambda: _queue_deferred_plugin_call(
            "am6b_refresh_anime_search",
            lease,
            query=query,
            submode=submode,
            page=page,
            languages=",".join(languages),
        ),
    )
    return True


def _set_video_metadata(list_item, result, display_title, mode):
    info_tag = list_item.getVideoInfoTag()
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(result, original_key, "") or ""
    overview = _am6b_value(result, "overview", "") or ""
    with contextlib.suppress(Exception):
        info_tag.setTitle(display_title)
    with contextlib.suppress(Exception):
        info_tag.setOriginalTitle(original)
    with contextlib.suppress(Exception):
        info_tag.setPlot(overview)
    with contextlib.suppress(Exception):
        info_tag.setMediaType("movie" if mode == "movies" else "tvshow")
    tmdb_id = _am6b_value(result, "id", "")
    if tmdb_id:
        with contextlib.suppress(Exception):
            info_tag.setUniqueIDs({"tmdb": str(tmdb_id)}, "tmdb")
    release_key = "release_date" if mode == "movies" else "first_air_date"
    release_date = _am6b_value(result, release_key, "") or ""
    if release_date:
        with contextlib.suppress(Exception):
            info_tag.setYear(int(release_date.split("-", 1)[0]))
        with contextlib.suppress(Exception):
            if mode == "movies":
                info_tag.setPremiered(release_date)
            else:
                info_tag.setFirstAired(release_date)
                info_tag.setTvShowTitle(display_title)


def _set_catalog_art(list_item, result):
    poster_path = _am6b_value(result, "poster_path", "") or ""
    backdrop_path = _am6b_value(result, "backdrop_path", "") or ""
    # The 1080p home cards render at 172 px wide.  A 342 px poster is a
    # full 2x source and avoids decoding the materially larger w500 asset for
    # every off-focus card; the focused hero keeps a 1280 px backdrop.
    poster = tmdb_image_url(poster_path, 'w342')
    thumb = tmdb_image_url(poster_path, 'w185')
    fanart = tmdb_image_url(backdrop_path, 'w1280')
    list_item.setArt(
        {
            "poster": poster,
            "thumb": thumb or poster,
            "icon": thumb or poster,
            "fanart": fanart,
        }
    )


def _set_title_properties(list_item, titles, original, media_kind, pending=False):
    if titles.get("zh"):
        list_item.setProperty("AM6B.Title.zh", titles["zh"])
        list_item.setProperty("Bobi.Title.zh", titles["zh"])
    if titles.get("en"):
        list_item.setProperty("AM6B.Title.en", titles["en"])
        list_item.setProperty("Bobi.Title.en", titles["en"])
    if isinstance(original, str) and original.strip():
        list_item.setProperty("AM6B.Title.original", original.strip())
    list_item.setProperty("AM6B.Media.kind", media_kind)
    if pending:
        list_item.setProperty("AM6B.Metadata.pending", "true")


def _catalog_item(result, mode, title_map):
    tmdb_id = _am6b_value(result, "id", "")
    if not tmdb_id:
        return None
    titles = title_map.get(tmdb_id, {}) if isinstance(title_map, dict) else {}
    titles = {
        "zh": str(titles.get("zh") or "").strip(),
        "en": str(titles.get("en") or "").strip(),
    }
    provider_title = _am6b_catalog_title(result, mode)
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(result, original_key, "") or ""
    display_title = titles.get("zh") or titles.get("en") or provider_title or original
    if not display_title:
        return None

    list_item = xbmcgui.ListItem(label=display_title)
    list_item.setContentLookup(False)
    _set_video_metadata(list_item, result, display_title, mode)
    _set_catalog_art(list_item, result)
    _set_title_properties(
        list_item,
        titles,
        original,
        "anime_movie" if mode == "movies" else "anime_series",
        pending=not bool(titles.get("en")),
    )

    from lib.clients.tmdb.frontend_metadata import apply as apply_frontend
    apply_frontend(list_item, tmdb_id, mode, dict(title=display_title, original_title=original), titles)
    if mode == "tv":
        from lib.clients.tmdb.season_cards import apply
        apply(list_item, tmdb_id, display_title, titles.get("en") or "", titles.get("zh") or "")

    is_folder = mode != "movies"
    if not is_folder:
        from lib.clients.cinema_ui import catalog_playable_property
        list_item.setProperty("IsPlayable", catalog_playable_property())
    url = _build_url(
        "am6b_open_streaming_item",
        mode=mode,
        submode="",
        id=tmdb_id,
        title=display_title,
        original=original,
        media_type="movie" if mode == "movies" else "tv",
    )
    return url, list_item, is_folder


def _is_animation(result):
    """Use provider genre evidence, never titles or additional detail requests."""
    genres = _am6b_value(result, "genre_ids", []) or _am6b_value(result, "genres", []) or []
    return any(str(_am6b_value(genre, "id", "") if isinstance(genre, dict)
                   or hasattr(genre, "id") else genre) == "16" for genre in genres)


def _anime_search_item(result, mode, title_map):
    # TMDb /search/movie and /search/tv search all genres. Unlike the anime
    # discover endpoint, they do not apply the anime category for us. Use the
    # returned genre evidence; never label a live-action hit as anime.
    if not _is_animation(result):
        return None
    return _catalog_item(result, mode, title_map)


def _generic_item(result, forced_section=None):
    tmdb_id = _am6b_value(result, "id", "")
    if not tmdb_id:
        return None
    animated = _is_animation(result)
    # The provider's TV type includes anime. Dedicated live-action shelves and
    # searches must exclude it, including already cached provider pages. Global
    # search keeps animation and labels it correctly instead of hiding it.
    if animated and forced_section in ("tv", "movie"):
        return None
    result_type = str(_am6b_value(result, "media_type", "") or forced_section or "").lower()
    if result_type in ("movie", "movies"):
        mode = "movies"
        media_type = "movie"
        media_kind = "anime_movie" if animated else "movie"
    elif result_type in ("tv", "show", "series"):
        mode = "tv"
        media_type = "tv"
        media_kind = "anime_series" if animated else "tv_series"
    else:
        return None

    localized_title = _am6b_catalog_localized_title(result, mode, "zh-CN")
    provider_title = _am6b_catalog_title(result, mode)
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(result, original_key, "") or ""
    display_title = localized_title or provider_title or original
    if not display_title:
        return None

    list_item = xbmcgui.ListItem(label=display_title)
    if original and original != display_title:
        list_item.setLabel2(original)
    list_item.setContentLookup(False)
    _set_video_metadata(list_item, result, display_title, mode)
    _set_catalog_art(list_item, result)
    titles = {"zh": localized_title or "", "en": ""}
    _set_title_properties(list_item, titles, original, media_kind)
    from lib.clients.tmdb.frontend_metadata import apply as apply_frontend
    apply_frontend(list_item, tmdb_id, mode, dict(title=display_title, original_title=original), titles)
    if mode == "tv":
        from lib.clients.tmdb.season_cards import apply
        apply(list_item, tmdb_id, display_title, chinese_title=localized_title or "")

    is_folder = mode != "movies"
    if not is_folder:
        from lib.clients.cinema_ui import catalog_playable_property
        list_item.setProperty("IsPlayable", catalog_playable_property())
    url = _build_url(
        "am6b_open_streaming_item",
        mode=mode,
        submode="",
        id=tmdb_id,
        title=display_title,
        original=original,
        media_type=media_type,
    )
    return url, list_item, is_folder


def _preferred_source_title(metadata, mode, fallback_title=""):
    localized = _am6b_catalog_localized_title(metadata, mode, "en-US")
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(metadata, original_key, "") or ""
    original = original.strip() if isinstance(original, str) else ""
    fallback_title = fallback_title.strip() if isinstance(fallback_title, str) else ""
    return localized or original or fallback_title


def handle_am6b_open_item(params):
    """Resolve a stable source-search title only after the user opens a card.

    First-screen cards never wait for an English request.  At click time the
    minimal TMDb detail request is performed in en-US with only external IDs
    appended, then handed to the movie/TV continuation
    functions.  This preserves the old
    English source-search contract without adding work to directory rendering.
    """
    mode = str(params.get("mode") or "").lower()
    if mode not in ("movies", "tv"):
        return False
    tmdb_id = str(params.get("id") or "").strip()
    if not tmdb_id:
        return False

    media_type = "movie" if mode == "movies" else "tv"
    fallback_title = str(params.get("original") or params.get("title") or "").strip()
    _ensure_tmdb_key()

    # Import the detail/playback graph only after an explicit click.  Calling
    # Movie/TV.details directly is deliberate: the older tmdb_get cache key does
    # not include locale, while the bounded transport cache keys the full URL.
    from lib.clients.tmdb.tmdb import TmdbClient

    if mode == "movies":
        from lib.api.tmdbv3api.objs.movie import Movie

        details_client = Movie()
    else:
        from lib.api.tmdbv3api.objs.tv import TV

        details_client = TV()

    previous_language = details_client.language
    metadata = None
    try:
        details_client.language = "en-US"
        metadata = details_client.details(tmdb_id, append_to_response="external_ids")
    except Exception as error:
        # Never include provider exception text; authenticated URLs may appear.
        kodilog("AM6B click-time source title resolution failed: " +
                type(error).__name__ + "/" + type(error.__context__).__name__, level=xbmc.LOGWARNING)
    finally:
        details_client.language = previous_language

    if not metadata:
        # Retrying the same unavailable provider through the legacy route only
        # doubles latency and used to leave Kodi's directory handle unfinished.
        from lib.utils.directory_failure import fail_directory

        return fail_directory()

    try:
        source_title = _preferred_source_title(metadata, mode, fallback_title)
        if mode == "movies":
            TmdbClient._show_tmdb_movie(metadata, mode, source_title, tmdb_id)
        else:
            TmdbClient._show_tmdb_shows(metadata, mode, source_title, tmdb_id, media_type)
    except Exception as error:
        kodilog("AM6B detail continuation failed: " + type(error).__name__, level=xbmc.LOGWARNING)
        from lib.utils.directory_failure import fail_directory

        return fail_directory()
    return True


def _fetch_streaming_page(section, page, query=""):
    client = TMDb(obj_cached=False)
    params = {
        "page": page,
        "language": "zh-CN",
        "include_adult": "false",
    }
    if query:
        params["query"] = query
        path = "/search/{}".format(section)
    else:
        contract = AM6B_STREAMING_CATALOGS.get(section)
        if not contract:
            return None
        path = contract[1]
        if section == "movie":
            params["region"] = "CN"
    return client._request_obj(
        path,
        params=urlencode(params),
        call_cached=False,
        add_lang=False,
    )


def _load_streaming_page(kind, section, page, query="", refresh=False):
    cache_key = _am6b_streaming_cache_key(kind, section, page, query)
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    data = _fetch_streaming_page(section, page, query=query)
    if data is not None:
        ttl = AM6B_STREAMING_SEARCH_CACHE_TTL if kind == "search" else AM6B_STREAMING_CATALOG_CACHE_TTL
        cache.set(cache_key, data, ttl)
    return data


def _add_next_item(directory_items, action, page, label="下一页", **params):
    next_item = xbmcgui.ListItem(label="下一页")
    next_item.setProperty("Bobi.NextPage", "true")
    # The legacy anime route increments the supplied CURRENT page on entry;
    # direct catalogue/search routes receive the TARGET page. Increment once.
    params["page"] = page if action == "next_page_anime" else page + 1
    directory_items.append((_build_url(action, **params), next_item, True))


def _render_directory(data, item_builder, category_label, content_type, next_action=None, page=1, next_params=None):
    handle = _plugin_handle()
    xbmcplugin.setContent(handle, content_type)
    xbmcplugin.setPluginCategory(handle, category_label)
    if data is None:
        # Kodi discards a failed directory and can expose its generic video
        # root. Return an explicitly failed, non-playable retry row instead:
        # transport success here does not mean the provider returned results.
        retry_action = next_action
        retry_params = dict(next_params or {})
        retry_params["page"] = page
        if retry_action == "next_page_anime":
            # This legacy route increments page before fetching. A retry must
            # enter the catalog directly, keeping the page that actually failed.
            retry_action = "search_item"
            retry_params["api"] = "tmdb"
        if retry_action:
            retry = xbmcgui.ListItem(label="加载失败 · 选择重试")
            retry.setProperty("IsPlayable", "false")
            retry.setProperty("AM6B.Directory.error", "provider_unavailable")
            retry.getVideoInfoTag().setPlot(
                "列表加载失败。选择此项重试，或返回修改搜索。"
            )
            xbmcplugin.addDirectoryItems(handle, [
                (_build_url(retry_action, **retry_params), retry, True),
            ])
            kodilog("AM6B directory provider unavailable; retry row retained", xbmc.LOGWARNING)
            xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
        else:
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return True

    directory_items = []
    with image_batch():
        for result in _am6b_value(data, "results", []) or []:
            item = item_builder(result)
            if item:
                directory_items.append(item)

    total_pages = _positive_int(_am6b_value(data, "total_pages", 0), 0)
    if next_action and total_pages > page:
        _add_next_item(directory_items, next_action, page, **(next_params or {}))
    xbmcplugin.addDirectoryItems(handle, directory_items)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    from lib.clients.tmdb.frontend_metadata import flush
    flush()
    from lib.clients.tmdb.season_cards import enqueue_directory
    enqueue_directory(directory_items)
    return True


def handle_am6b_anime_catalog(params, next_page=False):
    """Render the two locked AM6B anime rows without the generic navigation graph."""
    category = params.get("category", "")
    contract = AM6B_FAST_CATALOGS.get(category)
    if not contract:
        return False
    expected_mode, category_label = contract
    submode = params.get("submode") or expected_mode
    if submode != expected_mode:
        return False
    page = _positive_int(params.get("page"), 1) + (1 if next_page else 0)

    _ensure_tmdb_key()
    # Do not launch secondary-locale work until Kodi has accepted the usable
    # Chinese-first directory.  This keeps the first clickable frame ahead of
    # all optional network and cache activity.
    localized = _localized_catalogs(category, submode, page, schedule_hydration=False)
    zh_data = localized.get("zh-CN")
    zh_fallback_data = localized.get("zh-TW")
    en_data = localized.get("en-US")
    data = zh_data or zh_fallback_data or en_data

    title_map = _am6b_build_catalog_title_map(
        zh_data,
        en_data,
        submode,
        zh_fallback_data=zh_fallback_data,
    )
    rendered = _render_directory(
        data,
        lambda result: _catalog_item(result, submode, title_map),
        category_label,
        "movies" if submode == "movies" else "tvshows",
        next_action="next_page_anime",
        page=page,
        next_params={
            "mode": "anime",
            "submode": submode,
            "category": category,
        },
    )
    _schedule_missing_catalog_locales(category, submode, page, localized)
    return rendered


def handle_am6b_streaming_catalog(params, next_page=False):
    section = str(params.get("section") or "").lower()
    contract = AM6B_STREAMING_CATALOGS.get(section)
    if not contract:
        return False
    mode, _path, category_label = contract
    page = _positive_int(params.get("page"), 1) + (1 if next_page else 0)
    _ensure_tmdb_key()
    data = _safe_fetch(
        "{} catalog".format(section),
        lambda: _load_streaming_page("catalog", section, page),
    )
    return _render_directory(
        data,
        lambda result: _generic_item(result, forced_section=section),
        category_label,
        "movies" if mode == "movies" else "tvshows",
        next_action="am6b_streaming_catalog",
        page=page,
        next_params={"section": section},
    )


def _keyboard_query(heading):
    keyboard = xbmc.Keyboard("", heading)
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return ""
    return str(keyboard.getText() or "").strip()


def handle_am6b_streaming_search(params):
    section = str(params.get("section") or "multi").lower()
    if section not in AM6B_SEARCH_SECTIONS:
        return False
    page = _positive_int(params.get("page"), 1)
    query = str(params.get("query") or "").strip()
    prompted = not query and page == 1
    if not query and page == 1:
        headings = {
            "tv": "搜索电视剧",
            "movie": "搜索电影",
            "multi": "搜索影视",
            "anime_tv": "搜索动漫",
            "anime_movie": "搜索动漫电影",
        }
        query = _keyboard_query(headings[section])
    if not query:
        xbmcplugin.endOfDirectory(_plugin_handle(), cacheToDisc=False)
        # A dismissed keyboard is a navigation cancellation, not an empty
        # catalog. Do not strand the Cinema user on a lone parent-directory tile.
        # Headless requests and other skins retain their existing behavior.
        if (xbmc.getSkinDir() == "skin.bobbi.cinema"
                and xbmc.getCondVisibility("Window.IsActive(videos)")):
            xbmc.executebuiltin("ActivateWindow(1196)")
        return True

    _ensure_tmdb_key()
    if section in ("anime_tv", "anime_movie"):
        submode = "tv" if section == "anime_tv" else "movies"
        localized = _localized_anime_search(
            query, submode, page, schedule_hydration=False
        )
        zh_data = localized.get("zh-CN")
        zh_fallback_data = localized.get("zh-TW")
        en_data = localized.get("en-US")
        data = zh_data or zh_fallback_data or en_data
        title_map = _am6b_build_catalog_title_map(
            zh_data,
            en_data,
            submode,
            zh_fallback_data=zh_fallback_data,
        )
        rendered = _render_directory(
            data,
            lambda result: _anime_search_item(result, submode, title_map),
            "动漫搜索" if submode == "tv" else "动漫电影搜索",
            "tvshows" if submode == "tv" else "movies",
            next_action="am6b_streaming_search",
            page=page,
            next_params={"section": section, "query": query},
        )
        # New Cinema searches open a query-bearing URL from the separate prompt
        # action. Do not refresh an older bookmarked query-less interactive URL.
        if not (prompted and xbmc.getSkinDir() == 'skin.bobbi.cinema'):
            _schedule_missing_search_locales(query, submode, page, localized)
        return rendered

    data = _safe_fetch(
        "{} search".format(section),
        lambda: _load_streaming_page("search", section, page, query=query),
    )
    forced_section = None if section == "multi" else section
    return _render_directory(
        data,
        lambda result: _generic_item(result, forced_section=forced_section),
        "搜索结果",
        "videos" if section == "multi" else ("movies" if section == "movie" else "tvshows"),
        next_action="am6b_streaming_search",
        page=page,
        next_params={"section": section, "query": query},
    )


def warm_am6b_primary_catalogs(refresh_existing=False):
    """Warm four page-one zh-CN rows with at most two concurrent requests."""
    if _playback_active():
        return 0
    _ensure_tmdb_key()
    pending = []

    for category, contract in AM6B_FAST_CATALOGS.items():
        submode = contract[0]
        key = _am6b_anime_catalog_cache_key(category, submode, 1, "zh-CN")
        if refresh_existing or cache.get(key) is None:
            def fetch_anime(current_category=category, current_mode=submode, cache_key=key):
                if _playback_active():
                    return None
                data = _fetch_catalog(current_category, current_mode, 1, "zh-CN")
                if data is not None:
                    cache.set(cache_key, data, AM6B_ANIME_CATALOG_CACHE_TTL)
                return data

            pending.append(fetch_anime)

    for section in AM6B_STREAMING_CATALOGS:
        key = _am6b_streaming_cache_key("catalog", section, 1)
        if refresh_existing or cache.get(key) is None:
            def fetch_streaming(current_section=section, cache_key=key):
                if _playback_active():
                    return None
                data = _fetch_streaming_page(current_section, 1)
                if data is not None:
                    cache.set(cache_key, data, AM6B_STREAMING_CATALOG_CACHE_TTL)
                return data

            pending.append(fetch_streaming)

    if not pending:
        return 0
    successes = 0
    with ThreadPoolExecutor(max_workers=min(2, len(pending))) as executor:
        futures = [executor.submit(fetcher) for fetcher in pending]
        for future in futures:
            try:
                if future.result() is not None:
                    successes += 1
            except Exception:
                kodilog("AM6B primary catalog warmup request failed")
    return successes
