# SPDX-License-Identifier: GPL-2.0-or-later
"""RTL8852 NG/NO Bluetooth wake configuration; no Kodi dependencies."""
import configparser
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import struct
import subprocess
import time

ROOT = Path('/storage/.config/aurora6s-wake')
STATE = Path('/run/aurora6s-wake')
CONFIG = ROOT / 'settings.json'
TARGET = Path('/storage/.config/firmware/rtlbt/rtl8852bs_config')
FW_HASH = '1e27d21231c08010d5dcd4c24d294762f8ea2f608cb533a5955e0df3bd725440'
CONFIG_HASH = 'f60918c29e31671593ce38bb3870ffe83be9c2c82d232dd3c3f5d75cd89cecf2'
WAKE_HASH = '9b9280df7260f749e5ddbe506fccc27d4ba88d3281ccf766cf112998e006561c'
BONDS = Path('/storage/.cache/bluetooth')
MAC = re.compile(r'^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$')

def command(*args, check=True, timeout=15):
    p = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or repr(args))
    return p.stdout.strip()

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)

def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

def validate(data):
    # Upgrade the initial fixed-list format without retaining stale selections.
    if not isinstance(data, dict) or type(data.get('ethernet_off')) is not bool:
        raise ValueError('唤醒设置格式错误')
    if set(data) == {'peers', 'ethernet_off'}:
        peers = data['peers']
        if (not isinstance(peers, list) or len(peers) > 10
                or any(not isinstance(p, str) or not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', p) for p in peers)
                or len(set(peers)) != len(peers)):
            raise ValueError('旧唤醒名单格式错误')
    elif set(data) != {'remote_mode', 'ethernet_off'} or data['remote_mode'] != 'auto':
        raise ValueError('唤醒设置格式错误')
    return dict(remote_mode='auto', ethernet_off=data['ethernet_off'])

def settings():
    return validate(json.loads(CONFIG.read_text(encoding='utf-8')))

def controller():
    p = Path('/sys/class/bluetooth/hci0')
    # Current supported radio is UART; never send vendor commands to a USB dongle.
    if not p.exists() or '/usb' in str(p.resolve()) or 'tty' not in str((p / 'device').resolve()):
        raise RuntimeError('未找到受支持的 UART 蓝牙控制器')
    h = HCI()
    try:
        value = h.command(0x1009)
        if len(value) != 7 or value[0]: raise RuntimeError('无法读取蓝牙控制器地址')
        address = ':'.join('%02X' % x for x in value[1:][::-1])
    finally: h.close()
    if not MAC.fullmatch(address): raise RuntimeError('蓝牙控制器地址无效')
    return address

def connected_remotes():
    # One bounded kernel connection query, not one BlueZ call per saved device.
    # Pending connections (state 5 / handle 0) must not receive connected priority.
    output = command('hcitool', '-i', 'hci0', 'con', timeout=0.4)
    return {m[0].upper() for m in re.findall(
        r'\bLE\s+([0-9a-fA-F:]{17})\s+handle\s+\d+\s+state\s+(\d+)\b', output)
        if m[1] == '1'}

def paired_remotes(address=None):
    address = address or controller()
    connected = connected_remotes()
    items = []
    # Read only General fields; never return bond keys or whole info files.
    for path in sorted((BONDS / address).glob('*/info')):
        peer = path.parent.name.upper()
        if not MAC.fullmatch(peer): continue
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.read(path, encoding='utf-8')
        general = cp['General'] if cp.has_section('General') else {}
        if general.get('AddressType', '').lower() != 'public': continue
        if 'LE' not in general.get('SupportedTechnologies', '').split(';'): continue
        if general.get('Blocked','false').lower()=='true': continue
        if not any(cp.has_section(k) for k in ('LongTermKey','PeripheralLongTermKey','SlaveLongTermKey')): continue
        if '00001812-0000-1000-8000-00805f9b34fb' not in general.get('Services','').lower(): continue
        items.append(dict(address=peer, name=general.get('Name', peer), connected=peer in connected))
    return sorted(items, key=lambda x: (not x['connected'], x['name'].casefold(), x['address']))

def automatic_peers(address):
    # RC173 already has firmware power-key wake. Do not broaden it to
    # address-based wake, and do not consume one of the ten dynamic slots.
    peers = [p for p in paired_remotes(address)
             if p['name'].strip().casefold() != 'xiaopairc_173']
    return [p['address'] for p in peers[:10]]

def wake_platform(kernel, machine, dt, release, pcie_domain, cmdline):
    ids = {
        'ng': {'sc2_s905x4_tencent_aurora_6s_ng', 'sc2_s905x4_tencent_aurora_4pro_rtl8852_ng'},
        'no': {'sc2_s905x4_tencent_aurora_6s_hs400', 'sc2_s905x4_tencent_aurora_4pro_rtl8852_hs400'},
    }
    if machine != 'aarch64': raise RuntimeError('蓝牙唤醒内核架构不匹配')
    if kernel == '4.9.269' and dt in ids['ng'] and 'Amlogic-ng.arm' in release:
        if pcie_domain or 'pd_ignore_unused' not in cmdline.split():
            raise RuntimeError('NG 待机修复尚未生效，请重启加载新设备树和启动参数')
        return 'ng'
    if kernel == '5.15.196' and dt in ids['no'] and 'DISTRO_DEVICE="Amlogic-no"' in release:
        return 'no'
    raise RuntimeError('蓝牙唤醒内核、系统分支或设备树尚未适配')

def guard():
    platform = wake_platform(os.uname().release, os.uname().machine,
        Path('/proc/device-tree/coreelec-dt-id').read_bytes().rstrip(b'\0').decode(),
        Path('/etc/os-release').read_text(),
        Path('/proc/device-tree/pcieA@f5000000/power-domains').exists(),
        Path('/proc/cmdline').read_text())
    if digest('/lib/firmware/rtlbt/rtl8852bs_fw') != FW_HASH:
        raise RuntimeError('蓝牙固件版本尚未适配，未启动唤醒功能')
    return platform


def complete(packet, opcode):
    if len(packet) < 7 or packet[:2] != b'\x04\x0e': return None
    if len(packet) != packet[2] + 3 or packet[4:6] != struct.pack('<H', opcode): return None
    return packet[6:]

class HCI:
    def __init__(self, index=0):
        self.socket = socket.socket(31, socket.SOCK_RAW, 1)
        try:
            address = struct.pack('HHH', 31, index, 0)
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.bind(self.socket.fileno(), address, len(address)):
                raise OSError(ctypes.get_errno(), 'HCI bind')
            self.socket.setsockopt(0, 2, struct.pack('<IIIHxx', 1 << 4, 1 << 14, 0, 0))
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close(); raise
    def close(self): self.socket.close()
    def command(self, opcode, payload=b'', timeout=0.7):
        while select.select([self.socket], [], [], 0)[0]: self.socket.recv(1024)
        self.socket.send(struct.pack('<BHB', 1, opcode, len(payload)) + payload)
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if not select.select([self.socket], [], [], max(0, until-time.monotonic()))[0]: break
            result = complete(self.socket.recv(1024), opcode)
            if result is not None: return result
        raise TimeoutError('HCI command timeout: 0x%04x' % opcode)
    def identify(self, address):
        if self.command(0x1009) != b'\0' + bytes.fromhex(address.replace(':', ''))[::-1]:
            raise RuntimeError('蓝牙控制器身份改变')

def sync_peers(hci, peers, previous=()):
    # Remove only our entries, then add; never clear unrelated firmware entries.
    for peer in sorted(set(previous) | set(peers)):
        r = hci.command(0xfc7c, b'\0' + bytes.fromhex(peer.replace(':',''))[::-1])
        # On the pinned firmware, 0x12 is returned when the entry is absent.
        # Confirmed by remove(existing)=00, remove(again)=12, add=00.
        if r not in (b'\0', b'\x12'): raise RuntimeError('移除旧唤醒名单失败：' + peer)
    for peer in peers:
        r = hci.command(0xfc7b, b'\0' + bytes.fromhex(peer.replace(':',''))[::-1])
        if r != b'\0': raise RuntimeError('写入唤醒名单失败：' + peer)
