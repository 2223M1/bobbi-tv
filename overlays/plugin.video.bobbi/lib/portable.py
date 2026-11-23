"""Stock Kodi manual picker integration. No native AM6B IPC is imported.

Direct and explicitly paired local BT support are migration previews.
Prepared-cloud promotion and automatic continuation remain unavailable.
"""
from uuid import uuid4
import xbmc
import xbmcgui
from bobbi_platform.playback import selected_identity, UnsupportedPlayback
from bobbi_platform.kodi import standard_handoff
from bobbi_platform.onboarding import engine_message
from bobbi_platform.torrserver import TorrServerClient, TorrServerError, Cancelled, selected_magnet

SELECTION = 'bobbi.portable_selection'


def local_client():
    import xbmcvfs
    from bobbi_platform.environment import private_path
    from bobbi_platform.pairing import load, engine_document
    pair = load(private_path(xbmcvfs.translatePath, 'helper-pairing.json'))
    if pair is None:
        raise UnsupportedPlayback('先打开“bobbi 首次设置”连接本机助手，再选择 BT 片源。')
    return TorrServerClient(engine_document(pair))


def resolve_torrent(source, still_selected):
    # An HTTP .torrent link is not silently fetched and added. A known exact
    # infohash is required, and every supplied magnet must agree with it.
    supplied = [value for value in (source.url, source.guid)
                if isinstance(value, str) and value.lower().startswith('magnet:')]
    for value in supplied:
        selected_magnet(source.infoHash, value)
    expected, magnet = selected_magnet(source.infoHash, supplied[0] if supplied else None)
    client = local_client()
    progress = xbmcgui.DialogProgress()
    progress.create('bobbi · 准备所选片源', '正在读取文件列表，最多等待 30 秒；可随时取消。')
    choosing = False
    def cancelled():
        return not still_selected() or (not choosing and progress.iscanceled())
    def choose_file(files):
        nonlocal choosing
        if cancelled():
            return None
        choosing = True
        progress.close()
        # No implicit first-video choice, even for one result. A filename is
        # not proof of the user's intended episode or catalogue identity.
        selected = xbmcgui.Dialog().select('选择要播放的文件', [file.path for file in files])
        return files[selected] if 0 <= selected < len(files) else None
    try:
        result = client.select_source(expected, magnet=magnet, choose_file=choose_file,
                                      cancelled=cancelled, budget=30)
    finally:
        progress.close()
    identity = selected_identity('bt:' + result['info_hash'] + ':' + str(result['file_id']))
    # Only an already resolved single media file crosses the generic handoff.
    # Retain provenance separately; raw torrent/pack flags remain forbidden.
    return identity, {'url': result['url'], 'title': result['file_path'], 'resolved_backend': 'local_torrserver',
                      'info_hash': result['info_hash'], 'file_id': result['file_id']}


def queue_selected(window, source, pack_select=False, subtitle_download=False, local_subtitle=None):
    if window._selection_locked:
        return
    if pack_select or subtitle_download or local_subtitle:
        window.last_error = '该高级选源操作尚未完成通用版适配，请使用 Kodi 标准字幕菜单。'
        window.setProperty('playback_error', window.last_error)
        return
    window._selection_locked = True
    window.item_information.pop('episode_binding', None)
    window.item_information.update(selection_policy='portable_manual', request_id=uuid4().hex)
    xbmcgui.Window(10000).setProperty(SELECTION, window.item_information['request_id'])
    window._pending_selection = source
    window.close()


def manual_modal(window, base_modal):
    from lib.utils.kodi.utils import ADDON_HANDLE
    window._auto_select_pending = False
    while not xbmc.Monitor().abortRequested():
        window._selection_locked = False
        window._pending_selection = None
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
            # Reject missing backend BEFORE invoking legacy resolution which
            # can prompt for plugin installation or mutate cloud state.
            if (source.type not in ('Direct', 'Stremio', 'Torrent')
                    or source.isPack and source.type != 'Torrent'
                    or getattr(source, 'requiresCatalogEpisodeProof', False)
                    or getattr(source, 'preparedResourceId', '')
                    or getattr(source, 'directCloudKey', '')):
                raise UnsupportedPlayback('该片源需要 BT / 个人网盘后台，通用版尚未就绪。')
            if source.debridType:
                raise UnsupportedPlayback('此网盘版本仍需独立账号与文件校验适配，尚未启用。')
            if source.type == 'Torrent':
                identity, data = resolve_torrent(source, still_selected)
            else:
                data = window._ensure_playback_info(source)
            if not data:
                raise ValueError('No exact selected direct URL')
            if not still_selected():
                return False
            # Manual single handoff; no background retry or claim of startup.
            handle = -1 if window.item_information.get('direct_playback_handoff') else int(ADDON_HANDLE)
            handoff = standard_handoff(identity, handle, ready=still_selected)
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
            window.last_error = '当前片源未能解析。未自动改选其他版本。'
            if handoff is not None and handoff.state == 'submission_unknown':
                # The command may have reached Kodi. Never retry it or invoke
                # legacy cancellation that stops another/current video.
                window.last_error = '播放请求已发送但响应不明。请用 Kodi 标准播放器确认；本次不会重试。'
                xbmcgui.Dialog().ok('bobbi', window.last_error)
                return False
        xbmcgui.Dialog().ok('bobbi · 通用播放预览', window.last_error)
        # Preserve the actual candidate pool and user's position on retry.
        window._restore_position = window.position
        if getattr(window, 'source_session', None):
            window.source_session.reopen()
    return False
