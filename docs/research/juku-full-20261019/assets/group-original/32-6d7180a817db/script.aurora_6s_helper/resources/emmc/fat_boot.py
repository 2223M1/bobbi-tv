"""Read the boot FAT through a private, read-only UTF-8 loop mount.

A bind mount shares the original FAT charset; a separate read-only loop gives
us a separate superblock without remounting the live /flash used by Kodi.
"""
import contextlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

FAT_RW_OPTIONS = 'rw,noatime,utf8=1'
FAT_RO_OPTIONS = 'ro,noatime,utf8=1'


def command(args):
    result = subprocess.run(args, capture_output=True, encoding='utf-8',
                            errors='replace', timeout=30)
    if result.returncode:
        raise RuntimeError('启动分区 UTF-8 挂载操作失败：' + repr(args) + '\n' + result.stderr)
    return result.stdout.strip()


def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def mount_record(path):
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        fields, fs = left.split(), right.split()
        if unescape(fields[4]) == str(path):
            return dict(device=fields[2], root=unescape(fields[3]),
                        options=set(fields[5].split(',')), filesystem=fs[0],
                        source=unescape(fs[1]), super_options=set(fs[2].split(',')))
    raise ValueError('找不到启动分区挂载：' + str(path))


@contextlib.contextmanager
def boot_source(root):
    root = Path(root)
    # Ordinary directories are used for local unit tests and staged snapshots.
    if root != Path('/flash') and not root.is_mount():
        yield root
        return
    original = mount_record(root)
    if (original['filesystem'] != 'vfat' or original['root'] != '/'
            or 'ro' not in original['options'] or root.is_symlink()):
        raise ValueError('/flash 必须是只读 FAT 启动分区，才能安全读取中文文件名')
    source = Path(original['source'])
    info = source.stat()
    if (not stat.S_ISBLK(info.st_mode) or info.st_rdev != root.stat().st_dev
            or original['device'] != '%d:%d' % (os.major(info.st_rdev), os.minor(info.st_rdev))):
        raise ValueError('/flash 块设备与挂载记录不一致')
    view = Path(tempfile.mkdtemp(prefix='aurora-boot-utf8-', dir='/run'))
    try:
        loop = command(['losetup', '--find', '--show', '--read-only', str(source)])
        if not re.fullmatch(r'/dev/loop\d+', loop):
            raise ValueError('无法确认启动分区只读 loop 设备')
        mounted = False
        try:
            if Path('/sys/class/block/' + Path(loop).name + '/ro').read_text().strip() != '1':
                raise ValueError('启动分区 loop 不是只读设备')
            command(['mount', '-t', 'vfat', '-o', FAT_RO_OPTIONS, loop, str(view)])
            mounted = True
            actual = mount_record(view)
            if ('ro' not in actual['options'] or 'utf8' not in actual['super_options']
                    or view.stat().st_dev != Path(loop).stat().st_rdev):
                raise ValueError('启动分区 UTF-8 只读挂载未生效')
            if mount_record(root) != original:
                raise ValueError('/flash 挂载在读取期间发生变化')
            yield view
        finally:
            # Never remove a mount directory or detach a loop after failed umount.
            if mounted or view.is_mount():
                command(['umount', str(view)])
            command(['losetup', '-d', loop])
    finally:
        # rmdir cannot traverse a still-mounted source on cleanup failure.
        if not view.is_mount():
            view.rmdir()
