"""Real scan/play/control paths must finish under conflicting publication.

Only upstream directory IO is synthetic. Event gates select the problematic
interleavings; a subprocess bounds a regression that would otherwise deadlock
the pytest process and its fixture teardown.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
from threading import Event, Lock, RLock, Thread, current_thread, get_ident
import traceback
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.parametrize('race', ['scan_play', 'play_control'])
def test_publication_finishes_without_lock_cycle(tmp_path, race):
    receipt = tmp_path / 'receipt.json'
    result = subprocess.run([sys.executable, __file__, str(Path(__file__).resolve().parents[1]),
        str(tmp_path), str(receipt), race], capture_output=True, text=True, timeout=15)
    report = json.loads(receipt.read_text()) if receipt.exists() else {}
    assert result.returncode == 0, (result.stdout, result.stderr, report)
    assert not report['blocked'] and not report['errors']
    assert report['ticket_claimed']
    if race == 'scan_play':
        assert report['scan_state'] == 'completed'
    else:
        assert report['control_completed']


def probe(repo, root, receipt, race):
    for path in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib', 'tests'):
        sys.path.insert(0, str(repo / path))
    from bobbi_core.file_ref import from_selected
    from bobbi_platform.catalog_service import CatalogService
    from bobbi_platform.libraries import Registry
    from bobbi_platform.pan_service import PanService
    from bobbi_platform.scan_sources import NativePort
    from test_ce2096_pan_accounts import saved
    from test_media_library_index import insert

    ready, publisher, contender = Event(), Event(), Event()
    armed, errors, answer = [False], [], {}

    class OwnerLock:
        def __init__(self):
            self.lock, self.owner = Lock(), None
        def __enter__(self):
            name = current_thread().name
            if race == 'scan_play' and armed[0] and name == 'bobbi-library-scan':
                contender.set()
            self.lock.acquire()
            self.owner = get_ident()
            if race == 'scan_play' and armed[0] and name == 'point-play':
                publisher.set()
                assert contender.wait(5), 'scan did not reach publication'
            return self
        def __exit__(self, *unused):
            self.owner = None
            self.lock.release()

    class ServiceLock:
        def __init__(self):
            self.lock = RLock()
        def __enter__(self):
            if current_thread().name == 'control':
                # If play already owns this lock, let it finish; otherwise
                # hold the service lock before play requests its ticket.
                acquired = self.lock.acquire(False)
                contender.set()
                if not acquired:
                    self.lock.acquire()
            else:
                self.lock.acquire()
            return self
        def __exit__(self, *unused):
            self.lock.release()

    rows = [dict(file_id='original', name='Movie.mkv', size=100, directory=False)]
    pans = PanService(root, SimpleNamespace(snapshot=lambda: {}))
    expected = pans.accounts.install(saved(), pans.accounts.snapshot('quark'))
    pans.client_factory = lambda *args: SimpleNamespace(list_files=lambda parent, page, size:
        dict(items=[dict(row) for row in rows], page=page, has_more=False))
    registry = Registry(root / 'libraries.sqlite3')
    source = registry.save_directory('Movies', expected, 'folder')
    registry.close()
    catalog = CatalogService(root, pans)
    reference = from_selected(expected, rows[0], 'folder')
    insert(catalog.index, [reference], source['id'], expected)
    catalog.lock = OwnerLock()
    request = uuid4().hex

    def capture(operation):
        try:
            operation()
        except BaseException as error:
            errors.append(repr(error))

    def play():
        answer.update(catalog.dispatch('catalog_prepare_play', dict(expected=expected,
            object_id=reference['id'], request_id=request, intent='play')))

    player = Thread(target=lambda: capture(play), name='point-play', daemon=True)
    if race == 'scan_play':
        original_page = NativePort.page
        def page(self, *args, **kwargs):
            result = original_page(self, *args, **kwargs)
            armed[0] = True
            ready.set()
            assert publisher.wait(5), 'point-play did not reach publication'
            return result
        NativePort.page = page
        catalog.start_scan(expected, source['id'])
        assert ready.wait(5), 'native scan did not return directory IO'
        other = catalog.worker
    else:
        pans.lock = ServiceLock()
        original_cas = pans.accounts.run_if_current
        def account_cas(expected, operation, **kwargs):
            def guarded():
                if catalog.lock.owner == get_ident():
                    publisher.set()
                    assert contender.wait(5), 'control did not request the service lock'
                return operation()
            return original_cas(expected, guarded, **kwargs)
        pans.accounts.run_if_current = account_cas
        def control():
            assert publisher.wait(5), 'point-play did not reach its account CAS'
            answer['control_completed'] = pans.cancel_operation(expected, uuid4().hex)['cancelled']
        other = Thread(target=lambda: capture(control), name='control', daemon=True)
        other.start()
    player.start()
    player.join(5)
    other.join(0 if player.is_alive() else 5)
    blocked = [thread for thread in (other, player) if thread.is_alive()]
    report = dict(race=race, blocked=[thread.name for thread in blocked], errors=errors,
                  fake='provider HTTP directory rows only')
    if blocked:
        frames = sys._current_frames()
        report['stacks'] = {thread.name: traceback.format_stack(frames[thread.ident]) for thread in blocked}
        receipt.write_text(json.dumps(report, indent=2))
        os._exit(1)  # Both threads are daemon; leave no hung test worker.
    report['ticket_claimed'] = pans.claim_play(answer['ticket'])['file_ref'] == reference
    if race == 'scan_play':
        report['scan_state'] = catalog.index._scan(catalog.task)['state']
    else:
        report['control_completed'] = answer['control_completed']
    catalog.close()
    pans.close()
    receipt.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
