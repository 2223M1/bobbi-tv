import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, List, Mapping, Optional
from urllib.parse import unquote

import xbmc
from xbmcgui import Dialog

from lib.clients.nuvio.constants import NUVIO_ADDONS_KEY
from lib.clients.nuvio.helpers import (
    get_selected_stream_addon_records,
)
from lib.clients.nuvio.helpers import (
    get_selected_stream_addons as get_selected_nuvio_stream_addons,
)
from lib.clients.stremio.addon_client import StremioAddonClient
from lib.clients.stremio.constants import STREMIO_ADDON_ALIASES_KEY, STREMIO_ADDONS_KEY
from lib.clients.stremio.helpers import (
    get_addon_by_base_url,
    get_addon_display_name,
    get_selected_stream_addons,
)
from lib.clients.stremio.playback import (
    StremioPlaybackError,
    candidate_from_payload,
    classify,
    current_stremio_playback_capabilities,
    normalize_stream,
    payload_from_torrent,
    resolve,
)
from lib.db.cached import cache
from lib.domain.torrent import TorrentStream
from lib.gui.custom_dialogs import source_select
from lib.gui.search_status_window import SearchStatusWindow, SearchTaskManager
from lib.player import JacktookPLayer
from lib.utils.clients.utils import get_client, update_dialog
from lib.utils.debrid.debrid_utils import check_debrid_cached, is_supported_debrid_type
from lib.utils.general.utils import (
    DialogListener,
    Indexer,
    IndexerType,
    Players,
    SearchVariant,
    build_media_metadata,
    cache_results,
    clean_auto_play_undesired,
    get_cached_results,
    info_hash_to_magnet,
    normalize_tv_data,
    post_process,
    pre_process,
    safe_json_loads,
    set_content_type,
    set_watched_title,
)
from lib.utils.kodi.settings import auto_play_enabled, get_setting
from lib.utils.kodi.utils import (
    ADDON_PATH,
    cancel_playback,
    close_busy_dialog,
    kodilog,
    notification,
    translation,
)
from lib.utils.player.utils import resolve_playback_url
from lib.utils.source_manager import parse_source_selection, reconcile_source_selection

TITLE_LANGUAGE_LOCALIZED_FIRST = "localized_first"
TITLE_LANGUAGE_ENGLISH_FIRST = "english_first"
TITLE_LANGUAGE_ENGLISH_ONLY = "english_only"
MAX_SEARCH_WORKERS = 8
MAX_STREMIO_ADDONS_PER_SEARCH = 8


class SearchCancelled(Exception):
    """Raised when the user cancels an interactive search flow."""

    def __init__(self, results: Optional[List[TorrentStream]] = None):
        super().__init__("Search cancelled")
        self.results = results or []


class SilentProgressDialog:
    """No-op progress dialog for flows that should not show Kodi progress UI."""

    def create(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass

    def close(self):
        pass


def _build_search_cache_scope(scoped_addon_url: str = "") -> str:
    flags = {
        "torrent": bool(get_setting("torrent_enable")),
        "jackett": bool(get_setting("jackett_enabled")),
        "prowlarr": bool(get_setting("prowlarr_enabled")),
        "burst": bool(get_setting("jacktookburst_enabled")),
        "jackgram": bool(get_setting("jackgram_enabled")),
        "external_scraper": bool(get_setting("external_scraper_enabled")),
        "stremio": bool(get_setting("stremio_enabled")),
        "nuvio": bool(get_setting("nuvio_enabled")),
        "rd": bool(get_setting("real_debrid_enabled")),
        "ad": bool(get_setting("alldebrid_enabled")),
        "tb": bool(get_setting("torbox_enabled")),
        "oc": bool(get_setting("offcloud_enabled")),
        "pm": bool(get_setting("premiumize_enabled")),
        "db": bool(get_setting("debrider_enabled")),
        "ed": bool(get_setting("easydebrid_enabled")),
    }
    selected_stream_addons = str(cache.get(STREMIO_ADDONS_KEY) or "")
    selected_nuvio_addons = str(cache.get(NUVIO_ADDONS_KEY) or "")
    stremio_addon_aliases = json.dumps(cache.get(STREMIO_ADDON_ALIASES_KEY) or {}, sort_keys=True)
    source_manager_selection = str(cache.get("source_manager_selection") or "")
    external_scraper_module = str(get_setting("external_scraper_module") or "")
    raw_scope = "{}|{}|{}|{}|{}|{}|{}".format(
        "|".join([f"{key}:{int(value)}" for key, value in sorted(flags.items())]),
        selected_stream_addons,
        selected_nuvio_addons,
        stremio_addon_aliases,
        source_manager_selection,
        external_scraper_module,
        str(scoped_addon_url or ""),
    )
    if xbmc.getSkinDir() == 'skin.bobbi.cinema':
        raw_scope += '|cinema-independent-indexers-v4-catalog-candidates'
    # Two users/instances can share a media title but not their configured
    # private indexers. Only the fingerprint reaches the persisted cache key.
    instance = '\0'.join(str(get_setting(key, '') or '') for key in
        ('jackett_host', 'jackett_port', 'jackett_apikey'))
    raw_scope += '|jackett-instance:' + hashlib.sha256(instance.encode()).hexdigest()
    return hashlib.sha256(raw_scope.encode("utf-8")).hexdigest()


def _filter_isolated_jackgram_cache_results(
    query: str, results: List[TorrentStream]
) -> List[TorrentStream]:
    terms = str(query or "").casefold().split()
    if not terms:
        return results
    return [
        r
        for r in results
        if all(term in str(getattr(r, "title", "") or "").casefold() for term in terms)
    ]


def _search_worker_count() -> int:
    try:
        configured = int(get_setting("thread_number", 6))
    except (TypeError, ValueError):
        configured = 6
    return min(MAX_SEARCH_WORKERS, max(1, configured))


BUILTIN_INDEXER_SETTINGS = {
    Indexer.JACKETT: "jackett_enabled",
    Indexer.PROWLARR: "prowlarr_enabled",
    Indexer.BURST: "jacktookburst_enabled",
    Indexer.JACKGRAM: "jackgram_enabled",
    Indexer.EASYNEWS: "easynews_enabled",
    Indexer.STREMIO: "stremio_enabled",
    Indexer.EXTERNAL_SCRAPER: "external_scraper_enabled",
}


def _get_source_manager_selection() -> Optional[set]:
    """Return the cached source-manager selection as a set of strings.

    Missing or corrupt values return None so callers use the legacy open
    fallback. A persisted empty list remains an explicit empty whitelist.
    """
    parsed = parse_source_selection(cache.get("source_manager_selection"))
    return set(parsed) if parsed is not None else None


def _is_source_enabled(indexer_key, stremio_addon_key=None, addon_origin="Stremio"):
    selected = _get_source_manager_selection()

    # Missing or corrupt cache → everything is enabled (no whitelist restriction)
    if selected is None:
        return True

    # Compatible stream addons are keyed by their independent account origin.
    if stremio_addon_key:
        return f"{addon_origin}:{stremio_addon_key}" in selected

    # External scraper uses its configured module name as the cache key.
    # The fallback literal "External Scraper" supports older caches.
    if indexer_key == Indexer.EXTERNAL_SCRAPER:
        if not get_setting("external_scraper_enabled"):
            return False
        module_name = get_setting("external_scraper_module_name") or "External Scraper"
        return module_name in selected or "External Scraper" in selected

    # Managed builtin sources are enabled only when explicitly selected.
    return str(indexer_key) in selected


def _is_enabled(setting_id):
    value = get_setting(setting_id)
    return value is True or str(value).lower() == "true"


def _get_selected_nuvio_stream_addons_safe():
    try:
        return get_selected_nuvio_stream_addons()
    except Exception as error:
        kodilog(f"Unable to load selected Nuvio addons ({type(error).__name__})")
        return []


def _clean_title_candidate(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _unique_title_candidates(candidates: List[str]) -> List[str]:
    unique = []
    seen = set()

    for candidate in candidates:
        cleaned = _clean_title_candidate(candidate)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)

    return unique


def _normalize_search_variant(variant) -> str:
    allowed = {
        SearchVariant.DEFAULT,
        SearchVariant.TITLE_YEAR,
        SearchVariant.ORIGINAL_TITLE,
        SearchVariant.ORIGINAL_TITLE_YEAR,
    }
    return variant if variant in allowed else SearchVariant.DEFAULT


def _normalize_title_language_mode(mode) -> str:
    allowed = {
        TITLE_LANGUAGE_LOCALIZED_FIRST,
        TITLE_LANGUAGE_ENGLISH_FIRST,
        TITLE_LANGUAGE_ENGLISH_ONLY,
    }
    return mode if mode in allowed else TITLE_LANGUAGE_LOCALIZED_FIRST


def _extract_english_tmdb_title(details, mode: str) -> str:
    translations = getattr(details, "translations", None)
    entries = getattr(translations, "translations", translations)
    if not entries:
        return ""

    title_key = "title" if mode == "movies" else "name"

    for entry in entries:
        if getattr(entry, "iso_639_1", "") != "en":
            continue

        data = getattr(entry, "data", None)
        if not data:
            continue

        return _clean_title_candidate(getattr(data, title_key, ""))

    return ""


def _infer_tmdb_year(ids: dict, mode: str) -> Optional[int]:
    if not ids or mode not in ("movies", "tv"):
        return None
    tmdb_id = ids.get("tmdb_id")
    if not tmdb_id:
        return None
    try:
        from lib.clients.tmdb.utils.utils import get_tmdb_media_details

        details = get_tmdb_media_details(tmdb_id, mode)
        date_value = (
            getattr(details, "release_date", None)
            if mode == "movies"
            else getattr(details, "first_air_date", None)
        )
        return int(str(date_value)[:4]) if date_value else None
    except Exception as e:
        kodilog(f"Failed to infer TMDB year: {e}")
        return None


def _build_title_fallback_queries(
    query: str,
    ids: dict,
    mode: str,
    variant: str = SearchVariant.DEFAULT,
    year: Optional[int] = None,
    title_language_mode: Optional[str] = None,
) -> List[str]:
    variant = _normalize_search_variant(variant)
    title_language_mode = _normalize_title_language_mode(
        title_language_mode
        if title_language_mode is not None
        else get_setting("search_title_language_mode", TITLE_LANGUAGE_LOCALIZED_FIRST)
    )
    candidates = []

    cleaned_query = _clean_title_candidate(query)
    cleaned_year = _clean_title_candidate(year)

    localized_candidate = ""
    if cleaned_query and variant == SearchVariant.DEFAULT:
        localized_candidate = cleaned_query
    elif cleaned_query and cleaned_year and variant == SearchVariant.TITLE_YEAR:
        localized_candidate = f"{cleaned_query} {cleaned_year}"

    if localized_candidate:
        candidates.append(localized_candidate)

    if not ids:
        return _unique_title_candidates(candidates)

    tmdb_id = ids.get("tmdb_id")
    if not tmdb_id or mode not in ("movies", "tv"):
        return _unique_title_candidates(candidates)

    try:
        from lib.clients.tmdb.utils.utils import get_tmdb_media_details

        details = get_tmdb_media_details(tmdb_id, mode)
    except Exception as e:
        kodilog(f"Failed to load TMDB titles for fallback: {e}")
        details = None

    if not details:
        return _unique_title_candidates(candidates)

    english_title = _extract_english_tmdb_title(details, mode)
    original_title = getattr(details, "original_title", "") or getattr(details, "original_name", "")

    english_candidate = ""
    original_candidate = ""
    if variant == SearchVariant.DEFAULT:
        english_candidate = english_title
        original_candidate = original_title
    elif variant == SearchVariant.TITLE_YEAR and cleaned_year:
        if english_title:
            english_candidate = f"{english_title} {cleaned_year}"
        if original_title:
            original_candidate = f"{original_title} {cleaned_year}"

    if variant == SearchVariant.DEFAULT or variant == SearchVariant.TITLE_YEAR:
        if title_language_mode == TITLE_LANGUAGE_ENGLISH_ONLY:
            candidates = [english_candidate, original_candidate]
            if not any(candidates) and localized_candidate:
                candidates.append(localized_candidate)
        elif title_language_mode == TITLE_LANGUAGE_ENGLISH_FIRST:
            candidates = [english_candidate, original_candidate, localized_candidate]
        else:
            candidates = [localized_candidate, english_candidate, original_candidate]
    elif variant == SearchVariant.ORIGINAL_TITLE:
        if original_title:
            candidates.append(original_title)
        elif cleaned_query:
            candidates.append(cleaned_query)
    elif variant == SearchVariant.ORIGINAL_TITLE_YEAR:
        if original_title and cleaned_year:
            candidates.append(f"{original_title} {cleaned_year}")
        elif original_title:
            candidates.append(original_title)
        elif cleaned_query and cleaned_year:
            candidates.append(f"{cleaned_query} {cleaned_year}")
        elif cleaned_query:
            candidates.append(cleaned_query)

    return _unique_title_candidates(candidates)


def _anime_absolute_query(ids, mode, season):
    """One additional query for known first-season anime, regardless of age.

    Metadata is shared with title fallback. Do not infer season 2 absolute
    numbering or add extra requests to normal live-action searches.
    """
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or mode != 'tv' or str(season) != '1' or not (ids or {}).get('tmdb_id'):
        return ''
    try:
        from lib.clients.tmdb.utils.utils import get_tmdb_media_details
        details = get_tmdb_media_details(ids['tmdb_id'], mode)
        genres = [g.get('id') if isinstance(g, Mapping) else getattr(g, 'id', None)
                  for g in (getattr(details, 'genres', None) or [])]
        if 16 not in genres:
            return ''
        title = _extract_english_tmdb_title(details, mode) or getattr(details, 'original_name', '')
        return str(title).strip() if title else ''
    except (ValueError, TypeError, AttributeError, OSError):
        return ''


def _anime_release_query(ids, mode):
    """Native title for group discovery; no age distinction or guessed alias."""
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or mode not in ('tv', 'movies') or not (ids or {}).get('tmdb_id'):
        return ''
    try:
        from lib.clients.tmdb.utils.utils import get_tmdb_media_details
        details = get_tmdb_media_details(ids['tmdb_id'], mode)
        genres = [g.get('id') if isinstance(g, Mapping) else getattr(g, 'id', None)
                  for g in (getattr(details, 'genres', None) or [])]
        if 16 not in genres:
            return ''
        language = getattr(details, 'original_language', '')
        if isinstance(language, str) and language and language != 'ja':
            return ''  # Japanese release-group queries must not starve western animation.
        original = getattr(details, 'original_name' if mode == 'tv' else 'original_title', '')
        return str(original or _extract_english_tmdb_title(details, mode) or '').strip()
    except (ValueError, TypeError, AttributeError, OSError):
        return ''


def _cinema_catalog_aliases(ids, mode):
    """Reuse the existing bounded/cached detail request, with exact ID binding."""
    if mode not in ('tv', 'movies') or not (ids or {}).get('tmdb_id'):
        return []
    from lib.clients.tmdb.utils.utils import get_tmdb_media_details
    from lib.api.tmdbv3api.as_obj import AsObj
    try:
        details = get_tmdb_media_details(ids['tmdb_id'], mode)
        if isinstance(details, AsObj):
            details = details.to_dict()
        if not isinstance(details, dict) or str(details.get('id')) != str(ids['tmdb_id']):
            return []
        keys = ('name', 'original_name') if mode == 'tv' else ('title', 'original_title')
        aliases = [details.get(key) for key in keys]
        for item in details.get('translations', {}).get('translations', [])[:128]:
            if isinstance(item, dict) and isinstance(item.get('data'), dict):
                aliases.append(item['data'].get(keys[0]))
        alternate = details.get('alternative_titles') or {}
        for item in alternate.get('results', alternate.get('titles', []))[:128]:
            if isinstance(item, dict):
                aliases.append(item.get('title'))
        return list(dict.fromkeys(a.strip() for a in aliases if isinstance(a, str) and 2 <= len(a.strip()) <= 512))
    except (ValueError, TypeError, AttributeError, OSError):
        return []


def _cinema_anime_queries(ids, mode):
    """Independent ID/genre evidence for a bounded multilingual anime plan."""
    if mode != 'tv' or not (ids or {}).get('tmdb_id'):
        return []
    from lib.clients.tmdb.utils.utils import get_tmdb_media_details
    from lib.api.tmdbv3api.as_obj import AsObj
    from lib.utils.general.anime_identity import catalog_anime_queries
    try:
        details = get_tmdb_media_details(ids['tmdb_id'], mode)
        if isinstance(details, AsObj):
            details = details.to_dict()
        return catalog_anime_queries(details, ids['tmdb_id'])
    except (ValueError, TypeError, AttributeError, OSError):
        return []


def _cinema_anime_range_context(ids, mode, catalog_season, release_season, episode):
    if mode != 'tv' or not (ids or {}).get('tmdb_id'):
        return None
    from lib.clients.tmdb.utils.utils import get_tmdb_media_details
    from lib.api.tmdbv3api.as_obj import AsObj
    from bobbi_core.anime_range_candidates import context
    try:
        details = get_tmdb_media_details(ids['tmdb_id'], mode)
        if isinstance(details, AsObj):
            details = details.to_dict()
        return context(details, ids['tmdb_id'], catalog_season, release_season, episode)
    except (ValueError, TypeError, AttributeError, OSError):
        return None


def _cinema_release_season(value):
    """Keep explicit zero; invalid supplied context must not skip screening."""
    if type(value) is not int and not isinstance(value, str):
        raise ValueError('Invalid release season')
    number = int(value)
    if not 0 <= number <= 99 or (number == 0 and value not in (0, '0')):
        raise ValueError('Invalid release season')
    return number


def _cinema_requires_catalog_admission(source):
    """Untrusted title-indexed BT providers share the same work/episode gate."""
    return str(getattr(source, 'indexer', '')) in (str(Indexer.JACKETT), 'AnimeGarden')


def _cinema_filter_catalog_candidates(results, aliases, mode, release_season=None, release_episode=None, fallback_query=None, anime=False, anime_range_context=None):
    from bobbi_core.candidate_titles import matches
    from bobbi_core.search_completion import replace_rows
    # Missing catalog evidence is unknown, not a negative work match. The
    # original request remains a lexical screen only; never publish it as a
    # trusted catalog alias or relax the explicit season/episode checks.
    candidate_aliases = aliases or ([fallback_query] if isinstance(fallback_query, str) else [])
    title_basis = 'catalog_aliases' if aliases else ('request_query_unverified' if candidate_aliases else 'unavailable')
    from lib.utils.general.anime_identity import animation_release_conflict
    screened = [source for source in results or [] if not (
        anime and aliases and _cinema_requires_catalog_admission(source)
        and animation_release_conflict(getattr(source, 'title', ''), aliases))]
    from bobbi_core.anime_range_candidates import eligible as range_eligible
    range_rows = [source for source in screened if anime and mode == 'tv'
                  and _cinema_requires_catalog_admission(source)
                  and range_eligible(getattr(source, 'title', ''), anime_range_context, release_season, release_episode)]
    for source in range_rows:
        source.requiresCatalogEpisodeProof = True
    kept = [source for source in screened
            if not _cinema_requires_catalog_admission(source)
            or source in range_rows
            or matches(getattr(source, 'title', ''), candidate_aliases, mode, release_season=release_season)]
    if mode == 'tv' and release_season is not None and release_episode is not None:
        from lib.utils.general.processors import PreProcessBuilder
        scoped = [row for row in kept if _cinema_requires_catalog_admission(row)]
        eligible = PreProcessBuilder(scoped).filter_sources('', release_episode, release_season,
            anime_aliases=aliases if anime else None, anime_range_context=anime_range_context if anime else None).get_results()
        kept = [row for row in kept if row not in scoped or row in eligible]
    rejected = len(results or []) - len(kept)
    if rejected or title_basis == 'request_query_unverified':
        kodilog('Cinema catalog candidate screening: rejected={}, kept={}; title_basis={}; labels are not readiness'.format(rejected, len(kept), title_basis), level=xbmc.LOGINFO)
    return replace_rows(results, kept)


def _movie_catalog_context(ids, mode):
    if mode not in ('movie', 'movies'):
        return None
    from lib.clients.tmdb.movie_years import cached_movie_identity
    return cached_movie_identity((ids or {}).get('tmdb_id'))


def _tv_completed_context(ids, mode, tv_data, release_order=None):
    if mode != 'tv':
        return None
    from lib.clients.tmdb.tv_ended_window import cached_window
    return cached_window(ids, tv_data, release_order)


def _filter_tv_completed_candidates(results, evidence, ids, tv_data):
    if evidence is None:
        return results
    try:
        identifier = int(ids.get('tmdb_id'))
    except (AttributeError, TypeError, ValueError):
        return results
    from bobbi_core.tv_ended_window import status
    return [row for row in results if (
        str(getattr(row, 'type', '')).casefold() != 'torrent'
        or bool(getattr(row, 'preparedResourceId', ''))
        or status(getattr(row, 'title', ''), evidence, identifier,
                  tv_data.get('season', 1), tv_data.get('episode', 1))['status'] != 'conflict')]


def _filter_movie_year_candidates(results, catalog):
    """Reject explicit BT movie-year contradictions; unknown is not proof."""
    if not catalog or not catalog['aliases']:
        return results
    from bobbi_core.movie_identity import evidence_status
    kept = []
    for source in results or []:
        # Cloud/direct rows retain their existing independent identity gates.
        torrent = (str(getattr(source, 'type', '')) == str(IndexerType.TORRENT)
                   or bool(getattr(source, 'infoHash', '')))
        if (torrent and not getattr(source, 'preparedResourceId', '')
                and str(getattr(source, 'type', '')) not in (str(IndexerType.DIRECT), str(IndexerType.DEBRID), str(IndexerType.STREMIO_DEBRID))
                and evidence_status([getattr(source, 'title', '')], catalog['aliases'],
                    catalog['evidence'], catalog['tmdb_id'])['status'] == 'conflict'):
            continue
        kept.append(source)
    return kept


def _perform_search_with_title_fallback(
    indexer_key,
    dialog,
    query: str,
    ids: dict,
    mode: str,
    *args,
    variant: str = SearchVariant.DEFAULT,
    year: Optional[int] = None,
    title_language_mode: str = TITLE_LANGUAGE_LOCALIZED_FIRST,
    **kwargs,
):
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    from lib.clients.fanout_diagnostics import observe_owner
    variant = _normalize_search_variant(variant)
    title_language_mode = _normalize_title_language_mode(title_language_mode)
    queries = _build_title_fallback_queries(
        query,
        ids,
        mode,
        variant,
        year,
        title_language_mode=title_language_mode,
    )

    anime_query = _anime_absolute_query(ids, mode, args[0] if args else None) if indexer_key == Indexer.JACKETT else ''
    release_query = _anime_release_query(ids, mode) if indexer_key == Indexer.JACKETT else ''
    screen_catalog = (indexer_key == Indexer.JACKETT and xbmc.getSkinDir() == 'skin.bobbi.cinema'
                      and mode in ('tv', 'movies') and bool((ids or {}).get('tmdb_id')))
    catalog_aliases = _cinema_catalog_aliases(ids, mode) if screen_catalog else []
    anime_titles = _cinema_anime_queries(ids, mode) if screen_catalog else []
    kwargs.pop('anime_title_queries', None)  # Only the ID-bound catalogue supplies this plan.
    if anime_titles:
        kwargs['anime_title_queries'] = anime_titles
    kwargs.pop('movie_years', None)  # Never accept a caller-supplied year whitelist.
    kwargs.pop('movie_tmdb_id', None)
    kwargs.pop('movie_imdb_id', None)
    if screen_catalog and mode == 'movies':
        from lib.clients.tmdb.movie_years import cached_movie_identity
        identity = cached_movie_identity(ids.get('tmdb_id'))
        if identity is not None:
            evidence = identity['evidence']
            kwargs['movie_years'] = evidence
            kwargs['movie_tmdb_id'] = int(ids['tmdb_id'])
            kwargs['movie_imdb_id'] = identity.get('imdb_id')
            year = evidence.primary_year
    release_order = None
    if screen_catalog and mode == 'tv' and len(args) >= 2:
        from lib.clients.tmdb.episode_order import release_pair
        release_order = release_pair(ids, {'season': args[0], 'episode': args[1]})
    search_args = args
    if release_order:
        search_args = (release_order['season'], release_order['episode']) + args[2:]
    range_context = (_cinema_anime_range_context(ids, mode, _cinema_release_season(args[0]),
                        _cinema_release_season(search_args[0]), int(search_args[1]))
                     if screen_catalog and anime_titles and len(args) >= 2 else None)
    publish = kwargs.pop('publish', None)
    if publish is not None and indexer_key == Indexer.JACKETT:
        def publish_checked(rows):
            if screen_catalog:
                rows = _cinema_filter_catalog_candidates(rows, catalog_aliases, mode,
                    release_season=_cinema_release_season(search_args[0]) if mode == 'tv' and len(search_args) >= 2 else None,
                    release_episode=int(search_args[1]) if mode == 'tv' and len(search_args) >= 2 else None,
                    fallback_query=query, anime=bool(anime_titles), anime_range_context=range_context)
            return publish(rows)
        kwargs['publish'] = publish_checked
    if screen_catalog and len(queries) > 1:
        # One bounded shared fanout, retaining all identity/season gates. Do not
        # let a first alias's partial hits hide releases found by another alias.
        results = _perform_search(indexer_key, dialog, queries[0], mode, *search_args,
            variant=variant, year=year, title_queries=queries[:3],
            **({'anime_absolute_query': anime_query} if anime_query else {}),
            **({'anime_release_query': release_query} if release_query else {}), **kwargs)
        observe_owner(results, queries[0], ids, mode, year, args, search_args)
        return _cinema_filter_catalog_candidates(results, catalog_aliases, mode,
            release_season=_cinema_release_season(search_args[0]) if mode == 'tv' and len(search_args) >= 2 else None,
            release_episode=int(search_args[1]) if mode == 'tv' and len(search_args) >= 2 else None,
            fallback_query=query, anime=bool(anime_titles), anime_range_context=range_context)
    completion = None
    for attempt, candidate in enumerate(queries, start=1):
        if attempt > 1:
            kodilog(
                f"Retrying {indexer_key} search with fallback title {candidate!r}",
                level=xbmc.LOGINFO,
            )

        results = _perform_search(
            indexer_key,
            dialog,
            candidate,
            mode,
            *search_args,
            variant=variant,
            year=year,
            **({'anime_absolute_query': anime_query} if anime_query and attempt == 1 else {}),
            **({'anime_release_query': release_query} if release_query and attempt == 1 else {}),
            **kwargs,
        )
        observe_owner(results, candidate, ids, mode, year, args, search_args)
        if screen_catalog:
            results = _cinema_filter_catalog_candidates(results, catalog_aliases, mode,
                        release_season=_cinema_release_season(search_args[0]) if mode == 'tv' and len(search_args) >= 2 else None,
                        release_episode=int(search_args[1]) if mode == 'tv' and len(search_args) >= 2 else None,
                        fallback_query=query, anime=bool(anime_titles), anime_range_context=range_context)
        if isinstance(results, SearchResults):
            completion = (completion or SearchCompletion()).combine(results.completion)
        if results:
            return SearchResults(results, completion) if completion is not None else results

    return SearchResults([], completion) if completion is not None else []


def _source_values(source: Any) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    try:
        return vars(source)
    except TypeError:
        return {}


def _is_stremio_source(source: Any) -> bool:
    values = _source_values(source)
    return bool(
        values.get("stremioMetadata")
        or values.get("stremio_metadata")
        or values.get("addonKey")
        or values.get("addon_key")
    )


def _preferred_stremio_results(raw_streams: Any) -> List[TorrentStream]:
    if not isinstance(raw_streams, (list, tuple)):
        return []

    results = []
    for stream in raw_streams:
        try:
            candidate = normalize_stream(stream, origin="video")
            decision = classify(candidate, current_stremio_playback_capabilities())
            if not decision.supported:
                continue
        except (TypeError, ValueError):
            continue
        is_torrent = decision.source_class == "torrent_hash"
        results.append(
            TorrentStream(
                title=candidate.title or candidate.name or candidate.filename or "",
                type=IndexerType.TORRENT if is_torrent else "direct",
                addonKey="stremio_video",
                indexer=Indexer.STREMIO,
                url=info_hash_to_magnet(candidate.infoHash) if is_torrent else candidate.url or "",
                infoHash=candidate.infoHash or "",
                size=candidate.size or 0,
                streamSubtitles=list(candidate.subtitles),
                stremioMetadata=dict(stream) if isinstance(stream, Mapping) else {},
            )
        )
    return results


def _stremio_metadata_diagnostics(candidate: Any) -> str:
    fields = []
    for field in ("title", "name", "filename"):
        value = getattr(candidate, field, None)
        if not isinstance(value, str):
            continue
        code_points = sorted(
            {
                f"U+{ord(character):04X}"
                for character in value
                if (ord(character) < 0x20 and ord(character) not in {0x09, 0x0A, 0x0D})
                or ord(character) == 0x7F
            }
        )
        if code_points:
            fields.append(f"{field}={','.join(code_points)}")
    return " ".join(fields)


def _prepare_stremio_results(
    results: List[TorrentStream],
    notify_rejections: bool = True,
    rejection_reasons: Optional[List[str]] = None,
) -> List[TorrentStream]:
    prepared = []
    for source_index, result in enumerate(results):
        if not _is_stremio_source(result):
            prepared.append(result)
            continue

        payload = payload_from_torrent(result)
        candidate = candidate_from_payload(payload)
        decision = classify(candidate, current_stremio_playback_capabilities())
        if decision.supported:
            prepared.append(result)
        else:
            diagnostics = f"stremio_result index={source_index} decision={decision.code}"
            if decision.code == "unsafe_metadata":
                metadata_diagnostics = _stremio_metadata_diagnostics(candidate)
                if metadata_diagnostics:
                    diagnostics += f" {metadata_diagnostics}"
            kodilog(diagnostics, xbmc.LOGWARNING)
            if rejection_reasons is not None:
                rejection_reasons.append(decision.reason)
            if notify_rejections:
                notification(decision.reason)
    return prepared


def _resolve_stremio_source(source: Any, context: Optional[Mapping[str, Any]] = None):
    payload = payload_from_torrent(source)
    candidate = candidate_from_payload(payload)
    playback_context = dict(context or {})
    playback_context.update(current_stremio_playback_capabilities())
    decision = classify(candidate, playback_context)
    playback_context["is_torrent"] = decision.source_class == "torrent_hash"

    def legacy_resolver(resolved_payload, _context=None):
        resolved_payload.update(dict(context or {}))
        resolved_payload["is_torrent"] = playback_context["is_torrent"]
        for key in ("type", "debrid_type", "indexer", "is_pack"):
            if key in payload:
                resolved_payload.setdefault(key, payload[key])
        return resolve_playback_url(resolved_payload)

    resolved = resolve(candidate, playback_context, legacy_resolver=legacy_resolver)
    resolved.update(dict(context or {}))
    for key in ("type", "debrid_type", "indexer", "is_pack"):
        if key in payload:
            resolved.setdefault(key, payload[key])
    return resolved


def _resolve_cached_source(source: Any, params: Mapping[str, Any]):
    if _is_stremio_source(source):
        return _resolve_stremio_source(
            source,
            {
                "mode": params.get("mode", ""),
                "ids": safe_json_loads(params.get("ids")),
                "tv_data": safe_json_loads(params.get("tv_data") or "{}"),
                "is_torrent": False,
            },
        )

    legacy_source = source if isinstance(source, Mapping) else payload_from_torrent(source)
    resolved = resolve_playback_url(legacy_source)
    if resolved is None:
        from lib.utils.player.utils import resolve_failure_reason

        kodilog(f"resolve_cached_source_failed reason={resolve_failure_reason(legacy_source)}")
    return resolved


def _handle_super_quick_play(params: dict) -> bool:
    if params.get("force_select"):
        kodilog("Super quick play: force_select requested, skipping cached shortcut")
        return False

    if not get_setting("super_quick_play", False):
        kodilog("Super quick play disabled")
        return False

    ids = safe_json_loads(params.get("ids"))
    key = str(ids.get("original_id") or ids.get("imdb_id") or ids.get("tmdb_id") or "")

    if key:
        tv_data = safe_json_loads(params.get("tv_data") or "{}")
        if tv_data and "season" in tv_data and "episode" in tv_data:
            key += f"_{tv_data['season']}_{tv_data['episode']}"

    if not key:
        kodilog("Super quick play: No valid key found from ids")
        return False

    cached_torrent = cache.get(key)
    if not cached_torrent:
        kodilog("No cached media found")
        return False

    def play_cached_source() -> bool:
        def play(data: dict) -> None:
            for key in (
                "simkl_session_id",
                "simkl_resume_progress",
                "trakt_playback_id",
                "trakt_resume_progress",
                "nuvio_resume_percent",
            ):
                if key in params:
                    data[key] = params[key]
            player = JacktookPLayer()
            player.run(data=data)

        cached_url = cached_torrent.get("url") if isinstance(cached_torrent, Mapping) else None
        if isinstance(cached_url, str) and cached_url.startswith("plugin://"):
            play(dict(cached_torrent))
            return True

        try:
            from lib.cinema.playback_request import reserve_ui_entry
            source = reserve_ui_entry(cached_torrent) if isinstance(cached_torrent, Mapping) else cached_torrent
            playback_info = _resolve_cached_source(source, params)
            if playback_info and isinstance(source, Mapping) and source.get('_ui_reserved_request'):
                playback_info.update(request_id=source['request_id'],
                                     _ui_reserved_request=source['_ui_reserved_request'])
        except StremioPlaybackError as error:
            kodilog(
                f"stremio_playback_error phase=super_quick_play code={error.code}",
                xbmc.LOGWARNING,
            )
            notification(error.user_message)
            return True
        except Exception:
            notification(translation(90144))
            return True

        if not playback_info:
            notification(translation(90144))
            return True

        play(playback_info)
        return True

    if get_setting("silent_resume", False):
        return play_cached_source()

    dialog = Dialog()
    if dialog.yesno(
        translation(90142),
        translation(90143),
    ):
        return play_cached_source()

    kodilog("User chose not to play cached torrent")
    return False


def _process_search_results(
    results,
    mode,
    ep_name,
    episode,
    season,
    scoped_addon_url,
    query,
    media_type,
    rescrape,
    suppress_debrid_dialog=False,
    suppress_busy_dialog=False,
    recommendation_context=None,
):
    release_order = (recommendation_context or {}).get('release_order')
    if isinstance(release_order, dict) and mode == 'tv':
        season, episode = release_order['season'], release_order['episode']
        from lib.utils.parsers.pack_parser import detect_pack_scope
        from lib.utils.general.processors import explicit_episode_conflict
        # Renumbered later seasons require explicit release-season evidence;
        # an unlabelled first-season pack cannot inherit the new season.
        if season != release_order['catalog_season']:
            results = [result for result in results if (
                season in detect_pack_scope(result.title, season)['pack_seasons']
                or (detect_pack_scope(result.title, season)['pack_type'] == 'episode'
                    and not explicit_episode_conflict(result.title, season, episode)))]
    # Provider sorting/bypass preferences cannot override a positively wrong
    # season/episode in the Cinema picker. Unknown/absolute numbering is kept
    # for exact metadata resolution; this does not manufacture a file match.
    if recommendation_context is not None and mode in ('tv', 'anime'):
        from lib.utils.general.processors import explicit_episode_conflict
        results = [result for result in results
                   if not explicit_episode_conflict(result.title, season, episode)]
    bypassed_streams = []
    other_results = results

    if get_setting("stremio_bypass_addons", True):
        bypass_list_str = str(get_setting("stremio_bypass_addon_list", "") or "")
        bypass_addons = [value.strip() for value in bypass_list_str.split(",") if value.strip()]

        def is_bypassed(result):
            if result.addonKey and result.addonKey in bypass_addons:
                return True

            legacy_name = (result.addonSourceName or result.indexer or "").lower()
            return any(addon == legacy_name for addon in bypass_addons)

        bypassed_streams = [res for res in results if is_bypassed(res)]
        other_results = [res for res in results if not is_bypassed(res)]

    pre_results = []
    if other_results:
        pre_results = pre_process_results(
            other_results,
            mode,
            ep_name,
            episode,
            season,
            skip_episode_filter=bool(scoped_addon_url),
            anime_aliases=((recommendation_context or {}).get('catalog_aliases')
                if 16 in ((recommendation_context or {}).get('genre_ids') or []) else None),
            anime_range_context=(recommendation_context or {}).get('anime_range_context'),
        )

    post_results = []
    if pre_results:
        post_results = process_results(
            pre_results,
            query,
            mode,
            media_type,
            rescrape,
            episode,
            suppress_dialog=suppress_debrid_dialog,
            suppress_busy_dialog=suppress_busy_dialog,
            **({"recommendation_context": recommendation_context} if recommendation_context is not None else {}),
        )

    # Combine results, prioritizing bypassed streams exact native sorting
    return bypassed_streams + post_results


def run_search_entry(params: dict, catalog_sources=None):
    from lib.clients.cinema_ui import is_ui_action
    ui_action = is_ui_action()
    if ui_action:
        # Choosing a work is not consent to choose a source. Keep the shared
        # picker open until an explicit source click, including the Cinema skin.
        # Exact next-episode continuation has its own owner-bound entry path.
        params = dict(params, skip_cancel_on_back=True, force_select=True)
    # Cinema must compare the shared pool on every ordinary Play request;
    # an old single-source quick-play entry would bypass new providers.
    if not ui_action and xbmc.getSkinDir() != 'skin.bobbi.cinema' and _handle_super_quick_play(params):
        return

    query = params.get("query", "")
    mode = params.get("mode", "")
    media_type = params.get("media_type", "")
    ids = safe_json_loads(params.get("ids"))
    tv_data = normalize_tv_data(safe_json_loads(params.get("tv_data")))
    direct = params.get("direct", False)
    rescrape = params.get("rescrape", False)
    skip_cancel = params.get("skip_cancel_on_back", False)
    jackgram_only = (
        str(params.get("jackgram_only", "")).lower() == "true"
        or params.get("jackgram_only") is True
    )
    playback_resume = {
        key: params[key]
        for key in (
            "simkl_session_id",
            "simkl_resume_progress",
            "trakt_playback_id",
            "trakt_resume_progress",
            "nuvio_resume_percent",
            "_bobi_resume_percent",
            "_bobi_start_over",
        )
        if key in params
    }
    if ui_action:
        playback_resume['direct_playback_handoff'] = True

    variant = _normalize_search_variant(params.get("search_variant", SearchVariant.DEFAULT))
    title_language_mode = _normalize_title_language_mode(
        params.get(
            "search_title_language_mode",
            get_setting("search_title_language_mode", TITLE_LANGUAGE_LOCALIZED_FIRST),
        )
    )
    year = params.get("year")
    if year is not None:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    library_data = None
    if params.get("stremio_addon_url") and params.get("stremio_catalog_type"):
        library_data = {
            "source": "stremio_catalog",
            "addon_url": params.get("stremio_addon_url"),
            "catalog_type": params.get("stremio_catalog_type"),
            "meta_id": params.get("stremio_meta_id") or ids.get("original_id", ""),
        }

    set_content_type(mode)
    set_watched_title(query, ids, mode, media_type=media_type, library_data=library_data)

    ep_name = tv_data.get("name", "")
    episode = tv_data.get("episode", 1)
    season = tv_data.get("season", 1)

    scoped_addon_url = params.get("scoped_addon_url", "")
    if jackgram_only and scoped_addon_url:
        scoped_addon_url = ""
    preferred_stremio_streams = safe_json_loads(params.get("preferred_stremio_streams") or "[]")
    preferred_results = _preferred_stremio_results(preferred_stremio_streams)

    suppress_debrid_dialog = False
    if xbmc.getSkinDir() == 'skin.bobbi.cinema' and not direct:
        return _run_progressive_source_entry(params, query, ids, mode, media_type, tv_data,
            rescrape, scoped_addon_url, variant, title_language_mode, year, jackgram_only,
            playback_resume, preferred_results, catalog_sources=catalog_sources)
    try:
        results = search_client(
            query,
            ids,
            mode,
            media_type,
            rescrape,
            season,
            episode,
            scoped_addon_url=scoped_addon_url,
            variant=variant,
            title_language_mode=title_language_mode,
            year=year,
            jackgram_only=jackgram_only,
        )
    except SearchCancelled as exc:
        kodilog("Search cancelled from detailed status window")
        results = exc.results
        suppress_debrid_dialog = True
        if results and not rescrape:
            _cache_scope = _build_search_cache_scope(scoped_addon_url)
            if jackgram_only:
                _cache_scope = f"{_cache_scope}:jackgram"
            cache_results(
                results,
                query,
                mode,
                media_type,
                episode,
                season,
                cache_scope=_cache_scope,
            )

    if not results and not preferred_results:
        notification("No results found")
        if not skip_cancel:
            cancel_playback()
        return

    # Reuse the metadata that the source dialog already needs. Rank before
    # the configured result cap so a high-seed encode cannot evict a REMUX.
    source_metadata = None
    if xbmc.getSkinDir() == "skin.bobbi.cinema" and not direct:
        source_metadata = build_media_metadata(ids, mode) if ids else {}
        if mode in ('tv', 'movies') and (ids or {}).get('tmdb_id'):
            aliases = _cinema_catalog_aliases(ids, mode)
            source_metadata['catalog_aliases'] = aliases
            # Also screen old cached results and partial cancelled searches.
            results = _cinema_filter_catalog_candidates(results, aliases, mode, fallback_query=query)
    recommendation_context = {"mode": mode, "query": query, **source_metadata} if source_metadata is not None else None
    final_results = _prepare_stremio_results(preferred_results) + _process_search_results(
        results,
        mode,
        ep_name,
        episode,
        season,
        scoped_addon_url,
        query,
        media_type,
        rescrape,
        suppress_debrid_dialog=suppress_debrid_dialog,
        **({"recommendation_context": recommendation_context} if recommendation_context is not None else {}),
    )
    final_results = _filter_movie_year_candidates(final_results, _movie_catalog_context(ids, mode))

    if not final_results:
        notification(translation(90358))
        if not skip_cancel:
            cancel_playback()
        return

    preferred_group = params.get("preferred_group")
    force_select = params.get("force_select", False)
    autoplay_context = params.get("autoplay_context")

    # Fixed: if Auto-Play is enabled but fails (most commonly because
    # results exist but none match the preferred auto_play_quality), fall
    # back to the manual source-select screen instead of just cancelling
    # playback. The user still gets to pick a source manually rather than
    # a bare "no sources" failure when sources did in fact exist.
    autoplay_attempted = auto_play_enabled() and not force_select
    if autoplay_attempted:
        if auto_play(
            final_results,
            ids,
            tv_data,
            mode,
            preferred_group,
            autoplay_context=autoplay_context,
            playback_context=playback_resume,
        ):
            return

    if (
        not show_source_select(
            final_results,
            mode,
            ids,
            tv_data,
            query,
            media_type,
            rescrape,
            direct,
            autoplay_context=autoplay_context,
            playback_context=playback_resume,
            **({"source_metadata": source_metadata} if source_metadata is not None else {}),
            rejection_already_notified=autoplay_attempted,
        )
        and not skip_cancel
    ):
        cancel_playback()


def _perform_search(indexer_key, dialog, *args, **kwargs):
    show_dialog = kwargs.pop("show_dialog", True)
    scoped_addon_url = kwargs.pop("scoped_addon_url", "")
    addon_override = kwargs.pop("addon_override", None)

    if indexer_key == Indexer.STREMIO:
        if scoped_addon_url:
            addon = addon_override or get_addon_by_base_url(scoped_addon_url)
            stremio_addons = [addon] if addon else []
        else:
            stremio_addons = get_selected_stream_addons()[:MAX_STREMIO_ADDONS_PER_SEARCH]
        if not stremio_addons:
            notification("No Stremio addons selected")
            return []

        ids_dict = args[0]
        rest_args = args[1:]
        results = []

        for addon in stremio_addons:
            if show_dialog:
                update_dialog(addon.manifest.name, "Searching...", dialog)

            video_id = None
            original_id = ids_dict.get("original_id")
            media_kind = "series" if args[1] == "tv" or args[2] == "tv" else "movie"

            if original_id:
                prefix = original_id.split(":")[0]
                if addon.isSupported("stream", media_kind, prefix):
                    video_id = original_id

            # Try IMDb ID for addons that declare tt: prefix
            if (
                not video_id
                and ids_dict.get("imdb_id")
                and addon.isSupported("stream", media_kind, "tt")
            ):
                video_id = ids_dict.get("imdb_id")

            # Try TMDB ID for addons that declare tmdb: prefix
            if (
                not video_id
                and ids_dict.get("tmdb_id")
                and (
                    addon.isSupported("stream", media_kind, "tmdb:")
                    or addon.isSupported("stream", media_kind, "tmdb")
                )
            ):
                video_id = f"tmdb:{ids_dict['tmdb_id']}"

            if video_id:
                try:
                    client = StremioAddonClient(addon)
                    results.extend(client.search(video_id, *rest_args))
                except Exception as e:
                    kodilog(f"Error searching {addon.manifest.name}: {e}")

        return results

    client = get_client(indexer_key)
    if not client:
        return []

    if indexer_key == Indexer.BURST:
        kwargs["silent"] = True

    result = client.search(*args, **kwargs)
    if result is None and indexer_key == Indexer.JACKETT and xbmc.getSkinDir() == 'skin.bobbi.cinema':
        # Discovery/parser failures retain Jackett's legacy None public return,
        # but cannot become a successful empty provider in this orchestration.
        from bobbi_core.search_completion import SearchCompletion, SearchResults
        return SearchResults([], SearchCompletion(1, failed=1))
    return result


def _submit_search_tasks(
    executor,
    tasks,
    dialog,
    query,
    mode,
    media_type,
    season,
    episode,
    ids,
    scoped_addon_url,
    tmdb_id,
    imdb_id,
    show_dialog,
    variant: str = SearchVariant.DEFAULT,
    title_language_mode: str = TITLE_LANGUAGE_LOCALIZED_FIRST,
    year: Optional[int] = None,
    title_aliases: Optional[List[str]] = None,
    jackgram_only: bool = False,
):
    def submit_performer(*args, **kwargs):
        if "show_dialog" not in kwargs:
            kwargs["show_dialog"] = show_dialog
        if "scoped_addon_url" not in kwargs:
            kwargs["scoped_addon_url"] = scoped_addon_url
        if "variant" not in kwargs:
            kwargs["variant"] = variant
        if "title_language_mode" not in kwargs:
            kwargs["title_language_mode"] = title_language_mode
        if "year" not in kwargs:
            kwargs["year"] = year
        return executor.submit(
            _perform_search,
            *args,
            **kwargs,
        )

    if jackgram_only:
        if _is_source_enabled(Indexer.JACKGRAM):
            add_task_if_enabled(
                executor,
                tasks,
                "jackgram_enabled",
                Indexer.JACKGRAM,
                _perform_search,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
            )
        return

    if scoped_addon_url:
        addon = get_addon_by_base_url(scoped_addon_url)
        if (
            addon
            and (ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id"))
            and _is_source_enabled(Indexer.STREMIO, addon.key())
        ):
            tasks.append(
                submit_performer(Indexer.STREMIO, dialog, ids, mode, media_type, season, episode)
            )
    else:
        if _is_source_enabled(Indexer.EASYNEWS):
            add_task_if_enabled(
                executor,
                tasks,
                "easynews_enabled",
                Indexer.EASYNEWS,
                _perform_search_with_title_fallback,
                dialog,
                query,
                ids,
                mode,
                media_type,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
            )
        if _is_source_enabled(Indexer.BURST):
            add_task_if_enabled(
                executor,
                tasks,
                "jacktookburst_enabled",
                Indexer.BURST,
                _perform_search,
                dialog,
                imdb_id or "",
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
            )
        if get_setting("prowlarr_enabled") and _is_source_enabled(Indexer.PROWLARR):
            indexers_ids = get_setting("prowlarr_indexer_ids")
            tasks.append(
                executor.submit(
                    _perform_search_with_title_fallback,
                    Indexer.PROWLARR,
                    dialog,
                    query,
                    ids,
                    mode,
                    season,
                    episode,
                    indexers_ids,
                    show_dialog=show_dialog,
                    scoped_addon_url=scoped_addon_url,
                    variant=variant,
                    title_language_mode=title_language_mode,
                    year=year,
                )
            )
        if _is_source_enabled(Indexer.JACKETT):
            add_task_if_enabled(
                executor,
                tasks,
                "jackett_enabled",
                Indexer.JACKETT,
                _perform_search_with_title_fallback,
                dialog,
                query,
                ids,
                mode,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
            )
        if _is_source_enabled(Indexer.JACKGRAM):
            add_task_if_enabled(
                executor,
                tasks,
                "jackgram_enabled",
                Indexer.JACKGRAM,
                _perform_search,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
            )
        if _is_source_enabled(Indexer.EXTERNAL_SCRAPER):
            add_task_if_enabled(
                executor,
                tasks,
                "external_scraper_enabled",
                Indexer.EXTERNAL_SCRAPER,
                _perform_search,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=show_dialog,
                scoped_addon_url=scoped_addon_url,
                imdb_id=imdb_id or "",
                tvdb_id=(ids or {}).get("tvdb_id", ""),
                year=str(year) if year else "",
                aliases=title_aliases,
            )
        if get_setting("stremio_enabled") and (
            ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id")
        ):
            for addon in get_selected_stream_addons()[:MAX_STREMIO_ADDONS_PER_SEARCH]:
                if _is_source_enabled(Indexer.STREMIO, addon.key()):
                    tasks.append(
                        submit_performer(
                            Indexer.STREMIO,
                            dialog,
                            ids,
                            mode,
                            media_type,
                            season,
                            episode,
                            scoped_addon_url=addon.url(),
                        )
                    )
        if _is_enabled("nuvio_enabled") and (
            ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id")
        ):
            for addon in _get_selected_nuvio_stream_addons_safe()[:MAX_STREMIO_ADDONS_PER_SEARCH]:
                if _is_source_enabled(Indexer.STREMIO, addon.key(), addon_origin="Nuvio"):
                    tasks.append(
                        submit_performer(
                            Indexer.STREMIO,
                            dialog,
                            ids,
                            mode,
                            media_type,
                            season,
                            episode,
                            scoped_addon_url=addon.url(),
                            addon_override=addon,
                        )
                    )


def _collect_search_results(tasks, listener, show_dialog) -> List[TorrentStream]:
    results_by_future = {}
    total_tasks = len(tasks)
    completed_tasks = 0

    for future in as_completed(tasks):
        try:
            completed_tasks += 1
            if show_dialog and total_tasks > 0:
                percent = int(completed_tasks / total_tasks * 100)
                update_dialog("Searching", f"Searching... {percent}%", listener.dialog, percent)

            results = future.result()
            kodilog(
                f"Search task completed with {len(results) if results else 0} result(s)",
                level=xbmc.LOGDEBUG,
            )
            results_by_future[future] = results or []
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            kodilog(f"Error resolving future result in thread pool: {e}\n{error_details}")

    total_results = []
    for future in tasks:
        total_results.extend(results_by_future.get(future, []))
    return total_results


def _submit_search_tasks_managed(
    manager,
    dialog,
    query,
    mode,
    media_type,
    season,
    episode,
    ids,
    scoped_addon_url,
    tmdb_id,
    imdb_id,
    variant: str = SearchVariant.DEFAULT,
    title_language_mode: str = TITLE_LANGUAGE_LOCALIZED_FIRST,
    year: Optional[int] = None,
    title_aliases: Optional[List[str]] = None,
    jackgram_only: bool = False,
):
    def submit_performer_managed(name, indexer_key, *args, **kwargs):
        kwargs["show_dialog"] = False
        if "scoped_addon_url" not in kwargs:
            kwargs["scoped_addon_url"] = scoped_addon_url
        if "variant" not in kwargs:
            kwargs["variant"] = variant
        if "title_language_mode" not in kwargs:
            kwargs["title_language_mode"] = title_language_mode
        if "year" not in kwargs:
            kwargs["year"] = year
        return manager.submit_task(
            name,
            indexer_key,
            _perform_search,
            indexer_key,
            *args,
            **kwargs,
        )

    if jackgram_only:
        if _is_source_enabled(Indexer.JACKGRAM):
            add_task_if_enabled_managed(
                manager,
                "jackgram_enabled",
                Indexer.JACKGRAM,
                _perform_search,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
            )
        return

    if scoped_addon_url:
        addon = get_addon_by_base_url(scoped_addon_url)
        if (
            addon
            and (ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id"))
            and _is_source_enabled(Indexer.STREMIO, addon.key())
        ):
            submit_performer_managed(
                get_addon_display_name(addon),
                Indexer.STREMIO,
                dialog,
                ids,
                mode,
                media_type,
                season,
                episode,
                scoped_addon_url=scoped_addon_url,
            )
    else:
        if _is_source_enabled(Indexer.EASYNEWS):
            add_task_if_enabled_managed(
                manager,
                "easynews_enabled",
                Indexer.EASYNEWS,
                _perform_search_with_title_fallback,
                dialog,
                query,
                ids,
                mode,
                media_type,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
            )
        if _is_source_enabled(Indexer.BURST):
            add_task_if_enabled_managed(
                manager,
                "jacktookburst_enabled",
                Indexer.BURST,
                _perform_search,
                dialog,
                imdb_id or "",
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
            )
        if get_setting("prowlarr_enabled") and _is_source_enabled(Indexer.PROWLARR):
            indexers_ids = get_setting("prowlarr_indexer_ids")
            manager.submit_task(
                "Prowlarr",
                Indexer.PROWLARR,
                _perform_search_with_title_fallback,
                Indexer.PROWLARR,
                dialog,
                query,
                ids,
                mode,
                season,
                episode,
                indexers_ids,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
            )
        if _is_source_enabled(Indexer.JACKETT):
            add_task_if_enabled_managed(
                manager,
                "jackett_enabled",
                Indexer.JACKETT,
                _perform_search_with_title_fallback,
                dialog,
                query,
                ids,
                mode,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
                cancelled=getattr(getattr(manager, 'cancelled', None), 'is_set', None),
                deadline=getattr(manager, 'deadline', None),
                **({'_progressive': True} if hasattr(manager, 'session') else {}),
            )
        if _is_source_enabled(Indexer.JACKGRAM):
            add_task_if_enabled_managed(
                manager,
                "jackgram_enabled",
                Indexer.JACKGRAM,
                _perform_search,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
            )
        if _is_source_enabled(Indexer.EXTERNAL_SCRAPER):
            module_display_name = get_setting("external_scraper_module_name") or "External Scraper"
            manager.submit_task(
                module_display_name,
                Indexer.EXTERNAL_SCRAPER,
                _perform_search,
                Indexer.EXTERNAL_SCRAPER,
                dialog,
                tmdb_id,
                query,
                mode,
                media_type,
                season,
                episode,
                show_dialog=False,
                scoped_addon_url=scoped_addon_url,
                imdb_id=imdb_id or "",
                tvdb_id=(ids or {}).get("tvdb_id", ""),
                year=str(year) if year else "",
                aliases=title_aliases,
            )
        if get_setting("stremio_enabled") and (
            ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id")
        ):
            stremio_addons = get_selected_stream_addons()[:MAX_STREMIO_ADDONS_PER_SEARCH]
            filtered_addons = [
                addon
                for addon in stremio_addons
                if _is_source_enabled(Indexer.STREMIO, addon.key())
            ]
            for addon in filtered_addons:
                submit_performer_managed(
                    get_addon_display_name(addon),
                    Indexer.STREMIO,
                    dialog,
                    ids,
                    mode,
                    media_type,
                    season,
                    episode,
                    scoped_addon_url=addon.url(),
                )
        if _is_enabled("nuvio_enabled") and (
            ids.get("imdb_id") or ids.get("original_id") or ids.get("tmdb_id")
        ):
            nuvio_addons = _get_selected_nuvio_stream_addons_safe()[:MAX_STREMIO_ADDONS_PER_SEARCH]
            for addon in nuvio_addons:
                if _is_source_enabled(Indexer.STREMIO, addon.key(), addon_origin="Nuvio"):
                    submit_performer_managed(
                        f"Nuvio: {addon.manifest.name or addon.manifest.id}",
                        Indexer.STREMIO,
                        dialog,
                        ids,
                        mode,
                        media_type,
                        season,
                        episode,
                        scoped_addon_url=addon.url(),
                        addon_override=addon,
                    )


def _check_search_caches(
    query: str,
    ids: dict,
    mode: str,
    media_type: str,
    episode: int,
    season: int,
    cache_scope: str,
    allow_autoscrape_fallback: bool = True,
) -> Optional[List[TorrentStream]]:
    """Check the scoped cache and, optionally, the autoscrape fallback cache.

    Returns cached results if found (even an empty list), or None if
    no cache entry exists (caller should perform a fresh search).
    """
    cached = get_cached_results(
        query,
        mode,
        media_type,
        episode,
        season,
        cache_scope=cache_scope,
    )
    if cached is not None:
        return cached

    # Fallback: autoscrape cache (PlayNext background scrape) under
    # ``as_results:{id}_{season}_{episode}``.
    if not allow_autoscrape_fallback or (mode != "tv" and media_type != "tv"):
        return None
    id_value = (
        (ids or {}).get("original_id") or (ids or {}).get("imdb_id") or (ids or {}).get("tmdb_id")
    )
    if id_value is None or season is None or episode is None:
        return None

    from lib.db.cached import cache as _cache
    from lib.utils.player.utils import get_autoscrape_results_cache_key

    as_key = get_autoscrape_results_cache_key(id_value, season, episode)
    as_results = _cache.get(as_key)
    if as_results is None:
        return None

    kodilog(f"[CACHE] Autoscrape cache HIT for {as_key}, reusing {len(as_results)} results")
    cache_results(
        as_results,
        query,
        mode,
        media_type,
        episode,
        season,
        cache_scope=cache_scope,
    )
    return as_results


def _run_detailed_search(
    query: str,
    ids: dict,
    mode: str,
    media_type: str,
    season: int,
    episode: int,
    scoped_addon_url: str,
    tmdb_id: Optional[int],
    imdb_id: Optional[str],
    variant: str,
    title_language_mode: str,
    year: Optional[int],
    title_aliases: List[str],
    jackgram_only: bool = False,
) -> List[TorrentStream]:
    """Run an interactive search with immediate full-screen progress feedback."""
    if jackgram_only:
        scoped_addon_url = ""
    executor = ThreadPoolExecutor(max_workers=_search_worker_count())
    manager = SearchTaskManager(executor)
    try:
        _submit_search_tasks_managed(
            manager,
            None,
            query,
            mode,
            media_type,
            season,
            episode,
            ids,
            scoped_addon_url,
            tmdb_id,
            imdb_id,
            variant=variant,
            title_language_mode=title_language_mode,
            year=year,
            title_aliases=title_aliases,
            jackgram_only=jackgram_only,
        )

        item_info = {"ids": ids, "mode": mode}
        if ids:
            item_info.update(build_media_metadata(ids, mode))

        window = SearchStatusWindow(
            "search_status.xml",
            ADDON_PATH,
            task_manager=manager,
            item_information=item_info,
        )
        try:
            window.show()
            window.run_until_complete()
        finally:
            del window

        if manager.is_cancelled:
            manager.cancel_pending()
            raise SearchCancelled(manager.collect_results())

        return manager.collect_results()
    except Exception:
        manager.cancel_pending()
        raise
    finally:
        executor.shutdown(wait=False)


def _run_simple_search(
    query: str,
    ids: dict,
    mode: str,
    media_type: str,
    season: int,
    episode: int,
    scoped_addon_url: str,
    tmdb_id: Optional[int],
    imdb_id: Optional[str],
    show_dialog: bool,
    variant: str,
    title_language_mode: str,
    year: Optional[int],
    title_aliases: List[str],
    jackgram_only: bool = False,
) -> List[TorrentStream]:
    """Run a silent/background search or the emergency progress fallback."""
    if jackgram_only:
        scoped_addon_url = ""
    tasks: List[Future] = []
    with DialogListener() as listener:
        if show_dialog:
            listener.dialog.create("")

        with ThreadPoolExecutor(max_workers=_search_worker_count()) as executor:
            _submit_search_tasks(
                executor,
                tasks,
                listener.dialog,
                query,
                mode,
                media_type,
                season,
                episode,
                ids,
                scoped_addon_url,
                tmdb_id,
                imdb_id,
                show_dialog,
                variant=variant,
                title_language_mode=title_language_mode,
                year=year,
                title_aliases=title_aliases,
                jackgram_only=jackgram_only,
            )
            total_results = _collect_search_results(tasks, listener, show_dialog)

    return total_results


def search_client(
    query: str,
    ids: dict,
    mode: str,
    media_type: str,
    rescrape: bool,
    season: int,
    episode: int,
    show_dialog: bool = True,
    scoped_addon_url: str = "",
    variant: str = SearchVariant.DEFAULT,
    title_language_mode: str = TITLE_LANGUAGE_LOCALIZED_FIRST,
    year: Optional[int] = None,
    jackgram_only: bool = False,
) -> List[TorrentStream]:
    close_busy_dialog()
    reconcile_source_selection(
        cache_backend=cache,
        settings_getter=get_setting,
        stremio_addons_getter=get_selected_stream_addons,
        nuvio_addons_getter=get_selected_stream_addon_records,
    )
    if year is None:
        year = _infer_tmdb_year(ids, mode)

    title_aliases = _build_title_fallback_queries(
        query,
        ids,
        mode,
        SearchVariant.DEFAULT,
        year,
        title_language_mode=title_language_mode,
    )
    if jackgram_only and scoped_addon_url:
        scoped_addon_url = ""
    cache_scope = _build_search_cache_scope(scoped_addon_url)
    if jackgram_only:
        cache_scope = f"{cache_scope}:jackgram"

    if not rescrape:
        cached = _check_search_caches(
            query,
            ids,
            mode,
            media_type,
            episode,
            season,
            cache_scope,
            allow_autoscrape_fallback=not jackgram_only,
        )
        if cached is not None:
            if jackgram_only:
                return _filter_isolated_jackgram_cache_results(query, cached)
            return cached

    tmdb_id, imdb_id = (ids.get("tmdb_id"), ids.get("imdb_id")) if ids else (None, None)

    if show_dialog:
        try:
            total_results = _run_detailed_search(
                query,
                ids,
                mode,
                media_type,
                season,
                episode,
                scoped_addon_url,
                tmdb_id,
                imdb_id,
                variant,
                title_language_mode,
                year,
                title_aliases,
                jackgram_only=jackgram_only,
            )
        except SearchCancelled:
            raise
        except Exception as e:
            kodilog(f"Detailed search status failed, falling back to simple search: {e}")
            total_results = _run_simple_search(
                query,
                ids,
                mode,
                media_type,
                season,
                episode,
                scoped_addon_url,
                tmdb_id,
                imdb_id,
                True,
                variant,
                title_language_mode,
                year,
                title_aliases,
                jackgram_only=jackgram_only,
            )
    else:
        total_results = _run_simple_search(
            query,
            ids,
            mode,
            media_type,
            season,
            episode,
            scoped_addon_url,
            tmdb_id,
            imdb_id,
            show_dialog,
            variant,
            title_language_mode,
            year,
            title_aliases,
            jackgram_only=jackgram_only,
        )

    cache_results(
        total_results,
        query,
        mode,
        media_type,
        episode,
        season,
        cache_scope=cache_scope,
    )
    return total_results


def pre_process_results(
    results: List[TorrentStream],
    mode: str,
    ep_name: str,
    episode: int,
    season: int,
    skip_episode_filter: bool = False,
    anime_aliases=None,
    anime_range_context=None,
) -> List[TorrentStream]:
    return pre_process(results, mode, ep_name, episode, season, skip_episode_filter,
                       anime_aliases=anime_aliases, anime_range_context=anime_range_context)


def process_results(
    pre_results: List[TorrentStream],
    query: str,
    mode: str,
    media_type: str,
    rescrape: bool,
    episode: int,
    suppress_dialog: bool = False,
    suppress_busy_dialog: bool = False,
    recommendation_context=None,
) -> List[TorrentStream]:
    torrent_results = []
    if get_setting("torrent_enable"):
        torrent_results = post_process(pre_results, recommendation_context=recommendation_context) if recommendation_context is not None else post_process(pre_results)
    if not suppress_busy_dialog:
        close_busy_dialog()
    if suppress_dialog:
        debrid_results = check_debrid_cached(
            query, pre_results, mode, media_type, SilentProgressDialog(), rescrape, episode
        )
    else:
        with DialogListener() as listener:
            debrid_results = check_debrid_cached(
                query, pre_results, mode, media_type, listener.dialog, rescrape, episode
            )
    return debrid_results + torrent_results


def _run_progressive_source_entry(params, query, ids, mode, media_type, tv_data,
        rescrape, scoped_addon_url, variant, title_language_mode, year, jackgram_only,
        playback_context, preferred, catalog_sources=None):
    from lib.cinema.source_list_session import SourceListSession
    from lib.cinema.progressive_search import ProgressiveSearch
    from lib.utils.general.cinema_source_rank import rank_sources
    from lib.clients.bobi_library import load_index, find_sources
    from bobbi_core.provider_cache import ProviderResultCache
    from lib.clients.catalog_providers import provider_for, submit_catalogs
    from lib.utils.kodi.settings import get_cache_expiration, is_cache_enabled
    season, episode = tv_data.get('season', 1), tv_data.get('episode', 1)
    context = dict(mode=mode, query=query, media_type=media_type, ids=ids, tv_data=tv_data)
    # Cache-only identity is ready before any preferred/local BT card can show.
    # The worker may refresh it after the existing catalog detail lookup.
    movie_catalog = [_movie_catalog_context(ids, mode)]
    if mode == 'tv':
        from lib.clients.tmdb.episode_order import release_pair
        order = release_pair(ids, tv_data)
        if order:
            context['release_order'] = order
    tv_completed = [_tv_completed_context(ids, mode, tv_data, context.get('release_order'))]
    limit = max(1, min(100, int(get_setting('indexers_total_results', 10))))
    session = SourceListSession(dict(ids=ids, mode=mode, season=season, episode=episode,
        query=query, policy='b-full-unified-v6-movie-years', order_digest=(context.get('release_order') or {}).get('order_digest', ''), scope=scoped_addon_url, variant=variant,
        language=title_language_mode, jackgram_only=bool(jackgram_only)),
        lambda rows: rank_sources(_filter_tv_completed_candidates(
            _filter_movie_year_candidates(rows, movie_catalog[0]), tv_completed[0], ids, tv_data), context), limit)
    if catalog_sources:
        session.publish(session.epoch, 'local-entry', catalog_sources)
    if preferred:
        session.publish(session.epoch, 'preferred', _prepare_stremio_results(preferred))
    if not scoped_addon_url and not jackgram_only:
        # An optional exact-ID catalogue in the same ranked pool as all others.
        from lib.clients.mdsub_provider import find_sources as mdsub_sources
        session.publish(session.epoch, '漫迪 MDsub',
                        mdsub_sources(ids, mode, season, episode))
    if not scoped_addon_url and not jackgram_only:
        try:
            clouds = find_sources(load_index(), ids.get('tmdb_id'), mode, season, episode)
            session.publish(session.epoch, '115-local-index', clouds)
        except (ValueError, OSError, KeyError, TypeError) as error:
            session.publish(session.epoch, '115-local-index', state='FAILED', error=type(error).__name__)

    def transform(rows):
        # Exact-file catalogue rows have already passed their independent
        # identity gate. Keep stable locators out of the legacy search cache.
        catalog_rows, ordinary = [], []
        for row in rows:
            (catalog_rows if provider_for(row) else ordinary).append(row)
        rows = ordinary
        if not rows:
            return catalog_rows
        if mode in ('tv', 'movies'):
            target = context.get('release_order') or tv_data
            rows = _cinema_filter_catalog_candidates(rows, context.get('catalog_aliases', []), mode,
                release_season=_cinema_release_season(target.get('season', season)) if mode == 'tv' else None,
                release_episode=int(target.get('episode', 0)) or None if mode == 'tv' else None,
                fallback_query=query, anime=16 in (context.get('genre_ids') or []),
                anime_range_context=context.get('anime_range_context'))
        return catalog_rows + _prepare_stremio_results(_process_search_results(rows, mode, tv_data.get('name', ''),
            episode, season, scoped_addon_url, query, media_type, rescrape,
            suppress_debrid_dialog=True, suppress_busy_dialog=True, recommendation_context=context))

    def setup(manager):
        reconcile_source_selection(cache_backend=cache, settings_getter=get_setting,
                                   stremio_addons_getter=get_selected_stream_addons)
        scope = _build_search_cache_scope(scoped_addon_url) + ':provider-v1:' + hashlib.sha256(session.media.encode()).hexdigest()
        # The progressive path no longer reads/writes an aggregate full-search
        # cache. Healthy providers survive sibling failure and only missing or
        # expired scopes repeat IO. Exact-file catalogs own their locator cache.
        manager.result_cache = ProviderResultCache(cache, scope,
            hours=get_cache_expiration() if is_cache_enabled() else 0,
            refresh=rescrape, cacheable=lambda key: key in (Indexer.JACKETT, 'animegarden'))
        if ids:
            context.update(build_media_metadata(ids, mode))
        if mode in ('tv', 'movies') and ids.get('tmdb_id'):
            context['catalog_aliases'] = _cinema_catalog_aliases(ids, mode)
        if mode == 'tv' and 16 in (context.get('genre_ids') or []):
            target = context.get('release_order') or tv_data
            context['anime_range_context'] = _cinema_anime_range_context(ids, mode, _cinema_release_season(season),
                _cinema_release_season(target.get('season', season)), int(target.get('episode', episode)))
        movie_catalog[0] = _movie_catalog_context(ids, mode)
        tv_completed[0] = _tv_completed_context(ids, mode, tv_data, context.get('release_order'))
        session.set_metadata({key: value for key, value in context.items()
                              if key not in ('mode', 'query', 'media_type')})
        inferred_year = year if year is not None else _infer_tmdb_year(ids, mode)
        movie_years = None
        if mode == 'movies':
            from lib.clients.tmdb.movie_years import cached_movie_years
            movie_years = cached_movie_years(ids.get('tmdb_id'))
            if movie_years is not None:
                inferred_year = movie_years.primary_year
        aliases = _build_title_fallback_queries(query, ids, mode, SearchVariant.DEFAULT,
            inferred_year, title_language_mode=title_language_mode)
        if manager.cancelled.is_set():
            return
        if not scoped_addon_url and not jackgram_only and ids.get('tmdb_id'):
            submit_catalogs(manager,
                ids, mode, season, episode, inferred_year, context.get('catalog_aliases', []),
                context.get('release_order'),
                movie_years=movie_years)
        _submit_search_tasks_managed(manager, None, query, mode, media_type, season, episode,
            ids, scoped_addon_url, ids.get('tmdb_id'), ids.get('imdb_id'), variant=variant,
            title_language_mode=title_language_mode, year=inferred_year,
            title_aliases=aliases, jackgram_only=jackgram_only)
        if (not scoped_addon_url and not jackgram_only and mode == 'tv'
                and 16 in (context.get('genre_ids') or [])):
            # Raw releases supplement the existing providers. ANI-RSS preview
            # collapses same-episode versions and is not a source-selection API.
            # No BGM subject ID is promoted to trusted TMDb catalogue identity.
            from lib.clients.animegarden_provider import find_sources as animegarden_sources
            manager.submit_task('AnimeGarden RSS', 'animegarden', animegarden_sources,
                ids, mode, _cinema_anime_queries(ids, mode), manager.deadline, manager.cancelled)

    pump = ProgressiveSearch(session, setup, transform, workers=min(4, _search_worker_count()))
    pump.start()
    try:
        initial = [source for _, source in session.snapshot()['entries']]
        return show_source_select(initial, mode, ids, tv_data, query, media_type,
            rescrape, playback_context=playback_context, source_metadata={},
            source_session=session, source_pump=pump,
            auto_select_sources=str(params.get('force_select', False)).lower() not in ('true', '1'))
    finally:
        pump.cancel()


def show_source_select(
    results: List[TorrentStream],
    mode: str,
    ids: dict,
    tv_data: dict,
    query: str,
    media_type: str,
    rescrape: bool,
    direct: bool = False,
    autoplay_context: Optional[str] = None,
    playback_context: Optional[dict] = None,
    source_metadata: Optional[dict] = None,
    source_session=None,
    source_pump=None,
    rejection_already_notified: bool = False,
    auto_select_sources: bool = False,
) -> bool:
    rejection_reasons = []
    results = _prepare_stremio_results(
        results,
        notify_rejections=False,
        rejection_reasons=rejection_reasons,
    )
    if not results and source_session is None:
        if rejection_reasons and not rejection_already_notified:
            notification(rejection_reasons[0])
        return False

    item_info = {
        "tv_data": tv_data,
        "ids": ids,
        "mode": mode,
        "query": query,
        "media_type": media_type,
        "rescrape": rescrape,
        "auto_select_sources": auto_select_sources,
    }
    from lib.clients.cinema_ui import is_ui_action
    if is_ui_action():
        item_info['direct_playback_handoff'] = True
    if autoplay_context:
        item_info["playnext_context"] = True
        item_info["direct_play"] = True
    if playback_context:
        item_info.update(playback_context)

    if not direct and ids:
        item_info.update(source_metadata if source_metadata is not None else build_media_metadata(ids, mode))

    tv_data = tv_data if isinstance(tv_data, dict) else {}
    episode_title_zh = unquote(str(tv_data.get("display_name_zh") or ""))
    episode_title_en = unquote(str(tv_data.get("display_name_en") or tv_data.get("name") or ""))
    episode_display = unquote(str(tv_data.get("display_name") or ""))
    season_number = tv_data.get("season")
    episode_number = tv_data.get("episode")
    if mode == 'tv':
        from lib.clients.tmdb.episode_order import release_pair
        display_order = release_pair(ids, tv_data)
        if display_order:
            season_number, episode_number = display_order['season'], display_order['episode']
    item_info["episode_title_zh"] = episode_title_zh
    item_info['display_season'] = season_number
    item_info['display_episode'] = episode_number
    item_info["episode_title_en"] = episode_title_en
    item_info["episode_display_title"] = episode_display
    from lib.clients.tmdb.frontend_metadata import source_window
    # Preserve original_title for existing search/playback consumers; the
    # source window projects its English subtitle independently.
    item_info.update({key: value for key, value in source_window(item_info).items() if key != 'original_title'})

    xml_file_string = "source_select_direct.xml" if mode == "direct" else "source_select.xml"

    options = dict(source_session=source_session, source_pump=source_pump) if source_session is not None else {}
    return source_select(item_info, xml_file=xml_file_string, sources=results, **options)


def _autoplay_description(source: TorrentStream, ids: dict, mode: str) -> str:
    if not (get_setting("torrent_enable") and get_setting("torrent_client") == Players.JACKTORR):
        return ""

    if _is_stremio_source(source):
        payload = payload_from_torrent(source)
        decision = classify(
            candidate_from_payload(payload), current_stremio_playback_capabilities()
        )
        if decision.source_class != "torrent_hash" or is_supported_debrid_type(
            payload.get("debrid_type", "")
        ):
            return ""
    elif source.type in (
        IndexerType.DIRECT,
        IndexerType.STREMIO_DEBRID,
    ) or is_supported_debrid_type(source.debridType):
        return ""

    return build_media_metadata(ids or {}, mode).get("overview") or ""


def auto_play(
    results: List[TorrentStream],
    ids,
    tv_data,
    mode,
    preferred_group=None,
    force_select=False,
    autoplay_context: Optional[str] = None,
    playback_context: Optional[dict] = None,
) -> bool:
    if force_select:
        return False

    filtered_results = clean_auto_play_undesired(_prepare_stremio_results(results))
    if not filtered_results:
        notification("No suitable source found for auto play.")
        return False

    preferred_quality = str(get_setting("auto_play_quality"))
    quality_matches = [
        r for r in filtered_results if preferred_quality.lower() in r.quality.lower()
    ]

    if not quality_matches:
        notification("No sources found with the preferred quality.")
        return False

    selected_result = quality_matches[0]
    if preferred_group:
        group_matches = [r for r in quality_matches if preferred_group.lower() in r.title.lower()]
        if group_matches:
            selected_result = group_matches[0]

    description = _autoplay_description(selected_result, ids, mode)
    if _is_stremio_source(selected_result):
        try:
            playback_info = _resolve_stremio_source(
                selected_result,
                {
                    "description": description,
                    "mode": mode,
                    "ids": ids,
                    "tv_data": tv_data,
                    "is_torrent": False,
                },
            )
        except StremioPlaybackError as error:
            kodilog(
                f"stremio_playback_error phase=auto_play code={error.code}",
                xbmc.LOGWARNING,
            )
            notification(error.user_message)
            return False
    else:
        playback_info = resolve_playback_url(
            data={
                "title": selected_result.title,
                "description": description,
                "mode": mode,
                "indexer": selected_result.indexer,
                "type": selected_result.type,
                "debrid_type": selected_result.debridType,
                "ids": ids,
                "info_hash": selected_result.infoHash,
                "url": selected_result.url,
                "tv_data": tv_data,
                "is_torrent": False,
            },
        )

    if not playback_info:
        return False

    playback_info["autoplay"] = True
    if autoplay_context:
        playback_info["playnext_context"] = True
        playback_info["direct_play"] = True
    if playback_context:
        playback_info.update(playback_context)

    player = JacktookPLayer()
    player.run(data=playback_info)
    del player
    return True


def stremio_addon_generator(stremio_addons, dialog, show_dialog):
    for addon in stremio_addons:
        if show_dialog:
            update_dialog(addon.manifest.name, "Searching...", dialog)
        yield StremioAddonClient(addon)


def add_task_if_enabled(
    executor, tasks, setting_key, indexer_key, perform_search, dialog, *args, **kwargs
):
    """Add a search task to the task list if the corresponding setting is enabled."""
    if get_setting(setting_key):
        tasks.append(executor.submit(perform_search, indexer_key, dialog, *args, **kwargs))


def add_task_if_enabled_managed(
    manager, setting_key, indexer_key, perform_search, dialog, *args, **kwargs
):
    """Add a managed search task if the corresponding setting is enabled."""
    if get_setting(setting_key):
        name = str(indexer_key).title()
        manager.submit_task(name, indexer_key, perform_search, indexer_key, dialog, *args, **kwargs)
