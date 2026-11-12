"""A point recheck outranks an already-started mounted traversal.

Real filesystem/SQLite/worker paths; only kernel mount records are synthetic.
The transient per-scan guard is transactional and never grants file authority.
"""
import sqlite3
from threading import Event
from uuid import uuid4

import pytest

from test_scan_source_ports import cd2, movie, scan
from bobbi_core import mounted_ref


def guards(index):
    return [tuple(row) for row in index.db.execute('SELECT task,file FROM temp.scan_point_observations')]


def point(cd2):
    service, source, media, _ = cd2
    selected = movie(cd2)['entity_id']
    ticket = service.dispatch('catalog_mount_prepare', dict(source_id=source.id, object_id=selected,
        request_id=uuid4().hex, intent='play_from_start'))['ticket']
    return service.dispatch('catalog_mount_claim', dict(ticket=ticket))


@pytest.mark.parametrize('page_state', ['absent', 'older_ref'])
def test_older_scan_cannot_replace_fresh_point_observation(cd2, monkeypatch, page_state):
    service, source, media, _ = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    if page_state == 'absent':
        (media / 'Movie.mkv').unlink()
        scan(cd2)
    generation = service.index.db.execute('SELECT generation FROM memberships WHERE source=? AND file=?',
        (source.id, selected)).fetchone()[0]
    ready, release = Event(), Event()
    port, enumerated = service.mounted.port, set()
    original_page = port.page
    def delayed_page(*args, **kwargs):
        result = original_page(*args, **kwargs)
        enumerated.update(row['reference']['id'] for row in result['items'] if row['reference'])
        if not ready.is_set():
            assert (selected in enumerated) == (page_state == 'older_ref')
            ready.set()
            assert release.wait(5)
        return result
    monkeypatch.setattr(port, 'page', delayed_page)
    task = service.dispatch('catalog_mount_scan', dict(source_id=source.id))['task_id']
    try:
        assert ready.wait(5)
        before = service.index._scan(task)
        (media / 'Movie.mkv').write_bytes(b'new current video, different from the queued page')
        assert point(cd2)['object_id'] == selected
        assert guards(service.index) == [(task, selected)]
        after = service.index._scan(task)
        assert (after['pages'], after['scanned'], after['discovered']) == (
            before['pages'], before['scanned'], before['discovered'])
        assert service.index.db.execute('SELECT generation FROM memberships WHERE source=? AND file=?',
            (source.id, selected)).fetchone()[0] == generation
        fresh = service.index.trusted_mounted_file(service.mounted.authority(source.id), selected)
    finally:
        release.set()
        service.worker.join(5)
    assert not service.worker.is_alive()
    closed = service.index._scan(task)
    assert closed['state'] == 'completed' and closed['discovered'] == len(enumerated)
    assert movie(cd2)['availability'] == 'observed_present'
    assert service.index.trusted_mounted_file(service.mounted.authority(source.id), selected) == fresh
    assert service.index.db.execute('SELECT generation FROM memberships WHERE source=? AND file=?',
        (source.id, selected)).fetchone()[0] == (task if page_state == 'older_ref' else generation)
    assert guards(service.index) == []
    # Protection ends with that scan; a new full traversal can infer absence.
    (media / 'Movie.mkv').unlink()
    scan(cd2)
    assert movie(cd2)['availability'] == 'observed_absent'


@pytest.mark.parametrize('mismatch', ['source_id', 'namespace', 'generation'])
def test_point_guard_never_crosses_source_namespace_or_mount(cd2, mismatch):
    service, source, media, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    other = dict(authority, **{mismatch: 'f' * (32 if mismatch == 'source_id' else 64)})
    task = service.index.start(other['source_id'], other)
    service.index.begin(task)
    reference = mounted_ref.observed(authority, 'Movie.mkv', (media / 'Movie.mkv').stat())
    service.index.observe_mounted(authority, reference)
    assert guards(service.index) == []
    service.index.finish(task, 'failed', 'FIXTURE')


@pytest.mark.parametrize('terminal', ['completed', 'canceled', 'failed', 'interrupted', 'recover'])
def test_point_guard_is_cleared_on_every_terminal_and_recovery(cd2, terminal):
    service, source, media, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    point(cd2)
    assert guards(service.index)
    if terminal == 'recover':
        service.index.recover()
    else:
        service.index.finish(task, terminal)
    assert guards(service.index) == []
    assert not service.index.db.execute("SELECT name FROM sqlite_master WHERE name='scan_point_observations'").fetchall()
    # It is connection-local TEMP state, not a new persistent schema.
    assert service.index.db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_point_guard_and_final_cleanup_rollback_with_their_transactions(cd2):
    service, source, media, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    (media / 'Movie.mkv').write_bytes(b'new observation')
    reference = mounted_ref.observed(authority, 'Movie.mkv', (media / 'Movie.mkv').stat())
    tables = ('memberships', 'typed_objects', 'typed_observations', 'catalog_rows', 'catalog_scope_revisions')
    def snapshot():
        return {table: [tuple(row) for row in service.index.db.execute('SELECT * FROM ' + table)] for table in tables}
    before = snapshot()
    service.index.db.execute("CREATE TRIGGER reject_point BEFORE UPDATE ON catalog_meta BEGIN SELECT RAISE(ABORT,'point fixture'); END")
    with pytest.raises(sqlite3.IntegrityError, match='point fixture'):
        service.index.observe_mounted(authority, reference)
    assert guards(service.index) == [] and snapshot() == before
    service.index.db.execute('DROP TRIGGER reject_point')
    service.index.observe_mounted(authority, reference)
    before = snapshot()
    service.index.db.execute("CREATE TRIGGER reject_finish BEFORE UPDATE ON scans BEGIN SELECT RAISE(ABORT,'finish fixture'); END")
    with pytest.raises(sqlite3.IntegrityError, match='finish fixture'):
        service.index.finish(task, 'completed')
    assert guards(service.index) == [(task, reference['id'])] and snapshot() == before
    assert service.index._scan(task)['state'] == 'running'
    service.index.db.execute('DROP TRIGGER reject_finish')
    service.index.finish(task, 'completed')
    assert guards(service.index) == []


def test_admission_does_not_clear_an_active_scans_point_guard(cd2):
    service, source, _, _ = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    task = service.index.start(source.id, authority)
    service.index.begin(task)
    point(cd2)
    before = guards(service.index)
    with pytest.raises(ValueError, match='SCAN_BUSY'):
        service.index.start(source.id, authority)
    assert guards(service.index) == before
    service.index.finish(task, 'failed', 'FIXTURE')
    next_task = service.index.start(source.id, authority)
    assert guards(service.index) == []
    service.index.finish(next_task, 'canceled')
