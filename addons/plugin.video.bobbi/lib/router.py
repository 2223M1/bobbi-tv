"""Addon router — single-source RouteSpec table driving fast paths, matchers, and lazy dispatch.

Every action literal is declared once in ROUTE_SPECS with its explicit Kodi completion
contract ('directory', 'run_plugin', 'script_or_dialog', 'end_directory_finally',
'end_directory_failed_if_handle'), catalog-preparation policy, and lazy module target.
Legacy saved URLs and bobi_* -> bobbi_* aliases remain supported.
"""

from dataclasses import dataclass
from importlib import import_module
import sys
from urllib import parse


VALID_COMPLETIONS = frozenset(
    {
        "directory",
        "run_plugin",
        "script_or_dialog",
        "end_directory_finally",
        "end_directory_failed_if_handle",
    }
)


@dataclass(frozen=True)
class RouteSpec:
    group: str
    actions: tuple
    module: str = ""
    attr_map: dict = None
    completion: str = "directory"
    bypass_prepare_catalog: bool = False
    ensure_tmdb: bool = True
    pass_params: bool = True
    prefixes: tuple = ()
    custom: object = None


def _spec(
    group,
    targets,
    module="",
    *,
    completion="directory",
    bypass_prepare_catalog=False,
    ensure_tmdb=True,
    pass_params=True,
    prefixes=(),
    custom=None,
):
    if completion not in VALID_COMPLETIONS:
        raise ValueError(f"Unsupported route completion: {completion}")
    if isinstance(targets, dict):
        actions = tuple(targets.keys())
        attr_map = dict(targets)
    else:
        actions = tuple(targets)
        attr_map = {name: name for name in actions} if module else {}
    return RouteSpec(
        group=group,
        actions=actions,
        module=module,
        attr_map=attr_map,
        completion=completion,
        bypass_prepare_catalog=bypass_prepare_catalog,
        ensure_tmdb=ensure_tmdb,
        pass_params=pass_params,
        prefixes=tuple(prefixes),
        custom=custom,
    )


def _custom_osd_streams(_action, params):
    from lib.services.osd_playback import stream_directory

    return stream_directory(int(sys.argv[1]), params.get("stream_type"), params.get("panel"))


def _custom_osd_apply(_action, params):
    from lib.services.osd_playback import run

    return run("apply", token=params.get("token"))


def _custom_emby_rail(_action, params):
    from bobbi_platform.emby_dynamic import execute_home_rail

    return execute_home_rail(int(sys.argv[1]), params)


def _custom_retry_rail(_action, params):
    from lib.cinema.focus_anchor import bump
    import xbmcgui

    return bump(xbmcgui.Window(10000), params.get("rail", ""))


def _route_am6b_warmup():
    """Pre-import the lightweight catalog graph without opening a Kodi window."""
    from lib.clients.tmdb import anime_fast_catalog  # noqa: F401


def _custom_am6b_warm(_action, _params):
    return _route_am6b_warmup()


def _is_am6b_anime_catalog_action(action, params):
    locked_categories = {"Anime_Current_Quarter", "Anime_Movies_New"}
    if action == "next_page_anime":
        return params.get("mode") == "anime" and params.get("category") in locked_categories
    return (
        action == "search_item"
        and params.get("api") == "tmdb"
        and params.get("mode") == "anime"
        and params.get("category") in locked_categories
    )


def _route_am6b_anime_catalog(action, params):
    """Route the locked anime catalogs without importing all navigation clients."""
    from lib.clients.tmdb.anime_fast_catalog import handle_am6b_anime_catalog

    return handle_am6b_anime_catalog(params, next_page=action == "next_page_anime")


def _custom_tmdb_year_or_genres(action, params):
    from lib.clients.tmdb.tmdb import TmdbClient
    from lib.utils.general.utils import set_content_type

    mode = params["mode"]
    set_content_type(mode)
    if action == "search_tmdb_year":
        return TmdbClient.tmdb_search_year(
            mode, params["submode"], int(params["year"]), int(params["page"])
        )
    return TmdbClient.tmdb_search_genres(
        mode,
        params["genre_id"],
        int(params["page"]),
        submode=params.get("submode"),
    )


def _custom_extras(_action, params):
    from lib.gui.extras_window import ExtrasWindow
    from lib.jacktook.utils import ADDON_PATH

    item_information = {
        "tmdb_id": params.get("id"),
        "imdb_id": params.get("imdb_id"),
        "media_type": params.get("media_type"),
        "title": params.get("title"),
        "plot": params.get("plot", ""),
        "genre": params.get("genre", ""),
        "rating": params.get("rating", ""),
        "tv_data": params.get("tv_data", "{}"),
    }
    window = ExtrasWindow("extras.xml", ADDON_PATH, item_information=item_information)
    window.doModal()
    del window


def _resolve_callable(module_name, attr_path):
    target = import_module(module_name)
    for part in attr_path.split("."):
        target = getattr(target, part)
    return target


def _invoke_spec(spec, action, params):
    def _call():
        if spec.custom is not None:
            return spec.custom(action, params)
        attr_path = spec.attr_map.get(action)
        if not attr_path:
            return None
        fn = _resolve_callable(spec.module, attr_path)
        return fn(params) if spec.pass_params else fn()

    if spec.completion == "end_directory_finally":
        import xbmcplugin

        try:
            return _call()
        finally:
            xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=False)
    if spec.completion == "end_directory_failed_if_handle":
        try:
            return _call()
        finally:
            if int(sys.argv[1]) >= 0:
                import xbmcplugin

                xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False, cacheToDisc=False)
    return _call()


# ---------------------------------------------------------------------------
# Single-source RouteSpec registry (every action declared exactly once)
# ---------------------------------------------------------------------------

ROUTE_SPECS = (
    # OSD popup bypass routes (never trigger prepare_catalog or ensure_tmdb_init)
    _spec("osd", ("osd_streams",), completion="directory", bypass_prepare_catalog=True, ensure_tmdb=False, custom=_custom_osd_streams),
    _spec("osd", ("osd_apply",), completion="end_directory_finally", bypass_prepare_catalog=True, ensure_tmdb=False, custom=_custom_osd_apply),
    # Direct / pre-TMDb routes
    _spec("gui", {"playback_details": "publish_playback_details"}, "lib.gui.custom_dialogs", completion="run_plugin", ensure_tmdb=False),
    _spec("direct", {"bobbi_relationships": "PeopleClient.relationships"}, "lib.clients.tmdb.people_client", completion="directory", ensure_tmdb=False),
    _spec("direct", {"bobbi_resume_card": "open_resume_card"}, "lib.utils.views.continue_watching", completion="script_or_dialog", ensure_tmdb=False),
    _spec("direct", {"continue_watching_menu": "show_continue_watching"}, "lib.utils.views.continue_watching", completion="directory", ensure_tmdb=False),
    _spec("direct", ("emby_rail",), completion="directory", ensure_tmdb=False, custom=_custom_emby_rail),
    _spec("stremio", ("source_import_manage_phone",), "lib.clients.stremio.manage_phone", completion="end_directory_failed_if_handle", ensure_tmdb=False),
    _spec("direct", ("bobbi_retry_rail",), completion="run_plugin", ensure_tmdb=False, custom=_custom_retry_rail),
    _spec("direct", {"personal_catalog": "execute"}, "lib.utils.views.personal_catalog", completion="directory", ensure_tmdb=False),
    _spec("direct", {"personal_catalog_play": "indexed"}, "lib.pan_playback", completion="directory", ensure_tmdb=False),
    _spec("direct", {"personal_catalog_manage": "manage"}, "lib.utils.views.personal_catalog", completion="script_or_dialog", ensure_tmdb=False),
    _spec("direct", {"pan_play": "play", "pan_history_play": "resume"}, "lib.pan_playback", completion="directory", ensure_tmdb=False),
    _spec("direct", {"am6b_helper_pick": "helper_pick"}, "lib.clients.maintainable_ui", completion="script_or_dialog", ensure_tmdb=False),
    _spec("direct", {"am6b_home": "handle", "am6b_discovery": "handle", "bobbi_setup": "handle"}, "lib.clients.maintainable_ui", completion="directory", ensure_tmdb=False),
    _spec("direct", {"bobbi_order_episodes": "show_order_episodes"}, "lib.clients.tmdb.episode_order", completion="directory", ensure_tmdb=False),
    _spec("direct", {"bobbi_related_movies": "show_related_movies"}, "lib.clients.tmdb.related_movies", completion="directory", ensure_tmdb=False),
    _spec("direct", {"bobbi_search_prompt": "search_prompt"}, "lib.clients.cinema_ui", completion="script_or_dialog", ensure_tmdb=False),
    _spec("direct", {"bobbi_ui_row": "handle"}, "lib.clients.cinema_ui", completion="directory", ensure_tmdb=False),
    _spec("direct", {"bobbi_library": "handle", "bobbi_open": "handle"}, "lib.clients.bobbi_library", completion="directory", ensure_tmdb=False),
    _spec("direct", ("am6b_warm",), completion="run_plugin", ensure_tmdb=False, pass_params=False, custom=_custom_am6b_warm),
    # AM6B fast-path routes
    _spec("am6b_fast", {"bobbi_refresh_metadata": "hydrate"}, "lib.clients.tmdb.frontend_metadata", completion="run_plugin", ensure_tmdb=False),
    _spec("am6b_fast", {"bobbi_continue_action": "continue_action"}, "lib.utils.views.continue_watching", completion="script_or_dialog", ensure_tmdb=False),
    _spec("am6b_fast", {"am6b_refresh_season_cards": "hydrate"}, "lib.clients.tmdb.season_cards", completion="run_plugin", ensure_tmdb=False),
    _spec(
        "am6b_fast",
        {
            "am6b_streaming_catalog": "handle_am6b_streaming_catalog",
            "am6b_streaming_search": "handle_am6b_streaming_search",
            "am6b_open_streaming_item": "handle_am6b_open_item",
            "am6b_refresh_anime_catalog": "hydrate_am6b_anime_catalog",
            "am6b_refresh_anime_search": "hydrate_am6b_anime_search",
        },
        "lib.clients.tmdb.anime_fast_catalog",
        completion="directory",
        ensure_tmdb=False,
    ),
    # Stremio group
    _spec(
        "stremio",
        (
            "stremio_toggle_addons",
            "stremio_toggle_catalogs",
            "stremio_toggle_tv_addons",
            "stremio_filtered_selection",
            "add_custom_stremio_addon",
            "configure_stremio_addon",
            "remove_custom_stremio_addon",
            "rename_stremio_addon",
            "rename_stremio_catalog",
            "stremio_bypass_addons_select",
            "stremio_subtitle_addons_select",
        ),
        "lib.clients.stremio.addon_selection",
        completion="script_or_dialog",
        prefixes=("stremio_", "list_stremio"),
    ),
    _spec("stremio", ("stremio_manage_phone",), "lib.clients.stremio.manage_phone", completion="script_or_dialog"),
    _spec("stremio", ("stremio_login", "stremio_logout", "stremio_update"), "lib.clients.stremio.authentication", completion="script_or_dialog"),
    _spec("stremio", ("torrentio_toggle_providers",), "lib.clients.stremio.torrentio", completion="script_or_dialog"),
    _spec("stremio", ("list_catalog", "list_catalog_genres", "search_catalog"), "lib.clients.catalog_hub", completion="directory"),
    _spec(
        "stremio",
        (
            "clear_stremio_search_history",
            "list_stremio_seasons",
            "list_stremio_episodes",
            "list_stremio_movie",
            "list_stremio_tv_streams",
            "list_stremio_tv",
        ),
        "lib.clients.stremio.catalog_menus",
        completion="directory",
    ),
    # TMDb group
    _spec(
        "tmdb",
        ("search_tmdb_year", "search_tmdb_genres"),
        completion="directory",
        prefixes=(
            "handle_tmdb",
            "search_tmdb",
            "search_tmbd",
            "rescrape_tmdb",
            "show_tmdb",
            "handle_collection",
            "search_people",
            "handle_keyword",
            "show_keyword",
        ),
        custom=_custom_tmdb_year_or_genres,
    ),
    _spec(
        "tmdb",
        {
            "search_people_by_id": "PeopleClient.search_people_by_id",
            "handle_tmdb_person_details": "PeopleClient.handle_tmdb_person_details",
            "handle_tmdb_person_info": "PeopleClient.handle_tmdb_person_info",
        },
        "lib.clients.tmdb.people_client",
        completion="directory",
    ),
    _spec("tmdb", {"handle_collection_details": "TmdbCollections.add_collection_details"}, "lib.clients.tmdb.collections", completion="directory"),
    _spec(
        "tmdb",
        {
            "handle_tmdb_search": "TmdbClient.handle_tmdb_search",
            "handle_tmdb_query": "TmdbClient.handle_tmdb_query",
            "search_tmdb_lang": "TmdbClient.show_lang_items",
            "search_tmbd_network": "TmdbClient.show_network_items",
            "search_tmdb_recommendations": "TmdbClient.search_tmdb_recommendations",
            "search_tmdb_similar": "TmdbClient.search_tmdb_similar",
            "tmdb_search_modes": "TmdbClient.tmdb_search_modes",
            "tmdb_episode_search_modes": "TmdbClient.tmdb_episode_search_modes",
            "rescrape_tmdb_media": "TmdbClient.rescrape_tmdb_media",
            "show_tmdb_item": "TmdbClient.show_tmdb_item",
            "handle_collection_query": "TmdbClient.handle_collection_query",
            "handle_keyword_search": "TmdbClient.handle_keyword_search",
            "show_keyword_results": "TmdbClient.show_keyword_results",
        },
        "lib.clients.tmdb.tmdb",
        completion="directory",
    ),
    # Trakt group
    _spec(
        "trakt",
        {
            "trakt_add_to_watchlist": "TraktClient.trakt_add_to_watchlist",
            "trakt_remove_from_watchlist": "TraktClient.trakt_remove_from_watchlist",
            "trakt_add_to_favorites": "TraktClient.trakt_add_to_favorites",
            "trakt_remove_from_favorites": "TraktClient.trakt_remove_from_favorites",
            "trakt_mark_as_watched": "TraktClient.trakt_mark_as_watched",
            "trakt_mark_as_unwatched": "TraktClient.trakt_mark_as_unwatched",
            "add_to_collection": "TraktClient.trakt_add_to_collection",
            "remove_from_collection": "TraktClient.trakt_remove_from_collection",
            "trakt_create_list": "TraktClient.trakt_create_list",
            "trakt_delete_list": "TraktClient.trakt_delete_list",
            "trakt_like_list": "TraktClient.trakt_like_list",
            "trakt_unlike_list": "TraktClient.trakt_unlike_list",
            "trakt_add_item_to_list": "TraktClient.trakt_add_item_to_list",
            "trakt_remove_item_from_list": "TraktClient.trakt_remove_item_from_list",
        },
        "lib.clients.trakt.trakt",
        completion="run_plugin",
        prefixes=("trakt_",),
    ),
    _spec(
        "trakt",
        (
            "trakt_auth",
            "trakt_auth_revoke",
            "trakt_continue_watching",
            "trakt_discard_playback",
            "trakt_group_menu",
            "trakt_list_content",
            "trakt_resume",
            "list_trakt_page",
        ),
        "lib.navigation",
        completion="directory",
    ),
    # Simkl group
    _spec(
        "simkl",
        (
            "simkl_auth",
            "simkl_logout",
            "simkl_continue_watching",
            "simkl_library",
            "simkl_library_statuses",
            "simkl_library_items",
            "simkl_move_to_status",
            "simkl_update_history",
            "simkl_resume",
            "simkl_discard_playback",
        ),
        "lib.navigation",
        completion="directory",
    ),
    # Nuvio group
    _spec(
        "nuvio",
        (
            "nuvio_auth",
            "nuvio_logout",
            "nuvio_toggle_addons",
            "nuvio_menu",
            "nuvio_continue_watching",
            "nuvio_history",
            "nuvio_library",
            "nuvio_remove_progress",
            "nuvio_resume",
            "nuvio_add_to_library",
            "nuvio_remove_from_library",
            "nuvio_update_history",
            "nuvio_collections",
            "nuvio_collection_folders",
            "nuvio_collection_sources",
            "nuvio_collection_discover",
            "nuvio_collection_source_unavailable",
        ),
        "lib.navigation",
        completion="directory",
    ),
    # Debrid group
    _spec(
        "debrid",
        (
            "rd_auth",
            "rd_remove_auth",
            "ad_auth",
            "ad_remove_auth",
            "real_debrid_info",
            "alldebrid_info",
            "debrider_auth",
            "debrider_remove_auth",
            "debrider_info",
            "get_rd_downloads",
            "get_tb_downloads",
            "get_oc_downloads",
            "cloud",
            "cloud_details",
            "pm_auth",
            "pm_remove_auth",
            "tb_auth",
            "tb_remove_auth",
            "oc_auth",
            "oc_remove_auth",
            "torbox_info",
            "offcloud_info",
            "easynews_info",
        ),
        "lib.navigation",
        completion="directory",
    ),
    # Telegram / Jackgram group
    _spec(
        "telegram",
        ("telegram_menu", "search_jackgram"),
        "lib.navigation",
        completion="directory",
        prefixes=("telegram_", "list_telegram", "list_jackgram", "test_jackgram", "search_jackgram"),
    ),
    _spec("telegram", ("test_jackgram_connection",), "lib.clients.jackgram.utils", completion="script_or_dialog"),
    _spec(
        "telegram",
        (
            "list_jackgram_raw_files",
            "list_jackgram_latest_movies",
            "list_jackgram_latest_series",
            "list_jackgram_title_sources",
        ),
        "lib.clients.jackgram.utils",
        completion="directory",
    ),
    # Torrserver group
    _spec(
        "torrserver",
        (
            "torrent_action",
            "torrent_files",
            "display_picture",
            "display_text",
            "download_torrent_subtitles",
            "download_and_play_subtitles",
        ),
        "lib.utils.torrent.torrserver_utils",
        completion="directory",
    ),
    _spec("torrserver", ("torrents", "torrentio_selection"), "lib.navigation", completion="directory"),
    # WebDAV group
    _spec(
        "webdav",
        (
            "list_webdav",
            "webdav_provider_test",
            "display_text_webdav",
            "show_picture_webdav",
        ),
        "lib.clients.webdav.client",
        completion="directory",
    ),
    # Downloads group
    _spec(
        "downloads",
        (
            "download_video",
            "handle_download_file",
            "handle_cancel_download",
            "handle_pause_download",
            "handle_delete_file",
            "resume_download",
            "download_cloud_file",
            "downloads_viewer",
        ),
        "lib.downloader",
        completion="script_or_dialog",
    ),
    _spec("downloads", ("downloads_menu", "open_download_manager"), "lib.navigation", completion="directory"),
    # MDBList group
    _spec(
        "mdblist",
        (
            "search_mdbd_lists",
            "user_mdbd_lists",
            "top_mdbd_lists",
            "show_mdblist_list",
        ),
        "lib.clients.mdblist.mdblist",
        completion="directory",
    ),
    # Cache group
    _spec(
        "cache",
        (
            "clear_all_cached",
            "clear_trakt_cache",
            "clear_tmdb_cache",
            "clear_stremio_cache",
            "clear_debrid_cache",
            "clear_mdblist_cache",
            "clear_database_cache",
            "clear_history",
            "clear_search_history",
        ),
        "lib.navigation",
        completion="run_plugin",
        prefixes=("clear_",),
    ),
    # GUI group
    _spec(
        "gui",
        ("run_next_dialog", "run_resume_dialog", "run_skip_intro_dialog"),
        "lib.gui.custom_dialogs",
        completion="script_or_dialog",
    ),
    _spec("gui", ("extras",), completion="script_or_dialog", custom=_custom_extras),
    _spec(
        "gui",
        ("test_source_select", "test_run_next", "test_resume_dialog", "test_download_dialog"),
        "lib.navigation",
        completion="script_or_dialog",
    ),
    # Source manager group
    _spec(
        "source_manager",
        {"source_manager_toggle": "open_source_manager_dialog", "manage_search_sources": "open_unified_sources_hub"},
        "lib.gui.source_manager_dialog",
        completion="script_or_dialog",
        pass_params=False,
    ),
    # Core fallback group
    _spec("core", {"search": "run_search_entry"}, "lib.search", completion="directory"),
    _spec("core", ("open_excluded_languages_dialog",), "lib.gui.excluded_languages_dialog", completion="script_or_dialog", pass_params=False),
    _spec(
        "core",
        ("choose_external_scraper", "open_external_scraper_settings"),
        "lib.gui.external_scraper_dialog",
        completion="script_or_dialog",
        pass_params=False,
    ),
    _spec("core", ("resolve_for_pack_selection", "resolve_for_subtitles"), "lib.actions", completion="script_or_dialog"),
    _spec("core", ("show_episodes_details", "show_seasons_details"), "lib.utils.views.shows", completion="directory"),
    _spec("core", ("delete_last_title_entry",), "lib.utils.views.last_titles", completion="run_plugin"),
    _spec(
        "core",
        {
            "tv_shows_items": "tv_shows_items",
            "movies_items": "movies_items",
            "direct_menu": "direct_menu",
            "search_menu": "search_menu",
            "anime_menu": "anime_menu",
            "anime_item": "anime_item",
            "anime_search": "anime_search",
            "animation_menu": "animation_menu",
            "animation_item": "animation_item",
            "tv_menu": "tv_menu",
            "search_direct": "search_direct",
            "search_item": "search_item",
            "next_page_anime": "next_page_anime",
            "play_media": "play_media",
            "play_autoscraped": "play_autoscraped",
            "play_from_pack": "play_from_pack",
            "play_trailer": "play_trailer",
            "play_url": "play_url",
            "settings_menu": "settings_menu",
            "settings": "settings",
            "export_settings_backup": "export_settings_backup",
            "restore_settings_backup": "restore_settings_backup",
            "reset_all_settings": "reset_all_settings",
            "factory_reset": "factory_reset",
            "history_menu": "history_menu",
            "files_history": "files_history",
            "titles_history": "titles_history",
            "titles_calendar": "titles_calendar",
            "library_menu": "library_menu",
            "library_shows": "library_shows",
            "library_movies": "library_movies",
            "library_calendar": "library_calendar",
            "remove_from_library": "remove_from_library",
            "clear_library": "clear_library",
            "remove_continue_watching": "remove_from_continue_watching",
            "add_to_library": "add_to_library",
            "addon_update": "addon_update",
            "show_changelog": "show_changelog",
            "open_burst_config": "open_burst_config",
            "kodi_logs": "kodi_logs",
            "choose_view": "choose_view",
            "save_view": "save_view",
            "reset_views": "reset_views",
            "views_menu": "views_menu",
        },
        "lib.navigation",
        completion="directory",
    ),
)


def _build_indices(specs):
    by_action = {}
    by_group_actions = {}
    by_group_prefixes = {}
    for spec in specs:
        group_set = by_group_actions.setdefault(spec.group, set())
        prefix_list = by_group_prefixes.setdefault(spec.group, [])
        for prefix in spec.prefixes:
            if prefix not in prefix_list:
                prefix_list.append(prefix)
        for name in spec.actions:
            if name in by_action:
                raise ValueError(f"Duplicate route action declaration: {name}")
            by_action[name] = spec
            group_set.add(name)
    return (
        by_action,
        {k: frozenset(v) for k, v in by_group_actions.items()},
        {k: tuple(v) for k, v in by_group_prefixes.items()},
    )


ROUTE_BY_ACTION, _GROUP_ACTIONS, _GROUP_PREFIXES = _build_indices(ROUTE_SPECS)

# Derived sets and matchers (backward-compatible projections from ROUTE_SPECS)
_TRAKT_EXTRAS = frozenset(a for a in _GROUP_ACTIONS["trakt"] if not a.startswith("trakt_"))
_DEBRID_ACTIONS = _GROUP_ACTIONS["debrid"]
_TORRSERVER_ACTIONS = _GROUP_ACTIONS["torrserver"]
_WEBDAV_ACTIONS = _GROUP_ACTIONS["webdav"]
_DOWNLOAD_ACTIONS = _GROUP_ACTIONS["downloads"]
_GUI_ACTIONS = _GROUP_ACTIONS["gui"]
_MDBLIST_ACTIONS = _GROUP_ACTIONS["mdblist"]
_AM6B_FAST_ACTIONS = _GROUP_ACTIONS["am6b_fast"]


def _make_group_matcher(group):
    exact = _GROUP_ACTIONS.get(group, frozenset())
    prefixes = _GROUP_PREFIXES.get(group, ())
    if prefixes:
        return lambda action: action in exact or action.startswith(prefixes)
    return lambda action: action in exact


_is_stremio_action = _make_group_matcher("stremio")
_is_tmdb_action = _make_group_matcher("tmdb")
_is_trakt_action = _make_group_matcher("trakt")
_is_simkl_action = _make_group_matcher("simkl")
_is_nuvio_action = _make_group_matcher("nuvio")
_is_debrid_action = _make_group_matcher("debrid")
_is_telegram_action = _make_group_matcher("telegram")
_is_torrserver_action = _make_group_matcher("torrserver")
_is_webdav_action = _make_group_matcher("webdav")
_is_download_action = _make_group_matcher("downloads")
_is_mdblist_action = _make_group_matcher("mdblist")
_is_cache_action = _make_group_matcher("cache")
_is_gui_action = _make_group_matcher("gui")
_is_source_manager_action = _make_group_matcher("source_manager")


def _dispatch_group(group, action, params):
    spec = ROUTE_BY_ACTION.get(action)
    if spec is None or (group != "core" and spec.group != group):
        return None
    return _invoke_spec(spec, action, params)


def _route_am6b_fast(action, params):
    return _dispatch_group("am6b_fast", action, params)


def _route_stremio(action, params):
    return _dispatch_group("stremio", action, params)


def _route_tmdb(action, params):
    return _dispatch_group("tmdb", action, params)


def _route_trakt(action, params):
    return _dispatch_group("trakt", action, params)


def _route_debrid(action, params):
    return _dispatch_group("debrid", action, params)


def _route_telegram(action, params):
    return _dispatch_group("telegram", action, params)


def _route_simkl(action, params):
    return _dispatch_group("simkl", action, params)


def _route_nuvio(action, params):
    return _dispatch_group("nuvio", action, params)


def _route_torrserver(action, params):
    return _dispatch_group("torrserver", action, params)


def _route_webdav(action, params):
    return _dispatch_group("webdav", action, params)


def _route_downloads(action, params):
    return _dispatch_group("downloads", action, params)


def _route_mdblist(action, params):
    return _dispatch_group("mdblist", action, params)


def _route_cache(action, params):
    return _dispatch_group("cache", action, params)


def _route_gui(action, params):
    return _dispatch_group("gui", action, params)


def _route_source_manager(action, params):
    return _dispatch_group("source_manager", action, params)


def _route_core(action, params):
    return _dispatch_group("core", action, params)


ROUTE_GROUPS = (
    (_is_stremio_action, _route_stremio),
    (_is_tmdb_action, _route_tmdb),
    (_is_trakt_action, _route_trakt),
    (_is_simkl_action, _route_simkl),
    (_is_nuvio_action, _route_nuvio),
    (_is_debrid_action, _route_debrid),
    (_is_telegram_action, _route_telegram),
    (_is_torrserver_action, _route_torrserver),
    (_is_webdav_action, _route_webdav),
    (_is_download_action, _route_downloads),
    (_is_mdblist_action, _route_mdblist),
    (_is_cache_action, _route_cache),
    (_is_gui_action, _route_gui),
    (_is_source_manager_action, _route_source_manager),
)


def _get_route_handler(action):
    for matcher, handler in ROUTE_GROUPS:
        if matcher(action):
            return handler
    return _route_core


def addon_router(*, prepare_catalog=None):
    param_string = sys.argv[2][1:]
    params = dict(parse.parse_qsl(param_string))
    action = params.get("action", "")
    # Kodi favourites and saved URLs may outlive the version that created them.
    if action.startswith("bobi_"):
        action = params["action"] = "bobbi_" + action[5:]

    spec = ROUTE_BY_ACTION.get(action)
    if spec is not None and spec.bypass_prepare_catalog:
        return _invoke_spec(spec, action, params)

    # A player popup is not a catalogue window: do not initialise the catalogue
    # cache, old plugin inventory or saved browsing views on its first frame.
    if prepare_catalog is not None:
        prepare_catalog()
    if param_string:
        if spec is not None and not spec.ensure_tmdb:
            return _invoke_spec(spec, action, params)
        if _is_am6b_anime_catalog_action(action, params):
            return _route_am6b_anime_catalog(action, params)

        from lib.utils.tmdb_init import ensure_tmdb_init

        ensure_tmdb_init()

        route_handler = _get_route_handler(action)
        return route_handler(action, params)

    from lib.navigation import root_menu

    root_menu()
