"""Capture playback transport once per interpreter entry, without cloud accounts."""
import time
from math import isfinite

from bobbi_core.playback_ipc import call
from bobbi_core.playback_request import Client, unavailable


def capture(*, binding=None):
    """A failed capture remains unavailable for this entry and all its callbacks."""
    return capture_transport(binding=binding)[1]


def capture_transport(*, binding=None):
    """One Host for navigation's adapter query and the selected playback API.

    The generic callback is not native playback authority. Standard callers
    retain their existing select/current/handoff contract and IO budgets.
    """
    try:
        from .paths import ProfileBinding
        from .runtime import bind_call
        binding = ProfileBinding() if binding is None else binding
        binding.require_current()
        host_call = bind_call(binding.root() / 'runtime.json')
        binding.require_current()
    except (ImportError, OSError, ValueError, TypeError, RuntimeError):
        return None, unavailable(), unavailable_host_call

    def guarded(action, body, timeout=3):
        if type(timeout) not in (int, float) or not isfinite(timeout) or timeout <= 0:
            raise ValueError('Bounded Host timeout required')
        deadline = time.monotonic() + timeout
        binding.require_current()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Playback binding budget expired')
        result = host_call(action, body, timeout=min(timeout, remaining))
        binding.require_current()
        return result

    def bound(message, timeout=.3):
        if type(timeout) not in (int, float) or not 0 < timeout <= .3:
            raise ValueError('Bounded playback timeout required')
        return call(message, timeout=timeout, host_call=guarded)

    return binding, Client(bound), guarded


def unavailable_host_call(*args, **kwargs):
    raise OSError('PLAYBACK_BINDING_UNAVAILABLE')
