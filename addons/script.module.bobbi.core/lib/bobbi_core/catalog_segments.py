"""Manual exact-observation annotations in the existing review transaction.

These are not detected media facts or seek/EOF authority. In particular an
outro annotation cannot authorize skipping a credits scene or starting next.
"""
from bobbi_core.typed_ref import KINDS as PATH_KINDS
from copy import deepcopy
import json
import re

from .catalog_query import opaque

KINDS = ('intro', 'recap', 'outro', 'credits_scene')
MAX_MS = 864000000


def descriptor(value):
    if (type(value) is not dict or set(value) != {'observation_key', 'duration_ms', 'items'} or
            type(value['observation_key']) is not str or
            not re.fullmatch('[0-9a-f]{64}', value['observation_key']) or
            type(value['items']) is not list or len(value['items']) > len(KINDS)):
        raise ValueError('CATALOG_SEGMENTS_INVALID')
    duration = value['duration_ms']
    if not value['items']:
        if duration is not None:
            raise ValueError('CATALOG_SEGMENTS_INVALID')
    elif type(duration) is not int or not 0 < duration <= MAX_MS:
        raise ValueError('CATALOG_SEGMENTS_INVALID')
    items = []
    for row in value['items']:
        if (type(row) is not dict or set(row) != {'kind', 'start_ms', 'end_ms'} or
                type(row['kind']) is not str or row['kind'] not in KINDS or
                any(type(row[key]) is not int for key in ('start_ms', 'end_ms')) or
                not 0 <= row['start_ms'] < row['end_ms'] <= duration):
            raise ValueError('CATALOG_SEGMENTS_INVALID')
        items.append(dict(row))
    items.sort(key=lambda row: row['start_ms'])
    if (len({row['kind'] for row in items}) != len(items) or
            any(left['end_ms'] > right['start_ms'] for left, right in zip(items, items[1:]))):
        raise ValueError('CATALOG_SEGMENTS_OVERLAP')
    return dict(observation_key=value['observation_key'], duration_ms=duration, items=items)


def _record(value):
    if (type(value) is not dict or set(value) !=
            {'observation_key', 'duration_ms', 'items', 'source', 'observed_at'} or
            value['source'] != 'manual' or type(value['observed_at']) not in (int, float) or
            not 0 <= value['observed_at'] < 4102444800):
        raise ValueError('CATALOG_SEGMENTS_INVALID')
    return dict(descriptor({key: value[key] for key in ('observation_key', 'duration_ms', 'items')}),
                source='manual', observed_at=value['observed_at'])


def stored(index, file_id):
    row = index.db.execute('SELECT detail FROM file_segments WHERE file=?', (file_id,)).fetchone()
    return _record(json.loads(row[0])) if row else None


def summary(item, value, expected):
    if value is None:
        return None
    ref = item['file_ref']
    current = value['observation_key'] == opaque(ref)
    if ref.get('reference_kind') in PATH_KINDS:
        # Read/review scopes deliberately avoid filesystem probes. Only an
        # explicitly supplied authority can invalidate the saved observation;
        # a match below still means saved evidence, never current playback.
        if expected.get('generation'):
            current = current and expected['generation'] == ref.get('mount_generation', ref.get('source_generation'))
        if ref['reference_kind'] == 'local_path' and 'root_signature' in expected:
            current = current and expected.get('root_signature') == ref['root_signature']
    return dict(deepcopy(value), duration_source='manual', auto_allowed=False,
                state='matched' if current and item['available'] else 'verification_required')


def target(index, expected, cmd, item):
    current = stored(index, cmd['file_id'])
    if cmd['action'] == 'restore_description':
        # This is saved manual evidence, not a fresh probe or automatic policy.
        # In particular an old observation_key stays old after a replacement.
        value = cmd['mapping']['segments']
        return _record(value) if value is not None else None
    if cmd['action'] == 'undo':
        row = index.db.execute('SELECT before_segments FROM segment_changes WHERE file=? AND revision=?',
            (cmd['file_id'], item['revision'])).fetchone()
        # Legacy revisions predate this annotation domain. They cannot delete
        # newer data merely because there is no old domain-specific snapshot.
        if row is None:
            return current
        return _record(json.loads(row[0])) if row[0] else None
    if cmd['action'] != 'segments':
        return current
    value = descriptor(cmd['mapping'])
    if value['observation_key'] != opaque(item['file_ref']):
        raise ValueError('CATALOG_SEGMENTS_OBSERVATION_CHANGED')
    if not value['items']:
        return None
    record = _record(dict(value, source='manual', observed_at=index.now()))
    if summary(item, record, expected)['state'] != 'matched':
        raise ValueError('CATALOG_SEGMENTS_OBSERVATION_CHANGED')
    return record


def write(index, file_id, revision, before, after):
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':')) if value is not None else None
    index.db.execute('INSERT INTO segment_changes VALUES(?,?,?,?)',
        (file_id, revision, encode(before), encode(after)))
    index.db.execute('DELETE FROM segment_changes WHERE file=? AND revision<?', (file_id, revision - 31))
    if after is None:
        index.db.execute('DELETE FROM file_segments WHERE file=?', (file_id,))
    else:
        index.db.execute('INSERT OR REPLACE INTO file_segments VALUES(?,?)', (file_id, encode(after)))
