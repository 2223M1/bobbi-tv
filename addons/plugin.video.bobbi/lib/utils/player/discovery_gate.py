"""Single-flight retry gate for a session's read-only resource discovery."""
from threading import Lock


class DiscoveryGate:
    def __init__(self):
        self._lock = Lock()
        self._generation = None
        self._revision = 0
        self._sequence = 0
        self._pending = None
        self._attempts = 0
        self._due = 0.0
        self._ready = False

    def begin(self, now):
        with self._lock:
            if self._pending is not None or self._ready or now < self._due:
                return None
            self._sequence += 1
            self._pending = (self._revision, self._sequence)
            return self._pending

    def finish(self, token, found, now, publish):
        """Publish only the still-current generation while holding the gate."""
        with self._lock:
            if self._pending != token:
                return False
            self._pending = None
            if token[0] != self._revision:
                return False
            self._attempts += 1
            self._ready = bool(found)
            self._due = now + min(30.0, 2.0 ** min(self._attempts, 5))
            publish()
            return True

    def wake(self, generation):
        with self._lock:
            if generation == self._generation:
                return False
            self._generation = generation
            self._revision += 1
            self._ready = False
            self._attempts = 0
            self._due = 0.0
            return True
