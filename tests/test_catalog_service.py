from contextlib import contextmanager
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from types import SimpleNamespace
import json
import sys
import time
import tracemalloc

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform import catalog_service as module
from bobbi_platform.libraries import Registry
from test_media_library_index import scope, ref, insert


class Accounts:
    def __init__(self, expected):
        self.expected, self.lock = expected, RLock()
    def require_current(self, expected):
        if not self.is_current(expected):
            raise ValueError('ACCOUNT_CHANGED')
        return dict(expected)
    def is_current(self, expected):
        return expected == self.expected
    def run_if_current(self, expected, operation):
        with self.lock:
            self.require_current(expected)
            return operation()


class Pans:
    def __init__(self, expected, listing):
        self.accounts, self.listing, self.calls = Accounts(expected), listing, []
    @contextmanager
    def scan_operation(self, expected, operation_id, **budget):
        cancelled = Event()
        def check():
            self.accounts.require_current(expected)
            if cancelled.is_set():
                raise ValueError('CANCELED')
        op = SimpleNamespace(check=check, cancelled=cancelled, pages=0, items=0, budget=budget)
        yield op
    def list_for_scan(self, expected, parent, page, cursor, *, operation, size):
        assert size == 20
        operation.check()
        if operation.pages >= operation.budget['max_pages']:
            raise ValueError('PAN_BUDGET_EXHAUSTED')
        self.calls.append((parent, page, cursor))
        result = self.listing(parent, page, cursor)
        operation.pages += 1
        operation.items += len(result['items'])
        if operation.items > operation.budget['max_items']:
            raise ValueError('PAN_BUDGET_EXHAUSTED')
        return result


def file(i):
    return dict(directory=False, file_id=str(i), name='Show.S01E%05d.mkv' % i, size=1024)


def folder(i, path=None):
    return dict(directory=True, file_id=str(i), name='Folder ' + str(i), path=path or str(i))


def service(tmp_path, listing, expected=None):
    expected = expected or scope()
    store = Registry(tmp_path / 'libraries.sqlite3')
    source = store.save_directory('Test', expected, 'root')
    store.close()
    return CatalogService(tmp_path, Pans(expected, listing)), source['id'], expected


def wait(service):
    service.worker.join(30)
    assert not service.worker.is_alive()
    return service.index.jobs(service.pans.accounts.expected, task=service.task)['items'][0]


def test_synthetic_10k_multilevel_scan_is_bounded_and_queryable(tmp_path):
    def listing(parent, page, cursor):
        if parent == 'root':
            return dict(items=[folder('branch%d' % i) for i in range(10)], has_more=False)
        if parent.startswith('branch'):
            branch = int(parent[6:])
            return dict(items=[folder('leaf%d' % (branch * 10 + i)) for i in range(10)], has_more=False)
        leaf = int(parent[4:])
        return dict(items=[file(leaf * 100 + (page - 1) * 20 + i + 1) for i in range(20)], has_more=page < 5)
    svc, source, expected = service(tmp_path, listing)
    tracemalloc.start()
    began = time.monotonic()
    try:
        svc.start_scan(expected, source)
        job = wait(svc)
        elapsed = time.monotonic() - began
        peak = tracemalloc.get_traced_memory()[1]
        query = time.monotonic()
        result = svc.dispatch('catalog_items', dict(expected=expected, source=source))
        query_elapsed = time.monotonic() - query
        assert job['state'] == 'completed' and job['counts']['discovered'] == 10000
        assert job['counts']['scanned'] == 10110 and job['counts']['pages'] == 511
        assert svc.max_queue <= 100 and peak < 32 * 1024**2
        assert query_elapsed < .25 and len(result['items']) == 5
        print('SCAN_BENCHMARK ' + json.dumps(dict(files=10000, pages=511, elapsed_seconds=elapsed,
            peak_bytes=peak, max_queue=svc.max_queue, query_seconds=query_elapsed)))
    finally:
        tracemalloc.stop()
        svc.close()


@pytest.mark.parametrize('fault', ['third_page', 'cycle', 'cursor', 'limit', 'empty', 'invalid'])
def test_incomplete_scan_preserves_old_members(tmp_path, monkeypatch, fault):
    def listing(parent, page, cursor):
        if fault == 'third_page' and page == 3:
            raise OSError('upstream secret never returned')
        if fault == 'empty':
            return dict(items=[], has_more=True)
        if fault == 'invalid':
            return dict(items=[dict(file(1), size=0)], has_more=False)
        return dict(items=[file(1 if fault == 'cycle' else page)], has_more=True,
                    **({'next_cursor': 'same'} if fault == 'cursor' else {}))
    if fault == 'limit':
        monkeypatch.setattr(module, 'MAX_PAGES', 2)
    svc, source, expected = service(tmp_path, listing)
    try:
        insert(svc.index, [ref(999)], source, expected)
        svc.start_scan(expected, source)
        job = wait(svc)
        assert job['state'] == 'failed'
        assert 'secret' not in json.dumps(job)
        assert svc.index.db.execute('SELECT available FROM memberships WHERE file=?', (ref(999)['id'],)).fetchone()[0] == 1
    finally:
        svc.close()


@pytest.mark.parametrize('event', ['cancel', 'switch', 'shutdown'])
def test_late_reply_after_cancel_or_revoke_cannot_commit(tmp_path, event):
    entered, release = Event(), Event()
    def listing(parent, page, cursor):
        entered.set()
        assert release.wait(3)
        return dict(items=[file(1)], has_more=False)
    svc, source, expected = service(tmp_path, listing)
    try:
        task = svc.start_scan(expected, source)['task_id']
        assert entered.wait(1)
        if event == 'cancel':
            result = svc.dispatch('catalog_cancel', dict(expected=expected, task_id=task))
            assert result['state'] == 'running' and result['cancel_requested']
        elif event == 'switch':
            svc.pans.accounts.expected = scope('b', epoch=2)
        else:
            svc.stop.set()
            svc.cancel_event.set()
        release.set()
        svc.worker.join(3)
        assert not svc.worker.is_alive()
        assert svc.index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 0
        assert svc.index._scan(task)['state'] == ('canceled' if event == 'cancel' else 'interrupted')
    finally:
        release.set()
        svc.close()


def test_depth_limit_does_not_publish_full_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_DEPTH', 1)
    svc, source, expected = service(tmp_path, lambda parent, page, cursor:
        dict(items=[folder(parent + '-child')], has_more=False))
    try:
        svc.start_scan(expected, source)
        assert wait(svc)['result_summary'] == 'SCAN_DIRECTORY_LIMIT'
    finally:
        svc.close()


def test_baidu_uses_provider_parent_path_not_file_id(tmp_path):
    def listing(parent, page, cursor):
        return dict(items=[folder('101', '/movies')] if parent == 'root' else [file(1)], has_more=False)
    svc, source, expected = service(tmp_path, listing, scope(provider='baidu'))
    try:
        svc.start_scan(expected, source)
        assert wait(svc)['state'] == 'completed'
        assert [row[0] for row in svc.pans.calls] == ['root', '/movies']
    finally:
        svc.close()


def test_host_drains_scanner_before_provider_and_retains_lease_on_failure(tmp_path):
    from bobbi_platform.host import Host
    order = []
    host = Host(tmp_path)
    host.start()
    class Scanner:
        def close(self):
            order.append('scanner')
            if len(order) == 1:
                raise RuntimeError('CATALOG_DRAIN_PENDING')
    host.catalog = Scanner()
    host.pans = SimpleNamespace(close=lambda: order.append('pans'))
    try:
        with pytest.raises(RuntimeError, match='DRAIN_PENDING'):
            host.close()
        assert order[:2] == ['scanner', 'pans']
        assert not getattr(host, '_shutdown_complete', False)
        host.close()
        assert host._shutdown_complete
    finally:
        host.close()


def test_registry_extension_keeps_old_sources_and_no_account_secrets(tmp_path):
    from bobbi_platform.libraries import vfs_source
    registry = Registry(tmp_path / 'libraries.sqlite3')
    try:
        old = vfs_source('Original', '/media/')
        registry.save(old)
        expected = scope()
        first = registry.save_directory('Directory', expected, 'parent')
        second = registry.save_directory('Renamed', dict(expected, epoch=2), 'parent')
        assert first['id'] == second['id'] and registry.sources() == (old,)
        assert len(registry.directories()) == 1 and 'epoch' not in json.dumps(registry.directories())
    finally:
        registry.close()


def test_removed_source_recovery_preserves_file_metadata(tmp_path):
    svc, source, expected = service(tmp_path, lambda *args: dict(items=[file(1)], has_more=False))
    svc.start_scan(expected, source)
    assert wait(svc)['state'] == 'completed'
    # Simulate process loss just after the existing source registry commits.
    registry = Registry(tmp_path / 'libraries.sqlite3')
    registry.remove_directory(source)
    registry.close()
    svc.close()
    recovered = CatalogService(tmp_path, Pans(expected, lambda *args: None))
    try:
        assert recovered.index.items(expected)['items'][0]['available'] is False
        assert len(recovered.index.items(expected)['items']) == 1
    finally:
        recovered.close()


def test_remove_uses_existing_registry_and_keeps_objects(tmp_path):
    svc, source, expected = service(tmp_path, lambda *args: dict(items=[file(1)], has_more=False))
    try:
        svc.start_scan(expected, source)
        assert wait(svc)['state'] == 'completed'
        assert svc.dispatch('catalog_remove', dict(expected=expected, source_id=source)) == dict(removed=True)
        assert svc.dispatch('catalog_sources', dict(expected=expected)) == dict(items=[])
        assert svc.index.items(expected)['items'][0]['available'] is False
    finally:
        svc.close()


def test_failed_worker_launch_is_terminal_and_does_not_poison_queue(tmp_path, monkeypatch):
    svc, source, expected = service(tmp_path, lambda *args: dict(items=[], has_more=False))
    thread = module.Thread
    try:
        monkeypatch.setattr(module, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: (_ for _ in ()).throw(RuntimeError('no thread'))))
        with pytest.raises(RuntimeError, match='WORKER_UNAVAILABLE'):
            svc.start_scan(expected, source)
        result = svc.index.jobs(expected)['items'][0]
        assert result['state'] == 'failed' and result['result_summary'] == 'WORKER_START_FAILED'
        assert svc.worker is None
        monkeypatch.setattr(module, 'Thread', thread)
        svc.start_scan(expected, source)
        assert wait(svc)['state'] == 'completed'
    finally:
        svc.close()


def test_source_removal_cannot_race_scan_admission(tmp_path, monkeypatch):
    captured, allow_start, listing_started, allow_reply, removed = (Event() for _ in range(5))
    def listing(*args):
        listing_started.set()
        assert allow_reply.wait(3)
        return dict(items=[], has_more=False)
    svc, source, expected = service(tmp_path, listing)
    original, failures = svc._source, []
    def capture(*args):
        result = original(*args)
        if current_thread().name == 'test-admission':
            captured.set()
            assert allow_start.wait(3)
        return result
    monkeypatch.setattr(svc, '_source', capture)
    def remove():
        try:
            svc.dispatch('catalog_remove', dict(expected=expected, source_id=source))
        except ValueError as error:
            failures.append(str(error))
        finally:
            removed.set()
    starter = Thread(target=lambda: svc.start_scan(expected, source), name='test-admission')
    remover = Thread(target=remove)
    try:
        starter.start()
        assert captured.wait(1)
        remover.start()
        assert not removed.wait(.05)
        allow_start.set()
        starter.join(1)
        assert listing_started.wait(1)
        remover.join(1)
        assert failures == ['CATALOG_SCAN_BUSY']
        assert svc.dispatch('catalog_sources', dict(expected=expected))['items']
    finally:
        allow_start.set()
        allow_reply.set()
        starter.join(3)
        if remover.ident is not None:
            remover.join(3)
        svc.close()
