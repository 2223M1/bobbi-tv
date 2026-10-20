"""NG 21.x device access: dm-linear, raw identity checks and bounded env access."""
import contextlib
import os
from pathlib import Path
import stat
import struct
import fcntl
import tempfile
import uuid
import policy
from aurora_emmc import MIB


@contextlib.contextmanager
def region(op,off,size,readonly=False):
    with op.region_dm(off,size,readonly) as mapped:
        yield mapped


def checkpoint(op,report):
    op.raw_checkpoint(report)


@contextlib.contextmanager
def region_dm(op,off,size,readonly=False):
    """Use bounded dm-linear mappings for NG; do not depend on MPT nodes."""
    ident=os.stat(op.DISK)
    if not stat.S_ISBLK(ident.st_mode):raise ValueError('DM 后端必须为 eMMC 块设备')
    dev='%d:%d'%(os.major(ident.st_rdev),os.minor(ident.st_rdev))
    table=['0',str(size//512),'linear',dev,str(off//512)]
    name='aurora-region-'+uuid.uuid4().hex[:12]
    args=['dmsetup','create',name,'--table',' '.join(table)]
    if readonly:args+=['--readonly']
    op.run(args)
    try:
        if op.run(['dmsetup','table',name]).split()!=table:
            raise ValueError('DM 后端、偏移或长度核对失败')
        mapped=Path('/dev/mapper')/name
        with mapped.open('rb',buffering=0) as f:
            actual=struct.unpack('Q',fcntl.ioctl(f.fileno(),op.BLKGETSIZE64,b'\0'*8))[0]
        if actual!=size:raise ValueError('DM 容量与受限范围不一致')
        yield mapped
    finally:op.run(['dmsetup','remove','--retry',name])


def raw_checkpoint(op,report):
    """Revalidate whole-device identity after NG loses its kernel MPT nodes."""
    policy.identity(report)
    if (op.read('/sys/block/mmcblk0/device/cid')!=report['cid'] or
            int(op.read('/sys/block/mmcblk0/size'))*512!=report['emmc_bytes']):
        raise ValueError('写入后 eMMC 身份或容量发生变化')
    current={m['mountpoint']:m for m in op.mountinfo()}
    for name in ('/flash','/storage'):
        if name not in current or current[name]['dev']!=report['mounts'][name]['dev']:
            raise ValueError('操作期间外置启动盘发生变化')
    op.external(report)
    if list(Path('/sys/block/mmcblk0/holders').iterdir()):
        raise ValueError('eMMC 存在未释放的整盘映射')
    info=os.stat(op.DISK)
    if not stat.S_ISBLK(info.st_mode) or op.read('/sys/block/mmcblk0/dev')!='%d:%d'%(os.major(info.st_rdev),os.minor(info.st_rdev)):
        raise ValueError('eMMC 块设备节点不匹配')


@contextlib.contextmanager
def environment_options(op,report):
    op.raw_checkpoint(report)
    policy.layouts(report) # Validates the immutable original first 28 boundaries.
    row=report['mpt']['partitions'][3]
    if row['name']!='env' or row['size']!=8*MIB:raise ValueError('未知原厂 env 分区')
    # Amlogic's environment is 64 KiB at offset zero within its 8 MiB partition.
    # Pin this to the reviewed CE configuration, rather than guessing a format.
    entries=[line.split() for line in op.read('/etc/fw_env.config').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    emmc=[line for line in entries if line[0]=='/dev/env']
    if len(emmc)!=1 or len(emmc[0])!=4 or [int(x,0) for x in emmc[0][1:]]!=[0,65536,65536]:
        raise ValueError('未验证的 eMMC 引导环境配置')
    with op.region_dm(row['offset'],row['size']) as dev:
        with tempfile.TemporaryDirectory(prefix='aurora-env-') as folder:
            config=Path(folder)/'fw_env.config'
            config.write_text('%s 0x0 0x10000 0x10000\n'%dev)
            yield ['-c',str(config)]

