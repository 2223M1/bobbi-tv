#!/usr/bin/env python3

from lib.boot_gate import ready
if not ready():
    import xbmcgui
    xbmcgui.Dialog().ok('波比 TV', '安装尚未完成，请打开“波比 TV · 开始使用”恢复或重试。')
    raise SystemExit(0)

from lib.router import addon_router
from lib.utils.kodi.utils import load_saved_view_properties

load_saved_view_properties()
addon_router()
