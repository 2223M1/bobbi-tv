"""Cooperative HTTPS I/O on the caller thread, with no surviving network worker.

The caller owns the absolute deadline and cancellation callback. Each socket
operation also has an idle limit. System getaddrinfo remains synchronous: check
before/after it, but do not pretend it can be interrupted on every CE resolver.
"""
import errno
from http.client import HTTPSConnection
import io
import select
import socket
import ssl
import time
from urllib.request import HTTPSHandler

POLL_SECONDS = 0.1
IDLE_SECONDS = 5


def _wait(sock, writing, active, deadline):
    while True:
        active()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Online connection idle')
        readable, writable, exceptional = select.select(
            [] if writing else [sock], [sock] if writing else [], [sock],
            min(POLL_SECONDS, remaining))
        active()
        if readable or writable or exceptional:
            return


def _io(sock, operation, writing, active):
    deadline = time.monotonic() + IDLE_SECONDS
    while True:
        active()
        try:
            result = operation()
            active()
            return result
        except ssl.SSLWantReadError:
            _wait(sock, False, active, deadline)
        except ssl.SSLWantWriteError:
            _wait(sock, True, active, deadline)
        except BlockingIOError:
            _wait(sock, writing, active, deadline)


def _connect(host, port, active):
    active()
    addresses = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    active()  # No late connection may start after an uncancellable DNS call.
    deadline = time.monotonic() + IDLE_SECONDS
    last_error = OSError('No online address')
    pending = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
               getattr(errno, 'WSAEWOULDBLOCK', 10035)}
    for family, kind, protocol, _, address in addresses:
        active()
        sock = socket.socket(family, kind, protocol)
        try:
            sock.setblocking(False)
            result = sock.connect_ex(address)
            if result in pending:
                _wait(sock, True, active, deadline)
                result = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if result:
                raise OSError(result, 'Online connection failed')
            active()
            return sock
        except BaseException as error:
            sock.close()
            if not isinstance(error, OSError):
                raise
            last_error = error
    raise last_error


class _Reader(io.RawIOBase):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        owner.references += 1

    def readable(self):
        return True

    def readinto(self, buffer):
        return _io(self.owner.raw, lambda: self.owner.raw.recv_into(buffer),
                   False, self.owner.active)

    def close(self):
        if not self.closed:
            try:
                super().close()
            finally:
                self.owner.release()


class _Socket:
    """Keep the response's file alive after urllib releases its connection.

    Mirrors socket.makefile ownership: the connection and response each hold
    one reference. No other request or watcher can close or reuse this socket.
    """
    def __init__(self, raw, active):
        self.raw, self.active = raw, active
        self.references = 1
        self.closed = False

    def makefile(self, mode):
        if mode != 'rb':
            raise ValueError('Online response must be binary')
        return io.BufferedReader(_Reader(self))

    def sendall(self, data):
        view = memoryview(data)
        while view:
            sent = _io(self.raw, lambda: self.raw.send(view), True, self.active)
            if not sent:
                raise ConnectionError('Online connection closed')
            view = view[sent:]

    def release(self):
        self.references -= 1
        if self.references == 0:
            self.raw.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.release()


class _Connection(HTTPSConnection):
    def __init__(self, host, *, active, **kwargs):
        super().__init__(host, **kwargs)
        self.active = active

    def connect(self):
        # ProxyHandler({}) disables proxies; never add a separate CONNECT path.
        if self._tunnel_host:
            raise ValueError('Online proxy unsupported')
        raw = _connect(self.host, self.port, self.active)
        try:
            raw = self._context.wrap_socket(raw, server_hostname=self.host,
                                            do_handshake_on_connect=False)
            _io(raw, raw.do_handshake, False, self.active)
            self.sock = _Socket(raw, self.active)
        except BaseException:
            raw.close()
            raise


class CancellableHTTPSHandler(HTTPSHandler):
    def __init__(self, active, context):
        super().__init__(context=context)
        self.active = active

    def https_open(self, request):
        def connection(host, **kwargs):
            return _Connection(host, active=self.active, **kwargs)
        return self.do_open(connection, request, context=self._context)
