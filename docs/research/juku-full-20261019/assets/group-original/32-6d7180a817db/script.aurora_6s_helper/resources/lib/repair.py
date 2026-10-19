"""Standalone, backed-up repair installer. Never loads drivers through Kodi."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from device import detect, payload_key, PROFILE_IDS

PAYLOAD = Path(__file__).resolve().parents[1] / 'payload'
BACKUPS = Path('/storage/ce-fix-backup')
LOCK = Path('/run/aurora6s-repair.lock')
SYSTEMD = Path('/storage/.config/system.d')
NO = {'no/6s/dtb.img': '/flash/dtb.img',
      'no/6s/post-sysroot.sh': '/flash/post-sysroot.sh',
      'no/6s/rtl8852bs_config': '/storage/.config/firmware/rtlbt/rtl8852bs_config',
      'no/6s/99-zidoo-v12-keyboard.rules': '/storage/.config/udev.rules.d/99-zidoo-v12-keyboard.rules'}
NG = {'ng/6s/dtb.img': '/flash/dtb.img',
      'ng/6s/rtl8852bs_config': '/storage/.config/firmware/rtlbt/rtl8852bs_config'}
for _name in ('8852be.ko', 'rtkm.ko', 'leds-tca6507.ko', 'load-drivers.sh'):
    NG['ng/6s/' + _name] = '/storage/.config/aurora6s-ng/' + _name
for _name in ('aurora6s-ng-wifi.service', 'aurora6s-ng-led.service'):
    NG['ng/6s/' + _name] = str(SYSTEMD / _name)
UNITS = ('aurora6s-ng-wifi.service', 'aurora6s-ng-led.service', 'rtkbt-firmware-aml.service')
BOOT_HOOK_BEGIN = b'# BEGIN Aurora NO DTB check'
BOOT_HOOK_END = b'# END Aurora NO DTB check'


def targets(branch, board='6s', chip='rtl8852'):
    prefix = payload_key(branch, board, chip)
    if chip == 'ap6275p':
        allowed = ('dtb.img', 'leds-tca6507.ko', 'load-drivers.sh', 'aurora6s-ng-led.service') if branch == 'ng' else ('dtb.img', 'post-sysroot.sh', '99-zidoo-v12-keyboard.rules')
        base = NG if branch == 'ng' else NO
        return {prefix + '/' + Path(name).name: target for name, target in base.items()
                if Path(name).name in allowed}
    base = NG if branch == 'ng' else NO
    return {prefix + '/' + Path(name).name: target for name, target in base.items()}


def profile_targets(profile):
    return targets(profile['branch'], profile.get('board', '6s'), profile.get('chip', 'rtl8852'))


def cleanup_targets(branch, chip, version=8):
    """Only remove known previous Realtek deployment files, never whole directories."""
    if chip != 'ap6275p':
        return {}
    result = ({'cleanup/' + Path(name).name: target for name, target in NG.items()
               if Path(name).name in ('8852be.ko', 'rtkm.ko', 'rtl8852bs_config', 'aurora6s-ng-wifi.service')}
              if branch == 'ng' else {})
    # Formats 5..7 predate wake cleanup. Keep their exact restore allowlist.
    if version >= 8:
        result.update({
            'cleanup/wake-service': str(SYSTEMD / 'aurora6s-wake.service'),
            'cleanup/wake-enable': str(SYSTEMD / 'multi-user.target.wants/aurora6s-wake.service'),
            'cleanup/wake-suspend': str(SYSTEMD / 'systemd-suspend.service.d/90-aurora6s-wake.conf'),
            'cleanup/wake-old-ethernet': str(SYSTEMD / 'systemd-suspend.service.d/91-aurora-ethernet-repeat.conf'),
        })
    return result


def desired_link(branch, chip, name):
    if branch == 'ng' and chip == 'ap6275p' and name != 'aurora6s-ng-led.service':
        return None
    return '/usr/lib/systemd/system/' + name if name == 'rtkbt-firmware-aml.service' else str(SYSTEMD / name)


def backup_targets(manifest):
    """Keep pre-layout backups restorable without trusting arbitrary paths."""
    branch = manifest['branch']
    version = manifest.get('format', 1)
    if version == 9:
        return targets(branch, manifest['board'], manifest['chip'])
    if version in (3, 4, 5, 6, 7, 8):
        saved = targets(branch, manifest['board'], manifest['chip'])
        saved = {name: target for name, target in saved.items() if not name.endswith('/post-sysroot.sh')}
        # 1.3.0 Broadcom backups predate the shared NO input fix.
        if version == 3 and manifest['chip'] == 'ap6275p':
            saved = {name: target for name, target in saved.items() if name.endswith('/dtb.img')}
        return saved
    current = {name: target for name, target in targets(branch).items() if not name.endswith('/post-sysroot.sh')}
    if version == 2:
        return current
    if version != 1:
        raise RuntimeError('未知备份格式')
    legacy = {}
    for name, target in current.items():
        filename = Path(name).name
        key = ('ng/' + filename if branch == 'ng' and filename != 'rtl8852bs_config'
               else filename)
        legacy[key] = target
    return legacy


def links(branch):
    if branch != 'ng':
        return {}
    return {name: SYSTEMD / 'multi-user.target.wants' / name for name in UNITS}


def run(*args, check=True, timeout=30):
    return subprocess.run(args, check=check, capture_output=True, encoding='utf-8', timeout=timeout,
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_copy(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.aurora-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'wb') as out, open(source, 'rb') as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, 0o644)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def boot_hook_content(target, source):
    """Update only our marked block, retaining other initramfs customizations."""
    current = Path(target).read_bytes() if Path(target).exists() else b''
    block = Path(source).read_bytes().split(b'\n', 1)[1]  # Exclude the payload's shebang.
    lines = current.splitlines(keepends=True)
    begin = [i for i, line in enumerate(lines) if line.rstrip(b'\r\n') == BOOT_HOOK_BEGIN]
    end = [i for i, line in enumerate(lines) if line.rstrip(b'\r\n') == BOOT_HOOK_END]
    if not begin and not end:
        prefix = current or b'#!/bin/sh\n'
        return prefix + (b'' if prefix.endswith(b'\n') else b'\n') + block
    if len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
        raise RuntimeError('启动脚本中的 DTB 检查标记不完整：' + str(target))
    return b''.join(lines[:begin[0]]) + block + b''.join(lines[end[0] + 1:])


def set_link(path, value):
    path = Path(path)
    if value is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.aurora-', dir=str(path.parent)) as d:
        temp = Path(d) / 'link'
        temp.symlink_to(value)
        os.replace(temp, path)


def verify_payload():
    expected = json.loads((PAYLOAD / 'hashes.json').read_text(encoding='utf-8'))
    files = set()
    for key in PROFILE_IDS:
        parts = key.split('/')
        files.update(targets(parts[0], parts[1], parts[2] if len(parts) == 3 else 'rtl8852'))
    if set(expected) != files:
        raise RuntimeError('修复包清单不完整')
    for name, digest in expected.items():
        if sha(PAYLOAD / name) != digest:
            raise RuntimeError('修复包校验失败：' + name)


def flash_is_ro():
    for line in Path('/proc/mounts').read_text(encoding='utf-8').splitlines():
        fields = line.split()
        if fields[1] == '/flash':
            return 'ro' in fields[3].split(',')
    raise RuntimeError('/flash 未挂载')


def check(confirmed_6s=False, allow_unidentified=False, confirmed_board=None):
    profile = detect(confirmed_6s=confirmed_6s, allow_unidentified=allow_unidentified,
                     confirmed_board=confirmed_board)
    verify_payload()
    flash_is_ro()
    if not Path('/flash/dtb.img').is_file():
        raise RuntimeError('未找到外置 CE 的 /flash/dtb.img')
    if not profile['board']:
        profile['files'] = {}
        return profile
    if profile['branch'] == 'ng':
        unit = 'brcmfmac_sdio-firmware-aml.service' if profile['chip'] == 'ap6275p' else 'rtkbt-firmware-aml.service'
        if not Path('/usr/lib/systemd/system', unit).is_file():
            raise RuntimeError('缺少 CE 蓝牙启动服务：' + unit)
        if profile['chip'] == 'ap6275p':
            for required in ('/usr/lib/udev/rules.d/80-brcmfmac_pci.rules', '/lib/firmware/brcm/BCM4362A2.hcd'):
                if not Path(required).is_file():
                    raise RuntimeError('缺少 CE 博通支持文件：' + required)
        config = Path('/flash/config.ini').read_text(encoding='utf-8')
        # Experimental boot overrides must be removed deliberately, not silently carried over.
        if any(s in config for s in ('amlogic_pcie_init', 'wifi_dummy_init', 'systemd.mask=aurora6s-ng-wifi')):
            raise RuntimeError('config.ini 仍有 PCIe/Wi-Fi 诊断启动参数，请先恢复正常启动配置')
    profile['files'] = {
        name: Path(target).is_file() and (
            Path(target).read_bytes() == boot_hook_content(target, PAYLOAD / name)
            if name.endswith('/post-sysroot.sh') else sha(target) == sha(PAYLOAD / name))
        for name, target in profile_targets(profile).items()}
    profile['cleanup'] = [target for target in cleanup_targets(profile['branch'], profile['chip']).values()
                          if os.path.lexists(target)]
    return profile


def snapshot(path, backup):
    path = Path(path)
    if path.is_symlink():
        return {'link': os.readlink(path)}
    if path.exists():
        atomic_copy(path, backup)
        return {'sha256': sha(backup), 'mode': path.stat().st_mode & 0o777}
    return None


def restore_file(path, saved, source):
    path = Path(path)
    if saved is None:
        path.unlink(missing_ok=True)
    elif 'link' in saved:
        set_link(path, saved['link'])
    else:
        atomic_copy(source, path)
        os.chmod(path, saved['mode'])
        if sha(path) != saved['sha256']:
            raise RuntimeError('恢复校验失败：' + str(path))


def restore(backup):
    backup = Path(backup)
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    branch = manifest['branch']
    saved_targets = backup_targets(manifest)
    removed = cleanup_targets(branch, manifest['chip'], manifest['format']) if manifest.get('format') in (5, 6, 7, 8, 9) else {}
    if set(manifest.get('removed', {})) != set(removed):
        raise RuntimeError('清理备份清单不匹配')
    if set(manifest['files']) != set(saved_targets) or set(manifest['links']) != set(links(branch)):
        raise RuntimeError('备份清单不匹配')
    for name, saved in manifest['files'].items():
        if saved and 'sha256' in saved and sha(backup / name) != saved['sha256']:
            raise RuntimeError('备份校验失败：' + name)
    for name, saved in manifest.get('removed', {}).items():
        if saved and 'sha256' in saved and sha(backup / name) != saved['sha256']:
            raise RuntimeError('清理备份校验失败：' + name)
    wake_files = {}
    if manifest.get('format') in (6, 7) or (manifest.get('format') == 9 and 'wake_files' in manifest):
        import wake_install
        wake_files = wake_install.extra_targets(None if manifest.get('format') == 6 else manifest)
        if set(manifest.get('wake_files', {})) != set(wake_files):
            raise RuntimeError('待机修复备份清单不匹配')
        for name, saved in manifest['wake_files'].items():
            if saved and 'sha256' in saved and sha(backup / 'wake' / name) != saved['sha256']:
                raise RuntimeError('待机修复备份校验失败：' + name)
        run('systemctl','stop','aurora6s-wake.service',check=False)
    was_ro = flash_is_ro()
    run('mount', '-o', 'remount,rw', '/flash')
    try:
        for name, target in wake_files.items():
            restore_file(target, manifest['wake_files'][name], backup / 'wake' / name)
        for name, target in saved_targets.items():
            restore_file(target, manifest['files'][name], backup / name)
        for name, target in removed.items():
            restore_file(target, manifest['removed'][name], backup / name)
        for name, path in links(branch).items():
            set_link(path, manifest['links'][name])
        run('systemctl', 'daemon-reload')
        if manifest['keepalive_enabled'] in ('enabled', 'enabled-runtime'):
            args = ['systemctl', 'enable']
            if manifest['keepalive_enabled'] == 'enabled-runtime':
                args.append('--runtime')
            run(*(args + ['bt-uart-keepalive.service']))
        if manifest['keepalive_active'] == 'active':
            run('systemctl', 'start', 'bt-uart-keepalive.service')
        if branch == 'no':
            run('udevadm', 'control', '--reload-rules')
        os.sync()
    finally:
        if was_ro:
            run('mount', '-o', 'remount,ro', '/flash')


def install(confirmed_6s=False, confirmed_board=None, wake_settings=None):
    profile = check(confirmed_6s=confirmed_6s, confirmed_board=confirmed_board)
    branch = profile['branch']
    board, chip = profile.get('board', '6s'), profile.get('chip', 'rtl8852')
    selected_targets = profile_targets(profile)
    prepared_hooks = {name: boot_hook_content(target, PAYLOAD / name)
                      for name, target in selected_targets.items() if name.endswith('/post-sysroot.sh')}
    wake_files = {}
    wake_config = None
    import wake_install
    if wake_settings is None and wake_install.supported(profile):
        saved_options = Path(wake_install.ROOT + 'settings.json')
        wake_settings = (json.loads(saved_options.read_text(encoding='utf-8')) if saved_options.exists()
                         else {'remote_mode': 'auto', 'ethernet_off': False})
    if wake_settings is not None:
        import wake_install
        if not wake_install.supported(profile):
            raise RuntimeError('待机唤醒仅适用于 6S 或 4 Pro 的 RTL8852 NG/NO 系统')
        wake_settings = wake_install.validate(wake_settings)
        wake_install.verify()
        wake_install.verify_firmware()
        if branch == 'ng':
            wake_config = wake_install.boot_config(Path(wake_install.extra_targets(profile)['config.ini']).read_text(encoding='utf-8'))
        # Test bind mounts disappear on reboot. Never copy into a temporary override.
        target = '/storage/.config/firmware/rtlbt/rtl8852bs_config'
        mounted = any(l.split()[1] == target for l in Path('/proc/mounts').read_text().splitlines())
        if mounted and run('systemctl','is-active','aurora6s-wake.service',check=False).stdout.strip() != 'active':
            raise RuntimeError('当前仍在运行临时蓝牙实验配置，请先重启，再执行硬件修复')
        if mounted:
            run('systemctl','stop','aurora6s-wake.service')
        wake_files = wake_install.extra_targets(profile)
    removed = cleanup_targets(branch, chip)
    if chip == 'ap6275p' and (SYSTEMD / 'aurora6s-wake.service').exists():
        # Stop before reading firmware backups: the RTL service may still have
        # its temporary 0x1a config bind-mounted. Its shutdown restores the base.
        # Do not shorten the unit's 95-second graceful shutdown budget.
        run('systemctl', 'stop', 'aurora6s-wake.service', timeout=105)
    manage_keepalive = chip == 'rtl8852' or bool(removed)
    # Reject non-symlink wants entries before any modification.
    original_links = {}
    for name, path in links(branch).items():
        if path.exists() and not path.is_symlink():
            raise RuntimeError('启动链接不是符号链接：' + str(path))
        original_links[name] = os.readlink(path) if path.is_symlink() else None
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='aurora-addon-', dir=str(BACKUPS)))
    manifest = dict(format=9 if branch == 'no' else (7 if wake_files else (8 if chip == 'ap6275p' else 5)), branch=branch, board=board, chip=chip, files={}, removed={}, links=original_links,
                    keepalive_enabled=run('systemctl', 'is-enabled', 'bt-uart-keepalive.service', check=False).stdout.strip() if manage_keepalive else 'disabled',
                    keepalive_active=run('systemctl', 'is-active', 'bt-uart-keepalive.service', check=False).stdout.strip() if manage_keepalive else 'inactive')
    for name, target in selected_targets.items():
        manifest['files'][name] = snapshot(target, backup / name)
    for name, target in removed.items():
        manifest['removed'][name] = snapshot(target, backup / name)
    if wake_files:
        manifest['wake_files'] = {name: snapshot(target, backup / 'wake' / name) for name,target in wake_files.items()}
        shutil.copy2(Path(__file__).with_name('wake_install.py'), backup / 'wake_install.py')
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    shutil.copy2(__file__, backup / 'repair.py')
    shutil.copy2(Path(__file__).with_name('device.py'), backup / 'device.py')
    (backup / 'restore.sh').write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec /usr/bin/python3 repair.py --restore "$PWD"\n')
    prepared_sources = {}
    for name, content in prepared_hooks.items():
        source = backup / 'prepared' / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        prepared_sources[name] = source
    os.sync()
    was_ro = flash_is_ro()
    run('mount', '-o', 'remount,rw', '/flash')
    try:
        for name, target in selected_targets.items():
            source = prepared_sources.get(name, PAYLOAD / name)
            atomic_copy(source, target)
            if sha(target) != sha(source):
                raise RuntimeError('写入校验失败：' + name)
        if wake_files:
            for name,target in wake_install.files(profile).items():
                atomic_copy(wake_install.SOURCE / name,target)
                if sha(target) != sha(wake_install.SOURCE / name): raise RuntimeError('待机修复写入校验失败：'+name)
            with tempfile.TemporaryDirectory() as temp:
                generated = [('settings.json',json.dumps(wake_settings,ensure_ascii=False))]
                if wake_config is not None: generated.append(('config.ini',wake_config))
                for name,data in generated:
                    source=Path(temp)/name; source.write_text(data,encoding='utf-8')
                    atomic_copy(source,wake_files[name])
            set_link(wake_files['enable-link'],wake_files['aurora6s-wake.service'])
            for name in ('old-ethernet-hook','old-native-hook','old-heartbeat-hook'):
                Path(wake_files[name]).unlink(missing_ok=True)
            if 'aurora_bt_native.ko' in wake_files:
                Path(wake_files['aurora_bt_native.ko']).unlink(missing_ok=True)
        for name, path in links(branch).items():
            set_link(path, desired_link(branch, chip, name))
        for target in removed.values():
            Path(target).unlink(missing_ok=True)
        run('systemctl', 'daemon-reload')
        if manage_keepalive:
            load = run('systemctl', 'show', '-p', 'LoadState', '--value', 'bt-uart-keepalive.service').stdout.strip()
            if load and load != 'not-found':
                run('systemctl', 'disable', '--now', 'bt-uart-keepalive.service')
        if branch == 'no':
            run('udevadm', 'control', '--reload-rules')
        # Drivers are intentionally not started against the old live DTB.
        os.sync()
    except Exception as exc:
        try:
            restore(backup)
        except Exception as rollback:
            raise RuntimeError('部署失败且自动恢复失败。备份：%s；%s；%s' % (backup, exc, rollback)) from exc
        raise RuntimeError('部署失败，已恢复原文件。备份：%s；%s' % (backup, exc)) from exc
    finally:
        if was_ro:
            run('mount', '-o', 'remount,ro', '/flash')
    return str(backup)


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--install', action='store_true')
    action.add_argument('--restore', metavar='BACKUP')
    parser.add_argument('--wake-settings', help='JSON settings for RTL8852 NG/NO wake')
    parser.add_argument('--confirm-6s', action='store_true')
    parser.add_argument('--confirm-board', choices=('6s', '4pro'))
    args = parser.parse_args()
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.check:
            print(json.dumps(check(confirmed_6s=args.confirm_6s, confirmed_board=args.confirm_board,
                                   allow_unidentified=True), ensure_ascii=False))
        elif args.install:
            print(json.dumps({'backup': install(args.confirm_6s, args.confirm_board, json.loads(args.wake_settings) if args.wake_settings is not None else None)}, ensure_ascii=False))
        else:
            profile = detect(confirmed_6s=args.confirm_6s, confirmed_board=args.confirm_board, check_kernel=False)
            manifest = json.loads((Path(args.restore) / 'manifest.json').read_text(encoding='utf-8'))
            if profile['branch'] != manifest['branch']:
                raise RuntimeError('备份所属分支与当前系统不同')
            if (profile['board'], profile['chip']) != (manifest.get('board', '6s'), manifest.get('chip', 'rtl8852')):
                raise RuntimeError('备份所属机型/芯片与当前设备不同')
            restore(args.restore)
            print('原文件与启动链接已恢复；请重启盒子。')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(str(exc))
