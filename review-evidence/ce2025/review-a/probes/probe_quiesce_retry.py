#!/usr/bin/env python3
"""Read-only historical fault-injection diagnostic, not a future CI gate.

Requires --repo ABSOLUTE_PATH to a trusted checkout/export. No project edits,
no bytecode writes, no device or external network connections. Only actual
product modules plus the documented Kodi/IO/clock boundary doubles are used;
the quiesce probe creates a disposable temporary marker and real OS lock.

--source-ref is an optional unverified caller label. Actual input SHA-256
values are emitted. stdout is JSON. Exit 1 = target defect reproduced;
0 = not reproduced within this narrow scope, not release certification;
2 = environment or source interface incompatible.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import threading
import types
from types import SimpleNamespace

sys.dont_write_bytecode = True
SOURCE_PATHS = (
    "addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/host.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/instance_lock.py",
)


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(dict(status='incompatible', error=message, exit_code=2)))
        raise SystemExit(2)


def run_probe(repo):
    ROOT = repo
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
    from bobbi_platform import ce_install_ui as ui, runtime
    from bobbi_platform.instance_lock import InstanceLock

    clock = [0.0]
    events = []
    original_monotonic = ui.time.monotonic
    ui.time.monotonic = lambda: clock[0]

    with tempfile.TemporaryDirectory(prefix='ce2024-quiesce-retry-') as temp:
        path = Path(temp) / 'runtime.json'
        path.write_text('{}')
        owner = InstanceLock(str(path) + '.lock')
        owner.acquire()
        enabled = [True]
        actor = ui.KodiHost.__new__(ui.KodiHost)
        actor.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
        actor.skin = lambda: 'skin.estuary'
        actor.monitor = SimpleNamespace(waitForAbort=lambda seconds: clock.__setitem__(0, clock[0]+seconds) or False)
        ui.profile = lambda **kw: path

        def call(action, body, **kwargs):
            events.append(action)
            if action == 'status':
                return {'quiesce_protocol': 1}
            if action == 'quiesce':
                # Runtime.close removes this marker before Host.close drains the
                # admitted playback/other work and releases the process lease.
                path.unlink()
                return {'accepted': True}
            raise AssertionError(action)

        def rpc(method, params):
            if method == 'Addons.GetAddonDetails':
                return {'addon': {'enabled': enabled[0] if params['addonid']=='plugin.video.bobbi' else False,
                                  'version': '1'}}
            if method == 'Addons.SetAddonEnabled':
                events.append({'disable_requested_while_owner_lease_held': owner.fd is not None,
                               'addonid': params['addonid'], 'enabled': params['enabled']})
                enabled[0] = params['enabled']
                return 'OK'
            raise AssertionError(method)

        runtime.call = call
        ui.rpc = rpc
        observations = []
        try:
            for attempt in (1, 2):
                error = None
                try:
                    actor.quiesce()
                except ui.UpdateError as failure:
                    error = str(failure)
                observations.append(dict(attempt=attempt, error=error,
                                         runtime_marker_exists=path.exists(),
                                         owner_lease_held=owner.fd is not None,
                                         addon_enabled=enabled[0], events=list(events)))
        finally:
            actor.close()
            owner.close()
            ui.time.monotonic = original_monotonic

    return dict(observations=observations,
                defect_reproduced=(observations[0]['addon_enabled'] is True
                                   and observations[1]['addon_enabled'] is False
                                   and observations[1]['owner_lease_held']))


def main():
    parser = JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, type=Path, help='Absolute read-only source checkout/export')
    parser.add_argument('--source-ref', help='Unverified caller-declared source label')
    args = parser.parse_args()
    result = dict(purpose='historical_fault_injection_not_ci_gate',
                  declared_source_ref=args.source_ref, source_ref_verified=False,
                  source_root=str(args.repo), source_sha256={})
    try:
        if not args.repo.is_absolute():
            raise ValueError('--repo must be an absolute path')
        repo = args.repo.resolve(strict=True)
        if not repo.is_dir():
            raise ValueError('--repo must be a directory')
        result['source_root'] = str(repo)
        for name in SOURCE_PATHS:
            result['source_sha256'][name] = hashlib.sha256((repo/name).read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            result.update(run_probe(repo))
        code = 1 if result['defect_reproduced'] else 0
        result['status'] = 'target_defect_reproduced' if code else 'not_reproduced_in_scope'
    except Exception as error:
        code = 2
        result.update(status='incompatible', error_type=type(error).__name__, error=str(error))
    result['exit_code'] = code
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
