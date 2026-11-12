"""Bounded manual descriptions, not accounts, playback grants or a DB backup.

Only already-observed native file identities may propose existing review
commands. The target keeps its own revisions, requests, receipts and history.
"""
from copy import deepcopy
import json

from .catalog_review import command, mapping
from .file_ref import validate, same_file


SCHEMA = 'bobbi-catalog-manual-v1'
MAX_ENTRIES = 100
MAX_BYTES = 1024 * 1024


def _invalid():
    raise ValueError('CATALOG_TRANSFER_INVALID')


def _entry(raw):
    if (type(raw) is not dict or set(raw) != {'reference', 'state', 'mapping', 'source_revision'}
            or type(raw['source_revision']) is not int or not 1 <= raw['source_revision'] < 2**63):
        _invalid()
    ref = validate(raw['reference'])
    state, value = raw['state'], raw['mapping']
    if type(state) is not str or state not in ('confirmed', 'unmatched', 'ignored'):
        _invalid()
    if value is not None:
        value = mapping(value)
    if (state == 'confirmed' and (value is None or value['kind'] == 'custom')
            or state == 'ignored' and value is not None
            or state == 'unmatched' and value is not None and value['kind'] != 'custom'):
        _invalid()
    return dict(reference=ref, state=state, mapping=value, source_revision=raw['source_revision'])


def checked(value):
    if (type(value) is not dict or set(value) != {'schema', 'scope', 'entries'}
            or value['schema'] != SCHEMA or type(value['scope']) is not dict
            or set(value['scope']) != {'provider', 'account_id'}
            or type(value['entries']) is not list or not 1 <= len(value['entries']) <= MAX_ENTRIES):
        _invalid()
    entries = [_entry(row) for row in value['entries']]
    if len({row['reference']['id'] for row in entries}) != len(entries):
        _invalid()
    scope = value['scope']
    if any((row['reference']['provider'], row['reference']['account_id']) !=
           (scope['provider'], scope['account_id']) for row in entries):
        _invalid()
    return dict(schema=SCHEMA, scope=dict(scope), entries=entries)


def dumps(value):
    result = json.dumps(checked(value), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(result.encode('utf-8')) > MAX_BYTES:
        raise ValueError('CATALOG_TRANSFER_LIMIT')
    return result


def loads(raw):
    if type(raw) not in (str, bytes) or not 0 < len(raw.encode('utf-8') if type(raw) is str else raw) <= MAX_BYTES:
        raise ValueError('CATALOG_TRANSFER_LIMIT')

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                _invalid()
            value[key] = item
        return value

    def invalid_constant(_):
        _invalid()

    try:
        return checked(json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError('CATALOG_TRANSFER_INVALID') from None


def export_records(expected, records):
    if type(records) is not list or not 1 <= len(records) <= MAX_ENTRIES:
        raise ValueError('CATALOG_TRANSFER_LIMIT')
    if any(row.get('provenance') != 'manual' or row.get('supplement') is not None for row in records):
        _invalid()
    value = dict(schema=SCHEMA, scope={key: expected[key] for key in ('provider', 'account_id')},
        entries=[dict(reference=row['file_ref'], state=row['state'], mapping=row['mapping'],
                      source_revision=row['revision']) for row in records])
    return loads(dumps(value))  # One whitelist and byte budget at both boundaries.


def preview(value, expected, records):
    """Read-only plan; weak content evidence is never preselected by the UI."""
    value = checked(value)
    if (expected.get('provider'), expected.get('account_id')) != (
            value['scope']['provider'], value['scope']['account_id']):
        raise ValueError('CATALOG_ACCOUNT_MISMATCH')
    current = {row['file_ref']['id']: row for row in records}
    result = []
    for entry in value['entries']:
        ref = entry['reference']
        target = current.get(ref['id'])
        row = dict(file_id=ref['id'], name=ref['name'], status='unresolved',
                   reason='FILE_NOT_OBSERVED', command=None)
        if target is not None:
            actual = validate(target['file_ref'])
            if target.get('supplement') is not None:
                row.update(status='conflict', reason='TARGET_IS_SUPPLEMENT')
            elif not target.get('available') or not same_file(ref, actual):
                row['reason'] = 'FILE_CHANGED_OR_UNAVAILABLE'
            elif target['state'] == entry['state'] and target['mapping'] == entry['mapping']:
                row.update(status='unchanged', reason='ALREADY_EQUAL')
            elif target.get('provenance') == 'manual':
                row.update(status='conflict', reason='TARGET_HAS_MANUAL_STATE')
            else:
                action = ('confirm' if entry['mapping'] is not None else
                          'ignore' if entry['state'] == 'ignored' else 'unbind')
                cmd = command(dict(file_id=ref['id'], expected_revision=target['revision'],
                                   action=action, mapping=entry['mapping']))
                strong = ref['fingerprint'] is not None and ref['fingerprint'] == actual['fingerprint']
                row.update(status='ready' if strong else 'review_required',
                           reason='MATCHED_CONTENT' if strong else 'CONTENT_EVIDENCE_WEAK', command=cmd)
            row.update(current_revision=target['revision'], before=deepcopy(target['mapping']),
                       after=deepcopy(entry['mapping']))
        result.append(row)
    return dict(items=result)
