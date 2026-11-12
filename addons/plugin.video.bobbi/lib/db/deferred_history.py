"""One bounded history writer for natural episode handoff.

The snapshot is independent of player lifetime. The worker is non-daemon so
normal interpreter exit waits for the existing atomic save. Failed database
operations remain pending on the retained private database; they are retried
by its next commit. No network, GUI, playback or SQLite operations here.
"""
from copy import deepcopy
from collections import OrderedDict
from threading import Lock, Thread

_lane = Lock()
_databases = OrderedDict()
_MAX_PROFILES = 4


def _evictable():
    return next((root for root, database in _databases.items() if not database.has_pending()), None)


def defer_watched_file(data):
    """False means the caller must use its original synchronous save path."""
    if not _lane.acquire(blocking=False):
        return False
    try:
        from bobbi_platform.paths import profile_root
        # Resolve on the submitting owner's thread, before a switch can make
        # the worker interpret special://profile as a different user's root.
        root = profile_root('plugin.video.bobbi')
        if root not in _databases and len(_databases) >= _MAX_PROFILES and _evictable() is None:
            _lane.release()
            return False  # Never evict unsaved operations from another profile.
        snapshot = deepcopy(data)
        thread = Thread(target=_save, args=(snapshot, root), name='cinema-history-save', daemon=False)
        thread.start()
    except Exception:
        _lane.release()
        return False
    return True


def _save(snapshot, root):
    from lib.jacktook.utils import kodilog
    try:
        # A separate instance prevents the new player's history readers from
        # racing a mutation of the legacy module's in-memory operation list.
        from lib.db.pickle_db import PickleDatabase
        from lib.utils.general.utils import set_watched_file
        if root not in _databases:
            if len(_databases) >= _MAX_PROFILES:
                old = _evictable()
                if old is None:
                    raise RuntimeError('History profile writers busy')
                del _databases[old]
            _databases[root] = PickleDatabase(profile_root=root)
        database = _databases[root]
        _databases.move_to_end(root)
        if set_watched_file(snapshot, database=database) is not True:
            kodilog('[CINEMA-HISTORY] save deferred; original and pending operations preserved')
    except Exception as error:
        kodilog('[CINEMA-HISTORY] save unavailable: ' + type(error).__name__)
    finally:
        _lane.release()
