"""Supplement migration uses the existing description transaction and undo."""
from copy import deepcopy
from uuid import uuid4

import pytest

from bobbi_core import catalog_transfer as transfer
from bobbi_core.media_library_index import MediaIndex
from test_media_library_index import scope, ref, insert, command
from test_catalog_supplements import relation, cmd


def movie(file, revision=0):
    return dict(command(file, revision=revision), mapping=dict(kind='movie', title='Film',
        tmdb_id=10, season=None, episode=None, version=None))


@pytest.fixture
def scene(tmp_path):
    source, target = MediaIndex(tmp_path / 'source.db'), MediaIndex(tmp_path / 'target.db')
    main, extra = ref(1, name='Film.mkv'), ref(2, name='Interview.mkv')
    for db in (source, target):
        insert(db, [main, extra])
        assert db.apply(scope(), uuid4().hex, [movie(main)])['items'][0]['status'] == 'applied'
    # Source review revisions deliberately differ from the target's revision.
    source.apply(scope(), uuid4().hex, [movie(main, revision=1)])
    assert source.apply(scope(), uuid4().hex, [cmd(source, extra, relation(main['id']))])['items'][0]['status'] == 'applied'
    rows = source.manual_records(scope())['items']
    payload = transfer.loads(transfer.dumps(transfer.export_records(scope(), rows)))
    yield source, target, main, extra, payload
    source.close(); target.close()


def planned(scene):
    _, target, _, extra, payload = scene
    rows = target.manual_records(scope(), file_ids=transfer.lookup_ids(payload))['items']
    return next(row for row in transfer.preview(payload, scope(), rows)['items'] if row['file_id'] == extra['id'])


def test_relationship_export_import_receipt_and_undo_share_one_revision(scene):
    source, target, main, extra, payload = scene
    assert payload['schema'] == transfer.SUPPLEMENT_SCHEMA
    entry = next(row for row in payload['entries'] if row['reference']['id'] == extra['id'])
    assert entry['supplement']['relation']['parent_revision'] == 2
    row = planned(scene)
    assert row['status'] == 'review_required'
    operation = row['command']
    assert operation['mapping']['supplement']['relation']['parent_revision'] == 1
    before = target.item(scope(), extra['id'])
    preview = target.preview(scope(), [operation])['items'][0]
    assert preview['after_supplement']['state'] == 'confirmed'
    assert target.item(scope(), extra['id']) == before
    request = uuid4().hex
    receipt = target.apply(scope(), request, [operation])
    assert receipt['items'][0] == dict(status='applied', revision=1)
    assert target.apply(scope(), request, [operation]) == receipt
    actual = target.item(scope(), extra['id'])
    assert actual['supplement']['parent_file_id'] == main['id']
    assert planned(scene)['status'] == 'unchanged'
    target.apply(scope(), uuid4().hex, [command(extra, action='undo', revision=1)])
    assert 'supplement' not in target.item(scope(), extra['id'])
    assert target.item(scope(), extra['id'])['mapping'] == before['mapping']


@pytest.mark.parametrize('change', ['replace', 'review', 'reverse', 'absent'])
def test_parent_changes_between_preview_and_commit_never_publish_partial_description(scene, change):
    _, target, main, extra, _ = scene
    operation = planned(scene)['command']
    if change == 'replace':
        insert(target, [dict(main, size=main['size'] + 1), extra])
    elif change == 'review':
        target.apply(scope(), uuid4().hex, [command(main, revision=1, title='Changed')])
    elif change == 'absent':
        insert(target, [extra])  # A completed scan revokes only parent membership.
    else:
        target.apply(scope(), uuid4().hex, [movie(extra)])
        target.apply(scope(), uuid4().hex, [cmd(target, main, relation(extra['id']))])
        operation['expected_revision'] = target.item(scope(), extra['id'])['revision']
    before = target.item(scope(), extra['id'])
    result = target.apply(scope(), uuid4().hex, [operation])['items'][0]
    assert result['status'] == 'failed'
    assert target.item(scope(), extra['id']) == before


def test_stale_source_parent_is_preserved_in_export_but_not_silently_reconfirmed(scene):
    source, _, main, _, _ = scene
    source.apply(scope(), uuid4().hex, [movie(main, revision=2)])
    payload = transfer.export_records(scope(), source.manual_records(scope())['items'])
    row = planned((*scene[:4], payload))
    assert row['status'] == 'unresolved' and row['reason'] == 'SUPPLEMENT_REQUIRES_REVIEW'
    assert row['command'] is None


def test_existing_different_relationship_is_not_overwritten(scene):
    _, target, main, extra, _ = scene
    target.apply(scope(), uuid4().hex, [cmd(target, extra, relation(main['id'], title='Different label'))])
    assert planned(scene)['status'] == 'conflict'


def test_shared_work_relationship_and_legacy_import_do_not_erase_extras(scene):
    source, target, main, extra, _ = scene
    source.apply(scope(), uuid4().hex, [cmd(source, extra, relation())])
    payload = transfer.export_records(scope(), source.manual_records(scope())['items'])
    row = planned((*scene[:4], payload))
    assert row['command']['mapping']['supplement']['parent_reference'] is None
    assert target.apply(scope(), uuid4().hex, [row['command']])['items'][0]['status'] == 'applied'
    legacy = deepcopy(payload)
    legacy['schema'] = transfer.SCHEMA
    for entry in legacy['entries']:
        entry.pop('segments'); entry.pop('supplement')
    assert planned((*scene[:4], legacy))['status'] == 'conflict'


def test_parent_absent_from_payload_is_still_looked_up(scene):
    _, target, main, extra, payload = scene
    payload = dict(payload, entries=[row for row in payload['entries'] if row['reference']['id'] == extra['id']])
    assert transfer.lookup_ids(payload) == [extra['id'], main['id']]
    assert planned((*scene[:4], payload))['command'] is not None


def test_cross_account_parent_reference_is_rejected(scene):
    _, _, main, extra, payload = scene
    payload = deepcopy(payload)
    entry = next(row for row in payload['entries'] if row['reference']['id'] == extra['id'])
    foreign = ref(3, expected=scope('b'))
    entry['supplement']['parent_reference'] = foreign
    entry['supplement']['relation']['parent_file_id'] = foreign['id']
    with pytest.raises(ValueError):
        transfer.checked(payload)
