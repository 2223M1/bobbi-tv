# -*- coding: utf-8 -*-
"""
4. TVScraper — Kodi 入口。

扫描流程：Kodi 传入 title → 读 .tv/{title}.json → 无则请求 TMDB → 写入 .tv
单集：.tv/{title}/S01E01.json
"""

from __future__ import annotations

import json
import re
from typing import List, Optional
import sys
import urllib.parse
from urllib.parse import parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from lib import settings
from lib.list_item import (
    build_episode_list_item,
    build_find_item,
    build_tvshow_list_item,
    search_item_meta,
    tmdb_episode_json_to_meta,
    tmdb_tv_json_to_meta,
)
from lib.meta_files import MetaFiles
from lib.tmdb_api import TmdbApi

ADDON_ID = 'metadata.yyba.tv'
__handle__ = int(sys.argv[1])
settings.init_addon(ADDON_ID)

_WARNED: set = set()

# 常见分类目录名 — Kodi 误把父文件夹当作「一个剧集」时会出现
CONTAINER_FOLDER_TITLES = frozenset({
    '美剧', '日剧', '韩剧', '泰剧', '英剧', '国产剧', '港台剧', '港剧', '台剧',
    '动漫', '纪录片', '综艺', '电视剧', '剧集', 'tv', 'TV', 'shows', 'series',
    'anime', 'dorama', 'movies', 'film', 'video', 'videos', 'media',
})


def is_container_folder(title: str) -> bool:
    name = (title or '').strip()
    if not name:
        return False
    if name.lower() in CONTAINER_FOLDER_TITLES:
        return True
    return name in CONTAINER_FOLDER_TITLES


def warn_once(key: str, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    name = settings._cfg.addon_name()
    xbmc.log(f'[{name}] {message}', xbmc.LOGWARNING)
    try:
        xbmcgui.Dialog().notification(name, message, xbmcgui.NOTIFICATION_WARNING, 6000)
    except Exception:
        pass


class TVScraper:
    def __init__(self, handle: int) -> None:
        self._handle = handle
        self._cfg = settings._cfg
        self._tmdb = TmdbApi(self._cfg)
        self._meta = MetaFiles(self._cfg)
        self._name = self._cfg.addon_name()

    def log(self, msg: str, level=xbmc.LOGINFO) -> None:
        xbmc.log(f'[{self._name}] {msg}', level)

    @staticmethod
    def build_show_ref(tmdb_id: str, title: str) -> str:
        """find / getdetails episodeguide / getepisodelist 共用的 JSON 载荷。"""
        tid = str(tmdb_id or '').strip()
        folder_title = MetaFiles.sanitize_title(title)
        payload = {
            'tmdb_id': tid,
            'tmdb': tid,
            'title': folder_title,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))

    @staticmethod
    def parse_show_ref(value: str) -> tuple[str, str]:
        """从 url 字段解析 {"tmdb_id":"","title":""}，兼容纯数字 id / plugin URL。"""
        if not value:
            return '', ''
        text = settings._decode_url_param(value)
        if '{' in text or '"tmdb_id"' in text or '"tmdb"' in text:
            ref = settings._params_from_show_ref_text(text)
            if ref.get('tmdb_id') or ref.get('title'):
                return ref.get('tmdb_id', ''), ref.get('title', '')
        if text.startswith('plugin://') and '?' in text:
            qs = text.split('?', 1)[1]
            params = dict(parse_qsl(qs, keep_blank_values=True))
            inner = settings._decode_url_param(params.get('url', ''))
            if inner.startswith('{') or '"tmdb_id"' in inner:
                ref = settings._params_from_show_ref_text(inner)
                if ref.get('tmdb_id') or ref.get('title'):
                    return ref.get('tmdb_id', ''), ref.get('title', '')
            if inner and re.fullmatch(r'\d+', inner):
                title = settings._sanitize_title(params.get('title', ''))
                return inner, title
        if re.fullmatch(r'\d+', text):
            return text, ''
        match = re.search(r'/tv/(\d+)', text)
        if match:
            return match.group(1), ''
        match = re.search(r'(?:\?|&)(?:url|id|tmdb_id)=(\d+)', text)
        if match:
            return match.group(1), ''
        return '', ''

    @staticmethod
    def parse_tmdb_id(value: str) -> str:
        tmdb_id, _title = TVScraper.parse_show_ref(value)
        if tmdb_id:
            return tmdb_id
        if not value:
            return ''
        value = urllib.parse.unquote(str(value).strip())
        if re.fullmatch(r'\d+', value):
            return value
        match = re.search(r'/tv/(\d+)', value)
        if match:
            return match.group(1)
        match = re.search(r'(?:\?|&)(?:url|id|tmdb_id)=(\d+)', value)
        return match.group(1) if match else ''

    def resolve_title(self, raw: str = '') -> str:
        return self._cfg.resolve_scan_title(raw)

    def _parse_request_show(self, show_ref: str = '') -> tuple[str, str]:
        """从 url / episodeguide / 请求参数解析 tmdb_id 与本地文件夹剧名。"""
        raw_url = show_ref or self._cfg.request_params().get('url', '')
        tmdb_id, title = self.parse_show_ref(raw_url)
        ref = self._cfg.scraper_ref_params()
        if not tmdb_id:
            tmdb_id = str(ref.get('tmdb_id') or ref.get('url') or '').strip()
            if tmdb_id and not re.fullmatch(r'\d+', tmdb_id):
                tmdb_id = self.parse_tmdb_id(tmdb_id)
        if not title:
            title = MetaFiles.sanitize_title(ref.get('title', ''))
        if not title:
            title = MetaFiles.sanitize_title(self._cfg.request_params().get('title', ''))
        if not title:
            title = MetaFiles.sanitize_title(self._cfg.scan_title())
        if not title:
            title = MetaFiles.sanitize_title(
                self._cfg.folder_basename(self._cfg.scan_folder_path())
            )
        return tmdb_id, title

    @staticmethod
    def _encode_query(query: dict) -> str:
        return urllib.parse.urlencode(query, quote_via=urllib.parse.quote)

    def meta_root(self) -> str:
        return self._cfg.meta_root()

    @staticmethod
    def build_episode_ref(tmdb_id: str, season: int, episode: int, title: str = '') -> str:
        """单集唯一标识 — 直接作为 addDirectoryItem 的 url（Kodi 原样传给 getepisodedetails）。"""
        payload = {
            'tmdb_id': str(tmdb_id or '').strip(),
            'tmdb': str(tmdb_id or '').strip(),
            'season': int(season),
            'episode': int(episode),
            'title': MetaFiles.sanitize_title(title),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))

    @staticmethod
    def resolve_episode_ref(raw: str) -> str:
        """从 Kodi 回传的 url 参数提取 episode ref（兼容误传的 plugin URL）。"""
        text = settings._decode_url_param(str(raw or '').strip())
        if text.startswith('plugin://') and '?' in text:
            params = dict(parse_qsl(text.split('?', 1)[1], keep_blank_values=True))
            inner = settings._decode_url_param(params.get('url', ''))
            if inner:
                return inner
        return text

    @staticmethod
    def parse_episode_ref(value: str):
        value = TVScraper.resolve_episode_ref(value)
        if value.startswith('{'):
            data = settings._safe_json_loads(value)
            if isinstance(data, dict):
                try:
                    tmdb_id = str(data.get('tmdb_id') or data.get('tmdb') or '').strip()
                    season = int(data['season'])
                    episode = int(data['episode'])
                    title = MetaFiles.sanitize_title(str(data.get('title') or ''))
                    if tmdb_id and season >= 0 and episode >= 0:
                        return tmdb_id, season, episode, title
                except (TypeError, ValueError, KeyError):
                    pass
        parts = value.split('|')
        if len(parts) < 3:
            return None
        try:
            tmdb_id = str(parts[0]).strip()
            if not re.fullmatch(r'\d+', tmdb_id):
                tmdb_id = TVScraper.parse_tmdb_id(tmdb_id)
            season = int(parts[1])
            episode = int(parts[2])
            title = MetaFiles.sanitize_title(parts[3] if len(parts) > 3 else '')
            if tmdb_id:
                return tmdb_id, season, episode, title
        except (TypeError, ValueError):
            return None
        return None

    def _log_request_context(self, action: str) -> None:
        params = self._cfg.request_params()
        title = self.resolve_title()
        key = MetaFiles.title_key(title)
        folder = self._cfg.scan_folder_path()
        self.log(
            f'{action} title={title!r} key={key!r} folder={folder!r} '
            f'meta_root={self.meta_root()!r} param_keys={list(params.keys())!r}'
        )

    def _load_local_show(self, title: str):
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        if not meta_root or not key:
            return None
        data = self._meta.load_show(meta_root, title)
        return tmdb_tv_json_to_meta(data) if data else None

    def find(self, title: str, year=None) -> None:
        title = self.resolve_title(title)
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        self.log(f'find title={title!r} year={year!r} key={key!r}')

        if not title:
            warn_once('title', '扫描未收到标题或文件夹路径，无法刮削')
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        if is_container_folder(title):
            warn_once(
                'container',
                f'「{title}」是分类目录不是剧集。请删除错误的 .tv/{title}.json，'
                f'并将 Kodi 电视剧源设为「每个文件夹一个剧集」（源路径指向含子文件夹的目录）',
            )
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        if meta_root and key:
            meta = self._load_local_show(title)
            if meta:
                tmdb_id = (meta.get('uniqueids') or {}).get('tmdb', '0')
                display = meta.get('title') or title
                if meta.get('year'):
                    display = f'{display} ({meta["year"]})'
                show_ref = self.build_show_ref(tmdb_id, title)
                self.log(f'find local hit: {key!r} ref={show_ref!r}')
                xbmcplugin.setContent(self._handle, 'tvshows')
                xbmcplugin.addDirectoryItem(
                    self._handle,
                    show_ref,
                    build_find_item(display, meta),
                    False,
                )
                xbmcplugin.endOfDirectory(self._handle)
                return

        if not self._cfg.api_key():
            warn_once('api_key', '请填写 TMDB API Key')
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        search_query = TmdbApi.normalize_search_title(title) or title
        self.log(f'find TMDB search query={search_query!r}')
        results = self._tmdb.search_tv(title, year)
        if not results:
            self.log(f'find TMDB no results for query={search_query!r}', xbmc.LOGWARNING)
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        listing = []
        for item in results:
            tmdb_id = str(item.get('id') or '')
            if not tmdb_id:
                continue
            show_title = item.get('name') or ''
            first_air = item.get('first_air_date') or ''
            show_year = first_air[:4] if len(first_air) >= 4 else ''
            display = f'{show_title} ({show_year})' if show_year else show_title
            show_ref = self.build_show_ref(tmdb_id, title)
            listing.append((
                show_ref,
                build_find_item(display, search_item_meta(item)),
                False,
            ))

        if not listing:
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return
        xbmcplugin.setContent(self._handle, 'tvshows')
        xbmcplugin.addDirectoryItems(self._handle, listing, len(listing))
        xbmcplugin.endOfDirectory(self._handle)

    def get_details(self, show_ref: str) -> None:
        tmdb_id, title = self._parse_request_show(show_ref)
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        self.log(f'getdetails tmdb_id={tmdb_id!r} title={title!r} key={key!r}')
        if not tmdb_id:
            raw = self._cfg.request_params().get('url', '')
            self.log(f'getdetails parse failed raw_url={raw[:400]!r}', xbmc.LOGWARNING)

        if is_container_folder(title):
            warn_once('container', f'「{title}」是分类目录，请删除 .tv/{title}.json 并检查 Kodi 媒体源设置')
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        if meta_root and key:
            meta = self._load_local_show(title)
            if meta:
                ep_id = tmdb_id or (meta.get('uniqueids') or {}).get('tmdb', '')
                guide = self.build_show_ref(ep_id, title)
                self.log(f'getdetails local hit: {key!r} guide={guide!r}')
                list_item = build_tvshow_list_item(meta, folder_title=title, episodeguide=guide)
                xbmcplugin.setResolvedUrl(self._handle, True, list_item)
                return

        if not tmdb_id or not self._cfg.api_key():
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        data = self._tmdb.get_tv(tmdb_id)
        if not data:
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        if meta_root and key:
            self._meta.save_show(meta_root, title, data)
        elif meta_root:
            warn_once('title', f'无法写入 .tv：标题无效 {title!r}')

        meta = tmdb_tv_json_to_meta(data)
        guide = self.build_show_ref(tmdb_id, title)
        list_item = build_tvshow_list_item(meta, folder_title=title, episodeguide=guide)
        self.log(
            f'getdetails art poster={meta.get("poster_url")!r} guide={guide!r}',
            xbmc.LOGINFO,
        )
        xbmcplugin.setResolvedUrl(self._handle, True, list_item)

    def _load_show_raw(self, title: str):
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        if not meta_root or not key:
            return None
        return self._meta.load_show(meta_root, title)

    def _season_numbers(self, title: str, tmdb_id: str) -> List[int]:
        hint = TmdbApi.parse_season_hint(title)
        if hint:
            return [hint]
        data = self._load_show_raw(title)
        numbers = TmdbApi.season_numbers_from_show(data or {})
        if numbers:
            self.log(f'seasons from show json: {numbers}')
            return numbers
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        if meta_root and key:
            local_seasons = self._meta.local_season_numbers(meta_root, title)
            if local_seasons:
                self.log(f'seasons from local episodes: {local_seasons}')
                return local_seasons
        if data:
            return []
        if tmdb_id and self._cfg.api_key():
            data = self._tmdb.get_tv(tmdb_id)
            numbers = TmdbApi.season_numbers_from_show(data or {})
            if numbers:
                self.log(f'seasons from TMDB show: {numbers}')
                return numbers
        self.log('seasons unknown, fallback 1..50', xbmc.LOGWARNING)
        return list(range(1, 51))

    @staticmethod
    def _season_needs_remote(
        show_raw: Optional[dict],
        season: int,
        local_map: dict,
    ) -> bool:
        if not local_map:
            return True
        expected = MetaFiles.episode_count_from_show(show_raw, season)
        if expected is not None:
            return len(local_map) < expected
        return False

    def _episodes_for_season(
        self,
        tmdb_id: str,
        title: str,
        season: int,
        show_raw: Optional[dict],
        show_title: str,
    ) -> List[tuple[int, int, dict]]:
        """返回 (season_num, ep_num, episode_json) 列表，本地优先。"""
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        local_map: dict = {}
        if meta_root and key:
            local_map = self._meta.load_season_local(meta_root, title, season)

        if local_map and not self._season_needs_remote(show_raw, season, local_map):
            self.log(
                f'getepisodelist season={season} local-only episodes={len(local_map)}',
            )
            rows = []
            for ep_num in sorted(local_map):
                rows.append((season, ep_num, local_map[ep_num]))
            return rows

        if not self._cfg.api_key():
            if local_map:
                return [(season, ep_num, local_map[ep_num]) for ep_num in sorted(local_map)]
            return []

        remote_eps = self._tmdb.get_season_episodes(tmdb_id, season)
        if not remote_eps:
            if local_map:
                return [(season, ep_num, local_map[ep_num]) for ep_num in sorted(local_map)]
            return []

        rows = []
        local_used = 0
        for ep in remote_eps:
            ep_num = ep.get('episode_number')
            if ep_num is None:
                continue
            season_num = ep.get('season_number') or season
            if ep_num in local_map:
                ep_data = local_map[ep_num]
                local_used += 1
            else:
                ep_data = ep
                if meta_root and key:
                    self._meta.save_episode(meta_root, title, season_num, ep_num, ep)
            rows.append((season_num, ep_num, ep_data))

        if local_used:
            self.log(
                f'getepisodelist season={season} merged local={local_used} '
                f'remote={len(rows) - local_used}',
            )
        return rows

    def get_episode_list(self, show_ref: str) -> None:
        tmdb_id, title = self._parse_request_show(show_ref)
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        self.log(f'getepisodelist tmdb_id={tmdb_id!r} title={title!r} key={key!r}')

        if not tmdb_id:
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        show_raw = self._load_show_raw(title) if meta_root and key else None
        show_title = ''
        if meta_root and key:
            local_show = self._load_local_show(title)
            if local_show:
                show_title = title or local_show.get('title') or ''

        season_range = self._season_numbers(title, tmdb_id)
        if not season_range:
            xbmcplugin.endOfDirectory(self._handle, succeeded=True)
            return

        needs_remote = any(
            self._season_needs_remote(
                show_raw,
                season,
                self._meta.load_season_local(meta_root, title, season) if meta_root and key else {},
            )
            for season in season_range
        )
        if needs_remote and not self._cfg.api_key():
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        listing = []
        for season in season_range:
            for season_num, ep_num, ep_data in self._episodes_for_season(
                tmdb_id, title, season, show_raw, show_title,
            ):
                ep_meta = tmdb_episode_json_to_meta(ep_data, season_num, ep_num)
                list_item = build_episode_list_item(ep_meta, show_title or title)
                ep_ref = self.build_episode_ref(tmdb_id, season_num, ep_num, title)
                list_item.setLabel2(f'S{season_num:02d}E{ep_num:02d}')
                listing.append((ep_ref, list_item, False))

        if not listing:
            xbmcplugin.endOfDirectory(self._handle, succeeded=True)
            return
        self.log(f'getepisodelist episodes={len(listing)}')
        xbmcplugin.setContent(self._handle, 'episodes')
        xbmcplugin.addDirectoryItems(self._handle, listing, len(listing))
        xbmcplugin.endOfDirectory(self._handle)

    def get_episode_details(self, episode_ref: str) -> None:
        raw_ref = episode_ref or self._cfg.request_params().get('url', '')
        resolved = self.resolve_episode_ref(raw_ref)
        parsed = self.parse_episode_ref(resolved)
        if not parsed:
            self.log(f'getepisodedetails parse failed raw={raw_ref[:300]!r}', xbmc.LOGWARNING)
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        tmdb_id, season, episode_num, ref_title = parsed
        title = MetaFiles.sanitize_title(ref_title)
        if not title:
            _ignored, title = self._parse_request_show('')
        if not re.fullmatch(r'\d+', str(tmdb_id or '')):
            self.log(f'getepisodedetails invalid tmdb_id={tmdb_id!r}', xbmc.LOGWARNING)
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        show_title = ''
        self.log(
            f'getepisodedetails tmdb_id={tmdb_id!r} S{season:02d}E{episode_num:02d} '
            f'title={title!r} key={key!r}',
        )

        if meta_root and key:
            ep_data = self._meta.load_episode(meta_root, title, season, episode_num)
            if ep_data:
                local_show = self._load_local_show(title)
                if local_show:
                    show_title = title or local_show.get('title') or ''
                meta = tmdb_episode_json_to_meta(ep_data, season, episode_num)
                self.log(f'getepisodedetails local hit: {key}/{MetaFiles.episode_key(season, episode_num)!r}')
                xbmcplugin.setResolvedUrl(self._handle, True, build_episode_list_item(meta, show_title))
                return

        if not self._cfg.api_key():
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        data = self._tmdb.get_episode(tmdb_id, season, episode_num)
        if not data:
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        if meta_root and key:
            self._meta.save_episode(meta_root, title, season, episode_num, data)
            local_show = self._load_local_show(title)
            if local_show:
                show_title = title or local_show.get('title') or ''

        meta = tmdb_episode_json_to_meta(data, season, episode_num)
        xbmcplugin.setResolvedUrl(self._handle, True, build_episode_list_item(meta, show_title))

    def get_artwork(self, show_ref: str) -> None:
        tmdb_id, title = self._parse_request_show(show_ref)
        meta_root = self.meta_root()
        key = MetaFiles.title_key(title)
        self.log(f'getartwork tmdb_id={tmdb_id!r} title={title!r} key={key!r}')

        if is_container_folder(title):
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())
            return

        if meta_root and key:
            meta = self._load_local_show(title)
            if meta:
                ep_id = tmdb_id or (meta.get('uniqueids') or {}).get('tmdb', '')
                guide = self.build_show_ref(ep_id, title)
                list_item = build_tvshow_list_item(meta, folder_title=title, episodeguide=guide)
                xbmcplugin.setResolvedUrl(self._handle, True, list_item)
                return

        if tmdb_id and self._cfg.api_key():
            data = self._tmdb.get_tv(tmdb_id)
            if data:
                if meta_root and key:
                    self._meta.save_show(meta_root, title, data)
                meta = tmdb_tv_json_to_meta(data)
                guide = self.build_show_ref(tmdb_id, title)
                list_item = build_tvshow_list_item(meta, folder_title=title, episodeguide=guide)
                xbmcplugin.setResolvedUrl(self._handle, True, list_item)
                return
        xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())

    def handle_nfo_url(self, nfo_url: str) -> None:
        tmdb_id = self.parse_tmdb_id(nfo_url)
        if tmdb_id:
            self.get_details(tmdb_id)
        else:
            xbmcplugin.setResolvedUrl(self._handle, False, xbmcgui.ListItem())

    def route(self, paramstring: str) -> None:
        params = dict(parse_qsl(paramstring, keep_blank_values=True))
        self._cfg.load_request(params)
        action = params.get('action', '')

        if not self.meta_root() and action in (
            'find', 'getdetails', 'getepisodelist', 'getepisodedetails', 'getartwork', 'NfoUrl',
        ):
            warn_once('meta_path', '请填写本地存储路径（缓存目录 .tv/）')

        self._log_request_context(action)

        if action == 'find':
            self.find(params.get('title', ''), params.get('year'))
        elif action == 'getdetails':
            ref = params.get('url', '') or params.get('id', '') or params.get('tmdb_id', '')
            self.get_details(ref)
        elif action == 'getepisodelist':
            ref = params.get('url', '') or params.get('id', '') or params.get('tmdb_id', '')
            self.get_episode_list(ref)
        elif action == 'getepisodedetails':
            self.get_episode_details(params.get('url', '') or params.get('id', ''))
        elif action == 'getartwork':
            ref = params.get('id', '') or params.get('url', '') or params.get('tmdb_id', '')
            self.get_artwork(ref)
        elif action == 'NfoUrl':
            self.handle_nfo_url(params.get('url', ''))
        else:
            self.log(f'unknown action: {action}', xbmc.LOGWARNING)


if __name__ == '__main__':
    paramstring = ''
    if len(sys.argv) > 2:
        paramstring = sys.argv[2][1:] if sys.argv[2].startswith('?') else sys.argv[2]
    TVScraper(__handle__).route(paramstring)
