"""Supplement ownership is review metadata, never a main-media or resume identity."""
import json
import sqlite3
from uuid import uuid4

import pytest

from test_media_library_index import index, scope, ref, insert, command
from test_catalog_file_projection_contract import describe
from bobbi_core.catalog_review import command as checked_command
from bobbi_core.catalog_query import wire
from bobbi_core.media_library_index import MediaIndex


def relation(parent_file_id=None, metadata_key='tmdb:movie:10', **changes):
    return dict(dict(metadata_key=metadata_key, parent_file_id=parent_file_id, kind='bonus', title='制作花絮'), **changes)


def cmd(index, file, value=None, action='supplement', expected=None):
    expected = expected or scope()
    if action == 'supplement' and value and value.get('parent_file_id'):
        try:
            parent = index.item(expected, value['parent_file_id'])
            value = dict(value, parent_revision=parent['revision'], parent_evidence=parent['file']['observation_key'])
        except ValueError:
            value = dict(value, parent_revision=0, parent_evidence='a'*64)
    return dict(file_id=file['id'], expected_revision=index.item(expected, file['id'])['revision'],
                action=action, mapping=value)


def apply(index, command, expected=None):
    result = index.apply(expected or scope(), uuid4().hex, [command])['items'][0]
    assert result['status'] == 'applied'
    return result


def pair(index):
    main, extra = ref(1, name='Main film.mkv'), ref(2, name='The Interview.mkv')
    insert(index, [main, extra])
    describe(index, main, '导演剪辑')
    return main, extra


def test_attach_preview_apply_receipt_and_undo_preserve_original_mapping(index):
    main, extra = pair(index)
    describe(index, extra, '原备注', title='原人工名称', tmdb=11)
    original = index.item(scope(), extra['id'])['mapping']
    command = cmd(index, extra, relation(main['id']))
    before = index.preview(scope(), [command])['items'][0]
    assert before['status'] == 'ready' and before['before'] == before['after'] == original
    assert before['after_supplement']['title'] == '制作花絮'
    request = uuid4().hex
    receipt = index.apply(scope(), request, [command])
    assert receipt['items'][0]['status'] == 'applied'
    assert index.apply(scope(), request, [command]) == receipt
    record = index.item(scope(), extra['id'])
    assert record['mapping'] == original and record['supplement']['state'] == 'confirmed'
    apply(index, cmd(index, extra, action='undo'))
    restored = index.item(scope(), extra['id'])
    assert restored['mapping'] == original and 'supplement' not in restored


def test_default_versions_and_holdings_exclude_supplements_but_original_file_is_playable(index):
    main, extra = pair(index)
    describe(index, extra, '另一个原始备注')
    apply(index, cmd(index, extra, relation()))
    work = index.query(scope())['items'][0]
    assert work['variant_count'] == 1
    assert index.holdings(scope(), ['tmdb:movie:10'])['items'][0]['file_count'] == 1
    files = index.query(scope(), query=dict(view='files', parent_entity_id=work['entity_id']))['items']
    assert [row['entity_id'] for row in files] == [main['id']]
    extras = index.query(scope(), query=dict(view='supplements', parent_entity_id=work['entity_id']))['items']
    assert [row['entity_id'] for row in extras] == [extra['id']]
    assert extras[0]['supplement']['kind'] == 'bonus'
    assert index.trusted_file(scope(), extra['id']) == extra
    assert index.query(scope(), query=dict(view='files', review_state='confirmed'))['items']


def test_shared_and_version_specific_extras_are_distinct(index):
    a, extra = pair(index)
    b, shared = ref(3), ref(4)
    insert(index, [a, extra, b, shared])
    describe(index, b, '院线版')
    apply(index, cmd(index, extra, relation(a['id'])))
    apply(index, cmd(index, shared, relation(title='全作品访谈', kind='interview')))
    a_rows = index.query(scope(), query=dict(view='supplements', parent_entity_id=a['id']))['items']
    b_rows = index.query(scope(), query=dict(view='supplements', parent_entity_id=b['id']))['items']
    assert {row['entity_id'] for row in a_rows} == {extra['id'], shared['id']}
    assert {row['entity_id'] for row in b_rows} == {shared['id']}


@pytest.mark.parametrize('change', ['mapping', 'version', 'size'])
def test_changed_exact_parent_requires_relationship_recheck(index, change):
    main, extra = pair(index)
    apply(index, cmd(index, extra, relation(main['id'])))
    if change == 'size':
        insert(index, [dict(main, size=main['size'] + 1), extra])
    else:
        describe(index, main, '修改备注', tmdb=20 if change == 'mapping' else 10)
    assert index.item(scope(), extra['id'])['supplement']['state'] == 'verification_required'
    assert index.item(scope(), extra['id'])['file']['id'] == extra['id']


def test_detach_and_undo_restore_same_relation_not_other_file(index):
    main, extra = pair(index)
    apply(index, cmd(index, extra, relation(main['id'])))
    apply(index, cmd(index, extra, action='detach_supplement'))
    assert 'supplement' not in index.item(scope(), extra['id'])
    apply(index, cmd(index, extra, action='undo'))
    assert index.item(scope(), extra['id'])['supplement']['parent_file_id'] == main['id']


def test_descriptive_export_reports_extras_excluded_and_lookup_marks_import_target(index):
    main, extra = pair(index)
    describe(index, extra, '正片旧备注')
    apply(index, cmd(index, extra, relation(main['id'])))
    export = index.manual_records(scope())
    assert export['excluded_supplements'] == 1
    assert [row['file_ref']['id'] for row in export['items']] == [main['id']]
    target = index.manual_records(scope(), file_ids=[extra['id']])['items'][0]
    assert target['supplement']['kind'] == 'bonus' and target['mapping']['version'] == '正片旧备注'


@pytest.mark.parametrize('value', [relation('a'*64), relation(metadata_key='tmdb:tv:10'), relation(metadata_key='tmdb:movie:20')])
def test_missing_or_different_parent_cannot_be_confirmed(index, value):
    _, extra = pair(index)
    command = cmd(index, extra, value)
    assert index.preview(scope(), [command])['items'][0]['status'] == 'failed'
    assert index.apply(scope(), uuid4().hex, [command])['items'][0]['status'] == 'failed'
    assert 'supplement' not in index.item(scope(), extra['id'])


def test_other_account_and_self_parent_rejected(index):
    main, extra = pair(index)
    assert index.preview(scope(), [cmd(index, main, relation(main['id']))])['items'][0]['status'] == 'failed'
    command = cmd(index, extra, relation(main['id']))
    assert index.preview(scope('b'), [command])['items'][0]['status'] == 'failed'


def test_manually_named_parent_without_tmdb_uses_exact_file_not_invented_group(index):
    main, extra = ref(1), ref(2)
    insert(index, [main, extra])
    apply(index, command(main, title='家庭影像'))
    apply(index, cmd(index, extra, relation(main['id'], metadata_key=None)))
    attached = index.item(scope(), extra['id'])['supplement']
    assert attached['state'] == 'confirmed' and attached['metadata_key'] is None
    assert attached['parent_file_id'] == main['id']
    works = index.query(scope())['items']
    assert len(works) == 1 and works[0]['entity_id'] == main['id']
    assert works[0]['media_kind'] == 'unknown' and works[0]['metadata_key'] is None
    assert index.trusted_file(scope(), main['id']) == main
    assert index.query(scope(), query=dict(view='supplements', parent_entity_id=main['id']))['items'][0]['entity_id'] == extra['id']
    apply(index, command(main, revision=1, title='新的自建名称'))
    assert index.item(scope(), extra['id'])['supplement']['state'] == 'verification_required'


def test_no_tmdb_parent_must_already_be_explicitly_named(index):
    main, extra = ref(1), ref(2)
    insert(index, [main, extra])
    assert index.preview(scope(), [cmd(index, extra, relation(main['id'], metadata_key=None))])['items'][0]['status'] == 'failed'
    describe(index, main, '已有公开作品')
    assert index.preview(scope(), [cmd(index, extra, relation(main['id'], metadata_key=None))])['items'][0]['status'] == 'failed'
    with pytest.raises(ValueError):
        checked_command(cmd(index, extra, relation(metadata_key=None)))


@pytest.mark.parametrize('change', ['mapping', 'replacement'])
def test_parent_change_after_preview_cannot_silently_bind_new_parent(index, change):
    main, extra = pair(index)
    command = cmd(index, extra, relation(main['id']))
    assert index.preview(scope(), [command])['items'][0]['status'] == 'ready'
    if change == 'mapping':
        describe(index, main, '新版本备注')
    else:
        insert(index, [dict(main, size=main['size'] + 1), extra])
    assert index.apply(scope(), uuid4().hex, [command])['items'][0]['status'] == 'failed'
    assert 'supplement' not in index.item(scope(), extra['id'])


def test_no_filename_auto_classification_and_s00_remains_main(index):
    files = [ref(1, name='Extras.mkv'), ref(2, name='The Interview.mkv'), ref(3, name='Show.S00E01.mkv')]
    insert(index, files)
    for file in files:
        describe(index, file, None, kind='tv' if file == files[-1] else 'movie')
    assert index.db.execute('SELECT COUNT(*) FROM file_supplements').fetchone()[0] == 0
    assert sum(row['variant_count'] for row in index.query(scope())['items']) == 3


@pytest.mark.parametrize('bad', [dict(kind='movie'), dict(title='x'*161), dict(title='http://example.test'),
    dict(parent_file_id='file:///bad'), dict(stream_index=2)])
def test_extra_descriptor_rejects_invalid_or_playback_fields(bad):
    with pytest.raises(ValueError):
        checked_command(dict(file_id='a'*64, expected_revision=0, action='supplement', mapping=relation(**bad)))


def test_schema2_upgrade_preserves_authority_and_creates_real_recovery_copy(tmp_path):
    path = tmp_path/'old.sqlite3'
    original = MediaIndex(path)
    main, extra = pair(original)
    old_mapping = original.item(scope(), main['id'])['mapping']
    original.db.execute('DROP TABLE supplement_changes')
    original.db.execute('DROP TABLE file_supplements')
    original.db.execute('PRAGMA user_version=2')
    original.db.commit()
    original.close()
    upgraded = MediaIndex(path)
    assert upgraded.db.execute('PRAGMA user_version').fetchone()[0] == 3
    assert upgraded.item(scope(), main['id'])['mapping'] == old_mapping
    backup = sqlite3.connect(str(path) + '.schema2.bak')
    assert backup.execute('PRAGMA user_version').fetchone()[0] == 2
    assert backup.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    assert backup.execute('SELECT COUNT(*) FROM objects').fetchone()[0] == 2
    backup.close()
    apply(upgraded, cmd(upgraded, extra, relation(main['id'])))
    upgraded.close()
    restarted = MediaIndex(path)
    assert restarted.item(scope(), extra['id'])['supplement']['state'] == 'confirmed'
    restarted.close()


def test_failed_migration_keeps_schema2_and_no_partial_supplement_tables(tmp_path, monkeypatch):
    from bobbi_core import catalog_query
    path = tmp_path/'interrupted.sqlite3'
    old = MediaIndex(path)
    pair(old)
    old.db.execute('DROP TABLE supplement_changes')
    old.db.execute('DROP TABLE file_supplements')
    old.db.execute('PRAGMA user_version=2')
    old.db.execute('UPDATE catalog_meta SET schema=5')
    old.db.commit()
    old.close()
    with monkeypatch.context() as patch:
        patch.setattr(catalog_query, 'project', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError):
            MediaIndex(path)
    connection = sqlite3.connect(path)
    assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
    assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='file_supplements'").fetchone()
    connection.close()
    repaired = MediaIndex(path)
    assert repaired.db.execute('PRAGMA user_version').fetchone()[0] == 3
    repaired.close()


def schema2_fixture(path):
    original = MediaIndex(path)
    main, extra = pair(original)
    original.db.execute('DROP TABLE supplement_changes')
    original.db.execute('DROP TABLE file_supplements')
    original.db.execute('PRAGMA user_version=2')
    original.db.commit()
    original.close()
    return main, extra


def test_reupgrade_preserves_old_backup_and_captures_new_schema2_manual_state(tmp_path):
    path = tmp_path/'rollback.sqlite3'
    main, _ = schema2_fixture(path)
    first = MediaIndex(path)
    backup = first.migration_backup_path
    original_bytes = backup.read_bytes()
    first.close()
    # Simulate a deliberate offline restore of the first schema-2 recovery
    # point, followed by a real new manual edit made by the old application.
    source, destination = sqlite3.connect(backup), sqlite3.connect(path)
    source.backup(destination)
    source.close()
    mapping = json.loads(destination.execute('SELECT mapping FROM reviews WHERE file=?', (main['id'],)).fetchone()[0])
    mapping['version'] = '回退期间新人工备注'
    destination.execute('UPDATE reviews SET mapping=?,revision=revision+1 WHERE file=?',
                        (json.dumps(mapping), main['id']))
    destination.commit()
    destination.close()
    second = MediaIndex(path)
    assert second.migration_backup_path != backup and backup.read_bytes() == original_bytes
    newest = sqlite3.connect(second.migration_backup_path)
    assert newest.execute('PRAGMA user_version').fetchone()[0] == 2
    recovered = json.loads(newest.execute('SELECT mapping FROM reviews WHERE file=?', (main['id'],)).fetchone()[0])
    assert recovered['version'] == '回退期间新人工备注'
    assert second.item(scope(), main['id'])['mapping'] == recovered
    newest.close()
    second.close()


def test_backup_publish_failure_never_migrates_or_exposes_partial_final_file(tmp_path, monkeypatch):
    from bobbi_core import media_library_index
    path = tmp_path/'publish-failed.sqlite3'
    schema2_fixture(path)
    with monkeypatch.context() as patch:
        patch.setattr(media_library_index.os, 'link', lambda *args: (_ for _ in ()).throw(OSError('interrupted publication')))
        with pytest.raises(OSError, match='interrupted publication'):
            MediaIndex(path)
    original = sqlite3.connect(path)
    assert original.execute('PRAGMA user_version').fetchone()[0] == 2
    assert not original.execute("SELECT 1 FROM sqlite_master WHERE name='file_supplements'").fetchone()
    original.close()
    assert not list(tmp_path.glob('*.bak')) and list(tmp_path.glob('*.tmp'))
    repaired = MediaIndex(path)
    assert repaired.migration_backup_path.is_file()
    repaired.close()


def test_backup_and_schema_change_hold_the_same_writer_lock(tmp_path, monkeypatch):
    from bobbi_core import media_library_index
    path = tmp_path/'locked.sqlite3'
    schema2_fixture(path)
    publish, attempts = media_library_index.os.link, []
    def attempt_write(source, target):
        competing = sqlite3.connect(path, timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                competing.execute('UPDATE reviews SET revision=revision+1')
            attempts.append(True)
        finally:
            competing.close()
        publish(source, target)
    monkeypatch.setattr(media_library_index.os, 'link', attempt_write)
    upgraded = MediaIndex(path)
    assert attempts == [True]
    upgraded.close()
