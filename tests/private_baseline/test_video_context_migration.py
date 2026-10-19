"""One-way field migration preserves file identity, never subtitle dependence."""
from copy import deepcopy
import json
import sqlite3
from unittest.mock import patch

import pytest

from lib.cinema import _shared
from bobbi_core import subtitle_binding, video_context
from bobbi_core.capabilities import IPC_PROTOCOL, compatible, descriptor
from bobbi_core.prepared_index import document, load
from lib.clients.bobi_library import to_source
from test_cinema_prepared_index_resolve import prepared
from test_subtitle_binding import video


def test_old_import_is_an_alias_to_same_neutral_implementation_and_identical_key():
    for name in ('digest', 'video_identity', 'checked_video', 'prepared_video'):
        assert getattr(subtitle_binding, name) is getattr(video_context, name)
    original = video()
    assert video_context.checked_video(original) == original
    assert video_context.video_identity(original['media_id'], original['release_key'], original['selected']) == original


def test_legacy_snapshot_is_consumed_once_without_changing_qualified_file(prepared):
    queue, _, folder = prepared
    current = document(queue, 'account')
    original = deepcopy(current['titles'][0]['sources'][0])
    legacy = deepcopy(current)
    legacy['prepared_schema'] = 1
    row = legacy['titles'][0]['sources'][0]
    row['subtitle_video'] = row.pop('video_context')
    target = folder / 'legacy.json'
    target.write_text(json.dumps(legacy), encoding='utf-8')
    loaded = load(target)
    assert loaded['prepared_schema'] == 2
    assert loaded['titles'][0]['sources'][0] == original
    assert 'subtitle_video' not in loaded['titles'][0]['sources'][0]
    # Read-only loading never rewrites user state; owner publication emits v2.
    assert json.loads(target.read_text(encoding='utf-8')) == legacy
    assert document(queue, 'account') == current


def test_conflicting_legacy_and_new_video_context_is_rejected_without_guessing():
    row = dict(subtitle_video=video(), video_context=video(torrent_file_id=99))
    with pytest.raises(ValueError, match='Conflicting'):
        video_context.migrate_entry(row)


def test_matching_legacy_and_new_context_is_normalized_to_one_field():
    original = video()
    row = dict(subtitle_video=original, video_context=deepcopy(original))
    assert video_context.migrate_entry(row) is row
    assert row == {'video_context': original}


def test_new_snapshot_and_ipc_never_emit_legacy_field(prepared):
    queue, _, _ = prepared
    value = document(queue, 'account')
    assert value['prepared_schema'] == 2 and 'subtitle_video' not in json.dumps(value)
    assert IPC_PROTOCOL == 3 and 'video-context-v1' in descriptor()['capabilities']
    assert not compatible(dict(descriptor(), ipc_protocol=2))


@pytest.mark.parametrize('error', [ValueError, TypeError, KeyError, AttributeError, sqlite3.OperationalError])
def test_corrupt_optional_subtitle_database_record_does_not_block_video_projection(prepared, error):
    queue, _, _ = prepared
    before = document(queue, 'account')
    with patch('bobbi_core.subtitle_projection.records', side_effect=error('invalid subtitle fixture')):
        after = document(queue, 'account')
    assert after['titles'] == before['titles']


def test_converter_keeps_video_card_when_optional_subtitle_metadata_is_invalid(prepared):
    queue, _, _ = prepared
    snapshot = document(queue, 'account')
    row = snapshot['titles'][0]['sources'][0]
    row['prepared_subtitle'] = {'invalid': True}
    source = to_source(snapshot, row, dict(tmdb_id='1', mode='tv', season=1, episode=1))
    assert source.preparedResourceId == row['key']
    assert not getattr(source, 'preparedSubtitle', None)


@pytest.mark.parametrize('mutate', ['tuple', 'key', 'media'])
def test_bad_video_context_still_rejects_snapshot(prepared, mutate):
    queue, _, folder = prepared
    snapshot = document(queue, 'account')
    row = snapshot['titles'][0]['sources'][0]['video_context']
    if mutate == 'tuple':
        row['selected']['torrent_file_id'] += 1
    elif mutate == 'key':
        row['key'] = 'f' * 64
    else:
        row['media_id'] = 'tmdb:tv:1:s1:e2'
    target = folder / 'changed.json'
    target.write_text(json.dumps(snapshot), encoding='utf-8')
    with pytest.raises(ValueError):
        load(target)
