"""Local scope/observation boundaries and the single traversal owner.

Real SQLite, registry and filesystem, synthetic mount records; no live provider.
"""
import json
from pathlib import Path
import sqlite3
import sys
from threading import Event
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import catalog_query
from bobbi_core.media_library_index import MediaIndex
from bobbi_platform import catalog_service
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.mounted_catalog import MountedCatalog
from bobbi_platform.scan_sources import MountedSession
from test_media_library_index import scope, ref, insert, command
from test_scan_source_ports import cd2, scan, query, movie, prepare
from test_catalog_service import Pans


def test_unrelated_account_writes_and_source_removal_preserve_cursor_and_group(tmp_path):
    index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        files = [ref(i) for i in range(7)]
        insert(index, files)
        first = index.query(scope(), limit=2)
        group = index.group(scope(), files[0]['id'])
        other = scope('b')
        insert(index, [ref(20, expected=other)], source='b' * 32, expected=other)
        index.retain_sources(['a' * 32])
        second = index.query(scope(), cursor=first['next_cursor'], limit=2)
        assert second['projection_revision'] == first['projection_revision']
        assert len(index.group(scope(), files[0]['id'], offset=5,
            projection_revision=group['projection_revision'])['items']) == 2
        index.apply(scope(), uuid4().hex, [command(files[0], action='ignore')])
        with pytest.raises(ValueError, match='CURSOR_STALE'):
            index.query(scope(), cursor=first['next_cursor'], limit=2)
    finally:
        index.close()


def test_scope_revision_rolls_back_with_failed_batch(tmp_path):
    index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        insert(index, [ref(i) for i in range(3)])
        first = index.query(scope(), limit=1)
        task = index.start('a' * 32, scope())
        index.begin(task)
        index.db.execute("CREATE TRIGGER fail_batch BEFORE UPDATE ON scans BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with pytest.raises(sqlite3.IntegrityError):
            index.batch(task, [ref(9)], {'page': 1}, 1)
        assert index.query(scope(), cursor=first['next_cursor'], limit=1)['items']
        assert index.scope_revision(scope()) == first['projection_revision']
    finally:
        index.close()


def test_cursor_expiry_is_explicit_and_query_can_restart(tmp_path):
    index = MediaIndex(tmp_path / 'index.sqlite3')
    try:
        insert(index, [ref(i) for i in range(3)])
        clock = [1]
        index.query_reader.clock = lambda: clock[0]
        first = index.query(scope(), query={'text': 'Movie'}, limit=1)
        clock[0] += catalog_query.CURSOR_SECONDS
        with pytest.raises(ValueError, match='CURSOR_STALE'):
            index.query(scope(), query={'text': 'Movie'}, cursor=first['next_cursor'], limit=1)
        assert index.query(scope(), query={'text': 'Movie'}, limit=1)['items'] == first['items']
    finally:
        index.close()


def test_projection_upgrade_failure_preserves_original_records_and_retries(tmp_path, monkeypatch):
    path = tmp_path / 'index.sqlite3'
    index = MediaIndex(path)
    insert(index, [ref()])
    index.apply(scope(), uuid4().hex, [command(ref())])
    originals = [tuple(row) for row in index.db.execute('SELECT * FROM objects')]
    reviews = [tuple(row) for row in index.db.execute('SELECT * FROM reviews')]
    index.db.execute('UPDATE catalog_meta SET schema=4')
    index.db.commit()
    index.close()
    with monkeypatch.context() as patch:
        patch.setattr(catalog_query, 'project', lambda *args: (_ for _ in ()).throw(RuntimeError('migration interrupted')))
        with pytest.raises(RuntimeError, match='migration interrupted'):
            MediaIndex(path)
    with sqlite3.connect(path) as old:
        assert old.execute('SELECT * FROM objects').fetchall() == originals
        assert old.execute('SELECT * FROM reviews').fetchall() == reviews
        assert old.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 4
        assert old.execute('PRAGMA user_version').fetchone()[0] == 2
    index = MediaIndex(path)
    try:
        assert index.item(scope(), ref()['id'])['mapping']['title'] == 'Custom'
        assert index.db.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 5
    finally:
        index.close()


def test_typed_review_uses_same_cas_receipts_undo_and_fixed_namespace(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    stable = service.dispatch('catalog_mount_scope', dict(source_id=source.id))
    body = dict(source_id=source.id, namespace=stable['namespace'])
    selected = movie(cd2)['entity_id']
    row = service.dispatch('catalog_mount_item', dict(body, file_id=selected))
    cmd = command(dict(id=selected), title='Edited mounted description')
    request = uuid4().hex
    assert service.dispatch('catalog_mount_preview', dict(body, commands=[cmd]))['items'][0]['status'] == 'ready'
    assert service.dispatch('catalog_mount_apply', dict(body, request_id=request, commands=[cmd]))['items'][0]['status'] == 'applied'
    assert service.dispatch('catalog_mount_receipt', dict(body, request_id=request))['items'][0]['revision'] == 1
    assert service.dispatch('catalog_mount_apply', dict(body, request_id=uuid4().hex, commands=[cmd]))['items'][0]['status'] == 'conflict'
    undo = command(dict(id=selected), revision=1, action='undo')
    assert service.dispatch('catalog_mount_apply', dict(body, request_id=uuid4().hex, commands=[undo]))['items'][0]['status'] == 'applied'
    assert service.dispatch('catalog_mount_item', dict(body, file_id=selected))['mapping'] == row['mapping']
    assert service.index.receipt(scope(), request)['status'] == 'missing'
    assert not service.mounted.tickets
    registry = Registry(service.root / 'libraries.sqlite3')
    registry.save(vfs_source('Rebound', (media / 'different').as_posix(), source_id=source.id))
    registry.close()
    for action, args in [('query', {}), ('item', dict(file_id=selected)), ('preview', dict(commands=[cmd])),
                         ('receipt', dict(request_id=request))]:
        with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
            service.dispatch('catalog_mount_' + action, dict(body, **args))


def test_remount_retains_cards_rejects_old_tickets_and_explicitly_reselects(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    ticket = prepare(cd2, selected)['ticket']
    previous = service.index.trusted_mounted_file(service.mounted.authority(source.id), selected)
    mounts[0]['generation'] = 'b' * 64
    assert movie(cd2)['availability'] == 'unverified'
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.dispatch('catalog_mount_claim', dict(ticket=ticket))
    with pytest.raises(ValueError, match='FILE_CHANGED'):
        prepare(cd2, selected)
    fresh = service.dispatch('catalog_mount_prepare', dict(source_id=source.id,
        object_id=selected, request_id=uuid4().hex, intent='play_from_start'))['ticket']
    result = service.dispatch('catalog_mount_claim', dict(ticket=fresh))
    assert not result['resume_supported']
    assert movie(cd2)['availability'] == 'observed_present'
    history = [json.loads(row[0]) for row in service.index.db.execute('SELECT ref FROM typed_observations WHERE file=?', (selected,))]
    assert previous in history and len(history) == 2


def test_restart_keeps_typed_description_review_and_observation_history(cd2):
    service, source, _, mounts = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    stable = service.dispatch('catalog_mount_scope', dict(source_id=source.id))
    service.index.apply(stable, uuid4().hex, [command(dict(id=selected), title='Kept description')])
    service.close()
    mounts[0]['generation'] = 'c' * 64
    reopened = catalog_service.CatalogService(service.root, Pans(scope(), lambda *_: pytest.fail('native unused')))
    reopened.mounted.port = service.mounted.port
    try:
        rows = reopened.dispatch('catalog_mount_query', dict(source_id=source.id))['items']
        row = next(row for row in rows if row['entity_id'] == selected)
        assert row['display_title'] == 'Kept description' and row['availability'] == 'unverified'
        assert reopened.index.item(stable, selected)['revision'] == 1
        assert reopened.index.db.execute('SELECT count(*) FROM typed_observations WHERE file=?', (selected,)).fetchone()[0] == 1
        with pytest.raises(ValueError, match='FILE_CHANGED'):
            reopened.dispatch('catalog_mount_prepare', dict(source_id=source.id, object_id=selected,
                request_id=uuid4().hex, intent='play'))
    finally:
        reopened.close()


def test_offline_review_never_touches_mount_stat_or_mints_ticket(cd2, monkeypatch):
    service, source, _, mounts = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    mounts.clear()
    monkeypatch.setattr(service.mounted.port, 'describe', lambda *_: pytest.fail('local metadata must not stat FUSE'))
    row = service.dispatch('catalog_mount_item', dict(source_id=source.id, file_id=selected))
    assert row['file']['id'] == selected
    assert query(cd2)['items'][0]['availability'] == 'source_unavailable'
    assert service.dispatch('catalog_mount_apply', dict(source_id=source.id, request_id=uuid4().hex,
        commands=[command(dict(id=selected), action='ignore')]))['items'][0]['status'] == 'applied'
    assert not service.mounted.tickets


def test_offline_cards_outlive_bounded_scan_task_history(cd2):
    service, source, _, mounts = cd2
    scan(cd2)
    service.index.db.execute('DELETE FROM scans')
    service.index.db.commit()
    mounts.clear()
    row = service.dispatch('catalog_mount_sources', {})['items'][0]
    assert row['id'] == source.id and row['has_items'] and not row['has_jobs'] and not row['available']
    assert query(cd2)['items']


def test_only_catalog_service_owns_scan_loop_and_mounted_uses_shared_budget(cd2, monkeypatch):
    service, _, media, _ = cd2
    assert not hasattr(MountedCatalog, 'start') and not hasattr(MountedCatalog, 'scan')
    scan(cd2)
    initial = service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0]
    for i in range(25):
        (media / ('Extra%02d.mkv' % i)).write_bytes(b'video')
    monkeypatch.setattr(catalog_service, 'MAX_PAGES', 1)
    result = scan(cd2)
    assert result['state'] == 'failed' and result['result_summary'] == 'CATALOG_RECHECK_INCOMPLETE'
    assert service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0] >= initial


def test_mounted_and_native_admission_share_single_flight(cd2, monkeypatch):
    service, source, _, _ = cd2
    entered, release = Event(), Event()
    original = MountedSession.list_page
    def blocked(session, parent):
        entered.set()
        assert release.wait(5)
        return original(session, parent)
    monkeypatch.setattr(MountedSession, 'list_page', blocked)
    service.dispatch('catalog_mount_scan', dict(source_id=source.id))
    try:
        assert entered.wait(2)
        with pytest.raises(ValueError, match='SCAN_BUSY'):
            service.start_scan(scope(), 'a' * 32)
    finally:
        release.set()
        service.worker.join(5)


def test_native_inflight_also_blocks_mounted_admission(cd2):
    service, source, _, _ = cd2
    entered, release = Event(), Event()
    def blocked(*_):
        entered.set()
        assert release.wait(5)
        return dict(items=[], has_more=False)
    service.pans.listing = blocked
    registry = Registry(service.root / 'libraries.sqlite3')
    native = registry.save_directory('Native', scope(), 'root')
    registry.close()
    service.start_scan(scope(), native['id'])
    try:
        assert entered.wait(2)
        with pytest.raises(ValueError, match='SCAN_BUSY'):
            service.dispatch('catalog_mount_scan', dict(source_id=source.id))
    finally:
        release.set()
        service.worker.join(5)
