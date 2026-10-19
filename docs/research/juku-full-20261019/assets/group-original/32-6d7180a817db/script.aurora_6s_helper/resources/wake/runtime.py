# SPDX-License-Identifier: GPL-2.0-or-later
"""One heartbeat service and a synchronous suspend hook for the supported RTL8852 NG/NO radios."""
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid
from common import *

BASE = Path(__file__).resolve().parent
READY = STATE / 'ready.json'
MARKER = STATE / 'resume.json'
BUDGET = STATE / 'consumed.json'
ETHERNET = STATE / 'ethernet.json'
OWNED = STATE / 'owned.json'
REPAIR_LOCK = Path('/run/aurora6s-repair.lock')

def startup_controller():
    # Type=simple is active before rtk_hciattach finishes downloading firmware.
    if command('systemctl','is-active','bluetooth.service',check=False) != 'active':
        return None
    if command('systemctl','is-active','rtkbt-firmware-aml.service',check=False) != 'active':
        return None
    pid = command('systemctl','show','-p','MainPID','--value','rtkbt-firmware-aml.service')
    if not pid.isdigit() or int(pid) <= 0:
        return None
    try:
        return pid, controller()
    except (RuntimeError, OSError):
        return None

def initialize_when_ready(stopping):
    deadline = None; previous = None; stable = 0
    event('waiting_for_controller')
    while not stopping():
        enabled = command('systemctl','is-active','bluetooth.service',check=False) == 'active'
        if not enabled:
            deadline = None; previous = None; stable = 0
        else:
            if deadline is None: deadline = time.monotonic() + 90
            current = startup_controller()
            stable = stable + 1 if current and current == previous else int(bool(current))
            previous = current
            if stable >= 3:
                with REPAIR_LOCK.open('a') as repair_lock:
                    try:
                        fcntl.flock(repair_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        # Serialize against the Kodi startup retry/hardware repair.
                        if not stopping() and startup_controller() == current:
                            event('controller_ready_for_wake', address=current[1])
                            initialize()
                            return True
                        previous = None; stable = 0
            if time.monotonic() >= deadline:
                raise RuntimeError('蓝牙初始化未完成，唤醒服务未改动控制器；请检查 UART 初始化日志')
        time.sleep(1)
    return False

def event(kind, **kw):
    print(json.dumps(dict(event=kind, time=time.time(), **kw), ensure_ascii=False), flush=True)

def load(path):
    try: return json.loads(path.read_text())
    except FileNotFoundError: return {}

def refresh_peers(channel, address):
    # Caller holds hci.lock. Journal the union before HCI commands, including
    # partially added entries, so retries and the daemon/pre-hook share ownership.
    peers = automatic_peers(address)
    previous = load(OWNED)
    old = previous.get('peers', []) if (previous.get('boot_id'), previous.get('address')) == (boot_id(), address) else []
    save(OWNED, dict(boot_id=boot_id(), address=address, peers=sorted(set(old) | set(peers))))
    sync_peers(channel, peers, old)
    save(OWNED, dict(boot_id=boot_id(), address=address, peers=peers))
    event('wake_list_applied', count=len(peers))
    return peers

def mount_config():
    if digest(TARGET) != CONFIG_HASH: raise RuntimeError('现有蓝牙配置不是已核验的基础版本')
    if digest(BASE / 'rtl8852bs_config.wake') != WAKE_HASH: raise RuntimeError('心跳配置校验失败')
    command('mount', '--bind', str(BASE / 'rtl8852bs_config.wake'), str(TARGET))

def restore_config():
    mounted = any(l.split()[1] == str(TARGET) for l in Path('/proc/mounts').read_text().splitlines())
    if mounted:
        if digest(TARGET) != WAKE_HASH: raise RuntimeError('运行中的蓝牙配置被更改，拒绝卸载覆盖')
        command('umount', str(TARGET))

def initialize():
    guard()
    command('systemctl', 'stop', 'bluetooth.service', 'rtkbt-firmware-aml.service', timeout=40)
    try:
        # ExecStopPost blocks the radio; allow the power/reset state to settle.
        time.sleep(2)
        restore_config()
        mount_config()
        command('systemctl', 'start', 'rtkbt-firmware-aml.service', 'bluetooth.service', timeout=40)
    except BaseException:
        restore_config()
        command('systemctl', 'start', 'rtkbt-firmware-aml.service', 'bluetooth.service', check=False, timeout=40)
        raise

def native_reset(address, token):
    # Consume before writing, so service restarts cannot repeat a failed/finished attempt.
    save(BUDGET, dict(boot_id=boot_id(), token=token))
    if os.uname().release not in ('4.9.269', '5.15.196'):
        raise RuntimeError('当前内核不支持此蓝牙恢复方式')
    if Path('/sys/module/aurora_bt_native').exists():
        raise RuntimeError('已有蓝牙恢复模块，拒绝与其他恢复任务冲突')
    # Both supported kernels use the existing HCI close/open ioctl path.
    with REPAIR_LOCK.open('a') as repair_lock:
        fcntl.flock(repair_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        h=HCI()
        try: h.identify(address)
        finally: h.close()
        started=time.monotonic()
        command('hciconfig','hci0','reset',timeout=12)
        event('hci_close_open',token=token,seconds=time.monotonic()-started)

def eligible_resume(marker, consumed, boot, now):
    return (marker.get('boot_id') == boot and isinstance(marker.get('token'), str)
            and bool(marker['token']) and isinstance(marker.get('mono'), (int,float))
            and 0 <= now-marker['mono'] <= 15
            and (consumed.get('boot_id'), consumed.get('token')) != (boot, marker['token']))

def daemon():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open('/run/aurora-realtek-heartbeat.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    guard(); settings()
    # Leave initial UART setup and disabled Bluetooth alone. Service active is
    # insufficient: require a responsive, stable controller before reconfiguration.
    if not initialize_when_ready(lambda: stopping): return
    channel = None; address = None; synchronized = False; failures = 0; last_error = None
    owned = []; uart_pid = None; last_ack = 0
    try:
        while not stopping:
            started = time.monotonic()
            if command('systemctl','is-active','bluetooth.service',check=False) not in ('active','activating'):
                event('bluetooth_disabled'); break
            with open(str(STATE/'hci.lock'),'a') as io_lock:
                fcntl.flock(io_lock, fcntl.LOCK_EX)
                try:
                    current_pid = command('systemctl','show','-p','MainPID','--value','rtkbt-firmware-aml.service')
                    if current_pid != uart_pid:
                        if channel: channel.close()
                        channel=None; synchronized=False; owned=[]; uart_pid=current_pid
                    if channel is None:
                        address=controller(); channel=HCI(); channel.identify(address)
                    r = channel.command(0xfc94)
                    if len(r)!=3 or r[0]!=0: raise RuntimeError('控制器尚未就绪：'+r.hex())
                    failures=0; last_error=None; last_ack=time.monotonic()
                    marker=load(MARKER)
                    if eligible_resume(marker,load(BUDGET),boot_id(),time.monotonic()):
                        event('resume_ready', seconds=time.monotonic()-marker['mono'])
                        READY.unlink(missing_ok=True)
                        native_reset(address,marker['token'])
                        channel.close(); channel=None; synchronized=False; owned=[]
                    else:
                        if not synchronized:
                            owned=refresh_peers(channel,address); synchronized=True
                        save(READY,dict(boot_id=boot_id(),address=address,mono=time.monotonic(),owned=owned))
                except Exception as exc:
                    failures+=1
                    READY.unlink(missing_ok=True)
                    if str(exc)!=last_error:
                        event('retry',detail=str(exc),count=failures); last_error=str(exc)
                    if channel: channel.close(); channel=None
                    # No loop of controller resets. Failed wake recovery remains consumed.
                    if failures>=20 and time.monotonic()-last_ack>20: raise
            until = started + 1
            while not stopping and time.monotonic() < until:
                if eligible_resume(load(MARKER),load(BUDGET),boot_id(),time.monotonic()): break
                time.sleep(min(0.05,max(0.001,until-time.monotonic())))
    finally:
        READY.unlink(missing_ok=True)
        if channel: channel.close()
        # Returning to the stock configuration also removes a stale heartbeat dependency.
        shutting_down=command('systemctl','is-system-running',check=False) in ('stopping','offline')
        if shutting_down:
            # Other stop jobs are already queued; do not wait on them from ExecStop.
            restore_config()
        else:
            bluez_active=command('systemctl','is-active','bluetooth.service',check=False)=='active'
            command('systemctl','stop','bluetooth.service','rtkbt-firmware-aml.service',check=False,timeout=40)
            time.sleep(2)
            restore_config()
            units=['rtkbt-firmware-aml.service'] + (['bluetooth.service'] if bluez_active else [])
            command('systemctl','start','--no-block',*units,check=False,timeout=40)
        lock.close()

def ethernet_restore():
    data=load(ETHERNET)
    if data.get('boot_id')!=boot_id() or not data.get('restore'): return
    # Exact interface identity and previous administrative state, not link carrier.
    if Path('/sys/class/net/eth0/address').read_text().strip()!=data['address']:
        raise RuntimeError('有线接口身份改变，未恢复接口')
    command('ip','link','set','dev','eth0','up')
    ETHERNET.unlink(missing_ok=True)

def ethernet_down(enabled):
    ethernet_restore()
    if not enabled: return
    root=Path('/sys/class/net/eth0')
    if not root.exists() or not int((root/'flags').read_text().strip(),16)&1: return
    save(ETHERNET,dict(boot_id=boot_id(),address=(root/'address').read_text().strip(),restore=True))
    try:
        command('ip','link','set','dev','eth0','down')
        if int((root/'flags').read_text().strip(),16)&1: raise RuntimeError('有线网口被重新启用')
    except BaseException:
        ethernet_restore(); raise

def hook(action):
    STATE.mkdir(parents=True,exist_ok=True)
    with open(str(STATE/'hook.lock'),'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if action=='post':
            # RAM marker first; Ethernet restoration must not delay Bluetooth recovery.
            save(MARKER,dict(boot_id=boot_id(),token=uuid.uuid4().hex,mono=time.monotonic()))
            ethernet_restore(); return
        if action=='restore': ethernet_restore(); return
        guard(); config=settings()
        if command('systemctl','is-active','bluetooth.service',check=False) not in ('active','activating'):
            ethernet_down(config['ethernet_off']); return
        with open(str(STATE/'hci.lock'),'a') as io_lock:
            fcntl.flock(io_lock,fcntl.LOCK_EX)
            ready=load(READY)
            if ready.get('boot_id')!=boot_id() or time.monotonic()-ready.get('mono',0)>5:
                raise RuntimeError('蓝牙唤醒尚未就绪，本次待机已取消')
            h=HCI()
            try:
                h.identify(ready['address'])
                r=h.command(0xfc94)
                if len(r)!=3 or r[0]: raise RuntimeError('蓝牙未就绪，本次待机已取消')
                refresh_peers(h,ready['address'])
            finally: h.close()
        ethernet_down(config['ethernet_off'])

if __name__=='__main__':
    try:
        if sys.argv[1]=='daemon': daemon()
        elif sys.argv[1] in ('pre','post','restore'): hook(sys.argv[1])
        elif sys.argv[1]=='inspect':
            print(json.dumps(dict(peers=paired_remotes(),settings=settings()),ensure_ascii=False))
        else: raise ValueError('Unknown action')
    except Exception as exc:
        event('error',detail=str(exc)); raise SystemExit(1)
