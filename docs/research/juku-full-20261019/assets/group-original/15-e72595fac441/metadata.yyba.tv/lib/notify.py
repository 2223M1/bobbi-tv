# -*- coding: utf-8 -*-
"""User notifications for configuration issues."""

from __future__ import annotations

import xbmc
import xbmcgui

from lib import settings

_shown: set = set()


def warn_once(key: str, message: str) -> None:
    if key in _shown:
        return
    _shown.add(key)
    xbmc.log(f'[{settings.get_addon_name()}] {message}', xbmc.LOGWARNING)
    try:
        xbmcgui.Dialog().notification(settings.get_addon_name(), message, xbmcgui.NOTIFICATION_WARNING, 6000)
    except Exception:
        pass
