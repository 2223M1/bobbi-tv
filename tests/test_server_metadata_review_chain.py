"""SYS-090 controlled server-adapter/scan/SQLite/review interaction proofs.

Reuse the production-adapter fixture rather than another metadata store. Only
the remote response transport is synthetic. No live-server, TV, playback or
complete system-acceptance result is implied by these cross-module cases.
"""
from uuid import uuid4

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_platform.pan_accounts import PanError
from test_media_library_index import command
from test_catalog_supplements import cmd, relation
from test_server_descriptions import scene  # noqa: F401 - three-provider fixture


def call(scene, action, **body):
    return scene.service.dispatch(action, dict(expected=scene.expected, **body))


def item(scene, file):
    return call(scene, 'catalog_item', file_id=file['id'])


def manual_state(scene):
    # Candidate descriptions and scan membership are allowed to change; the
    # manual transaction, original receipts and parent evidence are not.
    tables = ('review_changes', 'supplement_changes', 'file_supplements',
              'review_requests', 'review_receipts')
    return {table: [tuple(row) for row in scene.index.db.execute(
        'SELECT * FROM ' + table + ' ORDER BY rowid')] for table in tables}


def preview(scene, value):
    before = manual_state(scene)
    result = call(scene, 'catalog_preview', commands=[value])['items'][0]
    assert manual_state(scene) == before
    return result


def commit(scene, value, status='applied'):
    request = uuid4().hex
    result = call(scene, 'catalog_apply', request_id=request, commands=[value])
    assert result['items'][0]['status'] == status
    after = manual_state(scene)
    assert call(scene, 'catalog_receipt', request_id=request)['items'] == [
        dict(index=0, **result['items'][0])]
    assert call(scene, 'catalog_apply', request_id=request, commands=[value]) == result
    assert manual_state(scene) == after
    return result['items'][0]


def scan(scene, state='completed'):
    task = call(scene, 'catalog_scan', source_id=scene.directory['id'])['task_id']
    scene.service.worker.join(5)
    assert not scene.service.worker.is_alive()
    job = call(scene, 'catalog_jobs', task=task)['items'][0]
    assert job['state'] == state, job
    return job


def media(scene, count):
    if scene.provider == 'plex':
        scene.wire.media = [dict(id=str(100+n), Part=[dict(id=str(200+n),
            key='/library/parts/%d/456/file.mkv' % (200+n), size=8,
            file='/movies/Source-%02d.mkv' % n)]) for n in range(count)]
    else:
        scene.wire.media = [dict(Id='version%d' % n, Protocol='File',
            Path='/movies/Source-%02d.mkv' % n, Size=8) for n in range(count)]
    scan(scene)
    refs, page = [], 1
    while True:
        result = scene.pans.list_files(scene.expected, scene.parent, page)
        refs.extend(from_selected(scene.expected, row, scene.parent) for row in result['items'])
        if not result['has_more']:
            break
        page += 1
    assert len(refs) == len({file['id'] for file in refs}) == count
    return refs


def name(scene, file, title):
    value = command(file, revision=item(scene, file)['revision'], title=title)
    assert preview(scene, value)['status'] == 'ready'
    commit(scene, value)


def attach(scene, extra, parent, title='Manual extra'):
    value = cmd(scene.index, extra, relation(parent['id'], metadata_key=None, title=title),
                expected=scene.expected)
    assert preview(scene, value)['status'] == 'ready'
    commit(scene, value)
    return item(scene, extra)['supplement']


def refresh_title(scene, title):
    # Deliberately change only the provider title, not the selected file or any
    # manual review field. A later episode/parent claim is exercised separately.
    scene.wire.claims['title' if scene.provider == 'plex' else 'Name'] = title


def manual_fields(value):
    return {key: value.get(key) for key in
            ('mapping', 'state', 'reason', 'revision', 'provenance', 'supplement')}


def test_provider_refresh_between_preview_commit_reparent_and_undo_preserves_manual_evidence(scene):
    first, second, extra = media(scene, 3)
    pending = command(first, title='User first parent')
    assert preview(scene, pending)['status'] == 'ready'
    refresh_title(scene, 'Provider changed while preview was open')
    scan(scene)
    commit(scene, pending)
    name(scene, second, 'User second parent')
    name(scene, extra, 'User child file')
    original = attach(scene, extra, first)
    before = {file['id']: manual_fields(item(scene, file)) for file in (first, second, extra)}
    journal = manual_state(scene)

    refresh_title(scene, 'Provider title only')
    scan(scene)
    assert manual_state(scene) == journal
    assert {file['id']: manual_fields(item(scene, file)) for file in (first, second, extra)} == before
    assert all(item(scene, file)['candidates'][-1]['description']['title'] == 'Provider title only'
               for file in (first, second, extra))

    # Editing only the supplement label must retain its original parent CAS.
    label = {key: value for key, value in original.items() if key != 'state'}
    label['title'] = 'User renamed extra only'
    rename = dict(file_id=extra['id'], expected_revision=item(scene, extra)['revision'],
                  action='supplement', mapping=label)
    assert preview(scene, rename)['status'] == 'ready'
    if scene.provider == 'plex':
        scene.wire.claims.update(type='episode', grandparentTitle='Wrong provider parent',
                                parentIndex=9, index=8)
    else:
        scene.wire.claims.update(Type='Episode', SeriesName='Wrong provider parent',
                                ParentIndexNumber=9, IndexNumber=8)
    scan(scene)
    commit(scene, rename)
    renamed = item(scene, extra)['supplement']
    assert renamed == dict(original, title=label['title'])
    attach(scene, extra, second, title=label['title'])
    reparented = item(scene, extra)['supplement']
    assert reparented['parent_file_id'] == second['id']
    assert reparented['parent_evidence'] == item(scene, second)['file']['observation_key']
    journal = manual_state(scene)
    refresh_title(scene, 'Provider refresh after manual reparent')
    scan(scene)
    assert manual_state(scene) == journal and item(scene, extra)['supplement'] == reparented
    undo = cmd(scene.index, extra, action='undo', expected=scene.expected)
    assert preview(scene, undo)['after_supplement'] == renamed
    commit(scene, undo)
    assert item(scene, extra)['supplement'] == renamed
    assert item(scene, extra)['mapping']['title'] == 'User child file'
    assert item(scene, first)['mapping']['title'] == 'User first parent'
    assert item(scene, second)['mapping']['title'] == 'User second parent'
    cards = call(scene, 'catalog_query')['items']
    assert {card['display_title'] for card in cards} == {'User first parent', 'User second parent'}
    assert all('server_description' not in card for card in cards)


@pytest.mark.parametrize('parent_change', ['manual_title', 'file_size'])
def test_refresh_cannot_reconfirm_historical_parent_or_rebind_title_only_edit(scene, parent_change):
    parent, extra = media(scene, 2)
    name(scene, parent, 'User parent')
    name(scene, extra, 'User extra')
    saved = attach(scene, extra, parent)
    detach = cmd(scene.index, extra, action='detach_supplement', expected=scene.expected)
    assert preview(scene, detach)['after_supplement'] is None
    commit(scene, detach)
    if parent_change == 'manual_title':
        name(scene, parent, 'User changed parent title')
    elif scene.provider == 'plex':
        scene.wire.media[0]['Part'][0]['size'] += 1
    else:
        scene.wire.media[0]['Size'] += 1
    refresh_title(scene, 'Conflicting server after parent change')
    scan(scene)
    undo = cmd(scene.index, extra, action='undo', expected=scene.expected)
    expected = dict(saved, state='verification_required')
    assert preview(scene, undo)['after_supplement'] == expected
    commit(scene, undo)
    assert item(scene, extra)['supplement'] == expected
    journal = manual_state(scene)
    refresh_title(scene, 'Another source-only refresh')
    scan(scene)
    assert manual_state(scene) == journal and item(scene, extra)['supplement'] == expected

    # A label edit uses saved evidence, not freshly captured parent evidence.
    label = {key: value for key, value in saved.items() if key != 'state'}
    label['title'] = 'Label edit is not parent reconfirmation'
    value = dict(file_id=extra['id'], expected_revision=item(scene, extra)['revision'],
                 action='supplement', mapping=label)
    before = item(scene, extra)
    assert preview(scene, value)['status'] == 'failed'
    commit(scene, value, status='failed')
    assert item(scene, extra) == before
    assert before['mapping']['title'] == 'User extra'


@pytest.mark.parametrize('fail_page', [1, 2], ids=['disconnected_before_page', 'partial_then_disconnect'])
def test_disconnected_or_partial_scan_retains_manual_title_parent_and_unseen_membership(scene, fail_page):
    refs = media(scene, 21)  # Production scan window is 20, not a patched pager.
    parent, extra = refs[0], refs[-1]
    name(scene, parent, 'Retained parent title')
    name(scene, extra, 'Retained extra title')
    saved = attach(scene, extra, parent)
    before = {file['id']: manual_fields(item(scene, file)) for file in (parent, extra)}
    journal = manual_state(scene)
    refresh_title(scene, 'Partially observed server title')
    endpoint = '/library/metadata/9' if scene.provider == 'plex' else '/Users/user1/Items/item1'
    original, seen = scene.wire.request, []

    def disconnected(path, **kwargs):
        if path == endpoint:
            seen.append(path)
            if len(seen) == fail_page:
                raise PanError('PAN_NETWORK_UNAVAILABLE')
        return original(path, **kwargs)

    scene.wire.request = disconnected
    try:
        job = scan(scene, state='failed')
    finally:
        scene.wire.request = original
    assert len(seen) == fail_page
    assert job['counts']['pages'] == fail_page - 1
    assert job['counts']['discovered'] == 20 * (fail_page - 1)
    assert manual_state(scene) == journal
    assert {file['id']: manual_fields(item(scene, file)) for file in (parent, extra)} == before
    assert all(item(scene, file)['available'] for file in (parent, extra))
    assert item(scene, extra)['supplement'] == saved
    assert item(scene, extra)['candidates'][-1]['description']['title'] == 'Server film'
    expected_title = 'Server film' if fail_page == 1 else 'Partially observed server title'
    assert item(scene, parent)['candidates'][-1]['description']['title'] == expected_title
    observation = scene.service.source_observation(scene.expected, scene.directory['id'])
    assert observation['coverage'] == 'partial' and observation['recheck_required']
    assert observation['indexed_count'] == 21
    assert all(item(scene, file)['available'] for file in refs)
    # The same owner can re-enumerate after reconnection; no direct SQL repair.
    scan(scene)
    assert manual_state(scene) == journal and item(scene, extra)['supplement'] == saved
    assert item(scene, extra)['candidates'][-1]['description']['title'] == 'Partially observed server title'
