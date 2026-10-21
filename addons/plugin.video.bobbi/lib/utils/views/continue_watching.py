import json
import os
from urllib.parse import unquote

from xbmc import executebuiltin
from xbmcplugin import setContent

from lib.db.pickle_db import PickleDatabase
from lib.cinema.frontend_contract import clean_title, history_rows, history_digest, progress
from lib.utils.general.utils import (
    Indexer,
    IndexerType,
    clear_continue_watching_history,
    set_pluging_category,
)
from lib.utils.kodi.utils import (
    ADDON_HANDLE,
    ADDON_PATH,
    add_directory_items_batch,
    apply_section_view,
    build_url,
    end_of_directory,
    make_list_item,
    notification,
    translation,
)
from lib.utils.views.last_files import parse_time


def has_continue_watching_items():
    return bool(history_rows(PickleDatabase().get_key("jt:lfh").items(), parse_time))


def remove_continue_watching_item(params):
    if params.get('entries'):
        expected = json.loads(params['entries'])
        database = PickleDatabase()
        current = database.get_key('jt:lfh')
        for key, digest in expected.items():
            data = current.get(key)
            if data is not None and history_digest(data) == digest:
                database.delete_item_if('jt:lfh', key, data, commit=False)
        database.commit()
        executebuiltin('Container.Refresh')
        return
    title = params.get("title")
    if title == "__all__":
        clear_continue_watching_history()
        notification(translation(91001))
        executebuiltin("Container.Refresh")
        return
    if title:
        PickleDatabase().delete_item(key="jt:lfh", subkey=title)
        executebuiltin("Container.Refresh")


def _source_label(data):
    """Best-effort human-readable source class for a stored playback payload."""
    indexer = data.get("indexer", "")
    name = data.get("name", "")
    if indexer in (Indexer.JACKGRAM, Indexer.TELEGRAM) or name in (
        Indexer.JACKGRAM,
        Indexer.TELEGRAM,
    ):
        return str(indexer or name)
    if data.get("indexer") == Indexer.EASYNEWS:
        return "Easynews"
    if data.get("debrid_type"):
        return str(data["debrid_type"])
    source_type = data.get("type", "")
    if source_type == IndexerType.STREMIO_DEBRID:
        return "Stremio"
    if source_type == IndexerType.DEBRID:
        return "Debrid"
    if source_type == IndexerType.TORRENT:
        return "Torrent"
    if source_type == IndexerType.DIRECT:
        return "Direct"
    if data.get("is_torrent") or data.get("magnet") or data.get("info_hash"):
        return "Torrent"
    return ""


def _source_kind(data):
    if data.get('prepared_resource_id') or data.get('direct_cloud_key') or '115' in str(data.get('indexer', '')):
        return '网盘'
    label = _source_label(data)
    return '种子' if label == 'Torrent' else '直链' if label in ('Direct', 'Easynews') else '网盘' if label else ''


def continue_action(params):
    from lib.navigation import _resume_search_params
    from lib.search import run_search_entry
    data = json.loads(params['data'])
    search = _resume_search_params(data, {})
    search['force_select'] = True
    run_search_entry(search)


def show_continue_watching(params=None):
    if params is None:
        params = {}

    set_pluging_category(translation(90200))
    setContent(ADDON_HANDLE, "videos")

    per_page = 10
    page = int(params.get("page", 1))

    history = PickleDatabase().get_key('jt:lfh')
    filtered_items = history_rows(history.items(), parse_time)

    total = len(filtered_items)
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered_items[start:end]

    directory_items = []

    for title, data, source_keys in items:
        # Display is a separate projection. Playback receives the original payload.
        # Retain release317's URL-decoding at the playback boundary.
        data = dict(data, title=unquote(data.get('title') or ''))
        tv_data = data.get('tv_data') or {}
        display = dict(data, title=clean_title(data.get('title')), continue_watching=True,
                       episode_title=tv_data.get('name', ''))
        display.update({k: tv_data[k] for k in ('season', 'episode') if k in tv_data})
        list_item = make_list_item(label=display['title'])
        list_item.setArt({'icon': os.path.join(ADDON_PATH, 'resources', 'img', 'magnet.png')})
        from lib.clients.tmdb.frontend_metadata import apply
        identifier = (data.get('ids') or {}).get('tmdb_id') or data.get('tmdb_id')
        apply(list_item, identifier, 'episode' if tv_data else 'movie', display)
        # UI-action rows own their resume/start-over flow. Native resume tags
        # inject duplicate context actions and can bypass source recovery.
        # Keep progress as display data; the original payload retains seconds.
        list_item.setProperty("PercentPlayed", str(round(progress(data))))
        list_item.setProperty('Bobi.SourceKind', _source_kind(data))

        # This action may open the picker before any media is resolved.
        list_item.setProperty("IsPlayable", "false")
        context_menu = [
            ('从头播放', 'RunPlugin({})'.format(build_url('play_media', data=json.dumps(data), start_over='true', continue_watching='true'))),
            ('选择其他片源', 'RunPlugin({})'.format(build_url('bobi_continue_action', data=json.dumps(data)))),
        ]
        context_menu.append(
            (
                '从继续观看中移除',
                'RunPlugin({})'.format(build_url('remove_continue_watching', entries=json.dumps({k: history_digest(history[k]) for k in source_keys}))),
            )
        )
        context_menu.append(
            (
                '清空继续观看',
                f"RunPlugin({build_url('remove_continue_watching', title='__all__')})",
            )
        )
        list_item.addContextMenuItems(context_menu)

        # url to play
        url = build_url("play_media", data=json.dumps(data), continue_watching='true')

        directory_items.append((url, list_item, False))

    if end < total:
        list_item = make_list_item(label="下一页")
        list_item.setProperty("Bobi.NextPage", "true")
        list_item.setArt({"icon": os.path.join(ADDON_PATH, "resources", "img", "nextpage.png")})
        directory_items.append(
            (build_url("continue_watching_menu", page=page + 1), list_item, True)
        )

    add_directory_items_batch(directory_items)

    end_of_directory(cache=False)
    apply_section_view("view.history", content_type="videos")
