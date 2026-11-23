"""Legacy complete operations; each captures one binding for all nested IO."""
from lib.cinema import _shared  # dependency bootstrap
from bobbi_core import playback_request as _core
from bobbi_core.playback_request import (
    Client, SelectionChanged, context, data_identity, digest, source_identity,
    torrent_file_identity, unavailable,
)
from .playback_ipc import call


def _owner_call(supplied):
    if supplied is not None:
        return supplied
    from bobbi_platform.playback_client import capture
    return capture().call


def select(*args, owner_call=None, **kwargs):
    return _core.select(*args, owner_call=_owner_call(owner_call), **kwargs)


def reserve_ui_entry(*args, owner_call=None, **kwargs):
    return _core.reserve_ui_entry(*args, owner_call=_owner_call(owner_call), **kwargs)


def bind_and_claim(*args, owner_call=None, **kwargs):
    return _core.bind_and_claim(*args, owner_call=_owner_call(owner_call), **kwargs)


def resolve_torrent(*args, owner_call=None, **kwargs):
    return _core.resolve_torrent(*args, owner_call=_owner_call(owner_call), **kwargs)


def resolved_torrent_file_identity(*args, owner_call=None, **kwargs):
    return _core.resolved_torrent_file_identity(*args, owner_call=_owner_call(owner_call), **kwargs)


def validate_torrent_resolution(*args, owner_call=None, **kwargs):
    return _core.validate_torrent_resolution(*args, owner_call=_owner_call(owner_call), **kwargs)


def startup_failure(*args, owner_call=None, **kwargs):
    return _core.startup_failure(*args, owner_call=_owner_call(owner_call), **kwargs)


def read_snapshot(*args, owner_call=None, **kwargs):
    return _core.read_snapshot(*args, owner_call=_owner_call(owner_call), **kwargs)


def owned_state(*args, owner_call=None, **kwargs):
    return _core.owned_state(*args, owner_call=_owner_call(owner_call), **kwargs)


def monitor_state(*args, owner_call=None, **kwargs):
    return _core.monitor_state(*args, owner_call=_owner_call(owner_call), **kwargs)


def terminal_state(*args, owner_call=None, **kwargs):
    return _core.terminal_state(*args, owner_call=_owner_call(owner_call), **kwargs)
