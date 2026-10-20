"""Pure layout/identity rules shared by preview, writer and offline tests."""
import copy
import hashlib
import re
import struct
from aurora_emmc import plan, parse_mpt, MIB, GIB
from layout_trial import fdt
from extract_recovery_metadata import validate_dtb_slots
from prepare_boot_environment import BOOTCMD, scan_through

MODELS = ('A4111', 'A4112')
FIELDS = ('index', 'name', 'offset', 'size', 'flags')
FIRST_FLAGS = [0, 0, 0, 0, 1, 17, 1, 1, 1, 1, 1, 1, 1, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
DISCLAIMER = '安装或移除双系统会重置 Android，清空应用、账号和用户数据。操作存在数据丢失、无法启动及设备损坏风险。插件作者不对刷双系统或备份还原造成的任何损失负责。'
RESTORE_WARNING = '还原将覆盖整块 eMMC 及 boot0/boot1，当前 CE、Android 和用户数据将被备份中的内容替换。安装/移除会重置 Android；还原不保留备份之后的数据，也不保证恢复加密数据。插件作者不对此操作造成的任何损失负责。'

def identity(report):
    if report.get('android_models') not in ([MODELS[0]], [MODELS[1]]):
        raise ValueError('必须从原厂 Android 属性明确识别为 A4111 或 A4112；不接受借用 DTB 或手动机型覆盖')
    osr = report['os_release']
    from platform_support import branch
    branch(osr)
    if not re.fullmatch(r'[0-9a-fA-F]{32}', report.get('cid', '')):
        raise ValueError('无法确认 eMMC CID')
    if set(report['boot_areas']) != {'mmcblk0boot0', 'mmcblk0boot1'} or any(n <= 0 for n in report['boot_areas'].values()):
        raise ValueError('无法确认两个 eMMC 硬件 boot 区')
    return report['android_models'][0]


def layouts(report):
    """Accept stock or a bounded dual layout with the tested order and gaps."""
    rows = report['mpt']['partitions']; original = copy.deepcopy(report)
    if len(rows) not in (29, 31) or not all(r.get('sysfs_matches') for r in rows):
        raise ValueError('未知分区布局或内核边界与 MPT 不一致')
    if [r['flags'] for r in rows[:28]] != FIRST_FLAGS:
        raise ValueError('原厂系统分区标志与支持的布局不一致')
    start = rows[27]['offset'] + rows[27]['size'] + 8*MIB
    stock = copy.deepcopy(rows[:28]) + [dict(index=29, name='userdata', offset=start,
        size=report['emmc_bytes']-start, flags=4, padding=0, sysfs_matches=True)]
    original['mpt']['partitions'] = stock
    original['blockers'] = []
    ce_bytes = rows[29]['size'] if len(rows) == 31 else 20*GIB
    if type(ce_bytes) is not int or ce_bytes < 4*GIB:
        raise ValueError('CE 数据区至少需要 4 GiB')
    dual = plan(original, 20, 1024, 'reset-data', 16, ce_bytes=ce_bytes)['partitions']
    expected = stock if len(rows) == 29 else dual
    if [[r[k] for k in FIELDS] for r in rows] != [[r[k] for k in FIELDS] for r in expected]:
        raise ValueError('仅支持原厂布局或本助手的 CE 启动区 / CE 数据区 / Android 用户区布局')
    if dual[-1]['size'] < 8*GIB:
        raise ValueError('空间不足：需为 Android 保留至少 8 GiB')
    return ('stock' if len(rows) == 29 else 'dual'), stock, dual


def install_layout(report, android_gib):
    if type(android_gib) is not int or android_gib < 8:
        raise ValueError('Android 用户数据空间必须为至少 8 GiB 的整数')
    _, stock, _ = layouts(report)
    # Keep the tested partition order; Android remains the final fill-to-end row.
    ce_bytes = stock[-1]['size'] - GIB - 16*MIB - android_gib*GIB
    if ce_bytes < 4*GIB:
        raise ValueError('剩余 CE 数据区不足 4 GiB')
    original = copy.deepcopy(report)
    original['mpt']['partitions'] = stock
    original['blockers'] = []
    return plan(original, 20, 1024, 'reset-data', android_gib, ce_bytes=ce_bytes)['partitions']


def ce_data_limit(size):
    # Allow for ext4 overhead and free working space, including on larger volumes.
    return size - max(2*GIB, (size+9)//10)


def capacity_choices(report, usage):
    _, stock, _ = layouts(report)
    maximum = (stock[-1]['size'] - GIB - 16*MIB - 4*GIB)//GIB
    choices = []
    for android_gib in range(8, maximum+1):
        rows = install_layout(report, android_gib)
        size = rows[29]['size']
        if usage <= ce_data_limit(size):
            choices.append(dict(android_gib=android_gib, ce_storage_bytes=size))
    if not choices:
        raise ValueError('空间不足：无法同时容纳当前 CE 数据及余量、CE 启动区和至少 8 GiB Android 用户区')
    return choices


def validate_dtb_layout(raw, rows):
    validate_dtb_slots(raw)
    first = None
    for offset in (0, 262144):
        nodes, header = fdt(raw[offset:offset+262144])
        if first is not None and nodes != first:
            raise ValueError('原厂 DTB 双副本内容不一致')
        first = nodes
        parts = nodes['/partitions']; explicit = rows[4:]
        if struct.unpack('>I', parts['parts'])[0] != len(explicit):
            raise ValueError('DTB 分区数与 MPT 不一致')
        handles = {}
        for path, props in nodes.items():
            if 'phandle' in props:
                if props['phandle'] in handles:raise ValueError('重复 DTB phandle')
                handles[props['phandle']] = path
        for i, row in enumerate(explicit):
            path = handles[parts['part-'+str(i)]]; props = nodes[path]
            wanted = 0xffffffffffffffff if i == len(explicit)-1 else row['size']
            if (path != '/partitions/'+row['name'] or props['pname'] != row['name'].encode()+b'\0'
                    or props['size'] != struct.pack('>Q', wanted) or props['mask'] != struct.pack('>I', row['flags'])):
                raise ValueError('DTB 分区内容与 MPT 不一致：'+row['name'])
    return first, header


def metadata_check(old_dtb, new_dtb, new_mpt, report, target):
    old, header = validate_dtb_layout(old_dtb, report['mpt']['partitions'])
    new, newheader = validate_dtb_layout(new_dtb, target)
    without_parts = lambda nodes: {k:v for k,v in nodes.items() if k != '/partitions' and not k.startswith('/partitions/')}
    if header != newheader or without_parts(old) != without_parts(new):
        raise ValueError('候选 DTB 改变了分区以外的硬件属性')
    for offset in (0, 262144):
        if new_dtb[offset+262128:offset+262136] != old_dtb[offset+262128:offset+262136]:
            raise ValueError('DTB 尾部格式发生变化')
    actual = parse_mpt(new_mpt, report['emmc_bytes'])['partitions']
    if [[r[k] for k in FIELDS] for r in actual] != [[r[k] for k in FIELDS] for r in target]:
        raise ValueError('生成的 MPT 与独立布局计算不一致')


def scanner(value):
    for count in (24, 29, 31):
        for source in (False, True):
            expected = scan_through(count)
            if source:expected = expected.replace('autoscr ${loadaddr}', 'source ${loadaddr}; autoscr ${loadaddr}')
            if value == expected:return count, source
    raise ValueError('未知 eMMC 启动扫描脚本，拒绝覆盖')


def environment_change(env, action):
    if env.get('bootcmd') != BOOTCMD or env.get('bootfromemmc') != 'run cfgloademmc' or env.get('bootfromnand') != '0':
        raise ValueError('外置优先 / Android 启动选择逻辑与支持的环境不一致')
    # The vendor storeboot resolves the boot slot at runtime via get_valid_slot.
    # Accept its persisted normal default; never select or rewrite a slot here.
    if env.get('active_slot') not in ('normal', '_a', '_b') or 'get_valid_slot' not in env.get('storeboot', '') or 'imgread kernel ${boot_part}' not in env.get('storeboot', ''):
        raise ValueError('无法确认原厂 Android A/B 引导入口')
    _, source = scanner(env['cfgloademmc'])
    new = scan_through(29 if action == 'install' else 24)
    if source:new = new.replace('autoscr ${loadaddr}', 'source ${loadaddr}; autoscr ${loadaddr}')
    return new


def backup_matches(report, saved):
    for key in ('cid', 'emmc_bytes', 'boot_areas', 'android_models'):
        if not saved.get(key) or saved[key] != report[key]:
            raise ValueError('备份与本机身份/容量不匹配：'+key)


def confirmation(action, reset, risk):
    if action == 'repair':
        if not risk:raise ValueError('必须确认布局修复风险和免责说明')
        return
    if action not in ('install', 'remove', 'backup', 'restore'):raise ValueError('未知操作')
    if action != 'backup' and not (reset and risk):
        raise ValueError('必须确认 Android 数据重置/覆盖和免责说明')


def bounded_region(row, capacity, tail_start):
    if row['name'] not in ('ce_system', 'ce_storage', 'userdata'):
        raise ValueError('禁止格式化系统/身份分区')
    off, size = row['offset'], row['size']
    if off < tail_start or size <= 0 or (off|size) % 512 or off+size > capacity:
        raise ValueError('目标映射超出已验证的用户区范围')
    return off, size
