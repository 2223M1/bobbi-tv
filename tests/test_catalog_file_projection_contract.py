"""Real SQLite file search/sort and schema-5 projection upgrade boundaries."""
import sqlite3
from uuid import uuid4

import pytest

from test_media_library_index import scope, ref, insert, command, index
from test_scan_source_ports import cd2, scan, query
from bobbi_core import catalog_query, mounted_ref
from bobbi_core.media_library_index import MediaIndex


def describe(index, file, note, *, expected=None, kind='movie', title='Shared title', tmdb=10):
    expected = expected or scope()
    revision = index.item(expected, file['id'])['revision']
    cmd = command(file, revision=revision)
    cmd['mapping'] = dict(kind=kind, title=title, tmdb_id=None if kind == 'custom' else tmdb,
        season=1 if kind == 'tv' else None, episode=2 if kind == 'tv' else None, version=note)
    result = index.apply(expected, uuid4().hex, [cmd])
    assert result['items'][0]['status'] == 'applied'


@pytest.mark.parametrize('name', ['Original.mkv', '长文件名' * 80 + '.mkv'], ids=['short', 'long'])
def test_file_reply_does_not_expose_private_detail_fields(index, name):
    file = ref(name=name)
    insert(index, [file])
    describe(index, file, '导演剪辑')
    row = index.query(scope(), query=dict(view='files'))['items'][0]
    assert not {key for key in row if key.startswith('_')}
    assert row['file_name'] == name[:160]
    assert row['truncated'] == (len(name) > 160)


@pytest.mark.parametrize('kind', ['movie', 'tv', 'custom'])
def test_version_note_search_uses_existing_normalization_and_scope(index, kind):
    first, second = ref(101, name='opaque-first.mkv'), ref(102, name='opaque-second.mkv')
    insert(index, [first], source='a' * 32)
    insert(index, [second], source='b' * 32)
    other = scope('b')
    unrelated = ref(103, expected=other)
    insert(index, [unrelated], source='c' * 32, expected=other)
    for file, expected in ((first, scope()), (second, scope()), (unrelated, other)):
        describe(index, file, '导演剪辑 ＡＢＣ Straße 100%_本地备注', kind=kind, expected=expected)
    for text in ('导演剪辑', 'abc', 'STRASSE', '100%_'):
        result = index.query(scope(), query=dict(view='files', text=text, source_id='a' * 32))
        assert [item['entity_id'] for item in result['items']] == [first['id']]
        assert result['items'][0]['version_label'] == '导演剪辑 ＡＢＣ Straße 100%_本地备注'
    assert not index.query(scope(), query=dict(text='100X_'))['items']
    assert not index.query(scope(), query=dict(text='100%X'))['items']
    work = index.query(scope(), query=dict(text='导演剪辑', source_id='a' * 32))['items'][0]
    parent = work['entity_id']
    if kind == 'tv':
        parent = index.query(scope(), query=dict(view='seasons', parent_entity_id=parent,
            text='导演剪辑', source_id='a' * 32))['items'][0]['entity_id']
        parent = index.query(scope(), query=dict(view='episodes', parent_entity_id=parent,
            text='导演剪辑', source_id='a' * 32))['items'][0]['entity_id']
    assert [item['entity_id'] for item in index.query(scope(), query=dict(view='files',
        parent_entity_id=parent, text='导演剪辑', source_id='a' * 32))['items']] == [first['id']]
    assert index.trusted_file(scope(), first['id']) == first


def test_version_edit_undo_and_unbind_reproject_search_and_stale_cursor(index):
    files = [ref(number) for number in (20, 21, 22)]
    insert(index, files)
    for file in files:
        describe(index, file, 'Old cut')
    first = index.query(scope(), query=dict(view='files', text='old cut'), limit=1)
    describe(index, files[0], 'New cut')
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        index.query(scope(), query=dict(view='files', text='old cut'), cursor=first['next_cursor'], limit=1)
    assert [item['entity_id'] for item in index.query(scope(), query=dict(view='files', text='new cut'))['items']] == [files[0]['id']]
    assert len(index.query(scope(), query=dict(view='files', text='old cut'))['items']) == 2
    assert index.apply(scope(), uuid4().hex, [command(files[0], revision=2, action='undo')])['items'][0]['status'] == 'applied'
    assert not index.query(scope(), query=dict(view='files', text='new cut'))['items']
    assert len(index.query(scope(), query=dict(view='files', text='old cut'))['items']) == 3
    assert index.apply(scope(), uuid4().hex, [command(files[0], revision=3, action='unbind')])['items'][0]['status'] == 'applied'
    assert len(index.query(scope(), query=dict(view='files', text='old cut'))['items']) == 2
    assert index.trusted_file(scope(), files[0]['id']) == files[0]


@pytest.mark.parametrize('limit', [1, 3, 32])
def test_files_sort_by_normalized_filename_and_paginate_ties(index, limit):
    names = ['Z.mkv', 'Ｂ.mkv', '阿.mkv', 'a.mkv', 'b.mkv', 'same.mkv', 'SAME.MKV', 'β.mkv']
    files = [ref(number, name=name) for number, name in enumerate(names)]
    insert(index, files)
    for file in files:
        describe(index, file, '收藏版')
    # Same work title has no useful order among the actual file versions.
    expected = sorted(files, key=lambda file: (catalog_query.normalized(file['name']), file['id']))
    collected, cursor = [], None
    while True:
        page = index.query(scope(), query=dict(view='files', sort='name', text='收藏版'), cursor=cursor, limit=limit)
        collected.extend(item['entity_id'] for item in page['items'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert collected == [file['id'] for file in expected]
    assert len(collected) == len(set(collected)) == len(files)


def test_file_sort_change_keeps_work_title_order_and_recent_added_order(index):
    files = [ref(44, name='Z-original.mkv'), ref(45, name='A-original.mkv')]
    tick = [100.0]
    index.now = lambda: tick[0]
    insert(index, files[:1])
    tick[0] += 60
    insert(index, files)
    describe(index, files[0], '版甲', title='Alpha work', tmdb=1)
    describe(index, files[1], '版乙', title='Zulu work', tmdb=2)
    assert [item['display_title'] for item in index.query(scope())['items']] == ['Alpha work', 'Zulu work']
    assert [item['file_name'] for item in index.query(scope(), query=dict(view='files'))['items']] == ['A-original.mkv', 'Z-original.mkv']
    assert [item['entity_id'] for item in index.query(scope(), query=dict(view='files', sort='recent_added'))['items']] == [files[1]['id'], files[0]['id']]


def test_mounted_version_search_uses_same_projection_without_creating_play_grant(cd2):
    service, source, _, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    file = next(item for item in query(cd2, query=dict(view='files'))['items'] if item['file_name'] == 'Movie.mkv')
    original = service.index.trusted_mounted_file(authority, file['entity_id'])
    describe(service.index, original, '国语收藏版', expected=authority)
    result = query(cd2, query=dict(view='files', text='国语收藏', source_id=source.id))
    assert [item['entity_id'] for item in result['items']] == [file['entity_id']]
    assert 'history_key' not in result['items'][0]
    assert not service.mounted.tickets and not service.mounted.claims
    assert service.index.trusted_mounted_file(authority, file['entity_id']) == original


# Actual projection schema at reviewed commit 9446e59; the authoritative tables
# below come from real index writes, not a hand-built substitute for review state.
V5_SCHEMA = ('id TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,'
    'work_id TEXT NOT NULL,season_id TEXT,episode_id TEXT,title TEXT NOT NULL,'
    'filename TEXT NOT NULL,title_sort TEXT NOT NULL,search_text TEXT NOT NULL,'
    'media_kind TEXT NOT NULL,season INTEGER,episode INTEGER,review_state TEXT NOT NULL,'
    'first_seen REAL,updated REAL NOT NULL,group_key TEXT NOT NULL,namespace TEXT NOT NULL,authority_generation TEXT NOT NULL,'
    'metadata_key TEXT,year INTEGER')
AUTHORITATIVE = ('objects', 'typed_objects', 'memberships', 'reviews', 'review_changes',
    'review_requests', 'review_receipts', 'review_receipt_scopes', 'object_times', 'catalog_scope_revisions')


def authoritative_snapshot(db):
    return {table: sorted(db.execute('SELECT * FROM ' + table).fetchall()) for table in AUTHORITATIVE}


@pytest.mark.parametrize('interrupt', [False, True])
def test_real_schema5_records_upgrade_atomically_and_keep_receipts(tmp_path, monkeypatch, interrupt):
    path = tmp_path / 'legacy-v5.sqlite3'
    index = MediaIndex(path)
    files = [ref(51, name='Z-opaque.mkv'), ref(52, name='A-opaque.mkv')]
    insert(index, files)
    for file in files:
        describe(index, file, '旧版导演剪辑')
    mounted_scope = dict(reference_kind='mounted_path', source_id='d' * 32,
        namespace='e' * 64, generation='f' * 64)
    local_file = tmp_path / 'Local.mkv'
    local_file.write_bytes(b'local media fixture')
    mounted_file = mounted_ref.observed(mounted_scope, local_file.name, local_file.stat())
    task = index.start(mounted_scope['source_id'], mounted_scope)
    index.begin(task)
    index.mounted_batch(task, [mounted_file], dict(page=1), 1)
    index.finish(task, 'completed')
    describe(index, mounted_file, '旧挂载收藏版', expected=mounted_scope)
    columns = [column.split()[0] for column in V5_SCHEMA.split(',')]
    legacy_rows = [tuple(row) for row in index.db.execute('SELECT ' + ','.join(columns) + ' FROM catalog_rows')]
    with index.transaction():
        index.db.execute('DROP TABLE catalog_rows')
        index.db.execute('CREATE TABLE catalog_rows(' + V5_SCHEMA + ')')
        index.db.executemany('INSERT INTO catalog_rows VALUES(' + ','.join('?' for _ in columns) + ')', legacy_rows)
        for file in files:
            index.db.execute('UPDATE catalog_rows SET search_text=? WHERE id=?',
                (catalog_query.normalized('Shared title\n' + file['name']), file['id']))
        index.db.execute('UPDATE catalog_meta SET schema=5')
        index.db.execute('DROP TABLE file_supplements')
        index.db.execute('DROP TABLE supplement_changes')
        index.db.execute('PRAGMA user_version=2')
    index.close()
    with sqlite3.connect(path) as old:
        before = authoritative_snapshot(old)
        old_projection = old.execute('SELECT * FROM catalog_rows ORDER BY id').fetchall()
        old_meta = old.execute('SELECT * FROM catalog_meta').fetchall()
    if interrupt:
        original = catalog_query.project
        calls = []
        def interrupted(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('projection upgrade interrupted')
            return original(*args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(catalog_query, 'project', interrupted)
            with pytest.raises(RuntimeError, match='projection upgrade interrupted'):
                MediaIndex(path)
        with sqlite3.connect(path) as old:
            assert authoritative_snapshot(old) == before
            assert old.execute('SELECT * FROM catalog_rows ORDER BY id').fetchall() == old_projection
            assert old.execute('SELECT * FROM catalog_meta').fetchall() == old_meta
            assert old.execute('PRAGMA user_version').fetchone()[0] == 2
    upgraded = MediaIndex(path)
    try:
        assert upgraded.db.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 6
        assert upgraded.db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert [item['file_name'] for item in upgraded.query(scope(), query=dict(view='files', text='旧版导演剪辑'))['items']] == ['A-opaque.mkv', 'Z-opaque.mkv']
        assert [item['entity_id'] for item in upgraded.query(mounted_scope,
            query=dict(view='files', text='旧挂载收藏版'))['items']] == [mounted_file['id']]
        with sqlite3.connect(path) as current:
            assert authoritative_snapshot(current) == before
    finally:
        upgraded.close()
