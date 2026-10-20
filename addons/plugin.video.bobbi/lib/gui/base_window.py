import abc
import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Tuple

import xbmcgui

from lib.domain.torrent import TorrentStream
from lib.utils.debrid.debrid_utils import (
    _is_torrent_ready_in_debrid,
    get_magnet_from_uri,
)
from lib.utils.general.utils import Indexer, IndexerType, truncate_text
from lib.utils.kodi.logging import summarize_locator_for_log
from lib.utils.parsers.pack_parser import detect_pack_scope
from lib.utils.kodi.utils import ADDON, kodilog, translation
from lib.clients.stremio.playback import resolve_stremio_playback_url

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92


class BaseWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, location, item_information=None, previous_window=None):
        super().__init__(xml_file, location)
        self.item_information = {}
        self.previous_window = previous_window
        self.CACHE_KEY = ""
        self._last_focused_control = (None, None)
        self.action_exitkeys_id = {
            ACTION_PREVIOUS_MENU,
            ACTION_PLAYER_STOP,
            ACTION_NAV_BACK,
        }
        if item_information is None:
            return
        self.add_item_information_to_window(item_information)

    def onInit(self):
        pass

    def get_cached_focus(self):
        if not self.CACHE_KEY:
            return None, None

        cache_prop = self._focus_cache_prop()
        cached_data = xbmcgui.Window(10000).getProperty(cache_prop)
        if not cached_data:
            cached_data = ADDON.getSetting(self.CACHE_KEY)
            if cached_data:
                xbmcgui.Window(10000).setProperty(cache_prop, cached_data)
                ADDON.setSetting(self.CACHE_KEY, "")
        if cached_data:
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError:
                return None, None
        return None, None

    def set_cached_focus(self, control_id, item_id):
        if not self.CACHE_KEY:
            return
        cache_data = json.dumps((control_id, item_id))
        xbmcgui.Window(10000).setProperty(self._focus_cache_prop(), cache_data)

    def _focus_cache_prop(self):
        cache_key = str(self.CACHE_KEY or "")
        cache_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return f"bobbi.focus.{cache_hash}"

    def set_default_focus(self, control_list=None, control_id=None, control_list_reset=False):
        try:
            # Retrieve cached focus if available
            control_id, item_id = self.get_cached_focus()
            if control_id and item_id:
                control = self.getControl(control_id)
                if isinstance(control, xbmcgui.ControlList):
                    control.selectItem(int(item_id))
                    self.setFocus(control)
                    return

            if control_list and control_list.size() > 0:
                if control_list_reset:
                    control_list.selectItem(0)
                self.setFocus(control_list)
            elif control_id:
                control = self.getControl(control_id)
                self.setFocus(control)
            else:
                raise ValueError("Neither valid control list nor control ID provided.")
        except (RuntimeError, ValueError) as e:
            kodilog(f"Could not set focus: {e}")
            if control_id:
                self.setFocusId(control_id)

    def getControlList(self, control_id):
        try:
            control = self.getControl(control_id)
        except RuntimeError as e:
            kodilog(f"Control does not exist {control_id}", {e})
            raise ValueError(f"Control with Id {control_id} does not exist") from e

        if not isinstance(control, xbmcgui.ControlList):
            raise AttributeError(f"Control with Id {control_id} should be of type ControlList")
        return control

    def add_item_information_to_window(self, item_information):
        self.item_information = deepcopy(item_information)
        for i in self.item_information:
            value = self.item_information[i]
            if i == "overview":
                value = truncate_text(str(value))
            try:
                self.setProperty(f"info.{i}", str(value))
            except UnicodeEncodeError:
                self.setProperty(f"info.{i}", value)

    def getControlProgress(self, control_id):
        control = self.getControl(control_id)
        if not isinstance(control, xbmcgui.ControlProgress):
            raise AttributeError(f"Control with Id {control_id} should be of type ControlProgress")

        return control

    def onClick(self, control_id):
        self.handle_action(7, control_id)

    def onAction(self, action):
        action_id = action.getId()
        if action_id in self.action_exitkeys_id:
            if self.previous_window:
                self.previous_window.setProperty("instant_close", "true")
                self.previous_window.close()
            self.close()
        elif action_id != 7:
            self.handle_action(action_id, self.getFocusId())

    def _ensure_playback_info(self, source: TorrentStream):
        from lib.clients.catalog_providers import provider_for, resolve_source
        catalog_provider = provider_for(source)
        if catalog_provider:
            from bobbi_platform.runtime import call
            account = call('account_status', {})
            self.item_information['_account'] = account
            # Resolve only the exact selected file. Do not mutate the stable
            # source card, and never put signed CDN addresses in quick-play.
            url = resolve_source(source, self.item_information)
            data = self.prepare_source_data(source=source, url=url, magnet='', is_torrent=False)
            data.update(transient_url=True, filename=source.title, size=source.size,
                        _account=deepcopy(account))
            data[catalog_provider + '_locator'] = source.url
            from bobbi_catalog.identity import media_key
            tv = self.item_information.get('tv_data') or {}
            data['_share'] = dict(locator=source.url, guid=source.guid, title=source.title,
                size=source.size, account=account,
                media=media_key((self.item_information.get('ids') or {}).get('tmdb_id'),
                    self.item_information.get('mode'), tv.get('season'), tv.get('episode')))
            return resolve_stremio_playback_url(data) or {}
        url, magnet, is_torrent = self._extract_source_details(source)

        if source.addedToDebrid and source.debridType and source.infoHash:
            is_ready = _is_torrent_ready_in_debrid(source.debridType, source.infoHash)
            if not is_ready:
                if self.item_information.get("selection_policy") == "exact":
                    raise RuntimeError("Selected cloud source is not ready")
                dialog = xbmcgui.Dialog()
                message = f"{translation(90696) % source.debridType}\n\n{translation(90697)}"
                choice = dialog.yesno(
                    translation(90695),
                    message,
                    yeslabel=translation(90698),
                    nolabel=translation(90699),
                )
                if not choice:
                    return {}
                source.addedToDebrid = False
                source.debridType = ""

        source_data = self.prepare_source_data(
            source=source,
            url=url,
            magnet=magnet,
            is_torrent=is_torrent,
        )
        return resolve_stremio_playback_url(source_data) or {}

    def _extract_source_details(self, source: TorrentStream) -> Tuple[str, str, bool]:
        url = source.url or ""
        guid = source.guid or ""
        magnet = ""
        indexer = source.indexer
        source_type = source.type
        is_torrent = source.type == IndexerType.TORRENT

        kodilog(
            "Source extraction input: indexer={!r}, type={!r}, guid={!r}, url={!r}, infohash={!r}".format(
                indexer,
                source_type,
                summarize_locator_for_log(guid),
                summarize_locator_for_log(url),
                str(source.infoHash or "").lower()[:12],
            )
        )

        if source_type in (IndexerType.DIRECT, IndexerType.STREMIO_DEBRID):
            return url, magnet, is_torrent

        if (self.item_information.get('selection_policy') == 'exact' and is_torrent
                and not source.infoHash and url.startswith(('http://', 'https://'))):
            # Keep the selected locator intact. JackTorr follows its redirects,
            # verifies the returned torrent, and binds that result to this choice.
            # Resolving here used to replace the URL with a redirect target and
            # download the same torrent twice, losing its selection identity.
            return url, magnet, is_torrent

        # Prefer magnet in guid
        if guid.startswith("magnet:?"):
            magnet = guid
        elif url.startswith("magnet:?"):
            # A provider's GUID is often only a human-facing details page.
            # Reuse its supplied transport directly; don't fetch that page
            # before reaching the existing magnet fallback.
            magnet, url = url, ""
        # Handle Burst indexer
        elif indexer == Indexer.BURST or guid.endswith(".torrent"):
            url = guid
        elif url.endswith(".torrent"):
            pass

        # Try to extract magnet from url
        if not magnet and url.startswith("http") and not url.endswith(".torrent"):
            magnet_candidate, _, torrent_url = get_magnet_from_uri(url)
            if torrent_url:
                url = torrent_url
            elif magnet_candidate:
                magnet = magnet_candidate

        # Try to extract magnet from guid if it's a details page
        elif not magnet and guid.startswith("http"):
            magnet_candidate, _, torrent_url = get_magnet_from_uri(guid)
            if magnet_candidate:
                magnet = magnet_candidate
            elif torrent_url:
                url = torrent_url

        # --- Fallback: magnet from url ---
        if not magnet and url.startswith("magnet:"):
            magnet, url = url, ""

        # --- Fallback: magnet from infoHash ---
        used_infohash_fallback = False
        has_http_url = bool(url and url.startswith("http"))
        if not magnet and source.infoHash and not has_http_url:
            from lib.utils.general.utils import info_hash_to_magnet

            magnet = info_hash_to_magnet(source.infoHash)
            used_infohash_fallback = True

        kodilog(
            f"Source extraction output: url={summarize_locator_for_log(url)!r}, magnet={summarize_locator_for_log(magnet)!r}, is_torrent={is_torrent}, used_infohash_fallback={used_infohash_fallback}"
        )

        return url, magnet, is_torrent

    def prepare_source_data(
        self,
        source: TorrentStream,
        url: str,
        magnet: str,
        is_torrent: bool,
        pack_select: bool = False,
    ) -> Dict[str, Any]:
        """Prepare the source data dictionary for resolving playback."""
        restricted_range = bool(getattr(source, 'requiresCatalogEpisodeProof', False))
        if restricted_range and (self.item_information.get('selection_policy') != 'exact'
                or not self.item_information.get('request_id') or pack_select or not is_torrent):
            raise RuntimeError('合集需要已核验的作品与集数，请返回普通选源播放')
        tv_data = self.item_information.get("tv_data")
        current_season = tv_data.get("season") if isinstance(tv_data, dict) else None
        release_binding = None
        if self.item_information.get('selection_policy') == 'exact':
            from lib.clients.tmdb.episode_order import selected_release_binding
            release_binding = selected_release_binding(self.item_information.get('ids'), tv_data, source.infoHash, source.title)
            if release_binding:
                current_season = release_binding['season']
        pack_scope = detect_pack_scope(
            source.title,
            current_season=current_season,
            source_is_pack=bool(source.isPack or pack_select),
        )
        kodilog(
            "Playback pack scope: type={!r}, seasons={!r}, reason={!r}, source={!r}".format(
                pack_scope["pack_type"],
                pack_scope["pack_seasons"],
                pack_scope["pack_reason"],
                source.title,
            )
        )

        playback_data = {
            "type": source.type,
            "indexer": source.indexer,
            "url": url,
            "magnet": magnet,
            "info_hash": source.infoHash,
            "title": self.item_information.get("title")
            or self.item_information.get("query")
            or source.title,
            "source_title": source.title,
            "is_torrent": is_torrent,
            "is_pack": pack_scope["is_pack"],
            "pack_type": pack_scope["pack_type"],
            "pack_seasons": pack_scope["pack_seasons"],
            "pack_reason": pack_scope["pack_reason"],
            "mode": self.item_information.get("mode"),
            "ids": self.item_information.get("ids"),
            "tv_data": tv_data,
            "poster": self.item_information.get("poster"),
            "description": self.item_information.get("overview") or "",
            "stream_subtitles": source.streamSubtitles,
        }
        if restricted_range:
            playback_data['require_catalog_episode_binding'] = True
        from lib.utils.general.cinema_source_rank import uses_anime_groups
        playback_data['anime'] = uses_anime_groups(self.item_information, source)
        from lib.utils.player.direct_continuity import attach_source
        attach_source(source, playback_data)
        if getattr(source, 'directCloudKey', ''):
            playback_data['direct_cloud_required'] = True
        if getattr(source, 'preparedResourceId', ''):
            playback_data.update(prepared_resource_id=source.preparedResourceId,
                                 prepared_version_key=source.preparedVersionKey,
                                 prepared_source_info_hash=source.preparedInfoHash)
        for key in ("selection_policy", "request_id", "episode_binding"):
            if key in self.item_information:
                playback_data[key] = self.item_information[key]
        if release_binding:
            playback_data['episode_binding'] = release_binding
        if playback_data.get("selection_policy") == "exact" and not playback_data.get("episode_binding"):
            from lib.utils.player.episode_identity import bind_selected_episode
            binding = bind_selected_episode(playback_data.get("ids"), tv_data, source.infoHash)
            if binding:
                playback_data["episode_binding"] = binding
        metadata = source.stremioMetadata
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, dict):
            metadata = {"_invalid_stremio_metadata": True}
        if str(getattr(source, 'guid', '') or '').startswith('bobi:') and source.type == IndexerType.DIRECT:
            # Exact selected-file sidecars from the validated personal index.
            # Keep unrelated Stremio/provider subtitle handling unchanged.
            paths = getattr(source, 'localSubtitles', [])
            if isinstance(paths, list):
                playback_data['subtitles_path'] = [p for p in paths[:4] if isinstance(p, str)
                    and p.startswith('/storage/videos/Clouddrive/CloudDrive/115open/')
                    and not any(part in {'.', '..'} for part in p.split('/'))
                    and '\x00' not in p and p.lower().endswith(('.ass', '.srt', '.ssa'))]
        if source.debridType:
            playback_data["debrid_type"] = source.debridType
        if metadata:
            playback_data["stremio_metadata"] = dict(metadata)
        behavior_hints = metadata.get("behaviorHints") or {}
        for source_key, target_key in (
            ("videoHash", "videoHash"),
            ("videoSize", "size"),
            ("filename", "filename"),
        ):
            value = metadata.get(source_key, behavior_hints.get(source_key))
            if value is not None:
                playback_data[target_key] = value
        if playback_data.get('selection_policy') == 'exact' and playback_data.get('prepared_resource_id'):
            from lib.clients.bobi_library import load_prepared_index, local_path
            from lib.cinema.preparation_client import resolve_entry
            prepared = load_prepared_index()
            entries = [entry for title in prepared['titles'] for entry in title['sources']
                       if entry['key'] == playback_data['prepared_resource_id']]
            if len(entries) != 1 or not resolve_entry(playback_data, prepared, entries[0]):
                raise RuntimeError('云端文件身份已变化或暂不可用，请刷新片源')
            playback_data['url'] = local_path(prepared['mount_root'], entries[0]['path'])
            playback_data['source_title'] = entries[0]['title']
            playback_data['video_context'] = entries[0].get('video_context')
        if playback_data.get('selection_policy') == 'exact' and playback_data.get('is_torrent'):
            try:
                from lib.clients.bobi_library import load_prepared_index, local_path
                from lib.cinema.prepared_index import selected_cloud
                from lib.cinema.preparation_client import resolve_entry
                prepared = load_prepared_index()
                entry = selected_cloud(playback_data, prepared)
                if entry:
                    entry = resolve_entry(playback_data, prepared, entry)
                if entry:
                    playback_data.update(url=local_path(prepared['mount_root'], entry['path']),
                        type=IndexerType.DIRECT, indexer='115 · CD2', is_torrent=False, magnet='',
                        source_title=entry['title'], prepared_resource_id=entry['key'],
                        prepared_version_key=entry['prepared_version_key'],
                        prepared_source_info_hash=entry['prepared_source_info_hash'],
                        video_context=entry.get('video_context'),
                        subtitles_path=[local_path(prepared['mount_root'], p) for p in entry.get('subtitles', [])[:4]])
                    playback_data.pop('episode_binding', None)
                    playback_data.pop('info_hash', None)
            except (OSError, ValueError, KeyError, TypeError):
                # Missing/invalid prepared state preserves the user's exact BT
                # selection. It must never silently choose another release.
                pass
        return playback_data

    @abc.abstractmethod
    def handle_action(self, action_id, control_id=None):
        pass
