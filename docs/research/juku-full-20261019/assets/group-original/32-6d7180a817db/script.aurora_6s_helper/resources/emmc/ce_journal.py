"""Bounded CE ext4 journal replay during an explicitly confirmed repair.

Never replay Android userdata, run a general writable fsck, or auto-undo.
The worker owns the device locks. Undo data is not a power-loss-safe backup.
"""
import hashlib
import os
from pathlib import Path
import shutil
import struct

import operations as op
import policy
import ota_repair as layout
from layout_trial import atomic_json, private_external


def inspect_super(raw, row):
    if (row['name'] != 'ce_storage' or len(raw) != 1024 or
            raw[56:58] != b'\x53\xef' or
            raw[120:136].rstrip(b'\0') != b'CE_AURORA_DATA'):
        raise ValueError('CE 日志恢复：文件系统身份不匹配')
    u32 = lambda off: struct.unpack_from('<I', raw, off)[0]
    compat, incompat = u32(92), u32(96)
    blocks = u32(4) | ((u32(336) << 32) if incompat & 0x80 else 0)
    if u32(24) != 2 or blocks * 4096 != row['size']:
        raise ValueError('CE 日志恢复：文件系统长度与分区不一致')
    if not incompat & 4:
        return False
    if (not compat & 4 or incompat & 8 or u32(224) == 0 or u32(228) != 0
            or any(raw[208:224])):
        raise ValueError('CE 日志恢复：仅支持分区内置 ext4 日志')
    if struct.unpack_from('<H', raw, 58)[0] & 2:
        raise ValueError('CE 文件系统已标记错误，不能只按未正常卸载处理')
    return True


def replay_if_needed(folder, report, target, update):
    row = target[-2]
    # This target was validated by dual_repair.assess, not supplied by the UI.
    if row != report['ota_repair']['partitions'][-2]:
        raise ValueError('CE 日志恢复范围已改变')
    policy.identity(report)
    policy.bounded_region(row, report['emmc_bytes'], report['mpt']['partitions'][28]['offset'])
    before = layout.read_at(row['offset'] + 1024, 1024)
    if not inspect_super(before, row):
        return False
    op.same_device(report, op.probe(repair_identity=True))
    op.external(report)
    op.target_idle(report)
    if not shutil.which('e2fsck'):
        raise ValueError('缺少 e2fsck，不能恢复 CE 文件系统日志')
    # Verify recognizable CE data without replaying or mounting it writable.
    with layout.mounted(row, report, 'ext4') as (root, _):
        if not (root/'.kodi').is_dir() or not (root/'.config').is_dir():
            raise ValueError('CE 日志恢复：缺少 CE 数据目录')
    folder = Path(folder)/'ce-journal'
    folder.mkdir(mode=0o700)
    private_external(folder)
    free = os.statvfs(folder)
    if free.f_bavail * free.f_frsize < 1024**3:
        raise ValueError('CE 日志恢复需要外置盘至少 1 GiB 可用空间，用于撤销记录')
    layout.store(folder/'before-superblock.bin', before)
    plan = {'cid': report['cid'], 'emmc_bytes': report['emmc_bytes'],
            'partition': row, 'superblock_sha256': hashlib.sha256(before).hexdigest(),
            'method': 'e2fsck journal_only with undo',
            'note': 'Undo is not a full backup; never apply after subsequent filesystem use.'}
    atomic_json(folder/'plan.json', plan)
    # A readonly preliminary result remains useful even if journal replay fails.
    with op.region_loop(row, report, readonly=True) as dev:
        layout.require_readonly(dev)
        p = layout.run_fsck(['e2fsck', '-f', '-n', str(dev)], update, row['name'])
        layout.store(folder/'before-check.log', p.stdout + p.stderr)
        if p.returncode not in (0, 4):
            raise ValueError('CE 文件系统检查工具异常，未回放日志；请查看任务日志')
    op.same_device(report, op.probe(repair_identity=True))
    op.external(report)
    op.target_idle(report)
    if layout.read_at(row['offset'] + 1024, 1024) != before:
        raise ValueError('CE 文件系统在检查期间发生变化，未回放日志')
    atomic_json(folder/'status.json', {'phase': 'prepared', 'device_writes_started': False})
    undo = folder/'journal.e2undo'
    with op.region_loop(row, report, readonly=False) as dev:
        # The branch backend verifies backing device, offset and size.
        update('repair-writing', '恢复 CE 文件系统日志；不要取消、断电或操作设备', device_writes_started=True)
        atomic_json(folder/'status.json', {'phase': 'replaying', 'device_writes_started': True})
        p = layout.run_fsck(['e2fsck', '-p', '-E', 'journal_only', '-z', str(undo), str(dev)],
                            update, row['name'], writing=True)
        layout.store(folder/'replay.log', p.stdout + p.stderr)
        os.sync()
        if p.returncode not in (0, 1) or not undo.is_file() or undo.stat().st_size == 0:
            raise ValueError('CE 日志恢复未完成，已停止后续分区修复；请保留任务中的 ce-journal 记录')
    after = layout.read_at(row['offset'] + 1024, 1024)
    if inspect_super(after, row):
        raise ValueError('CE 日志恢复标志未清除，停止后续修复')
    with op.region_loop(row, report, readonly=True) as dev:
        layout.require_readonly(dev)
        p = layout.run_fsck(['e2fsck', '-f', '-n', str(dev)], update, row['name'])
        layout.store(folder/'after-check.log', p.stdout + p.stderr)
        if p.returncode:
            raise ValueError('CE 日志回放后文件系统仍未通过检查，未继续修复分区布局；请保留 ce-journal 记录')
    atomic_json(folder/'status.json', {'phase': 'complete', 'device_writes_started': True,
                                      'readonly_check_exit': 0, 'undo_bytes': undo.stat().st_size})
    return True
