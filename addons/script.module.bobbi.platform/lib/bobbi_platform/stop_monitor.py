"""Owner cancellation plus Kodi abort, without disabling an addon to stop IO."""
import time


class StopMonitor:
    def __init__(self, stopping, monitor):
        self.stopping, self.monitor = stopping, monitor

    def abortRequested(self):
        return self.stopping.is_set() or self.monitor.abortRequested()

    def waitForAbort(self, timeout):
        end = time.monotonic() + max(0, timeout)
        while not self.abortRequested():
            remaining = end - time.monotonic()
            if remaining <= 0:
                return False
            # Keep Kodi callbacks pumped. Never pass zero (infinite in F9).
            if self.monitor.waitForAbort(min(.1, remaining)):
                return True
        return True
