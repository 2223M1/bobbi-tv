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
            if version not in (0, 1):
                raise ValueError('CATALOG_SCHEMA_UNSUPPORTED')
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
                ):
                    self.db.execute(sql)
                self.db.execute('PRAGMA user_version=1')
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

    def recover(self):
        # No provider proves a replayable cursor. Preserve the last committed
        # checkpoint for diagnosis, and require an explicit fresh generation.
        with self.transaction():
            self.db.execute("UPDATE scans SET state='interrupted',reason='SERVICE_RESTART',updated=? WHERE state IN ('queued','running')", (self.now(),))

    def retain_sources(self, sources):
        """Local explicit source removal, not an inference of remote deletion."""
        if type(sources) is not list or len(sources) > 32:
            raise ValueError('CATALOG_SOURCE_INVALID')
        sources = [identifier(value) for value in sources]
        with self.transaction():
            if sources:
                self.db.execute('UPDATE memberships SET available=0 WHERE source NOT IN (' +
                    ','.join('?' for _ in sources) + ')', sources)
            else:
                self.db.execute('UPDATE memberships SET available=0')

    def _scan(self, task, expected=None):
        row = self.db.execute('SELECT * FROM scans WHERE id=?', (identifier(task),)).fetchone()
        if row is None:
            raise ValueError('CATALOG_TASK_NOT_FOUND')
        result = dict(row, scope=json.loads(row['scope']), checkpoint=json.loads(row['checkpoint']))
        if expected is not None and (row['provider'], row['account']) != (expected['provider'], expected['account_id']):
            raise ValueError('CATALOG_ACCOUNT_MISMATCH')
        return result

    def start(self, source, expected):
        identifier(source)
        with self.transaction():
            active = self.db.execute("SELECT id FROM scans WHERE state IN ('queued','running')").fetchall()
            if active:
                raise ValueError('CATALOG_SCAN_BUSY')  # One low-priority worker.
            self.db.execute('DELETE FROM scans WHERE id IN (SELECT id FROM scans ORDER BY updated DESC,id DESC LIMIT -1 OFFSET ?)', (MAX_JOBS - 1,))
            self.db.execute('DELETE FROM scan_batches WHERE task NOT IN (SELECT id FROM scans)')
            task = uuid4().hex
            self.db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (task, source, encode(expected), expected['provider'], expected['account_id'],
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
            row = self._scan(task, expected)
            if row['state'] not in TERMINAL:
                self.db.execute('UPDATE scans SET cancel_requested=1,updated=? WHERE id=?', (self.now(), task))
            return scan_snapshot(self._scan(task))

    def batch(self, task, refs, checkpoint, scanned):
        if type(refs) is not list or len(refs) > 20 or type(scanned) is not int or not 0 <= scanned <= 20:
            raise ValueError('CATALOG_BATCH_INVALID')
        refs = [validate(ref) for ref in refs]
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
            discovered = 0
            for ref in refs:
                if (ref['provider'], ref['account_id']) != (run['provider'], run['account']):
                    raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                self.db.execute('INSERT INTO objects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET ref=excluded.ref',
                    (ref['id'], ref['provider'], ref['account_id'], encode(ref)))
                previous = self.db.execute('SELECT generation FROM memberships WHERE source=? AND file=?', (run['source'], ref['id'])).fetchone()
                discovered += int(previous is None or previous[0] != task)
                self.db.execute('INSERT INTO memberships VALUES(?,?,?,1) ON CONFLICT(source,file) DO UPDATE SET generation=excluded.generation,available=1',
                    (run['source'], ref['id'], task))
                state, reason, candidates = review.suggestion(ref['name'])
                self.db.execute("INSERT OR IGNORE INTO reviews VALUES(?,?,?,?,0,NULL,'filename')",
                    (ref['id'], state, reason, encode(candidates)))
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
                self.db.execute('UPDATE memberships SET available=0 WHERE source=? AND generation!=?', (row['source'], task))
            self.db.execute('UPDATE scans SET state=?,reason=?,updated=? WHERE id=?', (state, reason, self.now(), task))
            return scan_snapshot(self._scan(task))

    def jobs(self, expected, task=None, offset=0, limit=PAGE_SIZE):
        page(offset, limit)
        with self.lock:
            if task is not None:
                return dict(items=[scan_snapshot(self._scan(task, expected))], next_offset=None)
            ids = self.db.execute('SELECT id FROM scans WHERE provider=? AND account=? ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?',
                (expected['provider'], expected['account_id'], limit + 1, offset)).fetchall()
            return dict(items=[scan_snapshot(self._scan(row[0])) for row in ids[:limit]],
                        next_offset=offset + limit if len(ids) > limit else None)

    def _item(self, file, expected):
        row = self.db.execute('SELECT o.ref,r.* FROM objects o JOIN reviews r ON o.id=r.file WHERE o.id=? AND o.provider=? AND o.account=?',
            (identifier(file, 64), expected['provider'], expected['account_id'])).fetchone()
        if row is None:
            raise ValueError('CATALOG_FILE_NOT_FOUND')
        available = bool(self.db.execute('SELECT 1 FROM memberships WHERE file=? AND available=1 LIMIT 1', (file,)).fetchone())
        return dict(file_ref=json.loads(row['ref']), state=row['state'], reason=row['reason'],
                    candidates=json.loads(row['candidates']), revision=row['revision'],
                    mapping=json.loads(row['mapping']) if row['mapping'] else None, provenance=row['provenance'],
                    available=available)

    @staticmethod
    def _public(item):
        ref = item['file_ref']
        return dict({k: v for k, v in item.items() if k != 'file_ref'}, file=dict(
            id=ref['id'], name=ref['name'][:240], parent=ref['parent'][:240],
            truncated=len(ref['name']) > 240 or len(ref['parent']) > 240))

    def items(self, expected, source=None, state=None, offset=0, limit=PAGE_SIZE):
        page(offset, limit)
        where, args = 'o.provider=? AND o.account=?', [expected['provider'], expected['account_id']]
        if source is not None:
            where += ' AND EXISTS(SELECT 1 FROM memberships m WHERE m.file=o.id AND m.source=? AND m.available=1)'
            args.append(identifier(source))
        if state is not None:
            if state not in review.STATES:
                raise ValueError('CATALOG_REVIEW_STATE')
            where += ' AND r.state=?'
            args.append(state)
        with self.lock:
            rows = self.db.execute('SELECT o.id FROM objects o JOIN reviews r ON r.file=o.id WHERE ' + where + ' ORDER BY o.id LIMIT ? OFFSET ?',
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
        results = []
        for index, raw in enumerate(commands):
            digest = hashlib.sha256(encode([expected['provider'], expected['account_id'], raw]).encode()).hexdigest()
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
                        result = dict(status='applied', revision=revision)
                except ValueError:
                    result = dict(status='failed', reason='INVALID_OR_MISSING_ITEM')
                self.db.execute('INSERT INTO review_receipts VALUES(?,?,?,?,?)', (request_id, index, digest, encode(result), self.now()))
                self.db.execute('DELETE FROM review_receipts WHERE rowid IN (SELECT rowid FROM review_receipts ORDER BY updated DESC,rowid DESC LIMIT -1 OFFSET 1024)')
                results.append(result)
        return dict(items=results)
