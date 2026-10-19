"""Private CLI for subtitle_io: stdlib only, no Kodi import or fork state."""
import json
import sys


def protected_command():
    request = sys.stdin.buffer.read(16385)
    if len(request) > 16384:
        raise ValueError('SUBTITLE_IO_REQUEST_INVALID')
    command = json.loads(request)
    # -I intentionally removes the script directory from sys.path. Load only
    # our installed sibling, then protect lifetime BEFORE HTTP/SSL imports.
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('subtitle_child_lifetime',
        str(Path(__file__).with_name('child_lifetime.py')))
    lifetime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lifetime)
    lifetime.protect(command.get('lifetime'))
    return command


def report_error(error):
    # No URL/token/server text or arbitrary exception message crosses IPC.
    reason = str(error) if isinstance(error, ValueError) else 'SUBTITLE_IO_' + type(error).__name__
    if (not reason.startswith(('SUBTITLE_IO_', 'ASSRT_HTTP_', 'TORRENT_SUBTITLE_', 'OPENSUBTITLES_'))
            or not reason.replace('_', '').isalnum() or len(reason) > 80):
        reason = 'SUBTITLE_IO_FAILED'
    sys.stdout.buffer.write(json.dumps({'error': reason}).encode() + b'\n')


if __name__ == '__main__':
    try:
        _COMMAND = protected_command()
    except Exception as error:
        report_error(error)
        sys.exit(0)


import base64
import ipaddress
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request


OPENSUBTITLES_DOWNLOAD_HOSTS = frozenset((
    'www.opensubtitles.com', 'dl.opensubtitles.com', 'dl.opensubtitles.org'))


def command_guard(command):
    if (command.get('_cancelled', lambda: False)() or
            time.monotonic() >= command.get('_deadline', float('inf'))):
        raise ValueError('SUBTITLE_IO_DEADLINE')


def read_body(response, command, limit):
    """Embedded Kodi has no killable CLI child: yield at each socket read."""
    if '_deadline' not in command:
        return response.read(limit + 1)
    pieces, size = [], 0
    while True:
        command_guard(command)
        part = response.read1(min(65536, limit + 1 - size))
        if not part:
            break
        pieces.append(part)
        size += len(part)
        if size > limit:
            raise ValueError('SUBTITLE_IO_SIZE')
    command_guard(command)
    return b''.join(pieces)


def opensubtitles_url(url, mode):
    """The same exact HTTPS origins apply to direct and trusted tunnel IO."""
    if not isinstance(url, str) or len(url) > 8192:
        raise ValueError('SUBTITLE_IO_ORIGIN')
    parts = urlsplit(url)
    allowed = ({'api.opensubtitles.com'} if mode == 'opensubtitles_api'
               else OPENSUBTITLES_DOWNLOAD_HOSTS)
    if (parts.scheme != 'https'
            or parts.hostname not in allowed or parts.port not in (None, 443)
            or parts.username or parts.password or parts.fragment
            or any(ord(char) < 32 or ord(char) == 127 for char in url)):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    if mode == 'opensubtitles_api' and parts.path not in ('/api/v1/subtitles', '/api/v1/download'):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    return parts


def opensubtitles_origin(url, mode, all_addresses=False):
    """Validate DNS once; optionally retain two distinct public endpoints."""
    parts = opensubtitles_url(url, mode)
    addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    candidates = []
    seen = set()
    for address in addresses:
        key = (address[0], address[1], address[2], address[4])
        if key not in seen:
            seen.add(key)
            candidates.append(address)
        if len(candidates) == 2:
            break
    return parts, candidates if all_addresses else candidates[0]


def opensubtitles_connect(parts, addresses):
    """Fallback only before any HTTP bytes; the supervisor bounds total time."""
    import http.client
    import ssl
    candidates = addresses[:2]
    context = ssl.create_default_context()
    for index, address in enumerate(candidates):
        connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=5)
        sock, connected = None, False
        try:
            family, socktype, proto, _, endpoint = address
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(3)
            sock.connect(endpoint)
            sock.settimeout(5)
            connection.sock = context.wrap_socket(sock, server_hostname=parts.hostname)
            sock = None  # The TLS connection now owns it.
            connection.sock.settimeout(5)
            connected = True
            return connection
        except OSError:
            if index == len(candidates) - 1:
                raise
        finally:
            if sock is not None:
                sock.close()
            if not connected:
                connection.close()
    raise ValueError('SUBTITLE_IO_ORIGIN')


def opensubtitles_connect_proxy(parts):
    """Use only the existing loopback tunnel; CONNECT never receives API headers.

    The trusted Squid owns upstream DNS. The TLS peer must still prove the
    allowlisted original hostname, and failure never falls back or retries.
    """
    import http.client
    import ssl
    tunnel = http.client.HTTPConnection('127.0.0.1', 17895, timeout=3)
    connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=5)
    connected = False
    try:
        tunnel.set_tunnel(parts.hostname, 443)
        tunnel.connect()
        tunnel.sock.settimeout(5)
        connection.sock = ssl.create_default_context().wrap_socket(
            tunnel.sock, server_hostname=parts.hostname)
        tunnel.sock = None  # TLS now owns the tunnel socket.
        connection.sock.settimeout(5)
        connected = True
        return connection
    finally:
        tunnel.close()
        if not connected:
            connection.close()


def opensubtitles_retry_after(value):
    """Bound a server-directed cooldown without exporting response text."""
    import math
    import time
    from email.utils import parsedate_to_datetime
    try:
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError()
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, AttributeError, OverflowError):
            seconds = 60
    return max(1, min(86400, int(math.ceil(seconds))))


def fetch_opensubtitles(command):
    """Only API search/quota-bearing download and a credential-free text body.

    A separately resolved hostname is never handed back to urllib: the socket
    connects to the validated address and TLS still verifies the original host.
    POST is never redirected or retried. The supervisor owns the total deadline.
    """
    from urllib.parse import parse_qsl
    url, mode, limit = command['url'], command['mode'], command['limit']
    trusted_proxy = command.get('trusted_proxy')
    if trusted_proxy is not None and (trusted_proxy != 'am6b-tmdb-fallback-v1'
            or mode not in ('opensubtitles_api', 'opensubtitles_download')):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    if type(limit) is not int or not 0 < limit <= 2 * 1024 * 1024:
        raise ValueError('SUBTITLE_IO_SIZE')
    method = command.get('method', 'GET')
    body = command.get('json_body')
    if command.get('auth') or method not in ('GET', 'POST'):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    headers = command.get('headers') or {}
    allowed_headers = ({'api-key', 'user-agent', 'accept'} if mode == 'opensubtitles_api'
                       else {'user-agent', 'accept'})
    if (not isinstance(headers, dict) or len(headers) > 3
            or any(not isinstance(key, str) or key.lower() not in allowed_headers
                   or not isinstance(value, str) or len(value) > 512
                   or any(ord(char) < 32 or ord(char) == 127 for char in value)
                   for key, value in headers.items())):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    if len({key.lower() for key in headers}) != len(headers):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    headers = dict(headers, **{'Accept-Encoding': 'identity'})
    if mode == 'opensubtitles_download' and (method != 'GET' or body is not None):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    raw_body = None
    if method == 'POST':
        if (mode != 'opensubtitles_api' or not isinstance(body, dict)
                or set(body) != {'file_id', 'sub_format'}
                or type(body['file_id']) is not int or not 0 < body['file_id'] < 2 ** 63
                or body['sub_format'] != 'srt'):
            raise ValueError('SUBTITLE_IO_REQUEST_INVALID')
        raw_body = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    elif body is not None:
        raise ValueError('SUBTITLE_IO_REQUEST_INVALID')
    for _ in range(3):
        command_guard(command)
        if trusted_proxy is not None:
            parts, addresses = opensubtitles_url(url, mode), None
        else:
            parts, addresses = opensubtitles_origin(url, mode, all_addresses=True)
        if mode == 'opensubtitles_api':
            if ((method == 'GET' and parts.path != '/api/v1/subtitles')
                    or (method == 'POST' and (parts.path != '/api/v1/download' or parts.query))):
                raise ValueError('SUBTITLE_IO_ORIGIN')
        connection = (opensubtitles_connect_proxy(parts) if trusted_proxy is not None
                      else opensubtitles_connect(parts, addresses))
        try:
            command_guard(command)
            target = parts.path + (('?' + parts.query) if parts.query else '')
            connection.request(method, target, body=raw_body, headers=headers)
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                next_url = urljoin(url, response.getheader('Location') or '')
                following = urlsplit(next_url)
                if (method != 'GET' or next_url == url or (mode == 'opensubtitles_api'
                        and (response.status != 301
                             or (parts.scheme, parts.netloc, parts.path)
                             != (following.scheme, following.netloc, following.path)
                             or sorted(parse_qsl(parts.query)) != sorted(parse_qsl(following.query))))):
                    raise ValueError('SUBTITLE_IO_ORIGIN')
                url = next_url
                continue
            if response.status == 429:
                raise ValueError('OPENSUBTITLES_RATE_LIMIT_RETRY_' +
                                 str(opensubtitles_retry_after(response.getheader('Retry-After'))))
            if response.status != 200:
                code = response.status if response.status in (400, 401, 403, 404, 406, 408, 410, 500, 502, 503, 504) else 'OTHER'
                raise ValueError('OPENSUBTITLES_HTTP_' + str(code))
            if (response.getheader('Content-Encoding') or 'identity').lower() != 'identity':
                raise ValueError('SUBTITLE_IO_ENCODING')
            declared = response.getheader('Content-Length')
            if declared is not None and (not declared.isdigit() or not 0 <= int(declared) <= limit):
                raise ValueError('SUBTITLE_IO_SIZE')
            raw = read_body(response, command, limit)
            if len(raw) > limit:
                raise ValueError('SUBTITLE_IO_SIZE')
            if declared is not None and len(raw) != int(declared):
                raise ValueError('SUBTITLE_IO_LENGTH')
            command_guard(command)
            return raw
        finally:
            connection.close()
    raise ValueError('SUBTITLE_IO_REDIRECT_LIMIT')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate(url, mode):
    parts = urlsplit(url)
    if parts.username or parts.password or not parts.hostname or parts.fragment:
        raise ValueError('SUBTITLE_IO_ORIGIN')
    if mode == 'assrt':
        if (parts.scheme != 'https' or not (parts.hostname == 'assrt.net'
                or parts.hostname.endswith('.assrt.net'))):
            raise ValueError('SUBTITLE_IO_ORIGIN')
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('SUBTITLE_IO_ORIGIN')
    elif mode == 'share_cdn':
        if (parts.scheme not in ('http', 'https') or parts.port not in (None, 80, 443)
                or not any(parts.hostname == root or parts.hostname.endswith('.' + root)
                           for root in ('115.com', '115cdn.com', '115cdn.net'))):
            raise ValueError('SUBTITLE_IO_ORIGIN')
    elif mode != 'torrent' or parts.scheme not in ('http', 'https'):
        raise ValueError('SUBTITLE_IO_ORIGIN')


def fetch(command):
    def guard():
        command_guard(command)
    guard()
    if command.get('trusted_proxy') is not None and command.get('mode') not in (
            'opensubtitles_api', 'opensubtitles_download'):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    if command.get('mode') in ('opensubtitles_api', 'opensubtitles_download'):
        return fetch_opensubtitles(command)
    url, mode, limit = command['url'], command['mode'], command['limit']
    if type(limit) is not int or not 0 < limit <= 8 * 1024 * 1024:
        raise ValueError('SUBTITLE_IO_SIZE')
    headers = dict(command['headers'], **{'Accept-Encoding': 'identity'})
    if mode == 'share_cdn' and (command['method'] != 'GET' or command.get('auth')
            or command.get('json_body') is not None or set(key.lower() for key in headers) - {'user-agent', 'accept-encoding'}):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    auth = command.get('auth')
    if auth:
        token = base64.b64encode((':'.join(auth)).encode()).decode('ascii')
        headers['Authorization'] = 'Basic ' + token
    data = command.get('json_body')
    if data is not None:
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for _ in range(4 if mode == 'assrt' else 1):
        guard()
        validate(url, mode)
        request = Request(url, data=data, headers=headers, method=command['method'])
        try:
            response = opener.open(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            if mode == 'assrt' and response.code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get('Location', ''))
                headers = {'Accept-Encoding': 'identity'}
                continue  # Credential never follows a redirect, even same host.
            if response.code not in ((200,) if mode == 'assrt' else (200, 206)):
                raise ValueError(('ASSRT_HTTP_' + str(response.code)) if mode == 'assrt' else 'TORRENT_SUBTITLE_HTTP')
            if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ValueError('SUBTITLE_IO_ENCODING')
            declared = response.headers.get('Content-Length')
            if declared is not None and (not declared.isdigit() or not 0 <= int(declared) <= limit):
                raise ValueError('SUBTITLE_IO_SIZE')
            raw = read_body(response, command, limit)
            if len(raw) > limit:
                raise ValueError('SUBTITLE_IO_SIZE')
            if declared is not None and len(raw) != int(declared):
                raise ValueError('SUBTITLE_IO_LENGTH')
            guard()
            return raw
    raise ValueError('SUBTITLE_IO_REDIRECT_LIMIT')


def main(command=None):
    try:
        raw = fetch(protected_command() if command is None else command)
        sys.stdout.buffer.write(json.dumps({'bytes': len(raw)}).encode() + b'\n' + raw)
    except Exception as error:
        report_error(error)


if __name__ == '__main__':
    main(_COMMAND)
