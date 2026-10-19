"""Resolve per-device profile paths; never assume CE /storage on Android."""
from pathlib import Path


def profile(addon_id='script.module.bobbi.platform', name=''):
    import xbmcvfs
    if not addon_id.startswith(('script.', 'plugin.')) or 'bobbi' not in addon_id.split('.'):
        raise ValueError('bobbi addon profile required')
    root = Path(xbmcvfs.translatePath('special://profile/addon_data/' + addon_id)).resolve()
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ValueError('Profile path escaped')
    root.mkdir(parents=True, exist_ok=True)
    return target
