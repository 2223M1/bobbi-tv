"""Monotonic absolute-deadline HTTP transport with locked TCP->TLS attempt handoff.

Shared transport mechanism for platform HTTP clients (server_http, t4_http,
source_media_http, pan_http). Origin policy, headers, authentication, redirect
policy, and error codes remain owned by each caller.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
from functools import lru_cache
from http.client import HTTPConnection, HTTPSConnection
import io
import ipaddress
import select
import socket
import ssl
from threading import BoundedSemaphore, Event, Lock, Thread
import time
from urllib.parse import urlsplit
from urllib.request import HTTPHandler, HTTPSHandler

_DNS_SLOTS = BoundedSemaphore(8)
_CONNECT_PENDING = frozenset({
    errno.EINPROGRESS,
    errno.EWOULDBLOCK,
    errno.EALREADY,
    getattr(errno, 'WSAEWOULDBLOCK', 10035),
    getattr(errno, 'WSAEINPROGRESS', 10036),
    getattr(errno, 'WSAEALREADY', 10037),
})


@lru_cache(maxsize=1)
def default_tls_context() -> ssl.SSLContext:
    """Verified TLS context loading both system trust and bundled certifi roots."""
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    except ImportError:
        pass
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    try:
        context.set_alpn_protocols(['http/1.1'])
    except (NotImplementedError, ssl.SSLError):
        pass
    return context


class AttemptCancelled(OSError):
    """Raised when an AttemptHandle is cancelled before completion."""


class AttemptHandle:
    """Immutable per-attempt socket lifecycle and monotonic deadline owner.

    Socket transitions (unconnected -> TCP -> TLS) occur strictly under self._lock
    on this single AttemptHandle instance so an expired or cancelled attempt can
    never shut down or close a later attempt's socket.
    """

    def __init__(
        self,
        *,
        deadline: float | None = None,
        clock=time.monotonic,
        cancelled=None,
        check=None,
        read_window: float | None = None,
    ):
        self.deadline = deadline
        self.clock = clock
        self._cancelled = cancelled
        self._check = check
        self.read_window = read_window
        self.phase_deadline: float | None = None
        self._lock = Lock()
        self._sock = None
        self._phase = 'init'
        self._aborted = False
        self._abort_error: BaseException | None = None
        self._closed = False
        if deadline is not None and clock is not time.monotonic:
            budget = max(0.0, float(deadline - clock()))
            self._wall_deadline: float | None = time.monotonic() + budget + 1.0
        else:
            self._wall_deadline = None

    @property
    def phase(self) -> str:
        with self._lock:
            return self._phase

    def check(self) -> None:
        with self._lock:
            if self._abort_error is not None:
                raise self._abort_error
            if self._aborted:
                raise AttemptCancelled('HTTP attempt aborted')
        if self._check is not None:
            self._check()
        if self._cancelled is not None and self._cancelled():
            err = AttemptCancelled('HTTP attempt cancelled')
            self.abort(err)
            raise err
        if self.deadline is not None and self.clock() >= self.deadline:
            err = TimeoutError('HTTP deadline exceeded')
            self.abort(err)
            raise err
        if self._wall_deadline is not None and time.monotonic() >= self._wall_deadline:
            err = TimeoutError('HTTP wall deadline exceeded')
            self.abort(err)
            raise err

    def remaining(self, window: float | None = None) -> float:
        self.check()
        candidates: list[float] = []
        now = self.clock()
        if self.deadline is not None:
            candidates.append(self.deadline - now)
        if self.phase_deadline is not None:
            candidates.append(self.phase_deadline - now)
        if window is not None:
            candidates.append(window)
        if self._wall_deadline is not None:
            candidates.append(self._wall_deadline - time.monotonic())
        if not candidates:
            return 8.0
        rem = min(candidates)
        if rem <= 0:
            err = TimeoutError('HTTP deadline exceeded')
            self.abort(err)
            raise err
        return rem

    def attach_tcp(self, sock: socket.socket) -> socket.socket:
        with self._lock:
            if self._closed or self._aborted:
                _safe_shutdown_and_close(sock)
                raise self._abort_error or TimeoutError('HTTP attempt already closed')
            self._sock = sock
            self._phase = 'tcp'
            return sock

    def handoff_tls(
        self,
        tcp_sock: socket.socket,
        context: ssl.SSLContext,
        *,
        server_hostname: str,
        connect_cap: float | None = None,
    ) -> ssl.SSLSocket:
        if context.verify_mode == ssl.CERT_NONE:
            _safe_shutdown_and_close(tcp_sock)
            raise ssl.SSLError('Unverified TLS context is forbidden in bounded_http')
        with self._lock:
            if self._closed or self._aborted or self._sock is not tcp_sock:
                _safe_shutdown_and_close(tcp_sock)
                raise self._abort_error or TimeoutError('TCP socket invalidated before TLS handoff')
            tcp_sock.setblocking(False)
            tls_sock = context.wrap_socket(
                tcp_sock,
                server_hostname=server_hostname,
                do_handshake_on_connect=False,
            )
            self._sock = tls_sock
            self._phase = 'tls_handshake'
        handshake_deadline = (
            self.clock() + connect_cap if connect_cap is not None else None
        )
        try:
            tls_sock.setblocking(False)
            while True:
                cap = None if handshake_deadline is None else (handshake_deadline - self.clock())
                rem = self.remaining(cap)
                try:
                    tls_sock.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    rlist, wlist = [tls_sock], []
                except ssl.SSLWantWriteError:
                    rlist, wlist = [], [tls_sock]
                select.select(rlist, wlist, [tls_sock], min(0.02, rem))
            self.check()
            with self._lock:
                if self._closed or self._aborted:
                    raise self._abort_error or TimeoutError('TLS handoff aborted')
                self._phase = 'tls_ready'
            return tls_sock
        except BaseException:
            with self._lock:
                if self._sock is tls_sock:
                    self._sock = None
                    self._phase = 'failed'
            _safe_shutdown_and_close(tls_sock)
            raise

    def abort(self, error: BaseException | None = None) -> None:
        with self._lock:
            if not self._aborted:
                self._aborted = True
                self._abort_error = error
            sock = self._sock
        if sock is not None:
            _safe_shutdown(sock)

    def finish(self) -> None:
        """Verify budget and cancellation one final time before committing output."""
        self.check()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._sock = None

    def __enter__(self) -> AttemptHandle:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False


def _safe_shutdown(sock) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _safe_shutdown_and_close(sock) -> None:
    _safe_shutdown(sock)
    try:
        sock.close()
    except OSError:
        pass


def resolve_addresses(
    host: str,
    port: int | None,
    attempt: AttemptHandle,
    *,
    family: int = 0,
    socktype: int = socket.SOCK_STREAM,
    resolver=socket.getaddrinfo,
):
    """Resolve DNS within attempt's monotonic budget without unbounded caller stalls."""
    attempt.check()
    stripped = host.strip('[]') if isinstance(host, str) else ''
    if resolver is socket.getaddrinfo:
        try:
            ipaddress.ip_address(stripped)
        except ValueError:
            pass
        else:
            return socket.getaddrinfo(stripped, port, family, socktype, 0, socket.AI_NUMERICHOST)

    acquired = False
    while not acquired:
        rem = attempt.remaining()
        acquired = _DNS_SLOTS.acquire(timeout=min(0.02, rem))
    done = Event()
    box: list = [None, None]

    def work() -> None:
        try:
            box[0] = resolver(host, port, family, socktype)
        except BaseException as exc:
            box[1] = exc
        finally:
            _DNS_SLOTS.release()
            done.set()

    worker = Thread(target=work, name='bobbi-bounded-dns', daemon=True)
    worker.start()
    while not done.is_set():
        rem = attempt.remaining()
        done.wait(min(0.02, rem))
    attempt.check()
    if box[1] is not None:
        raise box[1]
    return box[0]


def connect_tcp(
    addresses,
    attempt: AttemptHandle,
    *,
    connect_cap: float | None = None,
    source_address=None,
    socket_options=(),
) -> socket.socket:
    """Non-blocking connect across resolved addresses within a shared connect budget."""
    attempt.check()
    if not addresses:
        raise OSError('No resolved socket addresses')
    now = attempt.clock()
    total_rem = attempt.remaining(connect_cap)
    overall_connect_end = now + total_rem
    last_err: BaseException = OSError('Connection failed')

    for idx, entry in enumerate(addresses):
        family, kind, proto, _, sockaddr = entry
        attempt.check()
        now = attempt.clock()
        left = overall_connect_end - now
        if left <= 0:
            raise TimeoutError('Connection budget exhausted')
        slice_end = now + left / max(1, len(addresses) - idx)
        sock = socket.socket(family, kind, proto)
        attempt.attach_tcp(sock)
        try:
            for opt in socket_options or ():
                sock.setsockopt(*opt)
            if source_address:
                sock.bind(source_address)
            sock.setblocking(False)
            code = sock.connect_ex(sockaddr)
            while code in _CONNECT_PENDING:
                # Check shared attempt deadline/cancellation stickily, while keeping
                # per-address slice expiry local to this candidate socket (SRC-07).
                global_rem = attempt.remaining()
                cur = attempt.clock()
                connect_left = overall_connect_end - cur
                if connect_left <= 0:
                    raise TimeoutError('Connection budget exhausted')
                slice_rem = slice_end - cur
                if slice_rem <= 0:
                    raise TimeoutError('Address connect slice timed out')
                wait_s = min(0.02, global_rem, connect_left, slice_rem)
                _, writable, exceptional = select.select([], [sock], [sock], wait_s)
                attempt.check()
                if writable or exceptional:
                    code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if code != 0:
                raise OSError(code, f'connect_ex failed ({code})')
            attempt.check()
            return sock
        except BaseException as exc:
            last_err = exc
            with attempt._lock:
                if attempt._sock is sock:
                    attempt._sock = None
                    attempt._phase = 'failed' if attempt._aborted else 'init'
            _safe_shutdown_and_close(sock)
            if isinstance(exc, AttemptCancelled) or attempt._aborted:
                raise
            if attempt.deadline is not None and attempt.clock() >= attempt.deadline:
                err = TimeoutError('HTTP deadline exceeded')
                attempt.abort(err)
                raise err from None
            if attempt.clock() >= overall_connect_end:
                raise TimeoutError('Connection budget exhausted') from None
    if isinstance(last_err, TimeoutError):
        raise last_err
    raise last_err


class BoundedSocketReader(io.RawIOBase):
    """Non-blocking reader enforcing AttemptHandle deadline on every header and body byte."""

    def __init__(self, proxy: _DeadlineSocketProxy, attempt: AttemptHandle):
        self._proxy = proxy
        self._attempt = attempt
        self._closed_flag = False
        self._deferred_error: BaseException | None = None

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if self._closed_flag:
            raise ValueError('I/O operation on closed file.')
        if self._deferred_error is not None:
            err, self._deferred_error = self._deferred_error, None
            raise err
        sock = self._proxy._raw
        call_deadline = (
            self._attempt.clock() + self._attempt.read_window
            if self._attempt.read_window is not None
            else None
        )
        handoff: float | None = None
        used = 0
        with memoryview(buffer) as target:
            while used < len(target):
                win = None if call_deadline is None else (call_deadline - self._attempt.clock())
                rem = self._attempt.remaining(win)
                try:
                    count = sock.recv_into(target[used:])
                except (BlockingIOError, ssl.SSLWantReadError):
                    writing = False
                except ssl.SSLWantWriteError:
                    writing = True
                except OSError as exc:
                    if not used:
                        raise
                    self._deferred_error = exc
                    break
                else:
                    if not count:
                        break
                    used += count
                    now = self._attempt.clock()
                    if handoff is None:
                        handoff = now + 0.001
                    elif now >= handoff:
                        break
                    continue
                if used:
                    break
                select.select(
                    [] if writing else [sock],
                    [sock] if writing else [],
                    [sock],
                    min(0.02, rem),
                )
        return used

    def close(self) -> None:
        if not self._closed_flag:
            self._closed_flag = True
            super().close()
            self._proxy._decref_socketios()


class _DeadlineSocketProxy:
    """Ref-counted socket wrapper preserving urllib Connection: close lifetime."""

    def __init__(self, raw_sock, attempt: AttemptHandle):
        self._raw = raw_sock
        self._attempt = attempt
        self._io_refs = 0
        self._closed = False
        self._raw.setblocking(False)

    def sendall(self, data, flags: int = 0) -> None:
        with memoryview(data) as view:
            sent = 0
            while sent < len(view):
                rem = self._attempt.remaining(self._attempt.read_window)
                try:
                    count = self._raw.send(view[sent:], flags)
                except (BlockingIOError, ssl.SSLWantWriteError):
                    select.select([], [self._raw], [self._raw], min(0.02, rem))
                    continue
                except ssl.SSLWantReadError:
                    select.select([self._raw], [], [self._raw], min(0.02, rem))
                    continue
                if count <= 0:
                    raise OSError('Socket closed during sendall')
                sent += count

    def makefile(self, mode: str = 'rb', buffering: int = -1, *args, **kwargs):
        if 'r' not in mode or 'b' not in mode:
            return self._raw.makefile(mode, buffering, *args, **kwargs)
        self._io_refs += 1
        raw_reader = BoundedSocketReader(self, self._attempt)
        buf_size = io.DEFAULT_BUFFER_SIZE if buffering <= 0 else buffering
        return io.BufferedReader(raw_reader, buffer_size=buf_size)

    def _decref_socketios(self) -> None:
        if self._io_refs > 0:
            self._io_refs -= 1
        if self._closed and self._io_refs <= 0:
            self._real_close()

    def _real_close(self) -> None:
        try:
            self._raw.close()
        except OSError:
            pass

    def close(self) -> None:
        self._closed = True
        if self._io_refs <= 0:
            self._real_close()

    def __getattr__(self, name: str):
        return getattr(self._raw, name)


def bind_connection(conn, attempt: AttemptHandle):
    """Bind any HTTPConnection/HTTPSConnection (including test-injected ones) to attempt."""
    if getattr(conn, '_bobbi_bound_attempt', None) is attempt:
        return conn
    try:
        conn._bobbi_bound_attempt = attempt
    except AttributeError:
        return conn
    sock = getattr(conn, 'sock', None)
    if sock is not None and not isinstance(sock, _DeadlineSocketProxy):
        attempt.attach_tcp(sock)
        conn.sock = _DeadlineSocketProxy(sock, attempt)
        return conn

    orig_connect = getattr(conn, 'connect', None)
    if orig_connect is None:
        return conn

    def guarded_connect():
        attempt.check()
        orig_connect()
        cur_sock = getattr(conn, 'sock', None)
        if cur_sock is not None and not isinstance(cur_sock, _DeadlineSocketProxy):
            attempt.attach_tcp(cur_sock)
            conn.sock = _DeadlineSocketProxy(cur_sock, attempt)

    conn.connect = guarded_connect
    return conn


class BoundedHTTPConnection(HTTPConnection):
    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        attempt: AttemptHandle,
        validate_address=None,
        connect_cap: float | None = None,
        resolver=socket.getaddrinfo,
        **kwargs,
    ):
        kwargs.pop('timeout', None)
        super().__init__(host, port=port, timeout=attempt.remaining(connect_cap), **kwargs)
        self._attempt = attempt
        self._validate_address = validate_address
        self._connect_cap = connect_cap
        self._resolver = resolver
        self._bobbi_bound_attempt = attempt

    def connect(self) -> None:
        infos = resolve_addresses(
            self.host,
            self.port,
            self._attempt,
            socktype=socket.SOCK_STREAM,
            resolver=self._resolver,
        )
        vetted = []
        for entry in infos:
            if self._validate_address is not None:
                self._validate_address(entry[4][0])
            vetted.append(entry)
        raw = connect_tcp(
            vetted,
            self._attempt,
            connect_cap=self._connect_cap,
            source_address=self.source_address,
        )
        self.sock = _DeadlineSocketProxy(raw, self._attempt)


class BoundedHTTPSConnection(HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        attempt: AttemptHandle,
        ssl_context: ssl.SSLContext | None = None,
        validate_address=None,
        connect_cap: float | None = None,
        resolver=socket.getaddrinfo,
        **kwargs,
    ):
        kwargs.pop('timeout', None)
        kwargs.pop('context', None)
        ctx = ssl_context or default_tls_context()
        super().__init__(host, port=port, timeout=attempt.remaining(connect_cap), context=ctx, **kwargs)
        self._attempt = attempt
        self._tls_context = ctx
        self._validate_address = validate_address
        self._connect_cap = connect_cap
        self._resolver = resolver
        self._bobbi_bound_attempt = attempt

    def connect(self) -> None:
        infos = resolve_addresses(
            self.host,
            self.port,
            self._attempt,
            socktype=socket.SOCK_STREAM,
            resolver=self._resolver,
        )
        vetted = []
        for entry in infos:
            if self._validate_address is not None:
                self._validate_address(entry[4][0])
            vetted.append(entry)
        tcp_sock = connect_tcp(
            vetted,
            self._attempt,
            connect_cap=self._connect_cap,
            source_address=self.source_address,
        )
        tls_sock = self._attempt.handoff_tls(
            tcp_sock,
            self._tls_context,
            server_hostname=self.host,
            connect_cap=self._connect_cap,
        )
        self.sock = _DeadlineSocketProxy(tls_sock, self._attempt)


def open_connection(
    url: str,
    attempt: AttemptHandle,
    *,
    validate_address=None,
    ssl_context: ssl.SSLContext | None = None,
    connect_cap: float | None = None,
    resolver=socket.getaddrinfo,
):
    """Construct a BoundedHTTP(S)Connection and request target for a validated URL."""
    u = urlsplit(url)
    if u.scheme == 'https':
        conn = BoundedHTTPSConnection(
            u.hostname,
            port=u.port,
            attempt=attempt,
            ssl_context=ssl_context,
            validate_address=validate_address,
            connect_cap=connect_cap,
            resolver=resolver,
        )
    else:
        conn = BoundedHTTPConnection(
            u.hostname,
            port=u.port,
            attempt=attempt,
            validate_address=validate_address,
            connect_cap=connect_cap,
            resolver=resolver,
        )
    target = (u.path or '/') + ('?' + u.query if u.query else '')
    return conn, target


class BoundedHTTPHandler(HTTPHandler):
    """urllib HTTPHandler enforcing AttemptHandle deadlines on headers and bodies."""

    def __init__(self, attempt_getter, *, resolver=socket.getaddrinfo):
        super().__init__()
        self._attempt_getter = attempt_getter
        self._resolver = resolver

    def http_open(self, req):
        attempt = self._attempt_getter(req)
        return self.do_open(
            lambda host, **kw: BoundedHTTPConnection(
                host,
                attempt=attempt,
                connect_cap=req.timeout if isinstance(req.timeout, (int, float)) else None,
                resolver=self._resolver,
            ),
            req,
        )


class BoundedHTTPSHandler(HTTPSHandler):
    """urllib HTTPSHandler enforcing AttemptHandle deadlines and verified TLS handoff."""

    def __init__(self, attempt_getter, *, ssl_context: ssl.SSLContext | None = None, resolver=socket.getaddrinfo):
        ctx = ssl_context or default_tls_context()
        super().__init__(context=ctx)
        self._attempt_getter = attempt_getter
        self._ssl_context = ctx
        self._resolver = resolver

    def https_open(self, req):
        attempt = self._attempt_getter(req)
        return self.do_open(
            lambda host, **kw: BoundedHTTPSConnection(
                host,
                attempt=attempt,
                ssl_context=self._ssl_context,
                connect_cap=req.timeout if isinstance(req.timeout, (int, float)) else None,
                resolver=self._resolver,
            ),
            req,
        )


@contextmanager
def header_phase(attempt: AttemptHandle, timeout: float | None):
    """Bound response header reading when overall deadline is None (e.g. Range streams)."""
    prev = attempt.phase_deadline
    attempt.phase_deadline = None if timeout is None else (attempt.clock() + timeout)
    try:
        yield
    finally:
        attempt.phase_deadline = prev
