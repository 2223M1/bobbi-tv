"""Per-source qualification snapshot from the existing authoritative ledger."""
import hashlib
import json


def qualification_target(target):
    """Target proof shared by token generation and projection invalidation."""
    stable = {key: value for key, value in target.items() if key != 'purpose'}
    selection = target.get('_selection')
    if isinstance(selection, dict):
        stable['_selection'] = {key: value for key, value in selection.items() if key != 'request_id'}
    return stable


def qualification_token(queue, item, source_hash):
    # Do not include global generation, watch progress, recommendation order,
    # leases or favorites. None of those retargets the media file. Include
    # all exact source bindings and the bounded probe evidence instead.
    rows = queue.db.execute('''SELECT b.task,b.media_id,b.version_key,b.evidence,p.payload
        FROM prepared_bindings b JOIN tasks t ON t.id=b.task
        JOIN preparation_targets p ON p.task=b.task AND p.media_id=b.media_id AND p.version_key=b.version_key
        WHERE b.resource=? AND t.account=? AND t.source_hash=? ORDER BY b.task,b.media_id,b.version_key''',
        (item['resource_id'], item['account'], source_hash)).fetchmany(17)
    if not rows or len(rows) > 16:
        raise ValueError('Missing or excessive exact source bindings')
    bindings = []
    for row in rows:
        evidence, target = json.loads(row['evidence']), json.loads(row['payload'])
        if not isinstance(evidence, dict) or not isinstance(target, dict):
            raise ValueError('Binding and target must be objects')
        selection = target.get('_selection')
        selected = selection.get('file') if isinstance(selection, dict) else None
        if not isinstance(selected, dict):
            raise ValueError('Verified source file selection required')
        if (row['media_id'] != item['media_id'] or row['version_key'] != item['version_key']
                or evidence.get('source_info_hash') != source_hash
                or evidence.get('cloud_file_id') != item['file_id']
                or evidence.get('cloud_path') != item['cloud_path'] or evidence.get('bytes') != item['bytes']
                or type(evidence.get('torrent_file_id')) is not int or type(selected.get('id')) is not int
                or selected['id'] < 1 or type(selected.get('length')) is not int
                or evidence.get('torrent_file_id') != selected.get('id')
                or not selected.get('path') or evidence.get('torrent_path') != selected['path']
                or evidence.get('bytes') != selected.get('length')):
            raise ValueError('Exact source binding no longer matches the qualified file')
        # Reopening the same release updates intake/request provenance and
        # current/next priority, not the qualified video. Hashing the complete
        # raw target JSON made a second ordinary preparation invalidate the
        # published token without any file change or generation publication.
        # Preserve ALL other evidence, including unknown future proof fields.
        stable_target = qualification_target(target)
        bindings.append(dict(task=row['task'], media_id=row['media_id'],
                             version_key=row['version_key'], evidence=evidence,
                             target=stable_target))
    fields = ('resource_id', 'provider', 'account', 'file_id', 'cloud_path', 'bytes',
              'kind', 'media_id', 'version_key', 'state', 'suppressed', 'identity_verified', 'qualification')
    value = {'schema': 2, 'resource': {key: item.get(key) for key in fields},
             'source_hash': source_hash, 'bindings': bindings}
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()
