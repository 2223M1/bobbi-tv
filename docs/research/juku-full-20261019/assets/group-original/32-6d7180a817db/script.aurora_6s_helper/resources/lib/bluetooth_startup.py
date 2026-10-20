"""One bounded startup retry of an already-installed Bluetooth attach service."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

import device

BLUETOOTH = Path('/sys/class/bluetooth')
STATE = Path('/run/aurora6s-bt-retry.json')
LOCK = Path('/run/aurora6s-bt-retry.lock')
REPAIR_LOCK = Path('/run/aurora6s-repair.lock')
BLUEZ_CONFIG = Path('/storage/.cache/services/bluez.conf')
UNITS = {'ap6275p': 'brcmfmac_sdio-firmware-aml.service',
         'rtl8852': 'rtkbt-firmware-aml.service'}
WAIT_SECONDS = 60


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, encoding='utf-8',
                          errors='replace', timeout=10,
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def unit_state(unit):
    result = command('systemctl', 'show', unit, '--no-pager',
                     '--property=LoadState,ActiveState,UnitFileState,Result')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def has_controller():
    # Conservatively leave all existing controllers alone, including USB dongles.
    return any(BLUETOOTH.glob('hci*'))


def usable(state):
    return (state.get('LoadState') == 'loaded' and
            state.get('UnitFileState') in ('static', 'enabled', 'enabled-runtime',
                                          'linked', 'linked-runtime', 'indirect', 'generated'))


def bluez_enabled(state):
    # CE starts bluetooth.service from settings even when UnitFileState=disabled.
    return (BLUEZ_CONFIG.is_file() and state.get('LoadState') == 'loaded'
            and state.get('ActiveState') == 'active'
            and state.get('UnitFileState') not in ('masked', 'masked-runtime'))


def save(unit, profile, status, detail=''):
    data = dict(unit=unit, dt_id=profile['dt_id'], status=status, detail=detail)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, STATE)


def recover_once(monitor, log):
    """Called in a Kodi startup thread; never installs/enables drivers or loops retries."""
    unit = ''
    profile = None
    attempted = False
    try:
        with LOCK.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            if STATE.exists() or monitor.abortRequested():
                return
            # Same live-DTB requirement as lighting, without mapping Android.
            profile = device.detect(check_kernel=False, runtime_profile=True)
            if profile['dt_id'] != profile['expected_dt_id']:
                log('skip: current DTB does not match the installed repair profile')
                return
            chip = device.pci_chip()
            if chip and chip != profile['chip']:
                log('skip: PCI wireless chip conflicts with current DTB')
                return
            unit = UNITS[profile['chip']]
            deadline = time.monotonic() + WAIT_SECONDS
            while not monitor.abortRequested():
                if has_controller():
                    log('controller already present; no retry needed')
                    return
                state = unit_state(unit)
                if not usable(state) or state.get('ActiveState') not in ('failed', 'active', 'activating'):
                    log('skip: %s is not a running/failed initialization service' % unit)
                    return
                if state['ActiveState'] == 'failed':
                    break
                if time.monotonic() >= deadline:
                    log('initialization still running; left unchanged')
                    return
                if monitor.waitForAbort(2):
                    return
            else:
                return

            with REPAIR_LOCK.open('a') as repair_lock:
                try:
                    fcntl.flock(repair_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    log('skip: hardware repair is running')
                    return
                # Recheck after locking: a user may have stopped/recovered it meanwhile.
                state = unit_state(unit)
                bluez = unit_state('bluetooth.service')
                if (has_controller() or not usable(state) or state.get('ActiveState') != 'failed'
                        or not bluez_enabled(bluez)
                        or monitor.abortRequested()):
                    return
                other_unit = next(name for name in UNITS.values() if name != unit)
                other = unit_state(other_unit)
                if other.get('ActiveState') in ('active', 'activating', 'deactivating'):
                    log('skip: another Bluetooth attach service is using the UART')
                    return
                # /run survives Kodi restarts but is cleared on system boot.
                save(unit, profile, 'retrying')
                attempted = True
                log('retrying failed %s once (%s)' % (unit, profile['dt_id']))
                command('systemctl', 'stop', unit)
                # The CE unit's ExecStopPost blocks Bluetooth; allow it to settle.
                if monitor.waitForAbort(2):
                    save(unit, profile, 'aborted')
                    return
                state = unit_state(unit)
                bluez = unit_state('bluetooth.service')
                other = unit_state(other_unit)
                if (has_controller() or not usable(state) or not bluez_enabled(bluez)
                        or state.get('ActiveState') not in ('inactive', 'failed')
                        or other.get('ActiveState') in ('active', 'activating', 'deactivating')
                        or monitor.abortRequested()):
                    save(unit, profile, 'aborted', 'state changed before restart')
                    log('retry cancelled: Bluetooth state changed before restart')
                    return
                # ExecStartPre unblocks it. Keep the system's firmware/UART settings.
                command('systemctl', 'start', unit)

            deadline = time.monotonic() + WAIT_SECONDS
            while not monitor.abortRequested():
                if has_controller():
                    save(unit, profile, 'recovered')
                    log('Bluetooth controller created after retry')
                    return
                state = unit_state(unit)
                if state.get('ActiveState') == 'failed':
                    save(unit, profile, 'failed', state.get('Result', ''))
                    log('retry failed; see journalctl -b -u ' + unit)
                    return
                if time.monotonic() >= deadline:
                    save(unit, profile, 'timeout')
                    log('retry has not created a controller; no further restart')
                    return
                if monitor.waitForAbort(2):
                    break
            save(unit, profile, 'aborted')
    except Exception as exc:
        if attempted:
            try:
                save(unit, profile, 'failed', str(exc))
            except OSError:
                pass
        log(('retry failed: ' if attempted else 'startup check skipped: ') + str(exc))
