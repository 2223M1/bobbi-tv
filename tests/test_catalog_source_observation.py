"""Source observation is descriptive; unchanged scans do not rewrite the view."""
import pytest

from test_media_library_index import scope, ref, insert
from test_scan_source_ports import cd2, scan, query, movie
from test_catalog_service import service as native_service, wait
from bobbi_core import mounted_ref
from bobbi_core.media_library_index import MediaIndex, encode, REPLY_BYTES
from bobbi_platform.catalog_service import source_list


def test_unchanged_native_scan_preserves_cursor_revision_and_edited_order(tmp_path):
    with_index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        index = with_index
        tick = [100]
        index.now = lambda: tick[0]
        files = [ref(i) for i in range(4)]
        insert(index, files)
        first = index.query(scope(), query={'sort': 'recent_edited'}, limit=2)
        before = [tuple(row) for row in index.db.execute('SELECT * FROM object_times ORDER BY file')]
        tick[0] += 60
        task = insert(index, files)
        assert index.scope_revision(scope()) == first['projection_revision']
        assert [tuple(row) for row in index.db.execute('SELECT * FROM object_times ORDER BY file')] == before
        assert index.query(scope(), query={'sort': 'recent_edited'}, cursor=first['next_cursor'], limit=2)['items']
        assert index._scan(task)['discovered'] == 4
    finally:
        with_index.close()


def test_unchanged_empty_scan_and_already_absent_membership_do_not_bump_revision(tmp_path):
    index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        insert(index, [])
        assert index.scope_revision(scope()) == 0
        insert(index, [ref()])
        before = index.scope_revision(scope())
        insert(index, [])
        assert index.scope_revision(scope()) == before + 1
        insert(index, [])
        assert index.scope_revision(scope()) == before + 1
    finally:
        index.close()


def test_unchanged_mounted_scan_and_point_keep_revision_but_point_still_fences_old_scan(cd2):
    service, source, _, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    first = query(cd2, limit=1)
    scan(cd2)
    assert query(cd2)['projection_revision'] == first['projection_revision']
    assert query(cd2, cursor=first['next_cursor'], limit=1)['items']
    selected = movie(cd2)['entity_id']
    reference = service.index.trusted_mounted_file(authority, selected)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    service.index.observe_mounted(authority, reference)
    assert service.index.scope_revision(authority) == first['projection_revision']
    assert service.index.db.execute('SELECT task,file FROM temp.scan_point_observations').fetchall()
    service.index.finish(task, 'canceled')


@pytest.mark.parametrize('change', ['rename', 'size', 'parent', 'membership', 'reappearance'])
def test_real_native_observation_change_stales_only_its_account(tmp_path, change):
    index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        files = [ref(i) for i in range(4)]
        other = scope('b')
        insert(index, [ref(i, expected=other) for i in range(3)], source='b' * 32, expected=other)
        insert(index, files)
        if change == 'reappearance':
            insert(index, [])
        own_page = index.query(scope(), limit=1)
        other_page = index.query(other, limit=1)
        changes = {'rename': {'name': 'Changed.mkv'}, 'size': {'size': 2048},
                   'parent': {'parent': 'other-directory'}}
        observed = [dict(files[0], **changes.get(change, {}))] + files[1:]
        insert(index, observed, source='c' * 32 if change == 'membership' else 'a' * 32)
        with pytest.raises(ValueError, match='CURSOR_STALE'):
            index.query(scope(), cursor=own_page['next_cursor'], limit=1)
        assert index.query(other, cursor=other_page['next_cursor'], limit=1)['items']
    finally:
        index.close()


def test_source_observation_distinguishes_full_partial_offline_and_remount(cd2, monkeypatch):
    service, source, media, mounts = cd2
    def observation():
        return service.dispatch('catalog_mount_sources', {})['items'][0]['observation']
    initial = observation()
    assert initial == dict(coverage='never', availability='unverified', recheck_required=True,
        indexed_count=0, latest_state='none', counts=dict(pages=0, scanned=0, discovered=0))
    completed = scan(cd2)
    full = observation()
    assert full['coverage'] == 'complete' and not full['recheck_required']
    assert full['counts'] == completed['counts'] and full['indexed_count'] == 2
    authority = service.mounted.authority(source.id)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    service.index.cancel_mounted(task, source.id, authority['namespace'])
    requested = observation()
    assert requested['latest_state'] == 'cancel_requested' and requested['coverage'] == 'partial'
    assert service.index._scan(task)['state'] == 'running'
    service.index.finish(task, 'canceled', 'CANCEL_CONFIRMED')
    assert observation()['latest_state'] == 'canceled'
    assert observation()['indexed_count'] == 2  # Partial scan did not infer absence.
    scan(cd2)
    mounts[0]['generation'] = 'b' * 64
    changed = observation()
    assert changed['coverage'] == 'complete'  # The retained old scan was complete.
    assert changed['availability'] == 'unverified' and changed['recheck_required']
    mounts.clear()
    monkeypatch.setattr(service.mounted.port, 'describe', lambda *_: pytest.fail('No FUSE stat on source cards'))
    offline = observation()
    assert offline['availability'] == 'source_unavailable' and offline['indexed_count'] == 2
    assert offline['recheck_required']


def test_missing_and_reappearing_file_counts_do_not_invent_complete_scan(cd2):
    service, source, media, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    selected = movie(cd2)['entity_id']
    (media / 'Movie.mkv').unlink()
    scan(cd2)
    missing = service.index.source_observation(authority, source.id)
    assert (missing['indexed_count'], missing['present_count'], missing['absent_count']) == (2, 1, 1)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    service.index.finish(task, 'failed', 'CATALOG_RECHECK_INCOMPLETE')
    (media / 'Movie.mkv').write_bytes(b'newly returned movie')
    fresh = mounted_ref.observed(authority, 'Movie.mkv', (media / 'Movie.mkv').stat())
    service.index.observe_mounted(authority, fresh)
    recovered = service.index.source_observation(authority, source.id)
    assert (recovered['present_count'], recovered['absent_count']) == (2, 0)
    assert recovered['coverage'] == 'partial' and recovered['recheck_required']


def test_source_summary_uses_current_scope_and_registry_names(tmp_path):
    service, source, expected = native_service(tmp_path, lambda *_: dict(items=[
        dict(directory=False, file_id='1', name='Movie.mkv', size=100)], has_more=False))
    try:
        service.start_scan(expected, source)
        completed = wait(service)
        row = service.dispatch('catalog_sources', dict(expected=expected))['items'][0]
        assert row['observation']['counts'] == completed['counts']
        assert row['observation']['coverage'] == 'complete'
        result = service.dispatch('catalog_query', dict(expected=expected, query=dict(view='files')))
        assert result['items'][0]['sources'] == [dict(id=source, name='Test')]
        other = scope('b')
        assert service.index.source_observation(other, source)['latest_job'] is None
        assert service.index.source_observation(other, source)['indexed_count'] == 0
    finally:
        service.close()


@pytest.mark.parametrize('name', ['片' * 80, '🎬' * 80, '\\"' * 40])
def test_all_32_source_cards_keep_identity_and_fit_runtime_budget(name):
    rows = [dict(id=('%032x' % i), name=name, reference_kind='mounted_path', device_verified=False,
        available=False, has_jobs=True, has_items=True, observation=dict(coverage='partial',
            availability='source_unavailable', recheck_required=True, latest_state='cancel_requested',
            counts=dict(pages=1200, scanned=12000, discovered=12000), indexed_count=12000)) for i in range(32)]
    result = source_list(rows)
    assert len(encode(result).encode('utf-8')) <= REPLY_BYTES
    assert [row['id'] for row in result['items']] == [row['id'] for row in rows]
    assert all(row['observation'] == rows[0]['observation'] for row in result['items'])
    assert all(row['name'] == name for row in rows)
    if result.get('truncated'):
        assert all(row['name'].endswith('…') for row in result['items'])


def test_source_status_does_not_inherit_a_previous_root_namespace(cd2):
    service, source, media, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    with pytest.raises(ValueError, match='ACCOUNT_MISMATCH'):
        service.index.source_observation(authority, 'e' * 32)
    rebound = dict(authority, namespace='e' * 64)
    result = service.index.source_observation(rebound, source.id)
    assert result['latest_job'] is None and result['indexed_count'] == 0


def test_empty_complete_scan_has_mount_generation_evidence_without_any_file(cd2):
    service, source, media, mounts = cd2
    (media / 'Movie.mkv').unlink()
    (media / 'Season 0' / 'Show.S00E01.mkv').unlink()
    scan(cd2)
    def state():
        return service.dispatch('catalog_mount_sources', {})['items'][0]['observation']
    assert state()['coverage'] == 'complete' and not state()['recheck_required']
    mounts[0]['generation'] = 'b' * 64
    assert state()['availability'] == 'unverified' and state()['recheck_required']
    scan(cd2)
    assert state()['coverage'] == 'complete' and not state()['recheck_required']
