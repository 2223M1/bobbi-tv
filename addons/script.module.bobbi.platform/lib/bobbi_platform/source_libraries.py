"""Capture source consent and narrow read adapters at the Kodi boundary."""
from bobbi_core.source_library import Store
from dataclasses import dataclass
from .paths import ProfileBinding


def capture(binding=None):
    binding = binding or ProfileBinding()
    return Store(binding.root('plugin.video.bobbi'), active=binding.is_current)


class ShareReader:
    """Read-only proof access to one profile and one captured Host instance."""
    def __init__(self, binding, call):
        self.binding, self._call = binding, call

    def _read(self, action, body, timeout):
        self.binding.require_current()
        result = self._call(action, body, timeout=timeout)
        self.binding.require_current()
        return result

    def account_scope(self, *, timeout):
        return self._read('account_status', {}, timeout)

    def known_failures(self, body, *, timeout):
        return self._read('share_known_failures', body, timeout)

    def failure(self, body, *, timeout):
        return self._read('share_failure', body, timeout)


def capture_reader(binding):
    from .runtime import bind_call
    try:
        binding.require_current()
        reader = ShareReader(binding, bind_call(binding.root() / 'runtime.json'))
        binding.require_current()
        return reader
    except (OSError, ValueError, RuntimeError):
        return None  # Missing capture stays unknown; never retry against a new Host.


@dataclass(frozen=True)
class CatalogContext:
    binding: object
    reader: object
    source: object
    cache_path: object
    credential: object


def capture_context(binding=None):
    """One query/window capture, before workers; never refresh this implicitly."""
    try:
        binding = binding or ProfileBinding()
        reader = capture_reader(binding)
        store = capture(binding)
        source = store.current()
        binding.require_current()
        return CatalogContext(binding, reader, source,
            binding.root('plugin.video.bobbi').parent / 'script.module.bobbi.catalog' / 'cache.sqlite3',
            binding.root() / '115-os_linux.json')
    except (ImportError, OSError, ValueError, RuntimeError):
        return None
