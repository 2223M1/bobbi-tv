"""TMDb-only direct HTTPS with bounded, TLS-preserving RFC8484 DNS fallback.

No global DNS/proxy mutation, image relay, borrowed application key or endpoint
discovery. Blocking platform DNS/connect remains subject to OS timeouts; this
is cooperative I/O, not a claim of forcibly interruptible libc getaddrinfo.
"""
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import struct
import time
from threading import Lock
from urllib.parse import urlsplit, urlencode

HOSTS = frozenset(('api.themoviedb.org', 'image.tmdb.org'))
RESOLVERS = (('dns.alidns.com', '223.5.5.5'), ('doh.pub', '1.12.12.12'))
MAX_BYTES = 8 * 1024 * 1024
_DNS_CACHE, _DNS_LOCK = {}, Lock()


class MetadataError(RuntimeError):
    def __init__(self, stage):
        known = {'CANCELLED', 'TIMEOUT', 'LENGTH', 'LIMIT', 'SHORT_READ', 'ORIGIN',
                 'DNS_REPLY', 'DNS_EMPTY', 'DNS', 'CONNECT', 'HEADERS', 'BODY',
                 'TLS', 'REDIRECT', 'PROXY_DISABLED', 'IMAGE_FORMAT', 'IMAGE_COOLDOWN',
                 'IMAGE_UNAVAILABLE', 'JSON', 'UNKNOWN'}
        self.stage = stage if stage in known or re.fullmatch(r'HTTP_[1-5][0-9]{2}', str(stage)) else 'UNKNOWN'
        super().__init__('METADATA_' + self.stage)


class HTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip=None, timeout=5):
        self.address = ip
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())

    def connect(self):
        raw = socket.create_connection((self.address or self.host, 443), self.timeout)
        try:
            # Verify the ORIGINAL DNS hostname, never the substituted address.
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _guard(deadline, cancelled):
    if cancelled():
        raise MetadataError('CANCELLED')
    if time.monotonic() >= deadline:
        raise MetadataError('TIMEOUT')


def receive(response, connection, deadline, cancelled, limit=MAX_BYTES):
    declared = response.getheader('Content-Length')
    if declared is not None and (not isinstance(declared, str) or not re.fullmatch(r'[0-9]{1,10}', declared)
                                 or int(declared) > limit):
        raise MetadataError('LENGTH')
    chunks, size = [], 0
    while True:
        _guard(deadline, cancelled)
        if connection.sock:
            connection.sock.settimeout(min(2, max(.05, deadline - time.monotonic())))
        chunk = response.read1(min(65536, limit + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise MetadataError('LIMIT')
    if declared is not None and size != int(declared):
        raise MetadataError('SHORT_READ')
    _guard(deadline, cancelled)
    return b''.join(chunks)


def dns_query(host, identifier):
    if host not in HOSTS:
        raise MetadataError('ORIGIN')
    question = b''.join(bytes([len(label)]) + label.encode('ascii') for label in host.split('.'))
    return struct.pack('!HHHHHH', identifier, 0x100, 1, 0, 0, 0) + question + b'\0\0\1\0\1'


def dns_answers(raw, question, with_ttl=False):
    if len(raw) < len(question) or len(raw) > 4096:
        raise MetadataError('DNS_REPLY')
    identifier, flags, qd, an, _, _ = struct.unpack('!HHHHHH', raw[:12])
    if (identifier != struct.unpack('!H', question[:2])[0] or flags & 0xF or
            not flags & 0x8000 or flags & 0x200 or qd != 1 or an > 64 or
            raw[12:len(question)] != question[12:]):
        raise MetadataError('DNS_REPLY')
    def name_end(offset):
        for _ in range(128):
            if offset >= len(raw):
                break
            length = raw[offset]
            if length == 0:
                return offset + 1
            if length & 0xC0 == 0xC0 and offset + 1 < len(raw):
                if ((length & 63) << 8 | raw[offset + 1]) >= len(raw):
                    break
                return offset + 2
            if length > 63:
                break
            offset += length + 1
        raise MetadataError('DNS_REPLY')
    offset, result, lifetimes = len(question), [], []
    for _ in range(an):
        offset = name_end(offset)
        if offset + 10 > len(raw):
            raise MetadataError('DNS_REPLY')
        kind, klass, ttl, length = struct.unpack('!HHIH', raw[offset:offset + 10])
        offset += 10
        end = offset + length
        if end > len(raw):
            raise MetadataError('DNS_REPLY')
        if kind == 1 and klass == 1 and length == 4:
            ip = ipaddress.ip_address(raw[offset:end])
            if ip.is_global:
                result.append(str(ip))
                lifetimes.append(ttl)
        offset = end
    if not result:
        raise MetadataError('DNS_EMPTY')
    result = list(dict.fromkeys(result))[:4]
    return (result, min(300, min(lifetimes))) if with_ttl else result


def resolve(host, deadline, cancelled, connect=HTTPS):
    question = dns_query(host, secrets.randbelow(65536))
    _guard(deadline, cancelled)
    with _DNS_LOCK:
        cached = _DNS_CACHE.get(host)
        if cached and cached[0] > time.monotonic():
            return list(cached[1])
    for resolver, bootstrap in RESOLVERS:
        _guard(deadline, cancelled)
        connection = connect(resolver, ip=bootstrap, timeout=min(2, deadline - time.monotonic()))
        try:
            connection.request('POST', '/dns-query', body=question,
                headers={'Content-Type': 'application/dns-message', 'Accept': 'application/dns-message'})
            response = connection.getresponse()
            if response.status != 200:
                continue
            addresses, ttl = dns_answers(receive(response, connection, deadline, cancelled, 4096), question, with_ttl=True)
            if ttl > 0:
                with _DNS_LOCK:
                    _DNS_CACHE[host] = (time.monotonic() + ttl, tuple(addresses))
            return addresses
        except (OSError, http.client.HTTPException, MetadataError):
            _guard(deadline, cancelled)
        finally:
            connection.close()
    raise MetadataError('DNS')


def fetch(url, deadline, cancelled=lambda: False, method='GET', body=None, headers=None,
          connect=HTTPS, resolver=resolve):
    try:
        parts = urlsplit(url)
        allowed = (isinstance(url, str) and parts.scheme == 'https' and parts.hostname in HOSTS and parts.port in (None, 443)
            and not parts.username and not parts.password and not parts.fragment and len(url) <= 8192
            and not any(ord(c) < 33 or ord(c) == 127 for c in url))
    except (TypeError, ValueError):
        allowed = False
    if not allowed:
        raise MetadataError('ORIGIN')
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query
    # Successful normal HTTPS does not pay a DoH query. TLS failures do not
    # trigger bypass; redirects are not followed to a relay or unknown origin.
    addresses, accelerated = [None], False
    last = 'CONNECT'
    while addresses:
        address = addresses.pop(0)
        _guard(deadline, cancelled)
        connection = connect(parts.hostname, ip=address, timeout=min(3, deadline - time.monotonic()))
        stage = 'CONNECT'
        try:
            connection.request(method, path, body=body, headers=dict(headers or {}, **{'Accept-Encoding': 'identity'}))
            stage = 'HEADERS'
            response = connection.getresponse()
            stage = 'BODY'
            raw = receive(response, connection, deadline, cancelled)
            if 300 <= response.status < 400:
                raise MetadataError('REDIRECT')
            return dict(status=response.status, headers=dict(response.getheaders()), body=raw,
                        route='doh-direct' if accelerated else 'system-direct')
        except ssl.SSLError:
            raise MetadataError('TLS') from None
        except MetadataError:
            raise
        except (socket.gaierror, OSError, http.client.HTTPException) as error:
            _guard(deadline, cancelled)
            last = 'DNS' if isinstance(error, socket.gaierror) else stage
            # Only idempotent GET can be retried after a possibly sent request.
            if method != 'GET':
                raise MetadataError(last) from None
            if not accelerated:
                addresses = resolver(parts.hostname, deadline, cancelled)[:2]
                accelerated = True
        finally:
            connection.close()
    if accelerated:
        with _DNS_LOCK:
            _DNS_CACHE.pop(parts.hostname, None)
    raise MetadataError(last)


def request(method, url, data=None, json=None, proxies=None, timeout=None):
    """Requests-compatible edge for bundled TMDb API; diagnostic messages are safe."""
    import requests
    headers, body = {}, data
    if json is not None:
        import json as codec
        body, headers['Content-Type'] = codec.dumps(json).encode(), 'application/json'
    elif isinstance(data, dict):
        body, headers['Content-Type'] = urlencode(data).encode(), 'application/x-www-form-urlencoded'
    try:
        if proxies:
            raise MetadataError('PROXY_DISABLED')
        result = fetch(url, time.monotonic() + 12, method=str(method).upper(), body=body, headers=headers)
    except MetadataError as error:
        wrapped = requests.ConnectionError(str(error))
        wrapped.metadata_stage = error.stage
        raise wrapped from None
    response = requests.Response()
    response.status_code, response._content = result['status'], result['body']
    response.headers.update(result['headers'])
    response.headers['X-Bobbi-Network-Route'] = result['route']
    response.encoding = 'utf-8'
    # Never retain the API-key-bearing URL on a Response or error message.
    response.url = 'https://' + urlsplit(url).hostname
    return response
