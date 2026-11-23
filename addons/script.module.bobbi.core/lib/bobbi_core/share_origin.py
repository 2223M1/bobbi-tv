"""Single-hop byte reader for an already validated 115 grant.

Range identity, accepted offsets, renewal, peer lifetime and account authority
belong to share_stream. This layer has no redirect, cookie jar, retry or pool.
"""
from contextlib import closing, contextmanager
from functools import lru_cache
from http.client import HTTPConnection, HTTPSConnection, HTTPResponse
import io
import select
import ssl
import time
from urllib.parse import quote, urlsplit


@lru_cache(maxsize=1)
def tls_context():
    import certifi
    # Same trusted roots as the existing requests transport. Certificates and
    # hostnames are verified. Only public trust configuration is shared.
    context = ssl.create_default_context(cafile=certifi.where())
    context.set_alpn_protocols(['http/1.1'])
    return context


class ReadyReader(io.RawIOBase):
    """Drain immediately readable transport records, never wait to fill a block.

    BufferedReader/HTTPResponse still own *all* HTTP framing, including bytes
    read ahead with the headers. Socket ownership stays with the one request.
    """
    def __init__(self, sock, timeout, clock=time.monotonic, cancelled=None):
        self.sock, self.timeout, self.clock = sock, timeout, clock
        self.cancelled = cancelled
        self.error = None

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.error is not None:
            raise self.error
        now = self.clock()
        deadline, handoff, used = now + self.timeout, None, 0
        with memoryview(buffer) as target:
            while used < len(target):
                try:
                    count = self.sock.recv_into(target[used:])
                except (BlockingIOError, ssl.SSLWantReadError):
                    writing = False
                except ssl.SSLWantWriteError:
                    writing = True
                except OSError as exc:
                    if not used:
                        raise
                    self.error = exc  # Publish the exact valid prefix first.
                    break
                else:
                    if not count:
                        break
                    used += count
                    now = self.clock()
                    if handoff is None:
                        handoff = now + .001
                    elif now >= handoff:
                        break
                    continue
                if used:
                    break
                if self.cancelled is not None and self.cancelled():
                    raise OSError('SHARE_STOPPED')
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError('SHARE_READ_UNAVAILABLE')
                reads, writes, _ = select.select([] if writing else [self.sock],
                    [self.sock] if writing else [], [], min(.2, remaining) if self.cancelled else remaining)
                if not reads and not writes:
                    if self.cancelled is not None:
                        continue  # Same original deadline; never spin on a quiet peer.
                    raise TimeoutError('SHARE_READ_UNAVAILABLE')
        return used


class _InputSocket:
    def __init__(self, sock, timeout, cancelled):
        self.sock, self.timeout, self.cancelled = sock, timeout, cancelled

    def makefile(self, mode):
        if mode != 'rb':
            raise ValueError('SHARE_TRANSPORT_INVALID')
        return io.BufferedReader(ReadyReader(self.sock, self.timeout, cancelled=self.cancelled))


class _Body:
    def __init__(self, response):
        self.status_code, self.headers = response.status, response.headers
        self._response = response

    def iter_content(self, size):
        # One available prefix per read, not a blocking read(size). A trickle
        # still returns to the owner's cancellation and delivery-window gates.
        while True:
            chunk = self._response.read1(size)
            if not chunk:
                return
            yield chunk


@contextmanager
def direct_socket(parts, target, headers, timeout):
    connect_timeout, body_timeout = timeout
    if parts.scheme == 'https':
        connection = HTTPSConnection(parts.hostname, parts.port, timeout=connect_timeout, context=tls_context())
    else:
        connection = HTTPConnection(parts.hostname, parts.port, timeout=connect_timeout)
    with closing(connection):
        connection.connect()
        connection.sock.settimeout(body_timeout)
        connection.request('GET', target, headers=headers)
        # The sole HTTPResponse owns framing, including header read-ahead.
        # getresponse() would detach the requested Connection: close socket.
        yield connection.sock


class RangeOrigin:
    def __init__(self, wire=direct_socket):
        self.wire = wire
        self.cancelled = None

    @contextmanager
    def get(self, url, *, headers, stream, allow_redirects, timeout):
        parts = urlsplit(url)
        if (not stream or allow_redirects or not parts.hostname or parts.scheme not in ('http','https')
                or parts.username is not None or parts.password is not None or parts.fragment
                or set(headers) != {'User-Agent', 'Range', 'Accept-Encoding', 'Connection'}
                or headers['Accept-Encoding'] != 'identity' or headers['Connection'] != 'close'):
            raise ValueError('SHARE_TRANSPORT_INVALID')
        target = parts.path or '/'
        if parts.query:
            target += '?' + parts.query
        # Preserve escapes and order in signed queries; only encode raw Unicode.
        target = quote(target, safe="/%?:@!$&'()*+,;=-._~[]")
        with self.wire(parts, target, headers, timeout) as sock:
            sock.setblocking(False)
            with HTTPResponse(_InputSocket(sock, timeout[1], self.cancelled), method='GET') as response:
                response.begin()
                for name in ('Content-Length', 'Content-Range', 'Content-Encoding', 'Transfer-Encoding'):
                    if len(response.headers.get_all(name, ())) > 1:
                        raise ValueError('SHARE_RANGE_IDENTITY')
                if 'Transfer-Encoding' in response.headers and 'Content-Length' in response.headers:
                    raise ValueError('SHARE_RANGE_IDENTITY')
                yield _Body(response)
