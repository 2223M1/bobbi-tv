"""Manual migration reuses the real index review/CAS/receipt path."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from bobbi_core import catalog_transfer as transfer
from bobbi_core.catalog_review import plan
from bobbi_core.file_ref import from_selected
from bobbi_core.media_library_index import MediaIndex
from test_media_library_index import scope, ref, insert, command


def record(index, expected, file):
    item = index.item(expected, file['id'])
    return dict(file_ref=index.trusted_file(expected, file['id']),
                **{key: item[key] for key in ('state', 'mapping', 'revision', 'provenance', 'available')})


@pytest.fixture
def scene(tmp_path):
    origin, target = MediaIndex(tmp_path / 'origin.sqlite3'), MediaIndex(tmp_path / 'target.sqlite3')
    expected = scope()
    files = [ref(number, name='特别篇.S00E0%d.mkv' % number) for number in range(1, 4)]
    insert(origin, files)
    insert(target, files)
    commands = [command(files[0], title='中文与Mixed Case'), command(files[1], action='ignore'),
                command(files[2], action='unbind')]
    commands[0]['mapping'] = dict(kind='tv', title='中文与Mixed Case', tmdb_id=42,
                                  season=0, episode=1, version=None)
    assert all(row['status'] == 'applied' for row in origin.apply(expected, uuid4().hex, commands)['items'])
    payload = transfer.export_records(expected, [record(origin, expected, file) for file in files])
    yield origin, target, expected, files, payload
    origin.close()
    target.close()


def test_export_roundtrip_contains_only_manual_descriptions_and_stable_identity(scene):
    origin, _, expected, files, payload = scene
    raw = transfer.dumps(payload)
    assert transfer.loads(raw.encode()) == payload
    assert payload['entries'][0]['mapping']['season'] == 0
    assert payload['entries'][0]['mapping']['version'] is None
    assert payload['entries'][1]['state'] == 'ignored'
    assert payload['entries'][2]['state'] == 'unmatched'
    for forbidden in ('credentials', 'Cookie', 'token', 'epoch', 'request_id', 'receipt',
                      'session_id', 'generation', 'candidates', 'playback', 'url'):
        assert forbidden not in raw
    assert all(row['source_revision'] == 1 for row in payload['entries'])


def test_weak_content_is_not_preselected_and_existing_pipeline_saves_with_local_revisions(scene):
    _, target, expected, files, payload = scene
    before = [target.item(expected, file['id']) for file in files]
    result = transfer.preview(payload, expected, [record(target, expected, file) for file in files])
    assert [row['status'] for row in result['items']] == ['review_required', 'review_required', 'review_required']
    assert [target.item(expected, file['id']) for file in files] == before  # Preview never writes.
    # Explicit user selection supplies ordinary local review entries.
    chunks = plan([dict(name=row['name'], command=row['command']) for row in result['items']])
    for chunk in chunks:
        cmds = [row['command'] for row in chunk['entries']]
        assert all(cmd['expected_revision'] == 0 for cmd in cmds)
        assert all(row['status'] == 'ready' for row in target.preview(expected, cmds)['items'])
        reply = target.apply(expected, chunk['request_id'], cmds)
        assert all(row['status'] == 'applied' for row in reply['items'])
        assert target.apply(expected, chunk['request_id'], cmds) == reply
        assert target.receipt(expected, chunk['request_id'])['items']
    repeated = transfer.preview(payload, expected, [record(target, expected, file) for file in files])
    assert all(row['status'] == 'unchanged' and row['command'] is None for row in repeated['items'])
    # Undo remains the index's existing per-file CAS, not a restoration table.
    undo = command(files[0], revision=1, action='undo')
    assert target.apply(expected, uuid4().hex, [undo])['items'][0]['status'] == 'applied'
    assert target.item(expected, files[0]['id'])['mapping'] is None


def test_existing_manual_target_state_is_a_conflict_not_overwritten(scene):
    _, target, expected, files, payload = scene
    target.apply(expected, uuid4().hex, [command(files[0], title='Keep my new title')])
    result = transfer.preview(payload, expected, [record(target, expected, file) for file in files])
    assert result['items'][0]['status'] == 'conflict' and result['items'][0]['command'] is None
    assert target.item(expected, files[0]['id'])['mapping']['title'] == 'Keep my new title'


def test_target_cas_still_rejects_changes_after_import_preview(scene):
    _, target, expected, files, payload = scene
    planned = transfer.preview(payload, expected, [record(target, expected, file) for file in files])['items'][0]['command']
    target.apply(expected, uuid4().hex, [command(files[0], title='Changed after preview')])
    assert target.apply(expected, uuid4().hex, [planned])['items'][0]['status'] == 'conflict'


def test_switched_account_or_same_name_different_file_is_not_a_match(scene):
    _, target, expected, files, payload = scene
    with pytest.raises(ValueError, match='^CATALOG_ACCOUNT_MISMATCH$'):
        transfer.preview(payload, scope(account='b'), [])
    other = ref(999, name=files[0]['name'])
    insert(target, [other], source='b' * 32)
    rows = transfer.preview(payload, expected, [record(target, expected, other)])['items']
    assert all(row['status'] == 'unresolved' and row['command'] is None for row in rows)


@pytest.mark.parametrize('change', ['size', 'unavailable'])
def test_replaced_or_missing_current_file_is_not_authorized(scene, change):
    _, target, expected, files, payload = scene
    current = [record(target, expected, file) for file in files]
    if change == 'size':
        current[0]['file_ref']['size'] += 1
    else:
        current[0]['available'] = False
    row = transfer.preview(payload, expected, current)['items'][0]
    assert row['status'] == 'unresolved' and row['command'] is None


def test_provider_content_fingerprint_is_required_for_ready_status(tmp_path):
    expected = scope(provider='aliyun')
    file = from_selected(expected, dict(file_id='drive:1', name='Movie.mkv', size=1024,
        directory=False, content_hash='fixture-content-hash'), 'drive:root')
    source = dict(file_ref=file, state='confirmed', mapping=dict(kind='movie', title='电影',
        tmdb_id=42, season=None, episode=None, version='院线版'), revision=1, provenance='manual', available=True)
    payload = transfer.export_records(expected, [source])
    current = dict(source, state='unmatched', mapping=None, revision=0, provenance='filename')
    assert transfer.preview(payload, expected, [current])['items'][0]['status'] == 'ready'
    current = deepcopy(current)
    current['file_ref']['fingerprint']['value'] = 'replacement-content'
    assert transfer.preview(payload, expected, [current])['items'][0]['status'] == 'unresolved'


@pytest.mark.parametrize('mutate', [lambda p: p.update(token='not-exportable'),
    lambda p: p.update(schema='future-schema'), lambda p: p['scope'].update(epoch=999),
    lambda p: p['entries'][0].update(source_revision=True),
    lambda p: p['entries'][0]['reference'].update(url='https://example.test/media'),
    lambda p: p['entries'][0].update(state='proposed'),
    lambda p: p['entries'][0]['mapping'].update(title='https://example.test/script'),
    lambda p: p['entries'].append(deepcopy(p['entries'][0]))])
def test_import_schema_rejects_untrusted_fields_before_any_write(scene, mutate):
    _, target, expected, files, payload = scene
    original = target.item(expected, files[0]['id'])
    altered = deepcopy(payload)
    mutate(altered)
    with pytest.raises(ValueError):
        transfer.loads(json.dumps(altered))
    assert target.item(expected, files[0]['id']) == original


@pytest.mark.parametrize('raw', ['{"schema":"a","schema":"b"}', '{"entries":NaN}',
                               '[', '[' * 2000 + ']' * 2000, b'\xff'])
def test_duplicate_partial_nonfinite_and_bad_encoding_are_rejected(raw):
    with pytest.raises(ValueError):
        transfer.loads(raw)


def test_export_rejects_automatic_candidates_and_oversized_documents(scene):
    _, target, expected, files, _ = scene
    with pytest.raises(ValueError):
        transfer.export_records(expected, [record(target, expected, files[0])])
    with pytest.raises(ValueError, match='^CATALOG_TRANSFER_LIMIT$'):
        transfer.loads(b' ' * (transfer.MAX_BYTES + 1))
