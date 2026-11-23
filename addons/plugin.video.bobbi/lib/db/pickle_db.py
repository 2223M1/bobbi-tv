"""Legacy history format with atomic, operation-merged cross-process writes.

Kodi runs several plugin interpreters. A stale in-memory dictionary must not
erase newer entries, and readers must never see a truncated file during save.
"""
import copy
import logging
import os
import pickle
import tempfile
import threading
import time
from contextlib import contextmanager

_WRITER_LOCK = threading.RLock()
_BASE_KEYS = ("jt:watch", "jt:lth", "jt:lfh", "jt:lib")
_MAX_BYTES = 64 * 1024 * 1024


@contextmanager
def _writer_lock(path):
    # OS locks are released on process death; no stale PID-file deletion.
    with _WRITER_LOCK, open(path + ".lock", "a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if not os.fstat(lock.fileno()).st_size:
                lock.write(b"0")
                lock.flush()
            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(lock, fcntl.LOCK_UN)
        deadline = time.monotonic() + 2
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("History writer busy")
                time.sleep(.025)
        try:
            yield
        finally:
            release()


def _read(path):
    try:
        with open(path, "rb") as stream:
            if os.fstat(stream.fileno()).st_size > _MAX_BYTES:
                raise ValueError("History exceeds size limit")
            database = pickle.load(stream)
    except FileNotFoundError:
        database = {}
    if not isinstance(database, dict) or any(
        key in database and not isinstance(database[key], dict) for key in _BASE_KEYS
    ):
        raise ValueError("Invalid history schema")
    return {**{key: {} for key in _BASE_KEYS}, **database}


def _atomic_save(path, database):
    encoded = pickle.dumps(database, protocol=4)
    if len(encoded) > _MAX_BYTES:
        raise ValueError("History exceeds size limit")
    fd, temporary = tempfile.mkstemp(prefix="database-", suffix=".pending", dir=os.path.dirname(path))
    # On failure retain the pending file for diagnosis. Never touch the current
    # database until the complete replacement is durable and validated.
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    _read(temporary)
    os.replace(temporary, path)
    if os.name != "nt":
        directory_fd = os.open(os.path.dirname(path), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


class PickleDatabase:
    def __init__(self, profile_root=None):
        if profile_root is not None and not os.path.isabs(os.fspath(profile_root)):
            raise ValueError('PROFILE_ROOT_INVALID')
        if profile_root is None:
            # Legacy foreground callers retain their explicit Kodi adapter.
            # Captured background storage never imports UI/cache singletons.
            import xbmcvfs
            data_dir = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi')
            xbmcvfs.mkdirs(data_dir)
        else:
            data_dir = os.fspath(profile_root)
            os.makedirs(data_dir, exist_ok=True)
        self._database_path = os.path.join(data_dir, "database.pickle")
        self._pending = []
        self._database = {key: {} for key in _BASE_KEYS}
        self._reload()

    def _reload(self):
        available = True
        try:
            self._database = _read(self._database_path)
        except Exception as error:
            # Unreadable history is not evidence that nothing was watched.
            # The original stays untouched; commit also fails closed.
            logging.getLogger(__name__).warning("History read unavailable; original preserved: %s", type(error).__name__)
            available = False
        for operation in self._pending:
            self._apply(self._database, operation)
        return available

    @staticmethod
    def _apply(database, operation):
        action, key, subkey, value = operation
        if action == "key":
            database[key] = copy.deepcopy(value)
            # Clearing/replacing a history namespace revokes its dependent
            # observations too. No independent facts authority survives it.
            database.pop(key + ':playback_start', None)
            return True
        elif action == "set":
            database.setdefault(key, {})[subkey] = copy.deepcopy(value)
            return True
        elif action == "delete":
            database.get(key, {}).pop(subkey, None)
            PickleDatabase._forget_file_observation(database, key, subkey)
            return True
        elif action == "delete_if" and database.get(key, {}).get(subkey) == value:
            database.get(key, {}).pop(subkey, None)
            PickleDatabase._forget_file_observation(database, key, subkey)
            return True
        elif action == "file_report":
            # Re-evaluate under the cross-process commit lock, not only in a
            # stale writer snapshot. A late old session cannot win disk order.
            current = database.get(key, {}).get(subkey)
            value, observation = value if type(value) is tuple else (value, None)
            if (isinstance(current, dict) and current.get('version') == 1
                    and current.get('generation') == value.get('generation')
                    and current.get('session_id') == value.get('session_id')
                    and value.get('sequence', 0) > current.get('sequence', 0)):
                facts_key = key + ':playback_start'
                facts = database.get(facts_key)
                if observation is not None and facts is not None and type(facts) is not dict:
                    raise ValueError('FILE_HISTORY_FACTS_SCHEMA_UNSUPPORTED')
                database[key][subkey] = copy.deepcopy(value)
                if observation is not None:
                    facts = database.setdefault(facts_key, {})
                    facts[subkey] = dict(binding={field: copy.deepcopy(value[field]) for field in
                        ('file_ref', 'generation', 'session_id', 'sequence')}, observation=copy.deepcopy(observation))
                else:
                    PickleDatabase._forget_file_observation(database, key, subkey)
                return True
        return False

    @staticmethod
    def _forget_file_observation(database, key, subkey):
        facts = database.get(key + ':playback_start')
        if type(facts) is dict:
            facts.pop(subkey, None)

    def _queue(self, operation, commit):
        self._stage(operation)
        if commit:
            return self.commit()

    def _stage(self, operation):
        operation = copy.deepcopy(operation)
        self._pending.append(operation)
        self._apply(self._database, operation)
        return operation

    def set_item(self, key: str, subkey: str, value, commit: bool = True):
        return self._queue(("set", key, subkey, value), commit)

    def has_pending(self):
        """A profile-bound deferred writer must not evict unsaved operations."""
        return bool(self._pending)

    def compare_and_set_key(self, key, expected, value):
        """Commit one descriptive namespace iff the displayed snapshot is current.

        The comparison is inside the existing cross-process writer lock. Other
        namespaces, including concurrent playback history, are always merged.
        A conflict never discards this writer's pending operations.
        """
        with _writer_lock(self._database_path):
            latest = _read(self._database_path)
            for operation in self._pending:
                self._apply(latest, operation)
            if latest.get(key) != expected:
                return False
            latest[key] = copy.deepcopy(value)
            _atomic_save(self._database_path, latest)
            self._database, self._pending = latest, []
            return True

    def file_report(self, key, subkey, value, *, observation=None):
        return self._queue(('file_report', key, subkey, (value, observation)), True)

    def file_report_result(self, key, subkey, value, *, observation=None):
        """Result of this call only, after the existing atomic commit.

        Failed operations keep the legacy pending journal, but a later replay
        does not revive this call's result or authorize any external action.
        """
        operation = self._stage(('file_report', key, subkey, (value, observation)))
        return self._commit(observed=operation)[1]

    def begin_file_session(self, key, subkey, transform, limit=500):
        """Reserve ordering before playback, using the existing atomic store.

        No callback or network work belongs here. A failed reservation never
        changes the in-memory record or discards pending legacy operations.
        """
        with _writer_lock(self._database_path):
            latest = _read(self._database_path)
            for operation in self._pending:
                self._apply(latest, operation)
            rows = latest.setdefault(key, {})
            if type(rows) is not dict:
                raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
            value = transform(copy.deepcopy(rows.get(subkey)))
            rows[subkey] = copy.deepcopy(value)
            if len(rows) > limit:
                oldest = sorted((k for k in rows if k != subkey),
                    key=lambda k: rows[k].get('updated_at', 0) if type(rows[k]) is dict else 0)
                for identifier in oldest[:len(rows) - limit]:
                    del rows[identifier]
            # Also collect orphans left by an older, v1-only program. Retention
            # is owned by the bounded history rows, never by another cache.
            facts = latest.get(key + ':playback_start')
            if type(facts) is dict:
                for identifier in tuple(facts):
                    if identifier not in rows:
                        del facts[identifier]
            _atomic_save(self._database_path, latest)
            self._database, self._pending = latest, []
            return copy.deepcopy(value)

    def get_item(self, key: str, subkey: str):
        self._reload()
        return copy.deepcopy(self._database.get(key, {}).get(subkey))

    def delete_item(self, key: str, subkey: str, commit: bool = True):
        return self._queue(("delete", key, subkey, None), commit)

    def delete_item_if(self, key, subkey, expected, commit=True):
        """Remove only the snapshot the user saw, preserving concurrent playback."""
        return self._queue(("delete_if", key, subkey, expected), commit)

    def set_key(self, key: str, value, commit: bool = True):
        return self._queue(("key", key, None, value), commit)

    def get_key(self, key: str):
        self._reload()
        return copy.deepcopy(self._database.get(key))

    def get_key_checked(self, key: str):
        """Read the same snapshot without presenting unavailable data as empty."""
        if not self._reload():
            raise OSError('History unavailable')
        return copy.deepcopy(self._database.get(key))

    def get_keys_checked(self, keys):
        """One disk snapshot for mixed title/file history and home previews."""
        if not self._reload():
            raise OSError('History unavailable')
        return {key: copy.deepcopy(self._database.get(key)) for key in keys}

    def commit(self):
        return self._commit()[0]

    def _commit(self, observed=None):
        """One merge/save; optionally observe one exact pending operation.

        Acceptance is measured under the process lock, not inferred from an
        equal row read afterwards. No callbacks or network IO belong here.
        """
        if not self._pending:
            return True, 'ignored_stale'
        try:
            with _writer_lock(self._database_path):
                latest = _read(self._database_path)
                accepted, superseded = False, False
                for operation in self._pending:
                    changed = self._apply(latest, operation)
                    if operation is observed:
                        accepted = changed is True
                    elif accepted and changed and operation[1] == observed[1] and (
                            operation[0] == 'key' or operation[2] == observed[2]):
                        superseded = True
                disposition = 'ignored_stale'
                if accepted:
                    value = observed[3][0] if type(observed[3]) is tuple else observed[3]
                    disposition = ('superseded_in_commit' if superseded or
                        latest.get(observed[1], {}).get(observed[2]) != value else 'applied')
                _atomic_save(self._database_path, latest)
                self._database = latest
                self._pending.clear()
            return True, disposition
        except Exception as error:
            logging.getLogger(__name__).warning("History save deferred; original preserved: %s", type(error).__name__)
            return False, 'failed'

    @property
    def database(self):
        """A snapshot, not a mutable handle bypassing the operation journal."""
        self._reload()
        return copy.deepcopy(self._database)
