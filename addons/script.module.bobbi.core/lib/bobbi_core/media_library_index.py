"""Independent local index. File identity, membership and mapping are separate.

SQLite batches include their checkpoint. Only a closed full generation can
mark absent memberships unavailable; incomplete scans preserve prior members.
There are no credentials, playable URLs or provider mutation operations here.
"""
from bobbi_core.typed_ref import KINDS as PATH_KINDS
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
import time
from uuid import uuid4

from .file_ref import validate
from . import catalog_review as review
from .job_snapshot import scan as scan_snapshot
from . import catalog_query

TERMINAL = ('completed', 'failed', 'canceled', 'interrupted')
FRONTIER_PROOF_VERSION = 1
RESUMABLE_SCAN_REASONS = frozenset({
    'PAN_BUDGET_EXHAUSTED',
    'PAN_OPERATION_TIMEOUT',
    'PAN_RATE_LIMITED',
    'CANCEL_CONFIRMED',
    'SERVICE_STOPPED',
    'SERVICE_RESTART',
    'INTERRUPTED_BY_RESTART',
})
MAX_JOBS = 128
PAGE_SIZE = 5  # Long multilingual FileRefs remain inside the 16 KiB runtime.
REPLY_BYTES = 15000  # Leaves room for runtime/phone response envelopes.


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
        raise ValueError('CATALOG_PAGE_INVALID')


def identifier(value, length=32):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}' % length, value):
        raise ValueError('CATALOG_ID_INVALID')
    return value


class MediaIndex:
    def __init__(self, path, now=time.time, file_facts=None):
        if file_facts is not None and not callable(file_facts):
            raise ValueError('FILE_MEDIA_FACTS_ADAPTER_INVALID')
        self.file_facts = file_facts  # Optional bound local read; never an ambient history lookup.
        self.path, self.now, self.lock = Path(path), now, RLock()
        self.migration_backup_path = None
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('CATALOG_STORAGE_UNSAFE')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(str(self.path), timeout=.15, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            with self.transaction():
                version = self.db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1, 2, 3, 4):
                    raise ValueError('CATALOG_SCHEMA_UNSUPPORTED')
                if version in (1, 2, 3):
                    self._backup_for_migration(version)
                for sql in (
                    'CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,ref TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS memberships(source TEXT NOT NULL,file TEXT NOT NULL,generation TEXT NOT NULL,available INTEGER NOT NULL,PRIMARY KEY(source,file))',
                    'CREATE TABLE IF NOT EXISTS reviews(file TEXT PRIMARY KEY,state TEXT NOT NULL,reason TEXT NOT NULL,candidates TEXT NOT NULL,revision INTEGER NOT NULL,mapping TEXT,provenance TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS review_changes(file TEXT NOT NULL,revision INTEGER NOT NULL,before_state TEXT NOT NULL,before_mapping TEXT,after_state TEXT NOT NULL,after_mapping TEXT,PRIMARY KEY(file,revision))',
                    'CREATE TABLE IF NOT EXISTS review_receipts(request TEXT NOT NULL,item INTEGER NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(request,item))',
                    'CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY,source TEXT NOT NULL,scope TEXT NOT NULL,provider TEXT NOT NULL,account TEXT NOT NULL,state TEXT NOT NULL,cancel_requested INTEGER NOT NULL,pages INTEGER NOT NULL,scanned INTEGER NOT NULL,discovered INTEGER NOT NULL,checkpoint TEXT NOT NULL,reason TEXT NOT NULL,updated REAL NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS scan_batches(task TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(task,digest))',
                    'CREATE INDEX IF NOT EXISTS object_scope ON objects(provider,account,id)',
                    'CREATE INDEX IF NOT EXISTS membership_file ON memberships(file,source)',
                    'CREATE TABLE IF NOT EXISTS object_times(file TEXT PRIMARY KEY,first_seen REAL,updated REAL NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS review_receipt_scopes(request TEXT NOT NULL,item INTEGER NOT NULL,provider TEXT NOT NULL,account TEXT NOT NULL,PRIMARY KEY(request,item))',
                    'CREATE TABLE IF NOT EXISTS review_requests(request TEXT PRIMARY KEY,digest TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS catalog_meta(singleton INTEGER PRIMARY KEY,schema INTEGER NOT NULL,generation TEXT NOT NULL,revision INTEGER NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS catalog_sources(source TEXT PRIMARY KEY,active INTEGER NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS typed_objects(id TEXT PRIMARY KEY,source TEXT NOT NULL,namespace TEXT NOT NULL,ref TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS catalog_scope_revisions(provider TEXT NOT NULL,account TEXT NOT NULL,namespace TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(provider,account,namespace))',
                    'CREATE TABLE IF NOT EXISTS typed_observations(file TEXT NOT NULL,digest TEXT NOT NULL,ref TEXT NOT NULL,observed REAL NOT NULL,PRIMARY KEY(file,digest))',
                    'CREATE TABLE IF NOT EXISTS file_supplements(file TEXT PRIMARY KEY,work_id TEXT NOT NULL,parent_file TEXT,detail TEXT NOT NULL)',
                    'CREATE INDEX IF NOT EXISTS supplement_work ON file_supplements(work_id,parent_file,file)',
                    'CREATE TABLE IF NOT EXISTS supplement_changes(file TEXT NOT NULL,revision INTEGER NOT NULL,before_relation TEXT,after_relation TEXT,PRIMARY KEY(file,revision))',
                    'CREATE TABLE IF NOT EXISTS file_segments(file TEXT PRIMARY KEY,detail TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS segment_changes(file TEXT NOT NULL,revision INTEGER NOT NULL,before_segments TEXT,after_segments TEXT,PRIMARY KEY(file,revision))',
                ):
                    self.db.execute(sql)
                # A point recheck outranks an already-started mounted scan.
                # This connection-local work table participates in the same
                # transactions without adding a persistent schema/cache.
                self.db.execute('CREATE TEMP TABLE scan_point_observations('
                    'task TEXT NOT NULL,file TEXT NOT NULL,PRIMARY KEY(task,file))')
                self.db.execute('INSERT OR IGNORE INTO object_times SELECT id,NULL,0 FROM objects')
                self.db.execute('INSERT OR IGNORE INTO object_times SELECT id,NULL,0 FROM typed_objects')
                self.db.execute('INSERT OR IGNORE INTO catalog_sources SELECT DISTINCT source,1 FROM memberships')
                catalog_query.create_projection(self.db)
                meta = self.db.execute('SELECT * FROM catalog_meta WHERE singleton=1').fetchone()
                rebuild = (meta is None or meta['schema'] != catalog_query.PROJECTION_SCHEMA or self.db.execute(
                    'SELECT count(*) FROM catalog_rows').fetchone()[0] != self.db.execute(
                    'SELECT (SELECT count(*) FROM objects)+(SELECT count(*) FROM typed_objects)').fetchone()[0])
                if rebuild:
                    self._rebuild_projection()
                else:
                    self._page_indexes()
                self.db.execute('PRAGMA user_version=4')
            self._attach_frontier()
            self.query_reader = catalog_query.CatalogQuery(self)
        except BaseException:
            self.db.close()
            raise

    def _attach_frontier(self):
        """Open bounded sidecar frontier DB (WAL) without altering main user_version=4 shape."""
        self.frontier_path = Path(str(self.path) + '.frontier.sqlite3')
        if self.frontier_path.is_symlink():
            raise ValueError('CATALOG_STORAGE_UNSAFE')
        if self.frontier_path.exists():
            healthy = False
            try:
                probe = sqlite3.connect(str(self.frontier_path), timeout=.15)
                try:
                    fver = probe.execute('PRAGMA user_version').fetchone()[0]
                    qchk = probe.execute('PRAGMA quick_check').fetchone()[0]
                    healthy = fver in (0, 1, 2, 3) and qchk == 'ok'
                finally:
                    probe.close()
            except sqlite3.Error:
                healthy = False
            if not healthy:
                for suffix in ('', '-journal', '-wal', '-shm'):
                    candidate = Path(str(self.frontier_path) + suffix)
                    if candidate.is_symlink():
                        raise ValueError('CATALOG_STORAGE_UNSAFE')
                    if candidate.exists():
                        candidate.unlink()
        if not self.frontier_path.exists():
            fd = os.open(str(self.frontier_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.frontier_db = sqlite3.connect(str(self.frontier_path), timeout=.15, check_same_thread=False)
        self.frontier_db.row_factory = sqlite3.Row
        self.frontier_db.execute('PRAGMA journal_mode=WAL')
        self.frontier_db.execute('PRAGMA synchronous=NORMAL')
        with self.frontier_db:
            fver = self.frontier_db.execute('PRAGMA user_version').fetchone()[0]
            if fver == 2:
                self._migrate_frontier_v2_to_v3()
            elif fver != 3:
                for tbl in ('scan_state', 'scan_dirs', 'scan_nodes', 'scan_page_entries', 'scan_page_cursors'):
                    self.frontier_db.execute(f'DROP TABLE IF EXISTS {tbl}')
            for sql in (
                'CREATE TABLE IF NOT EXISTS scan_state('
                'source TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,'
                'scope_digest TEXT NOT NULL,root_parent TEXT NOT NULL,scan_generation TEXT NOT NULL,'
                'last_task TEXT NOT NULL,last_batch TEXT NOT NULL,resumed INTEGER NOT NULL,'
                'partial_latch INTEGER NOT NULL,dir_count INTEGER NOT NULL,updated REAL NOT NULL,'
                'last_batch_task TEXT NOT NULL DEFAULT \'\',proof_version INTEGER NOT NULL DEFAULT 1)',
                'CREATE TABLE IF NOT EXISTS scan_dirs('
                'source TEXT NOT NULL,scan_generation TEXT NOT NULL,dir_key TEXT NOT NULL,'
                'depth INTEGER NOT NULL,expected_total INTEGER,'
                'seen_count INTEGER NOT NULL DEFAULT 0,next_offset INTEGER NOT NULL DEFAULT 0,'
                'last_cursor TEXT,ids_digest TEXT NOT NULL DEFAULT \'\','
                'proof_task TEXT NOT NULL DEFAULT \'\',proof_version INTEGER NOT NULL DEFAULT 1,'
                'PRIMARY KEY(source,scan_generation,dir_key))',
                'CREATE TABLE IF NOT EXISTS scan_nodes('
                'source TEXT NOT NULL,scan_generation TEXT NOT NULL,priority INTEGER NOT NULL,'
                'seq INTEGER PRIMARY KEY AUTOINCREMENT,node_key TEXT NOT NULL,depth INTEGER NOT NULL,'
                'leaf INTEGER NOT NULL,next_page INTEGER NOT NULL,cursor TEXT)',
                'CREATE INDEX IF NOT EXISTS scan_nodes_order ON scan_nodes(source,scan_generation,priority,seq)',
                'CREATE TABLE IF NOT EXISTS scan_page_entries('
                'source TEXT NOT NULL,scan_generation TEXT NOT NULL,dir_key TEXT NOT NULL,'
                'entry_sig TEXT NOT NULL,PRIMARY KEY(source,scan_generation,dir_key,entry_sig))',
                'CREATE TABLE IF NOT EXISTS scan_page_cursors('
                'source TEXT NOT NULL,scan_generation TEXT NOT NULL,dir_key TEXT NOT NULL,'
                'cursor TEXT NOT NULL,PRIMARY KEY(source,scan_generation,dir_key,cursor))',
            ):
                self.frontier_db.execute(sql)
            self.frontier_db.execute('PRAGMA user_version=3')
            # Invalidate any frontier superseded while running under a downgraded reader/writer
            # or interrupted between main commit and frontier commit (half-write recovery).
            for frow in self.frontier_db.execute('SELECT * FROM scan_state').fetchall():
                if not self._frontier_batch_consistent(frow):
                    self._clear_frontier(frow['source'])
                else:
                    self._rewind_unproven_nodes(frow['source'], frow['scan_generation'])

    def _migrate_frontier_v2_to_v3(self):
        state_cols = {r[1] for r in self.frontier_db.execute('PRAGMA table_info(scan_state)').fetchall()}
        if 'last_batch_task' not in state_cols:
            self.frontier_db.execute("ALTER TABLE scan_state ADD COLUMN last_batch_task TEXT NOT NULL DEFAULT ''")
            self.frontier_db.execute("UPDATE scan_state SET last_batch_task=CASE WHEN last_batch!='' THEN last_task ELSE '' END")
        if 'proof_version' not in state_cols:
            self.frontier_db.execute('ALTER TABLE scan_state ADD COLUMN proof_version INTEGER NOT NULL DEFAULT 0')
        dir_cols = {r[1] for r in self.frontier_db.execute('PRAGMA table_info(scan_dirs)').fetchall()}
        for col_sql, col_name in (
            ('seen_count INTEGER NOT NULL DEFAULT 0', 'seen_count'),
            ('next_offset INTEGER NOT NULL DEFAULT 0', 'next_offset'),
            ('last_cursor TEXT', 'last_cursor'),
            ("ids_digest TEXT NOT NULL DEFAULT ''", 'ids_digest'),
            ("proof_task TEXT NOT NULL DEFAULT ''", 'proof_task'),
            ('proof_version INTEGER NOT NULL DEFAULT 0', 'proof_version'),
        ):
            if col_name not in dir_cols:
                self.frontier_db.execute(f'ALTER TABLE scan_dirs ADD COLUMN {col_sql}')

    def _rewind_unproven_nodes(self, source, scan_generation):
        """Replay only unfinished page>1 directories lacking versioned proof; keep completed dirs."""
        unproven = self.frontier_db.execute(
            'SELECT n.seq,n.node_key,n.leaf,n.next_page,n.cursor,'
            'COALESCE(d.proof_version,0) AS d_ver,COALESCE(d.seen_count,0) AS d_seen '
            'FROM scan_nodes n LEFT JOIN scan_dirs d '
            'ON d.source=n.source AND d.scan_generation=n.scan_generation AND d.dir_key=n.node_key '
            'WHERE n.source=? AND n.scan_generation=? AND (n.next_page>1 OR n.cursor IS NOT NULL)',
            (source, scan_generation),
        ).fetchall()
        rewound_keys = set()
        for row in unproven:
            if row['leaf'] or row['d_ver'] < FRONTIER_PROOF_VERSION or row['d_seen'] <= 0:
                key = row['node_key']
                if key in rewound_keys:
                    self.frontier_db.execute(
                        'DELETE FROM scan_nodes WHERE source=? AND scan_generation=? AND seq=?',
                        (source, scan_generation, row['seq']),
                    )
                    continue
                rewound_keys.add(key)
                self.frontier_db.execute(
                    'UPDATE scan_nodes SET next_page=1,cursor=NULL WHERE source=? AND scan_generation=? AND seq=?',
                    (source, scan_generation, row['seq']),
                )
                self.frontier_db.execute(
                    'DELETE FROM scan_page_entries WHERE source=? AND scan_generation=? AND dir_key=?',
                    (source, scan_generation, key),
                )
                self.frontier_db.execute(
                    'DELETE FROM scan_page_cursors WHERE source=? AND scan_generation=? AND dir_key=?',
                    (source, scan_generation, key),
                )
                self.frontier_db.execute(
                    "UPDATE scan_dirs SET expected_total=NULL,seen_count=0,next_offset=0,"
                    "last_cursor=NULL,ids_digest='',proof_task='',proof_version=? "
                    'WHERE source=? AND scan_generation=? AND dir_key=?',
                    (FRONTIER_PROOF_VERSION, source, scan_generation, key),
                )
        self.frontier_db.execute(
            'UPDATE scan_dirs SET proof_version=? WHERE source=? AND scan_generation=? AND proof_version<?',
            (FRONTIER_PROOF_VERSION, source, scan_generation, FRONTIER_PROOF_VERSION),
        )
        if rewound_keys:
            self.frontier_db.execute(
                'UPDATE scan_state SET resumed=1,proof_version=? WHERE source=?',
                (FRONTIER_PROOF_VERSION, source),
            )
        else:
            self.frontier_db.execute(
                'UPDATE scan_state SET proof_version=? WHERE source=? AND proof_version<?',
                (FRONTIER_PROOF_VERSION, source, FRONTIER_PROOF_VERSION),
            )

    def _frontier_batch_consistent(self, frow):
        latest = self.db.execute(
            'SELECT id,state FROM scans WHERE provider=? AND account=? AND source=? ORDER BY updated DESC,id DESC LIMIT 1',
            (frow['provider'], frow['account'], frow['source']),
        ).fetchone()
        if latest is None or latest['id'] != frow['last_task'] or latest['state'] == 'completed':
            return False
        task_batch = self.db.execute(
            'SELECT digest FROM scan_batches WHERE task=? ORDER BY rowid DESC LIMIT 1',
            (frow['last_task'],),
        ).fetchone()
        last_batch = frow['last_batch']
        last_batch_task = frow['last_batch_task'] if 'last_batch_task' in frow.keys() else ''
        if task_batch is not None:
            return bool(last_batch) and last_batch == task_batch[0] and last_batch_task in ('', frow['last_task'])
        if not last_batch:
            return True
        if not last_batch_task or last_batch_task == frow['last_task']:
            return False
        anchor_batch = self.db.execute(
            'SELECT digest FROM scan_batches WHERE task=? ORDER BY rowid DESC LIMIT 1',
            (last_batch_task,),
        ).fetchone()
        return anchor_batch is not None and anchor_batch[0] == last_batch

    def _clear_frontier(self, source):
        for tbl in ('scan_state', 'scan_dirs', 'scan_nodes', 'scan_page_entries', 'scan_page_cursors'):
            self.frontier_db.execute(f'DELETE FROM {tbl} WHERE source=?', (source,))

    def _backup_for_migration(self, version):
        """Publish a complete, exclusive recovery point for this exact upgrade.

        The caller holds BEGIN IMMEDIATE before any DDL. A second read-only
        connection sees the same committed state while no other writer can
        change it. Older recovery points remain untouched, including after a
        rollback to schema 2 and subsequent manual edits there.
        """
        def check(path):
            if path.is_symlink():
                raise ValueError('CATALOG_STORAGE_UNSAFE')
            target = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                if (target.execute('PRAGMA user_version').fetchone()[0] != version or
                        target.execute('PRAGMA quick_check').fetchone()[0] != 'ok'):
                    raise ValueError('CATALOG_STORAGE_UNSAFE')
            except sqlite3.Error:
                raise ValueError('CATALOG_STORAGE_UNSAFE') from None
            finally:
                target.close()

        backup = Path(str(self.path) + '.schema%d.bak' % version)
        if backup.is_symlink():
            raise ValueError('CATALOG_STORAGE_UNSAFE')
        if backup.exists():
            check(backup)  # Never treat a prior partial copy as recoverable.
            backup = Path(str(self.path) + '.schema%d.%s.bak' % (version, uuid4().hex))
        staged = Path(str(backup) + '.' + uuid4().hex + '.tmp')
        fd = os.open(str(staged), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        source = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(str(staged))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        check(staged)
        # A hard link publishes the complete file atomically and fails if the
        # final path already exists. Neither legacy backups nor a racing writer
        # can be overwritten; an interrupted .tmp is never a recovery point.
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.link(staged, backup)
        staged.unlink()
        self.migration_backup_path = backup

    @contextmanager
    def transaction(self):
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield

    def close(self):
        with self.lock:
            if getattr(self, 'frontier_db', None) is not None:
                self.frontier_db.close()
            self.db.close()

    def _rebuild_projection(self):
        """Explicit owner maintenance, never performed by a read-page request.

        A staging table prevents partial generation publication. Startup holds
        the writer lease; references are decoded in bounded batches, then the
        staging table is switched atomically with its generation. Provider file
        browsing is independent of this local index maintenance.
        """
        prior = self.db.execute('SELECT revision FROM catalog_meta WHERE singleton=1').fetchone()
        revision = prior[0] + 1 if prior else 0
        self.db.execute('DROP TABLE IF EXISTS catalog_rows_build')
        catalog_query.create_projection(self.db, 'catalog_rows_build')
        rows = self.db.execute('SELECT id FROM objects UNION ALL SELECT id FROM typed_objects ORDER BY id')
        while True:
            batch = rows.fetchmany(100)
            if not batch:
                break
            for row in batch:
                catalog_query.project(self.db, row[0], 'catalog_rows_build')
        self.db.execute('DROP TABLE catalog_rows')
        self.db.execute('ALTER TABLE catalog_rows_build RENAME TO catalog_rows')
        self.db.execute('CREATE INDEX catalog_rows_scope ON catalog_rows(provider,account,title_sort,id)')
        self.db.execute('CREATE INDEX catalog_rows_work ON catalog_rows(provider,account,work_id,season_id,episode_id)')
        self.db.execute('CREATE INDEX catalog_rows_group ON catalog_rows(group_key,id)')
        self._page_indexes()
        self.db.execute('INSERT OR REPLACE INTO catalog_meta VALUES(1,?,?,?)',
            (catalog_query.PROJECTION_SCHEMA, uuid4().hex, revision))

    def _page_indexes(self):
        # Upgrade the read model in place and restore the same paths on an explicit rebuild.
        self.db.execute('CREATE INDEX IF NOT EXISTS catalog_rows_filename ON catalog_rows(provider,account,filename_sort,id)')
        self.db.execute('CREATE INDEX IF NOT EXISTS catalog_rows_season ON catalog_rows(provider,account,season_id,episode_id)')

    def rebuild_projection(self):
        with self.transaction():
            self._rebuild_projection()

    def _changed(self, expected):
        self.db.execute('UPDATE catalog_meta SET revision=revision+1 WHERE singleton=1')
        self.db.execute('INSERT INTO catalog_scope_revisions VALUES(?,?,?,1) '
            'ON CONFLICT(provider,account,namespace) DO UPDATE SET revision=revision+1',
            catalog_query.revision_key(expected))

    def scope_revision(self, expected):
        row = self.db.execute('SELECT revision FROM catalog_scope_revisions WHERE provider=? AND account=? AND namespace=?',
            catalog_query.revision_key(expected)).fetchone()
        return row[0] if row else 0

    def query(self, expected, **args):
        return self.query_reader.query(expected, **args)

    def describe_files(self, expected, file_ids):
        return self.query_reader.describe_files(expected, file_ids)

    def parent_descriptor(self, expected, parent_id):
        return self.query_reader.parent_descriptor(expected, parent_id)

    def holdings(self, expected, identities):
        return self.query_reader.holdings(expected, identities)

    def manual_records(self, expected, file_ids=None, offset=0, limit=5, projection_revision=None):
        """Host-only bounded migration descriptions, retaining exact stored evidence."""
        page(offset, limit)
        if file_ids is not None and (type(file_ids) is not list or not 1 <= len(file_ids) <= 5):
            raise ValueError('CATALOG_PAGE_INVALID')
        with self.lock:
            revision = self.scope_revision(expected)
            if projection_revision is not None and projection_revision != revision:
                raise ValueError('CATALOG_CURSOR_STALE')
            where, args = self.query_reader._partition(expected)
            excluded = 0  # v3 preserves supplement relationships in the same artifact.
            if file_ids is None:
                from .catalog_transfer import EXPORT_STATES
                # Undo retains the audit provenance but may restore an automatic
                # proposed/ambiguous state. Export only the format's manual
                # states; one restored suggestion must not abort a whole file.
                ids = [row[0] for row in self.db.execute('SELECT p.id FROM catalog_rows p '
                    'JOIN reviews r ON r.file=p.id WHERE ' + where +
                    " AND r.provenance='manual' AND (r.state IN (" + ','.join('?' for _ in EXPORT_STATES) +
                    ') OR EXISTS(SELECT 1 FROM file_segments s WHERE s.file=p.id) '
                    'OR EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id)) '
                    'ORDER BY p.id LIMIT ? OFFSET ?', args + list(EXPORT_STATES) + [limit + 1, offset])]
            else:
                requested = list(dict.fromkeys(identifier(value, 64) for value in file_ids))
                where, args = self.query_reader._partition(expected)
                ids = [row[0] for row in self.db.execute('SELECT p.id FROM catalog_rows p WHERE ' + where +
                    ' AND p.id IN (' + ','.join('?' for _ in requested) + ') ORDER BY p.id', args + requested)]
            items = []
            for identifier_value in ids[:limit]:
                item = self._item(identifier_value, expected)
                public = {key: item[key] for key in ('file_ref', 'state', 'mapping', 'revision', 'provenance', 'available')}
                if item.get('supplement'):
                    public['supplement'] = item['supplement']
                    parent_id = item['supplement']['parent_file_id']
                    public['supplement_parent'] = None
                    if parent_id:
                        try:
                            public['supplement_parent'] = self._item(parent_id, expected)['file_ref']
                        except ValueError:
                            pass  # Keep unresolved evidence, never invent a parent.
                if item.get('segments'):
                    public['segments'] = item['segments']
                if len(encode(dict(items=items + [public], projection_revision=revision,
                        next_offset=offset + len(items) + 1, excluded_supplements=excluded)).encode('utf-8')) > REPLY_BYTES:
                    if not items:
                        raise ValueError('CATALOG_REPLY_LIMIT')
                    break
                items.append(public)
            return dict(items=items, projection_revision=revision, excluded_supplements=excluded,
                next_offset=offset + len(items) if len(ids) > len(items) else None)

    def has_mounted_items(self, source_id, namespace):
        with self.lock:
            return self.db.execute('SELECT 1 FROM typed_objects WHERE source=? AND namespace=? LIMIT 1',
                (identifier(source_id), identifier(namespace, 64))).fetchone() is not None

    def trusted_file(self, expected, object_id):
        """Host-only reference lookup, not a public query response."""
        with self.lock:
            return validate(self._item(object_id, expected)['file_ref'])

    def trusted_mounted_file(self, authority, object_id):
        from .typed_ref import validate as mounted_validate
        with self.lock:
            row = self.db.execute('SELECT ref FROM typed_objects WHERE id=? AND source=? AND namespace=?',
                (identifier(object_id, 64), authority['source_id'], authority['namespace'])).fetchone()
            if row is None:
                raise ValueError('CATALOG_FILE_NOT_FOUND')
            return mounted_validate(json.loads(row[0]))

    def _remember_observation(self, reference):
        """Retain old evidence for diagnosis; history is not a playback permit."""
        raw = encode(reference)
        self.db.execute('INSERT OR IGNORE INTO typed_observations VALUES(?,?,?,?)',
            (reference['id'], hashlib.sha256(raw.encode()).hexdigest(), raw, self.now()))
        self.db.execute('DELETE FROM typed_observations WHERE file=? AND rowid NOT IN '
            '(SELECT rowid FROM typed_observations WHERE file=? ORDER BY observed DESC,rowid DESC LIMIT 32)',
            (reference['id'], reference['id']))

    def observe_mounted(self, authority, reference):
        """Publish an explicitly reselected current observation, never progress."""
        from .typed_ref import validate as mounted_validate
        reference = mounted_validate(reference)
        with self.transaction():
            previous = self.trusted_mounted_file(authority, reference['id'])
            generation = reference.get('mount_generation', reference.get('source_generation'))
            if (reference['reference_kind'], reference['source_id'], reference['namespace'], generation) != (
                    authority['reference_kind'],
                    authority['source_id'], authority['namespace'], authority['generation']):
                raise ValueError('CATALOG_AUTHORITY_CHANGED')
            self._remember_observation(previous)
            self._remember_observation(reference)
            ref_changed = previous != reference
            if ref_changed:
                self.db.execute('UPDATE typed_objects SET ref=? WHERE id=?', (encode(reference), reference['id']))
            # An explicit fresh-list/stat observation can rediscover a file
            # absent from the last closed scan. Restore only this membership;
            # its scan generation remains unchanged, and no sibling becomes
            # present merely because this file was selected.
            restored = self.db.execute('UPDATE memberships SET available=1 WHERE source=? AND file=? AND available=0',
                (authority['source_id'], reference['id']))
            for row in self.db.execute("SELECT id FROM scans WHERE state IN ('queued','running')").fetchall():
                run = self._scan(row['id'])
                if (self._mounted_task_matches(run, authority['source_id'], authority['namespace'])
                        and run['scope'].get('generation') == authority['generation']):
                    self.db.execute('INSERT OR IGNORE INTO temp.scan_point_observations VALUES(?,?)',
                        (run['id'], reference['id']))
            if ref_changed:
                self.db.execute('UPDATE object_times SET updated=? WHERE file=?', (self.now(), reference['id']))
                catalog_query.project(self.db, reference['id'])
            if ref_changed or restored.rowcount:
                self._changed(authority)

    def file_sources(self, object_id):
        with self.lock:
            return [row[0] for row in self.db.execute('SELECT m.source FROM memberships m '
                'JOIN catalog_sources s ON s.source=m.source WHERE m.file=? AND s.active=1',
                (identifier(object_id, 64),))]

    def receipt(self, expected, request_id):
        identifier(request_id)
        with self.lock:
            rows = self.db.execute('SELECT r.item,r.result FROM review_receipts r '
                'JOIN review_receipt_scopes s ON s.request=r.request AND s.item=r.item '
                'WHERE r.request=? AND s.provider=? AND s.account=? ORDER BY r.item',
                (request_id, *self._receipt_scope(expected))).fetchall()
            return dict(status='found' if rows else 'missing', items=[
                dict(json.loads(row['result']), index=row['item']) for row in rows])

    def group(self, expected, file_id, source_id=None, offset=0, limit=PAGE_SIZE,
              projection_revision=None):
        """Bounded same-directory suggestions, never filename-prefix grouping."""
        page(offset, limit)
        if projection_revision is not None and (type(projection_revision) is not int or projection_revision < 0):
            raise ValueError('CATALOG_QUERY_INVALID')
        with self.lock:
            ref = self._item(file_id, expected)['file_ref']
            sources = self.file_sources(file_id)
            if source_id is None:
                if len(sources) != 1:
                    raise ValueError('CATALOG_GROUP_AMBIGUOUS')
                source_id = sources[0]
            elif identifier(source_id) not in sources:
                raise ValueError('CATALOG_SOURCE_UNAVAILABLE')
            revision = self.scope_revision(expected)
            if projection_revision is not None and projection_revision != revision:
                raise ValueError('CATALOG_CURSOR_STALE')
            group_key = catalog_query.opaque(*catalog_query.scope_key(expected)[:2], ref['namespace'], ref['parent'])
            rows = self.db.execute('SELECT p.id FROM catalog_rows p WHERE p.group_key=? AND '
                'EXISTS(SELECT 1 FROM memberships m WHERE m.file=p.id AND m.source=?) ORDER BY p.id LIMIT ? OFFSET ?',
                (group_key, source_id, limit + 1, offset)).fetchall()
            result = dict(items=[], next_offset=None, group_id=catalog_query.opaque(
                *catalog_query.scope_key(expected), source_id, group_key),
                          anchor_id=file_id, projection_revision=revision, source_id=source_id)
            for row in rows[:limit]:
                item = self._public(self._item(row[0], expected))
                if len(encode(dict(result, items=result['items'] + [item], next_offset=offset + len(result['items']) + 1)).encode('utf-8')) > REPLY_BYTES:
                    if not result['items']:
                        raise ValueError('CATALOG_REPLY_LIMIT')
                    break
                result['items'].append(item)
            if len(rows) > len(result['items']):
                result['next_offset'] = offset + len(result['items'])
            return result

    def recover(self):
        # Mark interrupted active tasks with SERVICE_RESTART; committed frontier
        # batches with matching scope/batch proof can resume as partial.
        with self.transaction():
            self.db.execute("UPDATE scans SET state='interrupted',reason='SERVICE_RESTART',updated=? WHERE state IN ('queued','running')", (self.now(),))
            self.db.execute('DELETE FROM temp.scan_point_observations')

    def retain_sources(self, sources):
        """Local explicit source removal, not an inference of remote deletion."""
        if type(sources) is not list or len(sources) > 32:
            raise ValueError('CATALOG_SOURCE_INVALID')
        sources = [identifier(value) for value in sources]
        with self.transaction():
            previous = {row[0] for row in self.db.execute('SELECT source FROM catalog_sources WHERE active=1')}
            self.db.execute('UPDATE catalog_sources SET active=0')
            self.db.executemany('INSERT INTO catalog_sources VALUES(?,1) ON CONFLICT(source) DO UPDATE SET active=1',
                [(source,) for source in sources])
            if sources:
                self.db.execute('UPDATE memberships SET available=0 WHERE source NOT IN (' +
                    ','.join('?' for _ in sources) + ')', sources)
                with self.frontier_db:
                    for tbl in ('scan_state', 'scan_dirs', 'scan_nodes', 'scan_page_entries', 'scan_page_cursors'):
                        self.frontier_db.execute(f'DELETE FROM {tbl} WHERE source NOT IN (' +
                            ','.join('?' for _ in sources) + ')', sources)
            else:
                self.db.execute('UPDATE memberships SET available=0')
                with self.frontier_db:
                    for tbl in ('scan_state', 'scan_dirs', 'scan_nodes', 'scan_page_entries', 'scan_page_cursors'):
                        self.frontier_db.execute(f'DELETE FROM {tbl}')
            if previous != set(sources):
                changed_sources = previous.symmetric_difference(sources)
                for row in self.db.execute('SELECT DISTINCT p.provider,p.account,p.namespace FROM catalog_rows p '
                        'JOIN memberships m ON m.file=p.id WHERE m.source IN (' +
                        ','.join('?' for _ in changed_sources) + ')', tuple(changed_sources)).fetchall():
                    self._changed(dict(reference_kind=row['provider'], source_id=row['account'], namespace=row['namespace'])
                        if row['provider'] in PATH_KINDS else dict(provider=row['provider'], account_id=row['account']))

    def _scan(self, task, expected=None):
        row = self.db.execute('SELECT * FROM scans WHERE id=?', (identifier(task),)).fetchone()
        if row is None:
            raise ValueError('CATALOG_TASK_NOT_FOUND')
        result = dict(row, scope=json.loads(row['scope']), checkpoint=json.loads(row['checkpoint']))
        if expected is not None and (row['provider'], row['account']) != catalog_query.scope_key(expected)[:2]:
            raise ValueError('CATALOG_ACCOUNT_MISMATCH')
        return result

    def start(self, source, expected):
        identifier(source)
        with self.transaction():
            active = self.db.execute("SELECT id FROM scans WHERE state IN ('queued','running')").fetchall()
            if active:
                raise ValueError('CATALOG_SCAN_BUSY')  # One low-priority worker.
            self.db.execute('DELETE FROM temp.scan_point_observations')
            self.db.execute('DELETE FROM scans WHERE id IN (SELECT id FROM scans ORDER BY updated DESC,id DESC LIMIT -1 OFFSET ?)', (MAX_JOBS - 1,))
            self.db.execute('DELETE FROM scan_batches WHERE task NOT IN (SELECT id FROM scans)')
            with self.frontier_db:
                self._clear_frontier(source)
            task = uuid4().hex
            self.db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (task, source, encode(expected), *catalog_query.scope_key(expected)[:2],
                 'queued', 0, 0, 0, 0, '{}', '', self.now()))
        return task

    def start_resumable(self, source, expected, root_parent, *, resumable=True):
        identifier(source)
        if type(root_parent) is not str or len(root_parent) > 4096:
            raise ValueError('CATALOG_SOURCE_INVALID')
        provider, account = catalog_query.scope_key(expected)[:2]
        scope_digest = hashlib.sha256(encode([expected, root_parent]).encode()).hexdigest()
        with self.transaction():
            active = self.db.execute("SELECT id FROM scans WHERE state IN ('queued','running')").fetchall()
            if active:
                raise ValueError('CATALOG_SCAN_BUSY')
            prior = self.db.execute(
                'SELECT id,state,reason FROM scans WHERE provider=? AND account=? AND source=? ORDER BY updated DESC,id DESC LIMIT 1',
                (provider, account, source),
            ).fetchone()
            fstate = self.frontier_db.execute('SELECT * FROM scan_state WHERE source=?', (source,)).fetchone()
            batch_consistent = fstate is not None and self._frontier_batch_consistent(fstate)
            self.db.execute('DELETE FROM temp.scan_point_observations')
            self.db.execute('DELETE FROM scans WHERE id IN (SELECT id FROM scans ORDER BY updated DESC,id DESC LIMIT -1 OFFSET ?)', (MAX_JOBS - 1,))
            self.db.execute('DELETE FROM scan_batches WHERE task NOT IN (SELECT id FROM scans)')
            can_resume = False
            if (
                resumable
                and batch_consistent
                and bool(fstate['last_batch'])
                and prior is not None
                and prior['id'] == fstate['last_task']
                and prior['state'] in ('interrupted', 'canceled', 'failed')
                and prior['reason'] in RESUMABLE_SCAN_REASONS
                and (fstate['provider'], fstate['account'], fstate['scope_digest'], fstate['root_parent'])
                == (provider, account, scope_digest, root_parent)
            ):
                # Re-verify anchor batch survived MAX_JOBS eviction before trusting resume.
                anchor_task = fstate['last_batch_task'] or fstate['last_task']
                anchor_alive = self.db.execute(
                    'SELECT digest FROM scan_batches WHERE task=? ORDER BY rowid DESC LIMIT 1',
                    (anchor_task,),
                ).fetchone()
                if anchor_alive is not None and anchor_alive[0] == fstate['last_batch']:
                    pending_cnt = self.frontier_db.execute(
                        'SELECT count(*) FROM scan_nodes WHERE source=? AND scan_generation=?',
                        (source, fstate['scan_generation']),
                    ).fetchone()[0]
                    can_resume = pending_cnt > 0
            task = uuid4().hex
            now = self.now()
            self.db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (task, source, encode(expected), provider, account,
                 'queued', 0, 0, 0, 0, '{}', '', now))
            with self.frontier_db:
                if can_resume:
                    self._rewind_unproven_nodes(source, fstate['scan_generation'])
                    self.frontier_db.execute(
                        'UPDATE scan_state SET last_task=?,resumed=1,proof_version=?,updated=? WHERE source=?',
                        (task, FRONTIER_PROOF_VERSION, now, source),
                    )
                else:
                    self._clear_frontier(source)
                    self.frontier_db.execute(
                        'INSERT INTO scan_state('
                        'source,provider,account,scope_digest,root_parent,scan_generation,'
                        'last_task,last_batch,resumed,partial_latch,dir_count,updated,last_batch_task,proof_version'
                        ') VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (source, provider, account, scope_digest, root_parent, task, task, '', 0, 0, 1, now, '', FRONTIER_PROOF_VERSION),
                    )
                    self.frontier_db.execute(
                        'INSERT INTO scan_dirs('
                        'source,scan_generation,dir_key,depth,expected_total,seen_count,next_offset,last_cursor,ids_digest,proof_task,proof_version'
                        ') VALUES(?,?,?,?,NULL,0,0,NULL,?,?,?)',
                        (source, task, root_parent, 0, '', '', FRONTIER_PROOF_VERSION),
                    )
                    self.frontier_db.execute(
                        'INSERT INTO scan_nodes(source,scan_generation,priority,node_key,depth,leaf,next_page,cursor) VALUES(?,?,?,?,?,?,?,?)',
                        (source, task, 1, root_parent, 0, 0, 1, None),
                    )
        return task

    def frontier_peek(self, task):
        with self.lock:
            run = self._scan(task)
            fstate = self.frontier_db.execute(
                'SELECT * FROM scan_state WHERE source=? AND last_task=?',
                (run['source'], task),
            ).fetchone()
            if fstate is None:
                return None
            gen = fstate['scan_generation']
            node = self.frontier_db.execute(
                'SELECT * FROM scan_nodes WHERE source=? AND scan_generation=? ORDER BY priority ASC,seq ASC LIMIT 1',
                (run['source'], gen),
            ).fetchone()
            if node is None:
                return dict(empty=True, state=dict(fstate), queued=0)
            queued = self.frontier_db.execute(
                'SELECT count(*) FROM scan_nodes WHERE source=? AND scan_generation=?',
                (run['source'], gen),
            ).fetchone()[0]
            if node['leaf']:
                leaf_rows = [
                    dict(r)
                    for r in self.frontier_db.execute(
                        'SELECT * FROM scan_nodes WHERE source=? AND scan_generation=? AND leaf=1 ORDER BY priority ASC,seq ASC LIMIT 20',
                        (run['source'], gen),
                    ).fetchall()
                ]
                return dict(
                    empty=False,
                    state=dict(fstate),
                    node=dict(node),
                    leaf_nodes=leaf_rows,
                    queued=queued,
                    expected_total=None,
                    dir_proof=None,
                )
            dir_row = self.frontier_db.execute(
                'SELECT expected_total,seen_count,next_offset,last_cursor,ids_digest,proof_task,proof_version '
                'FROM scan_dirs WHERE source=? AND scan_generation=? AND dir_key=?',
                (run['source'], gen, node['node_key']),
            ).fetchone()
            dir_proof = (
                dict(
                    expected_total=dir_row['expected_total'],
                    seen_count=dir_row['seen_count'],
                    next_offset=dir_row['next_offset'],
                    last_cursor=dir_row['last_cursor'],
                    ids_digest=dir_row['ids_digest'],
                    proof_task=dir_row['proof_task'],
                    proof_version=dir_row['proof_version'],
                )
                if dir_row is not None
                else dict(
                    expected_total=None,
                    seen_count=0,
                    next_offset=0,
                    last_cursor=None,
                    ids_digest='',
                    proof_task='',
                    proof_version=FRONTIER_PROOF_VERSION,
                )
            )
            return dict(
                empty=False,
                state=dict(fstate),
                node=dict(node),
                queued=queued,
                expected_total=dir_proof['expected_total'],
                dir_proof=dir_proof,
            )

    def frontier_has_entry_overlap(self, task, dir_key, entry_sigs):
        if not entry_sigs:
            return False
        with self.lock:
            run = self._scan(task)
            fstate = self.frontier_db.execute(
                'SELECT scan_generation FROM scan_state WHERE source=? AND last_task=?',
                (run['source'], task),
            ).fetchone()
            if fstate is None:
                return False
            placeholders = ','.join('?' for _ in entry_sigs)
            return self.frontier_db.execute(
                f'SELECT 1 FROM scan_page_entries WHERE source=? AND scan_generation=? AND dir_key=? AND entry_sig IN ({placeholders}) LIMIT 1',
                (run['source'], fstate['scan_generation'], dir_key, *entry_sigs),
            ).fetchone() is not None

    def frontier_has_cursor(self, task, dir_key, cursor):
        if not cursor:
            return False
        with self.lock:
            run = self._scan(task)
            fstate = self.frontier_db.execute(
                'SELECT scan_generation FROM scan_state WHERE source=? AND last_task=?',
                (run['source'], task),
            ).fetchone()
            if fstate is None:
                return False
            return self.frontier_db.execute(
                'SELECT 1 FROM scan_page_cursors WHERE source=? AND scan_generation=? AND dir_key=? AND cursor=? LIMIT 1',
                (run['source'], fstate['scan_generation'], dir_key, cursor),
            ).fetchone() is not None

    def frontier_known_dir(self, task, dir_key):
        with self.lock:
            run = self._scan(task)
            fstate = self.frontier_db.execute(
                'SELECT scan_generation FROM scan_state WHERE source=? AND last_task=?',
                (run['source'], task),
            ).fetchone()
            if fstate is None:
                return False
            return self.frontier_db.execute(
                'SELECT 1 FROM scan_dirs WHERE source=? AND scan_generation=? AND dir_key=?',
                (run['source'], fstate['scan_generation'], dir_key),
            ).fetchone() is not None

    def begin(self, task):
        with self.transaction():
            row = self._scan(task)
            if row['state'] != 'queued':
                raise ValueError('CATALOG_TASK_TERMINAL')
            self.db.execute("UPDATE scans SET state='running',updated=? WHERE id=?", (self.now(), task))

    def cancel(self, task, expected):
        with self.transaction():
            return self._request_cancel(self._scan(task, expected))

    def _request_cancel(self, row):
        if row['state'] not in TERMINAL:
            self.db.execute('UPDATE scans SET cancel_requested=1,updated=? WHERE id=?', (self.now(), row['id']))
        return scan_snapshot(self._scan(row['id']))

    @staticmethod
    def _mounted_task_matches(row, source_id, namespace):
        """Task control binds its saved root, not a live mount generation."""
        scope = row['scope']
        return row['provider'] in PATH_KINDS and (row['account'], row['source']) == (source_id, source_id) and (
            scope.get('reference_kind'), scope.get('source_id'), scope.get('namespace')) == (
                row['provider'], source_id, namespace)

    def cancel_mounted(self, task, source_id, namespace):
        identifier(source_id)
        identifier(namespace, 64)
        with self.transaction():
            row = self._scan(task)
            if not self._mounted_task_matches(row, source_id, namespace):
                raise ValueError('CATALOG_ACCOUNT_MISMATCH')
            return self._request_cancel(row)

    def batch(self, task, refs, checkpoint, scanned, descriptions=None):
        return self._batch(task, refs, checkpoint, scanned, mounted=False, descriptions=descriptions)

    def frontier_batch(self, task, refs, checkpoint, scanned, descriptions=None, *, frontier_step=None):
        return self._batch(task, refs, checkpoint, scanned, mounted=False, descriptions=descriptions, frontier_step=frontier_step)

    def mounted_batch(self, task, refs, checkpoint, scanned):
        return self._batch(task, refs, checkpoint, scanned, mounted=True)

    def _batch(self, task, refs, checkpoint, scanned, mounted, descriptions=None, frontier_step=None):
        if type(refs) is not list or len(refs) > 20 or type(scanned) is not int or not 0 <= scanned <= 20:
            raise ValueError('CATALOG_BATCH_INVALID')
        if mounted:
            from .typed_ref import validate as ref_validate
        else:
            ref_validate = validate
        refs = [ref_validate(ref) for ref in refs]
        from .server_description import checked, replace_candidate
        from .server_ref import PROVIDERS as SERVER_PROVIDERS
        descriptions = {} if descriptions is None else descriptions
        if (type(descriptions) is not dict or set(descriptions) - {ref['id'] for ref in refs}
                or descriptions and (mounted or any(ref['provider'] not in SERVER_PROVIDERS for ref in refs))):
            raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
        descriptions = {ref['id']: checked(descriptions[ref['id']], ref) if descriptions[ref['id']] is not None else None
                        for ref in refs if ref['id'] in descriptions}
        checkpoint_raw = encode(checkpoint)
        if len(checkpoint_raw.encode()) > 8192:
            raise ValueError('CATALOG_CHECKPOINT_LIMIT')
        with self.transaction():
            run = self._scan(task)
            if run['state'] != 'running' or run['cancel_requested']:
                raise ValueError('CATALOG_SCAN_STOPPED')
            fstate = None if mounted else self.frontier_db.execute(
                'SELECT * FROM scan_state WHERE source=? AND last_task=?',
                (run['source'], task),
            ).fetchone()
            membership_gen = fstate['scan_generation'] if fstate is not None else task
            # Duplicate committed page retries are no-ops, including counts.
            batch_key = checkpoint_raw if frontier_step is None else encode([checkpoint, frontier_step.get('pop_seqs') or frontier_step.get('pop_seq')])
            batch_id = hashlib.sha256(batch_key.encode()).hexdigest()
            if self.db.execute('SELECT 1 FROM scan_batches WHERE task=? AND digest=?', (task, batch_id)).fetchone():
                return
            discovered, changed = 0, False
            active = self.db.execute('SELECT active FROM catalog_sources WHERE source=?', (run['source'],)).fetchone()
            self.db.execute('INSERT INTO catalog_sources VALUES(?,1) ON CONFLICT(source) DO UPDATE SET active=1', (run['source'],))
            if active and not active[0]:
                # Reactivating a registered source changes availability for
                # existing memberships even if this first page is empty.
                changed = self.db.execute('SELECT 1 FROM memberships WHERE source=? LIMIT 1',
                    (run['source'],)).fetchone() is not None
            for ref in refs:
                identity_scope = (ref['reference_kind'], ref['source_id']) if mounted else (ref['provider'], ref['account_id'])
                if identity_scope != (run['provider'], run['account']):
                    raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                ref_changed = False
                if mounted:
                    if (ref['namespace'], ref.get('mount_generation', ref.get('source_generation'))) != (run['scope']['namespace'], run['scope']['generation']):
                        raise ValueError('CATALOG_AUTHORITY_CHANGED')
                    point = self.db.execute('SELECT 1 FROM temp.scan_point_observations WHERE task=? AND file=?',
                        (task, ref['id'])).fetchone()
                    if not point:
                        previous_ref = self.db.execute('SELECT ref FROM typed_objects WHERE id=?', (ref['id'],)).fetchone()
                        if previous_ref:
                            self._remember_observation(json.loads(previous_ref[0]))
                        self._remember_observation(ref)
                        ref_changed = previous_ref is None or json.loads(previous_ref[0]) != ref
                        if ref_changed:
                            self.db.execute('INSERT INTO typed_objects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET ref=excluded.ref',
                                (ref['id'], ref['source_id'], ref['namespace'], encode(ref)))
                else:
                    previous_ref = self.db.execute('SELECT ref FROM objects WHERE id=?', (ref['id'],)).fetchone()
                    ref_changed = previous_ref is None or json.loads(previous_ref[0]) != ref
                    if ref_changed:
                        self.db.execute('INSERT INTO objects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET ref=excluded.ref',
                            (ref['id'], ref['provider'], ref['account_id'], encode(ref)))
                previous = self.db.execute('SELECT generation,available FROM memberships WHERE source=? AND file=?', (run['source'], ref['id'])).fetchone()
                discovered += int(previous is None or previous[0] != membership_gen)
                self.db.execute('INSERT INTO memberships VALUES(?,?,?,1) ON CONFLICT(source,file) DO UPDATE SET generation=excluded.generation,available=1',
                    (run['source'], ref['id'], membership_gen))
                state, reason, candidates = review.suggestion(ref['name'])
                self.db.execute("INSERT OR IGNORE INTO reviews VALUES(?,?,?,?,0,NULL,'filename')",
                    (ref['id'], state, reason, encode(candidates)))
                description_changed = False
                if ref['id'] in descriptions:
                    before = self.db.execute('SELECT candidates FROM reviews WHERE file=?', (ref['id'],)).fetchone()[0]
                    after = encode(replace_candidate(json.loads(before), descriptions[ref['id']]))
                    description_changed = before != after
                    if description_changed:
                        self.db.execute('UPDATE reviews SET candidates=? WHERE file=?', (after, ref['id']))
                if ref_changed or description_changed:
                    self.db.execute('INSERT INTO object_times VALUES(?,?,?) ON CONFLICT(file) DO UPDATE SET updated=excluded.updated',
                        (ref['id'], self.now(), self.now()))
                    catalog_query.project(self.db, ref['id'])
                changed = changed or ref_changed or description_changed or previous is None or not previous['available']
            if changed:
                self._changed(run['scope'])
            now = self.now()
            pages_delta = int(frontier_step.get('pages_delta', 1)) if frontier_step is not None else 1
            self.db.execute('UPDATE scans SET pages=pages+?,scanned=scanned+?,discovered=discovered+?,checkpoint=?,updated=? WHERE id=?',
                (pages_delta, scanned, discovered, checkpoint_raw, now, task))
            self.db.execute('INSERT INTO scan_batches VALUES(?,?)', (task, batch_id))
            if frontier_step is not None and fstate is not None:
                sgen = fstate['scan_generation']
                src = run['source']
                pop_seqs = frontier_step.get('pop_seqs') or [frontier_step['pop_seq']]
                with self.frontier_db:
                    self.frontier_db.executemany(
                        'DELETE FROM scan_nodes WHERE source=? AND scan_generation=? AND seq=?',
                        [(src, sgen, s) for s in pop_seqs],
                    )
                    continuations = frontier_step.get('continuations')
                    if continuations is None:
                        continuations = [frontier_step['continuation']] if frontier_step.get('continuation') is not None else []
                    if not frontier_step['is_leaf']:
                        drow = self.frontier_db.execute(
                            'SELECT expected_total,seen_count,next_offset,ids_digest FROM scan_dirs WHERE source=? AND scan_generation=? AND dir_key=?',
                            (src, sgen, frontier_step['dir_key']),
                        ).fetchone()
                        prev_digest = drow['ids_digest'] if drow is not None else ''
                        prev_seen = drow['seen_count'] if drow is not None else 0
                        prev_total = drow['expected_total'] if drow is not None else None
                        new_total = frontier_step.get('declared_total') if frontier_step.get('declared_total') is not None else prev_total
                        page_count = int(frontier_step.get('page_item_count', scanned))
                        new_seen = prev_seen + page_count
                        new_offset = int(frontier_step.get('next_offset', new_seen))
                        next_cur = continuations[0].get('cursor') if continuations else None
                        sig_digest = hashlib.sha256((prev_digest + '\n' + encode(frontier_step.get('entry_sigs') or [])).encode()).hexdigest()
                        self.frontier_db.execute(
                            'UPDATE scan_dirs SET expected_total=?,seen_count=?,next_offset=?,last_cursor=?,ids_digest=?,proof_task=?,proof_version=? '
                            'WHERE source=? AND scan_generation=? AND dir_key=?',
                            (new_total, new_seen, new_offset, next_cur, sig_digest, task, FRONTIER_PROOF_VERSION, src, sgen, frontier_step['dir_key']),
                        )
                    if frontier_step.get('entry_sigs') and continuations:
                        self.frontier_db.executemany(
                            'INSERT OR IGNORE INTO scan_page_entries VALUES(?,?,?,?)',
                            [(src, sgen, frontier_step['dir_key'], sig) for sig in frontier_step['entry_sigs']],
                        )
                    for leaf_key, leaf_depth in frontier_step.get('new_leaves', ()):
                        self.frontier_db.execute(
                            'INSERT INTO scan_nodes(source,scan_generation,priority,node_key,depth,leaf,next_page,cursor) VALUES(?,?,0,?,?,1,1,NULL)',
                            (src, sgen, leaf_key, leaf_depth),
                        )
                    for dir_key, dir_depth in frontier_step.get('new_dirs', ()):
                        self.frontier_db.execute(
                            'INSERT OR IGNORE INTO scan_dirs('
                            'source,scan_generation,dir_key,depth,expected_total,seen_count,next_offset,last_cursor,ids_digest,proof_task,proof_version'
                            ') VALUES(?,?,?,?,NULL,0,0,NULL,?,?,?)',
                            (src, sgen, dir_key, dir_depth, '', '', FRONTIER_PROOF_VERSION),
                        )
                        self.frontier_db.execute(
                            'INSERT INTO scan_nodes(source,scan_generation,priority,node_key,depth,leaf,next_page,cursor) VALUES(?,?,1,?,?,0,1,NULL)',
                            (src, sgen, dir_key, dir_depth),
                        )
                    for cont in continuations:
                        if cont.get('cursor') is not None:
                            self.frontier_db.execute(
                                'INSERT OR IGNORE INTO scan_page_cursors VALUES(?,?,?,?)',
                                (src, sgen, cont['node_key'], cont['cursor']),
                            )
                        self.frontier_db.execute(
                            'INSERT INTO scan_nodes(source,scan_generation,priority,node_key,depth,leaf,next_page,cursor) VALUES(?,?,?,?,?,?,?,?)',
                            (src, sgen, cont['priority'], cont['node_key'], cont['depth'], cont['leaf'], cont['next_page'], cont['cursor']),
                        )
                    if not continuations:
                        finished_keys = (
                            frontier_step.get('finished_leaf_keys') or [frontier_step['dir_key']]
                            if frontier_step['is_leaf']
                            else [frontier_step['dir_key']]
                        )
                        self.frontier_db.executemany(
                            'DELETE FROM scan_page_entries WHERE source=? AND scan_generation=? AND dir_key=?',
                            [(src, sgen, fk) for fk in finished_keys],
                        )
                        self.frontier_db.executemany(
                            'DELETE FROM scan_page_cursors WHERE source=? AND scan_generation=? AND dir_key=?',
                            [(src, sgen, fk) for fk in finished_keys],
                        )
                    queued_cnt = self.frontier_db.execute(
                        'SELECT count(*) FROM scan_nodes WHERE source=? AND scan_generation=?',
                        (src, sgen),
                    ).fetchone()[0]
                    if queued_cnt > 65536:
                        raise ValueError('SCAN_FRONTIER_LIMIT')
                    new_latch = 1 if (fstate['partial_latch'] or frontier_step.get('partial_latch')) else 0
                    self.frontier_db.execute(
                        'UPDATE scan_state SET last_batch=?,last_batch_task=?,dir_count=?,partial_latch=?,proof_version=?,updated=? WHERE source=?',
                        (batch_id, task, frontier_step['dir_count'], new_latch, FRONTIER_PROOF_VERSION, now, src),
                    )

    def finish(self, task, state, reason=''):
        if state not in TERMINAL or not re.fullmatch('[A-Z_]{0,64}', reason):
            raise ValueError('CATALOG_TASK_STATE')
        with self.transaction():
            row = self._scan(task)
            if row['state'] in TERMINAL:
                return scan_snapshot(row)
            fstate = self.frontier_db.execute(
                'SELECT * FROM scan_state WHERE source=? AND last_task=?',
                (row['source'], task),
            ).fetchone()
            if row['cancel_requested'] and state == 'completed':
                state, reason = 'canceled', 'CANCEL_CONFIRMED'
            scan_gen = fstate['scan_generation'] if fstate is not None else task
            if state == 'completed' and fstate is not None:
                partial_latch = bool(fstate['partial_latch'])
                resumed = bool(fstate['resumed'])
                with self.frontier_db:
                    self._clear_frontier(row['source'])
                if partial_latch:
                    state, reason = 'interrupted', 'SCAN_DIRECTORY_LIMIT'
                elif resumed:
                    # Multi-run resumed scans without an immutable upstream snapshot
                    # publish all newly discovered/updated members, but never withdraw
                    # unseen members as absent (REV-07).
                    state, reason = 'interrupted', 'SCAN_RESUMED_PARTIAL'
            elif fstate is not None and reason in {
                'PAN_INCOMPLETE_PAGE',
                'PAN_PAGE_EXPIRED',
                'SCAN_TOTAL_CHANGED',
                'SCAN_PAGE_CYCLE',
                'SCAN_CURSOR_CYCLE',
                'SCAN_INVALID_PAGE',
                'SCAN_FRONTIER_LIMIT',
                'ACCOUNT_REVOKED',
                'PROFILE_CHANGED',
                'CATALOG_AUTHORITY_CHANGED',
            }:
                with self.frontier_db:
                    self._clear_frontier(row['source'])
            if state == 'completed':
                missing = self.db.execute('UPDATE memberships SET available=0 WHERE source=? AND generation!=? AND available=1 AND NOT EXISTS('
                    'SELECT 1 FROM temp.scan_point_observations p WHERE p.task=? AND p.file=memberships.file)',
                    (row['source'], scan_gen, task))
                if missing.rowcount:
                    self._changed(row['scope'])
            self.db.execute('DELETE FROM temp.scan_point_observations WHERE task=?', (task,))
            self.db.execute('UPDATE scans SET state=?,reason=?,updated=? WHERE id=?', (state, reason, self.now(), task))
            return scan_snapshot(self._scan(task))

    def jobs(self, expected, task=None, offset=0, limit=PAGE_SIZE):
        page(offset, limit)
        with self.lock:
            if task is not None:
                return dict(items=[scan_snapshot(self._scan(task, expected))], next_offset=None)
            ids = self.db.execute('SELECT id FROM scans WHERE provider=? AND account=? ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?',
                (*catalog_query.scope_key(expected)[:2], limit + 1, offset)).fetchall()
            return dict(items=[scan_snapshot(self._scan(row[0])) for row in ids[:limit]],
                        next_offset=offset + limit if len(ids) > limit else None)

    def mounted_jobs(self, source_id, namespace, task=None, offset=0, limit=PAGE_SIZE):
        """Observe saved tasks without granting file-read or playback authority.

        A Registry source ID may be edited to a different root. Match the saved
        namespace as well; remounting the same root does not hide its old jobs.
        Job history is independently bounded by MAX_JOBS, not the media count.
        """
        identifier(source_id)
        identifier(namespace, 64)
        page(offset, limit)
        with self.lock:
            if task is not None:
                row = self._scan(task)
                if not self._mounted_task_matches(row, source_id, namespace):
                    raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                return dict(items=[scan_snapshot(row)], next_offset=None)
            ids = self.db.execute('SELECT id FROM scans WHERE provider IN (' + ','.join('?' for _ in PATH_KINDS) + ') AND account=? AND source=? '
                'ORDER BY updated DESC,id DESC LIMIT ?', (*PATH_KINDS, source_id, source_id, MAX_JOBS)).fetchall()
            rows = [self._scan(row[0]) for row in ids]
            rows = [row for row in rows if self._mounted_task_matches(row, source_id, namespace)]
            return dict(items=[scan_snapshot(row) for row in rows[offset:offset + limit]],
                next_offset=offset + limit if len(rows) > offset + limit else None)

    def source_observation(self, expected, source_id):
        """Bounded saved observation, not a live directory or playback probe.

        Coverage describes the latest retained task only. A point recheck can
        restore a file, but cannot turn a partial traversal into a full one.
        Kernel mount generation is presentation evidence supplied by the host.
        """
        source_id = identifier(source_id)
        provider, account, namespace = catalog_query.scope_key(expected)[:3]
        mounted = provider in PATH_KINDS
        if mounted and source_id != account:
            raise ValueError('CATALOG_ACCOUNT_MISMATCH')
        with self.lock:
            ids = self.db.execute('SELECT id FROM scans WHERE provider=? AND account=? AND source=? '
                'ORDER BY updated DESC,id DESC LIMIT ?', (provider, account, source_id, MAX_JOBS)).fetchall()
            runs = (self._scan(row[0]) for row in ids)
            latest = next((row for row in runs if not mounted or
                self._mounted_task_matches(row, source_id, namespace)), None)
            job = scan_snapshot(latest) if latest else None
            clauses, args = ['p.provider=?', 'p.account=?', 'm.source=?'], [provider, account, source_id]
            if mounted:
                clauses.append('p.namespace=?')
                args.append(namespace)
            # Start at this source's indexed memberships, not the account-wide
            # projection for every card in a multi-source account.
            counts = self.db.execute('SELECT COUNT(*),COALESCE(SUM(m.available),0),'
                'COALESCE(SUM(m.available=1 AND p.authority_generation!=?),0) FROM memberships m '
                'CROSS JOIN catalog_rows p ON p.id=m.file WHERE ' + ' AND '.join(clauses),
                [expected.get('generation', '')] + args).fetchone()
            generation_changed = bool(mounted and expected.get('generation') and (counts[2] or
                latest and latest['scope'].get('generation') != expected['generation']))
            unavailable = mounted and not expected.get('generation')
            availability = ('source_unavailable' if unavailable else 'unverified'
                if generation_changed or not latest else 'observed_present')
            # A failed remote read is not proof of an empty source. Keep the
            # saved files and mark the observation as requiring another scan.
            if latest and latest['state'] in ('failed', 'interrupted') and not unavailable:
                availability = 'unverified'
            return dict(latest_job=job, coverage='never' if not latest else
                'complete' if latest['state'] == 'completed' else 'partial',
                availability=availability, recheck_required=bool(unavailable or generation_changed or
                    not latest or latest['state'] != 'completed'), indexed_count=counts[0],
                present_count=counts[1], absent_count=counts[0] - counts[1])

    def _item(self, file, expected, include_supplement=True):
        if expected.get('reference_kind') in PATH_KINDS:
            row = self.db.execute('SELECT o.ref,r.* FROM typed_objects o JOIN reviews r ON o.id=r.file '
                'WHERE o.id=? AND o.source=? AND o.namespace=?',
                (identifier(file, 64), expected['source_id'], expected['namespace'])).fetchone()
        else:
            row = self.db.execute('SELECT o.ref,r.* FROM objects o JOIN reviews r ON o.id=r.file WHERE o.id=? AND o.provider=? AND o.account=?',
                (identifier(file, 64), expected['provider'], expected['account_id'])).fetchone()
        if row is None:
            raise ValueError('CATALOG_FILE_NOT_FOUND')
        available = bool(self.db.execute('SELECT 1 FROM memberships m JOIN catalog_sources s ON s.source=m.source '
            'WHERE m.file=? AND m.available=1 AND s.active=1 LIMIT 1', (file,)).fetchone())
        result = dict(file_ref=json.loads(row['ref']), state=row['state'], reason=row['reason'],
                    candidates=json.loads(row['candidates']), revision=row['revision'],
                    mapping=json.loads(row['mapping']) if row['mapping'] else None, provenance=row['provenance'],
                    available=available)
        if (expected.get('reference_kind') in PATH_KINDS and
                result['file_ref'].get('reference_kind') != expected['reference_kind']):
            raise ValueError('CATALOG_FILE_NOT_FOUND')
        if include_supplement:
            from .catalog_supplements import stored, summary
            relation = stored(self, file)
            if relation:
                result['supplement'] = summary(self, expected, relation)
        from .catalog_segments import stored as stored_segments, summary as segments_summary
        segments = stored_segments(self, file)
        if segments is not None:
            result['segments'] = segments_summary(result, segments, expected)
        return result

    def item(self, expected, file_id):
        with self.lock:
            return self._public(self._item(file_id, expected))

    @staticmethod
    def _receipt_scope(expected):
        if expected.get('reference_kind') in PATH_KINDS:
            return (expected['reference_kind'], catalog_query.opaque(expected['source_id'], expected['namespace']))
        return expected['provider'], expected['account_id']

    @staticmethod
    def _public(item):
        ref = item['file_ref']
        return dict({k: v for k, v in item.items() if k != 'file_ref'}, file=dict(
            id=ref['id'], name=ref['name'][:240], parent=ref['parent'][:240],
            observation_key=catalog_query.opaque(ref),
            truncated=len(ref['name']) > 240 or len(ref['parent']) > 240))

    def items(self, expected, source=None, state=None, offset=0, limit=PAGE_SIZE):
        page(offset, limit)
        mounted = expected.get('reference_kind') in PATH_KINDS
        where, args = ('o.source=? AND o.namespace=?', [expected['source_id'], expected['namespace']]) if mounted else (
            'o.provider=? AND o.account=?', [expected['provider'], expected['account_id']])
        if source is not None:
            where += ' AND EXISTS(SELECT 1 FROM memberships m WHERE m.file=o.id AND m.source=? AND m.available=1)'
            args.append(identifier(source))
        if state is not None:
            if state not in review.STATES:
                raise ValueError('CATALOG_REVIEW_STATE')
            where += ' AND r.state=?'
            args.append(state)
        with self.lock:
            rows = self.db.execute('SELECT o.id FROM ' + ('typed_objects' if mounted else 'objects') +
                ' o JOIN reviews r ON r.file=o.id WHERE ' + where + ' ORDER BY o.id LIMIT ? OFFSET ?',
                tuple(args + [limit + 1, offset])).fetchall()
            items = []
            for row in rows[:limit]:
                candidate = self._public(self._item(row[0], expected))
                if len(encode(dict(items=items + [candidate], next_offset=offset + len(items) + 1)).encode('utf-8')) > REPLY_BYTES:
                    if not items:
                        raise ValueError('CATALOG_REPLY_LIMIT')
                    break
                items.append(candidate)
            return dict(items=items, next_offset=offset + len(items) if len(rows) > len(items) else None)

    def preview(self, expected, commands):
        if type(commands) is not list or not 1 <= len(commands) <= PAGE_SIZE:
            raise ValueError('CATALOG_BATCH_LIMIT')
        results = []
        with self.lock:
            for raw in commands:
                try:
                    cmd = review.command(raw)
                    item = self._item(cmd['file_id'], expected)
                    state, after = self._target(cmd, item)
                    from .catalog_supplements import stored, target, summary
                    relation = target(self, expected, cmd, item)
                    from .catalog_segments import target as segments_target, summary as segments_summary
                    segments = segments_target(self, expected, cmd, item)
                    result = dict(status='ready' if item['revision'] == cmd['expected_revision'] else 'conflict',
                        file=self._public(item)['file'], revision=item['revision'], before=item['mapping'],
                        after=after, before_state=item['state'], after_state=state, action=cmd['action'])
                    if relation or item.get('supplement') or cmd['action'] in ('supplement', 'detach_supplement'):
                        result.update(before_supplement=item.get('supplement'), after_supplement=summary(self, expected, relation))
                    if segments or item.get('segments') or cmd['action'] == 'segments':
                        result.update(before_segments=item.get('segments'), after_segments=segments_summary(item, segments, expected))
                    results.append(result)
                except ValueError:
                    results.append(dict(status='failed', reason='INVALID_OR_MISSING_ITEM'))
        result = dict(items=results)
        if len(encode(result).encode('utf-8')) > REPLY_BYTES:
            raise ValueError('CATALOG_REPLY_LIMIT')
        return result

    def _target(self, cmd, item):
        if cmd['action'] == 'restore_description':
            value = cmd['mapping']
            # Checking the imported observation again inside the transaction
            # prevents same-revision file replacement between preview/apply.
            if (not item['available'] or item.get('supplement') is not None and 'supplement' not in value or
                    value['reference'] != item['file_ref']):
                raise ValueError('CATALOG_FILE_CHANGED')
            return value['state'], value['mapping']
        if cmd['action'] in ('supplement', 'detach_supplement', 'segments'):
            return item['state'], item['mapping']
        state = {'confirm': 'confirmed', 'ignore': 'ignored', 'unbind': 'unmatched', 'undo': 'unmatched'}[cmd['action']]
        after = cmd['mapping']
        if after is not None and after['kind'] == 'custom':
            state = 'unmatched'  # Named locally, still no catalog identity.
        if cmd['action'] == 'undo':
            change = self.db.execute('SELECT * FROM review_changes WHERE file=? AND revision=?', (cmd['file_id'], item['revision'])).fetchone()
            if change is None:
                raise ValueError('CATALOG_NO_UNDO')
            state = change['before_state']
            after = json.loads(change['before_mapping']) if change['before_mapping'] else None
        return state, after

    def apply(self, expected, request_id, commands):
        identifier(request_id)
        if type(commands) is not list or not 1 <= len(commands) <= PAGE_SIZE:
            raise ValueError('CATALOG_BATCH_LIMIT')
        receipt_scope = self._receipt_scope(expected)
        envelope = hashlib.sha256(encode([*receipt_scope, commands]).encode()).hexdigest()
        with self.transaction():
            prior = self.db.execute('SELECT digest FROM review_requests WHERE request=?', (request_id,)).fetchone()
            legacy = prior is None and self.db.execute('SELECT 1 FROM review_receipts WHERE request=? LIMIT 1', (request_id,)).fetchone()
            if legacy or prior is not None and prior[0] != envelope:
                return dict(items=[dict(status='conflict', reason='REQUEST_ID_REUSED') for _ in commands])
            self.db.execute('INSERT OR IGNORE INTO review_requests VALUES(?,?)', (request_id, envelope))
            self.db.execute('DELETE FROM review_requests WHERE rowid IN '
                '(SELECT rowid FROM review_requests ORDER BY rowid DESC LIMIT -1 OFFSET 1024)')
        results = []
        for index, raw in enumerate(commands):
            digest = hashlib.sha256(encode([*receipt_scope, raw]).encode()).hexdigest()
            with self.transaction():
                receipt = self.db.execute('SELECT digest,result FROM review_receipts WHERE request=? AND item=?', (request_id, index)).fetchone()
                if receipt:
                    results.append(json.loads(receipt['result']) if receipt['digest'] == digest else dict(status='conflict', reason='REQUEST_ID_REUSED'))
                    continue
                # A review spans descriptive state, supplements, segments and
                # query projection. A late domain rejection must roll all of
                # them back while still retaining its failed-item receipt.
                self.db.execute('SAVEPOINT review_item')
                try:
                    cmd = review.command(raw)
                    item = self._item(cmd['file_id'], expected)
                    if item['revision'] != cmd['expected_revision']:
                        result = dict(status='conflict', revision=item['revision'])
                    else:
                        state, after = self._target(cmd, item)
                        from .catalog_supplements import stored, target, write
                        relation_before = stored(self, cmd['file_id'])
                        relation_after = target(self, expected, cmd, item)
                        from .catalog_segments import stored as stored_segments, target as segments_target, write as write_segments
                        segments_before = stored_segments(self, cmd['file_id'])
                        segments_after = segments_target(self, expected, cmd, item)
                        revision = item['revision'] + 1
                        self.db.execute('INSERT INTO review_changes VALUES(?,?,?,?,?,?)',
                            (cmd['file_id'], revision, item['state'], encode(item['mapping']) if item['mapping'] else None,
                             state, encode(after) if after else None))
                        self.db.execute("UPDATE reviews SET state=?,mapping=?,revision=?,provenance='manual',reason='MANUAL_METADATA_ONLY' WHERE file=?",
                            (state, encode(after) if after else None, revision, cmd['file_id']))
                        write(self, cmd['file_id'], revision, relation_before, relation_after)
                        write_segments(self, cmd['file_id'], revision, segments_before, segments_after)
                        # The newest 32 revisions suffice for bounded per-file undo.
                        self.db.execute('DELETE FROM review_changes WHERE file=? AND revision<?', (cmd['file_id'], revision - 31))
                        self.db.execute('UPDATE object_times SET updated=? WHERE file=?', (self.now(), cmd['file_id']))
                        catalog_query.project(self.db, cmd['file_id'])
                        self._changed(expected)
                        result = dict(status='applied', revision=revision)
                except ValueError:
                    self.db.execute('ROLLBACK TO review_item')
                    result = dict(status='failed', reason='INVALID_OR_MISSING_ITEM')
                self.db.execute('RELEASE review_item')
                self.db.execute('INSERT INTO review_receipts VALUES(?,?,?,?,?)', (request_id, index, digest, encode(result), self.now()))
                self.db.execute('INSERT INTO review_receipt_scopes VALUES(?,?,?,?)',
                    (request_id, index, *receipt_scope))
                self.db.execute('DELETE FROM review_receipts WHERE rowid IN (SELECT rowid FROM review_receipts ORDER BY updated DESC,rowid DESC LIMIT -1 OFFSET 1024)')
                self.db.execute('DELETE FROM review_receipt_scopes WHERE NOT EXISTS('
                    'SELECT 1 FROM review_receipts r WHERE r.request=review_receipt_scopes.request AND r.item=review_receipt_scopes.item)')
                results.append(result)
        return dict(items=results)
