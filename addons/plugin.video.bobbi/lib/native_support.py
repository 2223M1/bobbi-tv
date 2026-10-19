"""Capability-based client dispatch. Never infer protocol from CPU or platform."""
from functools import lru_cache


@lru_cache(maxsize=1)
def available():
    from bobbi_platform.capabilities import probe
    from bobbi_platform.kodi import rpc
    return probe(rpc)['native_contract_available'] is True
