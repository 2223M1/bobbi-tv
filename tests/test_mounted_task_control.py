"""Saved CD2 task control survives offline/remount without file authority.

Uses the real CatalogService, SQLite, worker and local filesystem. Kernel mount
evidence is synthetic; this is not a live CD2/CoreELEC verification claim.
"""
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.scan_sources import MountedSession
from test_scan_source_ports import cd2, mounted_ui, movie, prepare, scan
from test_library_plugin import plugin


@pytest.fixture
def paused_scan(cd2, monkeypatch):
    service, source, _, _ = cd2
    entered, release = Event(), Event()
    original = MountedSession.list_page

    def paused(session, parent):
        entered.set()
        assert release.wait(5), 'Test failed to release its directory boundary'
        return original(session, parent)

    monkeypatch.setattr(MountedSession, 'list_page', paused)
    task = service.dispatch('catalog_mount_scan', dict(source_id=source.id))['task_id']
    assert entered.wait(5)
    try:
        yield task, release
    finally:
        release.set()
        service.worker.join(5)
        assert not service.worker.is_alive()


@pytest.mark.parametrize('change', ['offline', 'remount'])
def test_saved_task_stays_observable_and_cancellable_after_mount_changes(cd2, paused_scan, change):
    service, source, _, mounts = cd2
    task, release = paused_scan
    if change == 'offline':
        mounts.clear()
    else:
        mounts[0]['generation'] = 'b' * 64
    row = service.dispatch('catalog_mount_jobs', dict(source_id=source.id, task=task))['items'][0]
    assert row['state'] == 'running' and row['cancel_requested'] is False
    listed = service.dispatch('catalog_mount_sources', {})['items']
    assert len(listed) == 1 and listed[0]['id'] == source.id
    assert listed[0]['available'] is (change != 'offline')
    receipt = service.dispatch('catalog_mount_cancel', dict(source_id=source.id, task_id=task))
    assert receipt['state'] == 'running' and receipt['cancel_requested'] is True
    assert service.cancel_event.is_set() and service.operation.cancelled.is_set()
    release.set()
    service.worker.join(5)
    assert not service.worker.is_alive()
    row = service.dispatch('catalog_mount_jobs', dict(source_id=source.id, task=task))['items'][0]
    assert row['state'] == 'canceled'


def test_another_registered_source_cannot_observe_or_cancel_the_task(cd2, paused_scan):
    service, _, media, _ = cd2
    task, _ = paused_scan
    other = vfs_source('Other source', (media / 'different-root').as_posix())
    registry = Registry(service.root / 'libraries.sqlite3')
    registry.save(other)
    registry.close()
    assert service.dispatch('catalog_mount_jobs', dict(source_id=other.id)) == dict(items=[], next_offset=None)
    for action, key in [('catalog_mount_jobs', 'task'), ('catalog_mount_cancel', 'task_id')]:
        with pytest.raises(ValueError, match='CATALOG_ACCOUNT_MISMATCH'):
            service.dispatch(action, dict(source_id=other.id, **{key: task}))
    assert not service.cancel_event.is_set()
    assert not service.index._scan(task)['cancel_requested']


@pytest.mark.parametrize('change', ['removed', 'root_rebound'])
def test_removed_or_rebound_registration_does_not_inherit_old_task_control(cd2, paused_scan, change):
    service, source, media, mounts = cd2
    task, _ = paused_scan
    registry = Registry(service.root / 'libraries.sqlite3')
    if change == 'removed':
        registry.remove(source.id)
    else:
        registry.save(vfs_source('Changed root', (media / 'elsewhere').as_posix(), source_id=source.id))
    registry.close()
    mounts.clear()
    assert service.dispatch('catalog_mount_sources', {}) == dict(items=[])
    if change == 'root_rebound':
        assert service.dispatch('catalog_mount_jobs', dict(source_id=source.id)) == dict(items=[], next_offset=None)
    for action, key in [('catalog_mount_jobs', 'task'), ('catalog_mount_cancel', 'task_id')]:
        with pytest.raises(ValueError, match='SOURCE_NOT_FOUND' if change == 'removed' else 'CATALOG_ACCOUNT_MISMATCH'):
            service.dispatch(action, dict(source_id=source.id, **{key: task}))
    assert not service.cancel_event.is_set()
    assert not service.index._scan(task)['cancel_requested']


def test_offline_descriptions_and_tasks_never_authorize_scans_or_playback(cd2):
    service, source, _, mounts = cd2
    completed = scan(cd2)
    selected = movie(cd2)['entity_id']
    unclaimed = prepare(cd2, selected)['ticket']
    claimed = prepare(cd2, selected)['ticket']
    service.dispatch('catalog_mount_claim', dict(ticket=claimed))
    mounts.clear()
    assert service.dispatch('catalog_mount_jobs', dict(source_id=source.id))['items'][0]['task_id'] == completed['task_id']
    rows = service.dispatch('catalog_mount_query', dict(source_id=source.id))['items']
    assert rows and all(row['availability'] == 'source_unavailable' for row in rows)
    for action, body in [
        ('catalog_mount_scan', dict(source_id=source.id)),
        ('catalog_mount_prepare', dict(source_id=source.id, object_id=selected, request_id='c' * 32, intent='play')),
        ('catalog_mount_claim', dict(ticket=unclaimed)),
        ('catalog_mount_verify', dict(source_id=source.id, object_id=selected, request_id=claimed)),
    ]:
        with pytest.raises(ValueError, match='CATALOG_SOURCE_UNAVAILABLE'):
            service.dispatch(action, body)
    assert not service.cancel_event.is_set()
    unchanged = service.dispatch('catalog_mount_cancel', dict(source_id=source.id, task_id=completed['task_id']))
    assert unchanged['state'] == 'completed' and unchanged['cancel_requested'] is False
    assert not service.cancel_event.is_set()  # Completed task cannot cancel a later worker.


def test_offline_root_reaches_jobs_and_pending_cancel_is_truthful(cd2, mounted_ui, paused_scan, monkeypatch):
    service, source, _, mounts = cd2
    task, _ = paused_scan
    mounts.clear()
    ui = mounted_ui.plugin
    mounted_ui.catalog.execute({}, 17, mounted_ui.dispatch)
    task_rows = [row for row in ui.rows if dict(parse_qsl(urlsplit(row[0]).query)).get('mode') == 'jobs']
    assert len(task_rows) == 1
    target, item, _ = task_rows[0]
    assert dict(parse_qsl(urlsplit(target).query)) == dict(
        action='personal_catalog_manage', source=source.id, mode='jobs')
    assert '无需读取挂载目录' in item.label2
    service.dispatch('catalog_mount_cancel', dict(source_id=source.id, task_id=task))
    from bobbi_platform import catalog_ui
    labels = []
    monkeypatch.setattr(catalog_ui, 'call', mounted_ui.dispatch)
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(
        select=lambda title, rows: labels.extend(rows) or -1,
        ok=lambda *args: pytest.fail('Expected readable persisted task')))
    mounted_ui.catalog.manage(dict(parse_qsl(urlsplit(target).query)), mounted_ui.dispatch)
    assert any('扫描中' in label and ('正在取消' in label or '等待后台确认' in label) for label in labels)


def test_kernel_mounted_but_unreadable_source_has_direct_root_task_route(cd2, mounted_ui, paused_scan, monkeypatch):
    service, source, _, mounts = cd2
    task, _ = paused_scan
    assert mounts  # The kernel still lists this mount while its IO is pending.
    ui = mounted_ui.plugin
    with monkeypatch.context() as patch:
        patch.setattr(service.mounted.port, 'describe',
                      lambda *_: pytest.fail('Root/task navigation must not probe the unreadable mount'))
        mounted_ui.catalog.execute({}, 17, mounted_ui.dispatch)
        routes = [dict(parse_qsl(urlsplit(row[0]).query)) for row in ui.rows]
        assert dict(action='personal_catalog', source=source.id) in routes
        assert dict(action='personal_catalog_manage', source=source.id, mode='jobs') in routes
        from bobbi_platform import catalog_ui
        patch.setattr(catalog_ui, 'call', mounted_ui.dispatch)
        patch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(
            select=lambda *args: -1, ok=lambda *args: pytest.fail('Expected available task control')))
        mounted_ui.catalog.manage(dict(source=source.id, mode='cancel', task=task), mounted_ui.dispatch)
        assert service.cancel_event.is_set()
        assert service.index._scan(task)['state'] == 'running'


def _timely(action, release):
    """A failed lock regression releases the synthetic IO before failing."""
    result, done = {}, Event()

    def run():
        try:
            result['value'] = action()
        except BaseException as error:
            result['error'] = error
        finally:
            done.set()

    thread = Thread(target=run, daemon=True)
    thread.start()
    timely = done.wait(1)
    if not timely:
        release.set()
    thread.join(5)
    assert timely, 'Task control waited for a blocked mount operation'
    if 'error' in result:
        raise result['error']
    return result['value']


@pytest.mark.parametrize('boundary', ['batch', 'finish'])
def test_blocked_mount_validation_never_holds_task_lock_or_claims_instant_cancellation(cd2, monkeypatch, boundary):
    service, source, media, _ = cd2
    # A one-directory real scan gives deterministic publication boundaries.
    (media / 'Season 0' / 'Show.S00E01.mkv').unlink()
    (media / 'Season 0').rmdir()
    armed, entered, release = Event(), Event(), Event()
    describe = service.mounted.port.describe

    def blocked(source_id):
        if armed.is_set():
            entered.set()
            assert release.wait(5), 'Test did not release mount stat'
        return describe(source_id)

    monkeypatch.setattr(service.mounted.port, 'describe', blocked)
    if boundary == 'batch':
        original = MountedSession.list_page

        def arm(session, parent):
            value = original(session, parent)
            armed.set()
            return value

        monkeypatch.setattr(MountedSession, 'list_page', arm)
    else:
        original = service.index.mounted_batch

        def arm(*args, **kwargs):
            value = original(*args, **kwargs)
            armed.set()
            return value

        monkeypatch.setattr(service.index, 'mounted_batch', arm)
    task = service.dispatch('catalog_mount_scan', dict(source_id=source.id))['task_id']
    try:
        assert entered.wait(5)
        root = _timely(lambda: service.dispatch('catalog_mount_sources', {}), release)
        assert root['items'][0]['id'] == source.id
        job = _timely(lambda: service.dispatch('catalog_mount_jobs', dict(source_id=source.id, task=task)), release)
        assert job['items'][0]['state'] == 'running'
        receipt = _timely(lambda: service.dispatch('catalog_mount_cancel', dict(source_id=source.id, task_id=task)), release)
        assert receipt['state'] == 'running' and receipt['cancel_requested']
        assert service.worker.is_alive()  # The blocked OS call was not killed.
        assert service.index._scan(task)['state'] == 'running'
        release.set()
        service.worker.join(5)
        assert not service.worker.is_alive()
        assert service.index._scan(task)['state'] == 'canceled'
        count = service.index.db.execute('SELECT count(*) FROM typed_objects').fetchone()[0]
        assert count == (0 if boundary == 'batch' else 1)
    finally:
        release.set()
        service.worker.join(5)


def test_blocked_play_validation_does_not_prevent_jobs_or_its_own_cancel(cd2, monkeypatch):
    service, source, _, _ = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    armed, entered, release = Event(), Event(), Event()
    original_stat, original_describe = service.mounted.port.stat_by_reference, service.mounted.port.describe

    def stat_then_arm(*args, **kwargs):
        value = original_stat(*args, **kwargs)
        armed.set()
        return value

    def blocked(source_id):
        if armed.is_set():
            entered.set()
            assert release.wait(5)
        return original_describe(source_id)

    monkeypatch.setattr(service.mounted.port, 'stat_by_reference', stat_then_arm)
    monkeypatch.setattr(service.mounted.port, 'describe', blocked)
    outcomes, request = {}, 'e' * 32

    def prepare_in_thread():
        try:
            outcomes['value'] = prepare(cd2, selected, request)
        except ValueError as error:
            outcomes['error'] = str(error)

    worker = Thread(target=prepare_in_thread, daemon=True)
    worker.start()
    try:
        assert entered.wait(5)
        jobs = _timely(lambda: service.dispatch('catalog_mount_jobs', dict(source_id=source.id)), release)
        assert jobs['items'][0]['state'] == 'completed'
        result = _timely(lambda: service.dispatch('catalog_mount_cancel_play', dict(source_id=source.id, request_id=request)), release)
        assert result == dict(cancelled=True)
        assert worker.is_alive()
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert outcomes == dict(error='CATALOG_SCAN_STOPPED')
        assert not service.mounted.tickets and not service.mounted.claims
    finally:
        release.set()
        worker.join(5)
