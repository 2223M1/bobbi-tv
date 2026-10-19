import contextlib
import json
import re
import threading
from time import monotonic
from uuid import uuid4
from typing import Dict, List, Optional

import xbmc
import xbmcgui

from lib.clients.stremio.constants import STREMIO_ADDON_ALIASES_KEY
from lib.db.cached import cache
from lib.domain.torrent import TorrentStream
from lib.cinema.source_presentation import source_site_label
from lib.utils.general.source_platform import source_platform_label
from lib.gui.base_window import BaseWindow
from lib.gui.filter_items_window import FilterWindow
from lib.gui.filter_type_window import FilterTypeWindow
from lib.gui.qr_progress_dialog import QRProgressDialog
from lib.gui.resolver_window import ResolverWindow
from lib.gui.resume_window import ResumeDialog

# For web subtitle upload
from lib.services.subtitle_server import SubtitleUploadServer, get_local_ip
from lib.utils.debrid.debrid_utils import (
    add_source_to_debrid,
    get_source_status,
    get_torrent_data_from_uri,
)
from lib.utils.debrid.qrcode_utils import make_qrcode
from lib.utils.general.utils import (
    IndexerType,
    extract_publish_date,
    format_season_episode,
    get_colored_languages,
    get_info_hash_from_magnet,
    get_provider_color,
    get_random_color,
    normalize_tv_data,
    safe_json_loads,
)
from lib.utils.kodi.utils import (
    ADDON_PATH,
    action_url_run,
    bytes_to_human_readable,
    get_property,
    get_setting,
    kodilog,
    notification,
    set_property,
    translation,
)
from lib.utils.parsers.title_parser import (
    detect_chinese_subtitle_kind,
    parse_title_info,
    source_has_chinese_subtitles,
)
from lib.utils.torrent.torrserver_utils import add_source_to_torrserver

THEMES = {
    "0": {"card_bg": "FF362e33", "card_focus": "992A3E5C", "card_accent": "FF00559D"},
    "1": {"card_bg": "FF000000", "card_focus": "FF1A1A1A", "card_accent": "FF333333"},
    "2": {"card_bg": "FF1A0B2E", "card_focus": "994D004D", "card_accent": "FF00F3FF"},
    "3": {"card_bg": "FF1B261B", "card_focus": "992D402D", "card_accent": "FF7CFC00"},
    "4": {"card_bg": "FF141414", "card_focus": "992B2510", "card_accent": "FFD4AF37"},
}


def _plain_source_label(value):
    """Strip Kodi styling tags, not release-group or edition brackets."""
    return re.sub(r"\[/?(?:COLOR(?:\s+[^\]]+)?|B|I|UPPERCASE|LOWERCASE)\]", "", str(value or ""), flags=re.IGNORECASE)


def _quality_key(value):
    value = _plain_source_label(value).strip().casefold()
    return '4k' if value in {'4k', '2160p'} else value if value in {'1080p', '720p'} else 'n/a'


def _source_quality(source):
    value = _plain_source_label(getattr(source, 'quality', '')).strip()
    if value.casefold() not in ('', 'n/a', 'unknown', '未知'):
        return value
    from lib.utils.general.source_resolution import source_resolution
    facts = source_resolution(source)
    return {4320: '8K', 2160: '2160p', 1080: '1080p', 720: '720p', 480: '480p'}.get(facts.resolution, '未知')


def _quality_tabs(sources):
    from collections import Counter
    counts = Counter(_quality_key(_source_quality(source)) for source in sources)
    return [('全部', '__all__', len(sources))] + [(label, key, counts[key]) for label, key in
            [('4K', '4k'), ('1080p', '1080p'), ('720p', '720p'), ('其他', 'n/a')] if counts[key]]


def _plain_source_badges(value):
    text = _plain_source_label(value)
    text = re.sub(r'(?i)(?:\b(?:VIDEO|AUDIO|FORMAT|SOURCE|HDR|LANG|NOTE|EDITION)|视频|音频|封装|版本)\s*[:：]\s*', '', text)
    text = re.sub(r'\b(?:DV|DOLBY VISION)\b', '杜比视界', text, flags=re.I)
    text = re.sub(r'\bATMOS\b', 'Atmos', text, flags=re.I)
    return ' · '.join(dict.fromkeys(part.strip() for part in re.split(r'[·•|]+', text) if part.strip()))


def _manual_source_limit(sources, limit):
    """Apply one display budget after the complete, provider-neutral ranking."""
    return sources[:limit]


def _has_chinese_candidate(source):
    from lib.utils.general.cinema_source_rank import chinese_subtitle_preference
    return source_has_chinese_subtitles(source) or bool(chinese_subtitle_preference(source)[0])


def _provider_display_name(value):
    """Translate presentation only, never rewrite the provider or resolver type."""
    plain = _plain_source_label(value)
    return {'Torrent': 'BT种子', 'Direct': '直连资源', 'Debrid': '离线服务'}.get(plain, plain)


def _get_source_indexer_label(source: TorrentStream, aliases: Dict) -> str:
    platform = source_platform_label(source)
    if platform != source.indexer:
        return platform
    current_alias = aliases.get(source.addonKey) if isinstance(aliases, dict) else ""
    if current_alias:
        if source.addonInstanceLabel and source.addonName:
            return source.addonInstanceLabel.replace(source.addonName, current_alias, 1)
        return current_alias
    return source.addonInstanceLabel or source.indexer


def _source_filter_label(source):
    return source_site_label(source_platform_label(source), source.type, filter_option=True)


def _show_release_group(item_information, source):
    """User policy: encode groups belong only to BT anime/anime movies.

    Animation is established from existing TMDb genre IDs or explicit anime
    route context, never inferred from a release filename or indexer name.
    Cloud/debrid copies are not BT candidates even when their origin is a torrent.
    """
    from lib.utils.general.cinema_source_rank import uses_anime_groups
    return uses_anime_groups(item_information, source)


class SourceSelect(BaseWindow):
    def add_item_information_to_window(self, item_information):
        super().add_item_information_to_window(item_information)
        self._refresh_frontend_metadata(force=True)

    def _refresh_frontend_metadata(self, force=False):
        if not force and monotonic() < getattr(self, '_metadata_next_check', 0):
            return
        self._metadata_next_check = monotonic() + 2
        from lib.clients.tmdb.frontend_metadata import source_window, flush
        fields = source_window(getattr(self, 'item_information', {}))
        if force or fields != getattr(self, '_display_metadata', None):
            for key, value in fields.items():
                self.setProperty('info.' + key, value)
            self._display_metadata = fields
        flush()

    def __init__(
        self,
        xml_file: str,
        location: str,
        item_information: Optional[Dict] = None,
        sources: Optional[List[TorrentStream]] = None,
        uncached: Optional[List[TorrentStream]] = None,
    ):
        super().__init__(xml_file, location, item_information=item_information)
        self.uncached_sources: List[TorrentStream] = uncached or []
        self.position: int = -1
        self.sources: List[TorrentStream] = sources or []
        self.list_sources: List[TorrentStream] = []
        self.item_information: Dict = item_information or {}
        from lib.utils.general.cinema_source_rank import rank_sources
        self.sources = rank_sources(self.sources, self.item_information)
        self.playback_info: Optional[Dict] = None
        self.resume: Optional[bool] = None
        self.CACHE_KEY: str = str(self.item_information.get("tv_data", "")) or str(
            self.item_information.get("ids", "")
        )
        self.setProperty("instant_close", "false")
        self.setProperty("resolving", "false")
        self.filtered_sources: Optional[List[TorrentStream]] = None
        self.filter_applied: bool = False
        self._filter_spec = None
        self.resolved = False
        self._pending_selection = None
        self._restore_position = None
        self._selection_locked = False
        self._resolution_answered = False
        self.last_error = ""
        self.source_session = None
        self.source_pump = None
        self._source_revision = -1
        self._source_interacted = False
        self._auto_select_pending = False  # Manual source selection is product policy.

    def onInit(self) -> None:
        self.setProperty("playback_error", self.last_error)
        theme_index = get_setting("source_select_theme", "0")
        theme = THEMES.get(str(theme_index), THEMES["0"])
        if xbmc.getSkinDir() == "skin.bobbi.cinema":
            theme = {"card_bg": "FF18181C", "card_focus": "FF34343C", "card_accent": "FFF4F4F5"}
        self.setProperty("style.card_bg", theme["card_bg"])
        self.setProperty("style.card_focus", theme["card_focus"])
        self.setProperty("style.card_accent", theme["card_accent"])

        self.display_list: xbmcgui.ControlList = self.getControlList(1000)
        if getattr(self, 'source_session', None):
            # Render one current snapshot before accepting GUI focus receipts.
            # selectItem is queued; reading the old native selection here would
            # overwrite the card captured before the resolver closed us.
            self._refresh_progressive_sources(capture_focus=False, force=True)
        else:
            self.populate_qualities_header()
            self.populate_sources_list()
        self.set_default_focus(self.display_list, 1000, control_list_reset=True)
        # A newly opened recommendation list starts at its first card, not an
        # ordinal saved for an older, differently ordered search result set.
        if self.list_sources:
            position = self._restore_position if self._restore_position is not None else 0
            self.display_list.selectItem(max(0, min(position, len(self.list_sources) - 1)))
            self.setFocus(self.display_list)
        elif getattr(self, 'source_session', None):
            self.setFocusId(1300)  # The visible all-quality tab, not an empty list.
        super().onInit()
        if hasattr(self, '_source_ready'):
            self._source_ready.set()

    def populate_qualities_header(self):
        qualities_list = self.getControl(1300)
        current = qualities_list.getSelectedItem()
        selected = current.getProperty('quality') if current else '__all__'
        qualities_list.reset()
        self.setProperty("quality_item_width", '200')
        for display, key, count in _quality_tabs(self.sources):
            label = f"{display} ({count})"
            list_item = xbmcgui.ListItem(label)
            list_item.setProperty("quality", key)
            qualities_list.addItem(list_item)
        keys = [key for _, key, _ in _quality_tabs(self.sources)]
        qualities_list.selectItem(keys.index(selected) if selected in keys else 0)

    def doModal(self) -> bool:
        from lib.native_support import available
        self._native_owner = available()
        if not self._native_owner:
            from lib.portable import manual_modal
            return manual_modal(self, lambda: super(SourceSelect, self).doModal())
        prepared_retry = None
        while True:
            from lib.cinema.playback_ipc import call
            try:
                self._control_snapshot = call({'operation': 'snapshot'})
            except (OSError, ValueError, RuntimeError):
                self.last_error = '播放控制服务尚未就绪，请稍后重试'
                self.setProperty('playback_error', self.last_error)
                return False
            self._pending_selection = None
            self._selection_locked = False
            if prepared_retry is not None:
                from lib.cinema.prepared_retry import unchanged
                cloud_source, prior_snapshot = prepared_retry
                prepared_retry = None
                if not unchanged(prior_snapshot, self._control_snapshot):
                    return False  # A new selection/restart wins over a late retry.
                self._resolve_item(cloud_source)
            elif getattr(self, 'source_session', None) is None:
                super().doModal()
            else:
                self._run_progressive_window()
            pending = self._pending_selection
            if pending is None:
                if getattr(self, 'source_pump', None):
                    self.source_pump.cancel()
                    self.source_session.cancel()
                return self.resolved
            # Resolution runs outside the source dialog's GUI callback. The
            # source dialog has already closed; only one loading owner remains.
            source, options = pending
            if self._resolution_answered:
                self.item_information["direct_playback_handoff"] = True
            resolver = ResolverWindow(
                "resolver.xml", ADDON_PATH, source=source,
                item_information=dict(self.item_information), **options,
            )
            self.resolved = resolver.doModal(False)
            self.last_error = getattr(resolver, "error_message", "")
            self._resolution_answered = self._resolution_answered or getattr(resolver, "resolution_answered", False)
            if (not self.resolved and not resolver.user_cancelled
                    and resolver.startup_failure_category in {'buffer_timeout', 'preload_error'}
                    and isinstance(resolver.playback_info, dict)):
                from lib.cinema.prepared_retry import ready_source
                prepared_retry = ready_source(resolver.playback_info, resolver.startup_failure_category,
                    resolver.preparation_intent, lambda: resolver.user_cancelled or xbmc.Monitor().abortRequested())
                if prepared_retry:
                    kodilog('[CINEMA-PREPARE] SAME_FILE_CLOUD_RETRY request='
                            + self.item_information['request_id'])
            del resolver
            if self.resolved:
                return True
            if get_property("bobbi_cinema_selection") != self.item_information.get("request_id"):
                return False
            if prepared_retry is not None:
                continue  # One new exact request; never repeat the failed BT opener.
            self._restore_position = self.position
            if getattr(self, 'source_session', None):
                self.source_session.reopen()
            self.setProperty("resolving", "false")

    def close(self):
        if hasattr(self, '_source_closed'):
            self._source_closed.set()
        super().close()

    def _run_progressive_window(self):
        # Uses the existing WindowXMLDialog.show and ControlList's native
        # SendThreadMessage binding, as SearchStatusWindow already does.
        from threading import Event
        self._source_ready, self._source_closed = Event(), Event()
        self._auto_select_deadline = monotonic() + 30.0
        monitor = xbmc.Monitor()
        self.show()
        try:
            while not self._source_closed.is_set() and not monitor.abortRequested():
                # WindowXMLDialog.show queues onInit/onAction on this Python
                # interpreter. Event.wait does not dispatch Kodi callbacks;
                # the finite native wait does. Recheck closure after dispatch
                # so Back cannot redraw or reopen a closed selection window.
                if monitor.waitForAbort(0.12) or self._source_closed.is_set():
                    break
                if self._source_ready.is_set() and not self._selection_locked and not getattr(self, '_source_modal', False):
                    self._refresh_progressive_sources()
                    self._maybe_auto_select()
        finally:
            self.close()

    def _maybe_auto_select(self):
        """One automatic choice through the same exact-selection authority.

        Wait for all providers (at most 30 s), so a fast local result does not
        preempt Tencent/BT. Any user input takes over. Only a verified identical
        prepared file may replace a pre-AV failed BT transport; no other release
        is tried automatically. All remaining errors return to the normal picker.
        """
        if (not self._auto_select_pending or self._source_interacted
                or self._selection_locked or self._source_closed.is_set()):
            return
        status = self.source_session.status()
        if status['cancelled'] or status['confirmed']:
            self._auto_select_pending = False
            return
        pending = any(row['state'] not in self.source_session.TERMINAL
                      for row in status['providers'].values())
        if pending and monotonic() < self._auto_select_deadline:
            return
        self._auto_select_pending = False
        if pending:
            self.source_pump.cancel()
        snapshot = self.source_session.snapshot(full=True)
        from lib.utils.general.cinema_source_rank import source_preference
        context = dict(self.item_information, **snapshot['metadata'])
        choice = next(((key, source) for key, source in snapshot['entries']
                       if not source_preference(source, context)['caution']), None)
        if choice is None:
            self.last_error = '暂无可自动选择的可靠片源，请手动选择或重试'
            self.setProperty('playback_error', self.last_error)
            return
        key, source = choice
        selected = self.source_session.capture(self.source_session.epoch, key)
        if selected is None:
            return
        self.position = next((i for i, row in enumerate(self.list_sources)
                              if self.source_session.key(row) == key), 0)
        kodilog('AM6B unified autoplay: candidate=' + key + '; pool=' + str(len(snapshot['entries'])))
        self._resolve_item(selected, pack_select=False)
        if self._selection_locked:
            self.source_pump.cancel()
        else:
            self.source_session.reopen()

    def _refresh_progressive_sources(self, capture_focus=True, force=False):
        # A metadata worker can finish after the final provider revision.
        # Update only header properties; never reset cards or selected identity.
        self._refresh_frontend_metadata(force=force)
        status = self.source_session.status()
        if not force and status['revision'] == self._source_revision:
            return
        # Native initial focus is not a user selection. Until the first input,
        # newly ranked results may replace the provisional first recommendation.
        # A restored/captured card or actual navigation remains pinned by key.
        preserve_focus = (getattr(self, '_source_interacted', False)
                          or self.source_session.focus_key is not None)
        if capture_focus and self.list_sources and preserve_focus:
            item = self.display_list.getSelectedItem()
            if item:
                self.source_session.focus(item.getProperty('source_key'), self.display_list.getSelectedPosition())
        snapshot = self.source_session.snapshot(full=True)
        self._source_revision = snapshot['revision']
        self._recommended_key = snapshot['recommended_key']
        self.setProperty('source_coalesced_count', str(snapshot.get('superseded_count', 0)))
        if snapshot['metadata']:
            self.add_item_information_to_window(dict(self.item_information, **snapshot['metadata']))
        self.sources = [source for _, source in snapshot['entries']]
        self.populate_qualities_header()
        if self.filter_applied and getattr(self, '_filter_spec', None):
            self.filtered_sources = self._apply_source_filter(*self._filter_spec)
        self.populate_sources_list()
        if self.list_sources:
            keys = [self.source_session.key(source) for source in self.list_sources]
            position = keys.index(self.source_session.focus_key) if self.source_session.focus_key in keys else min(
                self.source_session.focus_position, len(keys) - 1)
            self.display_list.selectItem(position)
        pending = sum(row['state'] not in self.source_session.TERMINAL for row in snapshot['providers'].values())
        self.setProperty('source_loading', 'true' if pending else 'false')
        from lib.cinema.source_presentation import search_status
        summary, error, diagnostic = search_status(snapshot['providers'], bool(self.sources))
        if not pending and not getattr(self, '_provider_terminal_logged', False):
            from lib.cinema.source_presentation import provider_diagnostics
            self._provider_terminal_logged = True
            kodilog('BOBBI-PROVIDERS ' + json.dumps(provider_diagnostics(snapshot['providers']),
                                                  ensure_ascii=True, sort_keys=True), level=xbmc.LOGINFO)
        if self._auto_select_pending and not self._source_interacted:
            summary = '正在统一比较片源，完成后自动播放；操作列表可改为手动选择'
        if snapshot.get('superseded_count'):
            summary += ' · 已合并 {} 个 115 同版 BT'.format(snapshot['superseded_count'])
        self.setProperty('source_status', summary)
        self.setProperty('source_diagnostics', diagnostic)
        self.setProperty('playback_error', self.last_error or error)

    def handle_action(self, action_id: int, control_id: Optional[int] = None) -> None:
        self._source_interacted = True
        self._auto_select_pending = False
        # Native dialog callbacks may yield while a popup is open. Retain its
        # cards/focus; producers may publish, but the window loop must not redraw.
        self._source_modal = True
        try:
            self._handle_source_action(action_id, control_id)
        finally:
            self._source_modal = False

    def _handle_source_action(self, action_id: int, control_id: Optional[int] = None) -> None:
        if action_id == 7 and control_id == 1400:
            self._handle_filter_action()
        elif action_id == 117:  # Context menu action
            self._handle_context_menu_action()
        elif action_id == 7 and control_id == 1300:
            self._handle_quality_select_action()
        elif action_id == 7 and control_id == 1000:  # Select action
            self._handle_select_action(control_id)

    def _handle_filter_action(self):
        filter_type_popup = FilterTypeWindow("filter_type.xml", ADDON_PATH)
        group_sources = [source for source in self.sources if _show_release_group(getattr(self, "item_information", {}), source)]
        filter_type_popup.allow_release_groups = bool(group_sources)
        filter_type_popup.doModal()
        selected_type = filter_type_popup.selected_type
        del filter_type_popup
        if selected_type is None:
            return  # Back cancels the popup without clearing an existing filter.

        def get_unique(attr):
            if attr == 'quality':
                return sorted(set(_source_quality(s) for s in self.sources))
            return sorted(set(getattr(s, attr) for s in self.sources if getattr(s, attr)))

        def get_release_groups():
            groups = {}
            for source in group_sources:
                release_group = parse_title_info(source.title)["release_group"]
                if release_group:
                    groups.setdefault(release_group.casefold(), set()).add(release_group)
            return [
                sorted(groups[key], key=lambda group: (group.isupper(), group.islower(), group))[0]
                for key in sorted(groups)
            ]

        filter_map = {
            "quality": {
                "items": lambda: get_unique("quality"),
                "filter": lambda val: [s for s in self.sources if _source_quality(s) == val],
            },
            "provider": {
                "items": get_release_groups,
                "filter": lambda val: [
                    s
                    for s in group_sources
                    if parse_title_info(s.title)["release_group"].casefold() == val.casefold()
                ],
            },
            "type": {
                "items": lambda: get_unique("type"),
                "filter": lambda val: [s for s in self.sources if s.type == val],
            },
            "indexer": {
                "items": lambda: sorted({_source_filter_label(s) for s in self.sources if _source_filter_label(s)}),
                "filter": lambda val: [s for s in self.sources if _source_filter_label(s) == val],
            },
            "language": {
                "items": self._get_all_languages,
                "filter": lambda val: [
                    s
                    for s in self.sources
                    if val in getattr(s, "languages", []) or val in getattr(s, "fullLanguages", [])
                ],
            },
            "release_group": {
                "items": get_release_groups,
                "filter": lambda val: [
                    s
                    for s in group_sources
                    if parse_title_info(s.title)["release_group"].casefold() == val.casefold()
                ],
            },
        }

        one_click_filters = {
            "chinese_subtitles": lambda: [
                source for source in self.sources if _has_chinese_candidate(source)
            ],
            "only_torrents": lambda: [s for s in self.sources if s.type == "Torrent"],
            "only_debrid": lambda: [s for s in self.sources if s.type == "Debrid"],
        }

        if selected_type in one_click_filters:
            filtered_sources = self._apply_source_filter(selected_type, None)
            if not filtered_sources:
                kodilog("No sources found matching the filter")
                if selected_type == "chinese_subtitles":
                    notification("当前结果没有标注中文字幕的片源，可选择全部以清除筛选")
            self.filtered_sources = filtered_sources
            self.filter_applied = True
            self._filter_spec = (selected_type, None)
        elif selected_type in filter_map:
            items = filter_map[selected_type]["items"]()
            if selected_type == "language" and not items:
                notification(translation(90406))
                return
            popup = FilterWindow("filter_items.xml", ADDON_PATH, filter=items)
            popup.doModal()
            selected_filter = popup.selected_filter
            del popup
            if selected_filter is not None:
                filtered_sources = self._apply_source_filter(selected_type, selected_filter)
                if not filtered_sources:
                    kodilog("No sources found matching the filter")
                self.filtered_sources = filtered_sources
                self.filter_applied = True
                self._filter_spec = (selected_type, selected_filter)
            else:
                return  # A cancelled value picker preserves the current cards.
        else:
            self.filtered_sources = None
            self.filter_applied = False
            self._filter_spec = None

        self.populate_sources_list()
        if self.filter_applied and self.filtered_sources == []:
            self.setFocusId(1300)
        else:
            self.set_default_focus(self.display_list, 1000, control_list_reset=True)

    def _apply_source_filter(self, kind, value):
        if kind == 'indexer':
            return [s for s in self.sources if _source_filter_label(s) == value]
        if kind == 'quality':
            return [s for s in self.sources if _source_quality(s) == value]
        if kind == 'type':
            return [s for s in self.sources if getattr(s, kind) == value]
        if kind == 'quality_tab':
            return [s for s in self.sources if _quality_key(_source_quality(s)) == value]
        if kind in ('provider', 'release_group'):
            return [s for s in self.sources if _show_release_group(getattr(self, 'item_information', {}), s)
                    and parse_title_info(s.title)['release_group'].casefold() == value.casefold()]
        if kind == 'language':
            return [s for s in self.sources if value in (getattr(s, 'languages', None) or [])
                    or value in (getattr(s, 'fullLanguages', None) or [])]
        if kind == 'chinese_subtitles':
            return [s for s in self.sources if _has_chinese_candidate(s)]
        if kind in ('only_torrents', 'only_debrid'):
            expected = 'Torrent' if kind == 'only_torrents' else 'Debrid'
            return [s for s in self.sources if s.type == expected]
        raise ValueError('Unknown source filter')

    def _handle_context_menu_action(self):
        self.position = self.display_list.getSelectedPosition()
        if not 0 <= self.position < len(self.list_sources):
            return
        if getattr(self, 'source_session', None):
            item = self.display_list.getSelectedItem()
            selected_source = self.source_session.inspect(self.source_session.epoch,
                                                          item.getProperty('source_key') if item else '')
            if selected_source is None:
                return
        else:
            selected_source = self.list_sources[self.position]

        menu_items = []
        menu_actions = []

        if selected_source.type == IndexerType.TORRENT:
            menu_items.extend(
                [
                    translation(90365),
                    translation(90359),
                    translation(90082),
                    translation(90744),
                ]
            )
            menu_actions.extend(
                [
                    "download_to_debrid",
                    "add_to_torrserver",
                    "subtitle_download",
                    "upload_subtitle",
                ]
            )
        elif selected_source.type in (IndexerType.DIRECT, IndexerType.STREMIO_DEBRID):
            menu_items.extend([translation(90083), translation(90082), translation(90744)])
            menu_actions.extend(["download_file", "subtitle_download", "upload_subtitle"])
        else:
            menu_items.extend(
                [
                    translation(90084),
                    translation(90083),
                    translation(90082),
                    translation(90744),
                ]
            )
            menu_actions.extend(
                [
                    "pack_select",
                    "download_file",
                    "subtitle_download",
                    "upload_subtitle",
                ]
            )

        response = xbmcgui.Dialog().contextmenu(menu_items)
        if response < 0 or response >= len(menu_actions):
            return

        action = menu_actions[response]
        kodilog(
            f"SourceSelect context action selected: action={action}, mode={self.item_information.get('mode')}, query={self.item_information.get('query')}, year={self.item_information.get('year')}"
        )
        if action == "download_to_debrid":
            try:
                self._download_to_debrid(selected_source)
            except Exception as e:
                kodilog(f"SourceSelect _download_to_debrid raised: {e}")
                notification(str(e))
        elif action == "add_to_torrserver":
            self._add_to_torrserver(selected_source)
        elif action == "download_file":
            self._download_file(selected_source)
        elif action == "subtitle_download":
            self._resolve_item(selected_source, is_subtitle_download=True)
        elif action == "pack_select":
            self._resolve_item(selected_source, pack_select=True)
        elif action == "upload_subtitle":
            self._upload_subtitle(selected_source)

    def _handle_quality_select_action(self):
        quality_list = self.getControl(1300)
        selected_item = quality_list.getSelectedItem()
        if selected_item:
            selected_quality = selected_item.getProperty("quality")
            filtered_sources = list(self.sources) if selected_quality == '__all__' else [
                s for s in self.sources if _quality_key(_source_quality(s)) == selected_quality]
            if not filtered_sources:
                kodilog("No sources found matching the filter")
                return
            self.filtered_sources = filtered_sources
            self.filter_applied = selected_quality != '__all__'
            self._filter_spec = ('quality_tab', selected_quality) if self.filter_applied else None
            self.populate_sources_list()
            self.set_default_focus(self.display_list, 1000, control_list_reset=True)

    def _handle_select_action(self, control_id):
        self.position = self.display_list.getSelectedPosition()
        if not 0 <= self.position < len(self.list_sources):
            return
        if getattr(self, 'source_session', None):
            item = self.display_list.getSelectedItem()
            key = item.getProperty('source_key') if item else ''
            self.source_session.focus(key, self.position)
            selected_source = self.source_session.capture(self.source_session.epoch, key)
            if selected_source is None:
                self.last_error = '片源列表已更新，请重新选择当前显示的版本'
                self.setProperty('playback_error', self.last_error)
                return
        else:
            selected_source = self.list_sources[self.position]

        control_list = self.getControl(control_id)
        self.set_cached_focus(control_id, control_list.getSelectedPosition())
        self._resolve_item(selected_source, pack_select=False)
        if getattr(self, 'source_session', None):
            if self._selection_locked:
                self.source_pump.cancel()
            else:
                self.source_session.reopen()

    def populate_sources_list(self) -> None:
        self.display_list.reset()
        self.list_sources = (
            self.filtered_sources
            if self.filter_applied and self.filtered_sources is not None
            else self.sources
        )
        if getattr(self, 'source_session', None):
            self.list_sources = _manual_source_limit(self.list_sources, self.source_session.limit)
        aliases = {}
        with contextlib.suppress(Exception):
            aliases = cache.get(STREMIO_ADDON_ALIASES_KEY) or {}

        chinese_subtitle_count = sum(
            1 for source in self.list_sources if _has_chinese_candidate(source)
        )
        self.setProperty("chinese_subtitle_count", str(chinese_subtitle_count))
        self.setProperty("source_count", str(len(self.list_sources)))

        from lib.utils.general.cinema_source_rank import source_preference
        menu_items = []
        for position, source in enumerate(self.list_sources):
            info = parse_title_info(source.title)
            menu_item = xbmcgui.ListItem(label=source.title)
            if getattr(self, 'source_session', None):
                menu_item.setProperty('source_key', self.source_session.key(source))
            menu_item.setProperty("title", source.title)
            menu_item.setProperty("display_title", info["clean_title"])
            menu_item.setProperty("codec", info["codec"])
            menu_item.setProperty("audio", info["audio"])
            menu_item.setProperty("hdr_info", info["badges"])
            menu_item.setProperty("badges_plain", _plain_source_badges(info["badges"]))
            release_group = info["release_group"] or ""
            from lib.cinema.subtitle_projection import source_card_label, source_label
            chinese_subtitles = detect_chinese_subtitle_kind(
                source.title,
                languages=getattr(source, "languages", None),
                full_languages=getattr(source, "fullLanguages", None),
                stream_subtitles=getattr(source, "streamSubtitles", None),
                metadata=getattr(source, "stremioMetadata", None),
            )
            menu_item.setProperty("chinese_subtitle_detail", source_label(source) or chinese_subtitles)
            chinese_subtitles = source_card_label(source) or chinese_subtitles
            from lib.utils.general.cinema_source_rank import chinese_subtitle_preference
            subtitle_evidence = chinese_subtitle_preference(source)[1]
            if subtitle_evidence and not source_label(source):
                chinese_subtitles = subtitle_evidence
                menu_item.setProperty('chinese_subtitle_detail', subtitle_evidence)
            menu_item.setProperty("release_group", release_group)
            menu_item.setProperty("show_release_group", "true" if _show_release_group(getattr(self, "item_information", {}), source) else "false")
            menu_item.setProperty("provider_raw", release_group)
            menu_item.setProperty("chinese_subtitles", chinese_subtitles)
            from lib.clients.catalog_providers import provider_for
            if provider_for(source):
                # A file named bilingual has not established subtitle presence
                # or synchronization. Keep provenance separate from evidence.
                chinese_subtitles = subtitle_evidence
                menu_item.setProperty('chinese_subtitles', subtitle_evidence)
                menu_item.setProperty('chinese_subtitle_detail', subtitle_evidence or '字幕未验证')
                menu_item.setProperty('source_provenance', source.subindexer)
            menu_item.setProperty(
                "has_chinese_subtitles", "true" if chinese_subtitles else "false"
            )
            kodilog(f"SourceSelect populate_sources_list: source.type={source.type}")
            if source.type in IndexerType.TORRENT:
                if source.addedToDebrid and source.debridType:
                    provider_name = source.debridType
                else:
                    provider_name = source.type or source.subindexer
            elif source.type == IndexerType.DEBRID:
                provider_name = source.debridType or source.type
            elif source.type == IndexerType.STREMIO_DEBRID:
                if source.debridType:
                    provider_name = source.debridType
                elif source.isCached and not source.infoHash:
                    provider_name = source.type
                else:
                    provider_name = source.subindexer or source.type
            elif source.type == IndexerType.DIRECT:
                provider_name = source_platform_label(source) or source.type
            else:
                provider_name = source.debridType or source.type
            indexer_label = _get_source_indexer_label(source, aliases)
            menu_item.setProperty("type", get_provider_color(provider_name))
            menu_item.setProperty("indexer", get_random_color(indexer_label))
            menu_item.setProperty("source_site", source_site_label(indexer_label, source.type))
            menu_item.setProperty("guid", source.guid)
            menu_item.setProperty("infoHash", source.infoHash)
            menu_item.setProperty("size", bytes_to_human_readable(int(source.size)))
            if source.seeders and not source.isCached:
                menu_item.setProperty("seeders", str(source.seeders))
            if source.peers and not source.isCached:
                menu_item.setProperty("peers", str(source.peers))
            menu_item.setProperty("fullLanguages", get_colored_languages(source.fullLanguages))
            # The primary provider field is intentionally the release/encode
            # group, not the indexer website.  The source site remains available
            # separately as a low-priority diagnostic label.
            menu_item.setProperty("provider", get_random_color(release_group) if release_group else '')
            menu_item.setProperty("publishDate", extract_publish_date(source.publishDate))
            menu_item.setProperty("quality", source.quality)
            menu_item.setProperty("quality_plain", _source_quality(source))
            menu_item.setProperty("type_plain", _provider_display_name(provider_name))
            menu_item.setProperty("languages_plain", _plain_source_label(get_colored_languages(source.fullLanguages)))
            menu_item.setProperty("status", get_source_status(source))
            status = _plain_source_label(get_source_status(source))
            status = {"Download": "待验证片源", "Cached": "服务标记已缓存", "Added": "已提交 · 待就绪"}.get(status, status)
            menu_item.setProperty("status_plain", status)
            preference = source_preference(source, getattr(self, "item_information", {}))
            from lib.cinema.source_presentation import recommendation_label
            first_label = recommendation_label(True, preference['caution'], status)
            recommended = (self.source_session.key(source) == getattr(self, '_recommended_key', None)
                           if getattr(self, 'source_session', None) else position == 0)
            menu_item.setProperty("recommendation", first_label if recommended else "")
            menu_item.setProperty("recommendation_reason", preference["reason"])
            menu_item.setProperty("recommendation_status", recommendation_label(recommended, preference['caution'], status))
            menu_item.setProperty("isPack", str(source.isPack))

            menu_items.append(menu_item)
        self.display_list.addItems(menu_items)

    def _refresh_sources_list(self) -> None:
        if not hasattr(self, "display_list"):
            return

        current_position = max(getattr(self, "position", 0), 0)
        self.populate_sources_list()
        if self.list_sources:
            self.set_default_focus(self.display_list, 1000, control_list_reset=True)
            self.display_list.selectItem(min(current_position, len(self.list_sources) - 1))

    def _download_to_debrid(self, selected_source) -> None:
        kodilog("SourceSelect _download_to_debrid entered")
        url, magnet, _ = self._extract_source_details(selected_source)
        info_hash = selected_source.infoHash or ""
        torrent_data = b""

        if not info_hash and magnet:
            info_hash = get_info_hash_from_magnet(magnet).lower()

        if not info_hash and url.startswith("magnet:"):
            info_hash = get_info_hash_from_magnet(url).lower()

        if url:
            kodilog(f"Fetching torrent URL to extract info_hash: {url}")
            torrent_data, magnet_candidate, extracted_hash, torrent_url = get_torrent_data_from_uri(
                url
            )
            if magnet_candidate and not magnet:
                magnet = magnet_candidate
            if extracted_hash and not info_hash:
                info_hash = extracted_hash
            if torrent_url:
                selected_source.url = torrent_url

        if not info_hash and not torrent_data:
            notification(translation(90361))
            return

        debrid_type = add_source_to_debrid(
            info_hash,
            selected_source.debridType,
            torrent_data=torrent_data,
            torrent_name=selected_source.title or self.item_information.get("title", ""),
        )
        if debrid_type:
            kodilog(f"SourceSelect download_to_debrid succeeded via {debrid_type}")
            if info_hash:
                selected_source.infoHash = info_hash
            selected_source.debridType = debrid_type
            selected_source.addedToDebrid = True
            self._refresh_sources_list()

    def _add_to_torrserver(self, selected_source) -> None:
        url, magnet, _ = self._extract_source_details(selected_source)
        title = selected_source.title or self.item_information.get("title", "")
        poster = self.item_information.get("poster", "")

        import json as _json

        metadata = {
            "title": title,
            "mode": self.item_information.get("mode", ""),
            "ids": self.item_information.get("ids", {}),
            "tv_data": self.item_information.get("tv_data", {}),
        }
        data = _json.dumps(metadata)

        add_source_to_torrserver(
            magnet=magnet,
            url=url,
            info_hash=selected_source.infoHash or "",
            title=title,
            poster=poster,
            data=data,
            category=self.item_information.get("mode"),
        )

    def _download_file(self, selected_source) -> None:
        self.playback_info = self._ensure_playback_info(selected_source)
        if self.playback_info:
            self.playback_info.update(self.item_information)
        else:
            notification(translation(90407))
            return

        try:
            title = (
                self.playback_info.get("title") or self.item_information.get("title") or ""
            ).strip()
            year = self.item_information.get("year", "")
            tv_data = self.playback_info.get("tv_data")
            if isinstance(tv_data, str):
                tv_data = safe_json_loads(tv_data, {})
            tv_data = normalize_tv_data(tv_data)
            if tv_data and tv_data.get("season") and tv_data.get("episode"):
                season = int(tv_data["season"])
                episode = int(tv_data["episode"])
                file_name = f"{title} - {format_season_episode(season, episode)}"
            elif year:
                file_name = f"{title} ({year})"
            else:
                file_name = title

            mode = self.playback_info.get("mode", "movie")
            dest_data = {
                "title": title,
                "mode": "movies" if mode in ("movie", "movies") else mode,
            }
            if tv_data:
                dest_data["tv_data"] = tv_data

            from lib.downloader import get_destination_path

            destination = get_destination_path(dest_data)
            if not destination:
                notification(translation(90407))
                return

            xbmc.executebuiltin(
                action_url_run(
                    "handle_download_file",
                    file_name=file_name,
                    url=self.playback_info["url"],
                    destination=destination,
                )
            )
        except Exception as e:
            kodilog(f"Failed to start download: {e!s}")
            xbmcgui.Dialog().notification(translation(90653), translation(90654) % str(e))

    def _upload_subtitle(self, selected_source) -> None:
        """Show upload subtitle dialog with local/web options."""
        kodilog("[UPLOAD_SUBTITLE] Starting subtitle upload process")
        dialog = xbmcgui.Dialog()
        options = [
            translation(90746),  # Local File
            translation(90747),  # Upload from Browser
        ]
        choice = dialog.select(translation(90744), options)  # Upload Subtitle

        if choice == 0:  # Local file
            self._upload_subtitle_local(selected_source)
        elif choice == 1:  # Web upload
            self._upload_subtitle_from_web(selected_source)

    def _upload_subtitle_local(self, selected_source) -> None:
        """Open file browser to select a local subtitle file and resolve the source with it."""
        dialog = xbmcgui.Dialog()
        subtitle_file = dialog.browse(
            1, translation(90745), "files", ".srt|.ass|.ssa|.sub|.vtt|.txt"
        )
        if not subtitle_file:
            kodilog("[UPLOAD_SUBTITLE] User cancelled subtitle upload (no file selected)")
            return
        self._resolve_item(selected_source, local_subtitle_path=subtitle_file)

    def _upload_subtitle_from_web(self, selected_source) -> None:
        """Start web server and show QR dialog for browser-based subtitle upload."""
        kodilog("[UPLOAD_SUBTITLE] Starting web upload server")

        local_ip = get_local_ip()
        server = SubtitleUploadServer(port=8082)
        server.start()

        if not server.is_running:
            kodilog("[UPLOAD_SUBTITLE] Failed to start upload server")
            notification(translation(90744))
            return

        url = f"http://{local_ip}:{server.port}/"

        subtitle_result = [None]  # Use list for mutability in nested function
        dialog = None
        upload_complete = threading.Event()

        try:
            kodilog(f"[UPLOAD_SUBTITLE] Server started at {url}")

            # Generate QR code
            qr_path = make_qrcode(url)

            # Show QR dialog
            dialog = QRProgressDialog("qr_dialog.xml", ADDON_PATH)
            dialog.setup(
                title=translation(90748),  # Upload subtitle from your browser
                qr_code=qr_path or "",
                url=url,
                user_code="",
                is_debrid=False,
                custom_message=translation(90749) % url,
            )

            # Start polling thread to detect upload completion
            def poll_for_upload():
                kodilog("[UPLOAD_SUBTITLE] Polling thread started")
                import time

                poll_count = 0
                while not upload_complete.is_set():
                    time.sleep(0.5)
                    poll_count += 1

                    # Check if file was uploaded
                    file_path = server.get_uploaded_file()
                    if file_path:
                        kodilog(f"[UPLOAD_SUBTITLE] File detected via polling: {file_path}")
                        subtitle_result[0] = file_path
                        upload_complete.set()
                        # Close dialog from thread
                        try:
                            dialog.close()
                        except Exception as e:
                            kodilog(f"[UPLOAD_SUBTITLE] Error closing dialog from thread: {e}")
                        break

                    # Timeout after 10 minutes
                    if poll_count > 1200:
                        kodilog("[UPLOAD_SUBTITLE] Polling timeout")
                        upload_complete.set()
                        with contextlib.suppress(BaseException):
                            dialog.close()
                        break
                kodilog("[UPLOAD_SUBTITLE] Polling thread ended")

            # Start polling thread
            poll_thread = threading.Thread(target=poll_for_upload, daemon=True)
            poll_thread.start()

            # Show modal dialog (blocks until closed)
            kodilog("[UPLOAD_SUBTITLE] Showing modal dialog...")
            dialog.doModal()

            # Signal polling thread to stop
            upload_complete.set()

            # Check result
            if subtitle_result[0]:
                kodilog(f"[UPLOAD_SUBTITLE] Upload successful: {subtitle_result[0]}")
            elif dialog.iscanceled:
                kodilog("[UPLOAD_SUBTITLE] User cancelled")
            else:
                kodilog("[UPLOAD_SUBTITLE] Dialog closed without upload")

        finally:
            upload_complete.set()
            server.stop()
            kodilog("[UPLOAD_SUBTITLE] Web upload server stopped")

        # If we got a file, resolve the source with it
        if subtitle_result[0]:
            self._resolve_item(selected_source, local_subtitle_path=subtitle_result[0])

    def _resolve_item(
        self,
        selected_source,
        pack_select: bool = False,
        is_subtitle_download=False,
        local_subtitle_path: Optional[str] = None,
    ) -> None:
        if not getattr(self, "_native_owner", False):
            from lib.portable import queue_selected
            return queue_selected(self, selected_source, pack_select, is_subtitle_download, local_subtitle_path)
        if not pack_select and not is_subtitle_download:
            if self._selection_locked:
                return
            self._selection_locked = True
            self.last_error = ""
            # A binding belongs to one selected release, not the reusable list.
            self.item_information.pop("episode_binding", None)
            self.item_information["request_id"] = uuid4().hex
            self.item_information["selection_policy"] = "exact"
            from lib.cinema.playback_request import select, source_identity
            try:
                select(self._control_snapshot, self.item_information['request_id'], source_identity(selected_source))
            except (AttributeError, OSError, ValueError, RuntimeError):
                self._selection_locked = False
                self.last_error = '片源选择已变化或播放控制不可用，请重试'
                self.setProperty('playback_error', self.last_error)
                return
            set_property("bobbi_cinema_selection", self.item_information["request_id"])
            # Invalidate an older pending child immediately, before this source
            # starts potentially slow resolution.
            set_property("bobbi_active_player_session", self.item_information["request_id"])
            self._pending_selection = (selected_source, {
                "is_subtitle_download": False,
                "local_subtitle_path": local_subtitle_path,
            })
            self.setProperty("instant_close", "true")
            self.close()
            return
        self.setProperty("resolving", "true")
        # Explicit advanced actions must not inherit a failed exact request.
        advanced_information = dict(self.item_information)
        for key in ("selection_policy", "request_id", "episode_binding", "direct_playback_handoff"):
            advanced_information.pop(key, None)
        resolver_window = ResolverWindow(
            "resolver.xml",
            ADDON_PATH,
            source=selected_source,
            previous_window=self,
            item_information=advanced_information,
            is_subtitle_download=is_subtitle_download,
            local_subtitle_path=local_subtitle_path,
        )
        self.resolved = resolver_window.doModal(pack_select)
        del resolver_window

    def show_resume_dialog(self, playback_percent: float) -> Optional[bool]:
        try:
            resume_window = ResumeDialog(
                "resume_dialog.xml",
                ADDON_PATH,
                resume_percent=playback_percent,
            )
            resume_window.doModal()
            return resume_window.resume
        finally:
            del resume_window

    def _get_all_languages(self):
        all_languages = set()
        for s in self.sources:
            all_languages.update(getattr(s, "languages", []))
            all_languages.update(getattr(s, "fullLanguages", []))
        return sorted(all_languages)
