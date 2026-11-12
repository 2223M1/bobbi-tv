"""Real SQLite regressions for opening an initialized registry without writes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict
import json
import sqlite3
from threading import Barrier

import pytest

from bobbi_platform import libraries
from bobbi_platform.libraries import LibraryError, Registry, vfs_source


CONNECT = sqlite3.connect
SCHEMA = {
    'sources': 'id TEXT PRIMARY KEY, record TEXT NOT NULL',
    'metadata': 'key TEXT PRIMARY KEY, value TEXT NOT NULL',
    'pan_directories': 'id TEXT PRIMARY KEY, record TEXT NOT NULL',
}
SOURCE = vfs_source('Read contention fixture', 'smb://nas.example/Movies/',
                    source_id='1' * 32)
WRITE_ACTIONS = frozenset(getattr(sqlite3, name) for name in (
    'SQLITE_INSERT', 'SQLITE_UPDATE', 'SQLITE_DELETE',
    'SQLITE_CREATE_INDEX', 'SQLITE_CREATE_TABLE', 'SQLITE_CREATE_TEMP_INDEX',
    'SQLITE_CREATE_TEMP_TABLE', 'SQLITE_CREATE_TEMP_TRIGGER',
    'SQLITE_CREATE_TEMP_VIEW', 'SQLITE_CREATE_TRIGGER', 'SQLITE_CREATE_VIEW',
    'SQLITE_DROP_INDEX', 'SQLITE_DROP_TABLE', 'SQLITE_DROP_TEMP_INDEX',
    'SQLITE_DROP_TEMP_TABLE', 'SQLITE_DROP_TEMP_TRIGGER', 'SQLITE_DROP_TEMP_VIEW',
    'SQLITE_DROP_TRIGGER', 'SQLITE_DROP_VIEW', 'SQLITE_ALTER_TABLE',
    'SQLITE_REINDEX', 'SQLITE_ANALYZE',
))


def _create_db(path, *, version=1, tables=None, overrides=None):
    """Seed independently of Registry so a constructor regression is observable."""
    definitions = dict(SCHEMA if tables is None else
                       ((name, SCHEMA[name]) for name in tables))
    definitions.update(overrides or {})
    with closing(CONNECT(str(path))) as db, db:
        assert db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
        for name, columns in definitions.items():
            db.execute('CREATE TABLE {} ({})'.format(name, columns))
        if definitions.get('sources') == SCHEMA['sources']:
            db.execute('INSERT INTO sources VALUES (?, ?)',
                       (SOURCE.id, json.dumps(asdict(SOURCE))))
        if definitions.get('metadata') == SCHEMA['metadata']:
            db.execute('INSERT INTO metadata VALUES (?, ?)', ('fixture', 'preserve'))
        db.execute('PRAGMA user_version={}'.format(version))


def _assert_source_readable(path):
    with closing(Registry(path)) as store:
        assert store.get(SOURCE.id) == SOURCE
        assert store.sources() == (SOURCE,)
        assert store.directories() == ()


def _deny_writes(events):
    def authorize(action, first, second, _database, _origin):
        if (action in WRITE_ACTIONS or
                action == sqlite3.SQLITE_PRAGMA and
                str(first).lower() == 'user_version' and second is not None):
            events.append((action, first, second))
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorize


@pytest.mark.parametrize('statement', [
    'CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, record TEXT NOT NULL)',
    'PRAGMA user_version=1',
])
def test_read_guard_rejects_even_redundant_schema_writes(tmp_path, statement):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path)
    events = []
    with closing(CONNECT(str(path))) as db:
        db.set_authorizer(_deny_writes(events))
        assert db.execute('SELECT id FROM sources').fetchone()[0] == SOURCE.id
        with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
            db.execute(statement)
    assert events, 'The negative control must actually reach the write guard.'


def test_initialized_registry_opens_without_schema_or_version_writes(tmp_path, monkeypatch):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path)
    before = path.read_bytes()
    events = []

    def guarded_connect(*args, **kwargs):
        db = CONNECT(*args, **kwargs)
        db.set_authorizer(_deny_writes(events))
        return db

    monkeypatch.setattr(libraries.sqlite3, 'connect', guarded_connect)
    _assert_source_readable(path)
    assert events == []
    assert path.read_bytes() == before


@pytest.mark.parametrize('transaction', ['BEGIN IMMEDIATE', 'BEGIN'])
def test_initialized_registry_reads_while_another_connection_holds_lock(tmp_path, transaction):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path)
    with closing(CONNECT(str(path))) as holder:
        holder.execute(transaction)
        # BEGIN alone is deferred; this SELECT establishes a real shared lock.
        assert holder.execute('SELECT id FROM sources').fetchone()[0] == SOURCE.id
        with closing(CONNECT(str(path), timeout=0.01)) as probe:
            assert probe.execute('SELECT id FROM sources').fetchone()[0] == SOURCE.id
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                probe.execute('PRAGMA user_version=1')
        _assert_source_readable(path)
        assert holder.in_transaction
        holder.rollback()


def test_multiple_registry_readers_share_a_reserved_writer_lock(tmp_path):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path)
    readers = 6
    start = Barrier(readers)

    def read():
        start.wait(timeout=10)
        _assert_source_readable(path)
        return True

    with closing(CONNECT(str(path))) as holder:
        holder.execute('BEGIN IMMEDIATE')
        assert holder.execute('SELECT id FROM sources').fetchone()[0] == SOURCE.id
        with ThreadPoolExecutor(max_workers=readers) as pool:
            futures = [pool.submit(read) for _ in range(readers)]
            assert [future.result(timeout=10) for future in futures] == [True] * readers
        assert holder.in_transaction
        holder.rollback()


def test_first_open_initializes_the_registry(tmp_path):
    path = tmp_path / 'profile' / 'libraries.sqlite3'
    with closing(Registry(path)) as store:
        assert store.sources() == ()
        assert store.directories() == ()
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 1
        store.save(SOURCE)
    _assert_source_readable(path)


@pytest.mark.parametrize('tables', [(), ('sources',), ('sources', 'metadata'), tuple(SCHEMA)])
def test_version_zero_initializes_missing_tables_and_preserves_existing_rows(tmp_path, tables):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, version=0, tables=tables)
    with closing(Registry(path)) as store:
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert store.sources() == ((SOURCE,) if 'sources' in tables else ())
        assert store.directories() == ()
        if 'metadata' in tables:
            assert store.db.execute("SELECT value FROM metadata WHERE key='fixture'").fetchone() == ('preserve',)
        else:
            assert store.db.execute('SELECT * FROM metadata').fetchall() == []


def test_version_one_extends_only_missing_optional_pan_directories(tmp_path):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, tables=('sources', 'metadata'))
    _assert_source_readable(path)
    with closing(CONNECT(str(path))) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute("SELECT value FROM metadata WHERE key='fixture'").fetchone() == ('preserve',)
        assert db.execute('PRAGMA table_info(pan_directories)').fetchall() == [
            (0, 'id', 'TEXT', 0, None, 1), (1, 'record', 'TEXT', 1, None, 0)]


@pytest.mark.parametrize('version', [2, 99])
def test_unknown_storage_version_is_rejected_without_rewriting(tmp_path, version):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, version=version)
    before = path.read_bytes()
    with pytest.raises(LibraryError, match='UNKNOWN_STORAGE_VERSION'):
        Registry(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('missing', ['sources', 'metadata'])
def test_version_one_missing_required_table_is_rejected_without_repair(tmp_path, missing):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, tables=tuple(name for name in SCHEMA if name != missing))
    before = path.read_bytes()
    with pytest.raises(LibraryError):
        Registry(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('version', [0, 1])
@pytest.mark.parametrize('table,columns', [
    ('sources', 'id TEXT PRIMARY KEY'),
    ('sources', 'id TEXT, record TEXT NOT NULL'),
    ('sources', 'id TEXT PRIMARY KEY, record TEXT'),
    ('sources', 'id TEXT PRIMARY KEY, record BLOB NOT NULL'),
    ('sources', 'id TEXT PRIMARY KEY, record TEXT NOT NULL, extra TEXT'),
    ('metadata', 'key TEXT PRIMARY KEY'),
    ('metadata', 'key TEXT, value TEXT NOT NULL'),
    ('metadata', 'key TEXT PRIMARY KEY, value TEXT'),
    ('metadata', 'key TEXT PRIMARY KEY, value INTEGER NOT NULL'),
    ('metadata', 'key TEXT PRIMARY KEY, value TEXT NOT NULL, extra TEXT'),
    ('pan_directories', 'id TEXT PRIMARY KEY'),
    ('pan_directories', 'id TEXT, record TEXT NOT NULL'),
    ('pan_directories', 'id TEXT PRIMARY KEY, record TEXT'),
    ('pan_directories', 'id TEXT PRIMARY KEY, record BLOB NOT NULL'),
    ('pan_directories', 'id TEXT PRIMARY KEY, record TEXT NOT NULL, extra TEXT'),
])
def test_malformed_existing_table_is_rejected_without_repair(tmp_path, version, table, columns):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, version=version, overrides={table: columns})
    before = path.read_bytes()
    with pytest.raises(LibraryError):
        Registry(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('table', tuple(SCHEMA))
def test_view_cannot_impersonate_a_required_table(tmp_path, table):
    path = tmp_path / 'libraries.sqlite3'
    _create_db(path, tables=tuple(name for name in SCHEMA if name != table))
    first, second = ('key', 'value') if table == 'metadata' else ('id', 'record')
    with closing(CONNECT(str(path))) as db, db:
        db.execute("CREATE VIEW {} AS SELECT '' AS {}, '' AS {}".format(table, first, second))
    before = path.read_bytes()
    with pytest.raises(LibraryError):
        Registry(path)
    assert path.read_bytes() == before
