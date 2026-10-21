from datetime import date
from copy import deepcopy
from json import dumps as json_dumps
from json import loads
from threading import Event, Thread
from time import monotonic
from typing import Optional
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import hashlib
import re

import xbmc
from xbmc import getCondVisibility as get_visibility
from xbmcgui import Dialog, ListItem
from xbmcplugin import setResolvedUrl

from lib.api.nuvio import NuvioClient, is_nuvio_progress_sync_enabled
from lib.api.simkl import SimklClient, is_simkl_scrobbling_enabled
from lib.api.trakt.trakt import TraktAPI, TraktLists, TraktScrobble
from lib.api.trakt.trakt_utils import is_trakt_auth
from lib.clients.subtitle.utils import get_language_code
from lib.clients.tmdb.utils.utils import get_movie_keywords, tmdb_get
from lib.db.cached import cache
from lib.utils.general.utils import (
    make_listing,
    set_watched_file,
)
from lib.utils.kodi.settings import subtitle_automation_enabled
from lib.utils.kodi.utils import (
    ADDON_HANDLE,
    PLAYLIST,
    action_url_run,
    build_url,
    clear_property,
    close_all_dialog,
    close_busy_dialog,
    execute_builtin,
    get_property,
    get_setting,
    kodilog,
    notification,
    set_property,
    sleep,
    translation,
)
from lib.utils.player.utils import (
    autoscrape_next_episode,
    build_elementum_pack_next_playback,
    get_autoscrape_cache_key,
    get_autoscrape_results_cache_key,
)

AUTOPLAY_CONTEXT_NEXT_EPISODE = 1
ACTIVE_PLAYER_SESSION_PROPERTY = "bobbi_active_player_session"
PLAYNEXT_ACTION_PROPERTY = "bobbi_next_dialog_action"
PLAYBACK_START_TIMEOUT_SECONDS = 90.0
# Provisional local window-observation budget, separate from AV startup and
# resolver-owned dialog close. Device timing must validate this before release.
HANDOFF_CONFIRMATION_TIMEOUT_SECONDS = 1.0
HANDOFF_CONFIRMATION_POLL_MS = 50
# A stopped decoder can precede the independently relayed Kodi OnStop event.
# Retain this request while reconciling it, never infer EOF or revive it later.
TERMINAL_RECONCILIATION_SECONDS = 3.0
total_time_errors = ("0.0", "", 0.0, None)
video_fullscreen_check = "Window.IsActive(fullscreenvideo)"


class JacktookPLayer(xbmc.Player):
    _nextep_queue: list = []

    def __init__(self, on_started=None, on_error=None, cancel_event=None, on_progress=None, on_handoff=None):
        xbmc.Player.__init__(self)
        self.url = None
        self.playback_percent = 0.0
        self.playing_filename = ""
        self.media_marked = False
        self.cancel_all_playback = False
        self.kodi_monitor = xbmc.Monitor()
        self.next_dialog = get_setting("playnext_dialog_enabled")
        self.playing_next_time = int(get_setting("playnext_time", 50))
        self.PLAYLIST = PLAYLIST
        self.data = {}
        self.notification = notification
        self.lang_code = "en"
        self.subtitles_found = False
        self.on_started = on_started
        self.on_error = on_error
        self.on_progress = on_progress
        self.on_handoff = on_handoff
        self._handoff_confirmed = False
        self._provided_cancel_event = cancel_event
        self._start_notified = False
        self._resolution_answered = False
        self._is_trakt_scrobble_active = False
        self._is_simkl_scrobble_active = False
        self._playback_was_paused = False
        self._yamtrack_stop_attempted = False
        self._simkl_resume_applied = False
        self._simkl_resume_playback_observed = False
        self._simkl_playback_delete_attempted = False
        self._trakt_resume_applied = False
        self._trakt_resume_playback_observed = False
        self._trakt_playback_delete_attempted = False
        self.playback_session_id = ""
        self._was_superseded = False
        self._cinema_subtitle_attempts = 0
        self._cinema_subtitle_done = False
        self._cinema_subtitle_due = 0.0
        self._cinema_subtitle_manual = False
        self._cinema_subtitle_observed = None
        self._monitor_wake = Event()

    def _activate_playback_session(self):
        request_id = self.data.get("request_id", "")
        self.playback_session_id = (request_id if self.data.get("selection_policy") == "exact"
                                   and isinstance(request_id, str)
                                   and re.fullmatch(r"[0-9a-f]{32}", request_id) else uuid4().hex)
        self.data["playback_session_id"] = self.playback_session_id
        exact = self.data.get("selection_policy") == "exact"
        if exact:
            from lib.cinema.playback_ipc import call
            from lib.cinema.playback_request import context, data_identity
            try:
                snapshot = call({'operation': 'snapshot'})
                if self.data.get('_parent_request_id'):
                    parent = context(snapshot, self.data['_parent_request_id'])
                    snapshot = call(dict(parent, operation='reserve_child',
                        token=self.data.get('_continuation_token'), child_request_id=self.playback_session_id,
                        selection_identity=data_identity(self.data)))
                self._owner_context = context(snapshot, self.playback_session_id)
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                kodilog('[CINEMA-NEXT] SESSION_RESERVATION_REJECTED ' + type(error).__name__, level=xbmc.LOGWARNING)
                self._was_superseded = True
                return False
        if exact:
            # Compatibility labels only. The service above, not these strings,
            # has already accepted this exact request or one-use continuation.
            set_property(ACTIVE_PLAYER_SESSION_PROPERTY, self.playback_session_id)
            set_property("bobbi_cinema_selection", self.playback_session_id)
            return True
        else:
            set_property(ACTIVE_PLAYER_SESSION_PROPERTY, self.playback_session_id)
        clear_property(PLAYNEXT_ACTION_PROPERTY)
        clear_property('bobbi_cinema_terminal')
        kodilog(f"[PLAYER] Activated playback session {self.playback_session_id[:8]}")
        return True

    def _owns_playback_session(self) -> bool:
        if getattr(self, 'data', {}).get('selection_policy') == 'exact':
            from lib.cinema.playback_request import owned_state
            try:
                snapshot = owned_state(self.playback_session_id)
                original = getattr(self, '_owner_context', None)
                if original and any(snapshot.get(key) != original.get(key) for key in ('boot_id', 'epoch')):
                    return False
                observed = snapshot.get('observed') or {}
                pinned = getattr(self, '_native_instance', None)
                if pinned and observed and observed.get('native_instance') != pinned:
                    return False
                return True
            except OSError as error:
                kodilog('[CINEMA-OWNER] SNAPSHOT_UNAVAILABLE ' + type(error).__name__, level=xbmc.LOGWARNING)
                return False
            except (ValueError, RuntimeError):
                return False
        return bool(self.playback_session_id) and (
            get_property(ACTIVE_PLAYER_SESSION_PROPERTY) == self.playback_session_id
        )

    def _consume_next_dialog_action(self) -> bool:
        raw_action = get_property(PLAYNEXT_ACTION_PROPERTY)
        if not raw_action:
            return False
        try:
            payload = loads(raw_action)
        except (TypeError, ValueError):
            kodilog(f"[PLAYNEXT] Ignoring unscoped action payload: {raw_action!r}")
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("action") != "next_episode":
            return False
        if payload.get("session_id") != self.playback_session_id:
            return False
        clear_property(PLAYNEXT_ACTION_PROPERTY)
        return True

    def _release_playback_session(self):
        if not self._owns_playback_session():
            return
        clear_property(PLAYNEXT_ACTION_PROPERTY)
        clear_property(ACTIVE_PLAYER_SESSION_PROPERTY)

    def run(self, data=None):
        if data is None:
            data = {}
        data = dict(data)
        self._bobi_start_over = bool(data.pop('_bobi_start_over', False))
        self._startup_failed_for_reselect = False
        self.set_constants(data)
        data = self.data
        if data.get('selection_policy') == 'exact':
            try:
                from lib.cinema.preparation_client import capture_account
                capture_account(data, allow_capture=not (
                    data.get('_parent_request_id') or data.get('playnext_context') or data.get('autoplay')))
            except (OSError, ValueError, TypeError, RuntimeError):
                # Cloud side work may be unavailable; independent BT/public
                # HTTP playback still owns its ordinary native session.
                kodilog('[CINEMA-PREPARE] ACCOUNT_CAPTURE_UNAVAILABLE', level=xbmc.LOGWARNING)
        if self._activate_playback_session() is False:
            return
        self._cinema_phase('SESSION_ACTIVATED')
        # Subtitle presentation belongs to the resident AV receipt observer.
        # PRE_AV failure/cancellation must not create an owner with no observer.
        self.clear_playback_properties()
        if not self._is_trakt_tracking_excluded():
            self.add_external_trakt_scrolling()
        self._cinema_history_pending = data.get('selection_policy') == 'exact'
        if not self._cinema_history_pending:
            self.mark_watched(data)

        close_busy_dialog()
        kodilog(
            f"[PLAYER] run() started: url_type={'plugin' if self.url.startswith('plugin://') else 'direct'}, "
            f"mode={data.get('mode')}, url_start={self.url[:80]}"
        )

        try:
            if self.url.startswith('plugin://plugin.video.jacktorr/'):
                raise RuntimeError('旧 BT 解析地址已失效，请返回选源窗口重新选择；未启动旧播放控制。')
            if data.get('_catalog_next'):
                from lib.utils.player.direct_continuity import resolve_direct
                self.url = data['url'] = resolve_direct(data, lambda: self._cinema_cancel.is_set()
                    or not self._owns_playback_session())
            if (data.get('selection_policy') == 'exact'
                    and (data.get('direct_source') or {}).get('provider') == 'mdsub'):
                from bobbi_core.direct_cloud_client import entry as direct_entry, resolve as resolve_direct_cloud
                known = direct_entry(data)
                if not known or known['state'] != 'ready':
                    self.start_direct_preparation()
                if known and known['state'] == 'ready':
                    cloud = resolve_direct_cloud(data, lambda: self._cinema_cancel.is_set() or not self._owns_playback_session())
                    if not cloud:
                        raise RuntimeError('115 文件当前不可读或身份发生变化，请重新选源')
                    self.url = data['url'] = cloud['path']
                    data.update(direct_cloud_key=cloud['key'], size=cloud['bytes'], indexer='115 · CD2 · 漫迪')
                    self._cinema_phase('DIRECT_CLOUD_VERIFIED')
                elif data.get('_catalog_next') or data.get('direct_cloud_required'):
                    raise RuntimeError('同版本正在准备到 115，尚未验证就绪；请稍后重试')
            if data.get('prepared_resource_id'):
                self._cinema_phase('PREPARED_VERIFY_BEGIN')
                from lib.clients.bobi_library import load_prepared_index, local_path
                from lib.cinema.preparation_client import resolve_entry
                snapshot = load_prepared_index()
                entries = [entry for title in snapshot['titles'] for entry in title['sources']
                           if entry['key'] == data['prepared_resource_id']]
                if len(entries) != 1 or not resolve_entry(data, snapshot, entries[0], self._cinema_cancel.is_set):
                    raise RuntimeError('云端身份核验失败，未播放未知文件')
                self.url = data['url'] = local_path(snapshot['mount_root'], entries[0]['path'])
                data['source_title'] = entries[0]['title']
                data['video_context'] = entries[0].get('video_context')
                self._cinema_phase('PREPARED_VERIFY_END')
            self.list_item = make_listing(data)
            self._cinema_phase('LIST_ITEM_READY')
            if data.get("selection_policy") != "exact":
                self.PLAYLIST.add(self.url, self.list_item)
            self.play_video(self.list_item)
        except Exception as e:
            self.run_error(e)

        if self._was_superseded:
            kodilog("[PLAYER] run() superseded; skipping PlayNext queue drain")
            return

        had_nextep = False if data.get('_queue_drained_by_parent') else self._drain_nextep_queue()
        kodilog(f"[PLAYER] _drain_nextep_queue returned had_nextep={had_nextep}")
        kodilog("[PLAYER] run() completed")

    def _cinema_phase(self, phase):
        """Sparse exact-session timing only; no URLs, credentials or polling log."""
        if getattr(self, 'data', {}).get('selection_policy') == 'exact':
            kodilog('[CINEMA-PHASE] ' + json_dumps(dict(request=self.playback_session_id,
                    phase=phase, monotonic=round(monotonic(), 6))), level=xbmc.LOGINFO)

    def _drain_nextep_queue(self) -> bool:
        """Process queued next episodes after current video has stopped"""
        from lib.utils.kodi.settings import auto_play_enabled as _auto_play_enabled

        if not JacktookPLayer._nextep_queue:
            return False

        while JacktookPLayer._nextep_queue:
            entry = JacktookPLayer._nextep_queue.pop(0)
            data = entry.get("data", {})
            results = entry.get("results")
            kodilog(
                f"[PLAYNEXT] _drain_nextep_queue: "
                f"title={data.get('title', '')}, "
                f"has_results={results is not None}, "
                f"queue_remaining={len(JacktookPLayer._nextep_queue)}"
            )

            if _auto_play_enabled() or results is None:
                # This is an internal handoff after the previous plugin action
                # has already finished resolving. setResolvedUrl() no longer has
                # a pending Kodi request to answer, so mark the new playback for
                # an explicit Player.play() call.
                handoff_data = dict(data)
                handoff_data["direct_playback_handoff"] = True
                handoff_data['_queue_drained_by_parent'] = True
                self._cinema_phase('NEXT_CONSTRUCT_BEGIN')
                player = JacktookPLayer()
                self._cinema_phase('NEXT_CONSTRUCT_END')
                player.run(data=handoff_data)
                del player
            else:
                # Manual: show source select (safe context — no video playing)
                from lib.search import show_source_select as _show_source_select

                resolved = _show_source_select(
                    results,
                    mode=data.get("mode", "tv"),
                    ids=data.get("ids", {}),
                    tv_data=data.get("tv_data", {}),
                    query=data.get("query", ""),
                    media_type=data.get("media_type", ""),
                    rescrape=False,
                    direct=False,
                    autoplay_context=str(AUTOPLAY_CONTEXT_NEXT_EPISODE),
                )
                kodilog(f"[PLAYNEXT] source_select returned resolved={resolved}")
                if not resolved:
                    kodilog("[PLAYNEXT] source_select cancelled; cleanup only")
                    close_busy_dialog()
                    close_all_dialog()
                    clear_property("bobbi_next_dialog_action")
                    try:
                        self.PLAYLIST.clear()
                    except Exception as e:
                        kodilog(f"[PLAYNEXT] failed clearing playlist after cancel: {e}")

        return True

    def play_video(self, list_item):
        close_busy_dialog()

        self._cinema_phase('VOLUME_GATE_BEGIN')
        if not self._check_volume():
            self.cancel_playback()
            return
        self._cinema_phase('VOLUME_GATE_END')

        try:
            self._cinema_phase('PRE_AV_TRACKING_BEGIN')
            self._handle_trakt_scrobble(list_item)
            self._handle_simkl_scrobble()
            self._cinema_phase('PRE_AV_TRACKING_END')
            self._cinema_phase('PRE_AV_SUBTITLES_BEGIN')
            self.handle_subtitles(list_item)
            self._cinema_phase('PRE_AV_SUBTITLES_END')
            original_audio_hint = None
            if self.data.get('selection_policy') == 'exact':
                try:
                    from time import time
                    from lib.clients.tmdb.original_audio import cached_hint
                    from bobbi_core.original_audio import handoff_url
                    original_audio_hint = cached_hint(self.data, self.playback_session_id)
                    self.url = handoff_url(self.url, original_audio_hint, self.playback_session_id, time())
                except Exception:
                    original_audio_hint = None  # Optional preference, no video admission rights.
            # A resolved item always needs an explicit path. Previously adding
            # it to the global playlist incidentally supplied plugin/native
            # paths; exact requests intentionally do not mutate that playlist.
            list_item.setPath(self.url)
            from lib.cinema.frontend_contract import progress
            # One-shot position for this work; never persist it or carry it to
            # the next episode's playback payload.
            resume_percent = progress({'progress': self.data.pop('_bobi_resume_percent', None)})
            if getattr(self, '_bobi_start_over', False):
                list_item.setProperty('StartOffset', '0')
                list_item.setProperty('StartPercent', '0')
                list_item.getVideoInfoTag().setResumePoint(0, 0)
            elif 0 < resume_percent < 100:
                list_item.setProperty('StartPercent', str(resume_percent))
            if self.data.get('selection_policy') == 'exact':
                list_item.setProperty('bobitv.request_id', self.playback_session_id)
                list_item.setProperty('no-ext-subs-scan', 'true')
                if not self.url.startswith('plugin://plugin.video.bobbi.torrent/'):
                    from lib.cinema.playback_request import owned_state, bind_and_claim, digest
                    selected = owned_state(self.playback_session_id)['desired']['selection_identity']
                    identity = selected + '|transport:' + digest(self.url)
                    self._cinema_phase('BIND_AND_CLAIM_BEGIN')
                    self._owner_context = bind_and_claim(
                        self.playback_session_id, identity, self.url, self._cinema_cancel.is_set,
                        'player_play' if self.data.get('direct_playback_handoff') else 'resolved_url')
                    self._cinema_phase('BIND_AND_CLAIM_END')
                    # Only the already cached, exact ASS font working set is
                    # installed here. Extraction/download stays on the idle lane.
                    from lib.cinema.preparation_client import prepare_fonts
                    self._cinema_phase('FONT_PREFLIGHT_BEGIN')
                    font_result = prepare_fonts(self.data, self._owner_context, self._cinema_cancel.is_set)
                    self._cinema_phase('FONT_PREFLIGHT_END')
                    kodilog('[CINEMA-FONTS] request={} state={} reason={}'.format(
                        self.playback_session_id, font_result.get('state'), font_result.get('reason', '')))
                    list_item.setProperty('bobitv.file_identity', identity)
                    try:
                        from time import time
                        from bobbi_core.original_audio import attach
                        attach(list_item, original_audio_hint, self._owner_context, self.url, time())
                    except Exception:
                        pass  # Never fail an accepted video open for an audio hint.
            if self.data.get("direct_playback_handoff"):
                # The original plugin resolution has already completed. Start
                # the queued external-plugin URL explicitly instead of trying
                # to resolve a stale addon handle.
                kodilog("[PLAYER] play_video: calling Player.play for internal PlayNext handoff")
                self._resolution_answered = True
                self._cinema_phase('PLAY_ISSUED')
                self.play(self.url, list_item)
            else:
                # Normal plugin entry point: answer Kodi's pending resolution.
                # Calling Player.play() here as well would open the stream twice.
                self._resolution_answered = True
                self._cinema_phase('RESOLUTION_ISSUED')
                setResolvedUrl(ADDON_HANDLE, True, list_item)
                kodilog("[PLAYER] play_video: calling setResolvedUrl only", level=xbmc.LOGINFO)
            self.monitor()
            kodilog("[PLAYER] play_video: monitor() returned")
        except Exception as e:
            kodilog(f"Error during play_video: {e}")
            self.run_error(e)

    def _check_volume(self):
        try:
            if not get_setting("volume_check_enabled") or get_visibility("Player.Muted"):
                return True

            threshold = int(get_setting("volume_check_threshold", 50))

            request = {
                "jsonrpc": "2.0",
                "method": "Application.GetProperties",
                "params": {"properties": ["volume"]},
                "id": 1,
            }
            json_query = xbmc.executeJSONRPC(json_dumps(request))
            response = loads(json_query)

            volume = response.get("result", {}).get("volume", 0)
            if volume > threshold:
                execute_builtin(f"SetVolume({threshold})")
                notification(
                    translation(90221) % threshold,
                    heading=translation(90220),
                    time=3000,
                )

            return True
        except Exception as e:
            kodilog(f"Error checking volume: {e}")
            return True

    def _handle_trakt_scrobble(self, list_item):
        if self._is_trakt_tracking_excluded():
            return
        if is_trakt_auth() and get_setting("trakt_scrobbling_enabled") and self.data.get("ids"):
            try:
                last_position = TraktAPI().scrobble.trakt_get_last_tracked_position(self.data)
            except Exception as e:
                self._log_trakt_playback_failure("resume lookup", e)
                last_position = 0
            if last_position > 0 and not getattr(self, '_bobi_start_over', False):
                list_item.setProperty("StartPercent", str(last_position))
                self.playback_started_properly = True
            try:
                TraktAPI().scrobble.trakt_start_scrobble(self.data)
                self._is_trakt_scrobble_active = True
            except Exception as e:
                self._log_trakt_playback_failure("start scrobble", e)

    def _is_trakt_scrobble_enabled(self):
        return (
            not self._is_trakt_tracking_excluded()
            and self._is_trakt_scrobble_active
            and is_trakt_auth()
            and get_setting("trakt_scrobbling_enabled")
        )

    def _handle_simkl_scrobble(self):
        try:
            if self._is_simkl_tracking_excluded() or not is_simkl_scrobbling_enabled():
                return
            self._is_simkl_scrobble_active = self._queue_simkl_scrobble("start")
        except Exception as error:
            self._is_simkl_scrobble_active = False
            kodilog(f"[SIMKL] start setup failed; continuing playback ({type(error).__name__})")

    def _is_simkl_scrobble_enabled(self):
        try:
            return (
                getattr(self, "_is_simkl_scrobble_active", False)
                and not self._is_simkl_tracking_excluded()
                and is_simkl_scrobbling_enabled()
            )
        except Exception as error:
            kodilog(f"[SIMKL] state check failed; continuing playback ({type(error).__name__})")
            return False

    def _queue_simkl_scrobble(self, action):
        try:
            data = {
                "mode": self.data.get("mode"),
                "ids": dict(self.data.get("ids") or {}),
                "tv_data": dict(self.data.get("tv_data") or {}),
                "progress": self.data.get("progress", 0),
            }
            thread = Thread(target=self._send_simkl_scrobble, args=(action, data))
            thread.daemon = True
            thread.start()
            return True
        except Exception as error:
            kodilog(f"[SIMKL] {action} queue failed; continuing playback ({type(error).__name__})")
            return False

    @staticmethod
    def _send_simkl_scrobble(action, data):
        try:
            SimklClient().scrobble(action, data)
        except Exception as error:
            kodilog(f"[SIMKL] {action} failed; continuing playback ({type(error).__name__})")

    def handle_trakt_pause_resume(self):
        is_paused = bool(get_visibility("Player.Paused"))
        if is_paused and not self._playback_was_paused:
            if self._is_trakt_scrobble_enabled():
                try:
                    TraktAPI().scrobble.trakt_pause_scrobble(self.data)
                except Exception as e:
                    self._log_trakt_playback_failure("pause scrobble", e)
            if self._is_simkl_scrobble_enabled():
                self._queue_simkl_scrobble("pause")
        elif self._playback_was_paused and not is_paused:
            if self._is_trakt_scrobble_enabled():
                try:
                    TraktAPI().scrobble.trakt_start_scrobble(self.data)
                except Exception as e:
                    self._log_trakt_playback_failure("resume scrobble", e)
            if self._is_simkl_scrobble_enabled():
                self._queue_simkl_scrobble("start")

        self._playback_was_paused = is_paused

    def _startup_timeout_seconds(self):
        if (self.data.get('selection_policy') == 'exact' and self.data.get('is_torrent')
                and urlsplit(self.url or '').netloc == 'plugin.video.bobbi.torrent'):
            from bobbi_core.torrent_startup import budgets
            from bobbi_torrent.backend import load_config
            settings = load_config()
            return budgets(settings['metadata_seconds'], settings['buffering_seconds'])['total']
        return PLAYBACK_START_TIMEOUT_SECONDS

    def _wait_for_video_start(self):
        """Wait for this session only; failed child resolvers must not spin forever."""
        deadline = monotonic() + self._startup_timeout_seconds()
        while True:
            if not self._owns_playback_session():
                if self.data.get('selection_policy') == 'exact' and monotonic() < deadline:
                    from lib.cinema.playback_request import owned_state
                    try:
                        receipt = self._read_startup_failure()
                        if receipt and not self._cinema_cancel.is_set():
                            self._startup_failure_receipt = receipt
                            self._startup_failed_for_reselect = True
                            self._startup_failure_category = 'native_startup_error'
                            if self.on_error:
                                self.on_error()
                            return False
                        owned_state(self.playback_session_id)
                    except OSError:
                        sleep(100)
                        continue  # Unknown is not superseded; keep bounded startup observation alive.
                    except (ValueError, RuntimeError):
                        pass
                    else:
                        kodilog('[CINEMA-OWNER] STARTUP_OBSERVATION_RECONCILED', level=xbmc.LOGINFO)
                        continue
                kodilog('[CINEMA-OWNER] STARTUP_SELECTION_REPLACED_OR_UNAVAILABLE', level=xbmc.LOGWARNING)
                self._was_superseded = True
                return False
            cancelled = getattr(self, '_cinema_cancel', None)
            failed = bool(cancelled and cancelled.is_set())
            failed = failed or (self.data.get("selection_policy") == "exact" and
                                get_property("bobbi_cinema_cancel") == self.playback_session_id)
            try:
                if self.data.get('selection_policy') == 'exact':
                    from lib.cinema.playback_request import owned_state
                    owner_snapshot = owned_state(self.playback_session_id)
                    terminal = owner_snapshot.get('terminal') or {}
                    resolver_failure = (owner_snapshot.get('desired') or {}).get('resolver_failure') or {}
                    if resolver_failure.get('request_id') == self.playback_session_id:
                        self._startup_failure_category = resolver_failure.get('category')
                        self._startup_failed_for_reselect = self._startup_failure_category not in ('cancelled', 'aborted')
                        failed = True
                    if terminal.get('request_id') == self.playback_session_id and terminal.get('reason') == 'ERROR':
                        self._startup_failed_for_reselect = True
                    failed = failed or (terminal.get('request_id') == self.playback_session_id
                                        and terminal.get('reason') in ('STOP', 'ERROR', 'CANCEL', 'SUPERSEDED'))
                else:
                    terminal = loads(get_property('bobbi_cinema_terminal') or '{}')
                    failed = failed or (isinstance(terminal, dict)
                                        and terminal.get('session') == self.playback_session_id
                                        and terminal.get('end') is False)
            except (OSError, RuntimeError, ValueError, TypeError):
                pass
            if failed or self.kodi_monitor.abortRequested() or monotonic() >= deadline:
                if not failed and monotonic() >= deadline:
                    self._startup_failure_category = 'startup_timeout'
                    self._startup_failed_for_reselect = not self.kodi_monitor.abortRequested()
                    kodilog('[PLAYER] bounded startup budget exhausted', level=xbmc.LOGWARNING)
                if cancelled:
                    cancelled.set()
                kodilog('[PLAYER] startup failed or cancelled; closing own resolver', level=xbmc.LOGWARNING)
                if self.on_error:
                    self.on_error()
                if self.data.get("selection_policy") == "exact":
                    self.cancel_playback()
                # Do not Stop a different player or close unrelated dialogs.
                return False
            if self.isPlayingVideo() and self._matches_requested_playback():
                return True
            if self.data.get('selection_policy') == 'exact' and self.data.get('is_torrent'):
                self.start_cinema_preparation(pre_start=True)
            if getattr(self, "on_progress", None):
                self.on_progress()
            sleep(100)

    def _read_startup_failure(self):
        """Recover a child-bound PRE_AV error without restoring control rights."""
        from lib.cinema.playback_request import call, startup_failure
        original = getattr(self, '_owner_context', None)
        if not isinstance(original, dict) or not all(k in original for k in ('boot_id', 'epoch', 'request_id')):
            return None
        query = dict(original)
        if not query.get('file_identity'):
            # The BT child bound the actual file. The parent must not guess it
            # from a window property, nor use owned_state after terminal cancel.
            snapshot = call({'operation': 'snapshot'})
            desired = snapshot.get('desired') if isinstance(snapshot, dict) else None
            if (not isinstance(desired, dict)
                    or snapshot.get('boot_id') != query['boot_id']
                    or snapshot.get('epoch') != query['epoch']
                    or desired.get('epoch') != query['epoch']
                    or desired.get('request_id') != query['request_id']
                    or desired.get('file_bound') is not True
                    or desired.get('start_claimed') is not True):
                return None
            identity, selection = desired.get('file_identity'), desired.get('selection_identity')
            if (not isinstance(identity, str) or not 0 < len(identity) <= 1024
                    or not isinstance(selection, str) or not selection
                    or not identity.startswith(selection + '|')):
                return None
            query['file_identity'] = identity
        # A read/terminal race still has to pass the service's precise ERROR,
        # native-instance and pre-AV receipt checks. Never assign query to self.
        return startup_failure(query)

    def _matches_requested_playback(self):
        """Do not confuse another video with the selected request's stream."""
        if self.data.get("selection_policy") != "exact":
            return True
        try:
            from lib.cinema.playback_request import owned_state
            snapshot = owned_state(self.playback_session_id)
            observed = snapshot.get('observed')
            if (not observed or observed['request_id'] != self.playback_session_id
                    or not observed.get('av_started')):
                return False
            instance = observed['native_instance']
            pinned = getattr(self, '_native_instance', None)
            if pinned is not None and pinned != instance:
                return False
            self._native_instance = instance
            return True
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError):
            return False

    def monitor(self):
        ensure_dialog_closed = False
        observation_timed_out = False
        kodilog("[PLAYER] monitor() entered")

        try:
            if not self._wait_for_video_start():
                return
            self._cinema_phase('TARGET_VIDEO_OBSERVED')
            kodilog("[PLAYER] monitor: video started playing, entering main loop")

            # UI handoff must precede optional stream/resume work, and must not
            # depend on already being fullscreen or on a known stream duration.
            started = self.handle_playback_start()
            if self.data.get('selection_policy') == 'exact' and started is False:
                return
            self._record_started_history()
            self.start_cinema_preparation()

            # Once playing, initialize streams and subtitles
            self.select_audio_stream()
            self.handle_subtitle_selection()

            # Fetch IntroDB segments in background if enabled
            if self.skip_intro_enabled and self.data.get("mode") == "tv":
                introdb_thread = Thread(target=self.fetch_introdb_segments)
                introdb_thread.daemon = True
                introdb_thread.start()

            # Fetch stinger info in background if enabled
            if get_setting("stinger_notifications_enabled") and self.data.get("mode") == "movies":
                stinger_thread = Thread(target=self.fetch_stinger_info)
                stinger_thread.daemon = True
                stinger_thread.start()

            # Monitor loop
            unknown_deadline = None
            while self.isPlayingVideo():
                if self.data.get('selection_policy') == 'exact':
                    from lib.cinema.playback_request import monitor_state
                    observed_at = monotonic()
                    if self._cinema_cancel.is_set():
                        return
                    budget = .3 if unknown_deadline is None else min(.3, unknown_deadline - observed_at)
                    if budget <= 0:
                        observation_timed_out = True
                        self._cinema_phase('OWNER_OBSERVATION_TIMEOUT')
                        return
                    state = monitor_state(getattr(self, '_owner_context', None),
                                          getattr(self, '_native_instance', None), timeout=budget)
                    if unknown_deadline is not None and monotonic() >= unknown_deadline:
                        observation_timed_out = True
                        self._cinema_phase('OWNER_OBSERVATION_TIMEOUT')
                        return
                    if state == 'TERMINAL':
                        break  # Same-instance EOF may clear observed after isPlayingVideo.
                    if state == 'UNKNOWN':
                        if unknown_deadline is None:
                            unknown_deadline = observed_at + TERMINAL_RECONCILIATION_SECONDS
                        remaining = unknown_deadline - monotonic()
                        if remaining <= 0:
                            observation_timed_out = True
                            self._terminal_reason = 'UNKNOWN'
                            self._cinema_phase('OWNER_OBSERVATION_TIMEOUT')
                            return  # No cleanup/control authority from a cached snapshot.
                        sleep(min(50, max(1, int(remaining * 1000))))
                        continue
                    unknown_deadline = None
                    superseded = state == 'SUPERSEDED'
                else:
                    superseded = not self._owns_playback_session() or not self._matches_requested_playback()
                if superseded:
                    self._was_superseded = True
                    kodilog("[PLAYER] monitor superseded by a newer playback session")
                    return
                self.update_playback_progress()
                if self.check_cinema_stall():
                    break
                self._apply_simkl_resume()
                self._apply_trakt_resume()
                self._apply_nuvio_resume()
                self.check_cinema_subtitles()
                self.start_cinema_preparation()
                self.handle_trakt_pause_resume()
                self.check_cinema_continuity()
                self.check_autoscrape_threshold()

                if not ensure_dialog_closed:
                    ensure_dialog_closed = True
                    self.playback_close_dialogs()

                self.check_next_dialog()
                self.check_skip_intro()
                self.check_stinger_notification()

                # Handle pending next-episode action from dialog
                if self._consume_next_dialog_action():
                    self._handle_next_dialog_action()

                self._wait_monitor_tick()

            self._cinema_phase('TERMINAL_RECONCILIATION_BEGIN')
            # A read gap and subsequent terminal reconciliation share one
            # absolute transition window; do not turn 3 seconds into 3+3.
            remaining = (TERMINAL_RECONCILIATION_SECONDS if unknown_deadline is None
                         else min(TERMINAL_RECONCILIATION_SECONDS, unknown_deadline - monotonic()))
            if remaining > 0:
                self.wait_cinema_terminal(budget_seconds=remaining)
            self._cinema_phase('TERMINAL_RECONCILIATION_END')
            self.queue_cinema_natural_end()
            self._cinema_phase('STOP_BOOKKEEPING_BEGIN')
            self.handle_playback_stop()
            self._cinema_phase('STOP_BOOKKEEPING_END')
            self.offer_terminal_actions()
            kodilog("[PLAYER] monitor: main loop exited, handle_playback_stop completed")

        except Exception as error:
            kodilog('[PLAYER] monitor failed: ' + type(error).__name__, level=xbmc.LOGERROR)
            self.kill_dialog()
        finally:
            if hasattr(self, '_cinema_cancel'):
                self._cinema_cancel.set()
            if not observation_timed_out and self._owns_playback_session():
                kodilog("[PLAYER] monitor: owner cleanup for playback session")
                self.clear_playback_properties()
                self._release_playback_session()
                self._cinema_phase('OWNER_RELEASED')
            else:
                kodilog("[PLAYER] monitor: superseded session; skipping global cleanup")
        kodilog("[PLAYER] monitor: exiting")

    def handle_subtitles(self, list_item):
        exact = self.data.get('selection_policy') == 'exact'
        if exact:
            # Ordinary owned playback uses the preparation ledger and native
            # actor after AVStart. A legacy path/provider URL is not a verified
            # binding and must not cause synchronous fetch or setSubtitles here.
            # Explicit native browsing/track selection remains available in OSD.
            self.subtitles_found = False
            return
        session = getattr(self, 'playback_session_id', None)
        cancel = getattr(self, '_cinema_cancel', None)

        def cancelled():
            # This is checked for every download chunk: only local state here,
            # never an IPC round trip or a Kodi query for every 8 KiB.
            return (not session or getattr(self, 'playback_session_id', None) != session
                    or getattr(self, '_cinema_cancel', None) is not cancel
                    or cancel is None or cancel.is_set())

        if exact and (cancelled() or not self._owns_playback_session()):
            return
        # Skip subtitle handling during autoplay unless subtitles can be handled without dialogs.
        if (self.data.get("autoplay") and not self.data.get("stream_subtitles")
                and not self.data.get("subtitles_path")):
            kodilog("Autoplay mode: skipping subtitle handling")
            return

        self.subtitles_found = False
        subtitles_path = self.data.get("subtitles_path", [])
        if subtitles_path or get_property("search_subtitles"):
            list_item.setSubtitles(subtitles_path)
            if self.data.get('selection_policy') != 'exact':
                self.setSubtitleStream(0)
            self.subtitles_found = True
        elif get_setting("stremio_subtitle_enabled"):
            try:
                from lib.clients.subtitle.submanager import SubtitleManager

                auto_select = self.data.get("autoplay") or subtitle_automation_enabled()
                options = {'cancelled': cancelled} if exact else {}
                subtitle_manager = SubtitleManager(self.data, self.notification, **options)
                subs_paths = subtitle_manager.fetch_subtitles(auto_select=auto_select)
                if exact and (cancelled() or not self._owns_playback_session()):
                    self.subtitles_found = False
                    return
                if not subs_paths:
                    kodilog("No subtitles found, skipping subtitle loading")
                    self.subtitles_found = False
                    return
                list_item.setSubtitles(subs_paths)
                if self.data.get('selection_policy') != 'exact':
                    self.setSubtitleStream(0)
                self.subtitles_found = True
            except Exception as e:
                kodilog(f"Error loading subtitles: {e}")
                self.subtitles_found = False
        elif subtitle_automation_enabled():
            sub_language = str(get_setting("subtitle_language"))
            if sub_language and sub_language.lower() != "None":
                self.lang_code = get_language_code(sub_language)
        else:
            kodilog("No subtitle handling method selected, skipping subtitle loading")

    def handle_subtitle_selection(self):
        """
        Handles subtitle activation and selection logic after playback starts.
        """
        if self.data.get('selection_policy') == 'exact':
            self.check_cinema_subtitles()
            return  # Prepared sidecars also need instance-scoped native selection.
        if (self.data.get('selection_policy') == 'exact' or xbmc.getSkinDir() == 'skin.bobbi.cinema') and not getattr(self, 'subtitles_found', False):
            self.check_cinema_subtitles()
            # Do not enable an arbitrary foreign track when Chinese is absent.
            # The short startup retry also handles late same-release sidecars.
            return
        auto_select_enabled = subtitle_automation_enabled()
        stremio_subtitle_enabled = get_setting("stremio_subtitle_enabled")
        search_subtitles = get_property("search_subtitles")
        if self.subtitles_found or stremio_subtitle_enabled or search_subtitles:
            self.showSubtitles(True)
            if self.subtitles_found:
                self.notification(translation(90257), time=2000)
                clear_property("search_subtitles")

                # Auto-select subtitle by language if enabled (runs BEFORE return)
                if auto_select_enabled:
                    _, _, subtitles = self.get_player_streams()
                    kodilog(f"Available subtitles: {subtitles}", level=xbmc.LOGDEBUG)
                    for sub in subtitles:
                        if self.lang_code == sub.get("language") and sub.get("isforced") is False:
                            self.setSubtitleStream(sub["index"])
                            self.showSubtitles(True)
                            break

            return

        if auto_select_enabled:
            _, _, subtitles = self.get_player_streams()
            kodilog(f"Available subtitles: {subtitles}", level=xbmc.LOGDEBUG)
            for sub in subtitles:
                if self.lang_code == sub.get("language") and sub.get("isforced") is False:
                    self.setSubtitleStream(sub["index"])
                    self.showSubtitles(True)
                    break

        elif not (stremio_subtitle_enabled or auto_select_enabled):
            kodilog("Auto subtitle selection disabled")
            self.showSubtitles(False)

    def check_cinema_subtitles(self):
        """Bounded startup discovery; foreign streams do not finish the search."""
        exact = self.data.get('selection_policy') == 'exact'
        if exact and not subtitle_automation_enabled():
            return
        if ((self.data.get('selection_policy') != 'exact' and xbmc.getSkinDir() != 'skin.bobbi.cinema')
                or getattr(self, '_cinema_subtitle_done', False)
                or getattr(self, '_cinema_subtitle_manual', False)
                or (not exact and (getattr(self, 'subtitles_found', False)
                                   or self.data.get('subtitles_path')))):
            return
        cancel = getattr(self, '_cinema_cancel', None)
        if ((cancel is not None and cancel.is_set()) or not self._owns_playback_session()
                or not self._matches_requested_playback()):
            return
        session = self.playback_session_id
        now = monotonic()
        attempts = getattr(self, '_cinema_subtitle_attempts', 0)
        # 30s IO budget plus native apply/receipt time, not a longer search.
        if attempts >= (20 if exact else 16) or now < getattr(self, '_cinema_subtitle_due', 0.0):
            return
        self._cinema_subtitle_attempts = attempts + 1
        self._cinema_subtitle_due = now + (2.0 if exact else min(30.0, 2.0 ** min(attempts, 5)))
        try:
            if exact:
                from lib.cinema.playback_ipc import call
                from lib.services.subtitle_fallback import playback_context
                result = call(dict(self._owner_context, operation='auto_chinese_subtitle',
                                   native_instance=self._native_instance,
                                   subtitle_final_attempt=attempts == 19,
                                   subtitle_context=playback_context(self.data, self.getTotalTime())))
                if (self.playback_session_id != session or not self._owns_playback_session()
                        or not self._matches_requested_playback()
                        or getattr(self, '_cinema_cancel', None) is not cancel
                        or (cancel is not None and cancel.is_set())):
                    return
                status = result.get('status')
                if status == 'CANDIDATE_LOADED':
                    self._cinema_subtitle_done = True
                    notification('中文字幕已加载；可在字幕菜单更换或调整延迟')
                if status == 'MANUAL_PRESERVED':
                    self._cinema_subtitle_manual = True
                elif status == 'CONFIRMED':
                    self._cinema_subtitle_done = True
                    kodilog('[CinemaSubs] Native current-instance full Chinese track confirmed')
                elif status != 'QUEUED':
                    kodilog('[CinemaSubs] Native subtitle state: {}'.format(status))
                return  # No unscoped subtitle stream/visibility fallback.
            from lib.clients.subtitle.cinema import chinese_track
            _, current, subtitles = self.get_player_streams()
            if (self.playback_session_id != session or not self._owns_playback_session()
                    or not self._matches_requested_playback()
                    or getattr(self, '_cinema_cancel', None) is not cancel
                    or (cancel is not None and cancel.is_set())):
                return
            visible = bool(get_visibility('Player.ShowSubtitles'))
            index = current.get('index') if isinstance(current, dict) else None
            old = getattr(self, '_cinema_subtitle_observed', None)
            indices = {sub.get('index') for sub in subtitles if isinstance(sub, dict)}
            if old is not None and ((index != old[0] and index in old[2]) or visible != old[1]):
                # Existing-track changes and user hide/show beat automation.
                self._cinema_subtitle_manual = True
                return
            self._cinema_subtitle_observed = (index, visible, indices)
            track = chinese_track(subtitles)
            if (track is not None and self._owns_playback_session()
                    and self._matches_requested_playback()
                    and not (cancel is not None and cancel.is_set())
                    and not getattr(self, '_cinema_subtitle_manual', False)):
                self.setSubtitleStream(track['index'])
                self.showSubtitles(True)
                self._cinema_subtitle_done = True
                kodilog('[CinemaSubs] Chinese track enabled at startup')
            elif subtitles and attempts == 0:
                kodilog('[CinemaSubs] No identified Chinese stream; no arbitrary subtitle enabled')
        except (KeyError, TypeError, RuntimeError, OSError) as error:
            # Subtitle availability is optional; the existing bounded discovery
            # schedule retries without dropping AV monitoring or reopening UI.
            kodilog('[CinemaSubs] Discovery deferred: ' + type(error).__name__, level=xbmc.LOGWARNING)

    def notify_cinema_subtitles_changed(self, request_id, manual=False):
        """Wake from an attached-sidecar/track event, or freeze a manual choice."""
        if (request_id != self.playback_session_id or not self._owns_playback_session()
                or self._cinema_cancel.is_set()):
            return False
        if manual:
            self._cinema_subtitle_manual = True
        elif not getattr(self, '_cinema_subtitle_manual', False):
            self._cinema_subtitle_attempts = 0
            self._cinema_subtitle_due = 0.0
        return True

    def onAVChange(self):
        # Kodi invokes this for changed streams; no RPC or UI work in callback.
        if getattr(self, 'playback_session_id', ''):
            self.notify_cinema_subtitles_changed(self.playback_session_id)

    def select_audio_stream(self):
        """
        Handles automatic audio stream selection based on user settings.
        """
        if self.data.get('selection_policy') == 'exact':
            # Native original-audio preference is request/file-bound and one-shot.
            # A delayed global setAudioStream could override it or a user's choice.
            return
        auto_audio_enabled = get_setting("auto_audio")
        auto_audio_language = str(get_setting("auto_audio_language"))
        if auto_audio_enabled and auto_audio_language and auto_audio_language.lower() != "none":
            sleep(500)
            audio_streams = self.getAvailableAudioStreams()
            if audio_streams or len(audio_streams) > 0:
                lang_code = get_language_code(auto_audio_language)
                for stream_lang in audio_streams:
                    if stream_lang == lang_code:
                        self.setAudioStream(audio_streams.index(stream_lang))
                        break

    def handle_playback_failure(self):
        if self.data.get("selection_policy") == "exact":
            self.cancel_playback()
            return
        self.kill_dialog()
        if self.on_error:
            self.on_error()
        self.stop()

    def handle_playback_start(self):
        session = self.playback_session_id
        cancel_event = getattr(self, '_cinema_cancel', None)
        try:
            if getattr(self, "_start_notified", False):
                return getattr(self, '_handoff_confirmed', False) if self.data.get('selection_policy') == 'exact' else True
            if (not self._owns_playback_session()
                    or not self.isPlayingVideo() or not self._matches_requested_playback()):
                return False
            cancelled = getattr(self, "_cinema_cancel", None)
            if cancelled is not None and cancelled.is_set():
                return False
            self._start_notified = True
            if self.data.get("selection_policy") == "exact":
                set_property("bobbi_cinema_started", json_dumps({
                    "request_id": self.playback_session_id,
                    "url_sha256": hashlib.sha256(self.getPlayingFile().split("|", 1)[0].encode("utf-8")).hexdigest(),
                    "ids": self.data.get("ids", {}), "tv_data": self.data.get("tv_data", {}),
                    "source_info_hash": self.data.get("info_hash") or self.data.get("prepared_source_info_hash", ""),
                }))
            requested = None
            if self.data.get('selection_policy') == 'exact':
                self._record_cinema_handoff('REQUESTED')
            if self.on_started:
                requested = self.on_started()
            if self.data.get('selection_policy') == 'exact':
                if requested is not False:
                    from lib.cinema.playback_request import call, context, owned_state
                    state = owned_state(session)
                    args = context(state, session)
                    requested = call(dict(args, operation='request_fullscreen',
                        native_instance=state['observed']['native_instance'])).get('queued') is True
                if requested is not False and self._confirm_cinema_fullscreen(session, cancel_event):
                    self._handoff_confirmed = True
                    self._record_cinema_handoff('CONFIRMED')
                    callback = getattr(self, 'on_handoff', None)
                    if callback:
                        callback()
                    kodilog('[CINEMA-HANDOFF] target video and fullscreen confirmed '
                            + self.playback_session_id[:8], level=xbmc.LOGINFO)
                    return True
                if (self.playback_session_id == session and self._cinema_cancel is cancel_event
                        and self._owns_playback_session() and not self._cinema_cancel.is_set()):
                    self._record_cinema_handoff('FAILED')
                    kodilog('[CINEMA-HANDOFF303] request={} stage=FAIL reason=fullscreen_denied'.format(
                        session[:8]), level=xbmc.LOGWARNING)
                    set_property('bobbi_cinema_terminal', json_dumps({
                        'session': self.playback_session_id, 'end': False, 'category': 'fullscreen_denied'}))
                    self.cancel_playback()
                return False
            return True
        except Exception as e:
            kodilog(f"Error in handle_playback_start: {e}")
            if (self.data.get('selection_policy') == 'exact' and self.playback_session_id == session
                    and self._cinema_cancel is cancel_event and self._owns_playback_session()
                    and not self._cinema_cancel.is_set()):
                self.cancel_playback()
            return False

    def _record_cinema_handoff(self, phase):
        set_property('bobbi_cinema_handoff', json_dumps({
            'request_id': self.playback_session_id, 'phase': phase,
            'fullscreen': bool(get_visibility(video_fullscreen_check)),
        }))

    def _confirm_cinema_fullscreen(self, session, cancel_event):
        """Observe one requested transition; never reactivate after user returns."""
        ticks = int(HANDOFF_CONFIRMATION_TIMEOUT_SECONDS * 1000 / HANDOFF_CONFIRMATION_POLL_MS)
        deadline = monotonic() + HANDOFF_CONFIRMATION_TIMEOUT_SECONDS
        for tick in range(ticks + 1):
            if (self.playback_session_id != session or self._cinema_cancel is not cancel_event
                    or self._cinema_cancel.is_set() or not self._owns_playback_session()
                    or not self.isPlayingVideo() or not self._matches_requested_playback()):
                return False
            from lib.cinema.playback_request import call, context, owned_state
            state = owned_state(session)
            confirmed = call(dict(context(state, session), operation='confirm_fullscreen',
                                  native_instance=state['observed']['native_instance'])).get('confirmed')
            if confirmed is True:
                return True
            if monotonic() >= deadline:
                return False
            if tick < ticks:
                sleep(HANDOFF_CONFIRMATION_POLL_MS)
        return False

    def update_playback_progress(self):
        try:
            self.total_time = self.getTotalTime()
            self.current_time = self.getTime()
            if self.total_time and self.total_time > 0:
                self.watched_percentage = round(float(self.current_time / self.total_time * 100), 1)
                self.data["progress"] = self.watched_percentage
                self.data["current_time"] = self.current_time
                self.data["total_time"] = self.total_time
                self._simkl_resume_playback_observed = True
                self._trakt_resume_playback_observed = True
        except Exception as e:
            kodilog(f"Error updating playback progress: {e}")

    def check_autoscrape_threshold(self):
        if self.data.get('cinema_continuity'):
            return  # Do not run the legacy quality-only source picker in parallel.
        try:
            if not getattr(self, "total_time", None) or self.total_time < 60:
                return
            if not getattr(self, "current_time", None):
                return
            if getattr(self, "autoscrape_started", False) is not False:
                return
            if not get_setting("autoscrape_next_episode", False):
                return
            if self.data.get("mode") != "tv":
                return

            threshold = int(get_setting("autoscrape_threshold", 70))
            if self.current_time >= (self.total_time * threshold / 100):
                self.autoscrape_started = True
                next_tv_data = self._get_next_episode_data()
                if not next_tv_data:
                    return
                thread = Thread(target=autoscrape_next_episode, args=(self.data, next_tv_data))
                thread.daemon = True
                thread.start()
        except Exception as e:
            kodilog(f"Error in check_autoscrape_threshold: {e}")

    def check_next_dialog(self):
        if self.data.get('cinema_continuity'):
            return  # Natural EOF, not an early countdown/automatic credit skip.
        try:
            # Only show PlayNext for TV series, never for movies
            if self.data.get("mode") != "tv":
                return

            if not getattr(self, "total_time", None) or self.total_time < 60:
                return
            if not getattr(self, "current_time", None):
                return
            if not getattr(self, "playback_started_properly", False):
                if self.current_time < 10:
                    self.playback_started_properly = True
                else:
                    return
            if self.current_time < (self.total_time * 0.5):
                return

            use_percentage = get_setting("playnext_use_percentage", False)
            if use_percentage:
                percentage = int(get_setting("playnext_percentage", 95))
                if self.next_dialog and self.watched_percentage >= percentage:
                    self._open_next_dialog()
            else:
                time_left = int(self.total_time) - int(self.current_time)
                if self.next_dialog and time_left <= self.playing_next_time:
                    self._open_next_dialog()
        except Exception as e:
            kodilog(f"Error in check_next_dialog: {e}")

    def _open_next_dialog(self):
        """Open PlayNext with one resolved next episode payload."""
        try:
            next_tv_data = self._get_next_episode_data()
        except Exception as e:
            kodilog(f"[PLAYNEXT] Failed resolving next_tv_data for dialog: {e}")
            next_tv_data = None
        item_info = dict(self.data)
        if self._is_valid_next_tv_data(next_tv_data):
            self.data["next_tv_data"] = next_tv_data
            item_info["next_tv_data"] = next_tv_data
        xbmc.executebuiltin(action_url_run(name="run_next_dialog", item_info=item_info))
        self.next_dialog = False

    def _is_valid_next_tv_data(self, next_tv_data) -> bool:
        """Return True when next_tv_data identifies a positive non-current episode."""
        if not isinstance(next_tv_data, dict):
            return False
        try:
            season = int(next_tv_data.get("season"))
            episode = int(next_tv_data.get("episode"))
        except (TypeError, ValueError):
            return False
        if season <= 0 or episode <= 0:
            return False

        current_tv_data = self.data.get("tv_data") or {}
        try:
            current_season = int(current_tv_data.get("season"))
            current_episode = int(current_tv_data.get("episode"))
        except (TypeError, ValueError):
            return True
        return (season, episode) != (current_season, current_episode)

    def _authoritative_next_tv_data(self):
        """Prefer dialog/player next_tv_data, falling back to recalculation."""
        next_tv_data = self.data.get("next_tv_data")
        if self._is_valid_next_tv_data(next_tv_data):
            kodilog(f"[PLAYNEXT] Using authoritative next_tv_data {next_tv_data}")
            return next_tv_data

        next_tv_data = self._get_next_episode_data()
        kodilog(f"[PLAYNEXT] _get_next_episode_data returned {next_tv_data}")
        if self._is_valid_next_tv_data(next_tv_data):
            self.data["next_tv_data"] = next_tv_data
            return next_tv_data
        return None

    def _check_still_watching_threshold(self) -> bool:
        """Check consecutive autoplay count and prompt 'Still Watching?' dialog.

        Returns True if the user stopped (caller should abort), False to continue.
        """
        threshold = int(get_setting("playnext_threshold", 0))
        if threshold <= 0:
            return False

        count_str = get_property("bobbi_consecutive_autoplays")
        try:
            count = int(count_str) if count_str else 1
        except (ValueError, TypeError):
            count = 1

        if count >= threshold:
            from xbmcgui import Dialog

            confirmed = Dialog().yesno(
                "Still watching?",
                "You've watched several episodes in a row. Continue?",
                yeslabel="Continue",
                nolabel="Stop",
            )
            if not confirmed:
                clear_property("bobbi_consecutive_autoplays")
                clear_property("bobbi_next_dialog_action")
                return True
            count = 1
        else:
            count += 1

        set_property("bobbi_consecutive_autoplays", str(count))
        return False

    def _queue_elementum_pack_next(self, next_tv_data: dict) -> bool:
        """Queue the next episode from the currently selected Elementum pack."""
        next_data = build_elementum_pack_next_playback(self.data, next_tv_data)
        if not next_data:
            return False

        JacktookPLayer._nextep_queue.append({"data": next_data})
        kodilog(
            f"[PLAYNEXT] Queued same Elementum pack for "
            f"S{next_tv_data.get('season')}E{next_tv_data.get('episode')}"
        )
        self.stop()
        clear_property("bobbi_next_dialog_action")
        return True

    def _queue_from_autoscrape_cache(self, next_tv_data: dict, ids: dict) -> bool:
        """Queue resolved autoplay data or raw results for manual selection."""
        id_value = ids.get("original_id") or ids.get("imdb_id") or ids.get("tmdb_id")
        if id_value is None:
            return False

        cache_key = get_autoscrape_cache_key(
            id_value, next_tv_data.get("season"), next_tv_data.get("episode")
        )
        results_cache_key = get_autoscrape_results_cache_key(
            id_value, next_tv_data.get("season"), next_tv_data.get("episode")
        )

        from lib.utils.kodi.settings import auto_play_enabled

        if auto_play_enabled():
            cached_data = cache.get(cache_key)
            if not cached_data:
                kodilog(f"[PLAYNEXT] Autoscrape resolved cache MISS for key={cache_key}")
                return False

            entry_data = dict(cached_data)
            entry_data["autoplay"] = True
            entry_data["playnext_context"] = True
            JacktookPLayer._nextep_queue.append({"data": entry_data})
            kodilog("[PLAYNEXT] Queued autoplay from cache, stopping player")
        else:
            cached_results = cache.get(results_cache_key)
            if not cached_results:
                kodilog(f"[PLAYNEXT] Autoscrape results cache MISS for key={results_cache_key}")
                return False

            entry_data = {
                "mode": self.data.get("mode", "tv"),
                "ids": ids,
                "tv_data": next_tv_data,
                "return_tv_data": self.data.get("tv_data", {}),
                "query": self.data.get("title", ""),
                "media_type": self.data.get("media_type", ""),
                "playnext_context": True,
            }
            JacktookPLayer._nextep_queue.append(
                {
                    "data": entry_data,
                    "results": cached_results,
                }
            )
            kodilog(
                f"[PLAYNEXT] Queued manual source select from cache "
                f"({len(cached_results)} sources), stopping player"
            )

        self.stop()
        clear_property("bobbi_next_dialog_action")
        return True

    def _handle_next_dialog_action(self):
        """Handle PlayNext using the dialog's logical next episode as authority.

        Kodi's PLAYLIST may still exist for playback mechanics, but it must not
        decide the PlayNext target here: a stale playlist item can drift from
        the `next_tv_data` shown by the dialog. Resolve the logical next episode
        first, then queue it from cache or via the silent background search.
        """
        if self.data.get('cinema_continuity'):
            # Explicit next uses the same preselected release; never silently
            # falls back to the old independent search/quality preference.
            if getattr(self, '_cinema_next_data', None) and self._owns_playback_session():
                prepared = dict(self._cinema_next_data)
                if self.data.get('selection_policy') == 'exact':
                    from lib.cinema.playback_request import call, data_identity
                    grant = call(dict(self._owner_context, operation='manual_next',
                        native_instance=self._native_instance, selection_identity=data_identity(prepared)))
                    if not grant.get('authorized'):
                        return
                    prepared.update(_parent_request_id=self.playback_session_id,
                                    _continuation_token=grant['token'])
                else:
                    self.stop()
                JacktookPLayer._nextep_queue.append({'data': prepared})
                self._cinema_next_data = None
            return
        kodilog(
            f"[PLAYNEXT] _handle_next_dialog_action:"
            f" tv_data={self.data.get('tv_data')},"
            f" ids={self.data.get('ids')}"
        )

        if self._check_still_watching_threshold():
            return

        next_tv_data = self._authoritative_next_tv_data()
        if not next_tv_data:
            clear_property("bobbi_next_dialog_action")
            return

        ids = self.data.get("ids", {})

        # An explicit PlayNext click may reuse the exact pack selected by the
        # user. This is intentionally independent from global autoplay.
        if self._queue_elementum_pack_next(next_tv_data):
            return

        # Prefer the logical PlayNext queue paths over Kodi PLAYLIST advance.
        # PLAYLIST fallback is intentionally not consulted before next_tv_data.
        if self._queue_from_autoscrape_cache(next_tv_data, ids):
            return  # Cache hit → queued → player.stop() called

        # No cache: fire silent background search thread for the same target.
        kodilog("[PLAYNEXT] No cache, firing silent background search")
        item_data = {
            "ids": ids,
            "title": self.data.get("title", ""),
            "mode": self.data.get("mode", ""),
            "media_type": self.data.get("media_type", ""),
        }
        Thread(target=self._background_search_and_queue, args=(item_data, next_tv_data)).start()
        clear_property("bobbi_next_dialog_action")

    def _background_search_and_queue(self, item_data: dict, next_tv_data: dict) -> None:
        """Search silently in background, queue result, then stop player"""
        from lib.utils.player.utils import autoscrape_next_episode

        try:
            kodilog("[PLAYNEXT] Background search starting (silent)")
            autoscrape_next_episode(item_data, next_tv_data, force=True)
            kodilog("[PLAYNEXT] Background search complete, checking cache")

            ids = item_data.get("ids", {})
            # Check cache again — autoscrape_next_episode populates it
            self._queue_from_autoscrape_cache(next_tv_data, ids)
        except Exception as e:
            kodilog(f"[PLAYNEXT] Background search error: {e}")

    def _validate_next_episode_inputs(self):
        """Validate that we have the data needed to find the next episode.

        Returns (tmdb_id, season, episode) or None.
        """
        if self.data.get("mode") != "tv":
            return None

        ids = self.data.get("ids") or {}
        tmdb_id = ids.get("tmdb_id")
        if not tmdb_id:
            return None

        tv_data = self.data.get("tv_data") or {}
        season = tv_data.get("season")
        episode = tv_data.get("episode")
        if season is None or episode is None:
            return None

        try:
            season = int(season)
            episode = int(episode)
        except (TypeError, ValueError):
            return None

        return tmdb_id, season, episode

    def _fetch_season_episodes(self, tmdb_id: str, season: int) -> Optional[list]:
        """Fetch episode list for a given season from TMDB. Returns list or None."""
        season_details = tmdb_get("season_details", {"id": tmdb_id, "season": season})
        if not season_details or not hasattr(season_details, "episodes"):
            return None
        episodes = getattr(season_details, "episodes", [])
        return episodes or None

    def _advance_across_season_boundary(
        self, tmdb_id: str, season: int, episode: int, episodes: list, tv_details
    ) -> Optional[tuple]:
        """Calculate the next episode position, crossing season boundary if needed.

        Returns (next_season, next_episode, search_episodes) or None if at series end.
        """
        max_episode = max(
            (getattr(ep, "episode_number", 0) for ep in episodes),
            default=0,
        )

        next_season = season
        next_episode = episode + 1

        if episode < max_episode:
            return next_season, next_episode, episodes

        # Season boundary: advance to next season
        # TMDB's number_of_seasons INCLUDES season 0 (specials), so we count
        # only seasons with season_number > 0 from the seasons list instead.
        all_seasons = getattr(tv_details, "seasons", None)
        if all_seasons:
            real_seasons = {
                s.season_number for s in all_seasons if getattr(s, "season_number", 0) > 0
            }
            max_season = max(real_seasons) if real_seasons else 1
        else:
            max_season = getattr(tv_details, "number_of_seasons", 1) or 1
        if season >= max_season:
            return None

        next_season = season + 1
        next_episode = 1
        next_episodes = self._fetch_season_episodes(tmdb_id, next_season)
        if not next_episodes:
            return None

        return next_season, next_episode, next_episodes

    def _find_next_episode_by_number(self, episodes: list, target_episode: int):
        """Find episode by number, checking air_date is not in the future.

        Returns the episode object or None.
        """
        for ep in episodes:
            if getattr(ep, "episode_number", 0) != target_episode:
                continue
            air_date = getattr(ep, "air_date", None)
            if air_date:
                try:
                    parts = air_date.split("-")
                    ep_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    if date.today() < ep_date:
                        return None
                except (ValueError, IndexError):
                    pass
            return ep
        return None

    def _get_next_episode_data(self):
        """Return next_tv_data dict for the next aired episode, or None."""
        kodilog(
            f"[PLAYNEXT] _get_next_episode_data: mode={self.data.get('mode')}, "
            f"tv_data={self.data.get('tv_data')}, ids={self.data.get('ids')}"
        )

        inputs = self._validate_next_episode_inputs()
        if not inputs:
            kodilog("[PLAYNEXT] _get_next_episode_data: missing required inputs, returning None")
            return None
        tmdb_id, season, episode = inputs
        kodilog(
            f"[PLAYNEXT] _get_next_episode_data: tmdb_id={tmdb_id},"
            f" season={season}, episode={episode}"
        )

        tv_details = tmdb_get("tv_details", tmdb_id)
        if not tv_details:
            kodilog("[PLAYNEXT] _get_next_episode_data: tv_details fetch failed, returning None")
            return None

        episodes = self._fetch_season_episodes(tmdb_id, season)
        if not episodes:
            kodilog(
                "[PLAYNEXT] _get_next_episode_data: no episodes found for"
                " current season, returning None"
            )
            return None

        pos = self._advance_across_season_boundary(tmdb_id, season, episode, episodes, tv_details)
        if not pos:
            kodilog(
                "[PLAYNEXT] _get_next_episode_data: at series end or"
                " boundary fetch failed, returning None"
            )
            return None
        next_season, next_episode, search_episodes = pos

        next_ep = self._find_next_episode_by_number(search_episodes, next_episode)
        if not next_ep:
            kodilog(
                "[PLAYNEXT] _get_next_episode_data: next episode not found"
                " or not yet aired, returning None"
            )
            return None

        result = {
            "name": getattr(next_ep, "name", ""),
            "episode": next_episode,
            "season": next_season,
        }
        kodilog(f"[PLAYNEXT] _get_next_episode_data returning: {result}")
        return result

    def handle_playback_stop(self):
        kodilog("[PLAYER] handle_playback_stop entered")
        if self.data.get('selection_policy') == 'exact':
            self.data['terminal_reason'] = getattr(self, '_terminal_reason', 'UNKNOWN')
            self.data['completed'] = self.data['terminal_reason'] == 'NATURAL_EOF'
            kodilog('[CINEMA-TERMINAL] ' + self.data['terminal_reason'], level=xbmc.LOGINFO)
        self._cinema_phase('YAMTRACK_STOP_BEGIN')
        self._sync_yamtrack_watched()
        self._cinema_phase('YAMTRACK_STOP_END')
        self._queue_nuvio_progress_sync()
        if self._is_trakt_scrobble_enabled():
            try:
                scrobble = TraktAPI().scrobble
                if self.data.get('completed') is False:
                    scrobble.trakt_pause_scrobble(self.data)
                else:
                    scrobble.trakt_stop_scrobble(self.data)
            except Exception as e:
                self._log_trakt_playback_failure("stop scrobble", e)
            self._is_trakt_scrobble_active = False
        if getattr(self, "_is_simkl_scrobble_active", False):
            if self._is_simkl_scrobble_enabled():
                self._queue_simkl_scrobble("pause" if self.data.get('completed') is False else "stop")
            self._is_simkl_scrobble_active = False
        self._delete_completed_simkl_playback()
        self._delete_completed_trakt_playback()
        self._cinema_phase('TRACKING_STOP_END')

        if not self._is_trakt_tracking_excluded():
            self._cinema_phase('HISTORY_SAVE_BEGIN')
            deferred = False
            if getattr(self, '_cinema_natural_queued', False):
                from lib.db.deferred_history import defer_watched_file
                deferred = defer_watched_file(self.data)
            if not deferred:
                set_watched_file(self.data)
            else:
                self._cinema_phase('HISTORY_SAVE_QUEUED')
            self._cinema_phase('HISTORY_SAVE_END')

        if self.data.get('selection_policy') != 'exact':
            # Exact EOF may already have reserved the child; parent bookkeeping
            # cannot close a new user dialog or clear another request's action.
            close_busy_dialog()
            clear_property("bobbi_next_dialog_action")
        kodilog("[PLAYER] handle_playback_stop completed")

    def offer_terminal_actions(self):
        if (self.data.get('selection_policy') != 'exact'
                or getattr(self, '_cinema_natural_queued', False)
                or getattr(self, '_terminal_reason', 'UNKNOWN') not in ('ERROR', 'UNKNOWN', 'NATURAL_EOF')):
            return
        episode = self.data.get('mode') in ('tv', 'anime', 'episode')
        ended = getattr(self, '_terminal_reason', 'UNKNOWN') == 'NATURAL_EOF'
        if ended and (not episode or not self.data.get('cinema_continuity')):
            return
        session = self.playback_session_id
        def current():
            return (self.playback_session_id == session and not self.kodi_monitor.abortRequested()
                    and not xbmc.Player().isPlaying() and self._owns_playback_session())
        from lib.gui.terminal_actions import choose
        selected = choose(current, episode, ended)
        if selected == 'sources' and current():
            execute_builtin(action_url_run('search', mode=self.data.get('mode', 'movies'),
                query=self.data.get('query') or self.data.get('title', ''), ids=self.data.get('ids', {}),
                tv_data=self.data.get('tv_data', {}), media_type=self.data.get('media_type', ''),
                force_select=True, rescrape=True))
        elif selected == 'episodes' and current():
            target = build_url('show_episodes_details', mode='tv', ids=self.data.get('ids', {}),
                tv_name=self.data.get('query') or self.data.get('title', ''),
                season=(self.data.get('tv_data') or {}).get('season', 1),
                media_type=self.data.get('media_type', 'tv'))
            execute_builtin('ActivateWindow(videos,%s,return)' % target)

    def _queue_nuvio_progress_sync(self):
        try:
            if not is_nuvio_progress_sync_enabled():
                return
            data = dict(self.data)
            data["ids"] = dict(self.data.get("ids") or {})
            data["tv_data"] = dict(self.data.get("tv_data") or {})
            thread = Thread(target=self._send_nuvio_progress, args=(data,))
            thread.daemon = True
            thread.start()
        except Exception as error:
            kodilog(
                f"[NUVIO] playback sync queue failed; continuing playback ({type(error).__name__})"
            )

    @staticmethod
    def _send_nuvio_progress(data):
        try:
            NuvioClient().push_watch_progress(data)
        except Exception as error:
            kodilog(f"[NUVIO] playback sync failed; continuing playback ({type(error).__name__})")

    def _apply_nuvio_resume(self):
        if getattr(self, '_bobi_start_over', False):
            return
        if getattr(self, "_nuvio_resume_applied", False):
            return
        try:
            progress = float(self.data.get("nuvio_resume_percent"))
            total_time = float(self.getTotalTime())
        except (TypeError, ValueError):
            return
        if progress <= 0 or progress >= 95 or total_time <= 0:
            return
        try:
            self.seekTime(total_time * progress / 100)
            self.playback_started_properly = True
            self._nuvio_resume_applied = True
        except Exception as error:
            kodilog(f"[NUVIO] resume seek failed; continuing playback ({type(error).__name__})")

    def _apply_simkl_resume(self):
        if getattr(self, '_bobi_start_over', False):
            return
        if getattr(self, "_simkl_resume_applied", False):
            return
        try:
            progress = float(self.data.get("simkl_resume_progress"))
            total_time = float(self.getTotalTime())
        except (TypeError, ValueError):
            return
        if progress <= 0 or progress >= 100 or total_time <= 0:
            return
        try:
            self.seekTime(total_time * progress / 100)
            self.playback_started_properly = True
            self._simkl_resume_applied = True
        except Exception as error:
            kodilog(f"[SIMKL] resume seek failed; continuing playback ({type(error).__name__})")

    def _delete_completed_simkl_playback(self):
        if self.data.get('completed') is False:
            return
        if getattr(self, "_simkl_playback_delete_attempted", False):
            return
        if not getattr(self, "_simkl_resume_playback_observed", False):
            return
        session_id = SimklClient._positive_integer(self.data.get("simkl_session_id"))
        try:
            completed = float(self.data.get("progress", 0)) >= 90
        except (TypeError, ValueError):
            completed = False
        if not session_id or not completed:
            return
        self._simkl_playback_delete_attempted = True
        thread = Thread(target=self._delete_simkl_playback, args=(session_id,))
        thread.daemon = True
        thread.start()

    @staticmethod
    def _delete_simkl_playback(session_id):
        try:
            SimklClient().delete_playback(session_id)
        except Exception as error:
            kodilog(f"[SIMKL] playback deletion failed; preserving resume ({type(error).__name__})")

    def _apply_trakt_resume(self):
        if getattr(self, '_bobi_start_over', False):
            return
        if getattr(self, "_trakt_resume_applied", False):
            return
        try:
            progress = float(self.data.get("trakt_resume_progress"))
            total_time = float(self.getTotalTime())
        except (TypeError, ValueError):
            return
        if progress <= 0 or progress >= 80 or total_time <= 0:
            return
        try:
            self.seekTime(total_time * progress / 100)
            self.playback_started_properly = True
            self._trakt_resume_applied = True
        except Exception as error:
            kodilog(f"Trakt resume seek failed; continuing playback ({type(error).__name__})")

    def _delete_completed_trakt_playback(self):
        if self.data.get('completed') is False:
            return
        if getattr(self, "_trakt_playback_delete_attempted", False):
            return
        if not getattr(self, "_trakt_resume_playback_observed", False):
            return
        playback_id = TraktScrobble._playback_positive_integer(self.data.get("trakt_playback_id"))
        try:
            completed = float(self.data.get("progress", 0)) >= 80
        except (TypeError, ValueError):
            completed = False
        if not playback_id or not completed:
            return
        self._trakt_playback_delete_attempted = True
        thread = Thread(target=self._delete_trakt_playback, args=(playback_id,))
        thread.daemon = True
        thread.start()

    @staticmethod
    def _delete_trakt_playback(playback_id):
        try:
            TraktAPI().scrobble.delete_playback(playback_id)
        except Exception as error:
            kodilog(f"Trakt playback deletion failed; preserving resume ({type(error).__name__})")

    def _sync_yamtrack_watched(self):
        if self.data.get('completed') is False:
            return
        if getattr(self, "_yamtrack_stop_attempted", False):
            return
        if self._is_live_tv() or self.data.get("is_informational_placeholder"):
            return
        try:
            progress = float(self.data.get("progress") or 0)
        except (TypeError, ValueError):
            return
        if progress < 90:
            return

        self._yamtrack_stop_attempted = True
        try:
            from lib.clients.yamtrack import send_watched_state

            send_watched_state(self.data)
        except Exception as error:
            kodilog(f"[YAMTRACK] Playback sync failed ({type(error).__name__})")

    def build_playlist(self):
        next_tv_data = self._get_next_episode_data()
        kodilog(f"[PLAYNEXT] build_playlist: next_tv_data={next_tv_data}")
        if not next_tv_data:
            return

        ids = self.data.get("ids") or {}
        episode_name = next_tv_data.get("name", "")
        label = f"{next_tv_data.get('season')}x{next_tv_data.get('episode')}. {episode_name}"
        query = self.data.get("title", "")

        if get_setting("autoscrape_next_episode", False):
            url = build_url(
                "play_autoscraped",
                mode=self.data["mode"],
                query=query,
                ids=ids,
                tv_data=next_tv_data,
                preferred_group=self.preferred_group,
                autoplay_context=str(AUTOPLAY_CONTEXT_NEXT_EPISODE),
            )
        else:
            url = build_url(
                "search",
                mode=self.data["mode"],
                query=query,
                ids=ids,
                tv_data=next_tv_data,
                rescrape=True,
                preferred_group=self.preferred_group,
                autoplay_context=str(AUTOPLAY_CONTEXT_NEXT_EPISODE),
                skip_cancel_on_back=True,
            )

        # Deduplication: Check if this URL is already in the playlist
        for i in range(self.PLAYLIST.size()):
            if self.PLAYLIST[i].getPath() == url:
                kodilog(f"[PLAYNEXT] build_playlist: duplicate URL, skipping: {url}")
                return

        kodilog(f"[PLAYNEXT] build_playlist: adding to PLAYLIST label={label}, url={url}")

        list_item = ListItem(label=label)
        list_item.setPath(url)
        list_item.setProperty("IsPlayable", "true")

        self.PLAYLIST.add(url=url, listitem=list_item)

    def kill_dialog(self):
        if self.data.get("selection_policy") == "exact":
            if self._owns_playback_session() and self.on_error:
                self.on_error()
            return
        close_all_dialog()

    def playback_close_dialogs(self):
        if self.data.get("selection_policy") == "exact":
            self.handle_playback_start()
            return
        close_all_dialog()

    def set_constants(self, data):
        self._cinema_natural_queued = False
        data = dict(data)
        if data.get("selection_policy") == "exact" and not self.on_started:
            # History/cache entries retain the release identity, not authority
            # to reuse an old request. Internal continuations also get a fresh
            # child URL rather than reviving a cancelled resolver.
            if data.get('_ui_reserved_request') != data.get('request_id') or not data.get('request_id'):
                data["request_id"] = uuid4().hex
            parts = urlsplit(str(data.get("url", "")))
            if parts.scheme == "plugin" and parts.netloc == "plugin.video.bobbi.torrent":
                query = [(key, value) for key, value in parse_qsl(parts.query)
                         if key not in {"request_id", "selection_policy"}]
                query.extend([("selection_policy", "exact"), ("request_id", data["request_id"])])
                data["url"] = urlunsplit(parts._replace(query=urlencode(query)))
        self._cinema_subtitle_attempts = 0
        self._cinema_subtitle_done = False
        self._cinema_subtitle_due = 0.0
        self._cinema_subtitle_manual = False
        self._cinema_subtitle_observed = None
        if data.get("selection_policy") != "exact":
            self.PLAYLIST.clear()
        if not (data.get("playnext_context") or data.get("autoplay")):
            clear_property("bobbi_consecutive_autoplays")
        self.data = data
        if self.data.get('selection_policy') == 'exact':
            self.data['completed'] = False
            self.data.pop('terminal_reason', None)
        self._terminal_reason = 'UNKNOWN'
        self.data['cinema_continuity'] = bool(
            self.data.get('mode') in ('tv', 'anime', 'episode') and get_setting('cinema_continuity_enabled', False))
        self._cinema_cancel = getattr(self, "_provided_cancel_event", None) or Event()
        self._start_notified = False
        self._handoff_confirmed = False
        self._resolution_answered = False
        self._cinema_end = False
        self._cinema_progress_watchdog = None
        self._cinema_next_status = None
        from lib.utils.player.discovery_gate import DiscoveryGate
        self._cinema_discovery = DiscoveryGate()
        self._cinema_warm_started = False
        self._cinema_warm_job = None
        self._cinema_next_data = None
        self._cinema_warm_result = None
        self._cinema_prepare_ticket = None
        self._cinema_prepare_sent = False
        self._cinema_prepare_inflight = None
        self._cinema_prepare_intent = None
        self._cinema_prepare_attempts = 0
        self._cinema_prepare_due = 0.0
        self._cinema_prepare_diagnostic = None
        self._direct_prepare_sent = False
        self._direct_prepare_due = 0.0
        self._direct_prepare_attempts = 0
        if data.get('selection_policy') == 'exact':
            # Bounded structured context, no paths/URLs/credentials. This records
            # the real adapter fields; a synthetic unit fixture is not evidence
            # that every provider populated them on the box.
            source_hash = data.get('info_hash')
            kodilog('[CINEMA-PREPARE-CONTEXT] ' + json_dumps(dict(
                request=data.get('request_id'), is_torrent=bool(data.get('is_torrent')),
                info_hash=source_hash if isinstance(source_hash, str) and re.fullmatch('[0-9a-fA-F]{40}', source_hash) else None,
                mode=data.get('mode'), ids_present=bool(data.get('ids')),
                title_present=bool(data.get('title')), release_present=bool(data.get('source_title')))), level=xbmc.LOGINFO)
        self._cinema_generation_due = 0.0
        self.url = self.data["url"]
        self.watched_percentage = self.data.get("progress", 0.0)
        self.total_time = 0
        self.current_time = 0
        self.playback_started_properly = False
        self.autoscrape_started = False
        self.next_dialog = get_setting("playnext_dialog_enabled")
        self._is_trakt_scrobble_active = False
        self._is_simkl_scrobble_active = False
        self._playback_was_paused = False
        self._yamtrack_stop_attempted = False
        self._simkl_resume_applied = False
        self._simkl_resume_playback_observed = False
        self._simkl_playback_delete_attempted = False
        self._was_superseded = False
        from lib.utils.general.utils import extract_release_group

        self.preferred_group = extract_release_group(self.data.get("title", ""))

        # Skip intro state
        self.skip_intro_enabled = get_setting("skip_intro_enabled")
        self.skip_intro_auto = get_setting("skip_intro_auto")
        self.skip_intro_segments = None
        self.skip_intro_handled = {"intro": False, "recap": False}

        # Stinger notification state
        self.stinger_notified = False
        self.stinger_keywords = []
        self.has_stinger = False

    def onPlayBackEnded(self):
        self._wake_monitor()
        if getattr(self, 'data', {}).get('selection_policy') == 'exact':
            return  # Native instance terminal receipt, not this generic callback.
        self._cinema_end = True

    def onPlayBackStopped(self):
        self._wake_monitor()
        if getattr(self, 'data', {}).get('selection_policy') == 'exact':
            return
        self._cinema_end = False
        if hasattr(self, '_cinema_cancel'):
            self._cinema_cancel.set()

    def onPlayBackError(self):
        if (getattr(self, 'data', {}).get('selection_policy') != 'exact'
                and not getattr(self, '_start_notified', False)):
            self._startup_failed_for_reselect = True
        self.onPlayBackStopped()

    def _wake_monitor(self):
        # Generic callbacks are only scheduling hints. The monitor still reads
        # the owned native receipt; a late callback cannot grant EOF or cancel B.
        wake = getattr(self, '_monitor_wake', None)
        if wake is not None:
            wake.set()

    def _wait_monitor_tick(self):
        wake = getattr(self, '_monitor_wake', None)
        if wake is None:
            sleep(1000)
        else:
            wake.wait(1.0)
            wake.clear()

    def _record_started_history(self):
        # Keep the legacy history format/save implementation. Only remove its
        # synchronous disk commit from the time-to-first-frame critical path.
        if not getattr(self, '_cinema_history_pending', False):
            return
        self._cinema_history_pending = False
        if self._owns_playback_session() and self._matches_requested_playback():
            self._cinema_phase('START_HISTORY_BEGIN')
            self.mark_watched(self.data)
            self._cinema_phase('START_HISTORY_END')

    def start_cinema_preparation(self, pre_start=False):
        if (not pre_start and self.data.get('selection_policy') == 'exact'
                and not self.data.get('prepared_resource_id')
                and (self.data.get('direct_source') or {}).get('provider') == 'mdsub'):
            self.start_direct_preparation()
            return
        attempts = getattr(self, '_cinema_prepare_attempts', 0)
        if (getattr(self, '_cinema_prepare_sent', False)
                or getattr(self, '_cinema_prepare_inflight', None) is not None or attempts >= 6
                or monotonic() < getattr(self, '_cinema_prepare_due', 0)):
            return
        cancel = getattr(self, '_cinema_cancel', None)
        if (cancel is None or cancel.is_set()
                or get_property('bobbi_cinema_cancel') == self.playback_session_id
                or not self._owns_playback_session()):
            return
        try:
            from lib.cinema.preparation_client import source_intent, advance_intent
            target = loads(get_property('bobbi_cinema_preparation_target' if pre_start else 'bobbi_cinema_target') or '{}')
            selected_hash = self.data.get('info_hash')
            selected_hash = (selected_hash.lower() if isinstance(selected_hash, str)
                             and re.fullmatch(r'[0-9a-fA-F]{40}', selected_hash) else None)
            if pre_start and selected_hash is None and isinstance(target, dict):
                # Normalize only this comparison. Keep the provider attribute,
                # selected locator and consumer-verified file identity intact.
                from lib.utils.player.utils import _jacktorr_base32_transport_hash
                provider_hash = self.data.get('info_hash')
                if (target.get('request_id') == self.playback_session_id
                        and target.get('session') == self.playback_session_id
                        and self.data.get('request_id') == self.playback_session_id
                        and _jacktorr_base32_transport_hash(provider_hash,
                            self.data.get('magnet') or self.data.get('url'))):
                    import base64
                    selected_hash = base64.b32decode(provider_hash.upper()).hex()
            if pre_start and (not self.data.get('is_torrent') or not isinstance(target, dict)
                    or selected_hash is None or target.get('source_info_hash') != selected_hash):
                if isinstance(target, dict) and target.get('request_id') == self.playback_session_id:
                    self._preparation_diagnostic('EARLY_SOURCE_HASH_MISMATCH')
                return
            intent = (getattr(self, '_cinema_prepare_intent', None) or source_intent(self.data, target)
                      or (None if pre_start else advance_intent(self.data)))
        except (ValueError, TypeError):
            return
        if intent is None:
            if isinstance(target, dict) and target.get('request_id') == self.playback_session_id:
                self._preparation_diagnostic('SOURCE_INTENT_FIELDS_REJECTED')
            return
        self._cinema_prepare_intent = intent
        self._cinema_prepare_attempts = attempts + 1
        self._cinema_prepare_due = monotonic() + min(30, 2 ** (attempts + 1))
        job = self._cinema_prepare_inflight = object()
        session, cancel = self.playback_session_id, self._cinema_cancel
        def current_session():
            return (self._cinema_cancel is cancel and not cancel.is_set()
                    and self.playback_session_id == session and self._owns_playback_session()
                    and get_property('bobbi_cinema_cancel') != session)
        def submit():
            try:
                from lib.cinema.preparation_client import call, capture_account
                if not current_session():
                    return
                account = capture_account(self.data, allow_capture=not attempts)
                result = None
                allow_submit = not attempts
                if attempts:
                    result = call('status', {'request_id': intent['request_id']}, expected_account=account)
                    # Only an explicit negative may replay the same local intent.
                    allow_submit = (isinstance(result, dict) and result.get('request_id') == intent['request_id']
                                    and result.get('state') == 'absent')
                if not current_session():
                    return
                if allow_submit:
                    result = call('advance' if 'resource_id' in intent else 'prepare', intent, expected_account=account)
                if (not isinstance(result, dict) or result.get('request_id') != intent['request_id']
                        or result.get('state') not in ('queued', 'validating', 'accepted', 'failed')):
                    self._preparation_diagnostic('INTENT_RECEIPT_UNAVAILABLE')
                    return  # Unknown outcome: next bounded attempt queries status, never blind replay.
                if current_session():
                    self._cinema_prepare_ticket = result['request_id']
                    self._cinema_prepare_sent = True
                    kodilog('[CINEMA-PREPARE] INTENT_ACCEPTED_NOT_CLOUD_READY request=' + session, level=xbmc.LOGINFO)
            except Exception as error:
                kodilog('[CINEMA-PREPARE] ' + type(error).__name__, level=xbmc.LOGWARNING)
            finally:
                if self._cinema_prepare_inflight is job:
                    self._cinema_prepare_inflight = None
                if attempts == 5 and current_session() and not getattr(self, '_cinema_prepare_sent', False):
                    self._preparation_diagnostic('INTENT_RETRY_EXHAUSTED')
                    notification('115 准备状态尚未确认，重新选择同片源可重试；不会盲目重复提交云任务',
                                 heading='波比TV', time=5000)
        try:
            Thread(target=submit, name='cinema-prepare-ipc', daemon=True).start()
        except RuntimeError:
            if self._cinema_prepare_inflight is job:
                self._cinema_prepare_inflight = None

    def _preparation_diagnostic(self, code):
        if getattr(self, '_cinema_prepare_diagnostic', None) != code:
            self._cinema_prepare_diagnostic = code
            kodilog('[CINEMA-PREPARE] ' + code + ' request=' + self.playback_session_id, level=xbmc.LOGWARNING)

    def start_direct_preparation(self):
        """Local idempotent intake only; slow transfer/probes belong to service."""
        attempts = getattr(self, '_direct_prepare_attempts', 0)
        if (getattr(self, '_direct_prepare_sent', False)
                or self._cinema_cancel.is_set() or attempts >= 6
                or monotonic() < getattr(self, '_direct_prepare_due', 0)
                or not self._owns_playback_session()):
            return
        self._direct_prepare_due = monotonic() + 15
        applicable = False
        try:
            from bobbi_core.direct_cloud_client import intent
            from bobbi_core.direct_cloud import source_key, ACTIVE
            from bobbi_core.preparation_client import call, capture_account
            body = intent(self.data)
            if body is None:
                return
            applicable = True
            self._direct_prepare_attempts = attempts + 1
            account = capture_account(self.data, allow_capture=not attempts)
            expected = source_key(body)
            result = call('catalog_status', {'key': expected}, expected_account=account) if attempts else None
            allow_submit = not attempts or (isinstance(result, dict) and result.get('key') == expected
                                            and result.get('state') == 'absent')
            if not self._owns_playback_session() or self._cinema_cancel.is_set():
                return
            if allow_submit:
                result = call('catalog_prepare', body, expected_account=account)
            if (not isinstance(result, dict) or result.get('key') != expected
                    or result.get('state') not in set(ACTIVE) | {'ready', 'failed', 'rejected', 'retryable'}):
                self._preparation_diagnostic('DIRECT_PREPARATION_RECEIPT_UNAVAILABLE')
                return
            if self._owns_playback_session() and not self._cinema_cancel.is_set():
                self._direct_prepare_sent = True
                if result.get('state') == 'retryable':
                    notification('个人 115 准备读取失败；重新选择此片源可重试', heading='波比TV', time=5000)
                elif result.get('state') in ('failed', 'rejected'):
                    notification('个人 115 准备未完成；当前直连播放不受影响', heading='波比TV', time=5000)
                elif result.get('state') == 'uncertain':
                    notification('个人 115 任务结果待核对；不会重复提交', heading='波比TV', time=5000)
                elif result.get('state') != 'ready':
                    notification('当前片源正在准备到个人 115；完成验证后再标记就绪', heading='波比TV', time=5000)
        except (OSError, ValueError, RuntimeError):
            self._preparation_diagnostic('DIRECT_PREPARATION_UNAVAILABLE')
        finally:
            if (applicable and attempts == 5 and self._owns_playback_session() and not self._cinema_cancel.is_set()
                    and not getattr(self, '_direct_prepare_sent', False)):
                self._preparation_diagnostic('DIRECT_PREPARATION_RETRY_EXHAUSTED')
                notification('个人 115 准备状态尚未确认，重新选择同片源可重试；当前播放不受影响',
                             heading='波比TV', time=5000)

    def check_cinema_continuity(self):
        if not self.data.get('cinema_continuity') or not self._owns_playback_session():
            return
        if self._cinema_cancel.is_set() or self.total_time < 60 or self.current_time < 20:
            return
        now = monotonic()
        if now >= getattr(self, '_cinema_generation_due', 0):
            self._cinema_generation_due = now + 2
            from lib.clients.bobi_library import prepared_generation
            generation = prepared_generation()
            if generation:
                self.notify_cinema_resources_changed(self.playback_session_id, generation)
        gate = getattr(self, '_cinema_discovery', None)
        if gate is None:
            from lib.utils.player.discovery_gate import DiscoveryGate
            gate = self._cinema_discovery = DiscoveryGate()
        token = gate.begin(monotonic())
        if token is not None:
            session = self.playback_session_id
            cancel_event = self._cinema_cancel
            data = deepcopy(self.data)
            def current_session():
                return (self.playback_session_id == session
                        and self._cinema_cancel is cancel_event
                        and not cancel_event.is_set() and self._owns_playback_session())
            def prepare():
                prepared = None
                reason = 'NO_VERIFIED_SAME_VERSION'
                try:
                    from lib.clients.bobi_library import load_index
                    from lib.utils.player.continuity import next_cloud_data
                    if current_session():
                        ticket = getattr(self, '_cinema_prepare_ticket', None)
                        if ticket:
                            from lib.cinema.preparation_client import call, capture_account
                            status = call('status', {'request_id': ticket},
                                          expected_account=capture_account(data, allow_capture=False))
                            if status.get('state') == 'accepted':
                                expected_media = 'tmdb:tv:{}:s{}:e{}'.format((data.get('ids') or {}).get('tmdb_id'),
                                    (data.get('tv_data') or {}).get('season'), (data.get('tv_data') or {}).get('episode'))
                                versions = {item['version_key'] for item in status['result'].get('tasks', [])
                                            if item.get('media_id') == expected_media}
                                if len(versions) == 1 and current_session():
                                    data['prepared_version_key'] = next(iter(versions))
                                    self.data['prepared_version_key'] = data['prepared_version_key']
                                    self._cinema_prepare_ticket = None
                        index = load_index()
                        prepared = next_cloud_data(data, index) if not data.get('direct_source') else None
                        if not prepared and current_session():
                            from lib.utils.player.direct_continuity import next_direct_data
                            prepared, reason = next_direct_data(data, index, lambda: not current_session())
                        if (prepared and (prepared.get('direct_source') or {}).get('provider') == 'mdsub'
                                and not prepared.get('prepared_resource_id') and current_session()):
                            from bobbi_core.direct_cloud_client import prepare as prepare_direct, entry as direct_entry
                            ready = direct_entry(prepared)
                            if not ready or ready['state'] != 'ready':
                                pending_direct, prepared = prepared, None
                                reason = 'DIRECT_CLOUD_PREPARING'
                                from lib.cinema.preparation_client import capture_account
                                capture_account(pending_direct, allow_capture=False)
                                status = prepare_direct(pending_direct)
                                reason = ('DIRECT_CLOUD_FAILED' if status.get('state') in ('failed', 'rejected')
                                          else 'DIRECT_CLOUD_PREPARING')
                                # A resolved external URL is not a ready cloud episode.
                except Exception as error:
                    kodilog('[CINEMA-NEXT] prepare failed: ' + type(error).__name__)
                finally:
                    def publish():
                        if current_session():
                            self._cinema_next_data = prepared
                            self._cinema_warm_started = False
                            state = 'SAME_VERSION_RESOLVED' if prepared else reason
                            if state != getattr(self, '_cinema_next_status', None):
                                self._cinema_next_status = state
                                kodilog('[CINEMA-NEXT] ' + state, level=xbmc.LOGINFO)
                                if state in ('DIRECT_CLOUD_PREPARING', 'DIRECT_CLOUD_FAILED'):
                                    message = ('下一集正在存入个人 115，尚未就绪' if state == 'DIRECT_CLOUD_PREPARING'
                                               else '下一集存入 115 未完成，请检查准备状态或重新选源')
                                    set_property('AM6B.NextPreparationState', message)
                                    notification(message, heading='波比TV', time=5000)
                                elif prepared and (prepared.get('direct_source') or {}).get('provider') == 'mdsub':
                                    set_property('AM6B.NextPreparationState', '同版本下一集已在 115 验证就绪')
                    gate.finish(token, bool(prepared), monotonic(), publish)
            try:
                Thread(target=prepare, daemon=True).start()
            except RuntimeError:
                gate.finish(token, False, monotonic(), lambda: None)
        if (self._cinema_next_data and not self._cinema_warm_started
                and self._cinema_next_data.get('url', '').startswith('/storage/videos/Clouddrive/CloudDrive/')
                and getattr(self, '_cinema_warm_job', None) is None
                and 0 < self.total_time - self.current_time <= 90
                and not get_visibility('Player.Paused')
                and not get_visibility('Player.Caching')):
            self._cinema_warm_started = True
            warm_data = self._cinema_next_data
            target = warm_data['url']
            warm_job = self._cinema_warm_job = object()
            warm_session = self.playback_session_id
            warm_cancel = self._cinema_cancel
            def warm():
                try:
                    from lib.utils.player.continuity import warm_cloud_head
                    def cancelled():
                        return (warm_cancel.is_set() or self._cinema_cancel is not warm_cancel
                                or self._cinema_next_data is not warm_data
                                or self.playback_session_id != warm_session or not self._owns_playback_session()
                                or get_visibility('Player.Caching'))
                    result = warm_cloud_head(target, cancelled)
                    if not cancelled():
                        self._cinema_warm_result = result
                        kodilog('[CINEMA-NEXT] warm ' + json_dumps(result), level=xbmc.LOGINFO)
                except Exception as error:
                    kodilog('[CINEMA-NEXT] warm failed: ' + type(error).__name__)
                finally:
                    if self._cinema_warm_job is warm_job:
                        self._cinema_warm_job = None
            try:
                Thread(target=warm, daemon=True).start()
            except RuntimeError:
                if self._cinema_warm_job is warm_job:
                    self._cinema_warm_job = None

    def notify_cinema_resources_changed(self, request_id, generation):
        """Local index/service completion adapter; it never resolves on this thread."""
        if (request_id != self.playback_session_id or not self._owns_playback_session()
                or self._cinema_cancel.is_set() or not isinstance(generation, str)
                or not generation or len(generation) > 128):
            return False
        gate = getattr(self, '_cinema_discovery', None)
        if gate is None:
            from lib.utils.player.discovery_gate import DiscoveryGate
            gate = self._cinema_discovery = DiscoveryGate()
        return gate.wake(generation)

    def queue_cinema_natural_end(self):
        if (self.data.get('cinema_continuity') and getattr(self, '_cinema_end', False)
                and self._owns_playback_session() and not self._cinema_cancel.is_set()
                and not self._cinema_next_data):
            kodilog('[CINEMA-NEXT] EOF_WITHOUT_VERIFIED_NEXT', level=xbmc.LOGINFO)
            message = ('下一集尚未在 115 验证就绪，未自动启动不稳定外链；请稍后重试'
                       if str(getattr(self, '_cinema_next_status', '')).startswith('DIRECT_CLOUD')
                       else '本集已结束，未找到可接续的同版本下一集，请返回选源')
            notification(message, heading='波比TV', time=5000)
        if (not self.data.get('cinema_continuity') or not getattr(self, '_cinema_end', False)
                or not self._owns_playback_session() or self._cinema_cancel.is_set()
                or not self._cinema_next_data):
            return
        if self._check_still_watching_threshold():
            return
        prepared = dict(self._cinema_next_data)
        if self.data.get('selection_policy') == 'exact':
            from lib.cinema.playback_request import call, context, data_identity
            try:
                grant = call(dict(self._owner_context, operation='authorize_next',
                    native_instance=self._native_instance, selection_identity=data_identity(prepared)))
                if not grant.get('authorized'):
                    return
                # Consume the short-lived native EOF receipt now. History IO
                # must not delay this one-use reservation past its 3 s budget.
                child = prepared.get('request_id')
                if not isinstance(child, str) or not re.fullmatch('[0-9a-f]{32}', child):
                    child = uuid4().hex
                reserved = call(dict(self._owner_context, operation='reserve_child',
                    token=grant['token'], child_request_id=child,
                    selection_identity=data_identity(prepared)))
                context(reserved, child)
                prepared['request_id'] = prepared['_ui_reserved_request'] = child
                prepared.pop('_parent_request_id', None)
                prepared.pop('_continuation_token', None)
            except (AttributeError, OSError, ValueError, RuntimeError) as error:
                kodilog('[CINEMA-NEXT] NATURAL_RESERVATION_REJECTED ' + type(error).__name__, level=xbmc.LOGWARNING)
                return
        JacktookPLayer._nextep_queue.append({'data': prepared})
        self._cinema_natural_queued = True
        self._cinema_next_data = None
        kodilog('[CINEMA-NEXT] NATURAL_EOF_SAME_VERSION_HANDOFF', level=xbmc.LOGINFO)

    def check_cinema_stall(self):
        # Only the owned direct player after AVStart. A stalled network read is
        # an error/cancel, never a natural EOF authorization for another file.
        if (self.data.get('selection_policy') != 'exact' or self.data.get('is_torrent')
                or not self.url.startswith(('http://', 'https://', '/storage/videos/Clouddrive/'))):
            return False
        from lib.utils.player.direct_continuity import ProgressWatchdog
        watch = getattr(self, '_cinema_progress_watchdog', None)
        if watch is None:
            watch = self._cinema_progress_watchdog = ProgressWatchdog()
        suspended = get_visibility('Player.Paused') or get_visibility('Player.Seeking')
        if not watch.stalled(monotonic(), self.current_time, suspended):
            return False
        if not self._owns_playback_session() or not self._matches_requested_playback():
            return False
        self._cinema_end = False
        self._cinema_next_data = None
        kodilog('[CINEMA-NEXT] DIRECT_PROGRESS_TIMEOUT_90S', level=xbmc.LOGWARNING)
        notification('片源连续 90 秒无播放进度，已停止重试；请重新播放或更换片源', heading='波比TV', time=6000)
        self.cancel_playback()
        return True

    def wait_cinema_terminal(self, budget_seconds=0.5):
        """Reconcile a terminal event while retaining the same request owner.

        Never infer natural EOF from a near-end percentage or absence of a
        player: both are also true after a manual stop/error.
        The monitor uses a bounded 3 s transition, not a playback-start timeout.
        A cancelled/replaced request cannot consume a late successful event.
        """
        if not self.data.get('cinema_continuity') and self.data.get('selection_policy') != 'exact':
            return
        if type(budget_seconds) not in (float, int) or not 0 < budget_seconds <= TERMINAL_RECONCILIATION_SECONDS:
            raise ValueError('Bounded terminal reconciliation required')
        session, cancel = self.playback_session_id, self._cinema_cancel
        exact = self.data.get('selection_policy') == 'exact'
        deadline = monotonic() + budget_seconds
        # Iteration cap is independent of clock/test doubles. No busy polling.
        for _ in range(int(budget_seconds * 1000 / 50)):
            if (self.playback_session_id != session or self._cinema_cancel is not cancel
                    or cancel.is_set() or self._cinema_end):
                return
            try:
                if exact:
                    from lib.cinema.playback_request import terminal_state
                    terminal = terminal_state(getattr(self, '_owner_context', None),
                                              getattr(self, '_native_instance', None))
                    event = ({'session': session, 'end': terminal['reason'] == 'NATURAL_EOF',
                              'reason': terminal['reason']} if terminal else {})
                else:
                    if not self._owns_playback_session():
                        return
                    event = loads(get_property('bobbi_cinema_terminal') or '{}')
                if (self.playback_session_id != session or self._cinema_cancel is not cancel
                        or cancel.is_set()):
                    return
                if isinstance(event, dict) and event.get('session') == self.playback_session_id:
                    self._terminal_reason = event.get('reason', 'UNKNOWN')
                    if event.get('end') is True:
                        self._cinema_end = True
                    elif event.get('end') is False:
                        self._cinema_cancel.set()
                    return
            except (OSError, RuntimeError, ValueError, TypeError):
                pass
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(50, max(1, int(remaining * 1000))))
        kodilog('[CINEMA-NEXT] no terminal event; no automatic handoff', level=xbmc.LOGINFO)

    def fetch_introdb_segments(self):
        """Fetch segment data from IntroDB in a background thread."""
        try:
            ids = self.data.get("ids", {})
            tv_data = self.data.get("tv_data", {})
            imdb_id = ids.get("imdb_id")
            season = tv_data.get("season")
            episode = tv_data.get("episode")

            if not imdb_id or not season or not episode:
                kodilog("Skip intro: Missing IMDb ID, season, or episode")
                return

            from lib.clients.introdb import get_segments

            self.skip_intro_segments = get_segments(imdb_id, season, episode)
            kodilog(f"IntroDB segments: {self.skip_intro_segments}")
        except Exception as e:
            kodilog(f"Error fetching IntroDB segments: {e}")

    def check_skip_intro(self):
        try:
            if not self.skip_intro_enabled or not self.skip_intro_segments:
                return
            if not getattr(self, "current_time", None):
                return

            current_ms = int(self.current_time * 1000)

            for segment_type in ("recap", "intro"):
                if self.skip_intro_handled.get(segment_type):
                    continue

                segment = self.skip_intro_segments.get(segment_type)
                if not segment:
                    continue

                start_ms = segment.get("start_ms", 0)
                end_ms = segment.get("end_ms", 0)
                end_sec = segment.get("end_sec", end_ms / 1000)

                if start_ms <= current_ms <= end_ms:
                    self.skip_intro_handled[segment_type] = True

                    if self.skip_intro_auto:
                        self.seekTime(end_sec)
                    else:
                        label = "Skip Intro" if segment_type == "intro" else "Skip Recap"
                        xbmc.executebuiltin(
                            action_url_run(
                                name="run_skip_intro_dialog",
                                segment_data=json_dumps(segment),
                                skip_label=label,
                            )
                        )
                elif current_ms > end_ms:
                    self.skip_intro_handled[segment_type] = True
        except Exception as e:
            kodilog(f"Error in check_skip_intro: {e}")

    def fetch_stinger_info(self):
        """Fetch stinger keywords from TMDB in a background thread."""
        try:
            if not get_setting("stinger_notifications_enabled"):
                return
            if self.data.get("mode") != "movies":
                return

            ids = self.data.get("ids", {})
            tmdb_id = ids.get("tmdb_id")
            if not tmdb_id:
                kodilog("Stinger: Missing TMDB ID")
                return

            self.stinger_keywords = get_movie_keywords(tmdb_id)
            self.has_stinger = any(
                k.lower() in ("aftercreditsstinger", "duringcreditsstinger")
                for k in self.stinger_keywords
            )
            kodilog(f"Stinger keywords: {self.stinger_keywords}, has_stinger: {self.has_stinger}")
        except Exception as e:
            kodilog(f"Error fetching stinger info: {e}")

    def check_stinger_notification(self):
        try:
            if not get_setting("stinger_notifications_enabled"):
                return
            if not self.has_stinger or self.stinger_notified:
                return
            if not getattr(self, "total_time", None) or self.total_time < 60:
                return
            if not getattr(self, "current_time", None):
                return

            time_left = int(self.total_time) - int(self.current_time)
            stinger_notification_time = int(get_setting("stinger_notification_time", 180))

            if time_left <= stinger_notification_time:
                notification(translation(90183), time=5000)
                self.stinger_notified = True
        except Exception as e:
            kodilog(f"Error in check_stinger_notification: {e}")

    def clear_playback_properties(self):
        clear_property("script.trakt.ids")

    def add_external_trakt_scrolling(self):
        if self._is_trakt_tracking_excluded():
            return
        try:
            ids = self.data.get("ids", {})
            mode = self.data.get("mode")
            title = self.data.get("title", "")

            trakt_ids = {
                "tmdb": ids.get("tmdb_id"),
                "imdb": ids.get("imdb_id"),
                "slug": TraktLists().make_trakt_slug(title),
            }
            if mode == "tv":
                trakt_ids["tvdb"] = ids.get("tvdb_id")
            set_property("script.trakt.ids", json_dumps(trakt_ids))
        except Exception as e:
            self._log_trakt_playback_failure("metadata setup", e)

    def get_player_streams(self):
        activePlayers = '{"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}'
        json_query = xbmc.executeJSONRPC(activePlayers)
        json_response = loads(json_query)
        result = json_response.get("result")
        if not result or not isinstance(result, list) or not result:
            return None, {}, []
        playerid = result[0].get("playerid")
        if playerid is None:
            return None, {}, []
        details_query = {
            "jsonrpc": "2.0",
            "method": "Player.GetProperties",
            "params": {
                "properties": ["currentsubtitle", "subtitles"],
                "playerid": playerid,
            },
            "id": 1,
        }
        json_query = xbmc.executeJSONRPC(json_dumps(details_query))
        details = loads(json_query).get("result", {})
        return (
            playerid,
            details.get("currentsubtitle", {}),
            details.get("subtitles", []),
        )

    def ask_user_retry(self):
        dialog = Dialog()
        choice = dialog.yesno(
            translation(90629),
            translation(90630),
            yeslabel=translation(90631),
            nolabel=translation(90242),
        )
        if choice:
            try:
                self.play_video(make_listing(self.data))
            except Exception as e:
                kodilog(f"Retry failed: {e}")
                self.run_error(e)
        else:
            self.cancel_playback()
            notification("Playback Cancelled", time=2000)

    def mark_watched(self, data):
        if self._is_trakt_tracking_excluded():
            return
        set_watched_file(data)

    def _is_live_tv(self):
        return bool(self.data.get("is_live_tv"))

    def _is_trakt_tracking_excluded(self):
        return (
            self._is_live_tv()
            or bool(self.data.get("is_informational_placeholder"))
            or not self._has_trakt_tracking_identity()
        )

    def _has_trakt_tracking_identity(self):
        ids = self.data.get("ids")
        if not isinstance(ids, dict) or not self._is_positive_integer(ids.get("tmdb_id")):
            return False

        mode = self.data.get("mode")
        if mode == "movies":
            return True
        if mode != "tv":
            return False

        tv_data = self.data.get("tv_data")
        return isinstance(tv_data, dict) and all(
            self._is_positive_integer(tv_data.get(key)) for key in ("season", "episode")
        )

    def _is_simkl_tracking_excluded(self):
        return (
            self._is_live_tv()
            or bool(self.data.get("is_informational_placeholder"))
            or not self._has_simkl_tracking_identity()
        )

    def _has_simkl_tracking_identity(self):
        ids = self.data.get("ids")
        if not isinstance(ids, dict) or not self._is_positive_integer(ids.get("tmdb_id")):
            return False
        mode = self.data.get("mode")
        if mode == "movies":
            return True
        if mode != "tv":
            return False
        tv_data = self.data.get("tv_data")
        return (
            isinstance(tv_data, dict)
            and self._is_non_negative_integer(tv_data.get("season"))
            and self._is_positive_integer(tv_data.get("episode"))
        )

    @staticmethod
    def _is_positive_integer(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return value > 0
        return isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0

    @staticmethod
    def _is_non_negative_integer(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return value >= 0
        return isinstance(value, str) and value.strip().isdigit()

    def _log_trakt_playback_failure(self, action, error):
        ids = self.data.get("ids") or {}
        kodilog(
            f"[TRAKT] {action} failed; continuing playback "
            f"(mode={self.data.get('mode')!r}, tmdb_id={ids.get('tmdb_id')!r}): {error}"
        )

    def cancel_playback(self):
        kodilog("[PLAYER] cancel_playback called")
        if self.data.get("selection_policy") == "exact":
            if not self._owns_playback_session():
                return
            self._cinema_cancel.set()
            set_property("bobbi_cinema_cancel", self.playback_session_id)
            from lib.cinema.playback_ipc import call
            try:
                call(dict(self._owner_context, operation='cancel'))
            except (AttributeError, OSError, ValueError, RuntimeError):
                kodilog('[PLAYER] scoped cancel unavailable; no unowned Stop fallback', level=xbmc.LOGERROR)
            if not self._resolution_answered and not self.data.get("direct_playback_handoff"):
                self._resolution_answered = True
                setResolvedUrl(ADDON_HANDLE, False, ListItem(offscreen=True))
            self._cleanup_playback_session()
            return
        self._cleanup_playback_session()
        try:
            setResolvedUrl(ADDON_HANDLE, False, ListItem(offscreen=True))
        except Exception as e:
            kodilog(
                f"setResolvedUrl failed in cancel_playback (expected when using direct play): {e}"
            )
        self.stop()

    def _cleanup_playback_session(self):
        if self.data.get("selection_policy") == "exact":
            if self._owns_playback_session() and self.on_error:
                self.on_error()
            return
        kodilog("[PLAYER] _cleanup_playback_session: clearing PLAYLIST, closing dialogs")
        self.PLAYLIST.clear()
        close_busy_dialog()
        close_all_dialog()

    def run_error(self, e: Exception):
        cancelled = getattr(self, '_cinema_cancel', None)
        if (not getattr(self, '_start_notified', False)
                and not (cancelled and cancelled.is_set()) and self._owns_playback_session()):
            self._startup_failed_for_reselect = True
        if self.data.get("selection_policy") == "exact":
            if self._owns_playback_session():
                kodilog("[CINEMA-HANDOFF] playback failed: " + type(e).__name__, level=xbmc.LOGWARNING)
                # Internal continuation has no resolver window to report the
                # failure. Keep it visible without leaking provider exceptions
                # or notifying after a superseding request/user cancellation.
                if (not self.on_error and not self._cinema_cancel.is_set()
                        and getattr(self, '_startup_failure_category', '') not in {'cancelled', 'aborted'}):
                    notification('播放准备失败，请返回片源列表重试', heading='波比TV', time=4000)
                self.cancel_playback()
                self.clear_playback_properties()
                self._release_playback_session()
            return
        notification("Playback Failed", time=3500)
        if self.on_error:
            self.on_error()
        self.cancel_playback()
        self.clear_playback_properties()
