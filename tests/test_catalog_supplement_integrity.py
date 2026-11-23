"""Real review/query paths preserve one-level extras and main-file filtering."""
from uuid import uuid4

import pytest

from test_media_library_index import index, scope, ref, insert, command
from test_catalog_file_projection_contract import describe
from test_catalog_supplements import relation, cmd, apply
from bobbi_core.catalog_query import REPLY_BYTES, wire


@pytest.mark.parametrize('changed_graph', ['parent_became_extra', 'file_acquired_child'])
def test_undo_cannot_restore_an_extra_into_a_nested_or_cyclic_graph(index, changed_graph):
    main, extra, third = [ref(number) for number in (10, 11, 12)]
    insert(index, [main, extra, third])
    for file in (main, extra, third):
        describe(index, file, None)
    apply(index, cmd(index, extra, relation(main['id'])))
    apply(index, cmd(index, extra, action='detach_supplement'))
    if changed_graph == 'parent_became_extra':
        apply(index, cmd(index, main, relation(third['id'])))
    else:
        apply(index, cmd(index, third, relation(extra['id'])))
    before = index.item(scope(), extra['id'])
    undo = cmd(index, extra, action='undo')
    assert index.preview(scope(), [undo])['items'][0]['status'] == 'failed'
    request = uuid4().hex
    result = index.apply(scope(), request, [undo])
    assert result['items'][0]['status'] == 'failed'
    assert index.apply(scope(), request, [undo]) == result
    assert index.item(scope(), extra['id']) == before
    assert index.db.execute('SELECT COUNT(*) FROM file_supplements').fetchone()[0] == 1


def test_reverse_attachment_then_undo_does_not_hide_both_files_in_cycle(index):
    main, extra = ref(20), ref(21)
    insert(index, [main, extra])
    for file in (main, extra):
        describe(index, file, None)
    apply(index, cmd(index, extra, relation(main['id'])))
    apply(index, cmd(index, extra, action='detach_supplement'))
    apply(index, cmd(index, main, relation(extra['id'])))
    result = index.apply(scope(), uuid4().hex, [cmd(index, extra, action='undo')])
    assert result['items'][0]['status'] == 'failed'
    assert [row['entity_id'] for row in index.query(scope(), query={'view': 'files'})['items']] == [extra['id']]


@pytest.mark.parametrize('change', ['mapping', 'size'])
def test_undo_preserves_stale_historical_relation_as_unverified_without_renewing_it(index, change):
    main, extra = ref(30), ref(31)
    insert(index, [main, extra])
    describe(index, main, 'Original cut')
    apply(index, cmd(index, extra, relation(main['id'])))
    apply(index, cmd(index, extra, action='detach_supplement'))
    if change == 'mapping':
        describe(index, main, 'New cut', tmdb=11)
    else:
        insert(index, [dict(main, size=main['size'] + 1), extra])
    apply(index, cmd(index, extra, action='undo'))
    restored = index.item(scope(), extra['id'])['supplement']
    assert restored['parent_file_id'] == main['id']
    assert restored['state'] == 'verification_required'


@pytest.mark.parametrize('level', ['movie', 'tv_work', 'tv_season', 'tv_episode'])
def test_review_filter_on_a_main_version_page_cannot_reintroduce_supplement_files(index, level):
    main, extra = ref(40), ref(41)
    insert(index, [main, extra])
    kind = 'movie' if level == 'movie' else 'tv'
    for file in (main, extra):
        describe(index, file, None, kind=kind)
    apply(index, cmd(index, extra, relation(main['id'], metadata_key='tmdb:%s:10' % kind)))
    parent = index.query(scope())['items'][0]['entity_id']
    if level in ('tv_season', 'tv_episode'):
        parent = index.query(scope(), query=dict(view='seasons', parent_entity_id=parent))['items'][0]['entity_id']
    if level == 'tv_episode':
        parent = index.query(scope(), query=dict(view='episodes', parent_entity_id=parent))['items'][0]['entity_id']
    filtered = dict(view='files', parent_entity_id=parent, review_state='confirmed')
    assert [row['entity_id'] for row in index.query(scope(), query=filtered)['items']] == [main['id']]
    workbench = index.query(scope(), query=dict(view='files', review_state='confirmed'))['items']
    assert {row['entity_id'] for row in workbench} == {main['id'], extra['id']}
    extras = index.query(scope(), query=dict(view='supplements', parent_entity_id=main['id'],
                                            review_state='confirmed'))['items']
    assert [row['entity_id'] for row in extras] == [extra['id']]


def test_supplement_editor_receives_saved_parent_evidence_even_after_parent_changes(index):
    main, extra = ref(50), ref(51)
    insert(index, [main, extra])
    describe(index, main, 'Original')
    attachment = cmd(index, extra, relation(main['id']))
    saved = attachment['mapping']
    apply(index, attachment)
    for changed in (False, True):
        if changed:
            describe(index, main, 'Changed')
        for summary in (index.item(scope(), extra['id'])['supplement'],
                index.query(scope(), query=dict(view='supplements', parent_entity_id=main['id']))['items'][0]['supplement']):
            assert summary['parent_revision'] == saved['parent_revision']
            assert summary['parent_evidence'] == saved['parent_evidence']
            assert summary['state'] == ('verification_required' if changed else 'confirmed')
    retained = dict(saved, title='Edited extra title')
    command = cmd(index, extra, action='detach_supplement')
    command.update(action='supplement', mapping=retained)
    assert index.apply(scope(), uuid4().hex, [command])['items'][0]['status'] == 'failed'


def test_saved_parent_evidence_respects_bounded_supplement_pages_and_shared_nulls(index):
    files = [ref(number, name='中文文件' * 60 + str(number) + '.mkv') for number in range(60, 80)]
    insert(index, files)
    main, extras = files[0], files[1:]
    describe(index, main, 'Original')
    for number, extra in enumerate(extras):
        apply(index, cmd(index, extra, relation(main['id'] if number else None, title='花' * 160)))
    cursor, seen, pages = None, [], 0
    while True:
        result = index.query(scope(), query=dict(view='supplements', parent_entity_id=main['id']),
                             cursor=cursor, limit=32)
        assert len(wire(result)) <= REPLY_BYTES
        pages += 1
        for row in result['items']:
            detail = row['supplement']
            if detail['parent_file_id']:
                assert detail['parent_revision'] == 1 and len(detail['parent_evidence']) == 64
            else:
                assert detail['parent_revision'] is None and detail['parent_evidence'] is None
            seen.append(row['entity_id'])
        cursor = result['next_cursor']
        if cursor is None:
            break
        assert pages < 20
    assert pages > 1 and len(seen) == len(set(seen)) == len(extras)
    assert set(seen) == {row['id'] for row in extras}
