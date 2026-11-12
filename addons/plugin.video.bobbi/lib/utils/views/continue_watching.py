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
    try:
        return bool(_history_snapshot(PickleDatabase())[1])
    except (OSError, ValueError, TypeError, AttributeError):
        # Keep the destination discoverable so it can show its unavailable
        # state. A broken optional history store must not break the root menu.
        return True


def remove_continue_watching_item(params):
    if params.get('history_id'):
        from lib.db.file_history import FileHistory
        files = FileHistory()
        try:
            current = files.get(params['history_id'])
            if history_digest(current) == params.get('digest'):
                files.remove(params['history_id'], current)
        except (OSError, ValueError, TypeError):
            notification('本地文件记录暂不可用')
        executebuiltin('Container.Refresh')
        return
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


def _resume_status(state):
    # The completion receipt travels with this provider result. No global
    # window flag can be overwritten by a late Home/Personal request.
    label = '还没有在看的影片' if state == 'empty' else '暂时无法读取观看记录'
    item = make_list_item(label=label)
    item.setProperty('Bobi.Resume.State', state)
    from lib.cinema.frontend_contract import apply_rail_state
    apply_rail_state([('', item, False)], state, scope='local-profile')
    item.setProperty('IsPlayable', 'false')
    return ('', item, False)


def open_resume_card(params):
    """Read the current exact record, not a progress-bearing URL from yesterday."""
    from lib.cinema.focus_anchor import resume_key
    wanted = params.get('card', '')
    if not wanted.startswith('resume:') or len(wanted) != 71:
        return
    try:
        matches = [data for _, data, _ in _history_snapshot(PickleDatabase())[1]
                   if resume_key(data) == wanted]
    except (OSError, ValueError, TypeError, AttributeError):
        matches = []
    if len(matches) != 1:
        notification('记录已变化，请重新选择影片')
        return
    from lib.navigation import play_media
    play_media(dict(data=json.dumps(matches[0]), continue_watching='true'))


def _series_browse_context(data):
    """A public work route, never a copy of a historical playback request."""
    if (data.get('mode') not in ('tv', 'show', 'tvshow', 'episode', 'anime')
            or not isinstance(data.get('ids', {}), dict)
            or not isinstance(data.get('tv_data'), dict)):
        return []
    from lib.cinema.frontend_contract import history_identity
    identity = history_identity(data)
    if identity[0] != 'tv' or identity[1] <= 0 or identity[3] <= 0:
        return []
    url = build_url('show_tmdb_item', id=identity[1], mode='tv', media_type='tv',
                    title=clean_title(data.get('title')))
    return [('查看全剧分集', 'ActivateWindow(Videos,{},return)'.format(url))]


def _history_snapshot(database):
    # Both namespaces share one atomic read. Compatibility adapters exposing
    # only the legacy interface continue to provide ordinary title history.
    if not hasattr(database, 'get_keys_checked'):
        history = database.get_key_checked('jt:lfh')
        return history, history_rows(history.items(), parse_time)
    from datetime import datetime
    from lib.db.file_history import FileHistory, KEY
    values = database.get_keys_checked(('jt:lfh', KEY))
    history = values.get('jt:lfh') or {}
    items = history_rows(history.items(), parse_time)
    unavailable = False
    try:
        files = FileHistory.read_rows(values.get(KEY))
    except (ValueError, TypeError):
        files, unavailable = [], True
    for row in files:
        items.append([row['id'], dict(_file_record=row,
            timestamp=datetime.fromtimestamp(row['updated_at']).strftime('%a, %d %b %Y %H:%M:%S')), []])
    items = sorted(items, key=lambda row: parse_time((row[0], row[1])), reverse=True)
    if unavailable:
        items.append(['', {'_file_unavailable': True}, []])
    return history, items


def _file_item(record, link=None):
    from lib.cinema.frontend_contract import personal_file_projection
    from bobbi_platform.pan_accounts import NAMES
    display = personal_file_projection(record, NAMES)
    item = make_list_item(label=display['title'])
    item.setArt({'icon': os.path.join(ADDON_PATH, 'resources', 'img', 'history.png')})
    if display['percent'] is not None:
        item.setProperty('PercentPlayed', str(display['percent']))
    else:
        item.setProperty('Bobi.File.Duration', 'unknown')
    item.setProperty('Bobi.SourceKind', display['source'] + ' · ' + display['kind'])
    item.setProperty('Bobi.Resume.State', 'ready')
    item.setProperty('Bobi.Rail.State', 'ready')
    item.setProperty('Bobi.CardKey', 'file:' + record['id'])
    from lib.cinema.focus_anchor import opaque
    ref = record['file_ref']
    item.setProperty('node.visible', 'String.IsEqual(Window(Home).Property(Bobi.Rail.Account.%s),%s)'
                     % (ref['provider'], opaque(ref['account_id'])))
    item.setProperty('Bobi.File.State', display['state'])
    item.setProperty('Bobi.File.ResumeDetail', display['detail'])
    item.setProperty('IsPlayable', 'false')
    if link and link.get('entity_id') == record['id'] and link.get('parent_entity_id'):
        from lib.utils.views.personal_catalog import route, scope_params
        from bobbi_core.catalog_display import file_description
        target = route(action='personal_catalog', view='files', parent_entity_id=link['parent_entity_id'],
                       **scope_params(link['expected']))
        item.setProperty('Bobi.Catalog.Variants', target)
        detail = ' · '.join(filter(None, [link.get('work_title'),
            file_description(link, record['position'], record['duration'])]))
        item.setLabel2(detail)
        item.setProperty('Bobi.File.ResumeDetail', detail)
        item.addContextMenuItems([('查看此作品的文件版本', 'ActivateWindow(Videos,"' + target + '",return)')])
    item.addContextMenuItems([
        ('从头播放', 'RunPlugin({})'.format(build_url('pan_history_play', history_id=record['id'], start_over='true'))),
        ('从继续观看中移除', 'RunPlugin({})'.format(build_url('remove_continue_watching',
            history_id=record['id'], digest=history_digest(record)))),
    ])
    return build_url('pan_history_play', history_id=record['id']), item, False


def show_continue_watching(params=None):
    if params is None:
        params = {}

    set_pluging_category(translation(90200))
    setContent(ADDON_HANDLE, "videos")

    preview = params.get('resume_preview') == 'true'
    rail = params.get('rail') == 'continue_watching'
    per_page = 1 if preview else 20 if rail else 10
    page = 1 if preview else int(params.get("page", 1))

    try:
        history, filtered_items = _history_snapshot(PickleDatabase())
    except (OSError, ValueError, TypeError, AttributeError):
        error_row = _resume_status('error')
        if rail:
            error_row = (build_url('bobi_retry_rail', rail='continue_watching'), error_row[1], False)
        add_directory_items_batch([error_row])
        end_of_directory(cache=False)
        return

    total = len(filtered_items)
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered_items[start:end]
    links = {}
    file_ids = [data['_file_record']['id'] for _, data, _ in items if '_file_record' in data]
    if file_ids:
        try:
            from bobbi_platform.runtime import call
            links = {row['entity_id']: row for row in call('catalog_history_links', dict(history_ids=file_ids))['items']}
        except (ImportError, OSError, ValueError, RuntimeError, TypeError, KeyError):
            pass  # Missing catalogue does not remove or prevent original-file resume.

    directory_items = [_resume_status('empty')] if (preview or rail) and not filtered_items else []
    if rail and directory_items:
        row = directory_items[0]
        directory_items[0] = (build_url('am6b_streaming_catalog', section='movie', page=1), row[1], True)

    for title, data, source_keys in items:
        if data.get('_file_unavailable'):
            unavailable = make_list_item(label='个人文件观看记录暂不可用')
            unavailable.setProperty('IsPlayable', 'false')
            unavailable.setProperty('Bobi.Resume.State', 'error')
            unavailable.setProperty('Bobi.Rail.State', 'error')
            directory_items.append((build_url('bobi_retry_rail', rail='continue_watching')
                                    if rail else '', unavailable, False))
            continue
        if '_file_record' in data:
            directory_items.append(_file_item(data['_file_record'], links.get(data['_file_record']['id'])))
            continue
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
        list_item.setProperty('Bobi.Resume.State', 'ready')
        list_item.setProperty('Bobi.Rail.State', 'ready')

        # This action may open the picker before any media is resolved.
        list_item.setProperty("IsPlayable", "false")
        context_menu = [
            ('从头播放', 'RunPlugin({})'.format(build_url('play_media', data=json.dumps(data), start_over='true', continue_watching='true'))),
            ('选择其他片源', 'RunPlugin({})'.format(build_url('bobi_continue_action', data=json.dumps(data)))),
        ]
        context_menu.extend(_series_browse_context(data))
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
        from lib.cinema.focus_anchor import resume_key
        card_key = resume_key(data)
        if card_key:
            list_item.setProperty('Bobi.CardKey', card_key)
            # Keep public warming fields stable; this route uses only card to
            # re-read history and never trusts an external playback payload.
            url = build_url('bobi_resume_card', card=card_key,
                            id=identifier, mode='tv' if tv_data else 'movies')
        if rail and isinstance(data.get('_account'), dict):
            from lib.cinema.focus_anchor import opaque
            account = data['_account']
            provider = account.get('provider', '115')
            try:
                if provider == '115':
                    from bobbi_platform.account_manager import validate_snapshot
                    scope_token = opaque(validate_snapshot(account, authenticated=True))
                else:
                    from lib.utils.views.personal_catalog import scope_key
                    scope_token = scope_key(account)
                list_item.setProperty('node.visible',
                    'String.IsEqual(Window(Home).Property(Bobi.Rail.Scope.%s),%s)' % (provider, scope_token))
            except (ValueError, TypeError):
                list_item.setProperty('node.visible', 'false')

        directory_items.append((url, list_item, False))

    if not preview and not rail and end < total:
        list_item = make_list_item(label="下一页")
        list_item.setProperty("Bobi.NextPage", "true")
        list_item.setArt({"icon": os.path.join(ADDON_PATH, "resources", "img", "nextpage.png")})
        directory_items.append(
            (build_url("continue_watching_menu", page=page + 1), list_item, True)
        )

    add_directory_items_batch(directory_items)

    end_of_directory(cache=False)
    if not preview:
        apply_section_view("view.history", content_type="videos")
