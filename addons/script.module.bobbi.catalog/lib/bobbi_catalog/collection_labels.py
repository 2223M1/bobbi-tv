"""Public collection headings, keyed by a stable group hash. No file/share URLs."""
from functools import lru_cache
import json
from pathlib import Path
from bobbi_core.library_labels import ref


@lru_cache(maxsize=1)
def headings():
    return json.loads((Path(__file__).resolve().parents[2]/'resources/collection-headings.json').read_bytes())


def membership(group):
    identity = ref('qqdocs',group)
    name = headings().get(identity)
    return {identity:name} if name else {}
