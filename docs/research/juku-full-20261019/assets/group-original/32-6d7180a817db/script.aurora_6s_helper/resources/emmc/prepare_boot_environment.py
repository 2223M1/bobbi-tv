#!/usr/bin/env python3
"""Offline review of an eMMC boot environment change. Never calls fw_setenv."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from aurora_emmc import plan

BOOTCMD = ('if test ${bootfromnand} = 1; then setenv bootfromnand 0; saveenv; '
           'else run bootfromsd; run bootfromusb; run bootfromemmc; fi; run storeboot')
SCAN_PREFIX = 'for p in '
SCAN_SUFFIX = ('; do if fatload mmc 1:${p} ${loadaddr} cfgload; then setenv device mmc; '
               'setenv devnr 1; setenv partnr ${p}; setenv ce_on_emmc "yes"; '
               'autoscr ${loadaddr}; fi; done;')


def scan_through(last):
    return SCAN_PREFIX + ' '.join(format(i, 'X') for i in range(1, last + 1)) + SCAN_SUFFIX


def prepare(report, environment, mode='reset-data'):
    candidate = plan(report, 20, 1024, mode, 16)
    keys = ('bootcmd', 'cfgloademmc', 'bootfromemmc', 'storeboot', 'bootfromnand', 'active_slot')
    env = {}
    for line in environment.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key not in keys:
            continue
        if key in env:
            raise ValueError('Duplicate environment key: ' + key)
        env[key] = value
    if set(env) != set(keys):
        raise ValueError('Required original boot environment entries missing')
    if env['bootcmd'] != BOOTCMD or env['bootfromemmc'] != 'run cfgloademmc':
        raise ValueError('Unknown external/Android boot selection logic')
    if env['cfgloademmc'] != scan_through(24):
        raise ValueError('Unrecognized eMMC boot scanner; explicit review required')
    if env['bootfromnand'] != '0' or env['active_slot'] not in ('_a', '_b'):
        raise ValueError('Unexpected pending Android selection or slot')
    # This is not an interpreter for arbitrary vendor boot scripts.
    if 'get_valid_slot' not in env['storeboot'] or 'imgread kernel ${boot_part}' not in env['storeboot']:
        raise ValueError('Unrecognized Android A/B boot entry')
    for key in ('bootcmd', 'cfgloademmc', 'active_slot'):
        observed = report['boot_environment'][key]
        if observed['returncode'] or observed['stdout'] != key + '=' + env[key]:
            raise ValueError('Saved environment differs from probe: ' + key)
    target = next(p['index'] for p in candidate['partitions'] if p['name'] == 'ce_system')
    after = scan_through(target)
    return dict(schema=1, installation_ready=False, writes_performed=False,
                source_mpt_sha256=report['mpt_sha256'],
                source_android_dtb_sha256=report['android_dtb_sha256'],
                original_environment_sha256=hashlib.sha256(environment.encode()).hexdigest(),
                mode=mode, ce_system_partition=target, uboot_partition_hex=format(target, 'X'),
                mutations=[dict(key='cfgloademmc', expected_before=env['cfgloademmc'], after=after,
                                rollback=env['cfgloademmc'])],
                unchanged={k: v for k, v in env.items() if k != 'cfgloademmc'},
                notes=[
                    'Review artifact only: no device commands are executed.',
                    'Apply only after new partition geometry and CE files pass readback checks.',
                    'Compare live environment with expected_before and unchanged entries before applying.',
                    'USB/SD priority and the existing bootfromnand Android selection branch are retained.',
                    'Android selection and internal CE boot have not been tested with this layout.',
                    'CE cfgload replaces bootargs and DTB in RAM; fallback after a failed internal CE boot is not guaranteed.',
                    'Use stock cfgload plus config.ini rootopt; recheck target update script compatibility.',
                    'Restoring this environment value does not restore partition metadata or user data.'
                ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('environment', type=Path)
    parser.add_argument('--mode', choices=('reset-data', 'preserve-offset'), default='reset-data')
    args = parser.parse_args()
    try:
        result = prepare(json.loads(args.report.read_text()), args.environment.read_text(), args.mode)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, 'Refused: ' + str(exc) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
