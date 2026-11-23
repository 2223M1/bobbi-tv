"""User-owned Registry storage; pure source contracts live in core."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import secrets

# Compatibility imports are the same objects, not parallel validators/models.
from bobbi_core.library_contract import (
    MAX_CATALOG_BYTES, MAX_ITEMS, MAX_SOURCES, MAX_DIRECTORY_ITEMS,
    SCHEMES, VIDEO_EXTENSIONS, LibraryError, Item, Source,
    _text, _json, split_location, direct_url, validate_file_metadata,
    vfs_source, import_catalog, validate_source, relative_path,
    joined_path, directory_items,
)


class Registry:
    """SQLite serializes local UI edits; removal never contacts the source."""
    def __init__(self, path, *, read_only=False, timeout=1):
        self.path = Path(path)
        self.read_only = read_only
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise LibraryError('STORAGE_UNSAFE')
        self.db = None
        try:
            if read_only:
                # Owner-loop observation cannot initialize/migrate storage or
                # wait behind a writer. A busy/absent DB remains unknown.
                self.db = sqlite3.connect(self.path.absolute().as_uri() + '?mode=ro', uri=True, timeout=0)
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if not self.path.exists():
                    fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                self.db = sqlite3.connect(str(self.path), timeout=timeout)
                self.db.execute('PRAGMA secure_delete=ON')
            version, missing = self._schema()
            if version == 0 or missing:
                if read_only:
                    raise LibraryError('STORAGE_UNAVAILABLE')
                with self.db:
                    self.db.execute('BEGIN IMMEDIATE')
                    # Another opener may have initialized it while we waited.
                    version, missing = self._schema()
                    for name, key, value in missing:
                        self.db.execute('CREATE TABLE {} ({} TEXT PRIMARY KEY, {} TEXT NOT NULL)'.format(
                            name, key, value))
                    if version == 0:
                        self.db.execute('PRAGMA user_version=1')
        except LibraryError:
            if self.db is not None:
                self.db.close()
            raise
        except (OSError, sqlite3.Error):
            if self.db is not None:
                self.db.close()
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def _schema(self):
        """Validate locally without turning every scope/job read into a writer."""
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise LibraryError('UNKNOWN_STORAGE_VERSION')
        tables = dict(self.db.execute("SELECT name,type FROM sqlite_master WHERE name IN "
            "('sources','metadata','pan_directories')").fetchall())
        missing = []
        for name, key, value in (('sources', 'id', 'record'), ('metadata', 'key', 'value'),
                                 ('pan_directories', 'id', 'record')):
            if name not in tables:
                # The directory extension may be absent in an older v1 file;
                # missing core tables are not an empty registry to recreate.
                if version == 1 and name != 'pan_directories':
                    raise LibraryError('STORAGE_UNAVAILABLE')
                missing.append((name, key, value))
            elif (tables[name] != 'table' or
                  self.db.execute('PRAGMA table_info('+name+')').fetchall() != [
                      (0, key, 'TEXT', 0, None, 1), (1, value, 'TEXT', 1, None, 0)]):
                raise LibraryError('STORAGE_UNAVAILABLE')
        return version, missing

    def close(self):
        self.db.close()

    @staticmethod
    def _read(raw):
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_CATALOG_BYTES * 2:
            raise LibraryError('INVALID_SOURCE')
        value = _json(raw)
        try:
            if (not isinstance(value, dict)
                    or not {'id', 'name', 'kind', 'location', 'username', 'password', 'items'} <= set(value)
                    or set(value) - {'id', 'name', 'kind', 'location', 'username', 'password', 'items', 'metadata'}
                    or not isinstance(value['items'], list) or len(value['items']) > MAX_ITEMS):
                raise LibraryError('INVALID_SOURCE')
            value['items'] = tuple(Item(**item) for item in value['items'])
            return validate_source(Source(**value))
        except (TypeError, KeyError):
            raise LibraryError('INVALID_SOURCE') from None

    def sources(self):
        try:
            rows = self.db.execute('SELECT id, record FROM sources ORDER BY rowid LIMIT ?', (MAX_SOURCES + 1,)).fetchall()
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None
        if len(rows) > MAX_SOURCES:
            raise LibraryError('TOO_MANY_SOURCES')
        sources = []
        for source_id, raw in rows:
            source = self._read(raw)
            if source.id != source_id:
                raise LibraryError('INVALID_SOURCE')
            sources.append(source)
        return tuple(sources)

    def get(self, source_id):
        if not isinstance(source_id, str) or not re.fullmatch('[0-9a-f]{32}', source_id):
            raise LibraryError('SOURCE_NOT_FOUND')
        for source in self.sources():
            if source.id == source_id:
                return source
        raise LibraryError('SOURCE_NOT_FOUND')

    def save(self, source, expected_snapshot=None):
        source = validate_source(source)
        record = dict(source.__dict__, items=[item.__dict__ for item in source.items])
        raw = json.dumps(record, ensure_ascii=False)
        if len(raw.encode('utf-8')) > MAX_CATALOG_BYTES * 2:
            raise LibraryError('CATALOG_TOO_LARGE')
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                current = self.db.execute('SELECT id FROM sources').fetchall()
                if len(current) + len(self.directories()) >= MAX_SOURCES and source.id not in {row[0] for row in current}:
                    raise LibraryError('TOO_MANY_SOURCES')
                previous = self.db.execute('SELECT record FROM sources WHERE id=?', (source.id,)).fetchone()
                if expected_snapshot is not None:
                    revision = self.db.execute('SELECT value FROM metadata WHERE key=?',
                        ('source_revision:' + source.id,)).fetchone()
                    actual = (self._read(previous[0]) if previous else None, revision[0] if revision else None)
                    if actual != expected_snapshot:
                        raise LibraryError('CATALOG_AUTHORITY_CHANGED')
                if source.kind == 'media_server' and any(row.id != source.id and row.kind == 'media_server'
                        and row.metadata['provider'] == source.metadata['provider'] for row in self.sources()):
                    raise LibraryError('INVALID_SOURCE')
                if previous is None or self._read(previous[0]) != source:
                    self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                        ('source_revision:' + source.id, secrets.token_hex(32)))
                self.db.execute('INSERT OR REPLACE INTO sources(id, record) VALUES (?,?)', (source.id, raw))
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def source_snapshot(self, source_id):
        """Private configuration plus an opaque, non-secret configuration epoch.

        Older v1 registries acquire a token once. Equal saves preserve it;
        removal/recreation never revives it. No credential digest is public.
        """
        try:
            return self._source_snapshot(source_id)
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def _source_snapshot(self, source_id):
        source = self.get(source_id)
        key = 'source_revision:' + source.id
        row = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        if row is None:
            if self.read_only:
                raise LibraryError('STORAGE_UNAVAILABLE')
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                source = self.get(source_id)
                self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', (key, secrets.token_hex(32)))
                row = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        if type(row[0]) is not str or not re.fullmatch('[0-9a-f]{64}', row[0]):
            raise LibraryError('INVALID_SOURCE')
        # A concurrent save between the first two reads must not mix records.
        with self.db:
            self.db.execute('BEGIN')
            source = self.get(source_id)
            revision = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
            if revision is None or type(revision[0]) is not str or not re.fullmatch('[0-9a-f]{64}', revision[0]):
                raise LibraryError('INVALID_SOURCE')
            return source, revision[0]

    def run_if_current(self, source, revision, write):
        """CAS publication only; callers must finish network I/O beforehand."""
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                current = self.get(source.id)
                row = self.db.execute('SELECT value FROM metadata WHERE key=?',
                    ('source_revision:' + source.id,)).fetchone()
                if current != source or row is None or row[0] != revision:
                    raise LibraryError('CATALOG_AUTHORITY_CHANGED')
                return write()
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def migrate_legacy(self, location):
        """One-time non-destructive import. Removed connections stay removed."""
        if not location:
            return False
        source = vfs_source('原有视频目录', location,
            source_id=hashlib.sha256(('legacy\n' + location).encode('utf-8')).hexdigest()[:32])
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                if self.db.execute("SELECT 1 FROM metadata WHERE key='legacy_imported'").fetchone():
                    return False
                current = self.sources()
                already = any(s.kind == 'vfs' and s.location == source.location for s in current)
                if not already:
                    if len(current) + len(self.directories()) >= MAX_SOURCES:
                        raise LibraryError('TOO_MANY_SOURCES')
                    raw = json.dumps(dict(source.__dict__, items=[]), ensure_ascii=False)
                    self.db.execute('INSERT INTO sources(id, record) VALUES (?,?)', (source.id, raw))
                self.db.execute("INSERT INTO metadata VALUES ('legacy_imported', '1')")
                return not already
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def remove(self, source_id):
        self.get(source_id)
        try:
            with self.db:
                self.db.execute('DELETE FROM sources WHERE id=?', (source_id,))
                self.db.execute('DELETE FROM metadata WHERE key=?', ('source_revision:' + source_id,))
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def directories(self):
        rows = self.db.execute('SELECT record FROM pan_directories ORDER BY id LIMIT ?', (MAX_SOURCES + 1,)).fetchall()
        if len(rows) > MAX_SOURCES:
            raise LibraryError('TOO_MANY_SOURCES')
        return tuple(_pan_directory(_json(row[0])) for row in rows)

    def directory(self, source_id):
        for row in self.directories():
            if row['id'] == source_id:
                return row
        raise LibraryError('SOURCE_NOT_FOUND')

    def save_directory(self, name, expected, parent):
        # Store only a stable account identifier and explicit user-selected
        # directory. Epochs and credentials remain owned by PanService.
        key = hashlib.sha256(json.dumps([expected['provider'], expected['account_id'], parent],
            ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()[:32]
        row = _pan_directory(dict(id=key, name=name, provider=expected['provider'],
            account_id=expected['account_id'], parent=parent))
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current = self.directories()
            if len(current) + len(self.sources()) >= MAX_SOURCES and not any(r['id'] == key for r in current):
                raise LibraryError('TOO_MANY_SOURCES')
            self.db.execute('INSERT OR REPLACE INTO pan_directories VALUES(?,?)', (key, json.dumps(row, ensure_ascii=False)))
        return row

    def remove_directory(self, source_id):
        self.directory(source_id)
        with self.db:
            self.db.execute('DELETE FROM pan_directories WHERE id=?', (source_id,))


def _pan_directory(row):
    from bobbi_core.file_ref import PROVIDERS
    if (type(row) is not dict or set(row) != {'id', 'name', 'provider', 'account_id', 'parent'}
            or row['provider'] not in PROVIDERS or not re.fullmatch('[0-9a-f]{32}', str(row['id']))):
        raise LibraryError('INVALID_SOURCE')
    for key, maximum in (('name', 80), ('account_id', 256), ('parent', 4096)):
        _text(row[key], maximum)
        if '://' in row[key]:
            raise LibraryError('INVALID_SOURCE')
    return dict(row)
