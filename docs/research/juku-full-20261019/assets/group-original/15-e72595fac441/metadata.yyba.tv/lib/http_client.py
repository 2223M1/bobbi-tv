# -*- coding: utf-8 -*-
"""HTTP client using urllib with endpoint failover."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

import xbmc

from lib import settings
from lib.endpoint_probe import Endpoint, default_endpoint, invalidate_and_failover, resolve_endpoint
from lib.notify import warn_once

DEFAULT_TIMEOUT = 15
IMAGE_BASE = 'https://media.themoviedb.org/t/p'


def get_api_key() -> str:
    return settings.get_api_key()


def _ssl_context() -> ssl.SSLContext:
    verify = settings.get_bool_setting('ssl_verify', True)
    if verify:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_headers(endpoint: Endpoint) -> Dict[str, str]:
    headers = {'User-Agent': f'{settings.get_addon_name()}/1.0'}
    if endpoint.needs_host_header():
        headers['Host'] = endpoint.host_header
    return headers


def _error_kind(err: BaseException) -> str:
    if isinstance(err, urllib.error.HTTPError):
        return f'http_{err.code}'
    if isinstance(err, urllib.error.URLError):
        reason = str(getattr(err, 'reason', err)).lower()
        if 'timed out' in reason or 'timeout' in reason:
            return 'timeout'
        return 'url_error'
    return 'other'


def _log_request_error(endpoint_host: str, err: BaseException, phase: str = 'request') -> None:
    kind = _error_kind(err)
    name = settings.get_addon_name()
    if kind == 'http_401':
        _, source = settings.get_api_key_with_source()
        tail = settings.get_api_key_tail()
        xbmc.log(
            f'[{name}] {phase} failed ({endpoint_host}): HTTP 401 Unauthorized '
            f'(api_key source={source}, ...{tail})',
            xbmc.LOGERROR,
        )
        warn_once('api_key_invalid', '请检查 TMDB API Key 是否有效')
    elif kind == 'http_403':
        xbmc.log(f'[{name}] {phase} failed ({endpoint_host}): HTTP 403 Forbidden', xbmc.LOGERROR)
        warn_once('api_key_forbidden', 'TMDB API Key 被拒绝，请检查密钥权限')
    elif kind == 'timeout':
        xbmc.log(f'[{name}] {phase} failed ({endpoint_host}): timeout', xbmc.LOGWARNING)
    else:
        xbmc.log(f'[{name}] {phase} failed ({endpoint_host}): {err}', xbmc.LOGWARNING)


def _notify_no_endpoint() -> None:
    warn_once(
        'endpoint_unreachable',
        'TMDB 不可达，请切换手动模式并填写代理 IP 与 Host 头',
    )


def build_api_url(path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, str], Endpoint]:
    endpoint = resolve_endpoint()
    if endpoint is None:
        endpoint = default_endpoint()
    if not path.startswith('/'):
        path = '/' + path
    base = f'{endpoint.scheme}://{endpoint.authority}/3{path}'
    query = dict(params or {})
    api_key = get_api_key()
    if api_key and 'api_key' not in query:
        query['api_key'] = api_key
    if query:
        base += '?' + urllib.parse.urlencode(query)
    return base, _build_headers(endpoint), endpoint


def open_image_url(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = DEFAULT_TIMEOUT):
    req_url, img_headers = _image_request(url)
    merged = dict(img_headers)
    if headers:
        merged.update(headers)
    request = urllib.request.Request(req_url, headers=merged, method='GET')
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())


def _image_request(url: str) -> Tuple[str, Dict[str, str]]:
    headers = {'User-Agent': f'{settings.get_addon_name()}/1.0'}
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower()
    tmdb_image_hosts = ('image.tmdb.org', 'media.themoviedb.org')
    if host in tmdb_image_hosts and settings.get_setting('api_endpoint_mode', '0') == '2':
        proxy_host = settings.get_setting('api_host')
        if proxy_host:
            scheme = settings.get_setting('api_scheme', 'https') or 'https'
            port = settings.get_setting('api_port')
            authority = f'{proxy_host}:{port}' if port else proxy_host
            proxy_url = f'{scheme}://{authority}{parsed.path}'
            if parsed.query:
                proxy_url += '?' + parsed.query
            headers['Host'] = host
            return proxy_url, headers
    return url, headers


def open_url(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = DEFAULT_TIMEOUT):
    request = urllib.request.Request(
        url,
        headers=headers or {'User-Agent': f'{settings.get_addon_name()}/1.0'},
        method='GET',
    )
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())


def _request_once(url: str, headers: Dict[str, str], timeout: int) -> Optional[Dict[str, Any]]:
    with open_url(url, headers=headers, timeout=timeout) as response:
        status = response.getcode()
        if status and status >= 400:
            return None
        body = response.read().decode('utf-8')
        return json.loads(body)


def _build_request_url(path: str, params: Optional[Dict[str, Any]], endpoint: Endpoint) -> str:
    if not path.startswith('/'):
        path = '/' + path
    url = f'{endpoint.scheme}://{endpoint.authority}/3{path}'
    query = dict(params or {})
    api_key = get_api_key()
    if api_key and 'api_key' not in query:
        query['api_key'] = api_key
    if query:
        url += '?' + urllib.parse.urlencode(query)
    return url


def get_json(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict[str, Any]]:
    try:
        url, headers, endpoint = build_api_url(path, params)
    except urllib.error.URLError as err:
        xbmc.log(f'[{settings.get_addon_name()}] build_api_url failed: {err}', xbmc.LOGERROR)
        return None

    try:
        return _request_once(url, headers, timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as err:
        _log_request_error(endpoint.host, err)
        fallback = invalidate_and_failover(endpoint.host)
        if fallback is None:
            xbmc.log(
                f'[{settings.get_addon_name()}] no TMDB endpoint available after failover',
                xbmc.LOGERROR,
            )
            _notify_no_endpoint()
            return None
        xbmc.log(
            f'[{settings.get_addon_name()}] failover: {endpoint.host} -> {fallback.host}',
            xbmc.LOGINFO,
        )
        try:
            retry_url = _build_request_url(path, params, fallback)
            return _request_once(retry_url, _build_headers(fallback), timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as retry_err:
            _log_request_error(fallback.host, retry_err, phase='retry')
            xbmc.log(
                f'[{settings.get_addon_name()}] retry failed: no working TMDB endpoint',
                xbmc.LOGERROR,
            )
            _notify_no_endpoint()
            return None


def build_image_url(path: str, size: str = 'w500') -> str:
    if not path:
        return ''
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if not path.startswith('/'):
        path = '/' + path
    try:
        base = settings._cfg.image_base() or IMAGE_BASE
    except Exception:
        base = IMAGE_BASE
    return f'{base}/{size}{path}'
