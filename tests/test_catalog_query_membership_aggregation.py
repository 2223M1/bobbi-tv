"""Grouping counts files once and active sources once, across overlapping roots."""
from uuid import uuid4

import pytest

from test_media_library_index import scope, ref, insert, command
from bobbi_core.catalog_query import opaque
from bobbi_core.media_library_index import MediaIndex


@pytest.fixture
def grouped(tmp_path):
    index = MediaIndex(tmp_path / 'groups.sqlite3')
    files = [ref(number, name='Same.Title.%02d.mkv' % number) for number in range(9)]
    insert(index, files[:8])
    insert(index, [files[n] for n in (0, 3, 4)], source='b' * 32)
    insert(index, [files[n] for n in (1, 2, 4, 8)], source='c' * 32)
    for number, file in enumerate(files):
        if number == 7:
            continue
        tv = number in (3, 4, 5, 6)
        cmd = command(file)
        cmd['mapping'] = dict(kind='tv' if tv else 'movie', title='Same title',
            tmdb_id=20 if tv else 10 if number in (0, 1) else 11 if number == 2 else 12,
            season=0 if number in (3, 4, 5) else 2 if number == 6 else None,
            episode=1 if number in (3, 4, 6) else 2 if number == 5 else None, version=None)
        index.apply(scope(), uuid4().hex, [cmd])
    # One root no longer sees 0/2/3/5. Other live memberships still count.
    insert(index, [files[n] for n in (1, 4, 6, 7)])
    index.retain_sources(['a' * 32, 'b' * 32])
    other = scope('b')
    insert(index, [ref(0, expected=other)], source='d' * 32, expected=other)
    with index.transaction():
        index.db.executemany('INSERT INTO memberships VALUES(?,?,?,0)',
            [('%032x' % number, files[0]['id'], 'historical') for number in range(100)])
    try:
        yield index, files
    finally:
        index.close()


def work(kind, identifier):
    return opaque(scope()['provider'], scope()['account_id'], kind, identifier)


@pytest.mark.parametrize('filters, expected', [
    ({}, {10: (2, 2, 2, 'observed_present'), 11: (1, 0, 0, 'observed_absent'),
          12: (1, 0, 0, 'source_unavailable')}),
    ({'source_id': 'a' * 32}, {10: (2, 2, 2, 'observed_present'), 11: (1, 0, 0, 'observed_absent')}),
    ({'source_id': 'b' * 32}, {10: (1, 1, 1, 'observed_present')}),
    ({'source_id': 'c' * 32}, {10: (1, 1, 1, 'observed_present'), 11: (1, 0, 0, 'observed_absent'),
                            12: (1, 0, 0, 'source_unavailable')}),
    ({'availability': 'observed_absent'}, {11: (1, 0, 0, 'observed_absent')}),
    ({'availability': 'source_unavailable'}, {12: (1, 0, 0, 'source_unavailable')}),
])
def test_overlapping_and_removed_sources_preserve_filter_semantics(grouped, filters, expected):
    index, _ = grouped
    rows = index.query(scope(), query=dict(media_kind='movie', **filters))['items']
    actual = {row['entity_id']: tuple(row[key] for key in
        ('variant_count', 'available_count', 'source_count', 'availability')) for row in rows}
    assert actual == {work('movie', identifier): counts for identifier, counts in expected.items()}
    assert len(index.query(scope('b'))['items']) == 1


def test_season_episode_aggregation_deduplicates_variants_and_sources(grouped):
    index, files = grouped
    show = next(row for row in index.query(scope())['items'] if row['entity_id'] == work('tv', 20))
    assert (show['variant_count'], show['available_count'], show['source_count']) == (4, 3, 2)
    seasons = index.query(scope(), query=dict(view='seasons', parent_entity_id=show['entity_id']))['items']
    assert [row['season'] for row in seasons] == [0, 2]
    assert [(row['variant_count'], row['available_count'], row['source_count']) for row in seasons] == [(3, 2, 2), (1, 1, 1)]
    episodes = index.query(scope(), query=dict(view='episodes', parent_entity_id=seasons[0]['entity_id']))['items']
    assert [row['episode'] for row in episodes] == [1, 2]
    assert [(row['variant_count'], row['available_count'], row['source_count']) for row in episodes] == [(2, 2, 2), (1, 0, 0)]
    variants = index.query(scope(), query=dict(view='files', parent_entity_id=episodes[0]['entity_id']))['items']
    assert {row['entity_id'] for row in variants} == {files[3]['id'], files[4]['id']}
    assert all(row['variant_count'] == 1 and row['available_count'] == 1 for row in variants)


@pytest.mark.parametrize('view', ['works', 'files'])
@pytest.mark.parametrize('sort', ['name', 'recent_added', 'recent_edited'])
def test_grouping_retains_total_order_and_cursor_without_skipping_ties(grouped, view, sort):
    index, _ = grouped
    query = dict(view=view, sort=sort, text='same')
    full = index.query(scope(), query=query, limit=32)['items']
    cursor, collected = None, []
    while True:
        page = index.query(scope(), query=query, cursor=cursor, limit=1)
        collected.extend(page['items'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert collected == full
    assert len({row['entity_id'] for row in collected}) == len(collected)
