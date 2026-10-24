from datetime import timedelta
from typing import Any, Dict, Optional, cast
from threading import Event
from uuid import uuid4
from time import monotonic
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
        self.media_started = False
        self.presentation_confirmed = False
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
            from lib.cinema.playback_request import call, context, read_snapshot, SelectionChanged
            try:
                self._window_context = context(read_snapshot(),
                    self.item_information.get('request_id'), self.item_information.get('_selection_context'))
                if not call(dict(self._window_context, operation='register_window',
                                 token=self._window_token, role='loading'))['registered']:
                    return False
                self.show()
                self.resolve_source()
            except SelectionChanged:
                return False
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                kodilog('[CINEMA-HANDOFF] LOADING_CONTROL_UNAVAILABLE ' + type(error).__name__, level=xbmc.LOGWARNING)
                self.error_message = '播放控制暂时不可用，请返回选源重试。'
                notification(self.error_message, time=5000)
            finally:
                self.close()
        else:
            super().doModal()
        return self.resolved

    def onInit(self) -> None:
        super().onInit()
        self._capture_loading_dialog()
        if not self._modeless:
            self.resolve_source()

    def _capture_loading_dialog(self):
        # Kodi 21.3 WindowIDs.h reserves exactly 13000..13099 for Python
        # windows. Topmost may instead be its busy dialog or a user's modal;
        # neither identifies this WindowXMLDialog. Require one visible token
        # match in the official bounded namespace, including beneath overlays.
        self._capture_reason = 'LOADING_WINDOW_NOT_IDENTIFIED'
        matches = []
        for dialog_id in range(13000, 13100):
            # Window(existing_id) can throw an untranslatable native exception
            # for an empty Python slot. Read-only GUI labels safely return empty
            # for missing/retired windows; do not construct wrappers while scanning.
            if not xbmc.getCondVisibility('Window.IsVisible({})'.format(dialog_id)):
                continue
            if xbmc.getInfoLabel('Window({}).Property(AM6B.ResolverToken)'.format(dialog_id)) == self._window_token:
                matches.append(dialog_id)
                if len(matches) > 1:
                    self._capture_reason = 'LOADING_WINDOW_AMBIGUOUS'
                    return False
        if len(matches) != 1:
            return False
        self._dialog_id = matches[0]
        return True

    def _handoff_rejected(self, reason):
        # Fixed internal reason codes only, never exception text or credentials.
        kodilog('[CINEMA-HANDOFF] request={} rejected={}'.format(
            str(self.item_information.get('request_id', ''))[:8], reason), level=xbmc.LOGWARNING)
        return False

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
        from lib.cinema.playback_request import call, context, owned_state
        try:
            deadline = getattr(self, '_handoff_read_deadline', None)
            if deadline is None:
                state = owned_state(self.item_information.get('request_id'))
            else:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return self._handoff_rejected('PRESENTATION_BUDGET_EXHAUSTED')
                state = call({'operation': 'snapshot'}, timeout=min(.3, remaining))
                context(state, self.item_information.get('request_id'))
                if monotonic() >= deadline:
                    return self._handoff_rejected('PRESENTATION_BUDGET_EXHAUSTED')
            context(state, self.item_information.get('request_id'), getattr(self, '_window_context', None))
            return True
        except OSError as error:
            if not getattr(self, 'media_started', False) and not self.resolved and not self.cancel_event.is_set():
                self.error_message = '播放控制暂时不可用，请返回选源重试。'
            return self._handoff_rejected('SELECTION_CHECK_' + type(error).__name__.upper())
        except (RuntimeError, ValueError) as error:
            return self._handoff_rejected('SELECTION_CHECK_' + type(error).__name__.upper())

    def close_windows(self):
        try:
            if self.previous_window:
                self.previous_window.setProperty("instant_close", "true")
                self.previous_window.close()
        finally:
            # The previous presenter may already have retired. Its exception
            # must not prevent this resolver's own close from being submitted.
            self.close()
            self._loading_close_issued = True

    def handle_playback_started(self, deadline=None):
        def remaining():
            return .3 if deadline is None else min(.3, deadline - monotonic())
        def owned():
            if remaining() <= 0:
                return False
            self._handoff_read_deadline = deadline
            try:
                result = self._owns_selection()
                return result and remaining() > 0
            finally:
                self._handoff_read_deadline = None  # Back/Stop checks have their own budget.
        def command(message):
            budget = remaining()
            if budget <= 0:
                raise TimeoutError('PRESENTATION_BUDGET_EXHAUSTED')
            from lib.cinema.playback_request import call
            result = call(message, timeout=budget) if deadline is not None else call(message)
            if remaining() <= 0:
                raise TimeoutError('PRESENTATION_BUDGET_EXHAUSTED')
            return result
        if self.cancel_event.is_set():
            return self._handoff_rejected('REQUEST_CANCELLED')
        # The caller already observed this request's AV_STARTED. Presentation
        # IPC can be unknown without reopening a source that is already playing.
        self.media_started = self.resolved = True
        if getattr(self, '_loading_lease_released', False):
            return True
        if not owned():
            return self._handoff_rejected('SELECTION_NOT_OWNED')
        if not self._modeless:
            self.close_windows()
            return True
        elif self._window_context:
            if not getattr(self, '_loading_close_tracked', False):
                if not self._capture_loading_dialog():
                    return self._handoff_rejected(self._capture_reason)
                # Track the actual token-bearing window before its asynchronous
                # close. A lost track ACK can safely repeat this same receipt.
                try:
                    tracked = command(dict(self._window_context, operation='begin_window_close',
                                           token=self._window_token, dialog_id=self._dialog_id))
                    if tracked.get('tracked') is not True:
                        return self._handoff_rejected('OWNED_LOADING_TRACK_REJECTED')
                    self._loading_close_tracked = True
                except (OSError, RuntimeError, ValueError) as error:
                    return self._handoff_rejected('LOADING_TRACK_' + type(error).__name__.upper())
        else:
            # Do not release the loading lease or request fullscreen when the
            # visible window cannot be tied to this request's registered token.
            return self._handoff_rejected('LOADING_WINDOW_CONTEXT_MISSING')
        if not getattr(self, '_loading_close_issued', False):
            if remaining() <= 0:
                return self._handoff_rejected('PRESENTATION_BUDGET_EXHAUSTED')
            self._loading_close_attempted = True
            self.close_windows()
            self._loading_close_issued = True  # Returned only after the own close submission.
        if self._modeless:
            # close() queues GUI work. Give only our closing dialog a bounded
            # handoff window; never close a different modal dialog globally.
            for _ in range(20):
                if not owned() or self.cancel_event.is_set():
                    return self._handoff_rejected('RETIREMENT_SELECTION_LOST')
                if not self._dialog_id or not xbmc.getCondVisibility("Window.IsVisible({})".format(self._dialog_id)):
                    break
                if remaining() <= 0:
                    return self._handoff_rejected('PRESENTATION_BUDGET_EXHAUSTED')
                xbmc.sleep(min(25, max(1, int(remaining() * 1000))))
            else:
                return self._handoff_rejected('OWNED_LOADING_RETIREMENT_TIMEOUT')
            if not self._window_context or not command(dict(self._window_context,
                    operation='close_window', token=self._window_token))['closed']:
                return self._handoff_rejected('LOADING_LEASE_RELEASE_REJECTED')
            self._loading_lease_released = True
            # The player requests the conditional native handoff after this
            # callback; no unscoped ActivateWindow is issued from a resolver.
        return True

    def handle_handoff_confirmed(self):
        if (not self.cancel_event.is_set() and self._owns_selection()
                and get_property('bobbi_active_player_session') == self.item_information.get('request_id')
                and self.player is not None and self.player._handoff_confirmed):
            # The player already observed fullscreen. A subsequent user Back
            # must not revoke that completed handoff or cause another activation.
            self.presentation_confirmed = True
            self.resolved = True

    def handle_presentation_deferred(self):
        """Leave media running and retire only this token-bearing presenter.

        This fallback gives no fullscreen rights and does not release a lease
        without its authority receipt. A new/reused/ambiguous window is never
        closed, nor is the previous window or any other modal.
        """
        if (not getattr(self, 'media_started', False) or not self._modeless
                or getattr(self, '_loading_close_issued', False) or self.cancel_event.is_set()
                or not self._window_context or not self._capture_loading_dialog()):
            return False
        self._loading_close_attempted = True
        self.close()
        self._loading_close_issued = True
        return True

    def handle_playback_error(self):
        if getattr(self, 'media_started', False) or getattr(self, 'resolved', False):
            # A completed handoff cannot become a new source-selection modal
            # because a later subtitle/tracking callback failed.
            kodilog('[CINEMA-HANDOFF] post-handoff error does not reopen selection', level=xbmc.LOGWARNING)
            return
        from bobbi_core.share_failure import presentation_receipt, read_failure, message, PERMANENT
        if self.cancel_event.is_set() or getattr(self, 'user_cancelled', False):
            self.close()
            return
        receipt = presentation_receipt(self.player, getattr(self, '_window_context', None),
                                       self.item_information.get('request_id'))
        if not self._owns_selection() and receipt is None:
            self.close()
            return
        self.resolved = False
        self.setProperty("resolving", "false")
        self.error_message = "该片源暂时无法播放，请选择其他片源或重试。"
        category = getattr(self.player, '_startup_failure_category', None)
        if category == 'prepared_ready':
            self.error_message = ''
            self.setProperty('loading_stage', '同片源 115 已就绪，正在接续')
        elif category in {'target_unresolved', 'invalid_binding', 'selected_file_missing', 'no_candidate'}:
            self.error_message = "无法确认所选集数，请换一个片源。"
        elif category == 'metadata_timeout':
            self.error_message = "读取种子文件列表超时，请重试或换源。"
        elif category == 'buffer_timeout':
            self.error_message = "视频开头缓冲超时，请重试或换源。"
        elif category == 'torrent_download_timeout':
            self.error_message = "下载种子超时，请重试或换源。"
        elif category == 'torrent_download_failed':
            self.error_message = "未取得有效种子，请刷新片源后重试。"
        elif category in {'torrserver_error', 'preload_error', 'startup_timeout'}:
            self.error_message = "该片源暂时无法取得数据，请选择其他片源或稍后重试。"
        elif category == 'source_identity_mismatch':
            self.error_message = "种子与所选片源不符，已停止播放准备。请刷新片源。"
        elif category in {'cancelled', 'aborted'}:
            self.error_message = "播放准备已中止，请重新选源。"
        try:
            terminal = json.loads(get_property("bobbi_cinema_terminal") or "{}")
            if terminal.get("session") == self.item_information.get("request_id"):
                if terminal.get("category") in {"target_unresolved", "invalid_binding", "selected_file_missing", "no_candidate"}:
                    self.error_message = "无法确认所选集数，请换一个片源。"
                elif terminal.get('category') == 'fullscreen_denied':
                    self.error_message = '视频未能进入全屏，已停止本次播放，请重试。'
        except (ValueError, TypeError, AttributeError):
            pass
        failure = read_failure(getattr(self, 'source', None), self.item_information, receipt)
        # The diagnostic IPC may overlap a new selection/account intent. Read
        # the presentation receipt again; it never restores control ownership.
        still_current = (presentation_receipt(self.player, getattr(self, '_window_context', None),
                         self.item_information.get('request_id')) == receipt
                         if receipt is not None else self._owns_selection())
        if not still_current or self.cancel_event.is_set() or getattr(self, 'user_cancelled', False):
            self.error_message = ''
            self.close()
            return
        if failure is not None:
            self.error_message = message(failure['code'])
            self.share_failure = failure
            if failure['code'] in PERMANENT:
                self.source.verifiedShareFile = False
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
                on_presentation_deferred=self.handle_presentation_deferred,
            )
            if self._modeless:
                self.playback_info['_selection_context'] = self._window_context
            self.player.run(data=self.playback_info)
            if getattr(self.player, '_preav_control_error', ''):
                self.error_message = self.player._preav_control_error
        except Exception as e:
            from bobbi_catalog.api import ShareError
            from bobbi_core.share_failure import failure_value, message, PERMANENT
            # No arbitrary provider exception text or signed URL in logs/UI.
            kodilog('Error in resolver window: ' + type(e).__name__)
            if self.player is not None and getattr(self.player, '_startup_failure_receipt', None):
                # A later callback exception cannot erase the exact native
                # failure; the handler revalidates its presentation authority.
                self.handle_playback_error()
            else:
                self.error_message = ''
                if not self.cancel_event.is_set() and not getattr(self, 'user_cancelled', False) and self._owns_selection():
                    self.error_message = "片源解析失败，请重试或选择其他片源。"
                    if isinstance(e, ShareError):
                        self.share_failure = failure_value(e)
                        self.error_message = message(e.code)
                        if e.code in PERMANENT:
                            self.source.verifiedShareFile = False
            if not self._modeless and self.error_message:
                notification(self.error_message, time=5000)
            self.close()
        finally:
            # Player callbacks reference this window; release that cycle after run.
            if self.player is not None:
                self.resolution_answered = bool(self.player._resolution_answered)
                self.startup_failure_category = getattr(self.player, '_startup_failure_category', None)
                self.preparation_intent = getattr(self.player, '_cinema_prepare_intent', None)
                if isinstance(self.playback_info, dict):
                    self.playback_info['_account'] = getattr(self.player, 'data', {}).get('_account')
                if (self.startup_failure_category == 'prepared_ready' and not self.preparation_intent
                        and isinstance(self.playback_info, dict)):
                    # Early-ready may finish before the parent's first 100 ms
                    # preparation tick. This is a file hint, not playback proof.
                    from lib.cinema.preparation_client import source_intent
                    try:
                        self.preparation_intent = source_intent(self.playback_info,
                            json.loads(get_property('bobbi_cinema_preparation_target') or '{}'))
                    except (ValueError, TypeError):
                        pass
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
