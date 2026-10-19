"""Legacy history format with atomic, operation-merged cross-process writes.

Kodi runs several plugin interpreters. A stale in-memory dictionary must not
erase newer entries, and readers must never see a truncated file during save.
"""
import copy
import os
import pickle
import tempfile
import threading
import time
from contextlib import contextmanager

import xbmcvfs

from lib.jacktook.utils import kodilog
from lib.utils.kodi.utils import ADDON_ID


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
    def __init__(self):
        data_dir = xbmcvfs.translatePath(os.path.join("special://profile/addon_data/", ADDON_ID))
        self._database_path = os.path.join(data_dir, "database.pickle")
        xbmcvfs.mkdirs(data_dir)
        self._pending = []
        self._database = {key: {} for key in _BASE_KEYS}
        self._reload()
        self.addon_xml_path = xbmcvfs.translatePath(
            os.path.join("special://home/addons/", ADDON_ID, "addon.xml")
        )

    def _reload(self):
        try:
            self._database = _read(self._database_path)
        except Exception as error:
            # Unreadable history is not evidence that nothing was watched.
            # The original stays untouched; commit also fails closed.
            kodilog("History read unavailable; original preserved: " + type(error).__name__)
        for operation in self._pending:
            self._apply(self._database, operation)

    @staticmethod
    def _apply(database, operation):
        action, key, subkey, value = operation
        if action == "key":
            database[key] = copy.deepcopy(value)
        elif action == "set":
            database.setdefault(key, {})[subkey] = copy.deepcopy(value)
        elif action == "delete":
            database.get(key, {}).pop(subkey, None)
        elif action == "delete_if" and database.get(key, {}).get(subkey) == value:
            database.get(key, {}).pop(subkey, None)

    def _queue(self, operation, commit):
        self._pending.append(copy.deepcopy(operation))
        self._apply(self._database, operation)
        if commit:
            return self.commit()

    def set_item(self, key: str, subkey: str, value, commit: bool = True):
        return self._queue(("set", key, subkey, value), commit)

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

    def commit(self):
        if not self._pending:
            return True
        try:
            with _writer_lock(self._database_path):
                latest = _read(self._database_path)
                for operation in self._pending:
                    self._apply(latest, operation)
                _atomic_save(self._database_path, latest)
                self._database = latest
                self._pending.clear()
            return True
        except Exception as error:
            kodilog("History save deferred; original preserved: " + type(error).__name__)
            return False

    @property
    def database(self):
        """A snapshot, not a mutable handle bypassing the operation journal."""
        self._reload()
        return copy.deepcopy(self._database)
