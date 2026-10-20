# -*- coding: utf-8 -*-
"""2. TmdbApi — 按设置域名请求 TMDB，无故障转移。"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import xbmc

from lib import settings

IMAGE_BASE = 'https://media.themoviedb.org/t/p'
DEFAULT_TIMEOUT = 15
POSTER_SIZE = 'w500'
FANART_SIZE = 'w1280'
STILL_SIZE = 'w300'
PROFILE_SIZE = 'w185'


class TmdbApi:
    """TMDB HTTP 请求（剧集搜索 / 详情 / 单集）。"""

    def __init__(self, cfg: settings.Settings = None) -> None:
        self._cfg = cfg or settings._cfg

    def _endpoint(self) -> Optional[Dict[str, str]]:
        mode = self._cfg.endpoint_mode()
        if mode == settings.ENDPOINT_MANUAL:
            host = self._cfg.manual_host()
            if not host:
                return None
            return {
                'scheme': self._cfg.manual_scheme(),
                'host': host,
                'port': self._cfg.manual_port(),
                'host_header': self._cfg.manual_host_header(),
            }
        if mode == settings.ENDPOINT_THEMOVIEDB_ORG:
            return {'scheme': 'https', 'host': 'api.themoviedb.org', 'port': '', 'host_header': 'api.themoviedb.org'}
        return {'scheme': 'https', 'host': 'api.tmdb.org', 'port': '', 'host_header': 'api.tmdb.org'}

    def _authority(self, ep: Dict[str, str]) -> str:
        if ep.get('port'):
            return f"{ep['host']}:{ep['port']}"
        return ep['host']

    def _needs_host_header(self, ep: Dict[str, str]) -> bool:
        host = ep.get('host', '')
        return bool(re.match(r'^\d{1,3}(\.\d{1,3}){3}$', host))

    def _ssl(self) -> ssl.SSLContext:
        if self._cfg.ssl_verify():
            return ssl.create_default_context()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _headers(self, ep: Dict[str, str]) -> Dict[str, str]:
        headers = {'User-Agent': f'{self._cfg.addon_name()}/2.0'}
        if self._needs_host_header(ep):
            headers['Host'] = ep.get('host_header') or ep['host']
        return headers

    def _build_url(self, ep: Dict[str, str], path: str, params: Optional[Dict[str, Any]] = None) -> str:
        if not path.startswith('/'):
            path = '/' + path
        url = f"{ep['scheme']}://{self._authority(ep)}/3{path}"
        query = dict(params or {})
        key = self._cfg.api_key()
        if key and 'api_key' not in query:
            query['api_key'] = key
        if query:
            url += '?' + urllib.parse.urlencode(query)
        return url

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        ep = self._endpoint()
        if not ep:
            xbmc.log(f'[{self._cfg.addon_name()}] TMDB endpoint not configured', xbmc.LOGERROR)
            return None
        url = self._build_url(ep, path, params)
        name = self._cfg.addon_name()
        try:
            req = urllib.request.Request(url, headers=self._headers(ep), method='GET')
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT, context=self._ssl()) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as err:
            if err.code == 404 and '/season/' in path:
                return None
            xbmc.log(f'[{name}] TMDB HTTP {err.code} ({ep["host"]}) {path}', xbmc.LOGERROR)
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as err:
            xbmc.log(f'[{name}] TMDB request failed ({ep["host"]}): {err}', xbmc.LOGWARNING)
        return None

    @staticmethod
    def build_image_url(path: str, size: str = POSTER_SIZE) -> str:
        if not path:
            return ''
        if path.startswith(('http://', 'https://')):
            return path
        if not path.startswith('/'):
            path = '/' + path
        try:
            base = settings._cfg.image_base() or IMAGE_BASE
        except Exception:
            base = IMAGE_BASE
        return f'{base}/{size}{path}'

    def _lang_params(self, with_images: bool = False) -> Dict[str, Any]:
        lang = self._cfg.tmdb_language()
        params: Dict[str, Any] = {'language': lang}
        if with_images:
            short = lang.split('-')[0] if lang else 'zh'
            params['include_image_language'] = f'{short},null,en'
        return params

    @staticmethod
    def normalize_search_title(title: str) -> str:
        """TMDB 搜索用词：去掉季数后缀，保留剧名。"""
        text = (title or '').strip()
        if not text:
            return ''
        text = re.sub(r'[（(][第]?[一二三四五六七八九十百\d]+季[)）]\s*$', '', text)
        text = re.sub(r'[第][一二三四五六七八九十百\d]+季\s*$', '', text)
        text = re.sub(r'[\s._-]*(?:Season|S)\s*\d+\s*$', '', text, flags=re.I)
        return text.strip()

    _CN_NUM = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
               '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

    @classmethod
    def parse_season_hint(cls, title: str) -> Optional[int]:
        """从文件夹名解析季数，如 怪奇物语(第一季) → 1。"""
        text = title or ''
        match = re.search(r'[（(][第]?([一二三四五六七八九十百\d]+)季[)）]', text)
        if not match:
            match = re.search(r'[第]([一二三四五六七八九十百\d]+)季', text)
        if not match:
            match = re.search(r'(?:Season|S)\s*(\d+)', text, flags=re.I)
        if not match:
            return None
        token = match.group(1)
        if token.isdigit():
            return int(token)
        if token in cls._CN_NUM:
            return cls._CN_NUM[token]
        if len(token) == 2 and token[0] == '十' and token[1] in cls._CN_NUM:
            return 10 + cls._CN_NUM[token[1]]
        return None

    @staticmethod
    def clean_title(title: str, year: Optional[str] = None) -> str:
        clean = TmdbApi.normalize_search_title(title)
        if year and str(year).isdigit():
            clean = re.sub(rf'[\.\s_-]{year}[\.\s_-]', ' ', clean)
            clean = re.sub(r'[\.\s_-]+$', '', clean).strip()
        return clean

    def search_tv(self, title: str, year: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.clean_title(title, year) or (title or '').strip()
        params: Dict[str, Any] = {'query': query, **self._lang_params()}
        if year and str(year).isdigit():
            params['first_air_date_year'] = str(year)
        data = self.get_json('/search/tv', params)
        return (data or {}).get('results', []) or []

    def get_tv(self, tmdb_id: str) -> Optional[Dict[str, Any]]:
        if not tmdb_id or not re.fullmatch(r'\d+', str(tmdb_id)):
            return None
        params = {'append_to_response': 'credits', **self._lang_params(with_images=True)}
        data = self.get_json(f'/tv/{tmdb_id}', params)
        return data if isinstance(data, dict) else None

    @staticmethod
    def season_numbers_from_show(data: Dict[str, Any]) -> List[int]:
        """从剧集 JSON 的 seasons 字段提取正片季号（>=1）。"""
        seasons: List[int] = []
        for item in (data or {}).get('seasons') or []:
            if not isinstance(item, dict):
                continue
            sn = item.get('season_number')
            if sn is None:
                continue
            sn = int(sn)
            if sn >= 1:
                seasons.append(sn)
        if seasons:
            return sorted(set(seasons))
        total = (data or {}).get('number_of_seasons')
        if total:
            try:
                return list(range(1, int(total) + 1))
            except (TypeError, ValueError):
                pass
        return []

    def get_season_episodes(self, tmdb_id: str, season: int) -> List[Dict[str, Any]]:
        if not tmdb_id or not re.fullmatch(r'\d+', str(tmdb_id)):
            return []
        params = self._lang_params(with_images=True)
        data = self.get_json(f'/tv/{tmdb_id}/season/{season}', params)
        if not isinstance(data, dict):
            return []
        return data.get('episodes', []) or []

    def get_episode(self, tmdb_id: str, season: int, episode: int) -> Optional[Dict[str, Any]]:
        if not tmdb_id or not re.fullmatch(r'\d+', str(tmdb_id)):
            return None
        params = self._lang_params(with_images=True)
        data = self.get_json(f'/tv/{tmdb_id}/season/{season}/episode/{episode}', params)
        return data if isinstance(data, dict) else None
