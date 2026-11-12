"""Whitelisted file progress in the existing atomic history database.

The adapter has no threads and performs no network IO. Existing native and
standard history writers call save; Host reserves generation before playback.
"""
import math
import re
import time
from uuid import uuid4

from bobbi_core.file_ref import validate

KEY = 'bobbi:file_history:v1'
LIMIT = 500
REASONS = frozenset(('STARTED', 'PROGRESS', 'NATURAL_EOF', 'STOP', 'ERROR', 'UNKNOWN',
    'CANCEL', 'CANCELLED', 'SUPERSEDED', 'ACCOUNT_CHANGED', 'EXTERNAL_PLAYBACK', 'EVENT_OVERFLOW',
    'SERVICE_CLOSED', 'NEXT_DEADLINE', 'SHUTDOWN'))
FIELDS = frozenset(('version', 'id', 'file_ref', 'position', 'duration', 'completion_reason',
                    'updated_at', 'generation', 'session_id', 'sequence'))


def _number(value, optional=False):
    if optional and value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 864000:
        raise ValueError('FILE_HISTORY_POSITION_INVALID')
    return float(value)


def record(value):
    if (type(value) is not dict or set(value) != FIELDS or value.get('version') != 1
            or type(value.get('version')) is not int):
        raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
    result = dict(value, file_ref=validate(value['file_ref']))
    if (result['id'] != result['file_ref']['id'] or result['completion_reason'] not in REASONS
            or type(result['session_id']) is not str or not re.fullmatch('[0-9a-f]{32}', result['session_id'])
            or any(type(result[key]) is not int or result[key] < minimum
                   for key, minimum in (('generation', 1), ('sequence', 0)))
            or type(result['updated_at']) not in (int, float)
            or not math.isfinite(result['updated_at']) or not 0 <= result['updated_at'] < 4102444800):
        raise ValueError('FILE_HISTORY_RECORD_INVALID')
    result['position'], result['duration'] = _number(result['position']), _number(result['duration'], True)
    if result['duration'] is not None and result['position'] > result['duration']:
        raise ValueError('FILE_HISTORY_POSITION_INVALID')
    return result


class FileHistory:
    def __init__(self, database=None, report=None, clock=time.time):
        if database is None:
            from lib.db.pickle_db import PickleDatabase
            database = PickleDatabase()
        self.database, self.clock, self.report = database, clock, report or (lambda code: None)

    def begin(self, ref):
        ref = validate(ref)
        def reserve(previous):
            previous = record(previous) if previous is not None else None
            # Reserving a writer is not an observation of the selected content.
            # Keep the saved evidence with its progress until this session reports;
            # a failed open must not attach old progress to a replacement file.
            return dict(version=1, id=ref['id'], file_ref=previous['file_ref'] if previous else ref,
                position=previous['position'] if previous else 0.,
                duration=previous['duration'] if previous else None,
                completion_reason=previous['completion_reason'] if previous else 'STARTED',
                updated_at=previous['updated_at'] if previous else self.clock(),
                generation=previous['generation'] + 1 if previous else 1,
                session_id=uuid4().hex, sequence=0)
        try:
            value = self.database.begin_file_session(KEY, ref['id'], reserve, LIMIT)
            return dict(file_ref=ref, generation=value['generation'], session_id=value['session_id'])
        except (OSError, ValueError, TypeError, RuntimeError):
            self.report('FILE_HISTORY_RESERVATION_FAILED')
            return None

    def get(self, identifier):
        if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
            raise ValueError('FILE_HISTORY_ID_INVALID')
        rows = self.database.get_key_checked(KEY)
        if rows is None:
            raise ValueError('FILE_HISTORY_NOT_FOUND')
        if type(rows) is not dict:
            raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
        if identifier not in rows:
            raise ValueError('FILE_HISTORY_NOT_FOUND')
        return record(rows[identifier])

    def rows(self):
        return self.read_rows(self.database.get_key_checked(KEY), self.report)

    @staticmethod
    def read_rows(rows, report=lambda code: None):
        if rows is None:
            return []
        if type(rows) is not dict:
            raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
        result = []
        for key, value in rows.items():
            try:
                checked = record(value)
                if checked['id'] != key:
                    raise ValueError('FILE_HISTORY_RECORD_INVALID')
                if checked['position'] > 0 and checked['completion_reason'] != 'NATURAL_EOF':
                    result.append(checked)
            except (ValueError, TypeError, KeyError):
                report('FILE_HISTORY_RECORD_INVALID')
        return sorted(result, key=lambda row: row['updated_at'], reverse=True)[:LIMIT]

    def save(self, data):
        """Never serialize data or recurse through it: select only primitives."""
        try:
            context = data.get('_file_history')
            if context is None:
                return True  # Unsupported / unavailable history is not fake support.
            if type(context) is not dict or set(context) != {'file_ref', 'generation', 'session_id'}:
                raise ValueError('FILE_HISTORY_CONTEXT_INVALID')
            ref = validate(context['file_ref'])
            duration = _number(data.get('total_time'), True)
            duration = duration if duration else None
            value = record(dict(version=1, id=ref['id'], file_ref=ref,
                position=_number(data.get('current_time', 0)), duration=duration,
                completion_reason=data.get('terminal_reason', 'UNKNOWN'), updated_at=self.clock(),
                generation=context['generation'], session_id=context['session_id'],
                sequence=data.get('_file_history_sequence', 0)))
            if value['sequence'] <= 0:
                raise ValueError('FILE_HISTORY_SEQUENCE_INVALID')
            result = self.database.file_report(KEY, ref['id'], value)
            if result is not True:
                self.report('FILE_HISTORY_WRITE_FAILED')
            return result
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            self.report('FILE_HISTORY_RECORD_REJECTED')
            return False

    def remove(self, identifier, expected):
        current = self.get(identifier)
        if current != expected:
            return False
        return self.database.delete_item_if(KEY, identifier, current)
