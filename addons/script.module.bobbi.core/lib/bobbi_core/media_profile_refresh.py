"""Idle-only bounded requalification of existing exact prepared resources.

One owner, existing IO lane; no cloud submission, title insertion or file delete.
Historical resources stay playable when profile evidence is unavailable.
"""
from copy import deepcopy
import json

from bobbi_core.ledger_extension import install_extension
from bobbi_core.prepared_qualification import qualification_token

KEY = 'extension:media-profile-refresh:schema'
PROFILE_POLICY = 'explicit-numbered-commentary-v2'
DDL = {'media_profile_refresh': '''CREATE TABLE media_profile_refresh(
    resource TEXT PRIMARY KEY REFERENCES resources(id), state TEXT NOT NULL,
    attempts INTEGER NOT NULL, next_attempt REAL NOT NULL)'''}


class MediaProfileRefresh:
    def __init__(self, queue, provider, qualifier, allowed):
        self.queue, self.provider, self.qualifier, self.allowed = queue, provider, qualifier, allowed
        self.pending = None
        install_extension(queue.ledger, KEY, 1, DDL)
        self._rearm_changed_policy()

    def _rearm_changed_policy(self):
        # A fixed validator may now understand previously unsupported facts.
        # Ordinary restarts must not reset a bounded failed probe budget.
        policy_key = KEY + ':policy'
        with self.queue.ledger.transaction():
            old = self.queue.db.execute('SELECT value FROM settings WHERE key=?', (policy_key,)).fetchone()
            previous = old[0] if old else None
            if previous == PROFILE_POLICY:
                return
            rows = self.queue.db.execute("SELECT resource,attempts FROM media_profile_refresh "
                "WHERE state='UNAVAILABLE' ORDER BY resource LIMIT 8193").fetchall()
            if len(rows) > 8192:
                raise ValueError('Profile requalification exceeds resource budget')
            for row in rows:
                self.queue.ledger._audit('media_profile_policy_changed', row['resource'],
                    dict(previous_policy=previous, policy=PROFILE_POLICY,
                         previous_state='UNAVAILABLE', previous_attempts=row['attempts']))
            self.queue.db.execute("UPDATE media_profile_refresh SET state='RETRY',attempts=0,next_attempt=? "
                                  "WHERE state='UNAVAILABLE'", (self.queue.now(),))
            self.queue.db.execute('INSERT INTO settings VALUES(?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (policy_key, PROFILE_POLICY))

    def _record(self, plan, state):
        with self.queue.ledger.transaction():
            self._record_in_transaction(plan, state)

    def _record_in_transaction(self, plan, state):
        if not self.queue.db.in_transaction:
            raise RuntimeError('Profile status requires an owner transaction')
        self.queue.db.execute('INSERT INTO media_profile_refresh VALUES(?,?,?,?) '
            'ON CONFLICT(resource) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,next_attempt=excluded.next_attempt',
            (plan['resource'], state, plan['attempts'], self.queue.now()+60))
        self.queue.ledger._audit('media_profile_refresh', plan['resource'], dict(state=state, attempts=plan['attempts']))

    def next_action(self):
        if self.pending is not None or self.allowed() is not True:
            return None
        rows = self.queue.db.execute('''SELECT b.resource,b.task,p.payload,f.attempts FROM prepared_bindings b
            JOIN resources r ON r.id=b.resource
            JOIN preparation_targets p ON p.task=b.task AND p.media_id=b.media_id AND p.version_key=b.version_key
            LEFT JOIN media_profile_refresh f ON f.resource=b.resource
            WHERE f.resource IS NULL OR (f.state='RETRY' AND f.next_attempt<=?)
            ORDER BY json_extract(r.payload,'$.qualification.at') DESC,b.resource LIMIT 32''', (self.queue.now(),)).fetchall()
        for row in rows:
            plan = dict(resource=row['resource'], attempts=(row['attempts'] or 0)+1)
            item = self.queue.ledger.get(row['resource'])
            if item['state'] != 'ready' or item['suppressed'] or item.get('qualification', {}).get('media_profile'):
                self._record(plan, 'NOT_REQUIRED')
                continue
            task = self.queue.status(row['task'])
            try:
                token = qualification_token(self.queue, item, task['source_hash'])
                plan.update(token=token, item=item, task=row['task'], request=dict(
                    account=task['account'], destination=task['destination'], source_hash=task['source_hash'],
                    reserved_bytes=task['reserved_bytes'], observation=task['payload']['provider_observation'],
                    targets=[json.loads(row['payload'])]))
            except (ValueError, KeyError):
                self._record(plan, 'REJECTED_IDENTITY')
                continue
            self.pending = deepcopy(plan)
            return plan
        return None

    def perform(self, plan):
        try:
            if self.provider.account_scope() != plan['request']['account']:
                return None
            result = self.qualifier(self.provider, plan['request'])
            return result if self.provider.account_scope() == plan['request']['account'] else None
        except (OSError, ValueError, RuntimeError):
            return None

    def complete(self, plan, result):
        if self.pending != plan:
            return False
        self.pending = None
        if self.allowed() is not True:
            self._record(plan, 'RETRY')
            return False
        current = self.queue.ledger.get(plan['resource'])
        if (current['state'] != 'ready' or current['suppressed']
                or qualification_token(self.queue, current, plan['request']['source_hash']) != plan['token']):
            self._record(plan, 'REJECTED_CHANGED_RESOURCE')
            return False
        if not isinstance(result, dict) or not result.get('qualification', {}).get('media_profile'):
            self._record(plan, 'RETRY' if plan['attempts'] < 3 else 'UNAVAILABLE')
            return False
        fields = ('provider', 'account', 'file_id', 'cloud_path', 'bytes', 'kind', 'media_id', 'version_key')
        if result.get('file') != {key: current[key] for key in fields}:
            self._record(plan, 'REJECTED_CHANGED_RESOURCE')
            return False
        with self.queue.ledger.transaction():
            self.queue.ledger._mark_ready_in_transaction(plan['resource'], result['qualification'])
            # Profile changes affect per-source tokens and UI eligibility, so
            # explicitly publish a new snapshot generation, not stale JSON.
            generation = self.queue.generation()+1
            self.queue.db.execute("INSERT INTO settings VALUES('prepared_generation',?) "
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (str(generation),))
            self._record_in_transaction(plan, 'PROFILE_RECORDED_NOT_AUTOPLAY')
        return True
