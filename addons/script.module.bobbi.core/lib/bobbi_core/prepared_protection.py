"""Durable prepared-file protection, never playback or watched authority.

All SQLite work runs on the preparation owner. Native observations come from
the bounded local read-only lane. Unknown playback closes the recycle gate.
"""
import hashlib
import json
import math
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from bobbi_core.ledger import encode
from bobbi_core.native_receipt import receipt
from bobbi_core.prepared_index import MOUNT_ROOT

SCHEMA_KEY = 'extension:prepared-playback-protection:schema'
DDL = '''CREATE TABLE prepared_playback_protection(
    request TEXT PRIMARY KEY, resource TEXT REFERENCES resources(id),
    payload TEXT NOT NULL, startup_until REAL NOT NULL)'''


def install_schema(ledger):
    db = ledger.db
    version = db.execute('SELECT value FROM settings WHERE key=?', (SCHEMA_KEY,)).fetchone()
    table = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='prepared_playback_protection'").fetchone()
    if version:
        if version[0] != '1' or not table or ' '.join(table[0].split()) != ' '.join(DDL.split()):
            raise ValueError('Unknown playback protection schema; preserve the ledger')
        return None
    if table:
        raise ValueError('Unversioned playback protection table; explicit migration required')
    size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if size > 128 * 1024 * 1024 or shutil.disk_usage(ledger.path.parent).free < size * 2 + 128 * 1024 * 1024:
        raise ValueError('Playback protection backup capacity gate')
    backup = ledger.path.with_name(ledger.path.name + '.pre-playback-protection-v1-' + uuid4().hex)
    saved = sqlite3.connect(str(backup))
    try:
        db.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Playback protection backup integrity failed')
    finally:
        saved.close()
    digest = hashlib.sha256()
    with backup.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    with ledger.transaction():
        db.execute(DDL)
        db.execute('INSERT INTO settings VALUES(?,?)', (SCHEMA_KEY, '1'))
        ledger._audit('playback_protection_schema_installed', None,
                      dict(version=1, backup_name=backup.name, sha256=digest.hexdigest()))
    return backup


class PreparedProtection:
    def __init__(self, ledger):
        self.ledger = ledger
        self.migration_backup = install_schema(ledger)
        self._gate(False)
        # Keep a durable closed sentinel for older readers and independent
        # connections; fresh cleanup permission never survives this owner.
        self.ledger.db.execute("INSERT INTO settings VALUES('playback_protection',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (encode(dict(known=False, at=self.ledger.now())),))

    def _gate(self, known, at=None):
        self.ledger._playback_observation = dict(known=known, at=self.ledger.now() if at is None else at)

    @staticmethod
    def owner(request):
        return 'prepared-play:' + request

    def arm(self, plan):
        body, item = plan['body'], plan['file']
        url_hash = hashlib.sha256((MOUNT_ROOT + item['cloud_path']).encode('utf-8')).hexdigest()
        resource_hash = hashlib.sha256(item['resource_id'].encode('utf-8')).hexdigest()
        binding = dict(url_sha256=url_hash, identities=[
            'bt:' + body['source_info_hash'] + '|transport:' + url_hash,
            'prepared:' + resource_hash + '|transport:' + url_hash])
        db, now = self.ledger.db, self.ledger.now()
        with self.ledger.transaction():
            previous = db.execute('SELECT * FROM prepared_playback_protection WHERE request=?',
                                  (body['request_id'],)).fetchone()
            if previous:
                old = json.loads(previous['payload'])
                if (previous['resource'] != item['resource_id']
                        or any(old.get(key) != value for key, value in binding.items())):
                    raise ValueError('Playback protection request cannot change its exact file')
                # Polls cannot extend an abandoned startup indefinitely.
                return
            if db.execute('SELECT COUNT(*) FROM prepared_playback_protection').fetchone()[0] >= 32:
                raise ValueError('Prepared playback protection capacity reached')
            if self.ledger.get(item['resource_id'])['state'] != 'ready':
                raise ValueError('Only a ready resource can receive startup protection')
            db.execute('INSERT INTO prepared_playback_protection VALUES(?,?,?,?)',
                       (body['request_id'], item['resource_id'], encode(binding), now + 90))
            db.execute('INSERT INTO leases VALUES(?,?,?,?)',
                       (item['resource_id'], self.owner(body['request_id']), 'playback', now + 90))

    def observe(self, snapshot, age=0):
        # Fail closed even if a transaction fails before the final observation.
        self._gate(False)
        # An absent/unsupported native interface is not an idle player.
        valid = (isinstance(snapshot, dict) and type(snapshot.get('protocol')) is int
                 and snapshot['protocol'] == 1 and 'playback' in snapshot)
        fresh = type(age) in (int, float) and math.isfinite(age) and 0 <= age <= 10
        valid = valid and fresh
        raw = snapshot.get('playback') if valid else None
        current = receipt(raw) if raw is not None else None
        valid = valid and (raw is None or current is not None)
        active = current if current and current['phase'] != 'TERMINAL' else None
        db, now, matched = self.ledger.db, self.ledger.now(), False
        with self.ledger.transaction():
            rows = db.execute('SELECT * FROM prepared_playback_protection').fetchall()
            for row in rows:
                binding = json.loads(row['payload'])
                same = (active and active['request_id'] == row['request']
                        and active['url_sha256'] == binding['url_sha256']
                        and active['file_identity'] in binding['identities']
                        and binding.get('native_instance', active['native_instance']) == active['native_instance'])
                if same:
                    previous_sequence = binding.get('sequence', -1)
                    if active['sequence'] < previous_sequence:
                        valid = False
                        continue
                    matched = True
                    binding.update(native_instance=active['native_instance'], sequence=active['sequence'])
                    encoded = encode(binding)
                    if encoded != row['payload']:
                        db.execute('UPDATE prepared_playback_protection SET payload=? WHERE request=?',
                                   (encoded, row['request']))
                    lease = db.execute('SELECT purpose,expires FROM leases WHERE resource=? AND owner=?',
                                       (row['resource'], self.owner(row['request']))).fetchone()
                    # The 90s durable lease remains protected between 5s native
                    # observations. Renew with 60s still remaining, not on every
                    # identical paused/playing receipt. No fsync policy change.
                    if lease is None or lease['purpose'] != 'playback' or lease['expires'] <= now + 60:
                        db.execute('INSERT INTO leases VALUES(?,?,?,?) ON CONFLICT(resource,owner) '
                                   'DO UPDATE SET purpose=excluded.purpose,expires=excluded.expires',
                                   (row['resource'], self.owner(row['request']), 'playback', now + 90))
                elif valid and row['startup_until'] <= now:
                    db.execute('DELETE FROM leases WHERE resource=? AND owner=?',
                               (row['resource'], self.owner(row['request'])))
                    db.execute('DELETE FROM prepared_playback_protection WHERE request=?', (row['request'],))
            # Unknown/unregistered playback pauses deletion rather than guessing
            # its file from a title, playerid or reusable URL alone.
        # Neither IO completion delay nor slow COMMIT renews the age of the
        # actual native observation. Freshness expires even after a long stall.
        self._gate(bool(valid and (not active or matched)), at=now-age if fresh else now)


def native_resource_snapshot():
    from bobbi_core.playback_ipc import call
    return call({'operation': 'resource_snapshot'})


class ProtectionLane:
    """One local observation in flight; cloud probes cannot starve renewal."""
    def __init__(self, protection, read=None, clock=time.monotonic):
        self.protection, self.read, self.clock = protection, read or native_resource_snapshot, clock
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cinema-resource-observation')
        self.future, self.due = None, 0.0

    def _sample(self):
        began = self.clock()
        return began, self.read()

    def tick(self):
        if self.future is not None and self.future.done():
            try:
                sampled, result = self.future.result()
                age = self.clock() - sampled
            except Exception:
                result = None
                age = 0
            self.protection.observe(result, age=age)
            self.future, self.due = None, self.clock() + 5
        if self.future is None and self.clock() >= self.due:
            self.future = self.executor.submit(self._sample)

    def close(self):
        self.executor.shutdown(wait=True)  # Python 3.8; at most one IO future.
        self.protection.observe(None)
