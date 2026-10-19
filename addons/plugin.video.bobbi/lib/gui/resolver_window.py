from datetime import timedelta
from typing import Any, Dict, Optional, cast
from threading import Event
from uuid import uuid4
import json

import xbmc
import xbmcgui

from lib.clients.subtitle.submanager import SubtitleManager
from lib.db.cached import cache
from lib.domain.torrent import TorrentStream
from lib.gui.base_window import BaseWindow
from lib.gui.source_pack_select import SourcePackSelect
from lib.player import JacktookPLayer
from lib.utils.debrid.debrid_utils import get_pack_info
from lib.utils.kodi.utils import (
    ADDON_PATH,
    get_setting,
    kodilog,
    notification,
    set_property,
    get_property,
)


class ResolverWindow(BaseWindow):
    def __init__(
        self,
        xml_file: str,
        location: str,
        source: TorrentStream,
        item_information: Optional[Dict[str, Any]] = None,
        previous_window: Optional[BaseWindow] = None,
        close_callback: Optional[Any] = None,
        is_subtitle_download: bool = False,
        local_subtitle_path: Optional[str] = None,
    ) -> None:
        super().__init__(
            xml_file,
            location,
            item_information=item_information,
            previous_window=previous_window,
        )
        self.stream_data: Optional[Any] = None
        self.progress: int = 1
        self.resolver: Optional[Any] = None
        self.source: TorrentStream = source
        self.pack_select: bool = False
        self.is_subtitle_download = is_subtitle_download
        self.local_subtitle_path = local_subtitle_path
        self.item_information: Dict = item_information or {}
        self.close_callback: Optional[Any] = close_callback
        self.playback_info: Optional[Dict[str, Any]] = None
        self.pack_info: Optional[Any] = None
        self.previous_window: BaseWindow = previous_window
        self.setProperty("enable_busy_spinner", "false")
        # Presentation hint on this window, never playback/cancellation authority.
        self.setProperty("BobiLoadingPresenter", "true")
        self.resolved = False
        self.player = None
        self.cancel_event = Event()
        self.error_message = ""
        self.resolution_answered = False
        self._modeless = False
        self._dialog_id = 0
        self._window_token = uuid4().hex
        self.setProperty('AM6B.ResolverToken', self._window_token)
        self._window_context = None
        self.user_cancelled = False
        self.startup_failure_category = None
        self.preparation_intent = None

    def doModal(
        self,
        pack_select: bool = False,
    ) -> bool:
        self.pack_select = pack_select

        self._update_window_properties(self.source)
        self._modeless = (self.item_information.get("selection_policy") == "exact"
                          and not pack_select and not self.is_subtitle_download)
        if self._modeless:
            from lib.cinema.playback_request import call, context
            self._window_context = context(call({'operation': 'snapshot'}),
                                           self.item_information.get('request_id'))
            if not call(dict(self._window_context, operation='register_window',
                             token=self._window_token, role='loading'))['registered']:
                return False
            self.show()
            try:
                self.resolve_source()
            finally:
                self.close()
        else:
            super().doModal()
        return self.resolved

    def onInit(self) -> None:
        super().onInit()
        self._dialog_id = xbmcgui.getCurrentWindowDialogId()
        if not self._modeless:
            self.resolve_source()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id and getattr(self, "_modeless", False):
            self.user_cancelled = True
            self.cancel_event.set()
            request_id = self.item_information.get("request_id", "")
            if request_id and self._owns_selection():
                set_property("bobbi_cinema_cancel", request_id)
            self.close()
            return
        if action.getId() in self.action_exitkeys_id and self.player is not None:
            # Back closes the pending resolver and its waiter, not global playback.
            cancel = getattr(self.player, '_cinema_cancel', None)
            if cancel is not None:
                cancel.set()
        super().onAction(action)

    def _owns_selection(self):
        if not self._modeless:
            return True
        from lib.cinema.playback_request import owned_state
        try:
            owned_state(self.item_information.get('request_id'))
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def close_windows(self):
        if self.previous_window:
            self.previous_window.setProperty("instant_close", "true")
            self.previous_window.close()
        self.close()

    def handle_playback_started(self):
        if self.cancel_event.is_set() or self.resolved or not self._owns_selection():
            return False
        if not self._modeless:
            self.resolved = True
        elif self._dialog_id and self._window_context:
            # The resident adapter observes the actual token-bearing window
            # before close() queues its asynchronous GUI teardown. A caller's
            # visibility bool is never a fullscreen retry receipt.
            from lib.cinema.playback_request import call
            try:
                call(dict(self._window_context, operation='begin_window_close',
                          token=self._window_token, dialog_id=self._dialog_id))
            except (OSError, RuntimeError, ValueError):
                # Optional tracking may be unavailable on an older resident or
                # lose its reply. Still close normally; the required ownership
                # and lease-release checks below must retain their failures.
                pass
        self.close_windows()
        if self._modeless:
            # close() queues GUI work. Give only our closing dialog a bounded
            # handoff window; never close a different modal dialog globally.
            for _ in range(20):
                if not self._owns_selection() or self.cancel_event.is_set():
                    return False
                if not self._dialog_id or not xbmc.getCondVisibility("Window.IsVisible({})".format(self._dialog_id)):
                    break
                xbmc.sleep(25)
            else:
                kodilog("[CINEMA-HANDOFF] owned loading window did not close in time")
                return False
            from lib.cinema.playback_request import call
            if not self._window_context or not call(dict(self._window_context,
                    operation='close_window', token=self._window_token))['closed']:
                return False
            # The player requests the conditional native handoff after this
            # callback; no unscoped ActivateWindow is issued from a resolver.
        return True

    def handle_handoff_confirmed(self):
        if (not self.cancel_event.is_set() and self._owns_selection()
                and get_property('bobbi_active_player_session') == self.item_information.get('request_id')
                and self.player is not None and self.player._handoff_confirmed):
            # The player already observed fullscreen. A subsequent user Back
            # must not revoke that completed handoff or cause another activation.
            self.resolved = True

    def handle_playback_error(self):
        if getattr(self, 'resolved', False):
            # A completed handoff cannot become a new source-selection modal
            # because a later subtitle/tracking callback failed.
            kodilog('[CINEMA-HANDOFF] post-handoff error does not reopen selection', level=xbmc.LOGWARNING)
            return
        if not self._owns_selection():
            self.close()
            return
        self.resolved = False
        self.setProperty("resolving", "false")
        self.error_message = "该片源暂时无法播放，请选择其他片源或重试。"
        category = getattr(self.player, '_startup_failure_category', None)
        if category in {'target_unresolved', 'invalid_binding', 'selected_file_missing', 'no_candidate'}:
            self.error_message = "无法确定该片源中的目标集，未自动选择其他文件。"
        elif category == 'metadata_timeout':
            self.error_message = "等待 BT 元数据超时，尚未取得目标文件资料；请重试或选择其他片源。"
        elif category == 'buffer_timeout':
            self.error_message = "已取得目标文件资料，但首段缓冲超时；请重试或选择其他片源。"
        elif category == 'torrent_download_timeout':
            self.error_message = "获取种子文件超时，尚未开始视频缓冲；请重试或选择其他片源。"
        elif category == 'torrent_download_failed':
            self.error_message = "种子文件获取或校验失败，尚未开始视频缓冲；请刷新片源或重试。"
        elif category in {'torrserver_error', 'preload_error', 'startup_timeout'}:
            self.error_message = "该片源暂时无法取得数据，请选择其他片源或稍后重试。"
        elif category == 'source_identity_mismatch':
            self.error_message = "种子内容与所选片源不一致，已停止本次请求，请刷新片源。"
        elif category in {'cancelled', 'aborted'}:
            self.error_message = "本次播放请求已取消或中止，未自动切换片源。"
        try:
            terminal = json.loads(get_property("bobbi_cinema_terminal") or "{}")
            if terminal.get("session") == self.item_information.get("request_id"):
                if terminal.get("category") in {"target_unresolved", "invalid_binding", "selected_file_missing", "no_candidate"}:
                    self.error_message = "无法确定该片源中的目标集，未自动选择其他文件。"
                elif terminal.get('category') == 'fullscreen_denied':
                    self.error_message = '视频未能进入全屏，已停止本次播放，请重试。'
        except (ValueError, TypeError, AttributeError):
            pass
        self.close()

    def update_progress(self):
        if self.resolved or self.cancel_event.is_set():
            return
        try:
            progress = json.loads(get_property("bobbi_cinema_progress") or "{}")
            if progress.get("request_id") != self.item_information.get("request_id"):
                return
            labels = {"download": "正在下载并核对种子", "metadata": "正在解析片源", "buffering": "正在缓冲", "starting": "正在开始播放"}
            self.setProperty("loading_stage", labels.get(progress.get("phase"), "正在准备播放"))
        except (ValueError, TypeError, AttributeError):
            pass

    def resolve_source(self) -> Optional[Dict[str, Any]]:
        try:
            if self.cancel_event.is_set() or not self._owns_selection():
                return None
            kodilog("[CINEMA-HANDOFF] selected source resolution started "
                    + str(self.item_information.get("request_id", ""))[:8], level=xbmc.LOGINFO)
            is_pack = self.source.isPack or self.pack_select
            has_debrid = bool(self.source.debridType)

            if is_pack and has_debrid and (self.pack_select or not self._modeless):
                self.resolve_pack_source()
            else:
                self.resolve_single_source()

            if self.is_subtitle_download:
                self._download_subtitle()

            if self.local_subtitle_path and self.playback_info:
                existing_subtitles = self.playback_info.get("subtitles_path", [])
                if self.local_subtitle_path not in existing_subtitles:
                    existing_subtitles.append(self.local_subtitle_path)
                    self.playback_info["subtitles_path"] = existing_subtitles
                set_property("search_subtitles", "true")

            if not self.playback_info:
                raise Exception("Failed to resolve source")
            kodilog("[CINEMA-HANDOFF] selected source resolved; constructing player", level=xbmc.LOGINFO)

            if self.cancel_event.is_set() or not self._owns_selection():
                return None

            self.player = JacktookPLayer(
                on_started=self.handle_playback_started,
                on_error=self.handle_playback_error,
                cancel_event=self.cancel_event,
                on_progress=self.update_progress,
                on_handoff=self.handle_handoff_confirmed,
            )
            self.player.run(data=self.playback_info)
        except Exception as e:
            import traceback

            kodilog(f"Error in resolver window: {e}")
            kodilog(traceback.format_exc())
            self.error_message = "片源解析失败，请重试或选择其他片源。"
            if not self._modeless:
                notification(str(e), time=5000)
            if self.previous_window:
                self.previous_window.setProperty("instant_close", "true")
                self.previous_window.close()
            self.close()
        finally:
            # Player callbacks reference this window; release that cycle after run.
            if self.player is not None:
                self.resolution_answered = bool(self.player._resolution_answered)
                self.startup_failure_category = getattr(self.player, '_startup_failure_category', None)
                self.preparation_intent = getattr(self.player, '_cinema_prepare_intent', None)
            self.player = None

    def resolve_single_source(self) -> None:
        self.playback_info = self._ensure_playback_info(source=self.source)
        if self.playback_info:
            self._merge_item_information()
            self._cache_playback_info()

    def resolve_pack_source(self) -> None:
        self.pack_info = get_pack_info(
            debrid_type=self.source.debridType,
            info_hash=self.source.infoHash,
        )
        self.window = SourcePackSelect(
            "source_pack_select.xml",
            ADDON_PATH,
            source=self.source,
            pack_info=self.pack_info,
            item_information=self.item_information,
        )
        self.playback_info = self.window.doModal()
        if self.playback_info:
            self._merge_item_information()
            self._cache_playback_info()
        else:
            self.close_windows()

        del self.window

    def _merge_item_information(self) -> None:
        # Keep the display title already assembled by the selected-source
        # adapter when metadata has no usable replacement. This is not catalog
        # identity proof; preparation still validates its independent catalog.
        resolved_title = self.playback_info.get('title')
        self.playback_info.update(self.item_information)
        incoming_title = self.item_information.get('title')
        if ('title' in self.item_information
                and (not isinstance(incoming_title, str) or not incoming_title.strip())
                and isinstance(resolved_title, str) and resolved_title.strip()):
            self.playback_info['title'] = resolved_title

    def _cache_playback_info(self) -> None:
        playback_info = cast(Dict[str, Any], self.playback_info or {})
        if playback_info.get('transient_url'):
            return
        if get_setting("super_quick_play", False):
            kodilog("Super quick play enabled, caching playback info")
            key = ""
            if "ids" in playback_info:
                ids = cast(Dict[str, Any], playback_info["ids"] or {})
                key = str(ids.get("original_id") or ids.get("imdb_id") or ids.get("tmdb_id") or "")

            if key:
                tv_data = cast(Dict[str, Any], playback_info.get("tv_data", {}) or {})
                if tv_data and "season" in tv_data and "episode" in tv_data:
                    key += f"_{tv_data['season']}_{tv_data['episode']}"

            if key:
                cache.set(key, playback_info, timedelta(days=30))
                kodilog(f"Playback info cached with key: {key}")

    def _download_subtitle(self):
        try:
            subtitle_manager = SubtitleManager(self.playback_info, notification)
            subtitles_path = subtitle_manager.fetch_subtitles()
            if subtitles_path:
                set_property("search_subtitles", "true")
                if self.playback_info:
                    self.playback_info.update({"subtitles_path": subtitles_path})
            else:
                if subtitle_manager.last_fetch_status == "not_found":
                    kodilog("No subtitles found, continuing without subtitles")
                elif subtitle_manager.last_fetch_status == "not_selected":
                    kodilog("No subtitles selected, continuing without subtitles")
                else:
                    kodilog("Subtitle download skipped, continuing without subtitles")
        except Exception as e:
            kodilog(f"Subtitle download failed, continuing without subtitles: {e}")

    def _update_window_properties(self, source: TorrentStream) -> None:
        self.setProperty("enable_busy_spinner", "true")
        self.setProperty("loading_stage", "正在解析片源")


class SourceException(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, error_content: Any = None):
        self.message = message
        self.status_code = status_code
        self.error_content = error_content
        details = f"{self.message}"
        if self.status_code is not None:
            details += f" (Status code: {self.status_code})"
        if self.error_content is not None:
            details += f"\nError content: {self.error_content}"
        super().__init__(details)
        notification(details)
