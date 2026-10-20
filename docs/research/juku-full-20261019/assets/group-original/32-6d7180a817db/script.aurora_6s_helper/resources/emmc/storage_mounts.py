"""Copy storage without persisting the wake service's runtime firmware overlay."""
import contextlib
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from fat_boot import unescape

TARGET = Path('.config/firmware/rtlbt/rtl8852bs_config')
SOURCE = Path('.config/aurora6s-wake/rtl8852bs_config.wake')
CONFIG_HASH = 'f60918c29e31671593ce38bb3870ffe83be9c2c82d232dd3c3f5d75cd89cecf2'
WAKE_HASH = '9b9280df7260f749e5ddbe506fccc27d4ba88d3281ccf766cf112998e006561c'


def command(args):
    result = subprocess.run(args, capture_output=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise RuntimeError('storage 复制视图操作失败：' + repr(args) + '\n' + result.stderr)


def records():
    result = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        fields, fs = left.split(), right.split()
        result.append(dict(id=fields[0], device=fields[2], root=unescape(fields[3]),
                           path=unescape(fields[4]), options=fields[5].split(','), fs=fs[0]))
    return result


def digest(path):
    if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('蓝牙配置路径不是普通文件：' + str(path))
    with path.open('rb') as source:
        data = source.read(4097)
    if len(data) > 4096:
        raise ValueError('蓝牙配置大小异常：' + str(path))
    return hashlib.sha256(data).hexdigest()


def check_mounts(root):
    root = Path(root)
    rows = records()
    nested = [r for r in rows if r['path'].startswith(str(root)+'/')]
    if not nested:
        return False
    roots = [r for r in rows if r['path'] == str(root)]
    for row in nested:
        valid = (len(roots) == 1
                 and row['path'] == str(root/TARGET)
                 and roots[0]['root'] == '/' and roots[0]['fs'] == row['fs'] == 'ext4'
                 and row['device'] == roots[0]['device']
                 and row['root'] == '/'+str(SOURCE))
        if not valid:
            raise ValueError('Nested storage mount requires review: ' + row['path'])
    if len(nested) != 1:
        raise ValueError('Nested storage mount requires review: ' + str(root/TARGET))
    if (digest(root/SOURCE) != WAKE_HASH or digest(root/TARGET) != WAKE_HASH
            or not os.path.samefile(root/SOURCE, root/TARGET)):
        raise ValueError('蓝牙唤醒配置挂载与已知来源不一致：' + str(root/TARGET))
    return True


@contextlib.contextmanager
def storage_source(root=Path('/storage')):
    root = Path(root)
    if not check_mounts(root):
        yield root
        return
    # Non-recursive bind excludes child mounts, exposing the base config (0x18).
    # Never unmount the live overlay or stop/reset Bluetooth during migration.
    view = Path(tempfile.mkdtemp(prefix='aurora-storage-view-', dir='/run'))
    mounted = False
    try:
        command(['mount', '--bind', str(root), str(view)])
        mounted = True
        command(['mount', '--make-private', str(view)])
        command(['mount', '-o', 'remount,bind,ro', str(view)])
        rows = records()
        original = [r for r in rows if r['path'] == str(root)]
        actual = [r for r in rows if r['path'] == str(view)]
        if (len(original) != 1 or len(actual) != 1
                or any(r['path'].startswith(str(view)+'/') for r in rows)
                or 'ro' not in actual[0]['options']
                or any(actual[0][k] != original[0][k] for k in ('device','root','fs'))
                or root.stat().st_dev != view.stat().st_dev):
            raise ValueError('无法确认 storage 只读复制视图：' + str(view))
        if digest(view/TARGET) != CONFIG_HASH:
            raise ValueError('蓝牙挂载下的基础配置不是已核验版本：' + str(root/TARGET))
        check_mounts(root)
        yield view
    finally:
        if mounted:
            command(['umount', str(view)])
        view.rmdir()
