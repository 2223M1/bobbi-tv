"""Read-only acceptance test. Run on the opted-in CoreELEC box on a glass surface."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def check(seconds=8):
    storage = Path('/storage')
    addons = storage / '.kodi/addons'
    sys.path.insert(0, str(addons / 'script.module.bobbi.platform/lib'))
    from bobbi_platform import ce_glass_boot as boot, ce_glass_host as host
    state = storage / '.local/share/bobbi-private-updates/state.json'
    journal = storage / '.kodi/userdata/addon_data/script.bobbi.start/installation.json'
    opted = boot.opted_in(storage / '.kodi/userdata')
    release = boot._release(state, journal)
    result = dict(opted_in=opted, sequence=(release or {}).get('sequence'), passed=False)
    pids = subprocess.run(['pidof', 'kodi.bin'], capture_output=True, text=True).stdout.split()
    if len(pids) != 1 or not opted:
        return dict(result, reason='KODI_PID_OR_OPT_IN')
    pid = int(pids[0])
    executable = Path('/proc', str(pid), 'exe').resolve(strict=True)
    qualified = boot.verified_module(state, addons, executable, installation=journal) == addons / boot.PACKAGED_FILE
    if not qualified:
        return dict(result, reason='INSTALL_TUPLE_OR_MATERIALS_NOT_VERIFIED')
    stats_path = boot.RUNTIME / 'stats.json'
    identity = None
    first_swaps = None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        sample = host.inspect_runtime_status(opted_in=True, is_coreelec=True, host_available=True,
            owned_86_present=False, storage=storage, pid=pid, cjk=False)
        result.update(state=sample['state'], reason=sample['detail'])
        if sample['state'] == 'live_active':
            marker = (sample['pid'], sample['starttime_ticks'])
            if identity is not None and identity != marker:
                return dict(result, reason='KODI_PROCESS_CHANGED')
            identity = marker
            try:
                data = json.loads(stats_path.read_bytes())
            except (OSError, ValueError):
                continue
            swaps = data.get('total_swaps')
            if (type(swaps) is not int or data.get('enabled') != 1 or
                    not (data.get('glass_quads_last_frame') or 0) > 0):
                continue
            if first_swaps is None:
                first_swaps = swaps
            result.update(quads=data['glass_quads_last_frame'], tags=sample['tags_registered'],
                          blur_runs=data.get('blur_runs'), swap_delta=swaps-first_swaps)
            if swaps > first_swaps:
                return dict(result, passed=True)
        time.sleep(.25)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, choices=range(2,31), default=8, metavar='2..30')
    result = check(parser.parse_args().seconds)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)
