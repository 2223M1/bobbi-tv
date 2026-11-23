"""Legacy plugin transport entry; core never discovers the platform."""
from lib.cinema import _shared  # dependency bootstrap
from bobbi_core import playback_ipc as _core
from bobbi_core.playback_ipc import SOCKET_PATH, MAX_FRAME


def call(message, path=SOCKET_PATH, timeout=.3, *, host_call=None):
    if path is not None or host_call is not None:
        return _core.call(message, path, timeout, host_call=host_call)
    from bobbi_platform.playback_client import capture
    return capture().call(message, timeout=timeout)
