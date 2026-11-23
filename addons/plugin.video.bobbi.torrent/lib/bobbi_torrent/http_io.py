"""Request-local socket cancellation, including slow headers and trickle bodies.

No global urllib3 patch or detached request thread. The calling thread owns
Requests and its response; a joined watchdog only shuts down this request's
socket. TLS verification, Requests parsing and the ordinary read caps remain.
"""
import errno
import select
import socket
import ssl
import time
from threading import Event, Lock, Thread


class RequestIO:
    def __init__(self, session, check):
        self.session, self.check = session, check
        self.done, self.lock = Event(), Lock()
        self.sockets, self.error, self.adapters = [], None, None

    def track(self, sock):
        with self.lock:
            self.sockets.append(sock)
            if self.error is not None:
                self._shutdown(sock)
        return sock

    @staticmethod
    def _shutdown(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def watch(self):
        while not self.done.wait(.05):
            try:
                self.check()
            except Exception as error:
                with self.lock:
                    self.error = error
                    for sock in self.sockets:
                        self._shutdown(sock)
                return

    def connect(self, connection):
        """One connect budget across all addresses, with caller-owned sockets.

        Nonblocking connects let Back interrupt even an unconnected socket.
        getaddrinfo remains a synchronous OS boundary (no orphan DNS worker).
        Host/SNI and TLS verification still belong to urllib3's connection.
        """
        from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
        from urllib3.util.connection import allowed_gai_family
        deadline = time.monotonic() + connection.timeout
        connection._control_connect_deadline = deadline
        host, port = connection._dns_host, connection.port
        try:
            addresses = socket.getaddrinfo(host, port, allowed_gai_family(), socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise NameResolutionError(host, connection, error) from error
        pending = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                   getattr(errno, 'WSAEWOULDBLOCK', 10035)}
        error = OSError('No usable address')
        for index, (family, kind, protocol, _, address) in enumerate(addresses):
            self.check()
            if time.monotonic() >= deadline:
                raise ConnectTimeoutError(connection, 'Connection budget exhausted')
            # Leave remaining loopback addresses a chance (e.g. a service only
            # bound to IPv4 while the OS returns IPv6 first). Unused time from
            # an immediate refusal carries forward, never a fresh full budget.
            now = time.monotonic()
            attempt_deadline = now + (deadline-now)/(len(addresses)-index)
            sock = self.track(socket.socket(family, kind, protocol))
            try:
                for option in connection.socket_options or ():
                    sock.setsockopt(*option)
                if connection.source_address:
                    sock.bind(connection.source_address)
                sock.setblocking(False)
                result = sock.connect_ex(address)
                while result in pending:
                    self.check()
                    remaining = attempt_deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout('Connection budget exhausted')
                    _, writable, exceptional = select.select([], [sock], [sock], min(.05, remaining))
                    self.check()
                    if writable or exceptional:
                        result = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if result:
                    raise OSError(result, 'Connection failed')
                self.check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout('Connection budget exhausted')
                sock.settimeout(remaining)
                return sock
            except OSError as caught:
                error = caught
                sock.close()
            except BaseException:
                sock.close()
                raise
        self.check()
        if isinstance(error, socket.timeout) or time.monotonic() >= deadline:
            raise ConnectTimeoutError(connection, 'Connection budget exhausted') from error
        raise NewConnectionError(connection, 'Connection failed') from error

    def __enter__(self):
        import requests
        from requests.sessions import Session
        from urllib3.connection import HTTPConnection, HTTPSConnection
        from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
        guard = self
        class Connection:
            def _new_conn(self):
                return guard.connect(self)
            def connect(self):
                super().connect()
                guard.track(self.sock)  # includes the wrapped TLS socket
        class HTTP(Connection, HTTPConnection):
            pass
        class HTTPS(Connection, HTTPSConnection):
            def connect(self):
                from urllib3.util.ssl_ import create_urllib3_context, resolve_ssl_version, resolve_cert_reqs
                context = self.ssl_context
                if context is None:
                    context = create_urllib3_context(ssl_version=resolve_ssl_version(self.ssl_version),
                        ssl_minimum_version=self.ssl_minimum_version, ssl_maximum_version=self.ssl_maximum_version,
                        cert_reqs=resolve_cert_reqs(self.cert_reqs))
                    if not self.ca_certs and not self.ca_cert_dir and not self.ca_cert_data:
                        context.load_default_certs()
                self.ssl_context = TLSContext(context, self)
                try:
                    super().connect()
                finally:
                    self.ssl_context = context
        class TLSContext:
            # A per-connection facade, not a global patch or mutation of the
            # context's wrap method. urllib3 still configures trust, ALPN, client
            # certificates and verifies hostname/fingerprint in its usual path.
            def __init__(self, context, connection):
                object.__setattr__(self, '_context', context)
                object.__setattr__(self, '_connection', connection)
            def __getattr__(self, name):
                return getattr(self._context, name)
            def __setattr__(self, name, value):
                setattr(self._context, name, value)
            def wrap_socket(self, sock, **kwargs):
                kwargs['do_handshake_on_connect'] = False
                secured = guard.track(self._context.wrap_socket(sock, **kwargs))
                try:
                    secured.setblocking(False)
                    while True:
                        guard.check()
                        remaining = self._connection._control_connect_deadline - time.monotonic()
                        if remaining <= 0:
                            raise socket.timeout('Connection budget exhausted')
                        try:
                            secured.do_handshake()
                            break
                        except ssl.SSLWantReadError:
                            read, write = [secured], []
                        except ssl.SSLWantWriteError:
                            read, write = [], [secured]
                        select.select(read, write, [], min(.05, remaining))
                    guard.check()
                    secured.settimeout(max(.001, self._connection._control_connect_deadline - time.monotonic()))
                    return secured
                except BaseException:
                    secured.close()
                    raise
        class HTTPPool(HTTPConnectionPool):
            ConnectionCls = HTTP
        class HTTPSPool(HTTPSConnectionPool):
            ConnectionCls = HTTPS
        if isinstance(self.session, Session):
            # A fresh pool has no socket belonging to another request. Preserve
            # the caller's session configuration; no retries of mutating calls.
            self.adapters = self.session.adapters.copy()
            self.adapter = requests.adapters.HTTPAdapter(max_retries=0)
            self.adapter.poolmanager.pool_classes_by_scheme = {'http': HTTPPool, 'https': HTTPSPool}
            self.session.mount('http://', self.adapter)
            self.session.mount('https://', self.adapter)
        self.worker = Thread(target=self.watch, name='bobbi-control-io')
        self.worker.start()
        return self

    def __exit__(self, kind, error, traceback):
        self.done.set()
        self.worker.join()
        if self.adapters is not None:
            self.session.adapters = self.adapters
            self.adapter.close()
        if self.error is not None:
            raise self.error
        return False
