# -*- coding: utf-8 -*-
"""Write Kodi-compatible NFO files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, Tuple

from lib import vfs


def _sub(parent: ET.Element, tag: str, text: str = '') -> ET.Element:
    node = ET.SubElement(parent, tag)
    if text:
        node.text = str(text)
    return node


def _add_unique_ids(parent: ET.Element, uniqueids: Dict[str, str], default: str = 'tmdb') -> None:
    for key, value in uniqueids.items():
        if not value:
            continue
        node = _sub(parent, 'uniqueid', str(value))
        node.set('type', key)
        if key == default:
            node.set('default', 'true')


def _add_cast(parent: ET.Element, cast: Iterable[Tuple[str, str]]) -> None:
    for name, role in cast:
        actor = ET.SubElement(parent, 'actor')
        _sub(actor, 'name', name)
        if role:
            _sub(actor, 'role', role)


def write_movie_nfo(path: str, meta: Dict[str, Any]) -> None:
    root = ET.Element('movie')
    _sub(root, 'title', meta.get('title', ''))
    _sub(root, 'originaltitle', meta.get('originaltitle', ''))
    _sub(root, 'year', meta.get('year', ''))
    _sub(root, 'plot', meta.get('plot', ''))
    _sub(root, 'tagline', meta.get('tagline', ''))
    _sub(root, 'premiered', meta.get('premiered', ''))
    _sub(root, 'rating', meta.get('rating', ''))
    _sub(root, 'votes', meta.get('votes', ''))
    _sub(root, 'runtime', meta.get('runtime', ''))
    _sub(root, 'genre', meta.get('genre', ''))
    _sub(root, 'director', meta.get('director', ''))
    _sub(root, 'writer', meta.get('writer', ''))
    _sub(root, 'country', meta.get('country', ''))
    _sub(root, 'status', meta.get('status', ''))
    _add_unique_ids(root, meta.get('uniqueids', {}), 'tmdb')
    _add_cast(root, meta.get('cast', []))
    poster = meta.get('poster', 'poster.jpg')
    if poster:
        thumb = _sub(root, 'thumb', poster)
        thumb.set('aspect', 'poster')
    fanart_path = meta.get('fanart', 'fanart.jpg')
    if fanart_path:
        fanart = ET.SubElement(root, 'fanart')
        _sub(fanart, 'thumb', fanart_path)
    vfs.write_xml(path, root)


def write_tvshow_nfo(path: str, meta: Dict[str, Any]) -> None:
    root = ET.Element('tvshow')
    _sub(root, 'title', meta.get('title', ''))
    _sub(root, 'originaltitle', meta.get('originaltitle', ''))
    _sub(root, 'year', meta.get('year', ''))
    _sub(root, 'plot', meta.get('plot', ''))
    _sub(root, 'tagline', meta.get('tagline', ''))
    _sub(root, 'premiered', meta.get('premiered', ''))
    _sub(root, 'rating', meta.get('rating', ''))
    _sub(root, 'votes', meta.get('votes', ''))
    _sub(root, 'runtime', meta.get('runtime', ''))
    _sub(root, 'genre', meta.get('genre', ''))
    _sub(root, 'status', meta.get('status', ''))
    _add_unique_ids(root, meta.get('uniqueids', {}), 'tmdb')
    _add_cast(root, meta.get('cast', []))
    poster = meta.get('poster', 'poster.jpg')
    if poster:
        thumb = _sub(root, 'thumb', poster)
        thumb.set('aspect', 'poster')
    fanart_path = meta.get('fanart', 'fanart.jpg')
    if fanart_path:
        fanart = ET.SubElement(root, 'fanart')
        _sub(fanart, 'thumb', fanart_path)
    vfs.write_xml(path, root)


def write_episode_nfo(path: str, meta: Dict[str, Any]) -> None:
    root = ET.Element('episodedetails')
    _sub(root, 'title', meta.get('title', ''))
    _sub(root, 'plot', meta.get('plot', ''))
    _sub(root, 'season', meta.get('season', ''))
    _sub(root, 'episode', meta.get('episode', ''))
    _sub(root, 'aired', meta.get('aired', ''))
    _sub(root, 'runtime', meta.get('runtime', ''))
    _sub(root, 'rating', meta.get('rating', ''))
    _add_unique_ids(root, meta.get('uniqueids', {}), 'tmdb')
    thumb = meta.get('thumb', '')
    if thumb:
        _sub(root, 'thumb', thumb)
    vfs.write_xml(path, root)
