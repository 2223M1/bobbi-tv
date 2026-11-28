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
from lib.cinema import source_filters
from lib.utils.general.release_quality import cinema_quality_order, quality_text, release_quality
from lib.utils.general.source_platform import source_libraries, source_platform_label
from lib.gui.base_window import BaseWindow, _CAPTURE_PLAYBACK
from lib.gui.filter_items_window import FilterWindow
from lib.gui.filter_type_window import FilterTypeWindow
from lib.gui.qr_progress_dialog import QRProgressDialog
from lib.gui.resolver_window import ResolverWindow
from lib.gui.resume_window import ResumeDialog

# Lazy placeholders so importing source_select never eagerly imports requests/webserver
StremioWebServer = None
get_local_ip = None
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
    # Retain stable filter keys while grouping by size, not display scan mode.
    if value in {'4k', '2160', '2160p', '2160i'}:
        return '4k'
    if value in {'1080', '1080p', '1080i'}:
        return '1080p'
    if value in {'720', '720p', '720i'}:
        return '720p'
    return 'n/a'


def _source_quality(source):
    value = _plain_source_label(getattr(source, 'quality', '')).strip()
    # A class-derived upstream badge can say "1080p" for a 1080i filename or
    # dimensions alone. Use the same conservative display as the rank reason.
    if (value.casefold() not in ('', 'n/a', 'unknown', '未知')
            and not re.fullmatch(r'(?:[48]k|(?:4320|2160|1080|720|576|480)[pi]?)', value, re.I)):
        return value
    from lib.utils.general.source_resolution import source_resolution_label
    return source_resolution_label(source)


def _quality_tabs(sources, active=None):
    from collections import Counter
    counts = Counter(_quality_key(_source_quality(source)) for source in sources)
    return [('全部', '__all__', len(sources))] + [(label, key, counts[key]) for label, key in
            [('4K', '4k'), ('1080', '1080p'), ('720', '720p'), ('其他', 'n/a')] if counts[key] or key == active]


def _plain_source_badges(value):
    text = _plain_source_label(value)
    text = re.sub(r'(?i)(?:\b(?:VIDEO|AUDIO|FORMAT|SOURCE|HDR|LANG|NOTE|EDITION)|视频|音频|封装|版本)\s*[:：]\s*', '', text)
    text = re.sub(r'\b(?:DV|DOLBY VISION)\b', '杜比视界', text, flags=re.I)
    text = re.sub(r'\bATMOS\b', 'Atmos', text, flags=re.I)
    return ' · '.join(dict.fromkeys(part.strip() for part in re.split(r'[·•|]+', text) if part.strip()))


def _manual_source_limit(sources, limit):
    """Apply one display budget after the complete, provider-neutral ranking."""
    return sources[:limit]


def _source_card_fields(template, skin):
    if skin == 'skin.bobbi.cinema' and template in ('source_select.xml', 'source_select_direct.xml'):
        # Bundled XML, its quality variable, selection identity and diagnostics.
        # Other skins/templates retain the complete legacy property contract.
        return frozenset(('type_plain', 'title', 'chinese_subtitles', 'badges_plain',
            'release_group', 'size', 'seeders', 'languages_plain', 'source_site',
            'recommendation_status', 'quality_plain', 'source_key', 'peers',
            'status_plain', 'recommendation_reason', 'version_hint'))
    return None


class _CardUpdate:
    """Project owned fields once; retain the native item and its GUI locking."""
    def __init__(self, item, previous, fields=None):
        self.item = item
        self.previous = previous
        self.fields = fields
        self.values = {}

    def setProperty(self, key, value):
        if self.fields is None or key in self.fields:
            self.values[key] = value

    def flush(self):
        changed = {key: self.values.get(key, '')
                   for key in self.values.keys() | self.previous.keys()
                   if self.values.get(key, '') != self.previous.get(key, '')}
        if changed:
            # setProperties still takes Kodi's per-field GUI locks. Avoid
            # native reads, duplicate writes, and repeated Python crossings,
            # not the locks required for already-visible WindowXML items.
            self.item.setProperties(changed)
        self.previous.clear()
        self.previous.update(self.values)


def _has_chinese_candidate(source):
    from lib.utils.general.cinema_source_rank import chinese_subtitle_preference
    return source_has_chinese_subtitles(source) or bool(chinese_subtitle_preference(source)[0])


def _provider_display_name(value):
    """Translate presentation only, never rewrite the provider or resolver type."""
    plain = _plain_source_label(value)
    translated = {'Torrent': 'BT种子', 'Direct': '直连资源', 'Debrid': '离线服务'}.get(plain, plain)
    return source_site_label(translated, 'Direct')


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
        playback_client=_CAPTURE_PLAYBACK,
    ):
        super().__init__(xml_file, location, item_information=item_information,
                         playback_client=playback_client)
        self._card_fields = _source_card_fields(xml_file, xbmc.getSkinDir())
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
        from bobbi_platform.source_libraries import capture_context
        captured = capture_context()
        self._share_reader = captured.reader if captured is not None else None
        self._catalog_source = captured.source if captured is not None else None
        self._preferences = source_filters.Preferences(captured.binding) if captured is not None else None
        self._filters = self._preferences.read() if self._preferences else {}
        self.filter_applied = bool(self._filters)
        if self.filter_applied:
            self.filtered_sources = self._filtered_rows(self.sources)
        self._filter_summary = source_filters.summary(self._filters)
        self.source_pump = None
        self._source_revision = -1
        self._source_interacted = False
        self._retry_shown = False
        self.setProperty('source_empty_title', '没有符合条件的片源')
        self._show_filter_status()
        self._auto_select_pending = False  # Manual source selection is product policy.

    def onInit(self) -> None:
        guard = getattr(self, '_next_picker_guard', None)
        if guard is not None:
            from lib.utils.player.next_source_picker import picker_note, picker_status
            picker_note('WINDOW_INIT')
            self._next_picker_guard = None
            snapshot = picker_status(guard, playback_client=self.playback_client)
            if snapshot is None:
                self.close()
                return
            self._control_snapshot = snapshot
        # Kodi recreates controls when a closed resolver returns to this dialog.
        self._rendered_cards = {}
        self._rendered_card_values = {}
        self._rendered_keys = []
        self._quality_items = {}
        self._quality_keys = []
        self.setProperty("playback_error", self.last_error)
        theme_index = get_setting("source_select_theme", "0")
        theme = THEMES.get(str(theme_index), THEMES["0"])
        if xbmc.getSkinDir() == "skin.bobbi.cinema":
            theme = {"card_bg": "FF18181C", "card_focus": "FF34343C", "card_accent": "FFF4F4F5"}
        self.setProperty("style.card_bg", theme["card_bg"])
        self.setProperty("style.card_focus", theme["card_focus"])
        self.setProperty("style.card_accent", theme["card_accent"])

        self.display_list: xbmcgui.ControlList = self.getControlList(1000)
        self.getControl(1300).reset()  # Once per actual window opening.
        if getattr(self, 'source_session', None):
            # Render one current snapshot before accepting GUI focus receipts.
            # selectItem is queued; reading the old native selection here would
            # overwrite the card captured before the resolver closed us.
            self._refresh_progressive_sources(capture_focus=False, force=True)
        else:
            self.populate_qualities_header()
            self.populate_sources_list()
        # A newly opened recommendation list starts at its first card, not an
        # ordinal saved for an older, differently ordered search result set.
        if self.list_sources:
            position = self._restore_position if self._restore_position is not None else 0
            restored = getattr(self, '_restore_key', None)
            if restored and self.source_session:
                position = next((i for i, row in enumerate(self.list_sources)
                                 if self.source_session.key(row) == restored), position)
            self.display_list.selectItem(max(0, min(position, len(self.list_sources) - 1)))
            self.setFocus(self.display_list)
        else:
            self.setFocusId(1400 if self.filter_applied else 1300)
        super().onInit()
        if hasattr(self, '_source_ready'):
            self._source_ready.set()
        if guard is not None and self.list_sources:
            picker_note('FIRST_CARDS_BOUND')

    def populate_qualities_header(self):
        qualities_list = self.getControl(1300)
        items = getattr(self, '_quality_items', {})
        keys = getattr(self, '_quality_keys', [])
        selected = qualities_list.getSelectedItem() if keys else None
        selected_key = selected.getProperty('quality') if selected else None
        rules = getattr(self, '_filters', {})
        saved_quality = rules.get('quality')
        active = _quality_key(saved_quality[1]) if saved_quality else '__all__'
        self.setProperty('selected_quality', active)
        if not keys and saved_quality:
            selected_key = _quality_key(saved_quality[1])
        selected_position = keys.index(selected_key) if selected_key in keys else 0
        rebound = False
        available = self.sources
        for axis, (kind, value, _) in rules.items():
            if axis != 'quality':
                available = self._apply_source_filter(kind, value, sources=available)
        desired = _quality_tabs(available, active)
        wanted = {key for _, key, _ in desired}
        for position in range(len(keys) - 1, -1, -1):
            if keys[position] not in wanted:
                items.pop(keys.pop(position))
                qualities_list.removeItem(position)
                rebound = True
        self.setProperty("quality_item_width", '200')
        for display, key, count in desired:
            label = f"{display} ({count})"
            if key in items:
                if items[key].getLabel() != label:
                    items[key].setLabel(label)
            else:
                list_item = xbmcgui.ListItem(label)
                list_item.setProperty("quality", key)
                qualities_list.addItem(list_item)
                rebound = True
                items[key] = list_item
                keys.append(key)
        self._quality_items, self._quality_keys = items, keys
        if rebound and keys:
            # Kodi queues LABEL_BIND (which selects zero). Queue compensation
            # AFTER it even when a synchronous read still reports the old index.
            # No timer/delayed retry: subsequent user navigation wins normally.
            qualities_list.selectItem(keys.index(selected_key) if selected_key in keys
                                      else min(selected_position, len(keys) - 1))

    def doModal(self) -> bool:
        from lib.native_support import available
        self._native_owner = available()
        if not self._native_owner:
            if '_next_picker_context' in self.item_information:
                from lib.utils.player.next_source_picker import picker_note
                picker_note('NATIVE_UNAVAILABLE')
                return False  # An EOF permit cannot downgrade to an unguarded portable UI.
            from lib.portable import manual_modal
            return manual_modal(self, lambda: super(SourceSelect, self).doModal())
        # An automatic EOF entry is not a fresh user click. Preserve its CAS
        # snapshot and reject superseded GUI/account intent before first show.
        next_picker = self.item_information.pop('_next_picker_context', None)
        if next_picker is not None:
            from lib.utils.player.next_source_picker import picker_note, picker_status
            self._next_picker_guard = dict(_next_picker_context=next_picker,
                                          _account=self.item_information.get('_account'))
        prepared_retry = None
        prepared_retry_cancelled = None
        after_failed_source = False
        while True:
            read_snapshot = self.playback_client.read_snapshot
            try:
                if next_picker is not None:
                    # Recheck after window construction, not just before search.
                    self._control_snapshot = picker_status(dict(
                        _next_picker_context=next_picker, _account=self.item_information.get('_account')),
                        playback_client=self.playback_client)
                    next_picker = None
                    if self._control_snapshot is None:
                        return False
                    picker_note('WINDOW_PERMITTED')
                else:
                    self._control_snapshot = read_snapshot()
            except (OSError, ValueError, RuntimeError):
                self.last_error = '播放器尚未就绪，请稍后重试'
                self.setProperty('playback_error', self.last_error)
                # This dialog has not been shown yet; a property alone is invisible.
                notification(self.last_error, time=5000)
                if getattr(self, 'source_pump', None):
                    self.source_pump.cancel()
                if getattr(self, 'source_session', None):
                    self.source_session.cancel()
                return False
            self._pending_selection = None
            self._selection_locked = False
            self.setProperty("instant_close", "false")
            self.setProperty("resolving", "false")
            if prepared_retry is not None:
                from lib.cinema.prepared_retry import unchanged
                cloud_source, prior_snapshot, retry_account = prepared_retry
                prepared_retry = None
                retry_cancelled = prepared_retry_cancelled
                prepared_retry_cancelled = None
                if ((retry_cancelled and retry_cancelled())
                        or not unchanged(prior_snapshot, self._control_snapshot)):
                    return False  # A new selection/restart wins over a late retry.
                self._resolve_item(cloud_source, retry_account=retry_account, retry_cancelled=retry_cancelled)
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
                playback_client=self.playback_client,
                item_information=dict(self.item_information, _retry_after_failed_source=after_failed_source), **options,
                share_reader=getattr(getattr(self, 'source_session', None), 'share_reader', getattr(self, '_share_reader', None)),
            )
            self.resolved = resolver.doModal(False)
            self.last_error = getattr(resolver, "error_message", "")
            failure = getattr(resolver, 'share_failure', None)
            if (isinstance(failure, dict) and failure.get('code') in {'share_revoked', 'identity_changed'}
                    and getattr(self, 'source_session', None)):
                self.source_session.invalidate_share(self.source_session.epoch, source, failure['code'],
                                                     state=failure.get('share_state'))
            self._resolution_answered = self._resolution_answered or getattr(resolver, "resolution_answered", False)
            if (not self.resolved and not resolver.user_cancelled
                    and resolver.startup_failure_category in {'buffer_timeout', 'preload_error', 'prepared_ready'}
                    and isinstance(resolver.playback_info, dict)):
                from lib.cinema.prepared_retry import ready_source
                def retry_cancelled(pending=resolver, request_id=self.item_information.get('request_id')):
                    return (pending.user_cancelled or xbmc.Monitor().abortRequested()
                        or (pending.startup_failure_category == 'prepared_ready' and
                            (pending.cancel_event.is_set() or get_property('bobbi_cinema_cancel') == request_id)))
                prepared_retry = ready_source(resolver.playback_info, resolver.startup_failure_category,
                    resolver.preparation_intent, retry_cancelled,
                    session=getattr(resolver, 'prepared_session', None))
                if prepared_retry:
                    prepared_retry_cancelled = retry_cancelled
                    kodilog('[CINEMA-PREPARE] SAME_FILE_CLOUD_RETRY request='
                            + self.item_information['request_id'])
            del resolver
            if self.resolved:
                return True
            if get_property("bobbi_cinema_selection") != self.item_information.get("request_id"):
                return False
            after_failed_source = True
            if prepared_retry is not None:
                continue  # One new exact request; never repeat the failed BT opener.
            self._restore_position = self.position
            self._restore_key = self.source_session.key(source) if getattr(self, "source_session", None) else None
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
        # A manual cursor position must not change the automatic recommendation.
        snapshot = self.source_session.snapshot(full=True,
            pin_focus=not cinema_quality_order(getattr(self, 'item_information', {})))
        from lib.utils.general.cinema_source_rank import source_preference
        context = dict(self.item_information, **snapshot['metadata'])
        allowed = (set(self.source_session.key(s) for s in self._filtered_rows([s for _, s in snapshot['entries']]))
                   if getattr(self, 'filter_applied', False) else None)
        choice = next(((key, source) for key, source in snapshot['entries']
                       if (allowed is None or key in allowed) and not source_preference(source, context)['caution']), None)
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
        # Preserve the actual card under the cursor when later providers rank
        # ahead of it. Its ordinal is not part of the release's identity.
        preserve_focus = bool(self.list_sources)
        if capture_focus and self.list_sources and preserve_focus:
            item = self.display_list.getSelectedItem()
            if item:
                self.source_session.focus(item.getProperty('source_key'), self.display_list.getSelectedPosition())
        snapshot = self.source_session.snapshot(full=True,
            pin_focus=not cinema_quality_order(getattr(self, 'item_information', {})),
            after_content_revision=None if force else getattr(self, '_source_content_revision', None))
        self._source_revision = snapshot['revision']
        self._source_content_revision = snapshot['content_revision']
        self._recommended_key = snapshot['recommended_key']
        self.setProperty('source_coalesced_count', str(snapshot.get('superseded_count', 0)))
        if snapshot['metadata'] and (force or snapshot['metadata'] !=
                                     getattr(self, '_applied_source_metadata', None)):
            self.add_item_information_to_window(dict(self.item_information, **snapshot['metadata']))
            # A status receipt carries the same metadata snapshot. Do not turn
            # each provider tick into another full native header/queue update.
            self._applied_source_metadata = snapshot['metadata']
        if snapshot['entries'] is not None:
            self.sources = [source for _, source in snapshot['entries']]
            self.populate_qualities_header()
            if self.filter_applied:
                self.filtered_sources = self._filtered_rows(self.sources)
            self.populate_sources_list(incremental=not force)
        if self.list_sources and not capture_focus:
            keys = [self.source_session.key(source) for source in self.list_sources]
            position = keys.index(self.source_session.focus_key) if self.source_session.focus_key in keys else min(
                self.source_session.focus_position, len(keys) - 1)
            self.display_list.selectItem(position)
        pending = sum(row['state'] not in self.source_session.TERMINAL for row in snapshot['providers'].values())
        self.setProperty('source_loading', 'true' if pending else 'false')
        pump = getattr(self, 'source_pump', None)
        retryable = bool(pump and pump.retry_candidates())
        self._retry_shown = getattr(self, '_retry_shown', False) or (retryable and not pending)
        self.setProperty('source_retry_visible', 'true' if self._retry_shown else 'false')
        self.setProperty('source_retry_label', '正在查询…' if pending else
                         '补查失败来源' if retryable else '查询已完成')
        from lib.cinema.source_presentation import search_status
        summary, error, diagnostic = search_status(snapshot['providers'], bool(self.sources))
        self.setProperty('source_empty_title', '部分来源查询未完成' if error and not self.sources
                         else '没有符合条件的片源')
        self.setProperty('source_empty_hint', '部分来源未查完，可点击“补查失败来源”重试'
                         if error and not self.sources else
                         '按上键选择“全部”清晰度，或放宽筛选条件')
        if not pending and not getattr(self, '_provider_terminal_logged', False):
            from lib.cinema.source_presentation import provider_diagnostics
            self._provider_terminal_logged = True
            kodilog('BOBBI-PROVIDERS ' + json.dumps(provider_diagnostics(snapshot['providers']),
                                                  ensure_ascii=True, sort_keys=True), level=xbmc.LOGINFO)
        if self._auto_select_pending and not self._source_interacted:
            summary = '正在自动选源，操作列表可改为手选'
        if snapshot.get('superseded_count'):
            summary += ' · {} 个同版 BT 已由 115 替代'.format(snapshot['superseded_count'])
        self._base_source_status = summary
        if getattr(self, '_filter_summary', ''):
            self._show_filter_status()
        else:
            self.setProperty('source_status', summary)
        self.setProperty('source_diagnostics', diagnostic)
        self.setProperty('source_error', error)
        self.setProperty('playback_error', self.last_error)

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
        if action_id == 7 and control_id == 1500:
            self._retry_failed_sources()
        elif action_id == 7 and control_id == 1400:
            self._handle_filter_action()
        elif action_id == 117:  # Context menu action
            self._handle_context_menu_action()
        elif action_id == 7 and control_id == 1300:
            self._handle_quality_select_action()
        elif action_id == 7 and control_id == 1000:  # Select action
            self._handle_select_action(control_id)

    def _retry_failed_sources(self):
        pump = getattr(self, 'source_pump', None)
        if pump is None or not pump.retry_candidates():
            return
        if not pump.retry_failed():
            self.setProperty('source_status', '上次查询尚未结束，可先选择已有片源')
            return
        self._provider_terminal_logged = False
        self._refresh_progressive_sources()  # Incremental only; keep native cards/filter/focus.

    def _show_filter_status(self):
        summary = getattr(self, '_filter_summary', '')
        status = getattr(self, '_base_source_status', '')
        self.setProperty('filter_button_label', '已筛选' if summary else '筛选')
        self.setProperty('source_status', '   ·   '.join(x for x in (('已筛选 · ' + summary) if summary else '', status) if x))
        self.setProperty('source_empty_hint', '当前筛选：' + summary + '。可在“筛选”中重置。'
                         if summary else '按上键选择“全部”清晰度，或放宽筛选条件')

    def _filtered_rows(self, rows):
        rules = getattr(self, '_filters', {})
        if not rules:
            legacy = getattr(self, '_filter_spec', None)
            return self._apply_source_filter(*legacy, sources=rows) if legacy else list(rows)
        active = rules.get('source')
        if active and active[0] == 'library':
            name = next((n for row in rows if (n := source_libraries(row).get(active[1]))), None)
            if name and name != active[2]:
                rules['source'] = (active[0], active[1], name)
                self._filter_summary = source_filters.summary(rules)
        for kind, value, _ in rules.values():
            rows = self._apply_source_filter(kind, value, sources=rows)
        return rows

    def _change_filter(self, kind, value=None, label=None):
        rules = dict(getattr(self, '_filters', {}))
        if kind == 'reset':
            rules.clear()
        elif kind == 'clear_source':
            rules.pop('source', None)
        elif kind == 'quality_tab' and value == '__all__':
            rules.pop('quality', None)
        else:
            rule = source_filters.choice(kind, value, label)
            if not rule:
                return
            rules[source_filters.AXIS[kind]] = rule
        self._filters = rules
        self._filter_spec = None
        self.filter_applied = bool(rules)
        self.filtered_sources = self._filtered_rows(self.sources) if rules else None
        self._filter_summary = source_filters.summary(rules)
        self._show_filter_status()
        preferences = getattr(self, '_preferences', None)
        if preferences:
            try:
                preferences.write(rules)
            except (OSError, RuntimeError, ValueError):
                notification('筛选仅对本次生效，未能保存到当前用户')
        elif getattr(self, '_preferences', True) is None:
            notification('筛选仅对本次生效，未能保存到当前用户')
        self.populate_qualities_header()
        self.populate_sources_list()
        if self.list_sources:
            self.set_default_focus(self.display_list, 1000, control_list_reset=True)
        else:
            self.setFocusId(1400)

    def _library_options(self):
        active = getattr(self, '_filters', {}).get('source')
        known = source_filters.catalog_options(getattr(self, '_catalog_source', None))
        current = {}
        for source in self.sources:
            current.update(source_libraries(source))
        if active and active[0] == 'library':
            known.setdefault(active[1], active[2])
        # Current-title matches first, followed by sites and other configured libraries.
        def options(libraries):
            return [('library', key, name) for key, name in sorted(libraries.items(), key=lambda p:(p[1].casefold(),p[0]))]
        sites = sorted({_source_filter_label(s) for s in self.sources if _source_filter_label(s)})
        stations = {key: label for row in self.sources for key, label in
                    (getattr(row, 'sourceStations', {}) or {}).items()}
        result = (options(current) + [('station', key, label) for key, label in
                  sorted(stations.items(), key=lambda p:(p[1].casefold(), p[0]))]
                  + [('indexer', site, site) for site in sites]
                  + options({k:v for k,v in known.items() if k not in current}))
        if active and not any(rule[:2] == active[:2] for rule in result):
            result.append(active)
        return result

    def _handle_filter_action(self):
        filter_type_popup = FilterTypeWindow("filter_type.xml", ADDON_PATH)
        group_sources = [source for source in self.sources if _show_release_group(getattr(self, "item_information", {}), source)]
        filter_type_popup.allow_release_groups = bool(group_sources)
        filter_type_popup.doModal()
        selected_type = filter_type_popup.selected_type
        del filter_type_popup
        if selected_type is None:
            return  # Back cancels the popup without clearing an existing filter.
        if selected_type == 'reset':
            self._change_filter('reset')
            return
        if selected_type == 'indexer':
            options = self._library_options()
            from lib.clients import qqdocs_provider
            others = []
            if qqdocs_provider.enabled():
                from bobbi_catalog.collection_labels import headings
                visible = {key for kind, key, name in options if kind == 'library'}
                others = [('library', k, v) for k, v in sorted(headings().items(), key=lambda p:p[1].casefold())
                          if k not in visible]
            options = [('clear_source', None, '不限源库')] + options
            active = getattr(self, '_filters', {}).get('source')
            selected = active[:2] if active else ('clear_source', None)
            def pick(rows, more=False):
                prefix = {'library': '源库 · ', 'station': 'BT · ', 'indexer': '来源站点 · '}
                popup = FilterWindow("filter_items.xml", ADDON_PATH, filter=[
                    prefix.get(kind, '') + label for kind, _, label in rows]
                    + (['其他腾讯文档源库…'] if more else []))
                popup.active_position = next((i for i, row in enumerate(rows) if row[:2] == selected), None)
                popup.doModal()
                return popup.selected_position
            position = pick(options, bool(others))
            if position == len(options) and others:
                options = others
                position = pick(options)
            if position is not None and 0 <= position < len(options):
                self._change_filter(*options[position])
            return

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

        value_lists = {
            'quality': lambda: get_unique('quality'), 'type': lambda: get_unique('type'),
            'provider': get_release_groups, 'release_group': get_release_groups,
            'language': self._get_all_languages,
        }
        if selected_type in source_filters.FLAGS:
            self._change_filter(selected_type)
        elif selected_type in value_lists:
            items = value_lists[selected_type]()
            if not items:
                if selected_type == 'language':
                    notification(translation(90406))
                return
            popup = FilterWindow("filter_items.xml", ADDON_PATH, filter=items)
            popup.doModal()
            if popup.selected_filter is not None:
                self._change_filter(selected_type, popup.selected_filter)

    def _apply_source_filter(self, kind, value, sources=None):
        sources = self.sources if sources is None else sources
        if kind == 'library':
            return [s for s in sources if value in source_libraries(s)]
        if kind == 'station':
            return [s for s in sources if value in (getattr(s, 'sourceStations', {}) or {})]
        if kind == 'indexer':
            return [s for s in sources if _source_filter_label(s) == value or (value == '漫迪 MDsub' and s.indexer == value)]
        if kind == 'quality':
            return [s for s in sources if _source_quality(s) == value]
        if kind == 'type':
            return [s for s in sources if getattr(s, kind) == value]
        if kind == 'quality_tab':
            return [s for s in sources if _quality_key(_source_quality(s)) == value]
        if kind in ('provider', 'release_group'):
            return [s for s in sources if _show_release_group(getattr(self, 'item_information', {}), s)
                    and parse_title_info(s.title)['release_group'].casefold() == value.casefold()]
        if kind == 'language':
            return [s for s in sources if value in (getattr(s, 'languages', None) or [])
                    or value in (getattr(s, 'fullLanguages', None) or [])]
        if kind == 'chinese_subtitles':
            return [s for s in sources if _has_chinese_candidate(s)]
        if kind in ('only_torrents', 'only_debrid'):
            expected = 'Torrent' if kind == 'only_torrents' else 'Debrid'
            return [s for s in sources if s.type == expected]
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
            self._change_filter('quality_tab', selected_quality)

    def _handle_select_action(self, control_id):
        self.position = self.display_list.getSelectedPosition()
        if not 0 <= self.position < len(self.list_sources):
            return
        if getattr(self, 'source_session', None):
            item = self.display_list.getSelectedItem()
            key = item.getProperty('source_key') if item else ''
            self.source_session.focus(key, self.position)
            selected_source = self.source_session.capture(self.source_session.epoch, key, collect_siblings=True)
            if selected_source is None:
                self.last_error = '片源列表已更新，请重新选择当前显示的版本'
                self.setProperty('playback_error', self.last_error)
                return
        else:
            selected_source = self.list_sources[self.position]

        control_list = self.getControl(control_id)
        self.set_cached_focus(control_id, control_list.getSelectedPosition())
        self._resolve_item(selected_source, pack_select=False)
        # The enclosing search still owns its original deadline and cancellation
        # on exit. An early manual click must not close the retry list's providers.
        if getattr(self, 'source_session', None) and not self._selection_locked:
            self.source_session.reopen()

    def populate_sources_list(self, incremental=False) -> None:
        self.list_sources = (
            self.filtered_sources
            if self.filter_applied and self.filtered_sources is not None
            else self.sources
        )
        key_for = (self.source_session.key if getattr(self, 'source_session', None)
                   else lambda source: str(id(source)))
        cards = getattr(self, '_rendered_cards', {}) if incremental else {}
        card_values = getattr(self, '_rendered_card_values', {}) if incremental else {}
        keys = list(getattr(self, '_rendered_keys', [])) if incremental else []
        if not incremental:
            self.display_list.reset()  # Explicit filter/reopen, never provider publication.
        selected = self.display_list.getSelectedItem() if incremental else None
        selected_key = selected.getProperty('source_key') if selected else None
        selected_position = keys.index(selected_key) if selected_key in keys else 0
        ordered = cinema_quality_order(getattr(self, 'item_information', {}))
        if getattr(self, 'source_session', None):
            candidates = self.list_sources
            self.list_sources = _manual_source_limit(candidates, self.source_session.limit)
            # If the cursor's still-eligible file crossed the display cutoff,
            # reserve the last row for it during this interaction.
            if ordered and selected_key and len(candidates) > len(self.list_sources):
                if not any(key_for(row) == selected_key for row in self.list_sources):
                    keep = next((row for row in candidates[len(self.list_sources):]
                                 if key_for(row) == selected_key), None)
                    if keep is not None:
                        self.list_sources[-1] = keep
        recommended_key = getattr(self, '_recommended_key', None)
        if self.filter_applied:
            eligible = self.filtered_sources or []
            if not any(key_for(s) == recommended_key for s in eligible):
                recommended_key = next((key_for(s) for s in eligible if not getattr(s, 'shareFailure', '')), None)
        desired = {key_for(source): source for source in self.list_sources}
        rebound = False
        # Kodi can append but cannot insert into a ControlList. A changed
        # order needs one bind; reuse its native items and their field caches.
        surviving = [key for key in keys if key in desired]
        reorder = ordered and incremental and list(desired)[:len(surviving)] != surviving
        for position in range(len(keys) - 1, -1, -1):
            if keys[position] not in desired:
                removed_key = keys.pop(position)
                cards.pop(removed_key)
                card_values.pop(removed_key, None)
                if not reorder:
                    self.display_list.removeItem(position)
                rebound = True
        if reorder:
            keys = list(desired)
        else:
            keys += [key for key in desired if key not in cards]
        self.list_sources = [desired[key] for key in keys]
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
            key = key_for(source)
            if key not in cards:
                cards[key] = xbmcgui.ListItem(label=source.title)
                menu_items.append(cards[key])
            elif cards[key].getLabel() != source.title:
                cards[key].setLabel(source.title)
            menu_item = _CardUpdate(cards[key], card_values.setdefault(key, {}),
                                    getattr(self, '_card_fields', None))
            if getattr(self, 'source_session', None):
                menu_item.setProperty('source_key', self.source_session.key(source))
            menu_item.setProperty("title", source.title)
            menu_item.setProperty("display_title", info["clean_title"])
            menu_item.setProperty("codec", info["codec"])
            menu_item.setProperty("audio", info["audio"])
            menu_item.setProperty("hdr_info", info["badges"])
            badges = info["badges"]
            if ordered:
                video = release_quality(quality_text(source.title, self.item_information))
                badges = ' • '.join(filter(None, (video.origin_label, video.dynamic_label,
                    *(info[k] for k in ('codec', 'audio', 'edition', 'lang_detail', 'format', 'note')))))
            menu_item.setProperty("badges_plain", _plain_source_badges(badges))
            release_group = info["release_group"] or ""
            from bobbi_core.subtitle_projection import source_card_label, source_label
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
            menu_item.setProperty("release_group", release_group if _show_release_group(getattr(self, "item_information", {}), source) else "")
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
                menu_item.setProperty('source_provenance', '、'.join(source_libraries(source).values()) or source.subindexer)
            menu_item.setProperty(
                "has_chinese_subtitles", "true" if chinese_subtitles else "false"
            )
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
            display_indexer = source_site_label(indexer_label, source.type)
            stations = getattr(source, 'sourceStations', {}) or {}
            if source.type == 'Torrent' and (stations or source.indexer == 'Jackett'):
                display_indexer = '、'.join(sorted(set(stations.values()))) or '站点未标'
            library_names = source_libraries(source)
            if library_names:
                provider_name = '、'.join(library_names.values())
                display_indexer = source_platform_label(source)
            menu_item.setProperty("type", get_provider_color(provider_name))
            menu_item.setProperty("indexer", get_random_color(display_indexer or indexer_label))
            menu_item.setProperty("source_site", display_indexer)
            menu_item.setProperty("guid", source.guid)
            menu_item.setProperty("infoHash", source.infoHash)
            menu_item.setProperty("size", bytes_to_human_readable(int(source.size)))
            menu_item.setProperty("seeders", str(source.seeders) if source.seeders and not source.isCached else '')
            menu_item.setProperty("peers", str(source.peers) if source.peers and not source.isCached else '')
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
            if getattr(source, 'shareFailure', '') in ('share_revoked', 'identity_changed'):
                status = '分享已失效 · 可手动重试' if source.shareFailure == 'share_revoked' else '文件已变化 · 可手动重试'
            menu_item.setProperty("status_plain", status)
            preference = source_preference(source, getattr(self, "item_information", {}))
            from lib.cinema.source_presentation import recommendation_label
            first_label = recommendation_label(True, preference['caution'], status)
            recommended = (self.source_session.key(source) == recommended_key
                           if getattr(self, 'source_session', None) else position == 0)
            recommended = recommended and not getattr(source, 'shareFailure', '')
            menu_item.setProperty("recommendation", first_label if recommended else "")
            menu_item.setProperty("recommendation_reason", preference["reason"] if recommended else "")
            hint = []
            if ordered:
                if info['note']:
                    hint.append(_plain_source_badges(info['note']).replace('PROPER', 'PROPER 修订').replace('REPACK', 'REPACK 重封'))
                if info['audio']:
                    hint.append(_plain_source_badges(info['audio']))
            menu_item.setProperty("version_hint", ' · '.join(hint))
            menu_item.setProperty("recommendation_status", recommendation_label(recommended, preference['caution'], status))
            menu_item.setProperty("isPack", str(source.isPack))
            menu_item.flush()

        if reorder:
            self.display_list.reset()
            self.display_list.addItems([cards[key] for key in keys])
            rebound = True
        elif menu_items:
            self.display_list.addItems(menu_items)
            rebound = True
        self._rendered_cards, self._rendered_keys = cards, keys
        self._rendered_card_values = card_values
        if incremental and rebound and keys:
            # Structural updates enqueue a full native bind, despite preserving
            # our ListItems. Always enqueue the matching selection after that
            # bind; reading the old position cannot tell whether it was consumed.
            # A withdrawn card keeps its nearest surviving ordinal, never plays.
            position = keys.index(selected_key) if selected_key in keys else min(selected_position, len(keys) - 1)
            self.display_list.selectItem(position)

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

        from lib.utils.torrent.torrserver_utils import add_source_to_torrserver
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
        """Start paired PhoneManagement session (SUBTITLE_UPLOAD_SCOPES) for scoped subtitle upload (U10)."""
        global StremioWebServer, get_local_ip
        if StremioWebServer is None or get_local_ip is None:
            from lib.services.webserver import StremioWebServer as _SWS, get_local_ip as _gli
            if StremioWebServer is None:
                StremioWebServer = _SWS
            if get_local_ip is None:
                get_local_ip = _gli
        from bobbi_core.playback_request import source_identity
        from bobbi_platform.paths import ProfileBinding
        from lib.services.phone_management import PhoneManagement, SUBTITLE_UPLOAD_SCOPES

        kodilog("[UPLOAD_SUBTITLE] Starting paired phone subtitle upload session")
        binding = ProfileBinding()
        target_id = uuid4().hex
        try:
            expected_source_key = json.dumps(source_identity(selected_source), sort_keys=True, separators=(",", ":"))
        except Exception:
            expected_source_key = str(getattr(selected_source, "title", "") or getattr(selected_source, "url", ""))[:240]
        initial_session = get_property("bobbi_active_player_session")
        upload_complete = threading.Event()
        aborted_by_switch = [False]

        def target_current() -> bool:
            if getattr(self, "_selection_locked", False):
                aborted_by_switch[0] = True
                return False
            if get_property("bobbi_active_player_session") != initial_session:
                aborted_by_switch[0] = True
                return False
            return binding.is_current()

        local_ip = get_local_ip()
        chosen_port = 8081
        manager = None
        server = None
        for candidate_port in (8081, 0):
            probe_sock = None
            try:
                if candidate_port == 0:
                    import socket as _s
                    probe_sock = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
                    probe_sock.bind(("0.0.0.0", 0))
                    chosen_port = probe_sock.getsockname()[1]
                    probe_sock.close()
                    probe_sock = None
                else:
                    chosen_port = candidate_port
                origin = f"http://{local_ip}:{chosen_port}"
                manager = PhoneManagement(
                    {
                        "local_scope": "subtitle_upload",
                        "target_id": target_id,
                        "source_key": expected_source_key,
                        "title": _plain_source_label(getattr(selected_source, "title", ""))[:160],
                    },
                    origin,
                    scopes=SUBTITLE_UPLOAD_SCOPES,
                    profile_binding=binding,
                    target_current=target_current,
                )
                server = StremioWebServer(port=chosen_port, phone_management=manager)
                server.start()
                if server.is_running:
                    break
                manager.revoke()
            except Exception:
                if probe_sock is not None:
                    with contextlib.suppress(Exception):
                        probe_sock.close()
                if manager is not None:
                    manager.revoke()
                server = None

        if server is None or not server.is_running or manager is None:
            kodilog("[UPLOAD_SUBTITLE] Failed to start paired subtitle upload server")
            notification(translation(90744))
            return

        dialog = None
        detected_upload = [False]
        try:
            pairing_url = manager.pairing_url
            display_origin = f"http://{local_ip}:{server.port}/manage"
            qr_path = make_qrcode(pairing_url)

            dialog = QRProgressDialog("qr_dialog.xml", ADDON_PATH)
            dialog.setup(
                title=translation(90748),
                qr_code=qr_path or "",
                url=pairing_url,
                user_code="",
                is_debrid=False,
                custom_message=translation(90749) % display_origin,
            )

            def poll_for_upload():
                import time
                poll_count = 0
                while not upload_complete.is_set():
                    time.sleep(0.25)
                    poll_count += 1
                    if not target_current():
                        manager.discard_committed_subtitle()
                        manager.revoke()
                        upload_complete.set()
                        with contextlib.suppress(BaseException):
                            dialog.close()
                        break
                    if manager.committed_subtitle is not None:
                        detected_upload[0] = True
                        upload_complete.set()
                        with contextlib.suppress(BaseException):
                            dialog.close()
                        break
                    if poll_count > 2400:
                        upload_complete.set()
                        with contextlib.suppress(BaseException):
                            dialog.close()
                        break

            poll_thread = threading.Thread(target=poll_for_upload, daemon=True)
            poll_thread.start()
            dialog.doModal()
            upload_complete.set()
        finally:
            upload_complete.set()
            server.stop()

        if dialog is not None and getattr(dialog, "iscanceled", False) and not detected_upload[0]:
            manager.discard_committed_subtitle()
            return
        if aborted_by_switch[0] or not target_current():
            manager.discard_committed_subtitle()
            return
        consumed = manager.consume_committed_subtitle(target_id, expected_source_key)
        if consumed and consumed.get("path"):
            self._resolve_item(selected_source, local_subtitle_path=consumed["path"])

    def _resolve_item(
        self,
        selected_source,
        pack_select: bool = False,
        is_subtitle_download=False,
        local_subtitle_path: Optional[str] = None,
        retry_account=None,
        retry_cancelled=None,
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
            self.item_information.pop('_account', None)
            self.item_information["request_id"] = uuid4().hex
            self.item_information["selection_policy"] = "exact"
            from bobbi_core.playback_request import source_identity, context
            select = self.playback_client.select
            try:
                if retry_cancelled is not None and retry_cancelled():
                    self._selection_locked = False
                    return
                if retry_account is None:
                    accepted = select(self._control_snapshot, self.item_information['request_id'], source_identity(selected_source))
                else:
                    from bobbi_core.account_scope import validate_snapshot
                    retry_account = validate_snapshot(retry_account, authenticated=True)
                    prior = self._control_snapshot['desired']
                    retry_from = dict(request_id=prior['request_id'], selection_identity=prior['selection_identity'],
                                      category=prior['resolver_failure']['category'])
                    accepted = select(self._control_snapshot, self.item_information['request_id'], source_identity(selected_source),
                           account_scope=retry_account, retry_from=retry_from)
                    self.item_information['_account'] = retry_account
                self.item_information['_selection_context'] = context(accepted, self.item_information['request_id'])
            except (AttributeError, KeyError, OSError, TypeError, ValueError, RuntimeError):
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
            playback_client=self.playback_client,
            previous_window=self,
            item_information=advanced_information,
            is_subtitle_download=is_subtitle_download,
            local_subtitle_path=local_subtitle_path,
            share_reader=getattr(getattr(self, 'source_session', None), 'share_reader', getattr(self, '_share_reader', None)),
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
