"""
plugin.py - 插件框架核心，提供 Plugin 类（路由 / 存储 / 缓存 / ListItem 构建）
与 xbmcswift2 兼容的接口；底层使用 Kodi 21 原生 Python API。

导出: Plugin, xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon

用法: from core import plugin, xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon
      (core.py 负责重导出)
"""
import sys
import os
import re
import json
import time
import atexit
import threading
from functools import wraps
from urllib.parse import urlencode as _urlencode

# Kodi 原生模块
import xbmc
import xbmcplugin
import xbmcvfs
import xbmcgui
import xbmcaddon

try:
    xbmc.translatePath = xbmcvfs.translatePath
except AttributeError:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# URL 路由
# ═══════════════════════════════════════════════════════════════════════════

class NotFoundException(Exception):
    pass


class UrlRule:
    def __init__(self, url_rule, view_func, name):
        self.view_func = view_func
        rule = url_rule if url_rule == '/' else url_rule.rstrip('/') + '/?'
        params = re.findall(r'\<(.+?)\>', url_rule)
        if params:
            # 最后一个参数允许匹配 /（视频标题、搜索关键词等可能含斜杠）
            last = params[-1]
            prefix, suffix = rule.split('<%s>' % last, 1)
            rule = prefix.replace('<', '(?P<').replace('>', '>[^/]+?)') + \
                   '(?P<%s>.+?)' % last + suffix
        else:
            rule = rule.replace('<', '(?P<').replace('>', '>[^/]+?)')
        self._regex = re.compile('^' + rule + '$')
        self._format = url_rule.replace('<', '{').replace('>', '}')
        self._params = re.findall(r'\<(.+?)\>', url_rule)

    def match(self, path):
        m = self._regex.match(path)
        if m:
            return self.view_func, m.groupdict()
        raise NotFoundException()

    def make_path(self, items):
        fmt = {}
        query = {}
        for k, v in items.items():
            if k in self._params:
                fmt[k] = str(v)
            else:
                query[k] = str(v)
        path = self._format.format(**fmt)
        if query:
            path += '?' + _urlencode(query)
        return path


# ═══════════════════════════════════════════════════════════════════════════
# JSON 持久化存储
# ═══════════════════════════════════════════════════════════════════════════

def _read_json_storage(filepath):
    """从 disk 读 JSON dict。失败/不存在/类型不对 → {}。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _write_json_storage(filepath, data):
    """写 JSON dict 到 disk。失败仅 log，不抛。"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
    except OSError:
        pass
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data if data is not None else {}, f, ensure_ascii=False)
    except IOError as e:
        xbmc.log(
            '[plugin] write %s failed: %s' % (filepath, e),
            xbmc.LOGERROR,
        )


# Plugin.read_storage 用的模块级 mtime 缓存：hot path（mpd_server 每次
# ffmpeg refresh ~4s）避免每次 open + json.load disk。state 改动频率
# ~1 次/50 分钟（daemon 续命 m3u8_url），mtime 检查 ~O(1)。
read_storage_cache_mtime = {}
read_storage_cache_data = {}


class _Storage(dict):
    def __init__(self, filepath):
        super().__init__()
        self._filepath = filepath
        self._dirty = False
        self._load()
        atexit.register(self._atexit_sync)

    def _atexit_sync(self):
        try:
            self.sync()
        except Exception:
            pass

    def _load(self):
        if os.path.isfile(self._filepath):
            self.update(_read_json_storage(self._filepath))

    def sync(self):
        if self._dirty:
            _write_json_storage(self._filepath, dict(self))
            self._dirty = False

    def close(self):
        self.sync()

    def clear(self):
        super().clear()
        self._dirty = True
        self.sync()

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        self._dirty = True

    def __delitem__(self, k):
        super().__delitem__(k)
        self._dirty = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ═══════════════════════════════════════════════════════════════════════════
# dict -> xbmcgui.ListItem 转换
# ═══════════════════════════════════════════════════════════════════════════

def _dict_to_li(item):
    label = item.get('label', '')
    path = item.get('path', '')
    li = xbmcgui.ListItem(label=label)
    # Kodi 21 构造参数里的 path 不传给 OpenInputStream，必须显式 setPath
    path_str = path or item.get('url', '')
    if path_str:
        li.setPath(path_str)
    # 标记为可播放（防止 Kodi 回退到 folder 处理）

    icon = item.get('icon', '')
    thumb = item.get('thumbnail', icon)
    if icon or thumb:
        li.setArt({'icon': icon, 'thumb': thumb})
    
    info = item.get('info', {})
    if info:
        li.setInfo(item.get('info_type', 'video'), info)
    
    props = item.get('properties') or {}
    if 'inputstream' in props:
        li.setProperty('inputstream', str(props['inputstream']))
    for k, v in props.items():
        if k == 'inputstream':
            continue
        if k.startswith('inputstream.'):
            li.setProperty(k, str(v))

    # Kodi 21: IsPlayable 必须显式设置，否则 ListItem 被当 folder 处理
    # 导致 OpenInputStream 用 plugin:// 而不是 http:// path
    li.setProperty('IsPlayable', 'true')
    
    # 直播流：Kodi 21 需要设置 IsLiveStream 防止提前终止
    # 注意：不要设置 inputstreamaddon，Kodi 21 中该属性已弃用
    if item.get('is_live'):
        li.setProperty('IsLiveStream', 'true')
        li.setProperty('IsLive', 'true')
        # Kodi 21 推荐使用 VideoInfoTag 设置直播属性
        try:
            tag = li.getVideoInfoTag()
            tag.setMediaType('video')
        except Exception:
            pass
    
    cm = item.get('context_menu', [])
    if cm:
        li.addContextMenuItems([(l, a) for l, a in cm], replaceItems=True)
    
    return li, path


# ═══════════════════════════════════════════════════════════════════════════
# Plugin 兼容类
# ═══════════════════════════════════════════════════════════════════════════

class Plugin:
    def __init__(self):
        self._addon = xbmcaddon.Addon()
        self._addon_id = self._addon.getAddonInfo('id')
        self._routes = []
        self._view_functions = {}
        self._end_of_directory = False
        self._added_items = []
        self._storage_path = xbmcvfs.translatePath(
            'special://profile/addon_data/%s/.storage/' % self._addon_id)
        os.makedirs(self._storage_path, exist_ok=True)
        self._unsynced_storages = {}

    # ── route / url_for ──────────────────────────────────────────────────

    def route(self, url_rule, name=None):
        def decorator(f):
            view_name = name or f.__name__
            rule = UrlRule(url_rule, f, view_name)
            self._view_functions[view_name] = rule
            self._routes.append(rule)
            return f
        return decorator

    def url_for(self, endpoint, **items):
        rule = self._view_functions.get(endpoint)
        if not rule:
            for r in self._view_functions.values():
                if r.view_func is endpoint:
                    rule = r
                    break
        if not rule:
            raise NotFoundException("%s doesn't match any known patterns." % endpoint)
        return 'plugin://%s%s' % (self._addon_id, rule.make_path(items))

    # ── storage ──────────────────────────────────────────────────────────

    def get_storage(self, name='main'):
        filename = os.path.join(self._storage_path, name + '.json')
        if filename in self._unsynced_storages:
            return self._unsynced_storages[filename]
        s = _Storage(filename)
        # 限制缓存数量，防止长期运行（service 模式）内存泄漏
        if len(self._unsynced_storages) >= 30:
            oldest = next(iter(self._unsynced_storages))
            try:
                self._unsynced_storages[oldest].close()
            except Exception:
                pass
            del self._unsynced_storages[oldest]
        self._unsynced_storages[filename] = s
        return s

    def read_storage(self, name='main'):
        """从 disk 直接读 storage，绕过 in-memory cache。

        长跑进程（service.py）需要在短进程（addon.py）写入 disk 后
        立刻看到新值 —— Plugin._unsynced_storages 的进程内 cache 让
        跨进程同步失效。Hot path（mpd_server 每次 ffmpeg refresh）用
        模块级 mtime 缓存避免每次都重读+json parse disk。
        """
        filename = os.path.join(self._storage_path, name + '.json')
        try:
            mtime = os.path.getmtime(filename)
        except OSError:
            return {}
        cached_mtime = read_storage_cache_mtime.get(filename)
        if cached_mtime == mtime:
            data = read_storage_cache_data.get(filename)
            if data is not None:
                return data
        data = _read_json_storage(filename)
        read_storage_cache_mtime[filename] = mtime
        read_storage_cache_data[filename] = data
        return data

    def write_storage(self, name='main', data=None):
        """直接写 storage 到 disk，绕过 in-memory cache。

        长跑进程（service.py daemon）更新状态时用这个，避免和
        短进程（addon.py）的内存 cache 不一致。同时清掉本进程的
        mtime cache，让后续 read_storage 立即看到新值。
        """
        filename = os.path.join(self._storage_path, name + '.json')
        _write_json_storage(filename, data)
        # 主动失效 cache：disk 已变，mtime 比较下次会重读，但显式清掉
        # 避免 daemon 刚写入立刻 read 时拿到旧 cache（race window）。
        read_storage_cache_mtime.pop(filename, None)
        read_storage_cache_data.pop(filename, None)

    # ── cached ───────────────────────────────────────────────────────────

    _fcache_name = '.functions'

    def cached(self, TTL=10):
        """缓存装饰器，TTL 单位为分钟，默认 10 分钟。每个缓存条目独立计时过期"""
        ttl_seconds = TTL * 60

        def decorating_function(function):
            storage = self.get_storage(self._fcache_name)

            @wraps(function)
            def wrapper(*args, **kwargs):
                key = function.__name__ + '|' + '|'.join(str(a) for a in args)
                if kwargs:
                    key += '|__KW__|' + '|'.join(
                        '%s=%s' % (k, v) for k, v in sorted(kwargs.items()))
                entry = storage.get(key)
                if entry is not None:
                    # entry 格式: [timestamp, result]；兼容旧格式（裸值）
                    if isinstance(entry, list) and len(entry) == 2:
                        if time.time() - entry[0] < ttl_seconds:
                            return entry[1]
                    else:
                        # 旧格式无时间戳，视为已过期，删除后重新请求
                        del storage[key]
                result = function(*args, **kwargs)
                storage[key] = [time.time(), result]
                # 不显式 sync，依赖 _dirty 标记 + 进程退出 atexit / close
                return result
            return wrapper
        return decorating_function

    def clear_function_cache(self):
        try:
            self.get_storage(self._fcache_name).clear()
        except Exception:
            pass

    # ── open_settings ────────────────────────────────────────────────────

    def open_settings(self):
        self._addon.openSettings()

    # ── finish / add_items ───────────────────────────────────────────────

    def _add_items(self, items):
        handle = int(sys.argv[1])
        tuples = []
        for item in items:
            if not item:
                continue
            li, path = _dict_to_li(item)
            is_folder = not item.get('is_playable', False)
            tuples.append((path, li, is_folder))
        xbmcplugin.addDirectoryItems(handle, tuples, len(tuples))
        self._added_items.extend(items)

    def finish(self, items=None, succeeded=True,
               update_listing=False, cache_to_disc=True):
        if items:
            self._add_items(items)
        self._end_of_directory = True
        handle = int(sys.argv[1])
        xbmcplugin.endOfDirectory(handle, succeeded, update_listing, cache_to_disc)
        return self._added_items

    # ── set_resolved_url ─────────────────────────────────────────────────

    def set_resolved_url(self, item=None, subtitles=None):
        handle = int(sys.argv[1])
        self._end_of_directory = True

        if item is None:
            li = xbmcgui.ListItem()
            xbmcplugin.setResolvedUrl(handle, False, li)
            return [li]

        if isinstance(item, str):
            item = {'path': item}

        li, _ = _dict_to_li(item)

        # Kodi 21: setResolvedUrl 需要 ListItem.setPath() 显式设置 path，
        # 否则 OpenInputStream 拿到的是原始 plugin:// URL
        path = item.get('path', '')
        if path:
            li.setPath(path)

        succeeded = bool(path)
        xbmc.log('[set_resolved_url] succeeded=%s path=%s props=%s' % (
            succeeded, path,
            list(item.get('properties', {}).keys()),
        ), xbmc.LOGDEBUG)
        xbmcplugin.setResolvedUrl(handle, succeeded, li)

        if subtitles:
            # Kodi 21: setSubtitles 必须在播放开始后调用，等待 player 就绪
            t = threading.Thread(target=self._wait_and_set_subtitles,
                                 args=(subtitles,), daemon=True)
            t.start()

        return [li]

    def _wait_and_set_subtitles(self, subtitles):
        """等待播放器启动后设置外挂字幕"""
        player = xbmc.Player()
        for _ in range(30):
            if player.isPlaying():
                break
            time.sleep(1)
        if player.isPlaying():
            xbmc.log('[plugin] setting subtitles: %s' % subtitles, xbmc.LOGDEBUG)
            player.setSubtitles(subtitles)
        else:
            xbmc.log('[plugin] player not started, subtitles skipped', xbmc.LOGWARNING)

    # ── run ──────────────────────────────────────────────────────────────

    def run(self):
        argv = sys.argv
        handle = int(argv[1]) if len(argv) > 1 else -1
        url = argv[0]
        query = argv[2] if len(argv) > 2 else ''

        plugin_prefix = 'plugin://' + self._addon_id
        if url.startswith(plugin_prefix):
            path = url[len(plugin_prefix):]
        else:
            path = url
        if not path.startswith('/'):
            path = '/' + path
        if query:
            path += ('?' + query) if '?' not in path else '&' + query

        for rule in self._routes:
            try:
                view_func, params = rule.match(path)
            except NotFoundException:
                continue

            result = view_func(**params)

            if handle >= 0 and not self._end_of_directory:
                if result is not None:
                    result = self.finish(result)
                else:
                    handle_int = int(sys.argv[1])
                    xbmcplugin.endOfDirectory(handle_int, False)

            for s in self._unsynced_storages.values():
                try:
                    s.close()
                except Exception:
                    pass
            return result

        xbmc.log('[plugin] no route for: %s' % path, xbmc.LOGERROR)
        if handle >= 0:
            xbmcplugin.endOfDirectory(handle, False)
        return None
