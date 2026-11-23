"""Kodi page composition for the existing, pure artwork projection.

Capture one profile per synchronous page. No second cache, image worker or
global runtime registration; stale pages cannot adopt a newly selected root.
"""
from contextlib import contextmanager

from bobbi_core import image_cache
from .paths import ProfileBinding


@contextmanager
def image_batch():
    if image_cache.image_batch_active():
        yield
        return
    try:
        binding = ProfileBinding()
        root, current = binding.root(), binding.is_current
    except (ImportError, OSError, ValueError, RuntimeError):
        root, current = None, None
    with image_cache.image_batch(root, is_current=current):
        yield


def image_url(value, size=None, root=None):
    if root is not None or image_cache.image_batch_active():
        return image_cache.image_url(value, size, root)
    # Empty or non-TMDb art needs no Kodi path lookup at all.
    if not value or not isinstance(value, str):
        return image_cache.image_url(value, size)
    try:
        image_cache.image_path(value, size)
    except (TypeError, ValueError):
        # A stored loopback image may still need the core's strict rebinding.
        if not value.startswith('http://127.0.0.1:'):
            return value
    with image_batch():
        return image_cache.image_url(value, size)
