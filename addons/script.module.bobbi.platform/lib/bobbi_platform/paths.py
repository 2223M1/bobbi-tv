"""Resolve per-device profile paths; never assume CE /storage on Android."""
from pathlib import Path


def profile_root(addon_id='script.module.bobbi.platform'):
    """Read the current Kodi ownership boundary without creating directories."""
    import xbmcvfs
    if (type(addon_id) is not str or not addon_id.startswith(('script.', 'plugin.'))
            or 'bobbi' not in addon_id.split('.') or '/' in addon_id or '\\' in addon_id):
        raise ValueError('bobbi addon profile required')
    root = Path(xbmcvfs.translatePath('special://profile/addon_data/' + addon_id))
    if not root.is_absolute():
        raise ValueError('Absolute profile path required')
    return root.resolve()


def profile(addon_id='script.module.bobbi.platform', name=''):
    root = profile_root(addon_id)
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ValueError('Profile path escaped')
    root.mkdir(parents=True, exist_ok=True)
    return target


class ProfileBinding:
    """One instance's captured roots; a switch requires closing that instance.

    This observes Kodi's actual path mapping, not a guessed notification. It
    neither switches profiles nor moves credentials/state to another root.
    """
    ADDONS = ('script.module.bobbi.platform', 'plugin.video.bobbi')

    def __init__(self, resolver=None):
        self._resolver = resolver or profile_root
        self._roots = self._read()
        # Refuse a capture spanning a profile change between the two roots.
        if self._roots != self._read():
            raise ValueError('PROFILE_CHANGED')
        self._revoked = False

    def _read(self):
        roots = tuple(Path(self._resolver(addon_id)) for addon_id in self.ADDONS)
        if any(not root.is_absolute() for root in roots):
            raise ValueError('Absolute profile path required')
        return tuple(root.resolve() for root in roots)

    def root(self, addon_id='script.module.bobbi.platform'):
        try:
            return self._roots[self.ADDONS.index(addon_id)]
        except ValueError:
            raise ValueError('Profile root not captured') from None

    def is_current(self):
        # Once observed revoked, A -> B -> A cannot revive A's old leases,
        # UI continuations or phone permissions.
        if not self._revoked:
            try:
                if self._read() != self._roots:
                    self._revoked = True
            except (OSError, ValueError, RuntimeError):
                self._revoked = True
        return not self._revoked

    def require_current(self):
        if not self.is_current():
            raise ValueError('PROFILE_CHANGED')
