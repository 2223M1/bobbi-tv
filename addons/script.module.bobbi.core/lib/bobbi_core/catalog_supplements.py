"""Supplement relationships inside MediaIndex's review transaction and revision."""
import json
import re

from .catalog_query import opaque
from .catalog_review import text

KINDS = ('bonus', 'interview', 'deleted', 'trailer', 'other')


def descriptor(value):
    fields = {'metadata_key', 'parent_file_id', 'kind', 'title'}
    if (type(value) is not dict or set(value) not in (fields, fields | {'parent_revision', 'parent_evidence'}) or
            value['metadata_key'] is not None and (type(value['metadata_key']) is not str or
                not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', value['metadata_key'])) or
            value['kind'] not in KINDS or value['parent_file_id'] is not None and
            (type(value['parent_file_id']) is not str or not re.fullmatch('[0-9a-f]{64}', value['parent_file_id']))):
        raise ValueError('CATALOG_SUPPLEMENT_INVALID')
    revision, evidence = value.get('parent_revision'), value.get('parent_evidence')
    if value['parent_file_id']:
        if (type(revision) is not int or revision < 0 or type(evidence) is not str or
                not re.fullmatch('[0-9a-f]{64}', evidence)):
            raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
    elif revision is not None or evidence is not None or value['metadata_key'] is None:
        raise ValueError('CATALOG_SUPPLEMENT_INVALID')
    return dict(value, title=text(value['title'], 160), parent_revision=revision, parent_evidence=evidence)


def stored(index, file_id):
    row = index.db.execute('SELECT detail FROM file_supplements WHERE file=?', (file_id,)).fetchone()
    return json.loads(row[0]) if row else None


def target(index, expected, cmd, item):
    current = stored(index, cmd['file_id'])
    if cmd['action'] == 'detach_supplement':
        return None
    if cmd['action'] == 'undo':
        row = index.db.execute('SELECT before_relation FROM supplement_changes WHERE file=? AND revision=?',
            (cmd['file_id'], item['revision'])).fetchone()
        return json.loads(row[0]) if row and row[0] else None
    if cmd['action'] != 'supplement':
        return current
    value = descriptor(cmd['mapping'])
    where, args = index.query_reader._partition(expected)
    identity = ' AND p.id=?' if value['metadata_key'] is None else " AND p.review_state='confirmed' AND p.metadata_key=?"
    parent = index.db.execute('SELECT p.* FROM catalog_rows p WHERE ' + where +
        identity + ' AND p.id!=? ' +
        'AND NOT EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id)' +
        (' AND p.id=?' if value['parent_file_id'] else '') + ' LIMIT 1',
        args + [value['metadata_key'] or value['parent_file_id'], cmd['file_id']] +
        ([value['parent_file_id']] if value['parent_file_id'] else [])).fetchone()
    if parent is None:
        raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
    # A primary file already owning extras cannot itself become an extra. This
    # keeps one-level ownership and prevents circular/hidden parent graphs.
    if index.db.execute('SELECT 1 FROM file_supplements WHERE parent_file=? LIMIT 1', (cmd['file_id'],)).fetchone():
        raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
    result = dict(value, parent_work_id=parent['work_id'])
    if value['parent_file_id']:
        parent_item = index._item(value['parent_file_id'], expected)
        if (value['metadata_key'] is None and not custom_parent(parent_item) or
                parent_item['revision'] != value['parent_revision'] or
                opaque(parent_item['file_ref']) != value['parent_evidence']):
            raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
    return result


def custom_parent(item):
    return (item['state'] == 'unmatched' and item['provenance'] == 'manual' and
            (item.get('mapping') or {}).get('kind') == 'custom')


def summary(index, expected, relation):
    if relation is None:
        return None
    value = {key: relation[key] for key in ('metadata_key', 'parent_file_id', 'kind', 'title')}
    state = 'confirmed'
    if relation['parent_file_id']:
        try:
            parent_item = index._item(relation['parent_file_id'], expected, include_supplement=False)
            mapping = parent_item.get('mapping') or {}
            actual_key = 'tmdb:%s:%s' % (mapping.get('kind'), mapping.get('tmdb_id'))
            identity_matches = (custom_parent(parent_item) if relation['metadata_key'] is None else
                parent_item['state'] == 'confirmed' and actual_key == relation['metadata_key'])
            if (not identity_matches or
                    parent_item['revision'] != relation['parent_revision'] or
                    opaque(parent_item['file_ref']) != relation['parent_evidence']):
                state = 'verification_required'
        except ValueError:
            state = 'verification_required'
    else:
        where, args = index.query_reader._partition(expected)
        if not index.db.execute('SELECT 1 FROM catalog_rows p WHERE ' + where +
                " AND p.work_id=? AND p.review_state='confirmed' AND NOT EXISTS("
                'SELECT 1 FROM file_supplements s WHERE s.file=p.id) LIMIT 1', args + [relation['parent_work_id']]).fetchone():
            state = 'verification_required'
    return dict(value, state=state)


def write(index, file_id, revision, before, after):
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':')) if value is not None else None
    index.db.execute('INSERT INTO supplement_changes VALUES(?,?,?,?)',
        (file_id, revision, encode(before), encode(after)))
    index.db.execute('DELETE FROM supplement_changes WHERE file=? AND revision<?', (file_id, revision - 31))
    if after is None:
        index.db.execute('DELETE FROM file_supplements WHERE file=?', (file_id,))
    else:
        index.db.execute('INSERT OR REPLACE INTO file_supplements VALUES(?,?,?,?)',
            (file_id, after['parent_work_id'], after['parent_file_id'], encode(after)))
