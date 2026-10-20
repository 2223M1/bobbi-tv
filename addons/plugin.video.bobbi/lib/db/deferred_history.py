"""One bounded history writer for natural episode handoff.

The snapshot is independent of player lifetime. The worker is non-daemon so
normal interpreter exit waits for the existing atomic save. Failed database
operations remain pending on the retained private database; they are retried
by its next commit. No network, GUI, playback or SQLite operations here.
"""
from copy import deepcopy
from threading import Lock, Thread

_lane = Lock()
_database = None


def defer_watched_file(data):
    """False means the caller must use its original synchronous save path."""
    if not _lane.acquire(blocking=False):
        return False
    try:
        snapshot = deepcopy(data)
        thread = Thread(target=_save, args=(snapshot,), name='cinema-history-save', daemon=False)
        thread.start()
    except Exception:
        _lane.release()
        return False
    return True


def _save(snapshot):
    global _database
    from lib.jacktook.utils import kodilog
    try:
        # A separate instance prevents the new player's history readers from
        # racing a mutation of the legacy module's in-memory operation list.
        from lib.db.pickle_db import PickleDatabase
        from lib.utils.general.utils import set_watched_file
        if _database is None:
            _database = PickleDatabase()
        if set_watched_file(snapshot, database=_database) is not True:
            kodilog('[CINEMA-HISTORY] save deferred; original and pending operations preserved')
    except Exception as error:
        kodilog('[CINEMA-HISTORY] save unavailable: ' + type(error).__name__)
    finally:
        _lane.release()
