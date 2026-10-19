# -*- coding:utf-8 -*-
"""HTTP 请求封装：UA/Referer/Cookie 注入、超时、缓存开关。

关键发现（参考 https://github.com/xfangfang/wiliwili/blob/yoga/wiliwili/include/api/bilibili/util/http.hpp）：
  wiliwili 用的是裸 `User-Agent: wiliwili`，没有任何 sec-ch-* / Accept 头。
  但它能拿到 Atmos / Hi-Res / Dolby Vision，我们用现代 Chrome 反而拿不到。
  说明 B 站 server 对"现代浏览器 UA"和"非标客户端 UA"的策略不同：
    - 现代 Chrome UA 走 web 路径，被限制只回 AAC
    - 自定义 UA 走"特殊客户端"路径，放开所有格式

所以本插件**必须用 wiliwili 风格的 UA**，不能用真实浏览器 UA。

v0.5.0: 全局复用 `requests.Session` —— B 站 API 高频轮询场景下省一次
TCP+TLS 握手/请求；Cookie 通过 `Cookie` header 显式注入，Session
自身的 cookie jar 不被使用，无串扰风险。
"""
from urllib.parse import urlencode

import requests

from core import plugin, xbmc
from utils import getSetting


# 故意用 wiliwili 自己的标识，绕开 B 站的"web 客户端降级到 AAC"策略
_USER_AGENT = 'wiliwili'
_REFERER = 'https://www.bilibili.com'

# 双超时：连接 3s, 读 10s。Kodi 媒体中心场景下挂死比快速失败更糟。
_TIMEOUT_CONNECT = 3
_TIMEOUT_READ = 10

# 喂给 inputstream.adaptive 的 stream_headers / manifest_headers 字符串
BILI_REFERER = 'Referer=https://www.bilibili.com'


# 全局 Session：所有 GET/POST 复用，TCP+TLS 握手省一次/请求。
# 默认 headers 注入 UA + Referer + Origin；Cookie 走 per-call 注入。
_session = requests.Session()
_session.headers.update({
    'User-Agent': _USER_AGENT,
    'Referer': _REFERER,
    'Origin': 'https://www.bilibili.com',
})


def _resolve_cookie() -> str:
    """延迟 import 避免 api.http ↔ api.cookie 循环。"""
    from api.cookie import get_cookie
    return get_cookie()


def post_data(url: str, data: dict) -> dict:
    headers = {}
    cookie = _resolve_cookie()
    if cookie:
        headers['Cookie'] = cookie
    try:
        res = _session.post(
            url, data=data, headers=headers,
            timeout=(_TIMEOUT_CONNECT, _TIMEOUT_READ),
        ).json()
    except Exception as e:
        xbmc.log('[api.http] post_data error: %s: %s url=%s' % (
            type(e).__name__, str(e), url), xbmc.LOGWARNING)
        res = {'code': -1, 'message': '网络错误: %s' % type(e).__name__}
    return res


def _get_url(url: str) -> dict:
    """fetch_url 的实际 GET 实现（无缓存）。"""
    xbmc.log('url_get: ' + url, xbmc.LOGDEBUG)
    headers = {}
    cookie = _resolve_cookie()
    if cookie:
        headers['Cookie'] = cookie
    try:
        return _session.get(
            url, headers=headers,
            timeout=(_TIMEOUT_CONNECT, _TIMEOUT_READ),
        ).json()
    except Exception as e:
        xbmc.log(
            '[api.http] fetch_url error: %s: %s url=%s' % (
                type(e).__name__, str(e), url,
            ),
            xbmc.LOGWARNING,
        )
        return {'code': -1, 'message': '网络错误: %s' % type(e).__name__}


_cached_url = plugin.cached(TTL=1)(_get_url)


def fetch_url(url: str, *, raw: bool = False) -> dict:
    """GET 任意 URL。`raw=True` 跳过 1 分钟内存缓存（CDN 临时签名等场景）。

    返回 `.json()` 解析后的 dict（错误时返回 `{'code': -1, ...}`）。
    非 JSON 响应（m3u8 / 字幕 XML 等）会抛 JSONDecodeError，转成错误 dict。
    对非 JSON 响应，请用 `fetch_url_text`。
    """
    if raw or getSetting('network_request_cache') != 'true':
        return _get_url(url)
    return _cached_url(url)


def fetch_url_text(url: str) -> str:
    """GET 任意 URL，返回纯文本（非 `.json()` 解析）。

    用于 m3u8 文本、ASS/XML 字幕、m3u8 manifest 等非 JSON 响应。
    带 cookie headers（CDN 可能要 cookie 校验）。
    失败抛异常（让调用方决定如何处理）。
    """
    xbmc.log('url_get_text: ' + url, xbmc.LOGDEBUG)
    headers = {}
    cookie = _resolve_cookie()
    if cookie:
        headers['Cookie'] = cookie
    resp = _session.get(
        url, headers=headers,
        timeout=(_TIMEOUT_CONNECT, _TIMEOUT_READ),
    )
    resp.raise_for_status()
    return resp.text


def build_api_url(path: str, data: dict = None) -> str:
    url = f'https://api.bilibili.com{path}'
    if data:
        url += '?' + urlencode(data)
    return url


def _get_api(path: str, data=None) -> dict:
    return _get_url(build_api_url(path, data))


_cached_api = plugin.cached(TTL=1)(_get_api)


def get_api_data(path: str, data: dict = None, *, raw: bool = False) -> dict:
    """B 站 api.bilibili.com 接口入口。`raw=True` 跳过 1 分钟缓存。"""
    if raw or getSetting('network_request_cache') != 'true':
        return _get_api(path, data)
    return _cached_api(path, data)
