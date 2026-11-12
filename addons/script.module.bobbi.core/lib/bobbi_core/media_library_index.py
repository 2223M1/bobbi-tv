"""Independent local index. File identity, membership and mapping are separate.

SQLite batches include their checkpoint. Only a closed full generation can
mark absent memberships unavailable; incomplete scans preserve prior members.
There are no credentials, playable URLs or provider mutation operations here.
"""
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
    def __init__(self, path, now=time.time):
        self.path, self.now, self.lock = Path(path), now, RLock()
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('CATALOG_STORAGE_UNSAFE')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(str(self.path), timeout=.15, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError('CATALOG_SCHEMA_UNSUPPORTED')
            if version == 1:
                # Additive migration. Old binaries reject schema 2 instead of
                # accidentally writing stale projections. Keep a consistent
                # pre-migration backup; never overwrite a prior recovery point.
                backup = Path(str(self.path) + '.schema1.bak')
                if backup.is_symlink():
                    raise ValueError('CATALOG_STORAGE_UNSAFE')
                if not backup.exists():
                    fd = os.open(str(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                    target = sqlite3.connect(str(backup))
                    try:
                        self.db.backup(target)
                    finally:
                        target.close()
                # A failed/interrupted earlier copy may have left an empty or
                # partial destination. Its existence alone is not a recovery
                # point and must never allow a later attempt to migrate.
                target = sqlite3.connect(backup.resolve().as_uri() + '?mode=ro', uri=True)
                try:
                    if (target.execute('PRAGMA user_version').fetchone()[0] != 1
                            or target.execute('PRAGMA quick_check').fetchone()[0] != 'ok'):
                        raise ValueError('CATALOG_STORAGE_UNSAFE')
                except sqlite3.Error:
                    raise ValueError('CATALOG_STORAGE_UNSAFE') from None
                finally:
                    target.close()
            with self.transaction():
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
                self.db.execute('PRAGMA user_version=2')
            self.query_reader = catalog_query.CatalogQuery(self)
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield

    def close(self):
        with self.lock:
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
        self.db.execute('INSERT OR REPLACE INTO catalog_meta VALUES(1,?,?,?)',
            (catalog_query.PROJECTION_SCHEMA, uuid4().hex, revision))

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

    def has_mounted_items(self, source_id, namespace):
        with self.lock:
            return self.db.execute('SELECT 1 FROM typed_objects WHERE source=? AND namespace=? LIMIT 1',
                (identifier(source_id), identifier(namespace, 64))).fetchone() is not None

    def trusted_file(self, expected, object_id):
        """Host-only reference lookup, not a public query response."""
        with self.lock:
            return validate(self._item(object_id, expected)['file_ref'])

    def trusted_mounted_file(self, authority, object_id):
        from .mounted_ref import validate as mounted_validate
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
        from .mounted_ref import validate as mounted_validate
        reference = mounted_validate(reference)
        with self.transaction():
            previous = self.trusted_mounted_file(authority, reference['id'])
            if (reference['source_id'], reference['namespace'], reference['mount_generation']) != (
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
        # No provider proves a replayable cursor. Preserve the last committed
        # checkpoint for diagnosis, and require an explicit fresh generation.
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
            else:
                self.db.execute('UPDATE memberships SET available=0')
            if previous != set(sources):
                changed_sources = previous.symmetric_difference(sources)
                for row in self.db.execute('SELECT DISTINCT p.provider,p.account,p.namespace FROM catalog_rows p '
                        'JOIN memberships m ON m.file=p.id WHERE m.source IN (' +
                        ','.join('?' for _ in changed_sources) + ')', tuple(changed_sources)).fetchall():
                    self._changed(dict(reference_kind='mounted_path', source_id=row['account'], namespace=row['namespace'])
                        if row['provider'] == 'mounted_path' else dict(provider=row['provider'], account_id=row['account']))

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
            task = uuid4().hex
            self.db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (task, source, encode(expected), *catalog_query.scope_key(expected)[:2],
                 'queued', 0, 0, 0, 0, '{}', '', self.now()))
        return task

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
        return (row['provider'], row['account'], row['source']) == ('mounted_path', source_id, source_id) and (
            scope.get('reference_kind'), scope.get('source_id'), scope.get('namespace')) == (
                'mounted_path', source_id, namespace)

    def cancel_mounted(self, task, source_id, namespace):
        identifier(source_id)
        identifier(namespace, 64)
        with self.transaction():
            row = self._scan(task)
            if not self._mounted_task_matches(row, source_id, namespace):
                raise ValueError('CATALOG_ACCOUNT_MISMATCH')
            return self._request_cancel(row)

    def batch(self, task, refs, checkpoint, scanned):
        return self._batch(task, refs, checkpoint, scanned, mounted=False)

    def mounted_batch(self, task, refs, checkpoint, scanned):
        return self._batch(task, refs, checkpoint, scanned, mounted=True)

    def _batch(self, task, refs, checkpoint, scanned, mounted):
        if type(refs) is not list or len(refs) > 20 or type(scanned) is not int or not 0 <= scanned <= 20:
            raise ValueError('CATALOG_BATCH_INVALID')
        if mounted:
            from .mounted_ref import validate as ref_validate
        else:
            ref_validate = validate
        refs = [ref_validate(ref) for ref in refs]
        checkpoint_raw = encode(checkpoint)
        if len(checkpoint_raw.encode()) > 8192:
            raise ValueError('CATALOG_CHECKPOINT_LIMIT')
        with self.transaction():
            run = self._scan(task)
            if run['state'] != 'running' or run['cancel_requested']:
                raise ValueError('CATALOG_SCAN_STOPPED')
            # Duplicate committed page retries are no-ops, including counts.
            batch_id = hashlib.sha256(checkpoint_raw.encode()).hexdigest()
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
                identity_scope = ('mounted_path', ref['source_id']) if mounted else (ref['provider'], ref['account_id'])
                if identity_scope != (run['provider'], run['account']):
                    raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                ref_changed = False
                if mounted:
                    if (ref['namespace'], ref['mount_generation']) != (run['scope']['namespace'], run['scope']['generation']):
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
                discovered += int(previous is None or previous[0] != task)
                self.db.execute('INSERT INTO memberships VALUES(?,?,?,1) ON CONFLICT(source,file) DO UPDATE SET generation=excluded.generation,available=1',
                    (run['source'], ref['id'], task))
                state, reason, candidates = review.suggestion(ref['name'])
                self.db.execute("INSERT OR IGNORE INTO reviews VALUES(?,?,?,?,0,NULL,'filename')",
                    (ref['id'], state, reason, encode(candidates)))
                if ref_changed:
                    self.db.execute('INSERT INTO object_times VALUES(?,?,?) ON CONFLICT(file) DO UPDATE SET updated=excluded.updated',
                        (ref['id'], self.now(), self.now()))
                    catalog_query.project(self.db, ref['id'])
                changed = changed or ref_changed or previous is None or not previous['available']
            if changed:
                self._changed(run['scope'])
            self.db.execute('UPDATE scans SET pages=pages+1,scanned=scanned+?,discovered=discovered+?,checkpoint=?,updated=? WHERE id=?',
                (scanned, discovered, checkpoint_raw, self.now(), task))
            self.db.execute('INSERT INTO scan_batches VALUES(?,?)', (task, batch_id))

    def finish(self, task, state, reason=''):
        if state not in TERMINAL or not re.fullmatch('[A-Z_]{0,64}', reason):
            raise ValueError('CATALOG_TASK_STATE')
        with self.transaction():
            row = self._scan(task)
            if row['state'] in TERMINAL:
                return scan_snapshot(row)
            if row['cancel_requested'] and state == 'completed':
                state, reason = 'canceled', 'CANCEL_CONFIRMED'
            if state == 'completed':
                missing = self.db.execute('UPDATE memberships SET available=0 WHERE source=? AND generation!=? AND available=1 AND NOT EXISTS('
                    'SELECT 1 FROM temp.scan_point_observations p WHERE p.task=? AND p.file=memberships.file)',
                    (row['source'], task, task))
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
            ids = self.db.execute("SELECT id FROM scans WHERE provider='mounted_path' AND account=? AND source=? "
                'ORDER BY updated DESC,id DESC LIMIT ?', (source_id, source_id, MAX_JOBS)).fetchall()
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
        provider, account, namespace = catalog_query.scope_key(expected)
        mounted = provider == 'mounted_path'
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

    def _item(self, file, expected):
        if expected.get('reference_kind') == 'mounted_path':
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
        return dict(file_ref=json.loads(row['ref']), state=row['state'], reason=row['reason'],
                    candidates=json.loads(row['candidates']), revision=row['revision'],
                    mapping=json.loads(row['mapping']) if row['mapping'] else None, provenance=row['provenance'],
                    available=available)

    def item(self, expected, file_id):
        with self.lock:
            return self._public(self._item(file_id, expected))

    @staticmethod
    def _receipt_scope(expected):
        if expected.get('reference_kind') == 'mounted_path':
            return ('mounted_path', catalog_query.opaque(expected['source_id'], expected['namespace']))
        return expected['provider'], expected['account_id']

    @staticmethod
    def _public(item):
        ref = item['file_ref']
        return dict({k: v for k, v in item.items() if k != 'file_ref'}, file=dict(
            id=ref['id'], name=ref['name'][:240], parent=ref['parent'][:240],
            truncated=len(ref['name']) > 240 or len(ref['parent']) > 240))

    def items(self, expected, source=None, state=None, offset=0, limit=PAGE_SIZE):
        page(offset, limit)
        mounted = expected.get('reference_kind') == 'mounted_path'
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
                    results.append(dict(status='ready' if item['revision'] == cmd['expected_revision'] else 'conflict',
                        file=self._public(item)['file'], revision=item['revision'], before=item['mapping'],
                        after=after, after_state=state, action=cmd['action']))
                except ValueError:
                    results.append(dict(status='failed', reason='INVALID_OR_MISSING_ITEM'))
        result = dict(items=results)
        if len(encode(result).encode('utf-8')) > REPLY_BYTES:
            raise ValueError('CATALOG_REPLY_LIMIT')
        return result

    def _target(self, cmd, item):
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
                try:
                    cmd = review.command(raw)
                    item = self._item(cmd['file_id'], expected)
                    if item['revision'] != cmd['expected_revision']:
                        result = dict(status='conflict', revision=item['revision'])
                    else:
                        state, after = self._target(cmd, item)
                        revision = item['revision'] + 1
                        self.db.execute('INSERT INTO review_changes VALUES(?,?,?,?,?,?)',
                            (cmd['file_id'], revision, item['state'], encode(item['mapping']) if item['mapping'] else None,
                             state, encode(after) if after else None))
                        self.db.execute("UPDATE reviews SET state=?,mapping=?,revision=?,provenance='manual',reason='MANUAL_METADATA_ONLY' WHERE file=?",
                            (state, encode(after) if after else None, revision, cmd['file_id']))
                        # The newest 32 revisions suffice for bounded per-file undo.
                        self.db.execute('DELETE FROM review_changes WHERE file=? AND revision<?', (cmd['file_id'], revision - 31))
                        self.db.execute('UPDATE object_times SET updated=? WHERE file=?', (self.now(), cmd['file_id']))
                        catalog_query.project(self.db, cmd['file_id'])
                        self._changed(expected)
                        result = dict(status='applied', revision=revision)
                except ValueError:
                    result = dict(status='failed', reason='INVALID_OR_MISSING_ITEM')
                self.db.execute('INSERT INTO review_receipts VALUES(?,?,?,?,?)', (request_id, index, digest, encode(result), self.now()))
                self.db.execute('INSERT INTO review_receipt_scopes VALUES(?,?,?,?)',
                    (request_id, index, *receipt_scope))
                self.db.execute('DELETE FROM review_receipts WHERE rowid IN (SELECT rowid FROM review_receipts ORDER BY updated DESC,rowid DESC LIMIT -1 OFFSET 1024)')
                self.db.execute('DELETE FROM review_receipt_scopes WHERE NOT EXISTS('
                    'SELECT 1 FROM review_receipts r WHERE r.request=review_receipt_scopes.request AND r.item=review_receipt_scopes.item)')
                results.append(result)
        return dict(items=results)
