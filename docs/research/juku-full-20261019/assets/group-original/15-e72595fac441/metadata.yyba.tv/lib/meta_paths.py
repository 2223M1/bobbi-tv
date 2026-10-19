# -*- coding: utf-8 -*-
"""Resolve .meta directory paths (optional, independent of media source)."""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Dict, Optional

from lib import settings
from lib import vfs

META_DIRNAME = '.meta'
MOVIE_NFO = 'movie.nfo'
TVSHOW_NFO = 'tvshow.nfo'
POSTER_FILE = 'poster.jpg'
FANART_FILE = 'fanart.jpg'


def _meta_path_from_params(params: Optional[Dict[str, str]]) -> str:
    if not params:
        return ''
    raw = params.get('meta_path', '')
    if raw and not str(raw).startswith('plugin://'):
        return urllib.parse.unquote(str(raw).strip())
    return ''


def get_meta_root(params: Optional[Dict[str, str]] = None) -> str:
    """
    Optional .meta storage root. When empty, skip local read/write and use TMDB only.
    Structure: {meta_root}/.meta/{media_key}/
    """
    if params is None:
        params = settings.get_request_params()

    from_params = _meta_path_from_params(params)
    if from_params:
        return from_params

    return settings.get_setting('meta_path').strip()


def media_key_from_params(title: str, year: Optional[str] = None, filename_hint: str = '') -> str:
    if filename_hint:
        base = vfs.basename(filename_hint.strip())
        if '.' in base:
            base = base.rsplit('.', 1)[0]
        if base:
            return base.strip()

    clean_title = (title or '').strip()
    if not clean_title:
        return ''

    if year and str(year).isdigit():
        if re.search(r'\(\s*\d{4}\s*\)', clean_title):
            return clean_title
        return f'{clean_title} ({year})'
    return clean_title


def movie_meta_dir(meta_root: str, media_key: str) -> str:
    return vfs.join(meta_root, META_DIRNAME, media_key)


def show_meta_dir(meta_root: str, show_key: str) -> str:
    return vfs.join(meta_root, META_DIRNAME, show_key)


def episode_nfo_path(show_meta: str, season: int, episode: int) -> str:
    season_dir = vfs.join(show_meta, f'season{season:02d}')
    return vfs.join(season_dir, f'S{season:02d}E{episode:02d}.nfo')


def movie_nfo_path(meta_dir: str) -> str:
    return vfs.join(meta_dir, MOVIE_NFO)


def tvshow_nfo_path(meta_dir: str) -> str:
    return vfs.join(meta_dir, TVSHOW_NFO)


def poster_path(meta_dir: str) -> str:
    return vfs.join(meta_dir, POSTER_FILE)


def fanart_path(meta_dir: str) -> str:
    return vfs.join(meta_dir, FANART_FILE)
