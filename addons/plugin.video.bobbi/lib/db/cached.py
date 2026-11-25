import os
import pickle
import sqlite3
import sys
import threading
import traceback
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import xbmc
import xbmcaddon
import xbmcgui

from lib.jacktook.utils import kodilog

PY3 = sys.version_info.major >= 3
if PY3:
    from xbmcvfs import translatePath
else:
    from xbmc import translatePath

ADDON_DATA = translatePath(xbmcaddon.Addon("plugin.video.bobbi").getAddonInfo("profile"))
ADDON_ID = xbmcaddon.Addon().getAddonInfo("id")

if not PY3:
    ADDON_DATA = ADDON_DATA.decode("utf-8")

# Independent home widgets import this module concurrently on first launch.
os.makedirs(ADDON_DATA, exist_ok=True)

SQLITE_SETTINGS = {
    "journal_mode": "wal",
    "auto_vacuum": "full",
    "cache_size": 8 * 1024,
    "mmap_size": 64 * 1024 * 1024,
    "synchronous": "normal",
}

PERSISTENT_SOURCE_CONFIG_KEYS = (
    "stremio_user_addons",
    "stremio_addons",
    "stremio_catalog_addons",
    "stremio_tv_addons",
    "stremio_subtitle_addons",
    "stremio_bypass_addons",
    "stremio_bypass_addon_list",
    "stremio_addon_aliases",
    "stremio_catalog_aliases",
    "torrentio.providers",
    "nuvio_user_addons",
    "nuvio_addons",
)


def utc_now():
    """Return the current UTC time in the cache's legacy naive format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def pickle_hash(obj):
    data = pickle.dumps(obj)
    h = sha256()
    h.update(data)
    return h.hexdigest()


class _BaseCache:
    __instance = None

    _load_func = staticmethod(pickle.loads)
    _dump_func = staticmethod(pickle.dumps)
    _hash_func = staticmethod(pickle_hash)

    def _live(self):
        if not self._revoked:
            try:
                if self._current() is not True:
                    self._revoked = True
            except Exception:
                self._revoked = True
        return not self._revoked

    def _require_current(self):
        if not self._live():
            raise RuntimeError('CACHE_PROFILE_REVOKED')

    @classmethod
    def get_instance(cls):
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

    def _get(self, key, default=None, hashed_key=False, identifier=""):
        result = self.get(self._generate_key(key, hashed_key, identifier))
        return result if result is not None else default

    def _set(self, key, data, expiry_time, hashed_key=False, identifier=""):
        if expiry_time == timedelta(0):
            return  # Do nothing, as it will expire immediately

        self.set(
            self._generate_key(key, hashed_key, identifier),
            data,
            expiry_time,
        )

    def close(self):
        pass

    def _generate_key(self, key, hashed_key=False, identifier=""):
        if not hashed_key:
            key = self._hash_func(key)
        if identifier:
            key += identifier
        return key

    def _process(self, obj):
        return obj

    def _prepare(self, s):
        return s


class RuntimeCache:
    _store = {}

    @classmethod
    def set(cls, key, value):
        cls._store[key] = value

    @classmethod
    def get(cls, key):
        return cls._store.get(key)

    @classmethod
    def delete(cls, key):
        if key in cls._store:
            del cls._store[key]

    @classmethod
    def clear(cls):
        cls._store.clear()


class MemoryCache(_BaseCache):
    # Fixed property names bound Kodi Window storage even when writers lose an
    # index update or are stopped between individual atomic property calls.
    _SLOTS = 1024

    def __init__(self, database=ADDON_ID, *, current=lambda: True):
        self._current, self._revoked = current, False
        self._window = xbmcgui.Window(10000)
        self._database = database + "."

    def _property_key(self, key):
        slot = int(sha256(key.encode("utf-8")).hexdigest(), 16) % self._SLOTS
        return self._database + "_L1_V304_" + str(slot)

    def _generation(self):
        return self._window.getProperty(self._database + "_GEN_V304_")

    def get(self, key, revision=None):
        if not self._live():
            return None
        generation = self._generation()
        data = self._window.getProperty(self._property_key(key))
        if data:
            try:
                stored_key, stored_generation, stored_revision, val, expires = self._load_func(b64decode(data))
                if (stored_key == key and stored_generation == generation
                        and stored_revision == revision and isinstance(expires, datetime)
                        and expires > utc_now()):
                    return val if self._live() else None
            except Exception:
                return None

    def set(self, key, data, expires=timedelta(hours=24)):
        self._set_until(key, data, utc_now() + expires)

    def _set_until(self, key, data, expiry_dt, revision=None):
        """Store an absolute expiry without extending a promoted disk entry."""
        if not self._live():
            return
        generation = self._generation()
        self._add_key_to_index(key)
        try:
            val_to_store = (key, generation, revision, data, expiry_dt)

            blob = self._dump_func(val_to_store)
            if not self._live():
                return
            self._window.setProperty(self._property_key(key), b64encode(blob).decode())
        except Exception as e:
            if not self._live():
                return
            self.delete(key)  # A failed overwrite must not leave the old L1 value.
            kodilog(
                f"[MemoryCache] Error storing key {key!r}: {e!s}",
                level=xbmc.LOGERROR,
            )
            kodilog(traceback.format_exc(), level=xbmc.LOGERROR)

    def delete(self, key):
        if not self._live():
            return
        self._remove_key_from_index(key)
        self._window.clearProperty(self._property_key(key))
        # One-release migration: never read legacy unversioned properties.
        self._window.clearProperty(self._database + key)

    def delete_like(self, pattern):
        # Use SQLite itself, including ASCII-only folding, Unicode codepoint
        # wildcards and NUL handling. Bounded local scan, no disk payload reads.
        matcher = sqlite3.connect(":memory:")
        try:
            for key in self._slot_keys():
                if matcher.execute("SELECT ? LIKE ?", (key, pattern)).fetchone()[0]:
                    self.delete(key)
        finally:
            matcher.close()

    def clean_all(self):
        if not self._live():
            return
        self._window.setProperty(self._database + "_GEN_V304_", os.urandom(16).hex())
        for slot in range(self._SLOTS):
            self._window.clearProperty(self._database + "_L1_V304_" + str(slot))
        keys = self._get_key_index()
        for k in keys:
            self._window.clearProperty(self._database + k)
        self._window.clearProperty(self._database + "_KEY_INDEX_")

    def _slot_keys(self):
        keys = []
        for slot in range(self._SLOTS):
            try:
                raw = self._window.getProperty(self._database + "_L1_V304_" + str(slot))
                if raw:
                    keys.append(self._load_func(b64decode(raw))[0])
            except Exception:
                pass
        return keys

    def _get_key_index(self):
        try:
            data = self._window.getProperty(self._database + "_KEY_INDEX_")
            if data:
                index = self._load_func(b64decode(data))
                if isinstance(index, (set, list, tuple)):
                    return {key for key in index if isinstance(key, str)}
        except Exception:
            pass
        return set()

    def _save_key_index(self, index):
        try:
            blob = self._dump_func(index)
            self._window.setProperty(self._database + "_KEY_INDEX_", b64encode(blob).decode())
        except Exception:
            pass

    def _add_key_to_index(self, key):
        # Compatibility hook; the bounded slot scan is authoritative. Keeping
        # an unbounded best-effort set would reintroduce a storage leak.
        self._get_key_index()

    def _remove_key_from_index(self, key):
        pass


class HybridCache(_BaseCache):
    def __init__(self, database=None, *, current=lambda: True, strict_reads=False):
        self._current, self._revoked = current, False
        self._strict_reads = strict_reads
        self._require_current()
        # Legacy callers keep their existing default. Search supplies one
        # captured absolute database, including a profile-specific L1 namespace.
        if database is not None:
            path = Path(database)
            if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
                raise ValueError('CACHE_PRIVATE_DATABASE_REQUIRED')
        namespace = ADDON_ID if database is None else ADDON_ID + '.' + sha256(os.fsencode(database)).hexdigest()
        self.memory = MemoryCache(namespace, current=self._live)
        self.db = SQLiteCache(current=self._live, **({} if database is None else {'database': database}))

    def get(self, key):
        if not self._live():
            return None
        # One indexed singleton SELECT, never a payload read on a healthy L1
        # hit. SQLite commits are the cross-interpreter invalidation authority.
        revision = self.db._revision()
        if self._strict_reads and (revision is None or key in self.db._object_store):
            raise RuntimeError('CACHE_AUTHORITY_UNAVAILABLE')
        if key in self.db._object_store:
            return self.db.get(key)  # failed writes are explicitly local only
        # L1: Memory
        data = self.memory.get(key, revision) if revision is not None else None
        if data is not None:
            return data if self._live() else None

        # L2: Database
        entry = self.db._get_with_expiry(key, strict=self._strict_reads)
        if entry is not None:
            data, expires = entry
            if revision is not None and entry.shared:
                self.memory._set_until(key, data, min(expires, utc_now() + timedelta(minutes=30)), revision)
            return data if self._live() else None
        return None

    def set(self, key, data, expires=timedelta(hours=24)):
        if not self._live():
            return
        # One deadline covers both writes, including time spent serializing L1.
        expiry_dt = utc_now() + expires
        revision = self.db._set_until(key, data, expiry_dt)
        self.memory.delete(key)
        # The token was captured in the same SQLite write transaction.
        if revision is not None:
            self.memory._set_until(key, data, expiry_dt, revision)

    def delete(self, key):
        self.memory.delete(key)
        self.db.delete(key)

    def add_to_list(self, key, item, expires):
        existing_data = self.get_list(key)
        if item in existing_data:
            existing_data.remove(item)
        existing_data.append(item)
        self.set(key, existing_data, expires)

    def get_list(self, key):
        result = self.get(key)
        if result:
            seen = set()
            deduped = []
            for item in reversed(result):
                t = tuple(item)
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            deduped.reverse()
            return deduped
        return []

    def clear_list(self, key):
        self.set(key, [], expires=timedelta(seconds=1))

    def clean_all(self):
        self.db.clean_all()
        self.memory.clean_all()

    def delete_like(self, pattern):
        self.memory.delete_like(pattern)
        self.db.delete_like(pattern)

    def close(self):
        self._revoked = True
        self.db.close()


class SQLiteCache(_BaseCache):
    class _Entry(tuple):
        def __new__(cls, data, expires, shared=True):
            entry = tuple.__new__(cls, (data, expires))
            entry.shared = shared
            return entry

    def __init__(
        self,
        database=os.path.join(ADDON_DATA, ADDON_ID + ".cached.sqlite"),
        cleanup_interval=timedelta(minutes=15),
        *, current=lambda: True,
    ):
        self._current, self._revoked = current, False
        self._require_current()
        self._conn = sqlite3.connect(
            database,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            check_same_thread=False,
        )
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = utc_now()
        self._object_store = {}
        self._lock = threading.Lock()
        try:
            self._initialize_connection()
        except BaseException:
            self._conn.close()
            raise

    def _initialize_connection(self):
        for k, v in SQLITE_SETTINGS.items():
            self._require_current()
            self._conn.execute(f"PRAGMA {k}={v}")
        self._require_current()
        self._conn.execute('BEGIN IMMEDIATE')
        self._require_current()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS `cached` ("
            "key TEXT PRIMARY KEY NOT NULL, "
            "data BLOB NOT NULL, "
            "expires TIMESTAMP NOT NULL"
            ")"
        )
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache_revision ("
                           "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                           "identity TEXT NOT NULL, revision INTEGER NOT NULL)")
        if not self._conn.execute("SELECT 1 FROM cache_revision WHERE singleton=1").fetchone():
            self._conn.execute("INSERT OR IGNORE INTO cache_revision VALUES(1, lower(hex(randomblob(16))), 0)")
        for operation in ("INSERT", "UPDATE", "DELETE"):
            self._conn.execute("CREATE TRIGGER IF NOT EXISTS cached_revision_" + operation.lower()
                               + " AFTER " + operation + " ON cached BEGIN "
                               "UPDATE cache_revision SET revision=revision+1 WHERE singleton=1; END")
        self._require_current()
        self._conn.commit()
        # Every widget/service imports this cache. Do not compete for a delete
        # transaction at startup; reads independently enforce expiry below.

    def _mutate(self, sql, parameters=()):
        """Fence maintenance/invalidation as well as normal cache publication."""
        try:
            self._require_current()
            self._conn.execute('BEGIN IMMEDIATE')
            self._require_current()
            self._conn.execute(sql, parameters)
            self._require_current()
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def _revision(self):
        with self._lock:
            if not self._live():
                return None
            try:
                return self._conn.execute("SELECT identity, revision FROM cache_revision WHERE singleton=1").fetchone()
            except Exception:
                return None  # unavailable authority must never accept shared L1

    def _process(self, obj):
        return self._load_func(obj)

    def _prepare(self, s):
        return self._dump_func(s)

    def add_to_list(self, key, item, expires):
        """Append an item to a list stored under the given key."""
        existing_data = self.get_list(key)
        if item in existing_data:
            existing_data.remove(item)
        existing_data.append(item)
        self.set(
            key,
            existing_data,
            expires,
        )

    def get_list(self, key):
        """Retrieve the list stored under the given key."""
        result = self.get(key)
        if result:
            seen = set()
            deduped = []
            for item in reversed(result):
                t = tuple(item)
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            deduped.reverse()
            return deduped
        return []

    def get(self, key):
        entry = self._get_with_expiry(key)
        return entry[0] if entry is not None else None

    def _get_with_expiry(self, key, *, strict=False):
        """Read value and absolute expiry together for bounded L1 promotion."""
        with self._lock:
            if not self._live():
                return None
            if key in self._object_store:
                data, expires = self._object_store[key]
                if expires > utc_now():
                    return self._Entry(data, expires, shared=False)
                else:
                    # A failed overwrite may have left a longer-lived old disk
                    # row. Retain a small tombstone until a successful mutation
                    # removes it, so a later read cannot revive that old value.
                    self._object_store[key] = (None, expires)
                    return None
            self.check_clean_up()
            try:
                result = self._conn.execute(
                    "SELECT data, CAST(expires AS TEXT) FROM `cached` WHERE key = ?", (key,)
                ).fetchone()
            except Exception as e:
                if strict:
                    raise RuntimeError('CACHE_READ_UNAVAILABLE') from e
                kodilog(f"SQL error for key {key!r}: {e}", level=xbmc.LOGERROR)
                kodilog(traceback.format_exc(), level=xbmc.LOGERROR)
                return None
            if result:
                try:
                    data, raw_expiry = result
                    expires = datetime.fromisoformat(raw_expiry)
                    if expires > utc_now():
                        value = self._process(data)
                        return self._Entry(value, expires) if self._live() else None
                except Exception as error:
                    if strict:
                        raise RuntimeError('CACHE_VALUE_UNAVAILABLE') from error
                    # No key, payload, exception text or traceback: unpickling
                    # errors can contain user/provider data. Only this row dies.
                    kodilog("Invalid cache row: " + type(error).__name__, level=xbmc.LOGWARNING)
                    try:
                        self._require_current()
                        self._mutate("DELETE FROM cached WHERE key=? AND data=? AND CAST(expires AS TEXT)=?",
                                     (key, data, raw_expiry))
                    except Exception:
                        pass
            return None

    def set(self, key, data, expires):
        self._set_until(key, data, utc_now() + expires)

    def _set_until(self, key, data, expiry_dt):
        """Store the caller's absolute deadline, including a Hybrid L1 write."""
        with self._lock:
            try:
                self._require_current()
                self.check_clean_up()
                blob = sqlite3.Binary(self._prepare(data))
                self._require_current()
                self._conn.execute("BEGIN IMMEDIATE")
                self._require_current()
                self._conn.execute(
                    "INSERT OR REPLACE INTO `cached` (key, data, expires) VALUES(?, ?, ?)",
                    (
                        key,
                        blob,
                        expiry_dt,
                    ),
                )
                revision = self._conn.execute("SELECT identity, revision FROM cache_revision WHERE singleton=1").fetchone()
                self._require_current()
                self._conn.commit()
                self._object_store.pop(key, None)
                kodilog(
                    f"Set cache for key '{key}' until {expiry_dt}",
                    level=xbmc.LOGDEBUG,
                )
                return revision
            except Exception as e:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                if not self._live():
                    return None
                # Serialization can fail while SQLite is still writable. In
                # that case invalidate the old persistent value for other
                # connections too. A database that rejects writes may also
                # reject this deletion; only this instance's fallback is then
                # protected from stale disk values, not another interpreter.
                try:
                    self._require_current()
                    self._mutate("DELETE FROM `cached` WHERE key = ?", (key,))
                except Exception:
                    kodilog('Failed cache overwrite could not invalidate disk value', level=xbmc.LOGWARNING)
                kodilog(
                    f"Failed to set cache for key '{key}': {e!s}",
                    level=xbmc.LOGERROR,
                )
                # fallback to raw in‑memory store
                if self._live():
                    self._object_store[key] = (data, expiry_dt)

    def clear_list(self, key):
        """Clear the list stored under the given key."""
        self.set(key, [], timedelta(0))

    def delete(self, key):
        """Remove a single key from the SQLite store."""
        with self._lock:
            if not self._live():
                return
            self._mutate("DELETE FROM `cached` WHERE key = ?", (key,))
            self._object_store.pop(key, None)

    def delete_like(self, pattern):
        """Remove keys matching a pattern from the SQLite store."""
        with self._lock:
            if not self._live():
                return
            # Let SQLite apply exactly the same LIKE rules to fallback keys.
            keys = [key for key in self._object_store
                    if self._conn.execute("SELECT ? LIKE ?", (key, pattern)).fetchone()[0]]
            self._mutate("DELETE FROM `cached` WHERE key LIKE ?", (pattern,))
            for key in keys:
                self._object_store.pop(key, None)

    def _set_version(self, version):
        self._conn.execute(f"PRAGMA user_version={version}")

    @property
    def version(self):
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    @property
    def needs_cleanup(self):
        return self._last_cleanup + self._cleanup_interval < utc_now()

    def clean_up(self):
        if not self._live():
            return False
        try:
            self._mutate(
                "DELETE FROM `cached` WHERE expires <= STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW')"
            )
        except RuntimeError:
            if self._live():
                raise
            return False
        except sqlite3.OperationalError as error:
            code = getattr(error, 'sqlite_errorcode', 0) & 255
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            self._last_cleanup = utc_now()
            kodilog('Cache maintenance deferred: database busy', level=xbmc.LOGWARNING)
            return False
        self._last_cleanup = utc_now()
        return True

    def clean_all(self):
        preserved = (
            "stremio_user_addons",
            "stremio_addons",
            "stremio_catalog_addons",
            "stremio_tv_addons",
            "stremio_subtitle_addons",
            "stremio_bypass_addons",
            "stremio_bypass_addon_list",
            "stremio_addon_aliases",
            "stremio_catalog_aliases",
            "torrentio.providers",
            "nuvio_user_addons",
            "nuvio_addons",
        )
        quoted = ", ".join(f"'{k}'" for k in preserved)
        with self._lock:
            if not self._live():
                return
            self._mutate(f"DELETE FROM cached WHERE key NOT IN ({quoted})")
            for key in list(self._object_store):
                if key not in preserved:
                    self._object_store.pop(key, None)

    def check_clean_up(self):
        clean_up = self.needs_cleanup
        if clean_up:
            self.clean_up()
        return clean_up

    def close(self):
        with self._lock:
            self._revoked = True
            self._conn.close()


cache = HybridCache()
