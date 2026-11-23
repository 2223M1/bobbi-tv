"""Owner-thread readiness gate; failures never authorize cloud work or replay IO."""
import time


class AccountReadiness:
    def __init__(self, expected, clock=time.monotonic):
        if not isinstance(expected, str) or not expected:
            raise ValueError('An explicit account scope is required')
        self.expected, self.clock = expected, clock
        self.state, self.failures, self.next_check = 'UNVERIFIED', 0, 0.0
        self.error = None
        self.verified = False

    @property
    def ready(self):
        # A periodic startup-health refresh must not starve the independent
        # playback lane behind a slow media probe. That lane still checks
        # the actual account before and after every file read itself.
        return self.verified and self.state in ('READY', 'CHECKING')

    def begin(self):
        if self.state in ('CHECKING', 'ACCOUNT_MISMATCH') or self.clock() < self.next_check:
            return False
        self.state = 'CHECKING'
        return True

    def complete(self, account=None, error=None):
        if self.state != 'CHECKING':
            raise ValueError('No outstanding account check')
        now = self.clock()
        if error is not None:
            self.verified = False
            self.failures = min(self.failures + 1, 5)
            self.state, self.error = 'DEPENDENCY_UNAVAILABLE', type(error).__name__
            self.next_check = now + min(5 * 2 ** (self.failures - 1), 60)
        elif account != self.expected:
            self.verified = False
            # A successful response identifying another account is not a
            # transient network failure. Keep all cloud work closed until a
            # reviewed service restart; never silently adopt that account.
            self.state, self.error = 'ACCOUNT_MISMATCH', None
        else:
            self.verified = True
            self.state, self.error, self.failures = 'READY', None, 0
            self.next_check = now + 60
        return self.snapshot()

    def snapshot(self):
        return {'state': self.state,
                'ready': self.ready, 'error': self.error,
                'retry_after_seconds': max(0, round(self.next_check - self.clock(), 3))
                if self.state not in ('CHECKING', 'ACCOUNT_MISMATCH') else None}
