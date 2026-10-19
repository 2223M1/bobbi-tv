import contextlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from lib.api.trakt.trakt_utils import add_trakt_watched_context_menu, is_trakt_auth
from lib.clients.tmdb.utils.utils import (
    add_tmdb_episode_context_menu,
    add_tmdb_show_context_menu,
    tmdb_get,
)
from lib.utils.general.utils import (
    execute_thread_pool_collection,
    get_fanart_details,
    set_content_type,
    set_media_infoTag,
)
from lib.utils.kodi.utils import (
    add_directory_items_batch,
    apply_section_view,
    build_url,
    end_of_directory,
    get_setting,
    kodilog,
    make_list_item,
)
from lib.utils.nuvio_context import add_nuvio_history_context_menu
from lib.utils.simkl_context import add_simkl_history_context_menu


def show_seasons_details(params):
    set_content_type("season")

    ids = json.loads(params.get("ids", "{}"))
    mode = params.get("mode", "")
    media_type = params.get("media_type", "")

    if show_season_info(ids, mode, media_type) is False:
        from lib.utils.directory_failure import fail_directory

        return fail_directory()
    end_of_directory()
    apply_section_view("view.seasons", content_type="seasons")


def show_season_info(ids, mode, media_type):
    tmdb_id = ids.get("tmdb_id")
    tvdb_id = ids.get("tvdb_id")
    imdb_id = ids.get("imdb_id")

    if imdb_id:
        res = tmdb_get("find_by_imdb_id", imdb_id)
        if res and res.get("tv_results"):
            tmdb_id = res["tv_results"][0]["id"]

    # Keep one localized request and the upstream external-ID repair. Do not
    # re-fetch trailers/credits or mutate a process-global language setting.
    details = tmdb_get("tv_details", {
        "id": tmdb_id, "language": "zh-CN", "append_to_response": "external_ids",
    })
    if not details:
        return False

    # Callers such as the Nuvio library only know the tmdb_id. Resolve the
    # missing external ids from the details we already fetched, otherwise the
    # episode search carries a bare tmdb_id and sources that match by IMDB
    # (e.g. Torrentio) find nothing. No extra request: "tv_details" already
    # asks TMDB for external_ids.
    external_ids = getattr(details, "external_ids", None) or {}
    if not tvdb_id:
        tvdb_id = external_ids.get("tvdb_id") or tvdb_id
    if not imdb_id:
        imdb_id = external_ids.get("imdb_id") or imdb_id

    ids = {"tmdb_id": tmdb_id, "tvdb_id": tvdb_id, "imdb_id": imdb_id}

    name = details.name
    seasons = details.seasons
    fanart_details = get_fanart_details(tvdb_id=tvdb_id, mode=mode)

    results = execute_thread_pool_collection(
        seasons,
        _process_season,
        details,
        name,
        ids,
        mode,
        media_type,
        fanart_details,
    )

    # Sort by season number
    results.sort(key=lambda x: x[0])

    add_directory_items_batch(
        [(url, list_item, True) for _, url, list_item in results if list_item is not None]
    )
    from lib.clients.tmdb.related_movies import append_directory_entry
    append_directory_entry(ids)


def _process_season(season, details, name, ids, mode, media_type, fanart_details):
    season_name = season.name
    overview = season.overview
    if not overview:
        season.update({"overview": getattr(details, "overview", "")})

    season_number = season.season_number
    if not season_name or re.fullmatch(r'(?:Season\s*\d+|Miniseries|Specials)', season_name, re.IGNORECASE):
        season_name = "特别篇" if season_number == 0 else "第 {} 季".format(season_number)
    if season_number == 0 and not get_setting("include_tvshow_specials"):
        return  # skip specials if disabled

    list_item = make_list_item(label=season_name)
    set_media_infoTag(list_item, data=season, fanart_data=fanart_details, mode="season")
    from lib.clients.tmdb.frontend_metadata import apply
    apply(list_item, ids.get('tmdb_id'), 'season',
          dict(title=name, name=season_name, season=season_number, season_name=season_name))
    # The skin prefers ListItem.Title to Label. Keep both in the same display
    # language without mutating the cached provider object or search identity.
    list_item.getVideoInfoTag().setTitle(season_name)
    list_item.setProperty("IsPlayable", "false")

    context_menu = add_tmdb_show_context_menu(mode, ids)
    if is_trakt_auth():
        context_menu += add_trakt_watched_context_menu("shows", season=season_number, ids=ids)
    list_item.addContextMenuItems(context_menu)

    url = build_url(
        "show_episodes_details",
        tv_name=name,
        ids=ids,
        mode=mode,
        media_type=media_type,
        season=season_number,
    )

    return (season_number, url, list_item)


def show_episodes_details(params):
    set_content_type("episode")

    tv_name = params.get("tv_name", "")
    season = int(params.get("season", 1))
    ids = json.loads(params.get("ids", "{}"))
    mode = params.get("mode", "")
    media_type = params.get("media_type", "")

    kodilog(
        f"[EPISODES] show_episodes_details: tv_name={tv_name!r}, season={season}, "
        f"mode={mode!r}, media_type={media_type!r}, ids={ids}"
    )
    item_count = show_episode_info(tv_name, season, ids, mode, media_type)
    if item_count is None:
        from lib.utils.directory_failure import fail_directory

        return fail_directory("分集信息暂时无法加载，请稍后重试")
    kodilog(f"[EPISODES] show_episodes_details: added item_count={item_count}")
    end_of_directory()
    kodilog("[EPISODES] show_episodes_details: end_of_directory called")
    apply_section_view("view.episodes", content_type="episodes")


def _episode_value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _episode_map(season_details):
    episodes = _episode_value(season_details, "episodes", []) or []
    result = {}
    for episode in episodes:
        number = _episode_value(episode, "episode_number")
        if number is not None:
            result[int(number)] = episode
    return result


def _is_chinese_episode_title(value):
    value = str(value or "").strip()
    if not value:
        return False
    has_han = any("\u3400" <= char <= "\u9fff" for char in value)
    has_kana = any("\u3040" <= char <= "\u30ff" for char in value)
    return has_han and not has_kana


def _fetch_localized_season_pages(tmdb_id, season):
    requests = ("zh-CN", "zh-TW", "en-US")

    def load(language):
        try:
            return tmdb_get(
                "season_details",
                {
                    "id": tmdb_id,
                    "season": season,
                    "language": language,
                    "append_to_response": "",
                },
            )
        except Exception:
            kodilog(
                "[EPISODES] localized season request failed: language={}".format(language)
            )
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {language: executor.submit(load, language) for language in requests}
        return {language: future.result() for language, future in futures.items()}


def _build_localized_episode_rows(localized_pages):
    pages = {language: _episode_map(page) for language, page in localized_pages.items()}
    all_numbers = sorted(set().union(*(set(page) for page in pages.values())))
    rows = []
    for episode_number in all_numbers:
        zh_cn = pages.get("zh-CN", {}).get(episode_number)
        zh_tw = pages.get("zh-TW", {}).get(episode_number)
        english = pages.get("en-US", {}).get(episode_number)
        base_episode = zh_cn or zh_tw or english
        if base_episode is None:
            continue

        zh_cn_name = str(_episode_value(zh_cn, "name", "") or "").strip()
        zh_tw_name = str(_episode_value(zh_tw, "name", "") or "").strip()
        english_name = str(_episode_value(english, "name", "") or "").strip()
        chinese_name = ""
        for candidate in (zh_cn_name, zh_tw_name):
            if _is_chinese_episode_title(candidate):
                chinese_name = candidate
                break

        base_name = str(_episode_value(base_episode, "name", "") or "").strip()
        display_name = chinese_name or english_name or base_name or "第 {} 集".format(episode_number)
        search_name = english_name or base_name or chinese_name
        rows.append(
            (
                episode_number,
                base_episode,
                {
                    "zh": chinese_name,
                    "en": english_name,
                    "display": display_name,
                    "search": search_name,
                },
            )
        )
    return rows


def show_episode_info(tv_name, season, ids, mode, media_type):
    tmdb_id = ids.get("tmdb_id")
    localized_pages = _fetch_localized_season_pages(tmdb_id, season) if tmdb_id else {}
    localized_rows = _build_localized_episode_rows(localized_pages)

    if not localized_rows:
        # All three bounded localized requests have already completed. Reuse a
        # valid empty response; do not repeat the failed provider request again.
        season_details = next((page for page in localized_pages.values() if page is not None), None)
        if not season_details:
            kodilog(
                "[EPISODES] show_episode_info: no season_details for "
                "tmdb_id={}, season={}".format(tmdb_id, season)
            )
            return None
        localized_rows = []
        for episode in _episode_value(season_details, "episodes", []) or []:
            episode_number = int(_episode_value(episode, "episode_number", 0) or 0)
            name = str(_episode_value(episode, "name", "") or "").strip()
            localized_rows.append(
                (
                    episode_number,
                    episode,
                    {"zh": "", "en": name, "display": name, "search": name},
                )
            )

    kodilog(
        "[EPISODES] show_episode_info: localized episodes_count={} for tmdb_id={}, season={}".format(
            len(localized_rows), tmdb_id, season
        )
    )
    fanart_details = get_fanart_details(tvdb_id=ids.get("tvdb_id"), mode=mode)

    results = execute_thread_pool_collection(
        localized_rows,
        _process_localized_episode_row,
        tv_name,
        season,
        ids,
        mode,
        media_type,
        fanart_details,
    )
    results.sort(key=lambda item: item[0])
    item_count = len([list_item for _, _, list_item in results if list_item is not None])
    add_directory_items_batch(
        [(url, list_item, False) for _, url, list_item in results if list_item is not None]
    )
    from lib.clients.tmdb.related_movies import append_directory_entry
    append_directory_entry(ids)
    return item_count


def _process_localized_episode_row(
    row, tv_name, season, ids, mode, media_type, fanart_details
):
    _, episode, titles = row
    return _process_episode(
        episode,
        tv_name,
        season,
        ids,
        mode,
        media_type,
        fanart_details,
        localized_titles=titles,
    )


def episode_card_caption(number, title):
    """One episode number; preserve meaningful localized/original titles."""
    prefix = "第 {} 集".format(number)
    text = str(title or '').strip()
    generic = re.fullmatch(r'(?:第\s*0*' + str(number) + r'\s*集|Episode\s*0*' + str(number) + r')', text, re.IGNORECASE)
    return prefix if not text or generic else prefix + " · " + text


def _process_episode(
    episode,
    tv_name,
    season,
    ids,
    mode,
    media_type,
    fanart_details,
    localized_titles=None,
    display_order=None,
):
    localized_titles = localized_titles or {}
    episode_number = int(_episode_value(episode, "episode_number", 0) or 0)
    base_name = str(_episode_value(episode, "name", "") or "").strip()
    display_name = localized_titles.get("display") or base_name or "第 {} 集".format(episode_number)
    english_name = localized_titles.get("en") or ""
    chinese_name = localized_titles.get("zh") or ""
    search_name = localized_titles.get("search") or english_name or base_name or display_name

    tv_data = {
        "name": quote(search_name),
        "display_name": quote(display_name),
        "display_name_zh": quote(chinese_name),
        "display_name_en": quote(english_name),
        "episode": episode_number,
        "season": season,
    }

    list_item = make_list_item(label="{}x{}. {}".format(season, episode_number, display_name))
    list_item.setProperty("AM6B.Episode.Caption.zh", episode_card_caption(episode_number, display_name))
    if display_order:
        list_item.setLabel('{}x{}. {}'.format(display_order['season'], display_order['episode'], display_name))
        list_item.setProperty('AM6B.Episode.Caption.zh', episode_card_caption(display_order['episode'], display_name))
        list_item.setProperty('Bobi.CatalogEpisode', '{}x{}'.format(season, episode_number))
    if english_name and english_name != display_name:
        with contextlib.suppress(Exception):
            list_item.setLabel2(english_name)
    if chinese_name:
        list_item.setProperty("AM6B.Episode.Title.zh", chinese_name)
    if english_name:
        list_item.setProperty("AM6B.Episode.Title.en", english_name)
    list_item.setProperty("AM6B.Episode.SearchTitle", search_name)
    from lib.clients.cinema_ui import catalog_playable_property
    list_item.setProperty("IsPlayable", catalog_playable_property())
    list_item.setProperty("bobbi.simkl.tmdb_id", str(ids.get("tmdb_id", "")))
    list_item.setProperty("bobbi.simkl.media_type", "episode")
    list_item.setProperty("bobbi.simkl.season", str(season))
    list_item.setProperty("bobbi.simkl.episode", str(episode_number))
    set_media_infoTag(list_item, data=episode, fanart_data=fanart_details, mode="episode")
    from lib.clients.tmdb.frontend_metadata import apply
    apply(list_item, ids.get('tmdb_id'), 'episode', dict(title=tv_name,
          episode_title=display_name, season=season, episode=episode_number,
          still_path=_episode_value(episode, 'still_path', '')))
    if display_order:
        list_item.getVideoInfoTag().setSeason(display_order['season'])
        list_item.getVideoInfoTag().setEpisode(display_order['episode'])
        list_item.setProperty('Bobi.SeasonName', '')

    context_menu = add_tmdb_episode_context_menu(mode, tv_name, tv_data, ids)
    if is_trakt_auth():
        context_menu += add_trakt_watched_context_menu(
            "shows", season=season, episode=episode_number, ids=ids
        )
    context_menu += add_simkl_history_context_menu(
        "episode", ids.get("tmdb_id"), season, episode_number
    )
    context_menu += add_nuvio_history_context_menu(
        "episode", ids.get("tmdb_id"), season, episode_number, title=tv_name
    )
    list_item.addContextMenuItems(context_menu)

    url = build_url(
        "search",
        mode=mode,
        media_type=media_type,
        query=tv_name,
        ids=ids,
        tv_data=tv_data,
    )

    return (episode_number, url, list_item)
