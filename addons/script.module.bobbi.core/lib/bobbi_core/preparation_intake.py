"""Durable IPC intake. Only source intent and status are exposed, never proof."""
import json
import re

from bobbi_core.ledger import encode
from bobbi_core.source_intent import checked_body


class Intake:
    def __init__(self, ledger):
        self.ledger, self.db, self.now = ledger, ledger.db, ledger.now
        with ledger.transaction():
            # Validation only reads metadata; unlike cloud submission it is safe
            # to repeat after a crash. Cloud submission intents live separately.
                self.db.execute("UPDATE preparation_intents SET state='queued' WHERE state='validating'")

    def accept(self, body):
        checked_body(body)
        if not isinstance(body, dict) or set(body) != {'request_id', 'media', 'selected', 'purpose'}:
            raise ValueError('Source intent required, not verification evidence')
        identifier = body['request_id']
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise ValueError('Request identity required')
        payload = encode(body)
        if len(payload.encode('utf-8')) > 16384:
            raise ValueError('Intent exceeds IPC budget')
        with self.ledger.transaction():
            row = self.db.execute('SELECT payload FROM preparation_intents WHERE id=?', (identifier,)).fetchone()
            if row:
                if row[0] != payload:
                    raise ValueError('Same request identity cannot select another source')
            else:
                if self.db.execute("SELECT COUNT(*) FROM preparation_intents WHERE state IN ('queued','validating')").fetchone()[0] >= 64:
                    raise ValueError('Intent queue is full')
                self.db.execute('INSERT INTO preparation_intents VALUES(?,?,?,?,?)',
                                (identifier, payload, 'queued', self.now(), '{}'))
        return self.status(identifier)

    def status(self, identifier):
        row = self.db.execute('SELECT state,result FROM preparation_intents WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return dict(request_id=identifier, state=row[0], result=json.loads(row[1]))

    def accept_advance(self, message):
        """Reconstruct current selection from ledger proof, not client paths."""
        required = {'request_id', 'resource_id', 'media_id', 'version_key', 'source_info_hash'}
        if (not isinstance(message, dict) or set(message) != required
                or not isinstance(message['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', message['request_id'])
                or not isinstance(message['source_info_hash'], str) or not re.fullmatch('[0-9a-f]{40}', message['source_info_hash'])):
            raise ValueError('Exact prepared-current context required')
        item = self.ledger.get(message['resource_id'])
        if (item['state'] != 'ready' or item['suppressed'] or item['media_id'] != message['media_id']
                or item['version_key'] != message['version_key']):
            raise ValueError('Prepared current episode is no longer eligible')
        match = re.fullmatch(r'tmdb:tv:([1-9]\d*):s([1-9]\d*):e([1-9]\d*)', item['media_id'])
        if match is None:
            raise ValueError('Regular TV episode required for advance')
        rows = self.db.execute('''SELECT p.payload,b.task FROM prepared_bindings b JOIN tasks t ON t.id=b.task
            JOIN preparation_targets p ON p.task=b.task AND p.media_id=b.media_id AND p.version_key=b.version_key
            WHERE b.resource=? AND t.account=? AND t.source_hash=? AND b.media_id=? AND b.version_key=?''',
            (item['resource_id'], item['account'], message['source_info_hash'], item['media_id'], item['version_key'])).fetchall()
        if len(rows) != 1:
            raise ValueError('Missing or ambiguous prepared source provenance')
        selected = json.loads(rows[0][0])['_selection']
        file = selected['file']
        release_title = selected['release_title']
        # Published source-card labels intentionally name the actual episode.
        # They are not the original pack context: a bare [02] loses [S1 Fin].
        # Recover that context only from an accepted intent which admitted this
        # exact task/media/version. Keep legacy records immutable, and still run
        # the normal fresh-metadata selector/catalog proof after intake.
        origin = self.db.execute('SELECT payload,state,result FROM preparation_intents WHERE id=?',
                                 (selected['request_id'],)).fetchone()
        if origin is not None and origin['state'] == 'accepted':
            original = json.loads(origin['payload'])
            media, _, source_hash = checked_body(original)
            admitted = json.loads(origin['result']).get('tasks', [])
            if (source_hash == message['source_info_hash'] and media['kind'] == 'tv'
                    and media['tmdb_id'] == int(match[1]) and media['season'] == int(match[2])
                    and media['anime'] == selected['anime'] and media['title'] == selected['title']
                    and any(task.get('task_id') == rows[0]['task']
                            and task.get('media_id') == item['media_id']
                            and task.get('version_key') == item['version_key'] for task in admitted)):
                release_title = media['release_title']
        body = dict(request_id=message['request_id'], purpose='current',
            media=dict(tmdb_id=int(match[1]), kind='tv', season=int(match[2]), episode=int(match[3]),
                       anime=selected['anime'], title=selected['title'], release_title=release_title),
            selected=dict(source_info_hash=message['source_info_hash'], torrent_file_id=file['id'],
                          torrent_path=file['path'], torrent_file_bytes=file['length']))
        return self.accept(body)

    def take(self):
        with self.ledger.transaction():
            row = self.db.execute("SELECT id,payload FROM preparation_intents WHERE state='queued' ORDER BY updated,id LIMIT 1").fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE preparation_intents SET state='validating',updated=? WHERE id=?", (self.now(), row[0]))
        return json.loads(row[1])

    def finish(self, identifier, result, succeeded):
        state = 'accepted' if succeeded else 'failed'
        with self.ledger.transaction():
            changed = self.db.execute("UPDATE preparation_intents SET state=?,result=?,updated=? WHERE id=? AND state='validating'",
                                      (state, encode(result), self.now(), identifier)).rowcount
            if changed:
                self.ledger._audit('source_intent_' + state, None, {'request_id': identifier, 'result': result})
        return bool(changed)
