# -*- coding:utf-8 -*-
"""显示、格式化、文件系统等工具函数（无 plugin 依赖）。

职责速查（8 类，故意不拆 — 拆出去会引发循环 import，且单文件 125 行
仍在阅读舒适区）:
  1. UI 标签       tag, parts_tag
  2. 数字/时间转换 convert_number, timestamp_to_date, parse_duration
  3. 通知/对话框   notify, notify_error
  4. 设置/本地化   getSetting, localize, _get_addon
  5. 插件能力探测  is_dash_capable, install_adaptive, _ADAPTIVE_ADDON_ID
  6. 文本清理      clear_text
  7. 播放统计格式化 format_stat
  8. 文件系统      make_dirs, safe_remove_dir, get_temp_path, remove_dir
"""
import sys
import os
import re
import shutil
from datetime import datetime
from urllib.parse import urljoin

from core import xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon


def tag(info, color='red'):
    return f'[COLOR {color}]{info}[/COLOR]'


def parts_tag(p):
    return tag(f'【{p}P】', 'red')


def convert_number(num):
    if isinstance(num, str):
        return num
    if num < 10000:
        return str(num)
    if num < 99999500:
        result = round(num / 10000, 1)
        return str(result) + "万"
    else:
        result = round(num / 100000000, 1)
        return str(result) + "亿"


def timestamp_to_date(timestamp):
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y.%m.%d %H:%M:%S')


def notify(title, msg, t=1500):
    xbmcgui.Dialog().notification(title, msg, xbmcgui.NOTIFICATION_INFO, t, False)


def notify_error(res):
    message = res.get('message', '未知错误')
    notify('提示', f'{res.get("code", -1)}: {message}')


# 缓存 Addon 单例：localize / getSetting 在路由里调用频繁，每次新建
# xbmcaddon.Addon() 实例在 Kodi 21 里要走 Python ↔ C 桥接，省一次是一次。
_addon = None


def _get_addon():
    global _addon
    if _addon is None:
        _addon = xbmcaddon.Addon()
    return _addon


def localize(id):
    return _get_addon().getLocalizedString(id)


def getSetting(name):
    """Read an addon setting.

    In `addon.py` (CPythonInvoker) sys.argv[1] is the plugin handle
    that xbmcplugin.getSetting() requires. In `service.py` (long-lived
    xbmc.service) there is no plugin handle — sys.argv is just
    ['service.py'] — and the int() call would IndexError. Fall back
    to xbmcaddon.Addon().getSetting() which works in both contexts.
    """
    try:
        handle = int(sys.argv[1])
        return xbmcplugin.getSetting(handle, name)
    except (IndexError, ValueError):
        # service.py or any non-plugin context
        return _get_addon().getSetting(name)


# 全插件只这一处出现 addon id 字符串，改名时同步 addon.xml。
_ADAPTIVE_ADDON_ID = 'inputstream.adaptive'


def is_dash_capable():
    """点播能否走 DASH — 装 inputstream.adaptive 才有 (4K/HDR/Hi-Res/Atmos)；否则最高 720P (durl)。

    Kodi 21 每次导航是新进程，这里不需要缓存；不调用即无成本。
    """
    return bool(xbmc.getCondVisibility('System.HasAddon(%s)' % _ADAPTIVE_ADDON_ID))


def install_adaptive():
    """触发 Kodi 安装 inputstream.adaptive (异步, 不阻塞当前路由)。"""
    xbmc.executebuiltin('InstallAddon(%s)' % _ADAPTIVE_ADDON_ID)


def clear_text(text):
    return text.replace('<em class="keyword">', '').replace('</em>', '')


# 播放统计字段映射：(字段名, 中文标签)，按优先级排列；同标签只取第一个匹配
_STAT_KEY_MAP = [
    ('view', '播放'), ('play', '播放'), ('like', '点赞'), ('likes', '点赞'),
    ('coin', '投币'), ('favorite', '收藏'), ('collect', '收藏'),
    ('reply', '评论'), ('comment', '评论'), ('danmaku', '弹幕'),
    ('share', '分享'),
]


def format_stat(item):
    """从B站API返回的item中提取格式化后的播放统计字符串"""
    state = ''
    seen_labels = set()
    if 'stat' in item:
        stat = item['stat']
        for key, label in _STAT_KEY_MAP:
            if key in stat and label not in seen_labels:
                state += f"{convert_number(stat[key])}{label} · "
                seen_labels.add(label)
    elif 'cnt_info' in item:
        stat = item['cnt_info']
        for key, label in _STAT_KEY_MAP:
            if key in stat and label not in seen_labels:
                state += f"{convert_number(stat[key])}{label} · "
                seen_labels.add(label)
    else:
        if 'play' in item and isinstance(item['play'], int):
            state += f"{convert_number(item['play'])}播放 · "
        if 'comment' in item and isinstance(item['comment'], int):
            state += f"{convert_number(item['comment'])}评论 · "
    return state


def parse_duration(duration_text):
    parts = duration_text.split(':')
    duration = 0
    for part in parts:
        duration = duration * 60 + int(part)
    return duration


def make_dirs(path):
    """确保目录存在（不存在则创建）。返回 None。"""
    if not path.endswith('/'):
        path = path + '/'
    path = xbmc.translatePath(path)
    if xbmcvfs.exists(path):
        return
    try:
        _ = xbmcvfs.mkdirs(path)
    except Exception as e:
        xbmc.log('[plugin.video.bili] mkdirs via xbmcvfs failed: %s' % str(e), xbmc.LOGWARNING)
    if not xbmcvfs.exists(path):
        try:
            os.makedirs(path)
        except Exception as e:
            xbmc.log('[plugin.video.bili] mkdirs via os failed: %s' % str(e), xbmc.LOGWARNING)


def get_temp_path():
    temppath = xbmc.translatePath('special://temp/plugin.video.bili/')
    make_dirs(temppath)
    return temppath


def remove_dir(path):
    """强制删除目录：xbmcvfs.rmdir force=True → shutil.rmtree fallback。"""
    if not os.path.isdir(path):
        return
    try:
        xbmcvfs.rmdir(path, force=True)
    except Exception as e:
        xbmc.log('[plugin.video.bili] xbmcvfs.rmdir failed: %s' % e, xbmc.LOGWARNING)
    if os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            xbmc.log('[plugin.video.bili] shutil.rmtree failed: %s' % e, xbmc.LOGWARNING)


def rewrite_m3u8_relative_urls(text, base_url):
    """把 m3u8 文本里所有相对路径 URL 改成绝对路径。

    B 站 HLS m3u8 文本里 #EXT-X-MAP:URI 和 #EXTINF: 后的 segment URL
    可能是相对路径（如 'init.mp4' 或 'seg.m4s'）。ffmpeg 用 m3u8 base
    URL 拼接相对路径时，本地代理模式下会拼到 http://127.0.0.1:54321/
    下导致 404。需要在写本地文件前重写为基于 m3u8 URL 的绝对路径。

    绝对路径（http:// 或 https://）原样保留。
    """
    lines = text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        # 处理 #EXT-X-MAP:URI="..." 中的相对路径
        if stripped.startswith('#EXT-X-MAP:'):

            def _abs_uri(m):
                uri = m.group(1)
                if not uri.startswith(('http://', 'https://')):
                    uri = urljoin(base_url, uri)
                return 'URI="%s"' % uri

            line = re.sub(r'URI="([^"]*)"', _abs_uri, line)
            out.append(line)
        elif stripped and not stripped.startswith('#'):
            # 非注释行：segment URL 行；可能是相对路径
            if not stripped.startswith(('http://', 'https://')):
                line = urljoin(base_url, stripped)
            out.append(line)
        else:
            out.append(line)
    return '\n'.join(out)
