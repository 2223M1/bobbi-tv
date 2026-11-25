"""Finite media reads over the same validated connection policy as source JSON."""
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPSConnection, HTTPException
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlsplit

from bobbi_core.bounded_http import (
    AttemptCancelled,
    AttemptHandle,
    bind_connection,
    header_phase,
    open_connection,
)
from bobbi_core.library_contract import LibraryError
from bobbi_core.source_endpoint import endpoint

_STD_HTTP = HTTPConnection
_STD_HTTPS = HTTPSConnection


# Only these fixed categories may cross the device-local control socket.
MESSAGES = {
    'POINTER_INVALID': 'STRM 必须是单行 UTF-8 HTTP(S) 媒体地址，且不超过 16 KB。',
    'POINTER_PROPERTY_UNSUPPORTED': '这个 STRM 依赖未支持的 Kodi 属性。',
    'MEDIA_NOT_FINITE': '不支持将直播或播放列表作为有限原片播放。',
    'MEDIA_TIMEOUT': '读取媒体超时，请检查连接后重试。',
    'MEDIA_UNAVAILABLE': '原始媒体暂时不可用。',
    'MEDIA_AUTH': '原片授权已过期或没有读取权限，请重新选择。',
    'MEDIA_REDIRECT': '媒体服务器要求重定向，请提供最终的原片地址。',
    'MEDIA_RANGE_UNSUPPORTED': '此服务器不支持准确的分段读取，无法按原片播放。',
    'MEDIA_RANGE_INVALID': '服务器返回的范围、长度或实际字节不匹配。',
    'MEDIA_TYPE_UNSUPPORTED': '服务器返回的不是支持的媒体类型。',
    'MEDIA_IDENTITY_UNVERIFIED': '服务器未提供可核对文件版本的强 ETag，无法安全定位原片。',
    'SOURCE_STREAM_INVALID': '无法识别这项媒体选择。',

    'T4_AUTH': '站点拒绝了授权，请检查订阅是否过期。',
    'T4_URL': '地址不受支持。远程请用 HTTPS；家庭网络可用局域网 IP 的 HTTP 地址。',
    'T4_DUPLICATE': '配置中有重复站点标识，未保存。',
    'T4_NO_SITES': '没有可用的 type 4 站点。传统 Spider 需要服务端 T4 接口。',
    'T4_CONFIG': '这不是包含 sites 的 T4 配置；不支持递归订阅。',
    'T4_REDIRECT': '站点返回了重定向，请直接配置最终地址。',
    'T4_LIMIT': '站点内容超过限制，未继续读取。',
    'T4_TIMEOUT': '站点超时，请稍后再试。',
    'T4_NETWORK': '无法读取站点，请检查连接和权限。',
    'T4_LINES': '线路与分集无法一一对应，未选择其他版本。',
    'T4_PLAY_UNSUPPORTED': '仅支持无需解析的有限 HTTP(S) 原片；不支持网页解析、分离音视频或直播。',
    'T4_MEDIA_ORIGIN': '此媒体不在已验证的站点域名内，暂不能安全播放。',
    'T4_HEADERS': '此片源要求未支持的媒体请求头。',
    'T4_CHANGED': '站点、线路或分集已变化，请重新选择。',
    'T4_TOKEN_EXPIRED': '选片令牌已过期或来源已更新，请返回上一级重新打开目录。',
    'SOURCE_HTTP_URL': '原片地址不在允许的网络范围内。',
    'SOURCE_STREAM_CHANGED': '来源或文件已经变化，请返回重新选片。',
}


def connection(
    url,
    remaining,
    *,
    invalid='SOURCE_HTTP_URL',
    unavailable='MEDIA_UNAVAILABLE',
    attempt=None,
    ssl_context=None,
    connect_cap=None,
):
    """Both JSON and media connect to the vetted address, preserving TLS SNI."""
    u = urlsplit(endpoint(url, invalid))
    if attempt is None:
        def _check():
            if remaining() <= 0:
                raise TimeoutError('HTTP deadline exceeded')
        attempt = AttemptHandle(check=_check, read_window=remaining())

    def validate_address(raw_addr):
        ip = ipaddress.ip_address(raw_addr.split('%')[0])
        ip = getattr(ip, 'ipv4_mapped', None) or ip
        if ip.is_unspecified or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise LibraryError(invalid)
        if u.scheme == 'http' and not ip.is_private:
            raise LibraryError('T4_URL')

    cls = HTTPSConnection if u.scheme == 'https' else HTTPConnection
    std_cls = _STD_HTTPS if u.scheme == 'https' else _STD_HTTP
    if cls is not std_cls:
        target = (u.path or '/') + ('?' + u.query if u.query else '')
        conn = cls(u.hostname, port=u.port, timeout=remaining())
        bind_connection(conn, attempt)
        return conn, target

    conn, target = open_connection(
        url,
        attempt,
        validate_address=validate_address,
        ssl_context=ssl_context,
        connect_cap=connect_cap,
    )
    orig_connect = conn.connect

    def connect_mapped():
        try:
            orig_connect()
        except LibraryError:
            raise
        except (AttemptCancelled, TimeoutError, socket.timeout):
            raise
        except OSError:
            raise LibraryError(unavailable) from None

    conn.connect = connect_mapped
    return conn, target


_DEFAULT_CONNECTION = connection


class Response:
    def __init__(self, reply):
        self.headers, self.status_code, self.reply = reply.headers, reply.status, reply
        for key in ('Content-Length', 'Content-Range', 'Content-Type', 'Content-Encoding', 'ETag'):
            if len(self.headers.get_all(key, [])) > 1:
                raise LibraryError('MEDIA_RANGE_INVALID')

    def iter_content(self, size):
        while True:
            chunk = self.reply.read1(size)
            if not chunk:
                return
            yield chunk


def _origin_key(url: str) -> tuple[str, str | None, int]:
    u = urlsplit(url)
    return u.scheme.lower(), (u.hostname or '').lower(), u.port or (443 if u.scheme.lower() == 'https' else 80)


def _strip_redirect_headers(headers: dict, prev_url: str, next_url: str) -> dict:
    if _origin_key(prev_url) == _origin_key(next_url):
        return dict(headers)
    stripped = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in ('authorization', 'cookie', 'referer', 'x-emby-token', 'x-plex-token'):
            continue
        stripped[k] = v
    return stripped


class Session:
    def __init__(self, *, ssl_context=None, max_redirects: int = 0, origin_policy=None):
        self.cancelled = None
        self.ssl_context = ssl_context
        self.max_redirects = max_redirects
        self.origin_policy = origin_policy

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass  # Connections belong to individual bounded responses, never pooled.

    @contextmanager
    def get(
        self,
        url,
        *,
        headers,
        stream,
        allow_redirects,
        timeout,
        deadline=None,
        cancelled=None,
        max_redirects=None,
        origin_policy=None,
    ):
        if not stream or allow_redirects:
            raise LibraryError('MEDIA_RANGE_INVALID')
        allowed_hops = self.max_redirects if max_redirects is None else int(max_redirects)
        connect_cap, read_window = timeout if isinstance(timeout, tuple) else (timeout, timeout)
        active_cancel = cancelled or self.cancelled
        active_origin_policy = origin_policy if origin_policy is not None else self.origin_policy
        overall_deadline = deadline if deadline is not None else (time.monotonic() + connect_cap + read_window)
        cur_url = url
        cur_headers = dict(headers)
        visited = {cur_url}

        for hop in range(allowed_hops + 1):
            endpoint(cur_url, 'SOURCE_HTTP_URL')
            if active_origin_policy is not None:
                active_origin_policy(cur_url)
            hop_conn = None
            try:
                with AttemptHandle(
                    deadline=overall_deadline,
                    cancelled=active_cancel,
                    read_window=read_window if deadline is None else None,
                ) as attempt:
                    if connection is _DEFAULT_CONNECTION:
                        hop_conn, target = connection(
                            cur_url,
                            lambda: attempt.remaining(connect_cap),
                            attempt=attempt,
                            ssl_context=self.ssl_context,
                            connect_cap=connect_cap,
                        )
                    else:
                        hop_conn, target = connection(cur_url, lambda: attempt.remaining(connect_cap))
                        bind_connection(hop_conn, attempt)
                    hop_conn.request('GET', target, headers=cur_headers)
                    with header_phase(attempt, read_window if deadline is None else None):
                        reply = hop_conn.getresponse()
                    if reply.status in (301, 302, 303, 307, 308) and allowed_hops > 0:
                        loc = reply.getheader('Location', '')
                        reply.close()
                        hop_conn.close()
                        hop_conn = None
                        if hop >= allowed_hops or not loc or any(ord(c) < 32 or ord(c) == 127 for c in loc):
                            raise LibraryError('MEDIA_REDIRECT')
                        next_url = urljoin(cur_url, loc.strip())
                        if next_url in visited:
                            raise LibraryError('MEDIA_REDIRECT')
                        prev_scheme = urlsplit(cur_url).scheme.lower()
                        next_scheme = urlsplit(next_url).scheme.lower()
                        if prev_scheme == 'https' and next_scheme != 'https':
                            raise LibraryError('MEDIA_REDIRECT')
                        endpoint(next_url, 'SOURCE_HTTP_URL')
                        cur_headers = _strip_redirect_headers(cur_headers, cur_url, next_url)
                        cur_url = next_url
                        visited.add(cur_url)
                        continue
                    with reply:
                        resp = Response(reply)
                        resp.final_url = cur_url
                        yield resp
                        attempt.finish()
                        return
            except LibraryError:
                raise
            except (AttemptCancelled, TimeoutError, socket.timeout):
                raise LibraryError('MEDIA_TIMEOUT') from None
            except (HTTPException, OSError, UnicodeError):
                raise LibraryError('MEDIA_UNAVAILABLE') from None
            finally:
                if hop_conn is not None:
                    hop_conn.close()
        raise LibraryError('MEDIA_REDIRECT')


def evidence(response, *, require_etag=True):
    status = response.status_code
    if status in (401, 403):
        raise LibraryError('MEDIA_AUTH')
    if 300 <= status < 400:
        raise LibraryError('MEDIA_REDIRECT')
    if status in (200, 416):
        raise LibraryError('MEDIA_RANGE_UNSUPPORTED')
    if status != 206:
        raise LibraryError('MEDIA_UNAVAILABLE')
    media = response.headers.get('Content-Type', '').partition(';')[0].strip().lower()
    if not (media.startswith(('audio/', 'video/')) or media in (
            'application/octet-stream', 'application/x-iso9660-image', 'application/x-matroska')):
        raise LibraryError('MEDIA_TYPE_UNSUPPORTED')
    if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
        raise LibraryError('MEDIA_RANGE_INVALID')
    tag = response.headers.get('ETag', '')
    if require_etag and not re.fullmatch(r'"[!#-~]{1,128}"', tag):
        raise LibraryError('MEDIA_IDENTITY_UNVERIFIED')
    return tag


def probe_evidence(reply, *, require_etag=True):
    tag = evidence(reply, require_etag=require_etag)
    match = re.fullmatch(r'bytes 0-0/([1-9][0-9]{0,18})', reply.headers.get('Content-Range', ''))
    if not match or int(match[1]) >= 2**63 or reply.headers.get('Content-Length', '1') != '1':
        raise LibraryError('MEDIA_RANGE_INVALID')
    chunks = iter(reply.iter_content(2))
    if len(next(chunks, b'')) != 1 or next(chunks, b''):
        raise LibraryError('MEDIA_RANGE_INVALID')
    return int(match[1]), tag


def probe(url, headers, session_factory=Session, *, deadline=None, cancelled=None):
    probe_deadline = deadline if deadline is not None else (time.monotonic() + 7.0)
    req_headers = dict(headers, Range='bytes=0-0', **{'Accept-Encoding': 'identity', 'Connection': 'close'})
    with session_factory() as session:
        kwargs = dict(headers=req_headers, stream=True, allow_redirects=False, timeout=(3, 4))
        if isinstance(session, Session):
            kwargs.update(deadline=probe_deadline, cancelled=cancelled)
        with session.get(url, **kwargs) as reply:
            return probe_evidence(reply)


def probe_stream(
    url,
    headers,
    session_factory=Session,
    *,
    max_redirects=3,
    deadline=None,
    cancelled=None,
    origin_policy=None,
):
    """Probe finite Range media with controlled <=3-hop redirect and strong_etag vs weak_session classification."""
    probe_deadline = deadline if deadline is not None else (time.monotonic() + 9.0)
    req_headers = dict(headers, Range='bytes=0-0', **{'Accept-Encoding': 'identity', 'Connection': 'close'})
    with session_factory() as session:
        kwargs = dict(headers=req_headers, stream=True, allow_redirects=False, timeout=(3, 5))
        if isinstance(session, Session):
            kwargs.update(
                deadline=probe_deadline,
                cancelled=cancelled,
                max_redirects=max_redirects,
                origin_policy=origin_policy,
            )
        elif origin_policy is not None:
            origin_policy(url)
        with session.get(url, **kwargs) as reply:
            size, raw_tag = probe_evidence(reply, require_etag=False)
            mime = reply.headers.get('Content-Type', '').partition(';')[0].strip().lower()
            strong = bool(raw_tag and re.fullmatch(r'"[!#-~]{1,128}"', raw_tag))
            return {
                'size': size,
                'etag': raw_tag if strong else '',
                'mime': mime,
                'identity_mode': 'strong_etag' if strong else 'weak_session',
                'final_url': getattr(reply, 'final_url', url),
            }
