#!/usr/bin/env python3
"""Diagnose three historical lifecycle defects in an explicitly chosen checkout.

This is a frozen-old-source diagnostic, NOT a future CI or release acceptance
gate. It imports complete Host/Runtime/InstanceLock/StandardPlayback modules;
only Kodi's Player and the slow history-storage boundary are substituted.

Usage:
    python probe_lifecycle.py --repo /absolute/path/to/checkout
    python probe_lifecycle.py --repo /path/to/checkout --expected-head FULL_SHA
    python probe_lifecycle.py --repo /path/to/export --source-label old-export

No project source is edited. Python bytecode writes are disabled. Runtime
profiles and locks are created in temporary directories outside the checkout.
The real Runtime needs permission to listen on 127.0.0.1. No Kodi/device,
external network service, or existing user profile is contacted.

stdout contains JSON. Exit 1 = at least one historical defect observed;
exit 2 = environment, source identity, or interface incompatible; exit 0 =
these probes did not reproduce a defect, NOT certification of repaired code.
The JSON revision comes from the requested checkout and/or a declared label,
never from a hard-coded reviewed HEAD. A label alone is not verified identity.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import types

sys.dont_write_bytecode = True

SOURCE_PATHS = (
    'addons/script.module.bobbi.platform/lib/bobbi_platform/host.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/instance_lock.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/account_manager.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/cloud115.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/paths.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/playback.py',
    'addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py',
    'addons/plugin.video.bobbi/lib/services/standard_playback.py',
)


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'status': 'incompatible', 'error': message,
                          'exit_code': 2}, ensure_ascii=False))
        raise SystemExit(2)


def provenance(repo, expected_head, label):
    hashes = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
              for name in SOURCE_PATHS}
    result = dict(git_head=None, source_label=label, expected_head=expected_head,
                  expected_head_verified=False, tracked_probe_sources_modified=None,
                  source_sha256=hashes)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')

    def git(*args):
        value = subprocess.run(['git', '-C', str(repo), *args], env=env,
                               capture_output=True, text=True, timeout=10)
        return value.stdout.strip() if value.returncode == 0 else None

    try:
        top = git('rev-parse', '--show-toplevel')
        # An exported tree under an unrelated parent repository is not that
        # parent repository's HEAD. Do not attach its identity to these files.
        if top and Path(top).resolve() == repo:
            result['git_head'] = git('rev-parse', 'HEAD')
            changed = git('diff', '--no-ext-diff', '--name-only', 'HEAD', '--',
                          *SOURCE_PATHS)
            if changed is not None:
                result['tracked_probe_sources_modified'] = bool(changed)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if expected_head:
        if not re.fullmatch(r'[0-9a-fA-F]{40}', expected_head):
            raise ValueError('--expected-head requires a full 40-character SHA')
        if result['git_head'] != expected_head.lower():
            raise ValueError('Requested HEAD cannot be verified or does not match; '
                             'for an export omit --expected-head and use --source-label')
        if result['tracked_probe_sources_modified'] is not False:
            raise ValueError('Probe source files differ from HEAD or their status is unknown')
        result['expected_head_verified'] = True
    return result


def run_probes(repo, results):
    sys.path[:0] = [str(repo / 'addons/script.module.bobbi.platform/lib'),
                   str(repo / 'addons/plugin.video.bobbi')]
    from bobbi_platform.host import Host
    from bobbi_platform.instance_lock import InstanceLock

    xbmc = types.ModuleType('xbmc')
    xbmc.Player = type('Player', (), {})
    sys.modules['xbmc'] = xbmc
    from lib.services.standard_playback import StandardPlayback, HistoryWriter

    def can_acquire(path):
        contender = InstanceLock(str(path / 'runtime.json') + '.lock')
        try:
            contender.acquire()
        except OSError:
            return False
        else:
            contender.close()
            return True

    def release_local_host(host):
        # Cleanup after recording observations, including incompatible inputs.
        # This is only the disposable local host created by this diagnostic.
        try:
            host.runtime.close()
        finally:
            host.runtime.lease.close()

    with tempfile.TemporaryDirectory(prefix='ce2021-host-probe-') as temp:
        root = Path(temp)
        host = Host(root)
        try:
            host.start()
            cleanup = []

            def image_failure():
                cleanup.append('images')
                raise RuntimeError('injected image shutdown failure')

            host.images = types.SimpleNamespace(close=image_failure)
            host.streams = types.SimpleNamespace(close=lambda: cleanup.append('streams'))
            first_error = None
            try:
                host.close()
            except RuntimeError as error:
                first_error = str(error)
            lease_free = can_acquire(root)
            host.close()
            results.append(dict(case='host_failure_skips_cleanup_and_releases_lease',
                                first_error=first_error, cleanup_calls=cleanup,
                                lease_free_after_failure=lease_free,
                                retry_cleaned_streams='streams' in cleanup,
                                defect_reproduced=lease_free and 'streams' not in cleanup))
        finally:
            release_local_host(host)

    entered, release = threading.Event(), threading.Event()
    storage = types.ModuleType('lib.utils.general.utils')

    def slow_save(data):
        entered.set()
        if not release.wait(5):
            raise TimeoutError('probe timed out')

    storage.set_watched_file = slow_save
    sys.modules['lib.utils.general.utils'] = storage
    with tempfile.TemporaryDirectory(prefix='ce2021-history-probe-') as temp:
        root = Path(temp)
        host = Host(root)
        standard = None
        try:
            host.start()
            standard = StandardPlayback(host)
            standard.history.save({'probe': True})
            if not entered.wait(2):
                raise RuntimeError('history probe did not enter storage')
            standard.close()
            worker_alive = standard.history.worker.is_alive()
            host.close()
            lease_free = can_acquire(root)
            results.append(dict(case='standard_history_outlives_host_lease',
                                history_worker_alive_after_standard_close=worker_alive,
                                lease_free_while_history_worker_alive=lease_free,
                                defect_reproduced=worker_alive and lease_free))
        finally:
            release.set()
            if standard is not None:
                standard.history.worker.join(2)
            release_local_host(host)

    writer = HistoryWriter(lambda code: None)
    try:
        writer.close()
        writer.save({'accepted_after_close': True})
        results.append(dict(case='history_accepts_after_close',
                            worker_alive=writer.worker.is_alive(),
                            queued_after_close=writer.queue.qsize(),
                            defect_reproduced=(not writer.worker.is_alive()
                                               and writer.queue.qsize() == 1)))
    finally:
        writer.done.set()
        writer.worker.join(2)


def main():
    parser = JsonParser(description=__doc__,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, type=Path,
                        help='Explicit source checkout/export root; never edited')
    parser.add_argument('--expected-head', help='Verify full HEAD SHA and clean probe files')
    parser.add_argument('--source-label', help='Declared export label; not independently verified')
    args = parser.parse_args()
    result = dict(purpose='historical_defect_probe_not_ci_gate',
                  source_root=str(args.repo.resolve()), revision=None, probes=[],
                  interpretation='Exit 0 does not certify repaired code or a release')
    try:
        repo = args.repo.resolve(strict=True)
        if not repo.is_dir():
            raise ValueError('--repo must be a directory')
        result['revision'] = provenance(repo, args.expected_head, args.source_label)
        # Keep stdout machine-readable even if an imported source prints logs.
        with contextlib.redirect_stdout(io.StringIO()):
            run_probes(repo, result['probes'])
        code = 1 if any(row['defect_reproduced'] for row in result['probes']) else 0
        result['status'] = 'historical_defect_observed' if code else 'not_reproduced'
    except Exception as error:
        code = 2
        result.update(status='incompatible', error_type=type(error).__name__,
                      error=str(error))
    result['exit_code'] = code
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
