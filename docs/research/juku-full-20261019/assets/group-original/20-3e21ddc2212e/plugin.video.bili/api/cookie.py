# -*- coding:utf-8 -*-
"""Cookie 读取、解析、缓存；自动补全 buvid3 避免 CDN 403。"""
import re
import time
import uuid

from core import plugin


# 编译后的正则缓存，避免每个 key 重复编译
_cookie_re_cache = {}


def _ensure_buvid3(cookie: str) -> str:
    """确保 cookie 中存在 buvid3，不存在则从持久化存储中读取或生成。

    B 站 CDN 拒绝没有 buvid3 的请求（参考 wiliwili 做法）。
    """
    if 'buvid3=' in cookie:
        return cookie
    account = plugin.get_storage('account')
    saved = account.get('_buvid3', '')
    if not saved:
        # uuid4().hex 是 32 字符，拼接两次得 64 字符，匹配 B 站实际 buvid3 长度。
        saved = uuid.uuid4().hex + uuid.uuid4().hex
        account['_buvid3'] = saved
        # 显式 sync：plugin 进程的 atexit 时机不可靠（Kodi 中途切换
        # 目录可能跳过正常退出），落盘失败的话下次启动又得重新生成。
        account.sync()
    prefix = f'buvid3={saved}; '
    return prefix + cookie if cookie else prefix.rstrip('; ')


_cookie_cache = None
_cookie_cache_time = 0
_COOKIE_CACHE_TTL = 60  # 60s 内存缓存，避免每次请求都读磁盘


def clear_cookie_cache():
    """login/logout 路由调用，强制刷新 cookie 缓存。"""
    global _cookie_cache, _cookie_cache_time
    _cookie_cache = None
    _cookie_cache_time = 0


def get_cookie() -> str:
    """从持久化存储中读取 cookie，注入 buvid3，按 60s TTL 内存缓存。"""
    global _cookie_cache, _cookie_cache_time
    now = time.time()
    if _cookie_cache is not None and now - _cookie_cache_time < _COOKIE_CACHE_TTL:
        return _cookie_cache
    account = plugin.get_storage('account')
    cookie = account.get('cookie', '')
    cookie = _ensure_buvid3(cookie)
    _cookie_cache = cookie
    _cookie_cache_time = now
    return cookie


def get_cookie_value(key: str) -> str:
    """从 cookie 字符串中精确取 key 对应的 value（避免部分匹配）。"""
    cookie = get_cookie()
    if not cookie:
        return ''
    if key not in _cookie_re_cache:
        _cookie_re_cache[key] = re.compile(
            r'(?:^|;\s*)' + re.escape(key) + r'=([^;]*)'
        )
    m = _cookie_re_cache[key].search(cookie)
    return m.group(1) if m else ''


def get_uid() -> str:
    """当前登录用户的 mid，未登录返回 '0'。"""
    return get_cookie_value('DedeUserID') or '0'
