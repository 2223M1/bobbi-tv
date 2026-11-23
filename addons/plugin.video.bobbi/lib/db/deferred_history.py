"""One bounded history writer for natural episode handoff.

The snapshot is independent of player lifetime. The worker is non-daemon so
normal interpreter exit waits for the existing atomic save. Failed database
operations remain pending on the retained private database; they are retried
by its next commit. No network, GUI, playback or SQLite operations here.
An in-flight personal-file job can retain its own latest complete snapshot;
other requests still have no queue or synchronous personal-file fallback.
"""
from copy import deepcopy
from collections import OrderedDict
from threading import Lock, Thread

_lane = Lock()
_admission = Lock()
_job = None
_databases = OrderedDict()
_MAX_PROFILES = 4


def _evictable():
    return next((root for root, database in _databases.items() if not database.has_pending()), None)


def defer_watched_file(data, *, profile_binding=None):
    """True means admitted, not persisted. Personal callers never fall back.

    Only a newer report for the exact in-flight personal context can replace
    its latest snapshot. Legacy/cross-request overload still returns False.
    """
    global _job
    try:
        from bobbi_platform.paths import profile_root
        # Resolve on the submitting owner's thread, before a switch can make
        # the worker interpret special://profile as a different user's root.
        if profile_binding is not None:
            profile_binding.require_current()
            root = profile_binding.root('plugin.video.bobbi')
        else:
            root = profile_root('plugin.video.bobbi')
        snapshot = deepcopy(data)
        if profile_binding is not None:
            profile_binding.require_current()
    except Exception:
        return False
    key = None
    try:
        from lib.db.file_history import coalescing_key
        key = coalescing_key(snapshot, root)
    except ImportError:
        pass
    with _admission:
        if profile_binding is not None:
            try:
                # Waiting for admission cannot extend a revoked profile lease.
                # Already admitted work still drains its captured root below.
                profile_binding.require_current()
            except Exception:
                return False
        if _job is not None:
            if (key is None or key != _job['key'] or snapshot['_file_history_sequence'] <=
                    _job['latest']['_file_history_sequence']):
                return False
            # Replace the complete incoming observation, including absence of
            # facts. Missing facts revoke; never fill them from the old job.
            _job.update(latest=snapshot, revision=_job['revision'] + 1)
            return True
        if not _lane.acquire(blocking=False):
            return False
        job = dict(root=root, key=key, latest=snapshot, revision=1)
        _job = job
        try:
            if root not in _databases and len(_databases) >= _MAX_PROFILES and _evictable() is None:
                _finish(job)
                return False  # Never evict another profile's pending operations.
            # Publish/start atomically to admission. A failed start cannot
            # strand a later caller that was already told its update was kept.
            thread = Thread(target=_save, args=(job,), name='cinema-history-save', daemon=False)
            thread.start()
        except BaseException as error:
            _finish(job)
            if not isinstance(error, Exception):
                raise
            return False
        return True


def _finish(job):
    """Called under admission; never release a successor's lane twice."""
    global _job
    if _job is job:
        _job = None
        _lane.release()


def _diagnose(message):
    try:
        from lib.jacktook.utils import kodilog
        kodilog(message)
    except Exception:
        pass  # A broken diagnostic cannot discard an admitted newer report.


def _save(job):
    root = job['root']
    try:
        while True:
            with _admission:
                snapshot, revision = job['latest'], job['revision']
            try:
                # Only this worker accesses its private pending journal. IO is
                # outside admission and never re-resolves the active profile.
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
                    _diagnose('[CINEMA-HISTORY] save deferred; original and pending operations preserved')
            except Exception as error:
                _diagnose('[CINEMA-HISTORY] save unavailable: ' + type(error).__name__)
            with _admission:
                if job['revision'] == revision:
                    # No check/clear gap: a concurrent producer either updates
                    # this job before here, or admits a fresh job after release.
                    _finish(job)
                    return
    finally:
        with _admission:
            _finish(job)
