import ast
import json
from hashlib import sha256
from threading import RLock

from lib.api.trakt.base_cache import connect_database
from lib.utils.kodi.settings import EMPTY_USER
from lib.utils.kodi.utils import get_property, get_setting, kodilog

SELECT = "SELECT id FROM trakt_data"
DELETE = "DELETE FROM trakt_data WHERE id=?"
DELETE_LIKE = 'DELETE FROM trakt_data WHERE id LIKE "%s"'
WATCHED_INSERT = "INSERT OR IGNORE INTO watched VALUES (?, ?, ?, ?, ?, ?)"
WATCHED_DELETE = "DELETE FROM watched WHERE db_type = ?"
PROGRESS_INSERT = "INSERT OR IGNORE INTO progress VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
PROGRESS_DELETE = "DELETE FROM progress WHERE db_type = ?"
STATUS_INSERT = "INSERT INTO watched_status VALUES (?, ?, ?)"
STATUS_DELETE = "DELETE FROM watched_status"
BASE_DELETE = "DELETE FROM %s"
TC_BASE_GET = "SELECT data FROM trakt_data WHERE id = ?"
TC_BASE_SET = "INSERT OR REPLACE INTO trakt_data (id, data) VALUES (?, ?)"
TC_BASE_DELETE = "DELETE FROM trakt_data WHERE id = ?"
TRAKT_CACHE_OWNER_KEY = "trakt_cache_owner"
MAX_TRAKT_LEGACY_LITERAL_SIZE = 128 * 1024  # Bound Python AST expansion for repr rows.
MAX_TRAKT_JSON_ROW_SIZE = 512 * 1024  # About 2x the measured 1,000-row normalized cache.

_TRAKT_DB_LOCK = RLock()


def _active_trakt_user():
    try:
        user = get_setting("trakt_user")
    except Exception:
        return None
    if not isinstance(user, str):
        return None
    normalized = user.strip()
    if not normalized or normalized == EMPTY_USER:
        return None
    return normalized


def trakt_account_scope():
    """Capture the login before IO; never persist or log its credential."""
    token = get_property('trakt_token')
    fingerprint = sha256(token.encode()).digest() if isinstance(token, str) else None
    return _active_trakt_user(), fingerprint


def trakt_account_current(scope):
    return scope is None or scope == trakt_account_scope()


def _has_table(dbcon, table_name):
    try:
        row = dbcon.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _stored_cache_owner(dbcon):
    if not _has_table(dbcon, "trakt_data"):
        return None
    try:
        row = dbcon.execute(TC_BASE_GET, (TRAKT_CACHE_OWNER_KEY,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    owner = _decode_cache_value(row[0], TRAKT_CACHE_OWNER_KEY, str)
    return owner.strip() if isinstance(owner, str) and owner.strip() else None


def _owner_matches_active_user(dbcon):
    active = _active_trakt_user()
    if active is None:
        return True
    stored = _stored_cache_owner(dbcon)
    return stored is None or stored == active


def _ensure_rollback_journal(dbcon):
    if not getattr(dbcon, "in_transaction", False):
        try:
            dbcon.execute("PRAGMA journal_mode = MEMORY")
        except Exception:
            pass


def _sync_owner_in_tx(dbcon, explicit_user=None):
    active = explicit_user.strip() if isinstance(explicit_user, str) and explicit_user.strip() else _active_trakt_user()
    if active is None or active == EMPTY_USER or not _has_table(dbcon, "trakt_data"):
        return
    stored = _stored_cache_owner(dbcon)
    if stored is not None and stored != active:
        for table in ("watched", "progress", "watched_status", "trakt_data"):
            if _has_table(dbcon, table):
                dbcon.execute(f"DELETE FROM {table}")
    if stored != active:
        encoded_owner = _encode_cache_value(active, TRAKT_CACHE_OWNER_KEY)
        if encoded_owner is not None:
            dbcon.execute(TC_BASE_SET, (TRAKT_CACHE_OWNER_KEY, encoded_owner))


class TraktCache:
    def get(self, string, expected_type, item_type=None):
        result = None
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                if not _owner_matches_active_user(dbcon):
                    return None
                cache_data = dbcon.execute(TC_BASE_GET, (string,)).fetchone()
                if cache_data:
                    result = _decode_cache_value(
                        cache_data[0], string, expected_type, item_type=item_type
                    )
        except Exception:
            pass
        return result

    def set(self, string, data):
        if data is None:
            return None
        try:
            encoded = _encode_cache_value(data, string)
            if encoded is None:
                return None
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                _ensure_rollback_journal(dbcon)
                dbcon.execute("BEGIN IMMEDIATE")
                try:
                    _sync_owner_in_tx(dbcon)
                    dbcon.execute(TC_BASE_SET, (string, encoded))
                    dbcon.execute("COMMIT")
                except BaseException:
                    try:
                        dbcon.execute("ROLLBACK")
                    except Exception:
                        pass
                    raise
        except Exception:
            return None

    def delete(self, string):
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                dbcon.execute(TC_BASE_DELETE, (string,))
        except Exception:
            pass

    def clear_all(self):
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                dbcon.execute("DELETE FROM trakt_data")
                dbcon.execute("VACUUM")
        except Exception:
            pass


trakt_cache = TraktCache()


class TraktWatched:
    def bind_account(self, username):
        if not isinstance(username, str) or not username.strip() or username.strip() == EMPTY_USER:
            return
        with _TRAKT_DB_LOCK:
            dbcon = connect_database("trakt_db")
            _ensure_rollback_journal(dbcon)
            dbcon.execute("BEGIN IMMEDIATE")
            try:
                _sync_owner_in_tx(dbcon, explicit_user=username.strip())
                dbcon.execute("COMMIT")
            except BaseException:
                try:
                    dbcon.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def _replace_bucket(self, delete_command, delete_args, insert_command, insert_list, *, expected_scope=None):
        if insert_list is None:
            raise ValueError("Cannot replace Trakt bucket with unknown (None) snapshot")
        with _TRAKT_DB_LOCK:
            if not trakt_account_current(expected_scope):
                return False
            dbcon = connect_database("trakt_db")
            _ensure_rollback_journal(dbcon)
            dbcon.execute("BEGIN IMMEDIATE")
            try:
                _sync_owner_in_tx(dbcon, explicit_user=expected_scope[0] if expected_scope else None)
                dbcon.execute(delete_command, delete_args)
                dbcon.executemany(insert_command, insert_list)
                if not trakt_account_current(expected_scope):
                    dbcon.execute("ROLLBACK")
                    return False
                dbcon.execute("COMMIT")
                return True
            except BaseException:
                try:
                    dbcon.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def set_bulk_tvshow_status(self, insert_list):
        self._replace_bucket(STATUS_DELETE, (), STATUS_INSERT, insert_list)

    def set_tvshow_status(self, insert_dict):
        encoded = _encode_cache_value(insert_dict, "trakt_tvshow_status")
        if encoded is None:
            return
        with _TRAKT_DB_LOCK:
            dbcon = connect_database("trakt_db")
            _ensure_rollback_journal(dbcon)
            dbcon.execute("BEGIN IMMEDIATE")
            try:
                _sync_owner_in_tx(dbcon)
                dbcon.execute(
                    "INSERT OR REPLACE INTO trakt_data (id, data) VALUES (?, ?)",
                    (
                        "trakt_tvshow_status",
                        encoded,
                    ),
                )
                dbcon.execute("COMMIT")
            except BaseException:
                try:
                    dbcon.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def set_bulk_movie_watched(self, insert_list, *, expected_scope=None):
        return self._replace_bucket(WATCHED_DELETE, ("movie",), WATCHED_INSERT, insert_list, expected_scope=expected_scope)

    def set_bulk_tvshow_watched(self, insert_list, *, expected_scope=None):
        return self._replace_bucket(WATCHED_DELETE, ("episode",), WATCHED_INSERT, insert_list, expected_scope=expected_scope)

    def set_bulk_movie_progress(self, insert_list, *, expected_scope=None):
        return self._replace_bucket(PROGRESS_DELETE, ("movie",), PROGRESS_INSERT, insert_list, expected_scope=expected_scope)

    def set_bulk_tvshow_progress(self, insert_list, *, expected_scope=None):
        return self._replace_bucket(PROGRESS_DELETE, ("episode",), PROGRESS_INSERT, insert_list, expected_scope=expected_scope)

    def clear_all(self):
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                _ensure_rollback_journal(dbcon)
                dbcon.execute("BEGIN IMMEDIATE")
                try:
                    for table in ("watched", "progress", "watched_status"):
                        if _has_table(dbcon, table):
                            dbcon.execute(f"DELETE FROM {table}")
                    dbcon.execute("COMMIT")
                except BaseException:
                    try:
                        dbcon.execute("ROLLBACK")
                    except Exception:
                        pass
                    raise
        except Exception:
            pass

    def _executemany(self, command, insert_list):
        with _TRAKT_DB_LOCK:
            dbcon = connect_database("trakt_db")
            dbcon.executemany(command, insert_list)

    def _delete(self, command, args):
        with _TRAKT_DB_LOCK:
            dbcon = connect_database("trakt_db")
            dbcon.execute(command, args)

    def get_watched_status(self, db_type, media_id, season=None, episode=None):
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                if not _owner_matches_active_user(dbcon):
                    return False
                if db_type == "movie":
                    command = "SELECT 1 FROM watched WHERE db_type=? AND media_id=?"
                    args = (db_type, media_id)
                else:
                    command = "SELECT 1 FROM watched WHERE db_type=? AND media_id=? AND season=? AND episode=?"
                    args = (db_type, media_id, season, episode)

                result = dbcon.execute(command, args).fetchone()
                return result is not None
        except Exception:
            return False

    def get_progress(self, db_type, media_id, season=None, episode=None):
        try:
            with _TRAKT_DB_LOCK:
                dbcon = connect_database("trakt_db")
                if not _owner_matches_active_user(dbcon):
                    return 0.0
                if db_type == "movie":
                    command = "SELECT resume_point FROM progress WHERE db_type=? AND media_id=?"
                    args = (db_type, media_id)
                else:
                    command = "SELECT resume_point FROM progress WHERE db_type=? AND media_id=? AND season=? AND episode=?"
                    args = (db_type, media_id, season, episode)

                result = dbcon.execute(command, args).fetchone()
                if result:
                    return float(result[0])
                return 0.0
        except Exception:
            return 0.0


trakt_watched_cache = TraktWatched()


def cache_trakt_object(function, string, url, expected_type, item_type=None):
    cache = trakt_cache.get(string, expected_type, item_type=item_type)
    if cache:
        return cache
    result = function(url)
    if result is not None:
        trakt_cache.set(string, result)
    return result


def get_activity():
    string = "trakt_get_activity"
    try:
        with _TRAKT_DB_LOCK:
            dbcon = connect_database("trakt_db")
            if not _owner_matches_active_user(dbcon):
                return default_activities()
            data = dbcon.execute(TC_BASE_GET, (string,)).fetchone()
            if data:
                activity = _decode_cache_value(data[0], string, dict)
                if activity is not None and _matches_required_activity_shape(
                    activity, default_activities()
                ):
                    return activity
                if activity is not None:
                    kodilog(f"Unexpected Trakt activity row shape ignored: {string}")
    except Exception:
        pass
    return default_activities()


def set_activity(latest_activities, *, expected_scope=None):
    encoded = _encode_cache_value(latest_activities, "trakt_get_activity")
    if encoded is None:
        return
    with _TRAKT_DB_LOCK:
        if not trakt_account_current(expected_scope):
            return False
        dbcon = connect_database("trakt_db")
        _ensure_rollback_journal(dbcon)
        dbcon.execute("BEGIN IMMEDIATE")
        try:
            _sync_owner_in_tx(dbcon, explicit_user=expected_scope[0] if expected_scope else None)
            dbcon.execute(TC_BASE_SET, ("trakt_get_activity", encoded))
            if not trakt_account_current(expected_scope):
                dbcon.execute("ROLLBACK")
                return False
            dbcon.execute("COMMIT")
            return True
        except BaseException:
            try:
                dbcon.execute("ROLLBACK")
            except Exception:
                pass
            raise

def reset_activity(latest_activities):
    cached_data = get_activity()
    set_activity(latest_activities)
    return cached_data


def _decode_cache_value(raw_value, cache_key, expected_type, item_type=None):
    encoded_size = _encoded_cache_size(raw_value)
    if encoded_size is None:
        kodilog(f"Invalid Trakt cache row encoding ignored: {cache_key}")
        return None
    if encoded_size > MAX_TRAKT_JSON_ROW_SIZE:
        kodilog(f"Oversized or invalid Trakt cache row ignored: {cache_key}")
        return None

    decoded_from_json = False
    try:
        value = json.loads(raw_value)
        decoded_from_json = True
    except (
        UnicodeDecodeError,
        TypeError,
        ValueError,
        MemoryError,
        OverflowError,
        RecursionError,
    ):
        if encoded_size > MAX_TRAKT_LEGACY_LITERAL_SIZE:
            kodilog(f"Oversized legacy Trakt cache row ignored: {cache_key}")
            return None
        try:
            value = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError, TypeError, MemoryError, OverflowError, RecursionError):
            kodilog(f"Corrupt Trakt cache row ignored: {cache_key}")
            return None

    if expected_type is tuple:
        valid = (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and isinstance(value[0], list)
            and all(isinstance(item, dict) for item in value[0])
            and (value[1] is None or isinstance(value[1], dict))
        )
        if valid and decoded_from_json:
            value = (value[0], value[1])
    else:
        valid = isinstance(value, expected_type)
        if valid and item_type is not None:
            valid = all(isinstance(item, item_type) for item in value)
    if not valid:
        kodilog(f"Unexpected Trakt cache row type ignored: {cache_key}")
        return None
    return value


def _encoded_cache_size(raw_value):
    if isinstance(raw_value, bytes):
        return len(raw_value)
    if not isinstance(raw_value, str) or len(raw_value) > MAX_TRAKT_JSON_ROW_SIZE:
        return None if not isinstance(raw_value, str) else len(raw_value)
    try:
        return len(raw_value.encode("utf-8"))
    except UnicodeEncodeError:
        return None


def _encode_cache_value(value, cache_key):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, MemoryError, RecursionError):
        kodilog(f"Unsupported Trakt cache value not written: {cache_key}")
        return None
    if len(encoded) > MAX_TRAKT_JSON_ROW_SIZE:
        kodilog(f"Oversized Trakt cache value not written: {cache_key}")
        return None
    try:
        encoded_size = len(encoded.encode("utf-8"))
    except UnicodeEncodeError:
        kodilog(f"Invalid Trakt cache value encoding not written: {cache_key}")
        return None
    if encoded_size > MAX_TRAKT_JSON_ROW_SIZE:
        kodilog(f"Oversized Trakt cache value not written: {cache_key}")
        return None
    return encoded


def _matches_required_activity_shape(value, required):
    if not isinstance(value, dict):
        return False
    for key, required_value in required.items():
        if key not in value:
            return False
        actual_value = value[key]
        if isinstance(required_value, dict):
            if not _matches_required_activity_shape(actual_value, required_value):
                return False
        elif not isinstance(actual_value, type(required_value)):
            return False
    return True


def clear_trakt_hidden_data(list_type):
    string = f"trakt_hidden_items_{list_type}"
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE, (string,))
    except Exception:
        pass


def clear_trakt_collection_watchlist_data(list_type, media_type):
    if media_type == "movies":
        media_type = "movie"
    if media_type in ("tvshows", "shows"):
        media_type = "tvshow"
    string = f"trakt_{list_type}_{media_type}"
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE, (string,))
    except Exception:
        pass


def clear_trakt_list_contents_data(list_type):
    string = "trakt_list_contents_" + list_type + "_%"
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE_LIKE % string)
    except Exception:
        pass


def clear_trakt_list_data(list_type):
    string = f"trakt_{list_type}"
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE, (string,))
    except Exception:
        pass


def clear_trakt_calendar():
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE_LIKE % "trakt_get_my_calendar_%")
    except Exception:
        return


def clear_trakt_recommendations():
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE_LIKE % "trakt_recommendations_%")
    except Exception:
        return


def clear_trakt_favorites():
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE_LIKE % "trakt_favorites_%")
    except Exception:
        return


def clear_trakt_watchlist():
    """
    Clear the cached Trakt.tv watchlist.
    """
    try:
        dbcon = connect_database("trakt_db")
        dbcon.execute(DELETE_LIKE % "trakt_watchlist_%")
    except Exception:
        pass


def default_activities():
    return {
        "all": "2024-01-22T00:22:21.000Z",
        "movies": {
            "watched_at": "2020-01-01T00:00:01.000Z",
            "collected_at": "2020-01-01T00:00:01.000Z",
            "rated_at": "2020-01-01T00:00:01.000Z",
            "watchlisted_at": "2020-01-01T00:00:01.000Z",
            "favorited_at": "2020-01-01T00:00:01.000Z",
            "recommendations_at": "2020-01-01T00:00:01.000Z",
            "commented_at": "2020-01-01T00:00:01.000Z",
            "paused_at": "2020-01-01T00:00:01.000Z",
            "hidden_at": "2020-01-01T00:00:01.000Z",
        },
        "episodes": {
            "watched_at": "2020-01-01T00:00:01.000Z",
            "collected_at": "2020-01-01T00:00:01.000Z",
            "rated_at": "2020-01-01T00:00:01.000Z",
            "watchlisted_at": "2020-01-01T00:00:01.000Z",
            "commented_at": "2020-01-01T00:00:01.000Z",
            "paused_at": "2020-01-01T00:00:01.000Z",
        },
        "shows": {
            "rated_at": "2020-01-01T00:00:01.000Z",
            "watchlisted_at": "2020-01-01T00:00:01.000Z",
            "favorited_at": "2020-01-01T00:00:01.000Z",
            "recommendations_at": "2020-01-01T00:00:01.000Z",
            "commented_at": "2020-01-01T00:00:01.000Z",
            "hidden_at": "2020-01-01T00:00:01.000Z",
        },
        "seasons": {
            "rated_at": "2020-01-01T00:00:01.000Z",
            "watchlisted_at": "2020-01-01T00:00:01.000Z",
            "commented_at": "2020-01-01T00:00:01.000Z",
            "hidden_at": "2020-01-01T00:00:01.000Z",
        },
        "comments": {
            "liked_at": "2020-01-01T00:00:01.000Z",
            "blocked_at": "2020-01-01T00:00:01.000Z",
        },
        "lists": {
            "liked_at": "2020-01-01T00:00:01.000Z",
            "updated_at": "2020-01-01T00:00:01.000Z",
            "commented_at": "2020-01-01T00:00:01.000Z",
        },
        "watchlist": {"updated_at": "2020-01-01T00:00:01.000Z"},
        "favorites": {"updated_at": "2020-01-01T00:00:01.000Z"},
        "recommendations": {"updated_at": "2020-01-01T00:00:01.000Z"},
        "collaborations": {"updated_at": "2020-01-01T00:00:01.000Z"},
        "account": {
            "settings_at": "2020-01-01T00:00:01.000Z",
            "followed_at": "2020-01-01T00:00:01.000Z",
            "following_at": "2020-01-01T00:00:01.000Z",
            "pending_at": "2020-01-01T00:00:01.000Z",
            "requested_at": "2020-01-01T00:00:01.000Z",
        },
        "saved_filters": {"updated_at": "2020-01-01T00:00:01.000Z"},
        "notes": {"updated_at": "2020-01-01T00:00:01.000Z"},
    }
