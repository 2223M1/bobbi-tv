"""Per-install ShareStream rollout switch, independent of account/program data."""
import json
from pathlib import Path


def load(root):
    path = Path(root) / 'share-transport.json'
    if not path.exists():
        return False  # Untested installs retain the established block mode.
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256:
        raise ValueError('SHARE_PREFERENCE_INVALID')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (type(value) is not dict or set(value) != {'schema', 'mode'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['mode'] not in ('block', 'progressive')):
        raise ValueError('SHARE_PREFERENCE_INVALID')
    return value['mode'] == 'progressive'


def save(root, progressive):
    import os
    import tempfile
    if type(progressive) is not bool:
        raise ValueError('SHARE_PREFERENCE_INVALID')
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('SHARE_PREFERENCE_INVALID')
    root.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.share-transport-', dir=str(root))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(dict(schema=1, mode='progressive' if progressive else 'block'), out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, root / 'share-transport.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)
