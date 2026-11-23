"""Durable account-scoped preparation state; no provider IO or Kodi imports.

The service owns this writer. UI clients can request/status/cancel a subscription,
but cannot call publication or manufacture verification evidence.
"""
import hashlib
import json
import re
from pathlib import PurePosixPath
from uuid import uuid4

from bobbi_core.ledger import encode
from bobbi_core.retention import required_free_bytes

PRIORITY = {'current': 0, 'next': 1, 'manual': 2, 'recommendation': 3}
IN_FLIGHT = ('submitting', 'submitted', 'uncertain', 'downloading', 'mapping', 'checking')
TERMINAL = ('ready', 'failed', 'suppressed')
MEDIA = re.compile(r'tmdb:(?:movie:[1-9]\d*|tv:[1-9]\d*:s\d+:e[1-9]\d*)\Z')


def scope_path(value):
    if (not isinstance(value, str) or not value.startswith('/115open/')
            or '\\' in value or '\x00' in value
            or any(part in {'.', '..', ''} for part in value.split('/')[1:])
            or str(PurePosixPath(value)) != value):
        raise ValueError('Exact scoped 115 destination required')
    return value


def checked_request(request):
    required = {'provider', 'account', 'destination', 'source_info_hash', 'media_id',
                'version_key', 'bytes_required', 'purpose'}
    if not isinstance(request, dict) or set(request) != required:
        raise ValueError('Invalid preparation request fields')
    result = dict(request)
    if result['provider'] != '115':
        raise ValueError('Unsupported provider')
    for key in ('account', 'version_key'):
        if not isinstance(result[key], str) or not 1 <= len(result[key]) <= 256:
            raise ValueError('Stable account and release identities required')
    scope_path(result['destination'])
    if not isinstance(result['source_info_hash'], str) or not re.fullmatch('[0-9a-f]{40}', result['source_info_hash']):
        raise ValueError('Real normalized torrent info hash required')
    if not isinstance(result['media_id'], str) or not MEDIA.fullmatch(result['media_id']):
        raise ValueError('Exact media/episode identity required')
    if type(result['bytes_required']) is not int or result['bytes_required'] <= 0:
        raise ValueError('Positive bounded reservation required')
    if result['purpose'] not in PRIORITY:
        raise ValueError('Unknown preparation purpose')
    return result


def _download_finished(row):
    """Release only a download slot, never its reservation or qualification.

    A mapping/checking label alone is insufficient (including legacy rows).
    Completion must already be persisted for this account, destination and
    torrent with both cloud object IDs. Unknown/malformed evidence fails closed.
    """
    if row['provider'] != '115' or row['state'] not in ('mapping', 'checking'):
        return False
    if (not isinstance(row['account'], str) or not 1 <= len(row['account']) <= 256
            or not isinstance(row['source_hash'], str)
            or not re.fullmatch('[0-9a-f]{40}', row['source_hash'])):
        return False
    try:
        scope_path(row['destination'])
        payload = json.loads(row['payload'])
    except (TypeError, ValueError):
        return False
    observation = payload.get('provider_observation') if isinstance(payload, dict) else None
    if not isinstance(observation, dict) or set(observation) != {
            'account', 'destination', 'source_info_hash', 'state', 'file_id', 'parent_id'}:
        return False
    return (observation['state'] == 'finished'
            and observation['account'] == row['account']
            and observation['destination'] == row['destination']
            and observation['source_info_hash'] == row['source_hash']
            and all(isinstance(observation[key], str) and observation[key].strip()
                    for key in ('file_id', 'parent_id')))


class PreparationQueue:
    def __init__(self, ledger):
        self.ledger = ledger
        self.db = ledger.db
        self.now = ledger.now

    def status(self, task):
        row = self.db.execute('SELECT * FROM tasks WHERE id=? AND provider!=?', (task, 'legacy')).fetchone()
        if row is None:
            raise KeyError(task)
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        return result

    def request(self, request, selection=None):
        request = checked_request(request)
        payload = dict(request)
        if selection is not None:
            # Service-private output from verified_intents; never accepted as
            # a ready/verified flag through the IPC request schema.
            if (not isinstance(selection, dict) or set(selection) !=
                    {'file', 'title', 'release_title', 'anime', 'request_id', 'metadata_sha256', 'work_identity'}):
                raise ValueError('Invalid source-selection evidence')
            encode(selection)
            payload['_selection'] = selection
        key = hashlib.sha256(encode([request[k] for k in
            ('provider', 'account', 'destination', 'source_info_hash')]).encode()).hexdigest()
        with self.ledger.transaction():
            row = self.db.execute('SELECT id,reserved_bytes,state FROM tasks WHERE dedup_key=?', (key,)).fetchone()
            if row is not None:
                if row['reserved_bytes'] != request['bytes_required']:
                    raise ValueError('Same torrent changed size; reconcile metadata first')
                if row['state'] == 'suppressed':
                    raise ValueError('Cleaned resource requires an explicit user re-prepare')
                task, existing = row['id'], True
                self.db.execute('UPDATE tasks SET priority=MIN(priority,?) WHERE id=?',
                                (PRIORITY[request['purpose']], task))
            else:
                if self.db.execute("SELECT COUNT(*) FROM tasks WHERE provider!='legacy' AND state NOT IN ('ready','failed','suppressed')").fetchone()[0] >= 256:
                    raise ValueError('Bounded task queue is full')
                task, existing = uuid4().hex, False
                self.db.execute('''INSERT INTO tasks(id,source_hash,payload,state,reserved_bytes,updated,
                    provider,account,destination,dedup_key,priority) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (task, request['source_info_hash'], encode(request), 'queued', request['bytes_required'],
                     self.now(), request['provider'], request['account'], request['destination'], key, PRIORITY[request['purpose']]))
                self.ledger._audit('preparation_requested', None, {'task': task, 'dedup_key': key})
            inserted = self.db.execute('INSERT OR IGNORE INTO preparation_targets VALUES(?,?,?,?)',
                                       (task, request['media_id'], request['version_key'], encode(payload))).rowcount
            if not inserted and selection is not None:
                old_payload = json.loads(self.db.execute('SELECT payload FROM preparation_targets WHERE task=? AND media_id=? AND version_key=?',
                    (task, request['media_id'], request['version_key'])).fetchone()[0])
                old = old_payload.get('_selection')
                if old and any(old.get(key) != selection.get(key) for key in ('file', 'metadata_sha256', 'release_title')):
                    raise ValueError('Prepared target metadata changed; reconcile before replacing')
                self.db.execute('UPDATE preparation_targets SET payload=? WHERE task=? AND media_id=? AND version_key=?',
                    (encode(payload), task, request['media_id'], request['version_key']))
                from bobbi_core.prepared_qualification import qualification_target
                if (qualification_target(old_payload) != qualification_target(payload)
                        and self.db.execute('SELECT 1 FROM prepared_bindings WHERE task=? AND media_id=? AND version_key=? LIMIT 1',
                            (task, request['media_id'], request['version_key'])).fetchone()):
                    # The token includes accepted target evidence. Notify the
                    # existing generation-driven publisher in this same owner
                    # transaction; never bypass rejection of the old token.
                    generation = self.generation() + 1
                    self.db.execute("INSERT INTO settings VALUES('prepared_generation',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                    (str(generation),))
                    self.ledger._audit('prepared_target_changed', None, {'task': task, 'generation': generation})
            if inserted and existing and row['state'] == 'ready':
                self.db.execute("UPDATE tasks SET state='mapping',next_poll=0 WHERE id=?", (task,))
        return {'task_id': task, 'state': self.status(task)['state'], 'existing': existing}

    def begin_submission(self, task, total, free):
        # Persist the uncertainty boundary BEFORE calling AddOfflineFiles.
        with self.ledger.transaction():
            row = self.status(task)
            if row['state'] not in ('queued', 'space_blocked'):
                raise ValueError('Cannot resubmit a possibly submitted task')
            active = self.db.execute("SELECT provider,account,destination,source_hash,state,payload FROM tasks WHERE state IN ('reserved','submitting','submitted','uncertain','downloading','mapping','checking')").fetchall()
            if sum(not _download_finished(item) for item in active) >= 2:
                return False
            if type(total) is not int or type(free) is not int or not 0 <= free <= total or total <= 0:
                raise ValueError('Fresh provider capacity required')
            reserved = self.db.execute("SELECT COALESCE(SUM(reserved_bytes),0) FROM tasks WHERE provider=? AND account=? AND state IN ('submitting','submitted','uncertain','downloading','mapping','checking')",
                                       (row['provider'], row['account'])).fetchone()[0]
            if free < required_free_bytes(total, reserved, row['reserved_bytes']):
                self.db.execute("UPDATE tasks SET state='space_blocked',updated=? WHERE id=?", (self.now(), task))
                return False
            self.db.execute("UPDATE tasks SET state='submitting',updated=?,attempts=attempts+1 WHERE id=?", (self.now(), task))
            self.ledger._audit('preparation_submit_intent', None, {'task': task})
        return True

    def submitted(self, task, accepted):
        with self.ledger.transaction():
            if self.status(task)['state'] != 'submitting':
                raise ValueError('Late/duplicate submission result')
            state = 'submitted' if accepted is True else 'uncertain'
            self.db.execute('UPDATE tasks SET state=?,updated=?,next_poll=? WHERE id=?', (state, self.now(), self.now() + 5, task))
            self.ledger._audit('preparation_' + state, None, {'task': task})

    def recover(self):
        with self.ledger.transaction():
            self.db.execute("UPDATE tasks SET state='uncertain',next_poll=?,updated=? WHERE state='submitting'", (self.now(), self.now()))
            self.db.execute("UPDATE tasks SET state='mapping',next_poll=? WHERE state='checking'", (self.now(),))

    def observe(self, task, observation):
        # Provider responses enter only through the service's reviewed decoder.
        allowed = {'account', 'destination', 'source_info_hash', 'state', 'file_id', 'parent_id'}
        if set(observation) != allowed or observation['state'] not in ('missing', 'downloading', 'finished', 'failed', 'unknown'):
            raise ValueError('Unrecognized provider observation')
        with self.ledger.transaction():
            row = self.status(task)
            if row['state'] in TERMINAL or row['state'] in ('queued', 'space_blocked'):
                raise ValueError('Unsolicited/stale provider observation')
            for key, column in (('account', 'account'), ('destination', 'destination'), ('source_info_hash', 'source_hash')):
                if observation[key] != row[column]:
                    raise ValueError('Observation belongs to another account/source')
            state = {'missing': 'uncertain', 'unknown': 'uncertain', 'downloading': 'downloading',
                     'finished': 'mapping', 'failed': 'failed'}[observation['state']]
            if state == 'mapping' and (not observation['file_id'] or not observation['parent_id']):
                state = 'uncertain'  # A name/size is not a cloud object identity.
            payload = dict(row['payload'], provider_observation=observation)
            self.db.execute('UPDATE tasks SET state=?,payload=?,next_poll=?,updated=? WHERE id=?',
                            (state, encode(payload), self.now() + (60 if state == 'uncertain' else 15), self.now(), task))
            self.ledger._audit('preparation_observed', None, {'task': task, 'state': state})
        return state

    def due(self, playing=False, limit=16):
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError('Bounded task page required')
        rows = self.db.execute("SELECT id FROM tasks WHERE provider!='legacy' AND state NOT IN ('ready','failed','suppressed') AND next_poll<=? AND (?=0 OR priority<=1) ORDER BY priority,updated,id LIMIT ?",
                               (self.now(), int(bool(playing)), limit)).fetchall()
        return [self.status(row[0]) for row in rows]

    def publish(self, task, resource, evidence):
        required = {'source_info_hash', 'cloud_root_id', 'cloud_file_id', 'cloud_path',
                    'torrent_path', 'torrent_file_id', 'bytes'}
        if set(evidence) != required or type(evidence['torrent_file_id']) is not int or evidence['torrent_file_id'] < 0:
            raise ValueError('Exact BT/cloud file evidence required')
        relative = evidence['torrent_path']
        if (not isinstance(relative, str) or not relative or '\\' in relative
                or PurePosixPath(relative).is_absolute() or any(p in ('', '.', '..') for p in relative.split('/'))):
            raise ValueError('Canonical torrent path required')
        with self.ledger.transaction():
            row, item = self.status(task), self.ledger.get(resource)
            observation = row['payload'].get('provider_observation', {})
            if row['state'] not in ('mapping', 'checking', 'ready') or item['state'] != 'ready':
                raise ValueError('Only qualified media can be published')
            if (item['account'] != row['account'] or item['provider'] != row['provider']
                    or evidence['source_info_hash'] != row['source_hash']
                    or evidence['cloud_root_id'] != observation.get('file_id')
                    or observation.get('state') != 'finished'
                    or not evidence['cloud_root_id']
                    or evidence['cloud_file_id'] != item['file_id']
                    or evidence['cloud_path'] != item['cloud_path']
                    or evidence['bytes'] != item['bytes']
                    or not item['cloud_path'].startswith(row['destination'] + '/')):
                raise ValueError('File evidence does not belong to this cloud task')
            target = self.db.execute('SELECT 1 FROM preparation_targets WHERE task=? AND media_id=? AND version_key=?',
                                     (task, item['media_id'], item['version_key'])).fetchone()
            if not target:
                raise ValueError('Unrequested media or release')
            previous = self.db.execute('SELECT evidence FROM prepared_bindings WHERE task=? AND resource=?', (task, resource)).fetchone()
            if previous:
                if previous[0] != encode(evidence):
                    raise ValueError('Published binding changed')
                return self.generation()
            self.db.execute('INSERT INTO prepared_bindings VALUES(?,?,?,?,?)',
                            (task, resource, item['media_id'], item['version_key'], encode(evidence)))
            generation = self.generation() + 1
            self.db.execute("INSERT INTO settings VALUES('prepared_generation',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(generation),))
            # A pack may have more requested episodes; each remains independently
            # unresolved until it has its own qualified binding.
            missing = self.db.execute('''SELECT COUNT(*) FROM preparation_targets t WHERE task=?
                AND NOT EXISTS(SELECT 1 FROM prepared_bindings b WHERE b.task=t.task
                AND b.media_id=t.media_id AND b.version_key=t.version_key)''', (task,)).fetchone()[0]
            self.db.execute('UPDATE tasks SET state=?,updated=? WHERE id=?', ('mapping' if missing else 'ready', self.now(), task))
            self.ledger._audit('prepared_published', resource, {'task': task, 'generation': generation})
        return generation

    def generation(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='prepared_generation'").fetchone()
        return int(row[0]) if row else 0

    def resolve(self, account, media_id, version_key):
        rows = self.db.execute('''SELECT b.resource FROM prepared_bindings b JOIN tasks t ON t.id=b.task
            WHERE t.account=? AND b.media_id=? AND b.version_key=? ORDER BY b.resource LIMIT 2''',
                               (account, media_id, version_key)).fetchall()
        candidates = [self.ledger.get(row[0]) for row in rows]
        candidates = [item for item in candidates if item['state'] == 'ready' and not item['suppressed']]
        return candidates[0] if len(candidates) == 1 else None
