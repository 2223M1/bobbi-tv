"""Box-owned CD2 login renewal. Never replay a cloud mutation after an error."""
import time
from threading import Lock

from bobbi_core.cd2 import CD2, CD2Error

READ_ONLY = {'GetSystemInfo', 'GetSubFiles', 'GetSearchResults', 'GetDownloadUrlPath',
             'ListOfflineFilesByPath', 'GetRuntimeInfo', 'GetSpaceInfo'}


class CD2Authentication:
    """One preparation incarnation's auth, shared by independent IO clients.

    Only token renewal is serialized. Directory/media IO still owns separate
    requests sessions. This is not a cache of mounted-account authorization.
    """
    def __init__(self, token, credentials, clock=time.monotonic):
        self.token, self.credentials, self.clock = token, credentials, clock
        self.lock, self.revision, self.next_login = Lock(), 0, 0
        self.base = None

    def bind(self, base):
        with self.lock:
            if self.base is not None and self.base != base:
                raise ValueError('CD2 authentication belongs to another endpoint')
            self.base = base

    def snapshot(self):
        with self.lock:
            return self.token, self.revision

    def renew(self, client, rejected_revision):
        with self.lock:
            if self.revision != rejected_revision:
                client.token = self.token
                return True  # Another IO lane already renewed this generation.
            if self.clock() < self.next_login:
                return False
            self.next_login = self.clock() + 60
            credentials = self.credentials()
            try:
                if (not isinstance(credentials, dict) or set(credentials) != {'username', 'password'}
                        or any(not isinstance(value, str) or not 1 <= len(value) <= 4096 for value in credentials.values())):
                    raise CD2Error('invalid-private-login') from None
                client.token = None
                client.login(credentials['username'], credentials['password'])
                self.token = client.token
                self.revision += 1
                return True
            finally:
                if isinstance(credentials, dict):
                    credentials.clear()


class AuthenticatedCD2(CD2):
    def __init__(self, token, base, credentials, clock=time.monotonic, *, authentication=None):
        super().__init__(token, base)
        self.authentication = authentication or CD2Authentication(token, credentials, clock)
        try:
            self.authentication.bind(self.base)
        except BaseException:
            self.session.close()
            raise

    def rpc(self, method, payload=b''):
        if method == 'GetToken':
            return super().rpc(method, payload)
        self.token, revision = self.authentication.snapshot()
        try:
            return super().rpc(method, payload)
        except CD2Error as error:
            if error.status != '16':
                raise
            if not self.authentication.renew(self, revision) or method not in READ_ONLY:
                # The durable queue must reconcile this submission. Even an
                # authentication failure must not introduce a hidden second add.
                raise error
            return super().rpc(method, payload)
