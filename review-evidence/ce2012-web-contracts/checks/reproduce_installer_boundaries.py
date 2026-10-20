"""Behavioral counterexamples against a supplied Bobbi source tree.

The installer, KodiHost activation/quiesce, service.py, boot gate and Runtime
are the candidate's actual modules. Only Kodi's API/scheduling boundary and
wall clock are controlled. No network service on the user's device is touched.
Run: python reproduce_installer_boundaries.py --repo /path/to/bobbi-tv
Exit 1 means at least one required recovery/startup behavior is still broken.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import uuid
import xml.etree.ElementTree as ET


def probe(repo):
    platform = repo / 'addons/script.module.bobbi.platform/lib'
    plugin = repo / 'addons/plugin.video.bobbi'
    sys.path.insert(0, str(platform))
    from bobbi_platform.ce_installer import Installer, MANAGED
    from bobbi_platform.instance_lock import InstanceLock
    import bobbi_platform.ce_install_ui as ui
    import bobbi_platform.runtime as local_runtime

    results = []
    with tempfile.TemporaryDirectory(prefix='bobbi-install-review-') as folder:
        root = Path(folder)
        addons, work = root / 'addons', root / 'work'
        addons.mkdir(); work.mkdir()
        transaction = uuid.uuid4().hex
        (work / transaction / 'stage').mkdir(parents=True)
        (work / transaction / 'backup').mkdir()
        versions = {name: '1.0.0' for name in sorted(MANAGED)}
        state = dict(schema=1, phase='activation_pending', tx=transaction,
                     sequence=2, high_watermark=2,
                     items=[dict(id=n, had_old=True) for n in sorted(MANAGED)],
                     enabled=sorted(MANAGED), versions=versions,
                     previous_skin='skin.estuary')
        enabled, events = set(), []
        journal = work / 'installation.json'
        fake_xbmc = SimpleNamespace(getCondVisibility=lambda _: False,
                                    log=lambda *_: None, LOGINFO=1)
        fake_vfs = SimpleNamespace(translatePath=lambda _: str(journal))
        package = ModuleType('lib'); package.__path__ = [str(plugin / 'lib')]
        runtime = ModuleType('lib.portable_runtime')
        runtime.main = lambda *_: events.append('host_started')
        caps = ModuleType('bobbi_platform.capabilities')
        caps.probe = lambda *_: {'standard_playback': True}
        modules = {'xbmc': fake_xbmc, 'xbmcvfs': fake_vfs, 'lib': package,
                   'lib.portable_runtime': runtime,
                   'bobbi_platform.capabilities': caps}
        def rpc(method, params):
            if method != 'Addons.SetAddonEnabled':
                raise AssertionError(method)
            name = params['addonid']
            if params['enabled']:
                enabled.add(name)
                if name == 'plugin.video.bobbi':
                    events.append('enable_provider')
                    # A valid Kodi schedule: service evaluates its boot gate
                    # before SetAddonEnabled's caller finalizes the journal.
                    try:
                        runpy.run_path(str(plugin / 'service.py'), run_name='__main__')
                    except SystemExit as error:
                        events.append('service_exit:' + str(error.code))
            else:
                enabled.discard(name)
            return 'OK'
        host = ui.KodiHost.__new__(ui.KodiHost)
        # Candidate added an actual owner-thread readiness read. This fixture's
        # service entry records host_started instead of running a Kodi loop;
        # wire that same IO boundary to readiness, never fake enabled => ready.
        host.xbmc = fake_xbmc
        host.monitor = SimpleNamespace(waitForAbort=lambda _: False)
        def readiness(*args, **kwargs):
            if 'host_started' not in events:
                raise OSError('fixture host not running')
            return {'boot_id': 'fixture-running', 'desired': None}
        host.details = lambda name: dict(version='1.0.0', enabled=name in enabled)
        host.refresh = lambda: None
        host.verify = lambda _: None
        host.skin = lambda: 'skin.estuary'
        actor = Installer(addons, work, host, trust={'test': 'already-verified-boundary'})
        actor._write(state)
        with patch.dict(sys.modules, modules), patch.object(ui, 'rpc', rpc), patch.object(local_runtime, 'call', readiness):
            sys.modules.pop('lib.boot_gate', None)
            actor._activate(state)
            # Reopening is the advertised recovery, and it must not leave a
            # falsely complete, enabled-but-never-running service.
            reopening_recovered = actor.recover()
        results.append(dict(
            id='INSTALL-BOOT-GATE',
            expected='provider starts while its verified activation is pending, or reopening repairs it',
            actual=dict(events=list(events), phase=actor._read()['phase'],
                        provider_enabled='plugin.video.bobbi' in enabled,
                        reopening_recovered=reopening_recovered),
            passed='host_started' in events))

        # Also cover the deterministic reboot form: the process was lost after
        # Kodi enabled the provider but before the complete journal was saved.
        state['phase'] = 'activation_pending'
        actor._write(state)
        events.clear()
        with patch.dict(sys.modules, modules), patch.object(ui, 'rpc', rpc), patch.object(local_runtime, 'call', readiness):
            sys.modules.pop('lib.boot_gate', None)
            try:
                runpy.run_path(str(plugin / 'service.py'), run_name='__main__')
            except SystemExit as error:
                events.append('reboot_service_exit:' + str(error.code))
            resumed = actor.recover()
        results.append(dict(
            id='INSTALL-BOOT-AFTER-ENABLED-PROCESS-LOSS',
            expected='an already-enabled provider runs after reboot plus pending-activation recovery',
            actual=dict(events=list(events), phase=actor._read()['phase'],
                        provider_enabled='plugin.video.bobbi' in enabled,
                        reopening_recovered=resumed),
            passed='host_started' in events))

        for phase in ('staged', 'switching', 'restoring'):
            state['phase'] = phase
            actor._write(state)
            events.clear()
            with patch.dict(sys.modules, modules), patch.object(ui, 'rpc', rpc):
                sys.modules.pop('lib.boot_gate', None)
                try:
                    runpy.run_path(str(plugin / 'service.py'), run_name='__main__')
                except SystemExit as error:
                    events.append('service_exit:' + str(error.code))
            results.append(dict(id='CONTROL-BLOCK-' + phase.upper(),
                expected='unverified file vector cannot start the provider',
                actual=dict(phase=phase, events=list(events)),
                passed='host_started' not in events))

        state.update(phase='restored', host_pending='restore')
        actor._write(state)
        events.clear()
        with patch.dict(sys.modules, modules), patch.object(ui, 'rpc', rpc):
            sys.modules.pop('lib.boot_gate', None)
            runpy.run_path(str(plugin / 'service.py'), run_name='__main__')
        compatible_old_gate = actor._read()['phase'] in ('complete', 'restored')
        results.append(dict(id='CONTROL-RESTORED-HOST-PENDING',
            expected='verified restored files satisfy both the old gate and the actual service gate',
            actual=dict(events=list(events), old_gate=compatible_old_gate,
                        host_pending=actor._read().get('host_pending')),
            passed='host_started' in events and compatible_old_gate))

        state.pop('host_pending')
        state['phase'] = 'activation_pending'
        enabled.clear()
        actor._write(state)
        noop_error = None
        with patch.object(ui, 'rpc', lambda *_: 'OK'):
            try:
                actor._activate(state)
            except RuntimeError as error:
                noop_error = str(error)
        results.append(dict(id='CONTROL-NOOP-ENABLE',
            expected='an acknowledged but ineffective Kodi enable cannot complete the installation',
            actual=dict(error=noop_error, phase=actor._read()['phase']),
            passed=bool(noop_error) and actor._read()['phase'] == 'activation_pending'))

    with tempfile.TemporaryDirectory(prefix='bobbi-stale-runtime-review-') as folder:
        root = Path(folder)
        runtime_path = root / 'platform/runtime.json'
        child = """import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from bobbi_platform.runtime import Runtime
actor = Runtime(lambda action, body: {}, Path(sys.argv[2]))
actor.start()
os._exit(73)
"""
        killed = subprocess.run([sys.executable, '-I', '-B', '-c', child,
                                 str(platform), str(runtime_path)],
                                capture_output=True, text=True, timeout=10)
        if killed.returncode != 73:
            raise RuntimeError('Runtime child fixture failed: ' + killed.stderr)
        lease = InstanceLock(str(runtime_path) + '.lock')
        lease.acquire()  # The real prior owner is gone, despite the stale JSON.
        lease.close()
        marker_after_kill = runtime_path.exists()
        addons, work = root / 'addons', root / 'work'
        addons.mkdir(); work.mkdir()
        transaction = uuid.uuid4().hex
        (work / transaction / 'stage').mkdir(parents=True)
        (work / transaction / 'backup').mkdir()
        versions = {name: '1.0.0' for name in sorted(MANAGED)}
        state = dict(schema=1, phase='staged', tx=transaction,
                     sequence=2, high_watermark=1,
                     items=[dict(id=n, had_old=True) for n in sorted(MANAGED)],
                     enabled=[], versions=versions, previous_skin='skin.estuary')
        for name in sorted(MANAGED):
            (addons / name).mkdir()
            (addons / name / 'addon.xml').write_text('<addon id="%s" version="1.0.0"/>' % name)
            (work / transaction / 'stage' / name).mkdir()
        host = ui.KodiHost.__new__(ui.KodiHost)
        host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
        host.monitor = SimpleNamespace(waitForAbort=lambda _: False)
        host.skin = lambda: 'skin.estuary'
        host.details = lambda _: {'enabled': False, 'version': '1.0.0'}
        host.refresh = lambda: None
        actor = Installer(addons, work, host, trust={'test': 'already-verified-boundary'})
        actor._write(state)
        attempts = []
        # Only speed up the 15-second timeout; leave the real quiesce logic.
        for _ in range(2):
            clock = iter((0, 16))
            with patch.object(ui, 'profile', lambda **_: runtime_path), \
                    patch.object(ui.time, 'monotonic', lambda: next(clock)):
                try:
                    attempts.append(dict(recovered=actor.recover()))
                except (RuntimeError, OSError) as error:
                    attempts.append(dict(error=str(error)))
        results.append(dict(
            id='INSTALL-STALE-RUNTIME',
            expected='OS-released runtime ownership permits recovery after an actual process loss',
            actual=dict(child_exit=killed.returncode, marker_after_kill=marker_after_kill,
                        exclusive_runtime_lease_available=True, attempts=attempts,
                        phase=actor._read()['phase'], marker_remaining=runtime_path.exists()),
            passed=any(item.get('recovered') for item in attempts)))

        # A separate real living Runtime must remain protected. A timeout or
        # a disabled addon flag does not prove that this owner has stopped.
        live_child = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from bobbi_platform.runtime import Runtime
actor = Runtime(lambda action, body: {}, Path(sys.argv[2]))
actor.start()
print('READY', flush=True)
sys.stdin.readline()
actor.close()
"""
        alive = subprocess.Popen([sys.executable, '-I', '-B', '-c', live_child,
                                  str(platform), str(runtime_path)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            if alive.stdout.readline().strip() != 'READY':
                raise RuntimeError('Live Runtime fixture failed')
            before = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
            lease_busy = False
            lease = InstanceLock(str(runtime_path) + '.lock')
            try:
                lease.acquire()
            except OSError:
                lease_busy = True
            finally:
                lease.close()
            clock = iter((0, 16))
            error_text = None
            with patch.object(ui, 'profile', lambda **_: runtime_path), \
                    patch.object(ui.time, 'monotonic', lambda: next(clock)):
                try:
                    host.quiesce()
                except (RuntimeError, OSError) as error:
                    error_text = str(error)
            unchanged = runtime_path.is_file() and hashlib.sha256(runtime_path.read_bytes()).hexdigest() == before
            results.append(dict(id='CONTROL-ACTIVE-RUNTIME-OWNER',
                expected='quiesce does not delete the registration or admit replacement while its OS lease is held',
                actual=dict(lease_busy=lease_busy, error=error_text,
                            marker_unchanged=unchanged, process_alive=alive.poll() is None),
                passed=lease_busy and bool(error_text) and unchanged and alive.poll() is None))
        finally:
            try:
                alive.communicate('\n', timeout=10)
            except subprocess.TimeoutExpired:
                alive.kill(); alive.communicate(timeout=10)

    with tempfile.TemporaryDirectory(prefix='bobbi-enable-snapshot-review-') as folder:
        root = Path(folder)
        addons, work = root / 'addons', root / 'work'
        addons.mkdir(); work.mkdir()
        transaction = uuid.uuid4().hex
        (work / transaction / 'stage').mkdir(parents=True)
        (work / transaction / 'backup').mkdir()
        for name in sorted(MANAGED):
            for base, version in ((addons, '1.0.0'), (work / transaction / 'stage', '2.0.0')):
                target = base / name
                target.mkdir()
                (target / 'addon.xml').write_text('<addon id="%s" version="%s"/>' % (name, version))
        enabled = set(MANAGED)
        original_enabled = set(enabled)
        fail_once = [True]
        def rpc_snapshot(method, params):
            if method == 'Addons.GetAddons':
                # Added strict fallback enumeration is also an IO read. The
                # unknown-state contract permits aborting before file moves.
                raise RuntimeError('fixture inventory unavailable')
            if method == 'Addons.GetAddonDetails':
                name = params['addonid']
                if name == 'plugin.video.bobbi' and fail_once[0]:
                    fail_once[0] = False
                    raise RuntimeError('Kodi RPC failed: Addons.GetAddonDetails')
                version = ET.parse(addons / name / 'addon.xml').getroot().get('version')
                return {'addon': dict(enabled=name in enabled, version=version)}
            if method == 'Addons.SetAddonEnabled':
                if params['enabled']: enabled.add(params['addonid'])
                else: enabled.discard(params['addonid'])
                return 'OK'
            if method == 'Settings.GetSettingValue':
                return {'value': 'skin.estuary'}
            raise AssertionError(method)
        host = ui.KodiHost.__new__(ui.KodiHost)
        host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
        host.monitor = SimpleNamespace(waitForAbort=lambda _: False)
        host.refresh = lambda: None
        actor = Installer(addons, work, host, trust={'test': 'already-verified-boundary'})
        snapshot_error = None
        with patch.object(ui, 'rpc', rpc_snapshot), \
                patch.object(ui, 'profile', lambda **_: root / 'absent-runtime.json'):
            try:
                # Exactly the pre-change host.enabled() expression in apply.
                snapshot = host.enabled()
            except RuntimeError as error:
                snapshot_error = str(error)
                snapshot = None
            if snapshot is not None:
                state = dict(schema=1, phase='activation_pending', tx=transaction,
                    sequence=2, high_watermark=2,
                    items=[dict(id=n, had_old=True) for n in sorted(MANAGED)],
                    enabled=snapshot, versions={n: '2.0.0' for n in sorted(MANAGED)},
                    previous_skin='skin.estuary')
                host.quiesce()
                # Continue the exact verified-file boundary in apply. The
                # signature/parser is outside this state-snapshot regression.
                for name in sorted(MANAGED):
                    os.replace(addons / name, work / transaction / 'backup' / name)
                    os.replace(work / transaction / 'stage' / name, addons / name)
                actor._write(state)
                actor._activate(state)
                actor.rollback()
        results.append(dict(id='INSTALL-ENABLE-SNAPSHOT-UNKNOWN',
            expected='transient state-read error aborts snapshot capture or preserves the original enable vector',
            actual=dict(snapshot_error=snapshot_error,
                        originally_enabled_provider='plugin.video.bobbi' in original_enabled,
                        saved_enabled_provider=snapshot is not None and 'plugin.video.bobbi' in snapshot,
                        final_enabled_provider='plugin.video.bobbi' in enabled,
                        all_old_files_restored=all(ET.parse(addons / n / 'addon.xml').getroot().get('version') == '1.0.0'
                                                   for n in MANAGED),
                        phase=actor._read()['phase'] if actor._read() else None),
            passed=bool(snapshot_error) or enabled == original_enabled))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = probe(args.repo.resolve())
    document = dict(schema=1, cases=results, passed=sum(r['passed'] for r in results),
                    failed=sum(not r['passed'] for r in results))
    raw = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    print(raw, end='')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding='utf-8')
    return 1 if document['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
