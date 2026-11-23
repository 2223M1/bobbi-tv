"""Bounded manual descriptions, not accounts, playback grants or a DB backup.

Only already-observed native file identities may propose existing review
commands. The target keeps its own revisions, requests, receipts and history.
"""
from copy import deepcopy
import json

from .catalog_review import command, mapping
from .file_ref import validate, same_file


SCHEMA = 'bobbi-catalog-manual-v1'
SEGMENT_SCHEMA = 'bobbi-catalog-manual-v2'
SUPPLEMENT_SCHEMA = 'bobbi-catalog-manual-v3'
SCHEMAS = (SCHEMA, SEGMENT_SCHEMA, SUPPLEMENT_SCHEMA)
EXPORT_STATES = ('confirmed', 'unmatched', 'ignored')
MAX_ENTRIES = 100
MAX_BYTES = 1024 * 1024


def _invalid():
    raise ValueError('CATALOG_TRANSFER_INVALID')


def segment_record(value):
    """Strip only known projection fields; preserve the original observation."""
    if value is None:
        return None
    from .catalog_segments import _record
    fields = {'observation_key', 'duration_ms', 'items', 'source', 'observed_at'}
    if type(value) is not dict or not fields <= set(value) or set(value) - fields - {
            'state', 'duration_source', 'auto_allowed'}:
        _invalid()
    return _record({key: value[key] for key in fields})


def supplement_record(value):
    if value is None:
        return None
    from .catalog_supplements import descriptor
    if (type(value) is not dict or set(value) != {'relation', 'parent_reference', 'state'} or
            value['state'] not in ('confirmed', 'verification_required')):
        _invalid()
    relation = descriptor(value['relation'])
    parent = validate(value['parent_reference']) if value['parent_reference'] is not None else None
    if parent is not None and parent['id'] != relation['parent_file_id']:
        _invalid()
    if not relation['parent_file_id'] and parent is not None:
        _invalid()
    return dict(relation=relation, parent_reference=parent, state=value['state'])


def _description(state, value, segments=None, supplement=None):
    allowed = EXPORT_STATES + (('proposed', 'ambiguous') if segments is not None or supplement is not None else ())
    if type(state) is not str or state not in allowed:
        _invalid()
    if value is not None:
        value = mapping(value)
    if (state == 'confirmed' and (value is None or value['kind'] == 'custom')
            or state in ('ignored', 'proposed', 'ambiguous') and value is not None
            or state == 'unmatched' and value is not None and value['kind'] != 'custom'):
        _invalid()
    return value


def restore_descriptor(value):
    """One local revision covers metadata and exact-file annotations together."""
    fields = {'reference', 'state', 'mapping', 'segments'}
    if type(value) is not dict or set(value) not in (fields, fields | {'supplement'}):
        _invalid()
    reference = validate(value['reference'])
    from .catalog_segments import _record
    segments = _record(value['segments']) if value['segments'] is not None else None
    supplement = supplement_record(value.get('supplement'))
    result = dict(reference=reference, state=value['state'],
        mapping=_description(value['state'], value['mapping'], segments, supplement), segments=segments)
    if 'supplement' in value:
        result['supplement'] = supplement
    return result


def _entry(raw, schema=SCHEMA):
    fields = {'reference', 'state', 'mapping', 'source_revision'}
    if schema in (SEGMENT_SCHEMA, SUPPLEMENT_SCHEMA):
        fields.add('segments')
    if schema == SUPPLEMENT_SCHEMA:
        fields.add('supplement')
    if (type(raw) is not dict or set(raw) != fields
            or type(raw['source_revision']) is not int or not 1 <= raw['source_revision'] < 2**63):
        _invalid()
    ref = validate(raw['reference'])
    state, value = raw['state'], raw['mapping']
    from .catalog_segments import _record
    segments = _record(raw['segments']) if raw.get('segments') is not None else None
    supplement = supplement_record(raw.get('supplement'))
    if supplement is not None and supplement['parent_reference'] is not None and any(
            supplement['parent_reference'][key] != ref[key] for key in ('provider', 'account_id')):
        _invalid()
    value = _description(state, value, segments, supplement)
    result = dict(reference=ref, state=state, mapping=value, source_revision=raw['source_revision'])
    if schema in (SEGMENT_SCHEMA, SUPPLEMENT_SCHEMA):
        result['segments'] = segments
    if schema == SUPPLEMENT_SCHEMA:
        result['supplement'] = supplement
    return result


def checked(value):
    if (type(value) is not dict or set(value) != {'schema', 'scope', 'entries'}
            or value['schema'] not in SCHEMAS or type(value['scope']) is not dict
            or set(value['scope']) != {'provider', 'account_id'}
            or type(value['entries']) is not list or not 1 <= len(value['entries']) <= MAX_ENTRIES):
        _invalid()
    entries = [_entry(row, value['schema']) for row in value['entries']]
    if len({row['reference']['id'] for row in entries}) != len(entries):
        _invalid()
    scope = value['scope']
    if any((row['reference']['provider'], row['reference']['account_id']) !=
           (scope['provider'], scope['account_id']) for row in entries):
        _invalid()
    return dict(schema=value['schema'], scope=dict(scope), entries=entries)


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
    if any(row.get('provenance') != 'manual' for row in records):
        _invalid()
    schema = (SUPPLEMENT_SCHEMA if any(row.get('supplement') is not None for row in records) else
              SEGMENT_SCHEMA if any(row.get('segments') is not None for row in records) else SCHEMA)
    value = dict(schema=schema, scope={key: expected[key] for key in ('provider', 'account_id')},
        entries=[dict(reference=row['file_ref'], state=row['state'], mapping=row['mapping'],
                      source_revision=row['revision']) for row in records])
    if schema in (SEGMENT_SCHEMA, SUPPLEMENT_SCHEMA):
        for entry, row in zip(value['entries'], records):
            entry['segments'] = segment_record(row.get('segments'))
            if schema == SUPPLEMENT_SCHEMA:
                relation = row.get('supplement')
                entry['supplement'] = (dict(relation={key: val for key, val in relation.items() if key != 'state'},
                    parent_reference=row.get('supplement_parent'), state=relation['state']) if relation else None)
    return loads(dumps(value))  # One whitelist and byte budget at both boundaries.


def lookup_ids(value):
    value = checked(value)
    ids = [row['reference']['id'] for row in value['entries']]
    ids.extend(row['supplement']['relation']['parent_file_id'] for row in value['entries']
               if row.get('supplement') and row['supplement']['relation']['parent_file_id'])
    return list(dict.fromkeys(ids))


def _restore_supplement(value, current):
    """Rebase only the target's review CAS, never the saved file observation."""
    if value is None:
        return None, None
    from .catalog_query import opaque
    value = supplement_record(value)
    relation = value['relation']
    if value['state'] != 'confirmed':
        return None, 'SUPPLEMENT_REQUIRES_REVIEW'
    if relation['parent_file_id']:
        parent = current.get(relation['parent_file_id'])
        ref = value['parent_reference']
        if (parent is None or ref is None or not parent['available'] or parent.get('supplement') or
                parent['file_ref'] != ref or opaque(ref) != relation['parent_evidence']):
            return None, 'SUPPLEMENT_PARENT_CHANGED'
        mapping_value = parent['mapping'] or {}
        key = 'tmdb:%s:%s' % (mapping_value.get('kind'), mapping_value.get('tmdb_id'))
        if (relation['metadata_key'] is not None and (parent['state'] != 'confirmed' or key != relation['metadata_key']) or
                relation['metadata_key'] is None and not (parent['state'] == 'unmatched' and
                    parent['provenance'] == 'manual' and mapping_value.get('kind') == 'custom')):
            return None, 'SUPPLEMENT_PARENT_NOT_READY'
        relation = dict(relation, parent_revision=parent['revision'])
    return dict(value, relation=relation), None


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
            original_segments = segment_record(entry.get('segments'))
            current_segments = segment_record(target.get('segments'))
            supplement, supplement_error = _restore_supplement(entry.get('supplement'), current)
            target_relation = target.get('supplement')
            relation_equal = (target_relation is None and supplement is None or
                supplement is not None and target_relation == dict(supplement['relation'], state='confirmed'))
            metadata_equal = target['state'] == entry['state'] and target['mapping'] == entry['mapping']
            from .catalog_query import opaque
            if current_segments is not None and current_segments != original_segments:
                row.update(status='conflict', reason='TARGET_HAS_SEGMENTS')
            elif target_relation is not None and not relation_equal:
                row.update(status='conflict', reason='TARGET_IS_SUPPLEMENT')
            elif not target.get('available') or not same_file(ref, actual):
                row['reason'] = 'FILE_CHANGED_OR_UNAVAILABLE'
            elif original_segments is not None and opaque(ref) != opaque(actual):
                row['reason'] = 'OBSERVATION_CHANGED'
            elif supplement_error:
                row['reason'] = supplement_error
            elif metadata_equal and current_segments == original_segments and relation_equal:
                row.update(status='unchanged', reason='ALREADY_EQUAL')
            elif target.get('provenance') == 'manual' and not metadata_equal:
                row.update(status='conflict', reason='TARGET_HAS_MANUAL_STATE')
            else:
                action = ('confirm' if entry['mapping'] is not None else
                          'ignore' if entry['state'] == 'ignored' else 'unbind')
                cmd = command(dict(file_id=ref['id'], expected_revision=target['revision'],
                                   action=action, mapping=entry['mapping']))
                if value['schema'] in (SEGMENT_SCHEMA, SUPPLEMENT_SCHEMA):
                    restore = dict(reference=actual, state=entry['state'], mapping=entry['mapping'], segments=original_segments)
                    if value['schema'] == SUPPLEMENT_SCHEMA:
                        restore['supplement'] = supplement
                    cmd = command(dict(file_id=ref['id'], expected_revision=target['revision'],
                        action='restore_description', mapping=restore))
                strong = ref['fingerprint'] is not None and ref['fingerprint'] == actual['fingerprint']
                row.update(status='ready' if strong else 'review_required',
                           reason='MATCHED_CONTENT' if strong else 'CONTENT_EVIDENCE_WEAK', command=cmd)
            row.update(current_revision=target['revision'], before=deepcopy(target['mapping']),
                       after=deepcopy(entry['mapping']))
        result.append(row)
    return dict(items=result)
