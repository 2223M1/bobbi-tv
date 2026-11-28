"""Standard Kodi source picker using the same resolvers and resident lifecycle."""
from uuid import uuid4
import xbmc
import xbmcgui
from bobbi_platform.playback import selected_identity, UnsupportedPlayback
from bobbi_platform.kodi import standard_handoff
from bobbi_platform.onboarding import engine_message
from bobbi_platform.torrserver import TorrServerClient, TorrServerError, Cancelled, selected_magnet
from bobbi_platform.runtime import call

SELECTION = 'bobbi.portable_selection'


def local_client():
    import xbmcvfs
    from bobbi_platform.environment import private_path
    from bobbi_platform.pairing import load, engine_document
    pair = load(private_path(xbmcvfs.translatePath, 'helper-pairing.json'))
    if pair is None:
        raise UnsupportedPlayback('请先在“影院设置”的“BT 播放”中连接本机助手。')
    return TorrServerClient(engine_document(pair))


def resolve_torrent(source, still_selected, information=None, force_picker=False):
    # An HTTP .torrent link is not silently fetched and added. A known exact
    # infohash is required, and every supplied magnet must agree with it.
    supplied = [value for value in (source.url, source.guid)
                if isinstance(value, str) and value.lower().startswith('magnet:')]
    for value in supplied:
        selected_magnet(source.infoHash, value)
    expected, magnet = selected_magnet(source.infoHash, supplied[0] if supplied else None)
    client = local_client()
    progress = xbmcgui.DialogProgress()
    progress.create('正在准备片源', '正在读取文件列表，最多等待 30 秒，可随时取消。')
    choosing = False
    evidence = None
    def cancelled():
        return not still_selected() or (not choosing and progress.iscanceled())
    def choose_file(files):
        nonlocal choosing, evidence
        if cancelled():
            return None
        import json
        from bobbi_core.file_evidence import PlayOnceAction
        from bobbi_core.torrent_selection import select_exact_file, play_once_candidates
        from bobbi_core.episode_identity import (bind_selected_episode,
            bind_catalog_episode, resolve_episode_binding, check_transport_episode_file)
        rows = [dict(id=f.id, path=f.path, length=f.size) for f in files]
        items = {f.id: f for f in files}
        releases = [getattr(source, 'title', '')]
        # Explicit pack browsing keeps its existing multi-file picker.
        context = information or {}
        tv = context.get('tv_data') or {}
        known_media = bool(tv or context.get('mode') in ('movies', 'movie'))
        if context.get('require_catalog_episode_binding') and not tv:
            raise ValueError('CATALOG_EPISODE_PROOF_REQUIRED')
        if known_media and not (force_picker and len(files) > 1):
            rid = context['request_id']
            season, episode = tv.get('season', ''), tv.get('episode', '')
            raw, movie = information.get('episode_binding') or '', None
            if tv:
                from lib.utils.player.utils import _jacktorr_cached_tv_identity
                catalog = _jacktorr_cached_tv_identity(information.get('ids'))
                numbering = json.loads(raw) if isinstance(raw, str) and raw else raw
                if not numbering or 'version' not in numbering:
                    numbering = numbering or bind_selected_episode(information.get('ids'), tv, expected)
                    raw = bind_catalog_episode(information.get('ids'), tv, rid,
                        'bt:' + expected, expected, catalog, numbering or None) or raw
                if isinstance(raw, dict):
                    raw = json.dumps(raw)
                if information.get('require_catalog_episode_binding') and not raw:
                    raise ValueError('CATALOG_EPISODE_PROOF_REQUIRED')
            else:
                from lib.clients.tmdb.movie_years import cached_movie_identity
                from bobbi_core.movie_identity import make_binding, file_identity_status
                catalog = cached_movie_identity((information.get('ids') or {}).get('tmdb_id'))
                if catalog:
                    movie = make_binding(catalog['evidence'], catalog['tmdb_id'], catalog['aliases'],
                                         rid, 'bt:' + expected)
            binding = resolve_episode_binding(raw, rid, 'bt:' + expected, expected, season, episode)
            rows = play_once_candidates(rows, season, episode, releases, rid, 'bt:' + expected,
                                        expected, raw, json.dumps(movie) if movie else '')
            try:
                matched = select_exact_file(rows, season, episode, releases[0], expected, binding)
                if tv:
                    check_transport_episode_file(raw, matched['path'], releases)
                else:
                    basename = matched['path'].replace('\\', '/').rsplit('/', 1)[-1]
                    if not movie or file_identity_status(movie, basename)['status'] == 'identity_insufficient':
                        raise ValueError('MOVIE_FILE_IDENTITY_UNRESOLVED')
                evidence = 'AUTO_VERIFIED_FILE'
                return items[matched['id']]
            except ValueError:
                pass  # Membership allows this play only; it never proves the episode.
        action = PlayOnceAction.for_candidates(rows)
        if action is PlayOnceAction.NO_MATCH:
            raise ValueError('NO_MATCHING_FILE_IN_SELECTED_SOURCE')
        if action is PlayOnceAction.USE_SOLE:
            row = rows[0]
        else:
            choosing = True
            progress.close()
            selected = xbmcgui.Dialog().select('选择要播放的文件', [row['path'] for row in rows])
            if type(selected) is not int or not 0 <= selected < len(rows):
                return None
            row = rows[selected]
        evidence = action.value
        return items[row['id']]
    try:
        result = client.select_source(expected, magnet=magnet, choose_file=choose_file,
            cancelled=cancelled, budget=30, recheck_files=lambda: evidence == 'SOLE_ELIGIBLE_FILE')
    finally:
        progress.close()
    identity = selected_identity('bt:' + result['info_hash'] + ':' + str(result['file_id']))
    # Only an already resolved single media file crosses the generic handoff.
    # Retain provenance separately; raw torrent/pack flags remain forbidden.
    return identity, {'url': result['url'], 'title': result['file_path'], 'resolved_backend': 'local_torrserver',
                      'info_hash': result['info_hash'], 'file_id': result['file_id'],
                      'source_title': getattr(source, 'title', result['file_path']),
                      'file_evidence': evidence, 'torrent_path': result['file_path']}


def queue_selected(window, source, pack_select=False, subtitle_download=False, local_subtitle=None):
    if window._selection_locked:
        return
    window._selection_locked = True
    window.item_information.pop('episode_binding', None)
    window.item_information.update(selection_policy='exact', request_id=uuid4().hex)
    try:
        account = call('account_status', {})
        call('standard_playback', dict(operation='select',
            request_id=window.item_information['request_id'], account=account))
        window.item_information['_account'] = account
    except (OSError, ValueError, RuntimeError):
        window._selection_locked = False
        window.last_error = '播放器尚未就绪，请稍后重试。'
        window.setProperty('playback_error', window.last_error)
        return
    xbmcgui.Window(10000).setProperty(SELECTION, window.item_information['request_id'])
    window._pending_selection = source
    window._standard_options = dict(pack_select=pack_select, subtitle_download=subtitle_download,
                                    local_subtitle=local_subtitle)
    window.close()


def manual_modal(window, base_modal):
    from lib.utils.kodi.utils import ADDON_HANDLE
    window._auto_select_pending = False
    while not xbmc.Monitor().abortRequested():
        window._selection_locked = False
        window._pending_selection = None
        window.setProperty("instant_close", "false")
        window.setProperty("resolving", "false")
        if getattr(window, 'source_session', None) is None:
            base_modal()
        else:
            window._run_progressive_window()
        source = window._pending_selection
        if source is None:
            if getattr(window, 'source_pump', None):
                window.source_pump.cancel()
                window.source_session.cancel()
            return False
        request_id = window.item_information.get('request_id')
        def still_selected():
            return bool(request_id and not xbmc.Monitor().abortRequested()
                        and window.item_information.get('request_id') == request_id
                        and xbmcgui.Window(10000).getProperty(SELECTION) == request_id)
        handoff = None
        try:
            identity = selected_identity(str(source.guid or source.url or source.infoHash))
            options = getattr(window, '_standard_options', {})
            if source.type not in ('Direct', 'Stremio', 'Torrent'):
                raise UnsupportedPlayback('暂不支持打开此片源，请选择其他片源。')
            # Run discovery alongside selected URL resolution, not after the
            # player starts. Same-share authority is independently revalidated.
            subtitle_data = dict(window.item_information, source_title=getattr(source, 'title', ''))
            from lib.clients.catalog_providers import provider_for
            if provider_for(source):
                from bobbi_catalog.identity import media_key
                tv = window.item_information.get('tv_data') or {}
                subtitle_data['_share'] = dict(locator=source.url, guid=source.guid, title=source.title,
                    size=source.size, account=window.item_information['_account'],
                    media=media_key((window.item_information.get('ids') or {}).get('tmdb_id'),
                        window.item_information.get('mode'), tv.get('season'), tv.get('episode')))
            call('standard_playback', dict(operation='subtitle_start', request_id=request_id, data=subtitle_data))
            if source.type == 'Torrent':
                source_data = window._ensure_playback_info(source)
                if not source_data:
                    raise ValueError('SELECTED_SOURCE_UNRESOLVED')
                if not source_data.get('is_torrent', True):
                    data = source_data
                else:
                    identity, resolved = resolve_torrent(source, still_selected, source_data,
                                                        options.get('pack_select', False))
                    data = dict(source_data, **resolved)
                    for flag in ('magnet', 'is_pack', 'is_torrent', 'require_catalog_episode_binding'):
                        data.pop(flag, None)
            else:
                data = window._ensure_playback_info(source)
            if not data:
                raise ValueError('No exact selected direct URL')
            resolved_title = data.get('title')
            data.update(window.item_information)
            data['title'] = data.get('title') or resolved_title
            from lib.services.standard_playback import resolve_selected
            data = resolve_selected(data, lambda: not still_selected(),
                                    session=getattr(window, 'prepared_session', None))
            if options.get('local_subtitle'):
                data['subtitles_path'] = [options['local_subtitle']]
            if options.get('subtitle_download'):
                from lib.clients.subtitle.submanager import SubtitleManager
                paths = SubtitleManager(data, lambda *a, **k: None).fetch_subtitles()
                if paths:
                    data['subtitles_path'] = paths
            if not still_selected():
                return False
            accepted = call('standard_playback', dict(operation='register', request_id=request_id, data=data))
            if not accepted.get('accepted'):
                return False
            if accepted.get('subtitles_path'):
                data['subtitles_path'] = accepted['subtitles_path']
            def ready():
                return (still_selected() and call('standard_playback',
                    dict(operation='current', request_id=request_id)).get('current') is True)
            # Manual single handoff; no background retry or claim of startup.
            handle = -1 if window.item_information.get('direct_playback_handoff') else int(ADDON_HANDLE)
            handoff = standard_handoff(identity, handle, ready=ready)
            result = handoff.submit(identity, data)
            if result['opened']:
                window.resolved = True
                return True
            return False
        except Cancelled:
            # User cancellation is not a failure or permission to switch.
            if not still_selected():
                return False
            window._restore_position = window.position
            if getattr(window, 'source_session', None):
                window.source_session.reopen()
            continue
        except TorrServerError as error:
            window.last_error = engine_message(error.code)
        except UnsupportedPlayback as error:
            window.last_error = str(error)
        except (ValueError, OSError, RuntimeError):
            window.last_error = '片源解析失败，请重试或选择其他片源。'
            if handoff is not None and handoff.state == 'submission_unknown':
                # The command may have reached Kodi. Never retry it or invoke
                # legacy cancellation that stops another/current video.
                window.last_error = '未确认是否已开播，请打开播放控制查看。本次不会自动重试。'
                xbmcgui.Dialog().ok('bobbi', window.last_error)
                return False
        call('standard_playback', dict(operation='cancel', request_id=request_id))
        xbmcgui.Dialog().ok('片源暂不可用', window.last_error)
        # Preserve the actual candidate pool and user's position on retry.
        window._restore_position = window.position
        if getattr(window, 'source_session', None):
            window.source_session.reopen()
    return False
