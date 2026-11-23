"""Whitelisted file progress in the existing atomic history database.

The adapter has no threads and performs no network IO. Existing native and
standard history writers call save; Host reserves generation before playback.
The strict v1 row stays readable by retained programs. Start observations live
in this same store as dependent records, not a cache or another authority;
legacy writes invalidate their exact row binding without a schema migration.
"""
import math
import re
import time
from uuid import uuid4

from bobbi_core.file_ref import validate

KEY = 'bobbi:file_history:v1'
FACTS_KEY = KEY + ':playback_start'
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


def coalescing_key(data, root):
    """Pure admission identity shared by the existing history writers."""
    if type(data) is not dict or data.get('_pan_file') is not True:
        return None
    try:
        context = data['_file_history']
        if type(context) is not dict or set(context) != {'file_ref', 'generation', 'session_id'}:
            return None
        request = data.get('request_id')
        if type(request) is not str or not re.fullmatch('[0-9a-f]{32}', request):
            return None
        duration = _number(data.get('total_time'), True)
        value = record(dict(version=1, id=context['file_ref']['id'], file_ref=context['file_ref'],
            generation=context['generation'], session_id=context['session_id'],
            sequence=data.get('_file_history_sequence', 0), position=data.get('current_time', 0),
            duration=duration if duration else None, completion_reason=data.get('terminal_reason', 'UNKNOWN'),
            updated_at=0))
        if value['sequence'] <= 0:
            return None
        return (root, request, value['file_ref'], value['generation'], value['session_id'])
    except (ValueError, TypeError, KeyError):
        return None


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

    def media_facts(self, references):
        """One read-only snapshot; the history row remains strictly legacy v1.

        Return the original observation, not a rebind to the requested file.
        The catalogue compares the entire opaque FileRef before displaying a
        matching duration. Renames, moves and replacements keep old evidence.
        """
        from bobbi_core.catalog_query import opaque
        from bobbi_core.file_media_facts import MAX_BATCH
        if type(references) is not list or not 1 <= len(references) <= MAX_BATCH:
            raise ValueError('FILE_MEDIA_FACTS_BATCH_INVALID')
        references = [validate(ref) for ref in references]
        snapshot = self.database.get_keys_checked((KEY, FACTS_KEY))
        if type(snapshot) is not dict or set(snapshot) != {KEY, FACTS_KEY}:
            raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
        rows, observations = snapshot[KEY], snapshot[FACTS_KEY]
        if rows is None:
            return {}
        if type(rows) is not dict:
            raise ValueError('FILE_HISTORY_SCHEMA_UNSUPPORTED')
        result = {}
        for ref in references:
            if ref['id'] not in rows:
                continue
            try:
                saved = record(rows[ref['id']])
                if saved['id'] != ref['id']:
                    raise ValueError('FILE_HISTORY_RECORD_INVALID')
                observed = None
                if type(observations) is dict and ref['id'] in observations:
                    try:
                        from bobbi_core.playback_start_facts import observation
                        entry = observations[ref['id']]
                        binding = {key: saved[key] for key in ('file_ref', 'generation', 'session_id', 'sequence')}
                        if (type(entry) is dict and set(entry) == {'binding', 'observation'}
                                and type(entry['binding']) is dict and set(entry['binding']) == set(binding)
                                and all(type(entry['binding'][key]) is int for key in ('generation', 'sequence'))
                                and validate(entry['binding']['file_ref']) == saved['file_ref']
                                and entry['binding'] == binding and saved['sequence'] > 0):
                            checked = observation(entry['observation'], saved['file_ref'])
                            if all(checked[key] == saved[key] for key in ('generation', 'session_id')):
                                observed = checked
                    except (ValueError, TypeError, KeyError, OverflowError):
                        self.report('FILE_HISTORY_FACTS_REJECTED')
                if (saved['duration'] is not None and saved['duration'] > 0) or observed is not None:
                    result[ref['id']] = dict(source='playback_history',
                        observation_key=opaque(saved['file_ref']), duration_seconds=saved['duration'],
                        recorded_at=saved['updated_at'])
                    if observed is not None:
                        result[ref['id']]['playback_start'] = dict(recorded_at=observed['recorded_at'], facts=observed['facts'])
            except (ValueError, TypeError, KeyError, OverflowError):
                self.report('FILE_HISTORY_RECORD_INVALID')
        return result

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
        """Retain the legacy bool: True also includes an ignored old report."""
        return self._save(data, detailed=False)

    def save_result(self, data):
        """Local persistence evidence, never lifecycle proof or a write permit.

        Only this active call gets a receipt. A later pending-journal replay
        cannot notify a stale caller. The v1 history row is unchanged.
        """
        return self._save(data, detailed=True)

    def _save(self, data, detailed):
        """Never serialize data or recurse through it: select only primitives."""
        try:
            context = data.get('_file_history')
            if context is None:
                return dict(disposition='unsupported', receipt=None) if detailed else True
            if type(context) is not dict or set(context) != {'file_ref', 'generation', 'session_id'}:
                raise ValueError('FILE_HISTORY_CONTEXT_INVALID')
            ref = validate(context['file_ref'])
            duration = _number(data.get('total_time'), True)
            duration = duration if duration else None
            value = dict(version=1, id=ref['id'], file_ref=ref,
                position=_number(data.get('current_time', 0)), duration=duration,
                completion_reason=data.get('terminal_reason', 'UNKNOWN'), updated_at=self.clock(),
                generation=context['generation'], session_id=context['session_id'],
                sequence=data.get('_file_history_sequence', 0))
            observed = None
            if data.get('_file_start_observation') is not None:
                try:
                    from bobbi_core.playback_start_facts import observation
                    observed = observation(data['_file_start_observation'], ref)
                    if (data.get('_pan_file') is not True or data.get('selection_policy') != 'exact'
                            or any(observed[key] != context[key] for key in ('generation', 'session_id'))
                            or observed['expected']['request_id'] != data.get('request_id')):
                        raise ValueError('FILE_HISTORY_FACTS_CONTEXT_INVALID')
                except (ValueError, TypeError, KeyError, OverflowError):
                    observed = None
                    self.report('FILE_HISTORY_FACTS_REJECTED')
            value = record(value)
            if value['sequence'] <= 0:
                raise ValueError('FILE_HISTORY_SEQUENCE_INVALID')
            # One admitted operation owns progress and its dependent facts.
            # A True commit may still mean a stale report was ignored.
            if detailed:
                disposition = self.database.file_report_result(KEY, ref['id'], value, observation=observed)
                if disposition == 'failed':
                    self.report('FILE_HISTORY_WRITE_FAILED')
                receipt = ({key: value[key] for key in ('file_ref', 'generation', 'session_id',
                    'sequence', 'completion_reason', 'position', 'duration')} if disposition == 'applied' else None)
                return dict(disposition=disposition, receipt=receipt)
            result = self.database.file_report(KEY, ref['id'], value, observation=observed)
            if result is not True:
                self.report('FILE_HISTORY_WRITE_FAILED')
            return result
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            self.report('FILE_HISTORY_RECORD_REJECTED')
            return dict(disposition='invalid', receipt=None) if detailed else False

    def remove(self, identifier, expected):
        current = self.get(identifier)
        if current != expected:
            return False
        return self.database.delete_item_if(KEY, identifier, current)
