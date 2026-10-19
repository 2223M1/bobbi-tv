# -*- coding: utf-8 -*-
"""Download artwork to .meta directories."""

from __future__ import annotations

import xbmc

from lib import settings
from lib import vfs
from lib.http_client import open_image_url


def download_image(url: str, dest_path: str, timeout: int = 15) -> bool:
    if not url:
        return False
    try:
        with open_image_url(url, timeout=timeout) as response:
            data = response.read()
        if not data:
            xbmc.log(f'[{settings.get_addon_name()}] download_image empty: {url}', xbmc.LOGWARNING)
            return False
        ok = vfs.write_bytes(dest_path, data)
        if ok:
            xbmc.log(
                f'[{settings.get_addon_name()}] download_image ok: {dest_path}',
                xbmc.LOGDEBUG,
            )
        return ok
    except Exception as err:
        xbmc.log(
            f'[{settings.get_addon_name()}] download_image failed ({url}): {err}',
            xbmc.LOGWARNING,
        )
        return False


def resolve_local_artwork(meta_dir: str, poster_url: str, fanart_url: str) -> tuple:
    from lib.meta_paths import fanart_path, poster_path

    poster_dest = poster_path(meta_dir)
    fanart_dest = fanart_path(meta_dir)

    poster_local = poster_dest if vfs.isfile(poster_dest) else ''
    fanart_local = fanart_dest if vfs.isfile(fanart_dest) else ''

    if poster_url and not poster_local:
        if download_image(poster_url, poster_dest):
            poster_local = poster_dest

    if fanart_url and not fanart_local:
        if download_image(fanart_url, fanart_dest):
            fanart_local = fanart_dest

    return poster_local, fanart_local


def ensure_kodi_artwork(meta: dict, cache_key: str) -> dict:
    """Cache poster/fanart under addon profile when .meta is not configured."""
    if not cache_key:
        return meta
    cache_dir = vfs.join(settings.get_profile_path(), 'artcache', cache_key)
    poster_url = meta.get('poster_url', '')
    fanart_url = meta.get('fanart_url', '')
    if poster_url and not meta.get('poster_local'):
        dest = vfs.join(cache_dir, 'poster.jpg')
        if download_image(poster_url, dest) or vfs.isfile(dest):
            meta['poster_local'] = dest
    if fanart_url and not meta.get('fanart_local'):
        dest = vfs.join(cache_dir, 'fanart.jpg')
        if download_image(fanart_url, dest) or vfs.isfile(dest):
            meta['fanart_local'] = dest
    return meta
