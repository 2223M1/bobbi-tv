"""Identify the supported board/build without relying on Kodi."""
import os
import gzip
import json
import subprocess
import sys
from pathlib import Path
import platform
import re
import shlex

DT = Path('/proc/device-tree')
RELEASE = Path('/etc/os-release')
NG_RELEASE = '4.9.269'
KERNEL_CONFIG = Path('/proc/config.gz')
NG_FLAGS = ('CONFIG_ARM64=y', 'CONFIG_SMP=y', 'CONFIG_PREEMPT=y', 'CONFIG_MODULE_UNLOAD=y', 'CONFIG_MODVERSIONS=y')
DT_IDS = {'no': 'sc2_s905x4_tencent_aurora_6s_hs400',
          'ng': 'sc2_s905x4_tencent_aurora_6s_ng'}
CPUINFO = Path('/proc/cpuinfo')
PCI = Path('/sys/bus/pci/devices')
ANDROID_PROPERTIES = (Path('/android/vendor/build.prop'),
                      Path('/android/system/system/build.prop'),
                      Path('/android/system/build.prop'))
BOARD_MODELS = {'A4111': '4pro', 'A4112': '6s'}
PROFILE_IDS = {
    'ng/6s': DT_IDS['ng'], 'no/6s': DT_IDS['no'],
    'ng/4pro/rtl8852': 'sc2_s905x4_tencent_aurora_4pro_rtl8852_ng',
    'no/4pro/rtl8852': 'sc2_s905x4_tencent_aurora_4pro_rtl8852_hs400',
    'no/4pro/ap6275p': 'sc2_s905x4_tencent_aurora_4pro_ap6275p_hs400',
    'ng/4pro/ap6275p': 'sc2_s905x4_tencent_aurora_4pro_ap6275p_ng',
}


def payload_key(branch, board='6s', chip='rtl8852'):
    if branch not in ('ng', 'no'):
        raise RuntimeError('未知修复分支：' + str(branch))
    if board not in ('6s', '4pro') or chip not in ('rtl8852', 'ap6275p'):
        raise RuntimeError('无法确定机型或无线芯片')
    if board == '6s' and chip != 'rtl8852':
        raise RuntimeError('6S 机型与无线芯片不匹配')
    key = branch + '/' + board + ('/' + chip if board == '4pro' else '')
    if key not in PROFILE_IDS:
        raise RuntimeError('尚未提供该组合的修复包：' + key)
    return key


class AndroidIdentityUnavailable(RuntimeError):
    pass


def android_board():
    models = set()
    for path in ANDROID_PROPERTIES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            key, sep, value = line.partition('=')
            if sep and re.fullmatch(r'ro\.product\.(?:[\w]+\.)?model', key.strip()):
                if value.strip():
                    models.add(value.strip())
    if not models:
        helper = Path(__file__).resolve().parents[1] / 'emmc/read_hardware_model.py'
        try:
            result = subprocess.run([sys.executable, str(helper)], capture_output=True,
                                    encoding='utf-8', timeout=150,
                                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AndroidIdentityUnavailable('原厂机型读取失败：' + str(exc)) from exc
        if result.returncode:
            raise AndroidIdentityUnavailable('原厂机型读取失败：' + result.stderr.strip())
        try:
            values = json.loads(result.stdout)
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError('invalid model list')
            models = {v.strip() for v in values if v.strip()}
        except (ValueError, TypeError) as exc:
            raise AndroidIdentityUnavailable('原厂机型读取结果无效') from exc
    if not models:
        raise AndroidIdentityUnavailable('未找到原厂 Android 机型')
    if len(models) != 1:
        raise RuntimeError('Android 机型信息冲突：' + ', '.join(sorted(models)))
    model = next(iter(models))
    if model not in BOARD_MODELS:
        raise RuntimeError('不支持的原厂 Android 机型：' + model)
    return BOARD_MODELS[model]


def soc_revision():
    if not CPUINFO.is_file():
        return ''
    # The Serial field carries the SMC chip ID, not the per-core ARM revision.
    match = re.search(r'^Serial\s*:\s*([0-9a-fA-F]{32})\s*$',
                      CPUINFO.read_text(encoding='utf-8', errors='replace'), re.MULTILINE)
    if not match:
        return ''
    chipid = bytes.fromhex(match.group(1))
    if chipid[0] != 0x32 or chipid[2] & 0x0f != 2:
        return ''
    return '%X' % chipid[1]


def pci_chip():
    chips = set()
    for path in PCI.glob('*'):
        try:
            ident = (int((path/'vendor').read_text(encoding='utf-8'), 16), int((path/'device').read_text(encoding='utf-8'), 16))
        except (OSError, ValueError):
            continue
        chip = {(0x14e4, 0x449d): 'ap6275p', (0x10ec, 0xb852): 'rtl8852'}.get(ident)
        if chip:
            chips.add(chip)
    if len(chips) > 1:
        raise RuntimeError('发现多种板载无线芯片，无法选择修复包')
    return next(iter(chips), '')


def text_property(name):
    p = DT / name
    return p.read_bytes().rstrip(b'\0').decode(errors='replace') if p.exists() else ''


def check_ng_kernel():
    # A build date is not a module ABI. insmod still enforces vermagic and CRCs.
    if platform.release() != NG_RELEASE:
        raise RuntimeError('NG 驱动要求 4.9.269 / aarch64 内核')
    # NG has 32-bit userspace: Python uname may report armv7l on an ARM64 kernel.
    with gzip.open(KERNEL_CONFIG, 'rt', encoding='utf-8') as source:
        config = set(source.read().splitlines())
    if not set(NG_FLAGS).issubset(config):
        raise RuntimeError('NG 内核模块配置不匹配，需要 ARM64/SMP/PREEMPT/MODULE_UNLOAD/MODVERSIONS')


def detect(confirmed_6s=False, allow_unidentified=False, check_kernel=True, confirmed_board=None, runtime_profile=False):
    data = {}
    for line in RELEASE.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            values = shlex.split(v)
            data[k] = values[0] if len(values) == 1 else v
    if data.get('ID') != 'coreelec':
        raise RuntimeError('仅支持 CoreELEC 系统')
    variants = {data[k] for k in ('DISTRO_DEVICE', 'COREELEC_DEVICE') if data.get(k)}
    for key in ('DISTRO_ARCH', 'COREELEC_ARCH', 'LIBREELEC_ARCH'):
        if data.get(key):
            variants.add(data[key].split('.')[0])
    if len(variants) != 1 or next(iter(variants)) not in ('Amlogic-ng', 'Amlogic-no'):
        raise RuntimeError('无法确定 Amlogic-ng / Amlogic-no 分支，拒绝部署')
    branch = next(iter(variants)).split('-')[-1]
    version = data.get('VERSION_ID', '')
    if branch == 'ng' and version.split('.')[0] != '21':
        raise RuntimeError('NG 修复包支持 CoreELEC 21.x，请勿用于其他大版本')
    if branch == 'no' and version.split('.')[0] != '22':
        raise RuntimeError('NO 修复包仅验证 CoreELEC 22')
    if branch == 'ng' and check_kernel:
        check_ng_kernel()
    compatible = text_property('compatible').replace(' ', '').split('\0')
    if 'amlogic,sc2' not in compatible:
        raise RuntimeError('硬件平台不匹配：需要极光 4 Pro / 6S 的 SC2 平台')
    ident = text_property('coreelec-dt-id')
    model = text_property('model')
    if runtime_profile:
        # LED control consumes an already-installed board DTB. It neither selects
        # nor installs a repair payload and must not depend on Android mounts.
        for key, dtid in PROFILE_IDS.items():
            if key.startswith(branch + '/') and (ident == dtid or
                    (branch == 'no' and ident == dtid.removesuffix('_hs400'))):
                parts = key.split('/')
                board = parts[1]
                chip = parts[2] if len(parts) == 3 else 'rtl8852'
                return dict(branch=branch, version=version, model=model, dt_id=ident,
                            board=board, chip=chip, soc_revision='', payload=key,
                            expected_dt_id=dtid, board_source='installed_dtb',
                            chip_source='installed_dtb', board_verified=False,
                            confirmation_required=False, identity_error='',
                            model_choice_required=False)
        raise RuntimeError('请先安装对应机型的硬件修复并重启：当前 DTB 未提供已知灯控配置')
    identity_error = ''
    try:
        board = android_board()
    except AndroidIdentityUnavailable as exc:
        board, identity_error = '', str(exc)
    source = 'android' if board else ''
    revision, actual_chip = soc_revision(), pci_chip()
    model_choice_required = board == '4pro' and revision == 'D'
    confirmed = confirmed_board or ('6s' if confirmed_6s else None)
    if confirmed_6s and confirmed_board not in (None, '6s'):
        raise RuntimeError('手动确认的机型冲突')
    if confirmed and confirmed not in ('6s', '4pro'):
        raise RuntimeError('未知确认机型')
    if board and confirmed and board != confirmed and not model_choice_required:
        raise RuntimeError('手动确认与 Android 机型不匹配')
    known = bool(board)
    if model_choice_required:
        board, source, known = '', '', False
    if not board and confirmed:
        board, source = confirmed, 'manual'
    if not board and not allow_unidentified:
        message = '需先明确确认实物为极光 4 Pro（A4111）或 6S（A4112）'
        if identity_error:
            message += '\n' + identity_error
        raise RuntimeError(message)
    chip, chip_source = '', ''
    if board:
        # Revision is only a fallback: A4111 rev B with RTL8852BE exists.
        # An enumerated supported PCI ID takes precedence.
        expected = ('rtl8852' if board == '6s' or revision == 'D'
                    else 'ap6275p' if revision in ('A', 'B', 'C') else '')
        chip = actual_chip or expected
        chip_source = 'pci' if actual_chip else ('board' if board == '6s' else 'soc_revision')
        if not chip:
            raise RuntimeError('无法确定 4 Pro 无线版本：需要 PCI ID 或 S905X4 rev A/B/C/D')
        key = payload_key(branch, board, chip)
    else:
        key = ''
    if os.geteuid() != 0:
        raise RuntimeError('需要 CoreELEC 的 root 权限')
    return dict(branch=branch, version=version, model=model, dt_id=ident,
                board=board, chip=chip, soc_revision=revision, payload=key,
                expected_dt_id=PROFILE_IDS.get(key, ''), board_source=source,
                chip_source=chip_source, board_verified=known, confirmation_required=not known,
                identity_error=identity_error, model_choice_required=model_choice_required)
