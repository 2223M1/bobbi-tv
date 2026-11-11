"""Real SQLite projection and response behavior, no provider/device claims."""
import json
import platform
from pathlib import Path
import sqlite3
import sys
import time
import tracemalloc
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import catalog_query
from bobbi_core.media_library_index import MediaIndex
from test_media_library_index import scope, ref, insert, command


@pytest.fixture
def index(tmp_path):
    value = MediaIndex(tmp_path / 'catalog.sqlite3')
    yield value
    value.close()


def confirm(index, file, kind='movie', tmdb=10, season=None, episode=None, title='Same title'):
    cmd = command(file)
    cmd['mapping'] = dict(kind=kind, tmdb_id=tmdb, title=title, season=season, episode=episode, version='Local note')
    assert index.apply(scope(), uuid4().hex, [cmd])['items'][0]['status'] == 'applied'


def test_groups_are_descriptive_and_never_merge_original_refs(index):
    files = [ref(i) for i in range(8)]
    insert(index, files)
    for file in files[:3]:
        confirm(index, file)
    confirm(index, files[3], 'tv', season=0, episode=1)
    confirm(index, files[4], 'tv', season=0, episode=1)
    confirm(index, files[5], 'tv', season=1, episode=2)
    confirm(index, files[6], 'movie', tmdb=11)  # Same title, different work.
    result = index.query(scope())
    assert len(result['items']) == 4
    assert sorted(row['variant_count'] for row in result['items']) == [1, 1, 3, 3]
    movie = next(row for row in result['items'] if row['media_kind'] == 'movie' and row['variant_count'] == 3)
    variants = index.query(scope(), query=dict(view='files', parent_entity_id=movie['entity_id']))['items']
    assert {row['entity_id'] for row in variants} == {file['id'] for file in files[:3]}
    show = next(row for row in result['items'] if row['media_kind'] == 'tv')
    seasons = index.query(scope(), query=dict(view='seasons', parent_entity_id=show['entity_id']))['items']
    assert [row['season'] for row in seasons] == [0, 1]
    episodes = index.query(scope(), query=dict(view='episodes', parent_entity_id=seasons[0]['entity_id']))['items']
    assert len(episodes) == 1 and episodes[0]['season'] == 0 and episodes[0]['variant_count'] == 2
    raw = json.dumps(result)
    assert not any(name in raw for name in ('file_ref', 'account_id', 'provider', 'parent', 'tmdb_id', 'version'))


def test_unknown_and_multiepisode_files_never_default_to_first_season(index):
    insert(index, [ref(1, name='Show.E01.mkv'), ref(2, name='Show.S01E01-E02.mkv')])
    rows = index.query(scope())['items']
    assert len(rows) == 2 and all(row['media_kind'] == 'unknown' and row['season'] is None for row in rows)
    assert all(row['review_state'] == 'ambiguous' for row in rows)


def test_10k_scalar_search_pagination_has_zero_reference_decodes(index, monkeypatch):
    task = index.start('a' * 32, scope())
    index.begin(task)
    began = time.monotonic()
    for start in range(0, 10000, 20):
        index.batch(task, [ref(i, name='电影-%05d-🎬.mkv' % i) for i in range(start, start + 20)],
                    dict(page=start // 20), 20)
    index.finish(task, 'completed')
    build_seconds = time.monotonic() - began
    original, decodes = catalog_query.json.loads, []
    def decode(value, *args, **kwargs):
        decodes.append(value)
        return original(value, *args, **kwargs)
    monkeypatch.setattr(catalog_query.json, 'loads', decode)
    tracemalloc.start()
    began = time.monotonic()
    query = dict(text='电影-099', sort='name')
    result = index.query(scope(), query=query, limit=32)
    first_seconds = time.monotonic() - began
    seen = list(result['items'])
    while result['next_cursor']:
        result = index.query(scope(), query=query, cursor=result['next_cursor'], limit=32)
        seen.extend(result['items'])
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert len(seen) == 100 and len({row['entity_id'] for row in seen}) == 100
    assert [row['display_title'] for row in seen] == sorted(row['display_title'] for row in seen)
    assert decodes == []
    assert len(catalog_query.wire(result)) <= 15000
    assert peak < 8 * 1024**2
    print('CATALOG_QUERY_BENCHMARK ' + json.dumps(dict(platform=platform.platform(), files=10000,
        build_seconds=build_seconds, query_seconds=first_seconds, python_peak_bytes=peak,
        returned_rows=len(result['items']), decoded_references=len(decodes),
        response_bytes=len(catalog_query.wire(result)))))


@pytest.mark.parametrize('change', ['insert', 'unbind', 'remove', 'rebuild', 'account', 'epoch', 'query'])
def test_cursors_expire_explicitly_instead_of_skipping_or_repeating(index, change):
    files = [ref(i) for i in range(4)]
    insert(index, files)
    first = index.query(scope(), limit=2)
    expected, query = scope(), {}
    if change == 'insert':
        insert(index, files + [ref(5)])
    elif change == 'unbind':
        index.apply(scope(), uuid4().hex, [command(files[0], action='unbind')])
    elif change == 'remove':
        index.retain_sources([])
    elif change == 'rebuild':
        index.rebuild_projection()
    elif change == 'account':
        expected = scope('b')
    elif change == 'epoch':
        expected = scope(epoch=2)
    else:
        query = dict(sort='recent_added')
    with pytest.raises(ValueError, match='CATALOG_CURSOR_STALE'):
        index.query(expected, query=query, cursor=first['next_cursor'], limit=2)


def test_restart_and_deleted_projection_rebuild_keep_authority_and_unknown_dates(tmp_path):
    path = tmp_path / 'catalog.sqlite3'
    index = MediaIndex(path)
    files = [ref(i) for i in range(3)]
    insert(index, files)
    confirm(index, files[0])
    cursor = index.query(scope(), limit=1)['next_cursor']
    refs = [tuple(row) for row in index.db.execute('SELECT * FROM objects ORDER BY id')]
    mappings = [tuple(row) for row in index.db.execute('SELECT * FROM reviews ORDER BY file')]
    times = [tuple(row) for row in index.db.execute('SELECT * FROM object_times ORDER BY file')]
    index.db.execute('DROP TABLE catalog_rows')
    index.close()
    index = MediaIndex(path)
    try:
        assert len(index.query(scope())['items']) == 3
        assert [tuple(row) for row in index.db.execute('SELECT * FROM objects ORDER BY id')] == refs
        assert [tuple(row) for row in index.db.execute('SELECT * FROM reviews ORDER BY file')] == mappings
        assert [tuple(row) for row in index.db.execute('SELECT * FROM object_times ORDER BY file')] == times
        with pytest.raises(ValueError, match='CURSOR_STALE'):
            index.query(scope(), cursor=cursor, limit=1)
    finally:
        index.close()


def test_schema1_backup_migration_does_not_invent_first_seen(tmp_path):
    path = tmp_path / 'catalog.sqlite3'
    index = MediaIndex(path)
    insert(index, [ref()])
    for table in ('catalog_rows', 'catalog_meta', 'catalog_sources', 'object_times', 'review_requests', 'review_receipt_scopes'):
        index.db.execute('DROP TABLE ' + table)
    index.db.execute('PRAGMA user_version=1')
    index.close()
    index = MediaIndex(path)
    try:
        assert index.db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert index.db.execute('SELECT first_seen FROM catalog_rows').fetchone()[0] is None
        assert index.query(scope())['items'][0]['entity_id'] == ref()['id']
        backup = sqlite3.connect(str(path) + '.schema1.bak')
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 1
        assert backup.execute('SELECT count(*) FROM objects').fetchone()[0] == 1
        backup.close()
    finally:
        index.close()


@pytest.mark.parametrize('contents', [b'', b'partial SQLite backup'])
def test_incomplete_prior_backup_never_allows_schema_migration(tmp_path, contents):
    path = tmp_path / 'catalog.sqlite3'
    index = MediaIndex(path)
    insert(index, [ref()])
    index.db.execute('PRAGMA user_version=1')
    index.close()
    backup = Path(str(path) + '.schema1.bak')
    backup.write_bytes(contents)
    with pytest.raises(ValueError, match='CATALOG_STORAGE_UNSAFE'):
        MediaIndex(path)
    assert backup.read_bytes() == contents
    with sqlite3.connect(path) as original:
        assert original.execute('PRAGMA user_version').fetchone()[0] == 1
        assert original.execute('SELECT count(*) FROM objects').fetchone()[0] == 1


def test_actual_utf8_budget_cuts_page_not_identity_or_writes(index):
    files = [ref(i, name='长🎬' * 500 + '.mkv') for i in range(40)]
    task = index.start('a' * 32, scope())
    index.begin(task)
    index.batch(task, files[:20], dict(page=1), 20)
    index.batch(task, files[20:], dict(page=2), 20)
    index.finish(task, 'completed')
    result = index.query(scope(), limit=32)
    assert len(result['items']) < 32 and result['truncated'] and result['next_cursor']
    assert len(catalog_query.wire(dict(ok=True, result=result))) <= 16384
    assert len(catalog_query.wire(result)) <= 15000
    assert all(len(row['entity_id']) == 64 for row in result['items'])
    assert {row['entity_id'] for row in result['items']} <= {file['id'] for file in files}
    with pytest.raises(ValueError, match='BATCH_LIMIT'):
        index.apply(scope(), uuid4().hex, [command(file) for file in files[:6]])


def test_availability_is_distinct_from_review_and_shared_membership(index):
    file = ref()
    insert(index, [file])
    insert(index, [file], source='b' * 32)
    confirm(index, file)
    assert index.query(scope())['items'][0]['source_count'] == 2
    insert(index, [], source='a' * 32)
    assert index.query(scope())['items'][0]['availability'] == 'observed_present'
    insert(index, [], source='b' * 32)
    assert index.query(scope())['items'][0]['availability'] == 'observed_absent'
    index.retain_sources([])
    row = index.query(scope())['items'][0]
    assert row['availability'] == 'source_unavailable' and row['review_state'] == 'confirmed'


def test_receipt_is_account_scoped_readonly_and_envelope_cannot_expand(index):
    files = [ref(1), ref(2)]
    insert(index, files)
    key = uuid4().hex
    index.apply(scope(), key, [command(files[0])])
    before = index.db.total_changes
    assert index.receipt(scope(), key) == dict(status='found', items=[dict(index=0, status='applied', revision=1)])
    assert index.receipt(scope('b'), key) == dict(status='missing', items=[])
    assert index.db.total_changes == before
    result = index.apply(scope(), key, [command(file) for file in files])
    assert all(row['reason'] == 'REQUEST_ID_REUSED' for row in result['items'])
    assert index._item(files[1]['id'], scope())['revision'] == 0
    index.db.execute('DELETE FROM review_receipt_scopes')
    assert index.receipt(scope(), key)['status'] == 'missing'


def test_group_uses_full_trusted_parent_source_and_snapshot_revision(index):
    prefix = '目录' * 150
    first = [ref(i, name='Show.S00E%02d.mkv' % i, parent=prefix + '甲') for i in range(1, 8)]
    other = ref(10, name='Show.S00E10.mkv', parent=prefix + '乙')
    insert(index, first + [other])
    result = index.group(scope(), first[0]['id'])
    assert len(result['items']) == 5 and result['next_offset'] == 5
    second = index.group(scope(), first[0]['id'], offset=5, projection_revision=result['projection_revision'])
    assert len(second['items']) == 2 and second['next_offset'] is None
    assert {row['file']['id'] for row in result['items'] + second['items']} == {row['id'] for row in first}
    insert(index, [first[0]], source='b' * 32)
    with pytest.raises(ValueError, match='GROUP_AMBIGUOUS'):
        index.group(scope(), first[0]['id'])
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        index.group(scope(), first[0]['id'], source_id='a' * 32, projection_revision=result['projection_revision'])
    assert len(index.group(scope(), first[0]['id'], source_id='b' * 32)['items']) == 1
    with pytest.raises(ValueError, match='SOURCE_UNAVAILABLE'):
        index.group(scope(), first[0]['id'], source_id='c' * 32)


def test_group_never_crosses_namespace_or_account(index):
    account = scope(provider='aliyun')
    from bobbi_core.file_ref import from_selected
    one = from_selected(account, dict(file_id='drive1:1', name='Show.S01E01.mkv', directory=False, size=100), 'root')
    two = from_selected(account, dict(file_id='drive2:2', name='Show.S01E02.mkv', directory=False, size=100), 'root')
    insert(index, [one, two], expected=account)
    assert [row['file']['id'] for row in index.group(account, one['id'])['items']] == [one['id']]
    with pytest.raises(ValueError, match='FILE_NOT_FOUND'):
        index.group(scope(), one['id'])


@pytest.mark.parametrize('query', [dict(view='sql'), dict(limit=900), dict(parent_entity_id='bad'),
    dict(text='a' * 161), dict(view='seasons'), dict(media_kind='secret'), dict(availability='playable')])
def test_query_fields_are_closed(index, query):
    with pytest.raises(ValueError, match='QUERY_INVALID'):
        index.query(scope(), query=query)
