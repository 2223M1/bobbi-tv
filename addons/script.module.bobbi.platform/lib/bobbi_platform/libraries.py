"""User-owned libraries: local settings only, no network or media mutation.

Kodi handles SMB/NFS/WebDAV itself. Credentials live in the active Kodi profile,
not addon packages, logs, plugin routing URLs or imported public catalogues.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import uuid4

MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 2000
MAX_SOURCES = 32
MAX_DIRECTORY_ITEMS = 10000
SCHEMES = frozenset(('smb', 'nfs', 'dav', 'davs'))
VIDEO_EXTENSIONS = frozenset(('.mkv', '.mp4', '.m4v', '.mov', '.avi', '.webm', '.ts',
    '.m2ts', '.mpg', '.mpeg', '.vob', '.wmv', '.flv', '.iso'))


class LibraryError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _text(value, maximum=2048, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or not empty and not value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise LibraryError('INVALID_VALUE')
    return value


def _json(raw):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise LibraryError('INVALID_DOCUMENT')
            values[key] = value
        return values
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LibraryError('INVALID_DOCUMENT') from None


def split_location(location):
    """Accept a Kodi-selected URL, keeping its credentials out of display URLs."""
    _text(location, 8192)
    if re.match(r'^[A-Za-z]:[/\\]', location) or location.startswith('/'):
        if '\x00' in location or '|' in location:
            raise LibraryError('INVALID_LOCATION')
        return location.rstrip('/\\') + ('/' if '/' in location else '\\'), '', ''
    try:
        value = urlsplit(location)
        if (value.scheme not in SCHEMES or not value.hostname or value.query or value.fragment
                or not value.port and value.netloc.endswith(':') or '|' in location):
            raise LibraryError('INVALID_LOCATION')
        # Read the port to reject malformed/non-numeric values before saving.
        port = value.port
        host = '[' + value.hostname + ']' if ':' in value.hostname else value.hostname
        if any(c.isspace() or c in '\\|%' for c in host):
            raise LibraryError('INVALID_LOCATION')
        host += ':' + str(port) if port is not None else ''
        decoded = unquote(value.path)
        _text(decoded, 8192, True)
        if '\\' in decoded or any(p in ('.', '..') for p in decoded.split('/')):
            raise LibraryError('INVALID_LOCATION')
        path = quote(decoded.rstrip('/') + '/', safe='/')
        username, password = unquote(value.username or ''), unquote(value.password or '')
        _text(username, 512, True)
        _text(password, 1024, True)
        return urlunsplit((value.scheme, host, path, '', '')), username, password
    except (ValueError, UnicodeError):
        raise LibraryError('INVALID_LOCATION') from None


def direct_url(value):
    _text(value, 8192)
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ('http', 'https') or not parts.hostname or '@' in parts.netloc
                or parts.fragment or '|' in value or any(c.isspace() for c in value)
                or '\\' in value or parts.netloc.endswith(':')
                or unquote(parts.path).lower().endswith(('.strm', '.py', '.sh', '.bat', '.cmd', '.torrent'))):
            raise LibraryError('INVALID_MEDIA_URL')
        parts.port
    except ValueError:
        raise LibraryError('INVALID_MEDIA_URL') from None
    return value


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    url: str = field(repr=False)
    year: int = 0
    size: int = None
    modified: str = ''


def validate_file_metadata(size, modified):
    if size is not None and (type(size) is not int or not 0 <= size <= 2**63 - 1):
        raise LibraryError('INVALID_DOCUMENT')
    if not isinstance(modified, str) or len(modified) > 32:
        raise LibraryError('INVALID_DOCUMENT')
    if modified:
        try:
            datetime.fromisoformat(modified)
        except ValueError:
            raise LibraryError('INVALID_DOCUMENT') from None


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str
    location: str = field(default='', repr=False)
    username: str = field(default='', repr=False)
    password: str = field(default='', repr=False)
    items: tuple = field(default=(), repr=False)


def vfs_source(name, location, username='', password='', source_id=None):
    root, embedded_user, embedded_password = split_location(location)
    if (username or password) and (embedded_user or embedded_password):
        raise LibraryError('AMBIGUOUS_CREDENTIALS')
    source = Source(source_id or uuid4().hex, _text(name, 80), 'vfs', root,
                    username or embedded_user, password or embedded_password)
    return validate_source(source)


def import_catalog(raw, source_id=None):
    if not isinstance(raw, (str, bytes)) or len(raw.encode('utf-8') if isinstance(raw, str) else raw) > MAX_CATALOG_BYTES:
        raise LibraryError('CATALOG_TOO_LARGE')
    value = _json(raw)
    if (not isinstance(value, dict) or set(value) != {'schema', 'name', 'items'}
            or value['schema'] != 'bobbi-library-v1' or not isinstance(value['items'], list)
            or not 1 <= len(value['items']) <= MAX_ITEMS):
        raise LibraryError('INVALID_DOCUMENT')
    items, ids = [], set()
    for row in value['items']:
        if (not isinstance(row, dict) or not {'id', 'title', 'url'} <= set(row)
                or set(row) - {'id', 'title', 'url', 'year', 'size', 'modified'}):
            raise LibraryError('INVALID_DOCUMENT')
        item_id = _text(row['id'], 128)
        if item_id in ids:
            raise LibraryError('DUPLICATE_ITEM')
        year = row.get('year', 0)
        if type(year) is not int or year != 0 and not 1880 <= year <= 2200:
            raise LibraryError('INVALID_DOCUMENT')
        validate_file_metadata(row.get('size'), row.get('modified', ''))
        items.append(Item(item_id, _text(row['title'], 240), direct_url(row['url']), year,
                          row.get('size'), row.get('modified', '')))
        ids.add(item_id)
    return validate_source(Source(source_id or uuid4().hex, _text(value['name'], 80), 'catalog', items=tuple(items)))


def validate_source(source):
    if (not isinstance(source, Source) or not isinstance(source.id, str)
            or not re.fullmatch('[0-9a-f]{32}', source.id) or not isinstance(source.items, tuple)):
        raise LibraryError('INVALID_SOURCE')
    _text(source.name, 80)
    if source.kind == 'vfs':
        root, user, password = split_location(source.location)
        if root != source.location or user or password or source.items:
            raise LibraryError('INVALID_SOURCE')
        _text(source.username, 512, True)
        _text(source.password, 1024, True)
        if (source.username or source.password) and urlsplit(root).scheme not in ('smb', 'dav', 'davs'):
            raise LibraryError('UNSUPPORTED_AUTH')
    elif source.kind == 'catalog':
        if source.location or source.username or source.password or not 1 <= len(source.items) <= MAX_ITEMS:
            raise LibraryError('INVALID_SOURCE')
        seen = set()
        for item in source.items:
            if not isinstance(item, Item):
                raise LibraryError('INVALID_SOURCE')
            _text(item.id, 128)
            if item.id in seen:
                raise LibraryError('INVALID_SOURCE')
            _text(item.title, 240)
            direct_url(item.url)
            validate_file_metadata(item.size, item.modified)
            if type(item.year) is not int or item.year != 0 and not 1880 <= item.year <= 2200:
                raise LibraryError('INVALID_SOURCE')
            seen.add(item.id)
    else:
        raise LibraryError('UNSUPPORTED_SOURCE')
    return source


def relative_path(value):
    _text(value, 4096, True)
    if value and (value.startswith('/') or '\\' in value or ':' in value or '|' in value
                  or any(p in ('', '.', '..') for p in value.split('/'))):
        raise LibraryError('INVALID_RELATIVE_PATH')
    return value


def joined_path(source, relative=''):
    validate_source(source)
    if source.kind != 'vfs':
        raise LibraryError('UNSUPPORTED_SOURCE')
    relative_path(relative)
    value = urlsplit(source.location)
    if value.scheme in SCHEMES:
        auth = ''
        if source.username or source.password:
            auth = quote(source.username, safe='') + ':' + quote(source.password, safe='') + '@'
        return urlunsplit((value.scheme, auth + value.netloc, value.path + quote(relative, safe='/'), '', ''))
    return source.location + relative.replace('/', '\\') if '\\' in source.location else source.location + relative


def directory_items(directories, files):
    """Only single-level listing, with no .strm/plugin execution or recursion."""
    result = []
    if (not isinstance(directories, (list, tuple)) or not isinstance(files, (list, tuple))
            or len(directories) + len(files) > MAX_DIRECTORY_ITEMS):
        raise LibraryError('DIRECTORY_TOO_LARGE')
    for folder, names in ((True, directories), (False, files)):
        for name in names:
            if (not isinstance(name, str) or not name or '/' in name or '\\' in name
                    or ':' in name or '|' in name or len(name) > 4096
                    or name in ('.', '..') or any(ord(c) < 32 or ord(c) == 127 for c in name)):
                continue
            if folder or any(name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                result.append((folder, name))
    return tuple(sorted(set(result), key=lambda row: (not row[0], row[1].casefold())))


class Registry:
    """SQLite serializes local UI edits; removal never contacts the source."""
    def __init__(self, path):
        self.path = Path(path)
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise LibraryError('STORAGE_UNSAFE')
        self.db = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            self.db = sqlite3.connect(str(self.path), timeout=1)
            self.db.execute('PRAGMA secure_delete=ON')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise LibraryError('UNKNOWN_STORAGE_VERSION')
            self.db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute('PRAGMA user_version=1')
            self.db.commit()
        except LibraryError:
            if self.db is not None:
                self.db.close()
            raise
        except (OSError, sqlite3.Error):
            if self.db is not None:
                self.db.close()
            raise LibraryError('STORAGE_UNAVAILABLE') from None

    def close(self):
        self.db.close()

    @staticmethod
    def _read(raw):
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_CATALOG_BYTES * 2:
            raise LibraryError('INVALID_SOURCE')
        value = _json(raw)
        try:
            if (not isinstance(value, dict)
                    or set(value) != {'id', 'name', 'kind', 'location', 'username', 'password', 'items'}
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

    def save(self, source):
        source = validate_source(source)
        record = dict(source.__dict__, items=[item.__dict__ for item in source.items])
        raw = json.dumps(record, ensure_ascii=False)
        if len(raw.encode('utf-8')) > MAX_CATALOG_BYTES * 2:
            raise LibraryError('CATALOG_TOO_LARGE')
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                current = self.db.execute('SELECT id FROM sources').fetchall()
                if len(current) >= MAX_SOURCES and source.id not in {row[0] for row in current}:
                    raise LibraryError('TOO_MANY_SOURCES')
                self.db.execute('INSERT OR REPLACE INTO sources(id, record) VALUES (?,?)', (source.id, raw))
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
                    if len(current) >= MAX_SOURCES:
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
        except sqlite3.Error:
            raise LibraryError('STORAGE_UNAVAILABLE') from None
