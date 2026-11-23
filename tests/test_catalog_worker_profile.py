"""One worker's profile fence covers all ports without reversing owner locks."""
from threading import Event, Lock, get_ident

import pytest

from bobbi_core.media_library_index import MediaIndex
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.network_sources import NetworkPort
from bobbi_platform.scan_sources import LocalPort, MountedPort, NativePort
from test_catalog_service import Pans, file
from test_media_library_index import scope
from test_network_catalog_source import Upstream


@pytest.mark.parametrize('kind', ['native', 'mounted_path', 'local_path', 'network_path'])
def test_blocked_page_profile_switch_preserves_media_and_permanently_revokes_worker(tmp_path, monkeypatch, kind):
    root = tmp_path / 'A'
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'Movie.mkv').write_bytes(b'video')
    expected = scope()
    native_rows, upstream = [file(1)], Upstream()
    pans = Pans(expected, lambda *args: dict(items=list(native_rows), has_more=False))
    active, host_lock, checks = ['A'], Lock(), []
    service = None
    class OwnedLock:
        def __init__(self):
            self.lock, self.owner = Lock(), None
        def __enter__(self):
            self.lock.acquire()
            self.owner = get_ident()
        def __exit__(self, *unused):
            self.owner = None
            self.lock.release()
    def profile_current():
        # Composition may acquire a Host lock. It must never be invoked with
        # catalog's owner lock held (which would invert the Host->catalog order).
        assert service.lock.owner != get_ident(), 'profile callback ran under catalog lock'
        assert not pans.accounts.lock._is_owned(), 'profile callback ran under native account lock'
        with host_lock:
            checks.append(active[0])
            return active[0] == 'A'
    service = CatalogService(root, pans, profile_current=profile_current)
    service.lock = OwnedLock()
    other = MediaIndex(tmp_path / 'B' / 'media-index.sqlite3')
    store = Registry(root / 'libraries.sqlite3')
    if kind == 'native':
        source_id = store.save_directory('Native', expected, 'root')['id']
        start = lambda: service.start_scan(expected, source_id)
        port_type = NativePort
    else:
        source = vfs_source('Registered', 'smb://nas/Movies/' if kind == 'network_path' else media.as_posix())
        store.save(source)
        source_id = source.id
        if kind == 'network_path':
            port = NetworkPort(root, fetch=upstream)
            service.mounted.network_port = port
        elif kind == 'local_path':
            port = LocalPort(root, mounts=lambda: [])
            service.mounted.local_port = port
        else:
            port = MountedPort(root, mounts=lambda: [dict(path=media.as_posix(), generation='a' * 64)])
            service.mounted.port = port
        port_type = type(port)
        start = lambda: service.start_mounted_scan(service.mounted.authority(source_id, kind))
    store.close()
    entered, release = Event(), Event()
    original = port_type.page
    def page(port, *args, **kwargs):
        reply = original(port, *args, **kwargs)
        entered.set()
        assert release.wait(3), 'test did not release directory response'
        return reply
    def data(index):
        return {table: [tuple(row) for row in index.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in ('objects', 'typed_objects', 'memberships', 'reviews', 'catalog_rows')}
    try:
        task = start()['task_id']
        service.worker.join(3)
        assert not service.worker.is_alive() and service.index._scan(task)['state'] == 'completed'
        before_a, before_b = data(service.index), data(other)
        native_rows.append(file(2))
        (media / 'New.mkv').write_bytes(b'new video')
        upstream.tree[''].append(('New.mkv', False, 100, '2026-01-02T03:04:05Z'))
        monkeypatch.setattr(port_type, 'page', page)
        task = start()['task_id']
        assert entered.wait(2)
        active[0] = 'B'
        release.set()
        service.worker.join(3)
        assert not service.worker.is_alive()
        job = service.index._scan(task)
        assert (job['state'], job['reason']) == ('interrupted', 'PROFILE_CHANGED')
        assert service.profile_revoked.is_set() and service.cancel_event.is_set()
        assert data(service.index) == before_a and data(other) == before_b
        active[0] = 'A'
        with pytest.raises(ValueError, match='CATALOG_PROFILE_CHANGED'):
            start()
        assert checks[-1] == 'B'  # Permanent latch does not reconsult/revive A.
        assert data(service.index) == before_a and data(other) == before_b
    finally:
        release.set()
        service.close()
        other.close()


def test_host_injects_the_existing_profile_fence_and_fails_new_scan_admission(tmp_path, monkeypatch):
    active = [True]
    host = Host(tmp_path, profile_current=lambda: active[0])
    pans = Pans(scope(), lambda *args: dict(items=[], has_more=False))
    monkeypatch.setattr(host, '_pans', lambda: pans)
    catalog = host._catalog()
    try:
        assert catalog.profile_current.__self__ is host
        active[0] = False
        with pytest.raises(ValueError, match='CATALOG_PROFILE_CHANGED'):
            catalog.start_scan(scope(), 'a' * 32)
        assert host.profile_revoked and host.stopping.is_set()
        active[0] = True
        with pytest.raises(ValueError, match='CATALOG_PROFILE_CHANGED'):
            catalog.start_scan(scope(), 'a' * 32)
        assert catalog.worker is None
    finally:
        catalog.close()
