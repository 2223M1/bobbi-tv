"""Exact manual segment migration joins the same preview/CAS/receipt/undo."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from bobbi_core import catalog_transfer as transfer
from bobbi_core.media_library_index import MediaIndex
from test_media_library_index import scope, ref, insert, command
from test_catalog_segments import segment_command


def records(index, file=None):
    return index.manual_records(scope(), file_ids=[file['id']] if file else None)['items']


@pytest.fixture
def scene(tmp_path):
    source, target = MediaIndex(tmp_path / 'source.db'), MediaIndex(tmp_path / 'target.db')
    file = ref(1, name='Show.S01E01.mkv')
    for index in (source, target):
        insert(index, [file])
    source.now = lambda: 1234
    source.apply(scope(), uuid4().hex, [command(file)])
    source.apply(scope(), uuid4().hex, [segment_command(source, file)])
    payload = transfer.loads(transfer.dumps(transfer.export_records(scope(), records(source))))
    yield source, target, file, payload
    source.close(); target.close()


def test_metadata_and_segments_import_in_one_revision_and_one_undo(scene):
    source, target, file, payload = scene
    before = target.item(scope(), file['id'])
    planned = transfer.preview(payload, scope(), records(target, file))['items'][0]
    assert planned['status'] == 'review_required'  # No strong content hash, not preselected.
    cmd = planned['command']
    assert cmd['action'] == 'restore_description' and cmd['expected_revision'] == 0
    preview = target.preview(scope(), [cmd])['items'][0]
    assert preview['status'] == 'ready' and preview['after_segments']['observed_at'] == 1234
    assert target.item(scope(), file['id']) == before
    request = uuid4().hex
    result = target.apply(scope(), request, [cmd])
    assert result == dict(items=[dict(status='applied', revision=1)])
    assert target.apply(scope(), request, [cmd]) == result
    actual, original = target.item(scope(), file['id']), source.item(scope(), file['id'])
    assert actual['mapping'] == original['mapping'] and actual['segments'] == original['segments']
    assert not actual['segments']['auto_allowed']
    assert transfer.preview(payload, scope(), records(target, file))['items'][0]['status'] == 'unchanged'
    target.apply(scope(), uuid4().hex, [command(file, revision=1, action='undo')])
    undone = target.item(scope(), file['id'])
    assert undone['mapping'] == before['mapping'] and undone['state'] == before['state']
    assert 'segments' not in undone


def test_scan_replacement_after_preview_cannot_import_even_if_manual_revision_did_not_change(scene):
    _, target, file, payload = scene
    cmd = transfer.preview(payload, scope(), records(target, file))['items'][0]['command']
    insert(target, [dict(file, size=file['size'] + 1)])
    before = target.item(scope(), file['id'])
    assert before['revision'] == cmd['expected_revision']
    assert target.apply(scope(), uuid4().hex, [cmd])['items'][0]['status'] == 'failed'
    assert target.item(scope(), file['id']) == before


def test_stale_annotations_are_exported_and_restored_without_renewing_old_observation(scene):
    source, target, file, _ = scene
    replacement = dict(file, size=file['size'] + 1)
    for index in (source, target):
        insert(index, [replacement])
    payload = transfer.export_records(scope(), records(source))
    old_key = payload['entries'][0]['segments']['observation_key']
    cmd = transfer.preview(payload, scope(), records(target, file))['items'][0]['command']
    assert target.apply(scope(), uuid4().hex, [cmd])['items'][0]['status'] == 'applied'
    restored = target.item(scope(), file['id'])['segments']
    assert restored['observation_key'] == old_key and restored['state'] == 'verification_required'
    assert restored['auto_allowed'] is False and restored['observed_at'] == 1234


def test_only_segment_edit_on_automatic_suggestion_is_not_dropped_from_export(scene):
    source, _, file, _ = scene
    second = ref(2, name='Show.S01E02.mkv')
    insert(source, [second], source='b' * 32)
    source.apply(scope(), uuid4().hex, [segment_command(source, second)])
    payload = transfer.export_records(scope(), records(source))
    row = next(row for row in payload['entries'] if row['reference']['id'] == second['id'])
    assert row['state'] == 'proposed' and row['mapping'] is None and row['segments']


def test_different_manual_segment_or_title_is_conflict_not_overwritten(scene):
    _, target, file, payload = scene
    target.apply(scope(), uuid4().hex, [segment_command(target, file, duration=800000)])
    before = target.item(scope(), file['id'])
    row = transfer.preview(payload, scope(), records(target, file))['items'][0]
    assert row['status'] == 'conflict' and row['command'] is None
    assert target.item(scope(), file['id']) == before


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(auto_allowed=True), lambda s: s.update(source='detected'),
    lambda s: s.update(observed_at=10 ** 500), lambda s: s.update(duration_ms=True),
    lambda s: s['items'][0].update(end_ms=900000), lambda s: s.update(observation_key='url'),
])
def test_import_cannot_forge_automatic_policy_or_invalid_evidence(scene, mutate):
    _, target, file, payload = scene
    altered = deepcopy(payload)
    mutate(altered['entries'][0]['segments'])
    with pytest.raises(ValueError):
        transfer.loads(json.dumps(altered))
    assert target.item(scope(), file['id'])['revision'] == 0
