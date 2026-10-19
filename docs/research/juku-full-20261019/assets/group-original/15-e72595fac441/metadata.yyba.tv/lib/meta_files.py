# -*- coding: utf-8 -*-
"""3. MetaFiles — 本地优先，读写 .tv/{title}.json 与 .tv/{title}/SxxExx.json。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import xbmc
import xbmcvfs

from lib import settings

VFS_PREFIXES = (
    'special://', 'smb://', 'nfs://', 'ftp://', 'sftps://', 'ssh://',
    'dav://', 'davs://', 'upnp://', 'sources://',
)

EPISODE_FILE_RE = re.compile(r'^S(\d+)E(\d+)\.json$', re.IGNORECASE)


class MetaFiles:
    """本地缓存：剧集 {meta_root}/.tv/{title}.json，单集 {meta_root}/.tv/{title}/S01E01.json"""

    META_DIRNAME = '.tv'

    def __init__(self, cfg=None) -> None:
        self._cfg = cfg or settings._cfg

    @staticmethod
    def _is_vfs_path(path: str) -> bool:
        return (path or '').lower().startswith(VFS_PREFIXES)

    @classmethod
    def _normalize(cls, path: str) -> str:
        path = (path or '').strip()
        if cls._is_vfs_path(path):
            return path.replace('\\', '/')
        return path

    @classmethod
    def _join(cls, base: str, *parts: str) -> str:
        result = cls._normalize(base)
        for part in parts:
            if not part:
                continue
            piece = cls._normalize(part).strip('/\\')
            if cls._is_vfs_path(result):
                result = result.rstrip('/') + '/' + piece
            else:
                result = os.path.join(result, piece)
        return result

    @classmethod
    def _basename(cls, path: str) -> str:
        path = cls._normalize(path)
        if cls._is_vfs_path(path):
            return path.rstrip('/').rsplit('/', 1)[-1]
        return os.path.basename(path)

    @classmethod
    def _isdir(cls, path: str) -> bool:
        if not path or not xbmcvfs.exists(path):
            return False
        if hasattr(xbmcvfs, 'isdir'):
            return xbmcvfs.isdir(path)
        return os.path.isdir(path)

    @classmethod
    def _list_files(cls, path: str) -> List[str]:
        path = cls._normalize(path)
        if not path or not cls._isdir(path):
            return []
        try:
            listing = xbmcvfs.listdir(path)
            if isinstance(listing, (list, tuple)) and len(listing) == 2:
                return [str(name) for name in listing[1] if name]
            if isinstance(listing, (list, tuple)):
                return [str(name) for name in listing if name and not str(name).endswith('/')]
        except Exception:
            pass
        if not cls._is_vfs_path(path):
            try:
                return os.listdir(path)
            except OSError:
                return []
        return []

    @classmethod
    def parse_episode_filename(cls, name: str) -> Optional[Tuple[int, int]]:
        match = EPISODE_FILE_RE.match((name or '').strip())
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @classmethod
    def _isfile(cls, path: str) -> bool:
        if not path or not xbmcvfs.exists(path):
            return False
        if hasattr(xbmcvfs, 'isdir') and xbmcvfs.isdir(path):
            return False
        return True

    @classmethod
    def _ensure_dir(cls, path: str) -> None:
        """目录已存在则跳过，不存在才 mkdir。"""
        if not path:
            return
        path = cls._normalize(path)
        if cls._isdir(path):
            return
        cls._makedirs(path)

    @classmethod
    def _makedirs(cls, path: str) -> None:
        if not path:
            return
        path = cls._normalize(path)
        if cls._is_vfs_path(path):
            if '://' not in path:
                return
            idx = path.index('://')
            scheme = path[:idx + 3]
            rest = [p for p in path[idx + 3:].replace('\\', '/').strip('/').split('/') if p]
            if not rest:
                return
            built = scheme + rest[0]
            for part in rest[1:]:
                built = built.rstrip('/') + '/' + part
                if cls._isdir(built):
                    continue
                try:
                    xbmcvfs.mkdir(built)
                except Exception:
                    pass
            return
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)

    @classmethod
    def _write_text(cls, path: str, body: str) -> bool:
        path = cls._normalize(path)
        if not cls._is_vfs_path(path):
            try:
                parent = os.path.dirname(path)
                if parent:
                    cls._ensure_dir(parent)
                with open(path, 'w', encoding='utf-8') as handle:
                    handle.write(body)
                return True
            except Exception as err:
                xbmc.log(f'MetaFiles local write failed: {path!r} {err}', xbmc.LOGERROR)
                return False
        try:
            parent = cls._dirname(path)
            if parent:
                cls._ensure_dir(parent)
            handle = xbmcvfs.File(path, 'w')
            handle.write(body)
            handle.close()
            return True
        except Exception as err:
            try:
                real = xbmcvfs.translatePath(path) if hasattr(xbmcvfs, 'translatePath') else path
                parent = os.path.dirname(real)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                with open(real, 'w', encoding='utf-8') as handle:
                    handle.write(body)
                return True
            except Exception as err2:
                xbmc.log(f'MetaFiles write failed: {path!r} {err2}', xbmc.LOGERROR)
                return False

    @classmethod
    def _read_text(cls, path: str) -> str:
        try:
            if not cls._is_vfs_path(path) and os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as handle:
                    return handle.read()
            handle = xbmcvfs.File(path, 'r')
            data = handle.read()
            handle.close()
            return data or ''
        except Exception:
            return ''

    @classmethod
    def _dirname(cls, path: str) -> str:
        path = cls._normalize(path)
        if cls._is_vfs_path(path):
            if '/' not in path.rstrip('/'):
                return path
            return path.rstrip('/').rsplit('/', 1)[0]
        return os.path.dirname(path)

    @classmethod
    def _safe_filename(cls, name: str) -> str:
        name = (name or '').strip()
        if not name:
            return ''
        name = name.replace('\\', '/').split('/')[-1]
        return re.sub(r'[<>:"|?*\x00]', '_', name).strip()

    @classmethod
    def sanitize_title(cls, title: str) -> str:
        """去掉 episodeguide JSON 误解析产生的尾部垃圾。"""
        text = (title or '').strip()
        if not text:
            return ''
        text = re.sub(r'["\'}>\]]+$', '', text)
        text = re.sub(r'^[\[{"]+', '', text)
        return text.strip()

    @classmethod
    def title_key(cls, title: str) -> str:
        """Kodi 传入的本地目录/文件名，原样作为缓存键。"""
        return cls._safe_filename(cls.sanitize_title(title))

    @classmethod
    def episode_key(cls, season: int, episode: int) -> str:
        return f'S{int(season):02d}E{int(episode):02d}'

    def _normalize_meta_root(self, meta_root: str) -> str:
        path = self._normalize(meta_root)
        if not path:
            return ''
        if self._basename(path) == self.META_DIRNAME:
            return self._dirname(path)
        return path

    def show_json_path(self, meta_root: str, title: str) -> str:
        key = self.title_key(title)
        meta_root = self._normalize_meta_root(meta_root)
        if not meta_root or not key:
            return ''
        return self._join(meta_root, self.META_DIRNAME, f'{key}.json')

    def episode_json_path(self, meta_root: str, title: str, season: int, episode: int) -> str:
        key = self.title_key(title)
        ep_key = self.episode_key(season, episode)
        meta_root = self._normalize_meta_root(meta_root)
        if not meta_root or not key or not ep_key:
            return ''
        return self._join(meta_root, self.META_DIRNAME, key, f'{ep_key}.json')

    def _load_json(self, path: str, label: str) -> Optional[Dict[str, Any]]:
        if not path or not self._isfile(path):
            return None
        raw = self._read_text(path)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                xbmc.log(
                    f'[{self._cfg.addon_name()}] local hit: {path!r} ({label})',
                    xbmc.LOGINFO,
                )
                return data
        except (json.JSONDecodeError, TypeError) as err:
            xbmc.log(f'[{self._cfg.addon_name()}] json parse failed: {path!r} {err}', xbmc.LOGWARNING)
        return None

    def _save_json(self, path: str, label: str, data: Dict[str, Any]) -> bool:
        if not path:
            return False
        body = json.dumps(data, ensure_ascii=False, indent=2)
        if self._write_text(path, body):
            xbmc.log(f'[{self._cfg.addon_name()}] saved: {path!r} ({label})', xbmc.LOGINFO)
            return True
        xbmc.log(f'[{self._cfg.addon_name()}] save failed: {path!r}', xbmc.LOGERROR)
        return False

    def load_show(self, meta_root: str, title: str) -> Optional[Dict[str, Any]]:
        path = self.show_json_path(meta_root, title)
        key = self.title_key(title)
        return self._load_json(path, f'show={key!r}')

    def save_show(self, meta_root: str, title: str, data: Dict[str, Any]) -> bool:
        key = self.title_key(title)
        if not key:
            xbmc.log(f'[{self._cfg.addon_name()}] save skip: invalid title {title!r}', xbmc.LOGWARNING)
            return False
        return self._save_json(self.show_json_path(meta_root, title), f'show={key!r}', data)

    def load_episode(
        self, meta_root: str, title: str, season: int, episode: int,
    ) -> Optional[Dict[str, Any]]:
        path = self.episode_json_path(meta_root, title, season, episode)
        label = f'{self.title_key(title)!r}/{self.episode_key(season, episode)}'
        return self._load_json(path, label)

    def episode_dir_path(self, meta_root: str, title: str) -> str:
        key = self.title_key(title)
        meta_root = self._normalize_meta_root(meta_root)
        if not meta_root or not key:
            return ''
        return self._join(meta_root, self.META_DIRNAME, key)

    def load_season_local(
        self, meta_root: str, title: str, season: int,
    ) -> Dict[int, Dict[str, Any]]:
        """读取某一季全部本地单集 JSON，返回 episode_number -> data。"""
        ep_dir = self.episode_dir_path(meta_root, title)
        key = self.title_key(title)
        if not ep_dir or not key:
            return {}
        prefix = f'S{int(season):02d}E'
        result: Dict[int, Dict[str, Any]] = {}
        for name in self._list_files(ep_dir):
            if not name.lower().endswith('.json') or not name.upper().startswith(prefix):
                continue
            parsed = self.parse_episode_filename(name)
            if not parsed or parsed[0] != int(season):
                continue
            ep_num = parsed[1]
            path = self._join(ep_dir, name)
            data = self._load_json(path, f'{key!r}/{self.episode_key(season, ep_num)}')
            if data:
                result[ep_num] = data
        return result

    def local_season_numbers(self, meta_root: str, title: str) -> List[int]:
        """从本地 SxxExx.json 文件名推断季号列表。"""
        ep_dir = self.episode_dir_path(meta_root, title)
        if not ep_dir:
            return []
        seasons: set[int] = set()
        for name in self._list_files(ep_dir):
            parsed = self.parse_episode_filename(name)
            if parsed and parsed[0] >= 1:
                seasons.add(parsed[0])
        return sorted(seasons)

    @staticmethod
    def episode_count_from_show(show_data: Optional[Dict[str, Any]], season: int) -> Optional[int]:
        if not show_data:
            return None
        for item in show_data.get('seasons') or []:
            if not isinstance(item, dict):
                continue
            sn = item.get('season_number')
            if sn is None or int(sn) != int(season):
                continue
            count = item.get('episode_count')
            if count is not None:
                try:
                    return int(count)
                except (TypeError, ValueError):
                    return None
        return None

    def save_episode(
        self, meta_root: str, title: str, season: int, episode: int, data: Dict[str, Any],
    ) -> bool:
        key = self.title_key(title)
        if not key:
            return False
        path = self.episode_json_path(meta_root, title, season, episode)
        label = f'{key}/{self.episode_key(season, episode)}'
        return self._save_json(path, label, data)
