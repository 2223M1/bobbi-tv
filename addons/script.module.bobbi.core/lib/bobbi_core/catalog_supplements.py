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


def _require_single_level(index, file_id, relation):
    # Restoring historical metadata must preserve the same ownership invariant
    # as a new attachment. A detach can let either file acquire new relations
    # before undo; restoring its old edge must not hide a parent or form a cycle.
    parent = relation['parent_file_id']
    if parent == file_id or index.db.execute(
            'SELECT 1 FROM file_supplements WHERE parent_file=? OR file=? LIMIT 1',
            (file_id, parent)).fetchone():
        raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')


def target(index, expected, cmd, item):
    current = stored(index, cmd['file_id'])
    if cmd['action'] == 'restore_description' and 'supplement' in cmd['mapping']:
        value = cmd['mapping']['supplement']
        if value is None:
            if current is not None:
                raise ValueError('CATALOG_SUPPLEMENT_CONFLICT')
            return None
        if value['state'] != 'confirmed':
            raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
        parent_id = value['relation']['parent_file_id']
        if parent_id:
            parent = index._item(parent_id, expected)
            # A completed scan can revoke the parent membership without
            # changing its saved reference or review revision. Revalidate the
            # same availability condition as import preview, inside apply.
            if not parent['available'] or parent['file_ref'] != value['parent_reference']:
                raise ValueError('CATALOG_SUPPLEMENT_PARENT_CHANGED')
        cmd = dict(cmd, action='supplement', mapping=value['relation'])
    if cmd['action'] == 'detach_supplement':
        return None
    if cmd['action'] == 'undo':
        row = index.db.execute('SELECT before_relation FROM supplement_changes WHERE file=? AND revision=?',
            (cmd['file_id'], item['revision'])).fetchone()
        restored = json.loads(row[0]) if row and row[0] else None
        if restored:
            _require_single_level(index, cmd['file_id'], restored)
        return restored
    if cmd['action'] != 'supplement':
        return current
    value = descriptor(cmd['mapping'])
    _require_single_level(index, cmd['file_id'], value)
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
    # Editors must retain the saved parent CAS evidence when changing only an
    # extra's label. A later parent observation is not implicit reconfirmation.
    value.update(parent_revision=relation.get('parent_revision'),
                 parent_evidence=relation.get('parent_evidence'))
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
