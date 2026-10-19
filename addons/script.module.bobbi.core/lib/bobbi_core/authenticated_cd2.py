"""Box-owned CD2 login renewal. Never replay a cloud mutation after an error."""
import time

from bobbi_core.cd2 import CD2, CD2Error

READ_ONLY = {'GetSystemInfo', 'GetSubFiles', 'GetSearchResults', 'GetDownloadUrlPath',
             'ListOfflineFilesByPath', 'GetRuntimeInfo', 'GetSpaceInfo'}


class AuthenticatedCD2(CD2):
    def __init__(self, token, base, credentials, clock=time.monotonic):
        super().__init__(token, base)
        self.credentials = credentials
        self.clock = clock
        self.next_login = 0

    def rpc(self, method, payload=b''):
        try:
            return super().rpc(method, payload)
        except CD2Error as error:
            if error.status != '16' or method == 'GetToken' or self.clock() < self.next_login:
                raise
            self.next_login = self.clock() + 60
            credentials = self.credentials()
            if (not isinstance(credentials, dict) or set(credentials) != {'username', 'password'}
                    or any(not isinstance(value, str) or not 1 <= len(value) <= 4096 for value in credentials.values())):
                raise CD2Error('invalid-private-login') from None
            self.token = None
            try:
                self.login(credentials['username'], credentials['password'])
            finally:
                credentials.clear()
            if method not in READ_ONLY:
                # The durable queue must reconcile this submission. Even an
                # authentication failure must not introduce a hidden second add.
                raise error
            return super().rpc(method, payload)
