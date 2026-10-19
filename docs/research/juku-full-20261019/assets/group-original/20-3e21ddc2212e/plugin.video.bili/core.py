# -*- coding:utf-8 -*-
"""
plugin.py - 插件框架核心，提供 Plugin 类（路由 / 存储 / 缓存 / ListItem 构建）
与 xbmcswift2 兼容的接口；底层使用 Kodi 21 原生 Python API。

core.py 仅做重导出。所有模块应统一 `from core import plugin, xbmc, xbmcplugin,
xbmcvfs, xbmcgui, xbmcaddon`。
"""
from plugin import Plugin, xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon

plugin = Plugin()
