"""Playback-only scope routing; 115 credentials/preparation remain unchanged."""
from .pan_accounts import PanError, scope


class PlaybackAccounts:
    def __init__(self, legacy, pan_owner):
        self.legacy, self.pan_owner = legacy, pan_owner

    def snapshot(self):
        # Existing account-independent/BT selection behavior remains 115.
        return self.legacy.snapshot()

    def _owner(self, expected):
        if type(expected) is dict and 'provider' in expected:
            scope(expected, authenticated=True)
            owner = self.pan_owner()
            if owner is None:
                raise PanError('PAN_SERVICE_CLOSED')
            return owner.accounts
        return self.legacy

    def require_current(self, expected, authenticated=True):
        return self._owner(expected).require_current(expected, authenticated=authenticated)

    def is_current(self, expected):
        try:
            return self._owner(expected).is_current(expected)
        except (ValueError, RuntimeError):
            return False

    def run_if_current(self, expected, operation, authenticated=True):
        return self._owner(expected).run_if_current(expected, operation, authenticated=authenticated)
