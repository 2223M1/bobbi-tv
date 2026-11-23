"""Check installation state before importing any mutable cinema dependency."""
import json
from pathlib import Path


def ready():
    import xbmcvfs
    path = Path(xbmcvfs.translatePath(
        'special://profile/addon_data/script.bobbi.start/installation.json'))
    if not path.exists():
        return True
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            return False
        return json.loads(path.read_text(encoding='utf-8')).get('phase') in (
            'activation_pending', 'restore_pending', 'complete', 'restored')
    except (OSError, ValueError):
        return False
