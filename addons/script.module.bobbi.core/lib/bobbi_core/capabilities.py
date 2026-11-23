"""Explicit wire compatibility; capability checks are not health claims."""
from bobbi_core import CORE_API, CORE_VERSION

IPC_PROTOCOL = 3
CAPABILITIES = frozenset({
    'exact-resource-identity-v1', 'single-cloud-ledger-v1',
    'reconcile-uncertain-submit-v1', 'same-release-next-v1',
    'subtitle-binding-v2', 'video-context-v1', 'bounded-resolve-v1',
})


def descriptor():
    return {'core_api': CORE_API, 'core_version': CORE_VERSION,
            'ipc_protocol': IPC_PROTOCOL, 'capabilities': sorted(CAPABILITIES)}


def compatible(value):
    return (isinstance(value, dict) and type(value.get('core_api')) is int
            and value['core_api'] == CORE_API
            and type(value.get('ipc_protocol')) is int
            and value['ipc_protocol'] == IPC_PROTOCOL
            and isinstance(value.get('capabilities'), list)
            and all(isinstance(item, str) for item in value['capabilities'])
            and CAPABILITIES.issubset(value['capabilities']))
