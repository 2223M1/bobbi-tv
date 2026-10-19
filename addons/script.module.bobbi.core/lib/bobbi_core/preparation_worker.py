"""One provider IO lane, with durable decisions confined to the ledger owner.

next_action/complete belong to the single SQLite owner thread. perform may run
on one IO thread, never holding a database transaction. This module has no
Kodi imports and never treats provider acceptance as media qualification.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re
from uuid import uuid4


@dataclass(frozen=True)
class Action:
    token: str
    kind: str
    task: str
    request_json: str

    @property
    def request(self):
        return json.loads(self.request_json)


class PreparationWorker:
    def __init__(self, queue, provider, qualifier):
        if not callable(qualifier):
            raise ValueError('A real media qualifier is required before enabling cloud submissions')
        self.queue, self.provider, self.qualifier = queue, provider, qualifier
        self.pending = None
        self.followup = None
        queue.recover()

    def _action(self, kind, row):
        value = {key: row[key] for key in ('account', 'destination', 'source_hash', 'reserved_bytes')}
        if kind == 'qualify':
            value['observation'] = row['payload']['provider_observation']
            targets = self.queue.db.execute('''SELECT t.payload FROM preparation_targets t WHERE t.task=?
                AND NOT EXISTS(SELECT 1 FROM prepared_bindings b WHERE b.task=t.task
                    AND b.media_id=t.media_id AND b.version_key=t.version_key)
                ORDER BY t.media_id,t.version_key LIMIT 1''', (row['id'],)).fetchall()
            value['targets'] = [json.loads(target[0]) for target in targets]
        self.pending = Action(uuid4().hex, kind, row['id'], json.dumps(value, sort_keys=True))
        return self.pending

    def next_action(self, playing=False):
        if self.pending is not None:
            return None
        if self.followup is not None:
            task, self.followup = self.followup, None
            return self._action('submit', self.queue.status(task))
        for row in self.queue.due(playing=playing):
            state = row['state']
            if state in ('queued', 'space_blocked'):
                targets = self.queue.db.execute('SELECT payload FROM preparation_targets WHERE task=?', (row['id'],)).fetchall()
                if not targets or any('_selection' not in json.loads(target[0]) for target in targets):
                    self._defer(row['id'], 60, 'preparation_source_not_verified')
                    continue
                return self._action('capacity', row)
            if state in ('submitted', 'uncertain', 'downloading'):
                return self._action('poll', row)
            if state == 'mapping':
                # due(playing=True) excludes recommendation/manual work. Only
                # current/next exact-file header probes use this one IO lane;
                # otherwise an E1 BT session could never prepare E2 before EOF.
                return self._action('qualify', row)
        return None

    def perform(self, action):
        """Network lane. Return typed failures without echoing URLs or tokens."""
        value = action.request
        try:
            if self.provider.account_scope() != value['account']:
                return {'ok': False, 'error': 'ACCOUNT_CHANGED'}
            if action.kind == 'capacity':
                return {'ok': True, 'capacity': self.provider.space('/115open')}
            if action.kind == 'submit':
                # Identity of the magnet is fixed; no arbitrary request URL is
                # accepted and a timeout must never replay this mutation.
                result = self.provider.add_offline('magnet:?xt=urn:btih:' + value['source_hash'], value['destination'])
                if result != {'status': 'ACCEPTED_NOT_VERIFIED'}:
                    return {'ok': False, 'error': 'UNRECOGNIZED_SUBMISSION_RESULT'}
                return {'ok': True}
            if action.kind == 'poll':
                rows = [row for row in self.provider.offline_tasks(value['destination'])
                        if row.get('info_hash') == value['source_hash']]
                observed = {'account': value['account'], 'destination': value['destination'],
                            'source_info_hash': value['source_hash'], 'state': 'missing',
                            'file_id': '', 'parent_id': ''}
                if len(rows) == 1:
                    row = rows[0]
                    observed.update(state={0: 'downloading', 1: 'downloading', 2: 'finished', 3: 'failed'}.get(row['status'], 'unknown'),
                                    file_id=row.get('file_id', ''), parent_id=row.get('parent_id', ''))
                elif rows:
                    observed['state'] = 'unknown'
                return {'ok': True, 'observation': observed}
            if action.kind == 'qualify':
                # This callback is a service-owned adapter, never an IPC field.
                return {'ok': True, 'qualified': self.qualifier(self.provider, deepcopy(value))}
            return {'ok': False, 'error': 'UNKNOWN_ACTION'}
        except Exception as error:
            # Exception strings from HTTP libraries commonly contain auth URLs.
            result = {'ok': False, 'error': type(error).__name__[:64]}
            from bobbi_core.media_probe import ProbeError
            if isinstance(error, ProbeError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', str(error)):
                result['code'] = str(error)
            return result

    def _defer(self, task, delay, event, detail=None):
        with self.queue.ledger.transaction():
            self.queue.db.execute('UPDATE tasks SET next_poll=? WHERE id=?', (self.queue.now() + delay, task))
            self.queue.ledger._audit(event, None, dict(task=task, **(detail or {})))

    def complete(self, action, result):
        """Consume a network result once on the SQLite owner thread."""
        if self.pending is None or action != self.pending:
            return False
        self.pending = None
        self.queue.status(action.task)
        if action.kind == 'submit':
            self.queue.submitted(action.task, result.get('ok') is True)
            if result.get('ok') is not True:
                self._defer(action.task, 60, 'preparation_submit_uncertain')
            return True
        if result.get('ok') is not True:
            # Persist typed causes, never raw provider exception strings. This
            # distinguishes mapping, probe-budget and transport failures.
            detail = {'kind': action.kind}
            for key in ('error', 'code'):
                value = result.get(key)
                if isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
                    detail[key] = value
            self._defer(action.task, 60, 'preparation_io_failed', detail)
            return True
        if action.kind == 'capacity':
            capacity = result['capacity']
            if self.queue.begin_submission(action.task, capacity['total'], capacity['free']):
                self.followup = action.task
            else:
                self._defer(action.task, 30, 'preparation_wait_capacity_or_slot')
        elif action.kind == 'poll':
            self.queue.observe(action.task, result['observation'])
        elif action.kind == 'qualify':
            value = result['qualified']
            if not isinstance(value, dict) or set(value) != {'file', 'qualification', 'mapping'}:
                self._defer(action.task, 60, 'preparation_qualification_unavailable')
                return True
            # Both checks may fail. Leave the task unresolved and preserve the
            # observed resource; there is no index publication before publish.
            resource = self.queue.ledger.register(value['file'], managed=True, identity_verified=True)
            self.queue.ledger.mark_ready(resource, value['qualification'])
            self.queue.publish(action.task, resource, value['mapping'])
        return True
