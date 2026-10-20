# -*- coding: utf-8 -*-
"""TMDB endpoint probe, cache, and failover."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

from lib import settings, vfs

BUILTIN_ENDPOINTS: List[Dict[str, str]] = [
    {'scheme': 'https', 'host': 'api.tmdb.org', 'host_header': 'api.tmdb.org'},
    {'scheme': 'https', 'host': 'api.themoviedb.org', 'host_header': 'api.themoviedb.org'},
]

CACHE_FILENAME = 'endpoint_cache.json'
CACHE_TTL_SECONDS = 24 * 60 * 60
PROBE_TIMEOUT = 5

_IP_RE = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


class Endpoint:
    __slots__ = ('scheme', 'host', 'port', 'host_header')

    def __init__(
        self,
        scheme: str = 'https',
        host: str = '',
        port: str = '',
        host_header: str = '',
    ) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.host_header = host_header or host

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Endpoint':
        return cls(
            scheme=data.get('scheme', 'https'),
            host=data.get('host', ''),
            port=data.get('port', ''),
            host_header=data.get('host_header', data.get('host', '')),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            'scheme': self.scheme,
            'host': self.host,
            'port': self.port,
            'host_header': self.host_header,
        }

    @property
    def authority(self) -> str:
        if self.port:
            return f'{self.host}:{self.port}'
        return self.host

    def needs_host_header(self) -> bool:
        return bool(_IP_RE.match(self.host))


def _cache_path() -> str:
    return vfs.join(settings.get_profile_path(), CACHE_FILENAME)


def _read_cache() -> Optional[Endpoint]:
    path = _cache_path()
    if not vfs.isfile(path):
        return None
    try:
        content = vfs.read_text(path)
        if not content:
            return None
        data = json.loads(content)
        probed_at = int(data.get('probed_at', 0))
        if time.time() - probed_at > CACHE_TTL_SECONDS:
            return None
        host = data.get('host', '')
        if not host:
            return None
        return Endpoint.from_dict(data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_cache(endpoint: Endpoint) -> None:
    path = _cache_path()
    payload = endpoint.to_dict()
    payload['probed_at'] = int(time.time())
    vfs.write_text(path, json.dumps(payload, ensure_ascii=False))


def _clear_cache() -> None:
    vfs.remove(_cache_path())


def _default_endpoint() -> Endpoint:
    return Endpoint.from_dict(BUILTIN_ENDPOINTS[0])


def default_endpoint() -> Endpoint:
    return _default_endpoint()


def _ssl_context_for_verify(verify: bool) -> ssl.SSLContext:
    if verify:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _probe_one(endpoint: Endpoint, timeout: int = PROBE_TIMEOUT, verify: Optional[bool] = None) -> bool:
    if verify is None:
        verify = settings.get_bool_setting('ssl_verify', True)
    url = f'{endpoint.scheme}://{endpoint.authority}/3/configuration'
    api_key = settings.get_api_key()
    if api_key:
        url += '?' + urllib.parse.urlencode({'api_key': api_key})
    headers = {'User-Agent': f'{settings.get_addon_name()}/1.0'}
    if endpoint.needs_host_header():
        headers['Host'] = endpoint.host_header
    request = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=_ssl_context_for_verify(verify)
        ) as response:
            if response.getcode() != 200:
                return False
            body = response.read().decode('utf-8')
            json.loads(body)
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def _manual_endpoint() -> Endpoint:
    host = settings.get_setting('api_host')
    scheme = settings.get_setting('api_scheme', 'https')
    port = settings.get_setting('api_port')
    host_header = settings.get_setting('api_host_header') or host
    return Endpoint(scheme=scheme, host=host, port=port, host_header=host_header)


def probe_endpoints(exclude_host: str = '', timeout: int = PROBE_TIMEOUT) -> Optional[Endpoint]:
    verify = settings.get_bool_setting('ssl_verify', True)
    for item in BUILTIN_ENDPOINTS:
        endpoint = Endpoint.from_dict(item)
        if exclude_host and endpoint.host == exclude_host:
            continue
        if _probe_one(endpoint, timeout=timeout, verify=verify):
            return endpoint
    if verify:
        for item in BUILTIN_ENDPOINTS:
            endpoint = Endpoint.from_dict(item)
            if exclude_host and endpoint.host == exclude_host:
                continue
            if _probe_one(endpoint, timeout=timeout, verify=False):
                return endpoint
    return None


def _is_manual_mode() -> bool:
    return settings.get_setting('api_endpoint_mode', '0') == '1'


def resolve_endpoint(force_probe: bool = False) -> Optional[Endpoint]:
    if _is_manual_mode():
        endpoint = _manual_endpoint()
        return endpoint if endpoint.host else None

    if not force_probe:
        cached = _read_cache()
        if cached is not None:
            return cached

    endpoint = probe_endpoints()
    if endpoint is not None:
        _write_cache(endpoint)
        return endpoint
    return _default_endpoint()


def invalidate_and_failover(failed_host: str) -> Optional[Endpoint]:
    _clear_cache()
    if _is_manual_mode():
        manual = _manual_endpoint()
        return manual if manual.host else None
    endpoint = probe_endpoints(exclude_host=failed_host)
    if endpoint is not None:
        _write_cache(endpoint)
        return endpoint
    return None
