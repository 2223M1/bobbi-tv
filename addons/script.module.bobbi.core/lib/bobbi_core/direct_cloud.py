"""Durable, bounded preparation of exact catalogue HTTP files in personal 115.

This is separate from torrent provenance: URL/file hashes are never presented
as BT hashes. Only the owner thread uses SQLite; provider IO gets plain copies.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

MOUNT = '/storage/videos/Clouddrive/CloudDrive'
SOURCE_KEYS = {'provider', 'guid', 'locator', 'title', 'size'}
MEDIA_KEYS = {'tmdb_id', 'kind', 'season', 'episode'}
ACTIVE = ('queued', 'inspect', 'submit_ready', 'submitting', 'waiting', 'uncertain', 'qualify')
READ_RETRY_ERRORS = frozenset(('TimeoutError', 'ConnectionError', 'OSError',
    'ReadTimeout', 'ConnectTimeout', 'Timeout', 'ConnectionResetError',
    'DIRECT_SOURCE_DEADLINE', 'DIRECT_SOURCE_RANGE_UNAVAILABLE', 'DIRECT_SOURCE_TRUNCATED'))


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def checked(body):
    if not isinstance(body, dict) or set(body) != {'request_id', 'source', 'media'}:
        raise ValueError('DIRECT_INTENT_FIELDS')
    if not isinstance(body['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', body['request_id']):
        raise ValueError('DIRECT_REQUEST_ID')
    source, media = body['source'], body['media']
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS or source['provider'] != 'mdsub':
        raise ValueError('DIRECT_PROVIDER_UNSUPPORTED')
    if (not isinstance(source['guid'], str) or not re.fullmatch('mdsub:[0-9a-f]{64}', source['guid'])
            or not isinstance(source['title'], str) or not 1 <= len(source['title']) <= 1024
            or any(c in source['title'] for c in ('/', '\\', '\x00'))
            or any(ord(c) < 32 for c in source['title'])
            or not isinstance(source['locator'], str) or len(source['locator']) > 8192
            or not source['locator'].startswith('https://pan.mdsub.top/api/raw?')
            or type(source['size']) is not int or not 16384 <= source['size'] <= 200 * 1024**3):
        raise ValueError('DIRECT_SOURCE_IDENTITY')
    if (not isinstance(media, dict) or set(media) != MEDIA_KEYS or media['kind'] not in ('tv', 'movie')
            or any(type(media[k]) is not int for k in ('tmdb_id', 'season', 'episode'))
            or media['tmdb_id'] <= 0):
        raise ValueError('DIRECT_MEDIA_IDENTITY')
    if (media['kind'] == 'tv' and (media['season'] < 0 or media['episode'] < 1)
            or media['kind'] == 'movie' and (media['season'] != 0 or media['episode'] != 0)):
        raise ValueError('DIRECT_EPISODE_IDENTITY')
    return source, media


def source_key(body):
    source, media = checked(body)
    return hashlib.sha256(encode(dict(source=source, media=media)).encode()).hexdigest()


def validate_catalog(body):
    source, media = checked(body)
    from bobbi_mdsub.catalog import load, find_sources, source_fields
    rows = find_sources(load(), media['tmdb_id'], media['kind'], media['season'], media['episode'])
    rows = [row for row in rows if media['kind'] == 'movie' or row['episodes'] == [media['episode']]]
    matches = []
    for row in rows:
        fields = source_fields(row)
        expected = dict(provider='mdsub', guid=fields['guid'], locator=fields['url'], title=fields['title'], size=fields['size'])
        if expected == source:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('DIRECT_CATALOG_CHANGED')
    return source


class DirectQueue:
    def __init__(self, path, snapshot, account, destination, io, clock=time.time, account_scope=None):
        self.account_scope = account_scope
        self.db = sqlite3.connect(str(path), timeout=.1)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS direct_jobs (key TEXT PRIMARY KEY, account TEXT, destination TEXT, '
                        'body TEXT, state TEXT, created REAL, due REAL, attempts INTEGER, evidence TEXT, error TEXT)')
        self.db.execute("UPDATE direct_jobs SET state='queued' WHERE state='inspect'")
        # A crash or lost reply is not permission to replay a cloud mutation.
        self.db.execute("UPDATE direct_jobs SET state='uncertain' WHERE state='submitting'")
        # Old versions made exhausted read-only inspections permanently failed.
        # A successful inspect always persists evidence before any submission;
        # empty evidence is therefore required for this narrow migration.
        for row in self.db.execute("SELECT key,error FROM direct_jobs WHERE state='failed' AND attempts>=4 AND evidence='{}'").fetchall():
            if row['error'] in READ_RETRY_ERRORS:
                self.db.execute("UPDATE direct_jobs SET state='retryable' WHERE key=?", (row['key'],))
        self.db.commit()
        self.snapshot, self.account, self.destination = Path(snapshot), account, destination
        self.io, self.clock, self.pending = io, clock, None
        self.publish()

    def close(self):
        self.db.close()

    def accept(self, body):
        key = source_key(body)
        row = self.db.execute('SELECT * FROM direct_jobs WHERE key=?', (key,)).fetchone()
        if row is not None:
            if row['account'] != self.account or row['destination'] != self.destination:
                raise ValueError('DIRECT_ACCOUNT_CHANGED')
            if (row['state'] == 'retryable' and row['error'] in READ_RETRY_ERRORS
                    and row['evidence'] == '{}'
                    and json.loads(row['body'])['request_id'] != body['request_id']):
                validate_catalog(body)
                if self.db.execute("SELECT COUNT(*) FROM direct_jobs WHERE state NOT IN ('ready','failed','rejected','retryable')").fetchone()[0] >= 16:
                    raise ValueError('DIRECT_QUEUE_FULL')
                now = self.clock()
                self.db.execute("UPDATE direct_jobs SET body=?,state='queued',created=?,due=?,attempts=0,error='' WHERE key=?",
                                (encode(body), now, now, key))
                self.db.commit()
                self.publish()
        else:
            if (self.db.execute('SELECT COUNT(*) FROM direct_jobs').fetchone()[0] >= 2048
                    or self.db.execute("SELECT COUNT(*) FROM direct_jobs WHERE state NOT IN ('ready','failed','rejected','retryable')").fetchone()[0] >= 16):
                raise ValueError('DIRECT_QUEUE_FULL')
            now = self.clock()
            self.db.execute('INSERT INTO direct_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (key, self.account, self.destination, encode(body), 'queued', now, now, 0, '{}', ''))
            self.db.commit()
            self.publish()
        return self.status(key)

    def status(self, key):
        row = self.db.execute('SELECT * FROM direct_jobs WHERE key=?', (key,)).fetchone()
        if row is None:
            return dict(key=key, state='absent')
        return dict(key=key, state=row['state'], error=row['error'])

    def next_action(self):
        if self.pending is not None:
            return None
        row = self.db.execute("SELECT * FROM direct_jobs WHERE state NOT IN ('ready','failed','rejected','retryable') "
                              'AND due<=? ORDER BY created,key LIMIT 1', (self.clock(),)).fetchone()
        if row is None:
            return None
        if self.clock() - row['created'] > 3600:
            self.db.execute("UPDATE direct_jobs SET state='failed',error='PREPARATION_DEADLINE' WHERE key=?", (row['key'],))
            self.db.commit(); self.publish()
            return None
        state = row['state']
        kind = 'inspect' if state == 'queued' else 'submit' if state == 'submit_ready' else 'qualify' if state == 'qualify' else 'poll'
        if kind == 'submit':
            self.db.execute("UPDATE direct_jobs SET state='submitting' WHERE key=?", (row['key'],))
            self.db.commit()  # Durable intent precedes AddOfflineFiles.
        elif kind == 'inspect':
            self.db.execute("UPDATE direct_jobs SET state='inspect' WHERE key=?", (row['key'],))
            self.db.commit()
        self.pending = dict(key=row['key'], kind=kind, account=row['account'], destination=row['destination'],
            body=json.loads(row['body']), evidence=json.loads(row['evidence']))
        return self.pending

    def perform(self, action):
        try:
            return dict(ok=True, result=self.io.perform(action))
        except Exception as error:
            message = str(error)
            reason = message if re.fullmatch('DIRECT_[A-Z_]{1,56}', message) else type(error).__name__
            return dict(ok=False, error=reason)

    def complete(self, action, result):
        if action != self.pending:
            return False
        row = self.db.execute('SELECT * FROM direct_jobs WHERE key=?', (action['key'],)).fetchone()
        evidence = json.loads(row['evidence'])
        attempts = row['attempts'] + 1
        error = ''
        if not result.get('ok'):
            error = result.get('error', 'IO_FAILURE')
            if not re.fullmatch('[A-Za-z0-9_]{1,64}', error):
                error = 'IO_FAILURE'
            state = 'uncertain' if action['kind'] == 'submit' else 'queued' if action['kind'] == 'inspect' else row['state']
            due = self.clock() + min(120, 15 * attempts)
            if action['kind'] == 'inspect' and attempts >= 4:
                state = 'retryable' if error in READ_RETRY_ERRORS and not evidence else 'failed'
        else:
            value = result['result']
            evidence.update(value.get('evidence', {}))
            state = value['state']
            if state not in ('submit_ready', 'waiting', 'qualify', 'ready', 'rejected', 'failed', 'uncertain'):
                raise ValueError('DIRECT_RESULT_STATE')
            due = self.clock() + (15 if state in ('waiting', 'uncertain') else 0)
        self.db.execute('UPDATE direct_jobs SET state=?,due=?,attempts=?,evidence=?,error=? WHERE key=?',
                        (state, due, attempts, encode(evidence), error, action['key']))
        self.db.commit()
        self.pending = None
        self.publish()
        return True

    def publish(self):
        entries = []
        for row in self.db.execute('SELECT * FROM direct_jobs WHERE account=? AND destination=?', (self.account, self.destination)):
            body, evidence = json.loads(row['body']), json.loads(row['evidence'])
            item = dict(key=row['key'], state=row['state'], source=body['source'], media=body['media'], error=row['error'])
            if row['state'] == 'ready':
                item.update(file=evidence['file'], proof=evidence['proof'], video=evidence['video'])
            entries.append(item)
        document = dict(schema=1, account=self.account, destination=self.destination, entries=entries)
        if self.account_scope is not None:
            document['account_scope'] = self.account_scope
        data = encode(document).encode()
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.snapshot.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, self.snapshot)


class DirectResolver:
    """Fresh read-only file identity check through the existing bounded lane."""
    def __init__(self, queue, io):
        self.queue, self.io = queue, io

    def plan(self, body):
        if (not isinstance(body, dict) or set(body) != {'key', 'request_id', 'verification_id'}
                or any(not isinstance(body[k], str) or not re.fullmatch('[0-9a-f]{32}', body[k]) for k in ('request_id', 'verification_id'))
                or not isinstance(body['key'], str) or not re.fullmatch('[0-9a-f]{64}', body['key'])):
            raise ValueError('DIRECT_RESOLVE_IDENTITY')
        row = self.queue.db.execute('SELECT * FROM direct_jobs WHERE key=?', (body['key'],)).fetchone()
        if row is None or row['state'] != 'ready' or row['account'] != self.queue.account:
            raise ValueError('DIRECT_NOT_READY')
        return dict(body=dict(body), intent=json.loads(row['body']), evidence=json.loads(row['evidence']),
                    account=row['account'], destination=row['destination'])

    def perform(self, plan):
        return self.io.verify(plan)

    def finish(self, plan, verified):
        portable = isinstance(verified, dict) and set(verified) == {'playback_url'} and getattr(self.io, 'address', None) is not None
        if verified is not True and not portable:
            return dict(state='unavailable')
        current = self.plan(plan['body'])
        if current != plan:
            return dict(state='unavailable')
        item = plan['evidence']['file']
        result = dict(state='ready', **plan['body'], path=MOUNT + item['path'], bytes=item['bytes'],
                      proof=plan['evidence']['proof'])
        if portable:
            from .prepared_transport import checked_url
            result['playback_url'] = checked_url(verified['playback_url'])
        return result
