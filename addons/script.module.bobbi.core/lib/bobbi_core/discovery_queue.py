"""Durable next-release discovery, anchored only to admitted source evidence.

An additive versioned extension of the same resource ledger, not another truth
store. Older schema-2 consumers can ignore these tables without discarding them.
Discovery never calls providers or marks files ready. A proved result enters the
existing deduplicated preparation queue and must still pass cloud qualification.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re
import shutil
import sqlite3
from uuid import uuid4

from bobbi_core.ledger import encode
from bobbi_core.preparation import checked_request
from bobbi_core.source_intent import checked_body

EXTENSION = 'extension:next-discovery:schema'
TABLE = 'next_discovery_jobs'
MAX_JOBS = 512


def install_extension(ledger):
    """One verified SQLite backup before the first additive DDL transaction."""
    db = ledger.db
    version = db.execute('SELECT value FROM settings WHERE key=?', (EXTENSION,)).fetchone()
    table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
    if version:
        if version[0] != '1' or not table:
            raise ValueError('Unknown/incomplete discovery extension; preserve database')
        expected = ('id', 'account', 'destination', 'media_id', 'version_key', 'payload', 'state',
                    'attempts', 'next_poll', 'updated', 'nonce', 'result')
        if tuple(row[1] for row in db.execute('PRAGMA table_info(next_discovery_jobs)')) != expected:
            raise ValueError('Discovery extension columns changed')
        return None
    if table:
        raise ValueError('Unversioned discovery table; do not overwrite')
    size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if size > 128 * 1024 * 1024 or shutil.disk_usage(ledger.path.parent).free < size * 2 + 128 * 1024 * 1024:
        raise ValueError('Bounded discovery migration backup capacity gate')
    backup = ledger.path.with_name(ledger.path.name + '.pre-next-discovery-v1-' + uuid4().hex)
    saved = sqlite3.connect(str(backup))
    try:
        db.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Discovery extension backup integrity failed')
    finally:
        saved.close()
    with ledger.transaction():
        db.execute('''CREATE TABLE next_discovery_jobs(
            id TEXT PRIMARY KEY, account TEXT NOT NULL, destination TEXT NOT NULL,
            media_id TEXT NOT NULL, version_key TEXT NOT NULL, payload TEXT NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_poll REAL NOT NULL,
            updated REAL NOT NULL, nonce TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}',
            UNIQUE(account,destination,media_id,version_key))''')
        db.execute('CREATE INDEX next_discovery_due ON next_discovery_jobs(state,next_poll)')
        db.execute('INSERT INTO settings VALUES(?,?)', (EXTENSION, '1'))
        ledger._audit('next_discovery_extension_installed', None, {'version': 1, 'backup_name': backup.name})
    return backup


class DiscoveryQueue:
    def __init__(self, preparation):
        self.preparation = preparation
        self.ledger, self.db, self.now = preparation.ledger, preparation.db, preparation.now
        self.migration_backup = install_extension(self.ledger)
        with self.ledger.transaction():
            # No cloud submission occurs in discovery IO. Interrupted discovery
            # can run again; possibly submitted cloud tasks remain in their own
            # queue and are never reset by this recovery.
            self.db.execute("UPDATE next_discovery_jobs SET state='waiting',nonce='',next_poll=? WHERE state='running'", (self.now(),))

    def schedule(self, task, media_id, version_key):
        source = self.preparation.status(task)
        if source['state'] in ('failed', 'suppressed'):
            raise ValueError('Ineligible current source task')
        row = self.db.execute('SELECT payload FROM preparation_targets WHERE task=? AND media_id=? AND version_key=?',
                              (task, media_id, version_key)).fetchone()
        if row is None:
            raise ValueError('Discovery requires an admitted preparation target')
        request = json.loads(row[0])
        selection = request.pop('_selection', None)
        checked_request(request)
        match = re.fullmatch(r'tmdb:tv:([1-9]\d*):s([1-9]\d*):e([1-9]\d*)', media_id)
        if match is None or request['purpose'] not in ('current', 'manual') or not isinstance(selection, dict):
            raise ValueError('Discovery is not recursive or a recommendation scanner')
        file = selection['file']
        anchor = dict(request_id=selection['request_id'], purpose=request['purpose'],
            media=dict(tmdb_id=int(match[1]), kind='tv', season=int(match[2]), episode=int(match[3]),
                anime=selection['anime'], title=selection['title'], release_title=selection['release_title']),
            selected=dict(source_info_hash=request['source_info_hash'], torrent_file_id=file['id'],
                          torrent_path=file['path'], torrent_file_bytes=file['length']))
        checked_body(anchor)
        next_media = 'tmdb:tv:{}:s{}:e{}'.format(match[1], match[2], int(match[3]) + 1)
        key = hashlib.sha256(encode([source['account'], source['destination'], next_media, version_key]).encode()).hexdigest()
        payload = dict(task=task, anchor=anchor, selection=selection)
        encoded = encode(payload)
        with self.ledger.transaction():
            old = self.db.execute('SELECT id FROM next_discovery_jobs WHERE id=?', (key,)).fetchone()
            if not old:
                if self.db.execute('SELECT COUNT(*) FROM next_discovery_jobs').fetchone()[0] >= MAX_JOBS:
                    raise ValueError('Discovery history capacity reached; preserve evidence')
                self.db.execute('''INSERT INTO next_discovery_jobs(id,account,destination,media_id,version_key,payload,state,next_poll,updated)
                    VALUES(?,?,?,?,?,?,'waiting',?,?)''',
                    (key, source['account'], source['destination'], next_media, version_key, encoded, self.now(), self.now()))
                self.ledger._audit('next_discovery_scheduled', None, {'job': key, 'task': task, 'media_id': next_media})
        return key

    def get(self, key):
        row = self.db.execute('SELECT * FROM next_discovery_jobs WHERE id=?', (key,)).fetchone()
        if row is None: raise KeyError(key)
        result = dict(row)
        for field in ('payload', 'result'): result[field] = json.loads(result[field])
        return result

    def claim(self):
        with self.ledger.transaction():
            if self.db.execute("SELECT 1 FROM next_discovery_jobs WHERE state='running'").fetchone():
                return None
            rows = self.db.execute("SELECT * FROM next_discovery_jobs WHERE state='waiting' AND next_poll<=? ORDER BY next_poll,id", (self.now(),)).fetchall()
            for row in rows:
                payload = json.loads(row['payload'])
                current = self.preparation.status(payload['task'])
                if current['state'] in ('suppressed', 'failed'):
                    self.db.execute("UPDATE next_discovery_jobs SET state='cancelled',updated=? WHERE id=?", (self.now(), row['id']))
                    self.ledger._audit('next_discovery_cancelled', None, {'job': row['id'], 'reason': 'CURRENT_SOURCE_INELIGIBLE'})
                    continue
                # A concurrently prepared next target closes the gap, even if
                # its cloud qualification is still pending. Do not submit a
                # competing torrent merely to win a timing race.
                existing = self.db.execute('''SELECT 1 FROM preparation_targets p JOIN tasks t ON t.id=p.task
                    WHERE t.account=? AND t.destination=? AND p.media_id=? AND p.version_key=?
                    AND t.state NOT IN ('failed','suppressed') LIMIT 1''',
                    (row['account'], row['destination'], row['media_id'], row['version_key'])).fetchone()
                if existing:
                    self.db.execute("UPDATE next_discovery_jobs SET state='superseded',updated=? WHERE id=?", (self.now(), row['id']))
                    continue
                nonce = uuid4().hex
                self.db.execute("UPDATE next_discovery_jobs SET state='running',attempts=attempts+1,nonce=?,updated=? WHERE id=?", (nonce, self.now(), row['id']))
                return self.get(row['id'])
        return None

    def defer(self, key, nonce, reason):
        if not isinstance(reason, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,63}', reason):
            raise ValueError('Fixed diagnostic code required, no provider text')
        with self.ledger.transaction():
            row = self.get(key)
            if row['state'] != 'running' or row['nonce'] != nonce:
                return False
            delay = min(21600, 300 * 2 ** min(row['attempts'] - 1, 7))
            self.db.execute("UPDATE next_discovery_jobs SET state='waiting',nonce='',next_poll=?,updated=?,result=? WHERE id=?",
                (self.now() + delay, self.now(), encode({'reason': reason}), key))
            self.ledger._audit('next_discovery_deferred', None, {'job': key, 'reason': reason, 'delay': delay})
        return True

    def accept(self, key, nonce, request, selection):
        """Consume the service's verified_next result, never an IPC payload."""
        row = self.get(key)
        if row['state'] != 'running' or row['nonce'] != nonce:
            return None
        checked_request(request)
        same_version = request['version_key'] == row['version_key']
        if not same_version:
            from bobbi_core.episode_revision import compatible_pair
            anchor = row['payload']['anchor']
            same_version = compatible_pair(PurePosixPath(anchor['selected']['torrent_path']).name,
                PurePosixPath(selection['file']['path']).name, anchor['media']['season'],
                anchor['media']['episode'], row['version_key'], request['version_key'])
        if (request['purpose'] != 'next' or not same_version
                or any(request[k] != row[k] for k in ('account', 'destination', 'media_id'))
                or self.preparation.status(row['payload']['task'])['state'] in ('suppressed', 'failed')):
            raise ValueError('Late discovery target no longer matches the admitted request')
        # Not wrapped in our transaction: PreparationQueue owns its short DB
        # transaction. A crash between this call and the state update is safe:
        # the next claim finds the existing target; cloud submission isn't replayed.
        prepared = self.preparation.request(request, selection)
        with self.ledger.transaction():
            self.db.execute("UPDATE next_discovery_jobs SET state='prepared',nonce='',updated=?,result=? WHERE id=? AND nonce=?",
                (self.now(), encode({'state': 'PREPARATION_REQUESTED_NOT_READY', 'task_id': prepared['task_id']}), key, nonce))
            self.ledger._audit('next_discovery_preparation_requested', None, {'job': key, 'task_id': prepared['task_id']})
        return prepared
