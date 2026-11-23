"""Compatibility construction captures one resource reader before worker start."""
from lib.cinema import _shared  # dependency bootstrap
import time
from bobbi_core import prepared_protection as _core
from bobbi_core.prepared_protection import PreparedProtection, install_schema, DDL, SCHEMA_KEY


def native_resource_snapshot():
    from bobbi_platform.playback_client import capture
    return capture().call({'operation': 'resource_snapshot'})


class ProtectionLane(_core.ProtectionLane):
    def __init__(self, protection, read=None, clock=time.monotonic):
        if read is None:
            from bobbi_platform.playback_client import capture
            client = capture()
            read = lambda: client.call({'operation': 'resource_snapshot'})
        super().__init__(protection, read, clock)
