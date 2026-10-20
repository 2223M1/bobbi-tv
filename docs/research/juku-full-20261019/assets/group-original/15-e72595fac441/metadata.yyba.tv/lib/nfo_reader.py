# -*- coding: utf-8 -*-
"""Parse Kodi-compatible NFO files."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from lib import vfs


def _text(element) -> str:
    if element is None or element.text is None:
        return ''
    return element.text.strip()


def _parse_unique_ids(root) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for node in root.findall('uniqueid'):
        uid_type = node.get('type', '')
        value = _text(node)
        if uid_type and value:
            ids[uid_type] = value
    return ids


def _parse_actors(root) -> List[Tuple[str, str]]:
    cast: List[Tuple[str, str]] = []
    for actor in root.findall('actor'):
        name = _text(actor.find('name'))
        role = _text(actor.find('role'))
        if name:
            cast.append((name, role))
    return cast


def _parse_fanart(root) -> str:
    fanart = root.find('fanart')
    if fanart is None:
        return ''
    thumb = fanart.find('thumb')
    return _text(thumb)


def read_movie_nfo(path: str) -> Optional[Dict[str, Any]]:
    root = vfs.parse_xml(path)
    if root is None or root.tag != 'movie':
        return None
    return {
        'title': _text(root.find('title')),
        'originaltitle': _text(root.find('originaltitle')),
        'plot': _text(root.find('plot')),
        'year': _text(root.find('year')),
        'premiered': _text(root.find('premiered')),
        'rating': _text(root.find('rating')),
        'votes': _text(root.find('votes')),
        'runtime': _text(root.find('runtime')),
        'tagline': _text(root.find('tagline')),
        'genre': _text(root.find('genre')),
        'director': _text(root.find('director')),
        'writer': _text(root.find('writer')),
        'country': _text(root.find('country')),
        'status': _text(root.find('status')),
        'uniqueids': _parse_unique_ids(root),
        'cast': _parse_actors(root),
        'poster': _text(root.find('thumb')),
        'fanart': _parse_fanart(root),
    }


def read_tvshow_nfo(path: str) -> Optional[Dict[str, Any]]:
    root = vfs.parse_xml(path)
    if root is None or root.tag != 'tvshow':
        return None
    return {
        'title': _text(root.find('title')),
        'originaltitle': _text(root.find('originaltitle')),
        'plot': _text(root.find('plot')),
        'year': _text(root.find('year')),
        'premiered': _text(root.find('premiered')),
        'rating': _text(root.find('rating')),
        'votes': _text(root.find('votes')),
        'runtime': _text(root.find('runtime')),
        'tagline': _text(root.find('tagline')),
        'genre': _text(root.find('genre')),
        'status': _text(root.find('status')),
        'uniqueids': _parse_unique_ids(root),
        'cast': _parse_actors(root),
        'poster': _text(root.find('thumb')),
        'fanart': _parse_fanart(root),
    }


def read_episode_nfo(path: str) -> Optional[Dict[str, Any]]:
    root = vfs.parse_xml(path)
    if root is None or root.tag != 'episodedetails':
        return None
    return {
        'title': _text(root.find('title')),
        'plot': _text(root.find('plot')),
        'season': _text(root.find('season')),
        'episode': _text(root.find('episode')),
        'aired': _text(root.find('aired')),
        'runtime': _text(root.find('runtime')),
        'rating': _text(root.find('rating')),
        'uniqueids': _parse_unique_ids(root),
        'thumb': _text(root.find('thumb')),
    }
