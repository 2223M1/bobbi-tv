"""A scope projection, not another account owner, credential store or lock."""
from bobbi_core.account_scope import AccountError

from .pan_accounts import PanError, provider_id, scope, SERVER_PROVIDERS


def projected(value):
    return scope(dict(value, provider='115'), '115')


def legacy_scope(value):
    value = scope(value, '115')
    return {key: item for key, item in value.items() if key != 'provider'}


class Accounts:
    def __init__(self, native, legacy, servers=None):
        self.native, self.legacy, self.servers = native, legacy, servers

    def _owner(self, provider):
        if provider in dict(SERVER_PROVIDERS):
            if self.servers is None:
                raise PanError('PAN_ADAPTER_UNAVAILABLE')
            return self.servers
        return self.native

    def __repr__(self):
        return '<Unified accounts: credentials hidden>'

    @staticmethod
    def _call(method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except AccountError:
            raise PanError('PAN_ACCOUNT_CHANGED') from None

    def snapshot(self, provider):
        return (projected(self.legacy.snapshot()) if provider_id(provider) == '115'
                else self._owner(provider).snapshot(provider))

    def require_current(self, expected, authenticated=True):
        expected = scope(expected, authenticated=authenticated)
        if expected['provider'] == '115':
            self._call(self.legacy.require_current, legacy_scope(expected), authenticated=authenticated)
            return expected
        return self._owner(expected['provider']).require_current(expected, authenticated)

    def is_current(self, expected):
        try:
            self.require_current(expected, authenticated=False)
            return True
        except PanError:
            return False

    def run_if_current(self, expected, operation, authenticated=True):
        expected = scope(expected, authenticated=authenticated)
        if expected['provider'] == '115':
            return self._call(self.legacy.run_if_current, legacy_scope(expected), operation,
                              authenticated=authenticated)
        return self._owner(expected['provider']).run_if_current(expected, operation, authenticated)

    def credentials(self, expected):
        expected = scope(expected, authenticated=True)
        if expected['provider'] == '115':
            return self._call(self.legacy.credentials, legacy_scope(expected))
        return self._owner(expected['provider']).credentials(expected)

    def subscribe(self, listener):
        native_unsubscribe = self.native.subscribe(listener)
        server_unsubscribe = self.servers.subscribe(listener) if self.servers is not None else lambda: None
        # Some read-only test ports expose snapshot only; the real Host always
        # supplies AccountManager. Runtime gates still compare its live scope.
        subscribe = getattr(self.legacy, 'subscribe', None)
        legacy_unsubscribe = (subscribe(lambda old, new: listener(projected(old), projected(new)))
                              if callable(subscribe) else lambda: None)
        def unsubscribe():
            native_unsubscribe()
            legacy_unsubscribe()
            server_unsubscribe()
        return unsubscribe

    def install(self, value, expected):
        if scope(expected)['provider'] == '115':
            raise PanError('PAN_LOGIN_UNAVAILABLE')  # Existing QR owner only.
        return self.native.install(value, expected)

    def _checked(self, provider, value):
        # Generic QR staging has no 115 flow; retain its native validator gate.
        return self.native._checked(provider, value)

    def renew(self, value, expected, previous=None):
        if scope(expected)['provider'] == '115':
            raise PanError('PAN_LOGIN_UNAVAILABLE')  # No second cookie writer.
        return self.native.renew(value, expected, previous=previous)

    def logout(self, expected):
        expected = scope(expected)
        if expected['provider'] == '115':
            return projected(self._call(self.legacy.logout, legacy_scope(expected)))
        return self._owner(expected['provider']).logout(expected)
