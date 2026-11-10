import json
import os

from lib.db.pickle_db import PickleDatabase
from lib.jacktook.utils import kodilog
from lib.utils.general.utils import parse_time, set_pluging_category
from lib.utils.kodi.utils import (
    ADDON_PATH,
    add_directory_items_batch,
    apply_section_view,
    build_url,
    container_refresh,
    end_of_directory,
    make_list_item,
    translation,
)

pickle_db = PickleDatabase()


def delete_last_title_entry(params):
    pickle_db.delete_item(key="jt:lth", subkey=params.get("title"))
    container_refresh()


def show_last_titles(params):
    if params is None:
        params = {}

    set_pluging_category(translation(90070))

    per_page = 10
    page = int(params.get("page", 1))

    all_items = list(reversed(pickle_db.get_key("jt:lth").items()))
    total = len(all_items)

    start = (page - 1) * per_page
    end = start + per_page
    items = all_items[start:end]

    items = sorted(items, key=parse_time, reverse=True)

    # Add "Clear Titles" button
    directory_items = []

    list_item = make_list_item(label="Clear Titles")
    list_item.setArt({"icon": os.path.join(ADDON_PATH, "resources", "img", "clear.png")})
    directory_items.append((build_url("clear_history", type="lth"), list_item, True))

    from lib.clients.tmdb.frontend_metadata import apply, flush

    for title, data in items:
        formatted_time = data["timestamp"]
        mode = data["mode"]
        ids = data.get("ids")
        if mode not in ("tv", "movies", "tg_latest"):
            continue

        label = f"{title} — {formatted_time}"
        list_item = make_list_item(label=label)
        if mode in ("tv", "movies"):
            # The local history record owns identity, title/time and ordering.
            # Optional display metadata never waits for HTTP or hides an entry.
            tag = list_item.getVideoInfoTag()
            tag.setMediaType("tvshow" if mode == "tv" else "movie")
            tag.setTitle(title)
            try:
                apply(list_item, ids.get("tmdb_id") if isinstance(ids, dict) else None,
                      mode, dict(title=title))
            except Exception as error:
                kodilog("History display metadata unavailable: " + type(error).__name__)
            finally:
                list_item.setLabel(label)
        list_item.setArt({"icon": os.path.join(ADDON_PATH, "resources", "img", "trending.png")})
        list_item.addContextMenuItems(
            [
                (
                    "Delete from history",
                    f"RunPlugin({build_url('delete_last_title_entry', title=title)})",
                )
            ]
        )

        if mode == "tv":
            directory_items.append(
                (build_url("show_seasons_details", ids=ids, mode=mode), list_item, True)
            )
        elif mode == "movies":
            list_item.setProperty("IsPlayable", "true")
            directory_items.append(
                (build_url("search", mode=mode, query=title, ids=ids), list_item, False)
            )
        elif mode == "tg_latest":
            directory_items.append(
                (
                    build_url(
                        "list_jackgram_title_sources",
                        data=json.dumps(data.get("tg_data")),
                    ),
                    list_item,
                    True,
                )
            )

    if end < total:
        list_item = make_list_item(label="下一页")
        list_item.setProperty("Bobi.NextPage", "true")
        list_item.setArt({"icon": os.path.join(ADDON_PATH, "resources", "img", "nextpage.png")})
        directory_items.append((build_url("titles_history", page=page + 1), list_item, True))

    add_directory_items_batch(directory_items)

    end_of_directory()
    apply_section_view("view.history")
    flush()
