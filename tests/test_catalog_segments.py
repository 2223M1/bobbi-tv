"""Exact-file manual segments through existing SQLite review/CAS/undo/receipt."""
from copy import deepcopy
import json
import sqlite3
from uuid import uuid4

import pytest

from bobbi_core import catalog_segments, catalog_transfer
from bobbi_core.catalog_query import REPLY_BYTES, wire
from bobbi_core.media_library_index import MediaIndex
from bobbi_platform.runtime import Runtime, bind_call
from test_media_library_index import index, scope, ref, insert, command
from test_local_catalog_source import local, scan, files


def segment_command(index, file, items=None, expected=None, duration=600000):
    item = index.item(expected or scope(), file['id'])
    return dict(file_id=file['id'], expected_revision=item['revision'], action='segments',
        mapping=dict(observation_key=item['file']['observation_key'], duration_ms=duration,
            items=items if items is not None else [dict(kind='intro', start_ms=0, end_ms=30000)]))


def apply(index, command, expected=None):
    result = index.apply(expected or scope(), uuid4().hex, [command])['items'][0]
    assert result['status'] == 'applied'
    return result


def test_preview_apply_receipt_clear_undo_and_reverse_undo_share_one_revision(index):
    file = ref();insert(index, [file])
    initial = index.item(scope(), file['id'])
    index.now = lambda: 1234
    cmd = segment_command(index, file, [dict(kind=kind, start_ms=n * 100000, end_ms=n * 100000 + 10000)
                                      for n, kind in enumerate(catalog_segments.KINDS)])
    before_changes = index.db.total_changes
    preview = index.preview(scope(), [cmd])['items'][0]
    assert index.db.total_changes == before_changes
    assert preview['before_segments'] is None and preview['after_segments']['source'] == 'manual'
    assert preview['after_segments']['duration_source'] == 'manual'
    assert preview['after_segments']['observed_at'] == 1234 and not preview['after_segments']['auto_allowed']
    assert index.item(scope(), file['id']) == initial
    request = uuid4().hex
    reply = index.apply(scope(), request, [cmd])
    assert reply == dict(items=[dict(status='applied', revision=1)])
    assert index.apply(scope(), request, [cmd]) == reply
    assert index.receipt(scope(), request)['items'] == [dict(index=0, status='applied', revision=1)]
    saved = index.item(scope(), file['id'])
    assert saved['segments'] == preview['after_segments']
    assert saved['mapping'] == initial['mapping'] and saved['state'] == initial['state']
    assert saved['file'] == initial['file']
    assert index.apply(scope(), uuid4().hex, [cmd])['items'][0]['status'] == 'conflict'
    clear = segment_command(index, file, [], duration=None)
    apply(index, clear)
    assert 'segments' not in index.item(scope(), file['id'])
    undo = command(file, revision=2, action='undo')
    assert index.preview(scope(), [undo])['items'][0]['after_segments'] == saved['segments']
    apply(index, undo)
    assert index.item(scope(), file['id'])['segments'] == saved['segments']
    apply(index, command(file, revision=3, action='undo'))
    assert 'segments' not in index.item(scope(), file['id'])


@pytest.mark.parametrize('action', ['confirm', 'unbind', 'ignore'])
def test_existing_metadata_writes_and_their_undo_preserve_segments(index, action):
    file = ref();insert(index, [file])
    apply(index, segment_command(index, file))
    saved = index.item(scope(), file['id'])['segments']
    apply(index, command(file, revision=1, action=action))
    assert index.item(scope(), file['id'])['segments'] == saved
    apply(index, command(file, revision=2, action='undo'))
    assert index.item(scope(), file['id'])['segments'] == saved


def test_supplement_and_segment_edits_preserve_each_others_domain_and_undo(index):
    from test_catalog_supplements import pair, cmd as supplement_command, relation
    main, extra = pair(index)
    apply(index, segment_command(index, extra))
    before = index.item(scope(), extra['id'])['segments']
    apply(index, supplement_command(index, extra, relation(main['id'])))
    attached = index.item(scope(), extra['id'])
    assert attached['segments'] == before and attached['supplement']['state'] == 'confirmed'
    apply(index, segment_command(index, extra, [], duration=None))
    cleared = index.item(scope(), extra['id'])
    assert 'segments' not in cleared and cleared['supplement'] == attached['supplement']
    apply(index, command(extra, revision=cleared['revision'], action='undo'))
    restored = index.item(scope(), extra['id'])
    assert restored['segments'] == before and restored['supplement'] == attached['supplement']
    apply(index, supplement_command(index, extra, action='detach_supplement'))
    assert index.item(scope(), extra['id'])['segments'] == before


@pytest.mark.parametrize('change', ['size', 'name', 'fingerprint'])
def test_replacement_invalidates_old_evidence_and_undo_never_rebinds_it(index, change):
    file = ref();insert(index, [file])
    index.now = lambda: 1234
    apply(index, segment_command(index, file))
    original = index.item(scope(), file['id'])['segments']
    stale = segment_command(index, file)
    newer = dict(file, **({'size': file['size'] + 1} if change == 'size' else
        {'name': 'Renamed.mkv'} if change == 'name' else
        {'fingerprint': {'algorithm': 'sha1', 'value': 'b' * 40}}))
    # FileRef's provider-specific fingerprint is validated, so use an actual
    # strong-reference provider for that branch rather than forging evidence.
    if change == 'fingerprint':
        from bobbi_core.file_ref import from_selected
        expected = scope(provider='aliyun')
        file = from_selected(expected, dict(file_id='drive:f', directory=False,
            name='Film.mkv', size=1024, content_hash='old'), 'drive:root')
        insert(index, [file], expected=expected, source='b' * 32)
        apply(index, segment_command(index, file, expected=expected), expected)
        original = index.item(expected, file['id'])['segments']
        stale = segment_command(index, file, expected=expected)
        newer = from_selected(expected, dict(file_id='drive:f', directory=False,
            name='Film.mkv', size=1024, content_hash='new'), 'drive:root')
    else:
        expected = scope()
    insert(index, [newer], expected=expected)
    before = index.item(expected, file['id'])
    assert before['segments']['state'] == 'verification_required'
    assert before['segments']['observation_key'] == original['observation_key']
    assert index.preview(expected, [stale])['items'][0]['status'] == 'failed'
    assert index.apply(expected, uuid4().hex, [stale])['items'][0]['status'] == 'failed'
    assert index.item(expected, file['id']) == before
    apply(index, segment_command(index, file, [], expected, duration=None), expected)
    apply(index, command(file, revision=2, action='undo'), expected)
    restored = index.item(expected, file['id'])['segments']
    assert restored == dict(original, state='verification_required')


@pytest.mark.parametrize('mutation', [
    lambda value: value.update(duration_ms=True),
    lambda value: value.update(duration_ms=None),
    lambda value: value.update(duration_ms=600000.0),
    lambda value: value.update(duration_ms=864000001),
    lambda value: value.update(source='detected'),
    lambda value: value.update(observed_at=1),
    lambda value: value.update(observation_key='a' * 63),
    lambda value: value['items'][0].update(start_ms=-1),
    lambda value: value['items'][0].update(end_ms=True),
    lambda value: value['items'][0].update(end_ms=float('nan')),
    lambda value: value['items'][0].update(end_ms=0),
    lambda value: value['items'][0].update(end_ms=600001),
    lambda value: value['items'][0].update(kind='auto_next'),
    lambda value: value['items'][0].update(skip=True),
    lambda value: value['items'].append(dict(value['items'][0])),
])
def test_invalid_or_forged_segment_evidence_never_writes(index, mutation):
    file = ref();insert(index, [file])
    cmd = segment_command(index, file)
    mutation(cmd['mapping'])
    before = index.item(scope(), file['id'])
    assert index.preview(scope(), [cmd])['items'][0]['status'] == 'failed'
    # Non-finite values are rejected by the existing strict wire encoder.
    try:
        result = index.apply(scope(), uuid4().hex, [cmd])
        assert result['items'][0]['status'] == 'failed'
    except ValueError:
        pass
    assert index.item(scope(), file['id']) == before
    assert index.db.execute('SELECT COUNT(*) FROM file_segments').fetchone()[0] == 0


def test_outro_overlapping_credits_scene_is_conflict_not_skip_policy(index):
    file = ref();insert(index, [file])
    cmd = segment_command(index, file, [dict(kind='outro', start_ms=500000, end_ms=600000),
        dict(kind='credits_scene', start_ms=550000, end_ms=580000)])
    assert index.preview(scope(), [cmd])['items'][0]['status'] == 'failed'
    assert index.apply(scope(), uuid4().hex, [cmd])['items'][0]['status'] == 'failed'
    cmd['mapping']['items'][0]['end_ms'] = 550000
    apply(index, cmd)
    result = index.item(scope(), file['id'])['segments']
    assert [row['kind'] for row in result['items']] == ['outro', 'credits_scene']
    assert result['auto_allowed'] is False


def test_failed_segment_write_rolls_back_review_revision_and_retries_same_request(index):
    file = ref();insert(index, [file])
    cmd = segment_command(index, file)
    request = uuid4().hex
    index.db.execute("CREATE TRIGGER fail_segment BEFORE INSERT ON file_segments BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
    with pytest.raises(sqlite3.IntegrityError):
        index.apply(scope(), request, [cmd])
    assert index.item(scope(), file['id'])['revision'] == 0
    assert not index.receipt(scope(), request)['items']
    assert index.db.execute('SELECT COUNT(*) FROM review_changes').fetchone()[0] == 0
    index.db.execute('DROP TRIGGER fail_segment')
    assert index.apply(scope(), request, [cmd])['items'][0]['status'] == 'applied'
    assert index.item(scope(), file['id'])['segments']['state'] == 'matched'


def test_segments_do_not_cross_account_or_file_and_requests_remain_idempotent(index):
    file, other = ref(), ref(2);insert(index, [file, other])
    cmd = segment_command(index, file)
    request = uuid4().hex
    apply(index, cmd)
    assert 'segments' not in index.item(scope(), other['id'])
    assert index.apply(scope('b'), request, [cmd])['items'][0]['status'] == 'failed'
    assert index.receipt(scope(), request)['items'] == []
    assert index.apply(scope(), request, [cmd])['items'][0]['reason'] == 'REQUEST_ID_REUSED'


def test_local_exact_observation_and_authority_changes_invalidate_without_new_id(local):
    assert scan(local)['state'] == 'completed'
    service, source, media, _ = local
    selected = next(row['entity_id'] for row in files(local) if row['display_title'] == 'Movie.mkv')
    expected = service.dispatch('catalog_local_scope', dict(source_id=source.id))
    cmd = segment_command(service.index, dict(id=selected), expected=expected)
    assert service.dispatch('catalog_local_preview', dict(source_id=source.id, commands=[cmd]))['items'][0]['status'] == 'ready'
    request = uuid4().hex
    assert service.dispatch('catalog_local_apply', dict(source_id=source.id, request_id=request,
        commands=[cmd]))['items'][0]['status'] == 'applied'
    original = service.index.item(expected, selected)['segments']
    for authority in (dict(expected, generation='b' * 64),
                      dict(expected, root_signature=dict(device=1, inode=1))):
        assert service.index.item(authority, selected)['segments']['state'] == 'verification_required'
        stale = segment_command(service.index, dict(id=selected), expected=authority)
        assert service.index.apply(authority, uuid4().hex, [stale])['items'][0]['status'] == 'failed'
    (media / 'Movie.mkv').write_bytes(b'replacement with different length')
    assert scan(local)['state'] == 'completed'
    updated = service.index.item(expected, selected)
    assert updated['file']['id'] == selected
    assert updated['segments'] == dict(original, state='verification_required')
    assert service.dispatch('catalog_local_receipt', dict(source_id=source.id,
        request_id=request))['items'][0]['status'] == 'applied'


def test_schema3_migration_backup_and_restart_preserve_data(tmp_path):
    path = tmp_path / 'catalog.sqlite3'
    original = MediaIndex(path)
    file = ref();insert(original, [file]);apply(original, command(file, title='Preserved'))
    original.db.execute('DROP TABLE file_segments')
    original.db.execute('DROP TABLE segment_changes')
    original.db.execute('PRAGMA user_version=3')
    original.db.commit();original.close()
    upgraded = MediaIndex(path)
    try:
        assert upgraded.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert upgraded.item(scope(), file['id'])['mapping']['title'] == 'Preserved'
        with sqlite3.connect(upgraded.migration_backup_path) as backup:
            assert backup.execute('PRAGMA user_version').fetchone()[0] == 3
            assert backup.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            assert not backup.execute("SELECT 1 FROM sqlite_master WHERE name='file_segments'").fetchone()
        apply(upgraded, segment_command(upgraded, file))
        saved = upgraded.item(scope(), file['id'])
    finally:
        upgraded.close()
    restarted = MediaIndex(path)
    try:
        assert restarted.item(scope(), file['id']) == saved
        assert restarted.migration_backup_path is None
    finally:
        restarted.close()


def test_schema3_interrupted_migration_rolls_back_and_preserves_backup(tmp_path, monkeypatch):
    from bobbi_core import catalog_query
    path = tmp_path / 'catalog.sqlite3'
    original = MediaIndex(path)
    file = ref();insert(original, [file]);apply(original, command(file))
    original.db.execute('DROP TABLE file_segments')
    original.db.execute('DROP TABLE segment_changes')
    original.db.execute('PRAGMA user_version=3')
    original.db.execute('UPDATE catalog_meta SET schema=5')
    original.db.commit();original.close()
    with monkeypatch.context() as patch:
        patch.setattr(catalog_query, 'project', lambda *args: (_ for _ in ()).throw(OSError('migration stopped')))
        with pytest.raises(OSError, match='migration stopped'):
            MediaIndex(path)
    with sqlite3.connect(path) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0] == 3
        assert old.execute('SELECT revision FROM reviews').fetchone()[0] == 1
        assert not old.execute("SELECT 1 FROM sqlite_master WHERE name IN ('file_segments','segment_changes')").fetchall()
    backup = path.with_name(path.name + '.schema3.bak')
    before = backup.read_bytes()
    repaired = MediaIndex(path)
    try:
        assert repaired.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert backup.read_bytes() == before and repaired.migration_backup_path != backup
        assert repaired.item(scope(), file['id'])['mapping']['title'] == 'Custom'
    finally:
        repaired.close()


def test_segment_change_history_uses_existing_bounded_32_revision_window(index):
    file = ref();insert(index, [file])
    for number in range(35):
        apply(index, segment_command(index, file, [dict(kind='intro', start_ms=number, end_ms=30000)]))
    assert index.db.execute('SELECT COUNT(*) FROM segment_changes').fetchone()[0] == 32
    assert index.db.execute('SELECT COUNT(*) FROM review_changes').fetchone()[0] == 32
    assert index.db.execute('SELECT COUNT(*) FROM file_segments').fetchone()[0] == 1


def test_segment_pages_and_preview_remain_bounded(index):
    values = [ref(number, name='长文件名' * 100 + str(number)) for number in range(5)]
    insert(index, values)
    cmds = [segment_command(index, file, [dict(kind=kind, start_ms=n * 100000, end_ms=n * 100000 + 90000)
        for n, kind in enumerate(catalog_segments.KINDS)]) for file in values]
    assert len(wire(index.preview(scope(), cmds))) <= REPLY_BYTES
    index.apply(scope(), uuid4().hex, cmds)
    assert len(wire(index.items(scope()))) <= REPLY_BYTES
    assert all('segments' in row for row in index.items(scope())['items'])


def test_v2_export_and_v1_import_conflict_preserve_segments(index, tmp_path):
    file, plain = ref(), ref(2);insert(index, [file, plain])
    apply(index, command(file));apply(index, command(plain))
    before_records = index.manual_records(scope(), file_ids=[file['id']])['items']
    payload = catalog_transfer.export_records(scope(), before_records)
    apply(index, segment_command(index, file))
    before = index.item(scope(), file['id'])
    records = index.manual_records(scope(), file_ids=[file['id']])['items']
    exported = catalog_transfer.export_records(scope(), records)
    assert exported['schema'] == catalog_transfer.SEGMENT_SCHEMA
    assert exported['entries'][0]['segments']['observation_key'] == before['segments']['observation_key']
    assert len(index.manual_records(scope())['items']) == 2
    # Ordinary descriptions stay readable by the legacy v1 consumer.
    assert catalog_transfer.export_records(scope(), index.manual_records(scope(), file_ids=[plain['id']])['items'])
    result = catalog_transfer.preview(payload, scope(), records)['items'][0]
    assert result['status'] == 'conflict' and result['reason'] == 'TARGET_HAS_SEGMENTS' and result['command'] is None
    assert index.item(scope(), file['id']) == before
    altered = deepcopy(payload)
    altered['entries'][0]['segments'] = records[0]['segments']
    with pytest.raises(ValueError, match='^CATALOG_TRANSFER_INVALID$'):
        catalog_transfer.loads(json.dumps(altered))
    other = scope('b')
    second = ref(expected=other);insert(index, [second], expected=other, source='b' * 32)
    apply(index, command(second), other)
    assert len(index.manual_records(other)['items']) == 1
    runtime = Runtime(lambda action, body: index.manual_records(scope()), tmp_path / 'runtime.json')
    runtime.start()
    try:
        assert len(bind_call(runtime.path)('catalog_manual_records', {})['items']) == 2
    finally:
        runtime.close()
