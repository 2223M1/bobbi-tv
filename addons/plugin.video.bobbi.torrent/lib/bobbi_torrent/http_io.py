"""Request-local socket cancellation, including slow headers and trickle bodies.

No global urllib3 patch or detached request thread. The calling thread owns
Requests and its response; a joined watchdog only shuts down this request's
socket. TLS verification, Requests parsing and the ordinary read caps remain.
"""
import socket
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

    def __enter__(self):
        import requests
        from requests.sessions import Session
        from urllib3.connection import HTTPConnection, HTTPSConnection
        from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
        guard = self
        class Connection:
            def _new_conn(self):
                return guard.track(super()._new_conn())
            def connect(self):
                super().connect()
                guard.track(self.sock)  # includes the wrapped TLS socket
        class HTTP(Connection, HTTPConnection):
            pass
        class HTTPS(Connection, HTTPSConnection):
            pass
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
