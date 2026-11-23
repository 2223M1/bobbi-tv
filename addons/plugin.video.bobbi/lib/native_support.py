"""Capability-based client dispatch. Never infer protocol from CPU or platform."""
import time

_cached = None
_until = 0


def available():
    global _cached, _until
    from bobbi_platform.capabilities import probe
    from bobbi_platform.kodi import rpc
    # The resident service and all picker invokers must agree. A transient
    # startup probe must not leave the service on stock while a later GUI
    # interpreter sends it private-native ownership commands.
    try:
        from bobbi_platform.runtime import call
        state = call('status', {}, timeout=.25)
        if state.get('playback_adapter') in ('native', 'standard'):
            return state['playback_adapter'] == 'native'
    except (OSError, ValueError, RuntimeError):
        pass
    if time.monotonic() >= _until:
        _cached = probe(rpc)['native_contract_available'] is True
        _until = time.monotonic() + (30 if _cached else 2)
    return _cached
