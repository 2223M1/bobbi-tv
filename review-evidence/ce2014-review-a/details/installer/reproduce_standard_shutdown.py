#!/usr/bin/env python3
"""Prove whether installer exclusion covers an admitted standard history write.

The candidate Host, Runtime, KodiHost, StandardPlayback, HistoryWriter and
set_watched_file are imported and executed. Only Kodi extension IO and the final
database persistence boundary are controlled. The shutdown call order is the
candidate portable_runtime.main finally order (standard.close; host.close).
Kodi Disabled acknowledgement is asynchronous, as recorded in PRIMARY-SOURCES.
Requires sibling reproduce_install_lifecycle.py for Kodi extension-only doubles.
No source, device, account or external network mutation occurs.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

from reproduce_install_lifecycle import bootstrap_paths, kodi_import_io, PROVIDER, REFERENCE


def probe(repo, directory, blocked):
    bootstrap_paths(repo)
    kodi_import_io(repo, directory, PROVIDER)
    sys.modules['xbmc'].getSupportedMedia = lambda kind: '.mkv|.mp4'
    from bobbi_platform import ce_install_ui as ui
    from bobbi_platform.host import Host
    from bobbi_platform.instance_lock import InstanceLock
    from lib.services.standard_playback import StandardPlayback
    utility = importlib.import_module('lib.utils.general.utils')
    original_database, original_rpc, original_profile = utility.pickle_db, ui.rpc, ui.profile
    entered, release = threading.Event(), threading.Event()
    if not blocked:
        release.set()
    writes, errors = [], []
    state = dict(enabled=True, installer_returned=False, shutdown_completed=False)

    class DatabaseIO:
        def set_item(self, key, subkey, value):
            entered.set()
            if not release.wait(8):
                raise TimeoutError('review database IO fixture not released')
            record = dict(key=key, subkey=subkey, value=deepcopy(value),
                          after_installer_quiesce=state['installer_returned'])
            writes.append(record)
            (directory / 'observed-history-io.json').write_text(json.dumps(writes))
            return True

    utility.pickle_db = DatabaseIO()
    host = Host(directory)
    host.start()
    standard = StandardPlayback(host)
    closer = None
    installer = ui.KodiHost.__new__(ui.KodiHost)
    installer.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
    installer.monitor = SimpleNamespace(waitForAbort=lambda delay: bool(time.sleep(min(delay, .01))))
    ui.profile = lambda **_: directory / 'runtime.json'

    def shutdown():
        try:
            # The two actual methods are called in portable_runtime.main's
            # product order, including HistoryWriter's real join deadline.
            standard.close()
            host.close()
            state['shutdown_completed'] = True
        except BaseException as error:
            errors.append(type(error).__name__ + ': ' + str(error))

    def rpc(method, params):
        nonlocal closer
        if method == 'Settings.GetSettingValue':
            return {'value': 'skin.estuary'}
        if method == 'Addons.GetAddonDetails':
            return {'addon': dict(enabled=state['enabled'] if params['addonid'] == PROVIDER else False,
                                  version='1.0.0')}
        if method == 'Addons.SetAddonEnabled':
            if params['addonid'] == PROVIDER and not params['enabled']:
                state['enabled'] = False
                if closer is None:
                    closer = threading.Thread(target=shutdown, name='review-kodi-disabled-event')
                    closer.start()
            return 'OK'
        raise AssertionError(method)

    ui.rpc = rpc
    try:
        first = dict(title='Review episode', type='', current_time=42,
                     terminal_reason='STARTED', review_item=1)
        second = dict(first, current_time=100, terminal_reason='NATURAL_EOF', review_item=2)
        standard.history.save(first)
        standard.history.save(second)
        if not entered.wait(3):
            raise RuntimeError('Real HistoryWriter did not reach the controlled persistence boundary')
        if not blocked:
            deadline = time.monotonic() + 3
            while len(writes) < 2 and time.monotonic() < deadline:
                time.sleep(.01)
            if len(writes) != 2:
                raise RuntimeError('Positive control did not complete both admitted writes')
        before = InstanceLock(str(directory / 'runtime.json') + '.lock')
        try:
            before.acquire()
            initially_exclusive = False
        except OSError:
            initially_exclusive = True
        finally:
            before.close()
        started = time.monotonic()
        try:
            installer.quiesce()
            state['installer_returned'] = True
            quiesce_error = None
        except (OSError, ValueError, RuntimeError) as error:
            quiesce_error = str(error)
        elapsed = time.monotonic() - started
        worker_alive_at_return = standard.history.worker.is_alive()
        acquired_by_installer = getattr(installer, '_runtime_lease', None) is not None
        # Keep the installer's real OS lease held while releasing old IO.
        # Any recorded write now is provably after replacement permission.
        release.set()
        standard.history.worker.join(3)
        if closer is not None:
            closer.join(3)
        actual = dict(initial_owner_lease_exclusive=initially_exclusive,
                      quiesce_error=quiesce_error,
                      elapsed_seconds=round(elapsed, 4),
                      installer_holds_runtime_lease=acquired_by_installer,
                      history_worker_alive_at_quiesce_return=worker_alive_at_return,
                      old_writes_after_quiesce=sum(row['after_installer_quiesce'] for row in writes),
                      writes=writes, errors=errors, **state)
        passed = (initially_exclusive and quiesce_error is None and acquired_by_installer
                  and not worker_alive_at_return and not actual['old_writes_after_quiesce'] and not errors)
        return dict(id='STANDARD-SLOW-HISTORY-QUIESCE' if blocked else 'CONTROL-STANDARD-DRAINED-HISTORY',
                    passed=passed,
                    expected='installer replacement permission follows all admitted history writes, with normal drained shutdown still succeeding',
                    actual=actual)
    finally:
        release.set()
        if closer is not None:
            closer.join(3)
        standard.close()
        standard.history.worker.join(3)
        host.close()
        installer.close()
        utility.pickle_db, ui.rpc, ui.profile = original_database, original_rpc, original_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    with tempfile.TemporaryDirectory(prefix='bobbi-pr3-standard-shutdown-') as temporary:
        tests = []
        for blocked in (True, False):
            directory = Path(temporary) / ('slow' if blocked else 'drained')
            directory.mkdir()
            tests.append(probe(repo, directory, blocked))
    sources = [
        'addons/plugin.video.bobbi/lib/portable_runtime.py',
        'addons/plugin.video.bobbi/lib/services/standard_playback.py',
        'addons/plugin.video.bobbi/lib/utils/general/utils.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/host.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py',
    ]
    result = dict(reference_head=REFERENCE,
                  scope='Actual candidate standard/history/installer/Host/Runtime methods; Kodi and database IO doubles only; no device certification or demonstrated corruption',
                  count=len(tests), passed=sum(row['passed'] for row in tests),
                  failed=sum(not row['passed'] for row in tests), tests=tests,
                  sources=[dict(path=path, sha256=hashlib.sha256((repo/path).read_bytes()).hexdigest()) for path in sources])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
