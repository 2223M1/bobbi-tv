"""Prevent an AM6B+ Kodi regression run from powering the TV or switching its input.

Run as root on the CoreELEC 4.9 Amlogic test box. No command opens the CEC adapter
or sends a bus message. The normal family configuration is only ever read.
"""
import argparse
import json
import os
import re
import time
from pathlib import Path
from xml.etree import ElementTree as ET


REG = Path('/sys/class/aocec/fun_cfg')
ADAPTER_DEVICE = Path('/dev/aocec')
FAMILY = Path('/storage/.kodi')
ADAPTER = Path('userdata/peripheral_data/cec_CEC_Adapter.xml')
BOOT_CONFIG = Path('/flash/config.ini')
BACKUP = Path('/run/bobbi-test-cec-before.json')
# 231 = None; 36028 = Ignore. Values used by this CoreELEC version's peripherals.xml.
OFF = dict.fromkeys((
    'enabled', 'activate_source', 'activate_on_activity', 'send_inactive_source',
    'power_avr_on_as', 'cec_standby_screensaver', 'cec_standby_screensaver_paused',
    'cec_wake_screensaver', 'standby_tv_on_pc_standby', 'wakeup_cec_auto_power',
    'wakeup_cec_streaming', 'wakeup_cec_active_route',
), '0')
OFF.update(wake_devices='231', standby_devices='231', wake_devices_advanced='',
           standby_devices_advanced='', standby_pc_on_tv_standby='36028',
           action_on_explicit_standby='36028')


def config(profile):
    settings = ET.parse(profile / ADAPTER)
    found = {}
    for node in settings.iter('setting'):
        key = node.get('id')
        if key in OFF:
            if key in found:
                raise ValueError('Duplicate CEC peripheral setting')
            found[key] = node.get('value')
    return found


def device_mask():
    if not (REG.is_file() and ADAPTER_DEVICE.is_char_device()):
        raise RuntimeError('Unsupported CEC adapter: abort this hardware test')
    return int(REG.read_text().strip(), 16)


def open_processes():
    # Opening the character device, even just to query it, can initialise libCEC.
    found = 0
    for directory in Path('/proc').glob('[0-9]*/fd'):
        try:
            for fd in directory.iterdir():
                try:
                    if os.readlink(fd) == str(ADAPTER_DEVICE):
                        found += 1
                        break
                except FileNotFoundError:
                    pass  # normal concurrent close
        except FileNotFoundError:
            pass  # process exited
    return found


def boot_mask(path):
    # Read-only; never remount /flash or change bootloader preferences for a regression.
    values = []
    for line in path.read_text().splitlines():
        if re.match(r'^\s*cec_func_config\s*=', line):
            m = re.fullmatch(r'''\s*cec_func_config\s*=\s*(["']?)((?:0x)?[0-9a-fA-F]+)\1\s*(?:#.*)?''', line)
            if not m:
                raise RuntimeError('Unrecognised CEC boot setting; do not reboot')
            values.append(int(m[2], 16))
    if len(values) != 1:
        raise RuntimeError('Missing or ambiguous CEC boot setting; do not reboot')
    return values[0]


def verify(profile, before_box_reboot=False):
    mask, settings, opened = device_mask(), config(profile), open_processes()
    if settings != OFF or mask != 0 or opened:
        raise RuntimeError(f'CEC test blocked: mask={hex(mask)}; profile_off={settings == OFF}; handles={opened}')
    receipt = dict(mask=hex(mask), profile_settings=settings, profile_off=True, cec_device_open_processes=opened)
    if before_box_reboot:
        boot = boot_mask(BOOT_CONFIG)
        if boot:
            raise RuntimeError(f'CEC boot mask {hex(boot)} can re-enable CEC before Kodi; do not reboot')
        receipt['configured_boot_mask'] = hex(boot)
    return receipt


def disable():
    previous = device_mask()
    if config(FAMILY) != OFF or open_processes():
        raise RuntimeError('First disable the family Kodi CEC adapter and its power actions; test blocked')
    if not BACKUP.exists():
        with BACKUP.open('x') as f:
            json.dump(dict(mask=hex(previous), profile_settings=config(FAMILY)), f)
    if previous:
        # fun_cfg_store clears the mask and logical addresses on zero; it does not transmit.
        REG.write_text('0\n')
    time.sleep(.2)
    return dict(action='disable', before=hex(previous), prior_at_first_guard=json.loads(BACKUP.read_text())['mask'],
                **verify(FAMILY))


def stage(profile):
    # Only an offline, explicitly marked fixture under /storage/.cache can receive XML.
    profile = profile.absolute()
    if profile != profile.resolve() or not profile.is_relative_to(Path('/storage/.cache')):
        raise RuntimeError('Not an owned test profile')
    marker = profile / 'profile_identity'
    owner = profile.parent / 'owner'
    if (marker.is_symlink() or marker.read_text().strip() not in ('official', 'nara')
            or owner.is_symlink() or owner.read_text().strip() != 'CE2201 Arctic Fuse isolated test 81c76b'):
        raise RuntimeError('Not a recognised Arctic Fuse fixture')
    dest = profile / ADAPTER
    if dest != dest.resolve():
        raise RuntimeError('Unsafe CEC fixture destination')
    verify(FAMILY)
    if dest.exists():
        if config(profile) != OFF:
            raise RuntimeError('Existing CEC fixture settings differ: do not start Kodi')
    else:
        # Must precede first launch: factory settings enable wake, standby and activate_source.
        dest.parent.mkdir(mode=0o700, exist_ok=True)
        tree = ET.Element('settings')
        for key, value in OFF.items():
            ET.SubElement(tree, 'setting', id=key, value=value)
        with dest.open('xb') as f:
            ET.ElementTree(tree).write(f, encoding='utf-8', xml_declaration=True)
    return dict(action='stage', **verify(profile))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('disable', 'verify', 'stage'))
    parser.add_argument('--profile', type=Path, default=FAMILY)
    parser.add_argument('--before-box-reboot', action='store_true')
    args = parser.parse_args()
    if args.before_box_reboot and args.action != 'verify':
        parser.error('--before-box-reboot is only valid with verify')
    if args.action == 'disable':
        if args.profile != FAMILY:
            parser.error('disable operates on the host driver with the family profile')
        receipt = disable()
    elif args.action == 'stage':
        receipt = stage(args.profile)
    else:
        receipt = dict(action='verify', **verify(args.profile, args.before_box_reboot))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
