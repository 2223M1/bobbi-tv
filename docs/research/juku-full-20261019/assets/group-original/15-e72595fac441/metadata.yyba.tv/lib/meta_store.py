# -*- coding: utf-8 -*-
"""Local-first metadata load/save for .meta directories."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import xbmc

from lib import settings
from lib import vfs
from lib.artwork import resolve_local_artwork
from lib.http_client import build_image_url
from lib.meta_paths import (
    episode_nfo_path,
    fanart_path,
    movie_meta_dir,
    movie_nfo_path,
    poster_path,
    show_meta_dir,
    tvshow_nfo_path,
)
from lib.nfo_reader import read_episode_nfo, read_movie_nfo, read_tvshow_nfo
from lib.nfo_writer import write_episode_nfo, write_movie_nfo, write_tvshow_nfo


def _poster_size() -> str:
    return settings.get_setting('poster_size', 'w500') or 'w500'


def _fanart_size() -> str:
    return settings.get_setting('fanart_size', 'w1280') or 'w1280'


def _format_people(value) -> str:
    if not value:
        return ''
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get('name', '')
            else:
                name = str(item)
            if name:
                names.append(name)
        return ' / '.join(names)
    return str(value)


def _format_genres(value) -> str:
    if not value:
        return ''
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return ' / '.join(g.get('name', '') for g in value if g.get('name'))
        return ' / '.join(str(g) for g in value if g)
    return str(value)


def _build_cast(credits: Dict[str, Any], limit: int = 10) -> List[Tuple[str, str]]:
    cast: List[Tuple[str, str]] = []
    for item in (credits or {}).get('cast', [])[:limit]:
        name = item.get('name', '')
        role = item.get('character', '')
        if name:
            cast.append((name, role))
    return cast


def _local_art_paths(meta_dir: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    poster = poster_path(meta_dir)
    fanart = fanart_path(meta_dir)
    if vfs.isfile(poster):
        meta['poster_local'] = poster
    if vfs.isfile(fanart):
        meta['fanart_local'] = fanart
    return meta


def load_movie_metadata(meta_root: str, media_key: str) -> Optional[Dict[str, Any]]:
    if not meta_root or not media_key:
        return None
    meta_dir = movie_meta_dir(meta_root, media_key)
    nfo = movie_nfo_path(meta_dir)
    meta = read_movie_nfo(nfo)
    if not meta:
        return None
    return _local_art_paths(meta_dir, meta)


def tmdb_movie_to_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    credits = data.get('credits') or {}
    release_date = data.get('release_date') or ''
    year = release_date[:4] if len(release_date) >= 4 else ''
    runtime = data.get('runtime') or 0
    uniqueids = {'tmdb': str(data.get('id', ''))}
    if data.get('imdb_id'):
        uniqueids['imdb'] = data['imdb_id']
    directors = [c.get('name', '') for c in credits.get('crew', []) if c.get('job') == 'Director']
    writers = [c.get('name', '') for c in credits.get('crew', []) if c.get('department') == 'Writing']
    return {
        'title': data.get('title') or '',
        'originaltitle': data.get('original_title') or data.get('title') or '',
        'plot': data.get('overview') or '',
        'year': year,
        'premiered': release_date,
        'rating': str(data.get('vote_average') or ''),
        'votes': str(data.get('vote_count') or ''),
        'runtime': str(runtime),
        'tagline': data.get('tagline') or '',
        'genre': _format_genres(data.get('genres')),
        'director': ' / '.join(directors),
        'writer': ' / '.join(writers[:5]),
        'country': _format_genres(data.get('production_countries')),
        'status': data.get('status') or '',
        'uniqueids': uniqueids,
        'cast': _build_cast(credits),
        'poster_url': build_image_url(data.get('poster_path') or '', _poster_size()),
        'fanart_url': build_image_url(data.get('backdrop_path') or '', _fanart_size()),
        'poster': 'poster.jpg',
        'fanart': 'fanart.jpg',
    }


def save_movie_metadata(meta_root: str, media_key: str, tmdb_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not meta_root or not media_key:
        return None
    meta_dir = movie_meta_dir(meta_root, media_key)
    meta = tmdb_movie_to_meta(tmdb_data)
    try:
        vfs.makedirs(meta_dir)
        poster_local, fanart_local = resolve_local_artwork(
            meta_dir,
            meta.get('poster_url', ''),
            meta.get('fanart_url', ''),
        )
        write_movie_nfo(movie_nfo_path(meta_dir), meta)
        saved = load_movie_metadata(meta_root, media_key)
        if saved:
            if poster_local:
                saved['poster_local'] = poster_local
            if fanart_local:
                saved['fanart_local'] = fanart_local
        return saved or meta
    except Exception as err:
        xbmc.log(f'[{settings.get_addon_name()}] save_movie_metadata failed: {err}', xbmc.LOGERROR)
        meta['poster_local'] = ''
        meta['fanart_local'] = ''
        return meta


def load_tvshow_metadata(meta_root: str, show_key: str) -> Optional[Dict[str, Any]]:
    if not meta_root or not show_key:
        return None
    meta_dir = show_meta_dir(meta_root, show_key)
    meta = read_tvshow_nfo(tvshow_nfo_path(meta_dir))
    if not meta:
        return None
    return _local_art_paths(meta_dir, meta)


def tmdb_tv_to_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    credits = data.get('credits') or {}
    first_air = data.get('first_air_date') or ''
    year = first_air[:4] if len(first_air) >= 4 else ''
    uniqueids = {'tmdb': str(data.get('id', ''))}
    return {
        'title': data.get('name') or '',
        'originaltitle': data.get('original_name') or data.get('name') or '',
        'plot': data.get('overview') or '',
        'year': year,
        'premiered': first_air,
        'rating': str(data.get('vote_average') or ''),
        'votes': str(data.get('vote_count') or ''),
        'runtime': str((data.get('episode_run_time') or [0])[0] if data.get('episode_run_time') else ''),
        'tagline': '',
        'genre': _format_genres(data.get('genres')),
        'status': data.get('status') or '',
        'uniqueids': uniqueids,
        'cast': _build_cast(credits),
        'poster_url': build_image_url(data.get('poster_path') or '', _poster_size()),
        'fanart_url': build_image_url(data.get('backdrop_path') or '', _fanart_size()),
        'poster': 'poster.jpg',
        'fanart': 'fanart.jpg',
    }


def save_tvshow_metadata(meta_root: str, show_key: str, tmdb_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not meta_root or not show_key:
        return None
    meta_dir = show_meta_dir(meta_root, show_key)
    meta = tmdb_tv_to_meta(tmdb_data)
    try:
        vfs.makedirs(meta_dir)
        poster_local, fanart_local = resolve_local_artwork(
            meta_dir,
            meta.get('poster_url', ''),
            meta.get('fanart_url', ''),
        )
        write_tvshow_nfo(tvshow_nfo_path(meta_dir), meta)
        saved = load_tvshow_metadata(meta_root, show_key)
        if saved:
            if poster_local:
                saved['poster_local'] = poster_local
            if fanart_local:
                saved['fanart_local'] = fanart_local
        return saved or meta
    except Exception as err:
        xbmc.log(f'[{settings.get_addon_name()}] save_tvshow_metadata failed: {err}', xbmc.LOGERROR)
        return meta


def load_episode_metadata(meta_root: str, show_key: str, season: int, episode: int) -> Optional[Dict[str, Any]]:
    if not meta_root or not show_key:
        return None
    meta_dir = show_meta_dir(meta_root, show_key)
    path = episode_nfo_path(meta_dir, season, episode)
    return read_episode_nfo(path)


def tmdb_episode_to_meta(data: Dict[str, Any], season: int, episode: int) -> Dict[str, Any]:
    uniqueids = {'tmdb': str(data.get('id', ''))}
    return {
        'title': data.get('name') or '',
        'plot': data.get('overview') or '',
        'season': str(season),
        'episode': str(episode),
        'aired': data.get('air_date') or '',
        'runtime': str(data.get('runtime') or ''),
        'rating': str(data.get('vote_average') or ''),
        'uniqueids': uniqueids,
        'thumb_url': build_image_url(data.get('still_path') or '', _poster_size()),
        'thumb': '',
    }


def save_episode_metadata(
    meta_root: str,
    show_key: str,
    season: int,
    episode: int,
    tmdb_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not meta_root or not show_key:
        return None
    meta_dir = show_meta_dir(meta_root, show_key)
    meta = tmdb_episode_to_meta(tmdb_data, season, episode)
    path = episode_nfo_path(meta_dir, season, episode)
    try:
        vfs.makedirs(vfs.dirname(path))
        still_url = meta.get('thumb_url', '')
        if still_url:
            from lib.artwork import download_image

            still_path = vfs.join(vfs.dirname(path), f'S{season:02d}E{episode:02d}.jpg')
            if download_image(still_url, still_path):
                meta['thumb'] = still_path
        write_episode_nfo(path, meta)
        return read_episode_nfo(path)
    except Exception as err:
        xbmc.log(f'[{settings.get_addon_name()}] save_episode_metadata failed: {err}', xbmc.LOGERROR)
        return meta
