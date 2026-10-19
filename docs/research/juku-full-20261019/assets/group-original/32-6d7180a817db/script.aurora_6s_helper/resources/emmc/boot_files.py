"""Recursive boot-file inventories shared by staging, sizing and readback."""
import os
from pathlib import Path, PurePosixPath
import stat

BOOT_REQUIRED = {'kernel.img', 'SYSTEM', 'dtb.img', 'config.ini', 'cfgload'}
LEGACY_BOOT_ALLOWED = BOOT_REQUIRED | {'resolution.ini', 'dovi.ko', 'kernel.img.md5', 'SYSTEM.md5', 'dtb.xml'}
# NG updates replay aml_autoscript setenv lines, resetting our eMMC scanner.
# Internal CE already has its environment configured by the installer.
BOOT_EXCLUDES = ['device_trees', 'aml_autoscript']


def required_boot_names(names):
    """Resolve only kernel.img case-insensitively; keep actual source spelling."""
    names = list(names)
    kernels = [name for name in names if name.casefold() == 'kernel.img']
    if len(kernels) > 1:
        raise ValueError('启动文件名在 FAT32 上大小写冲突：' + ', '.join(kernels))
    resolved = {name: name for name in BOOT_REQUIRED if name in names and name != 'kernel.img'}
    if kernels:
        resolved['kernel.img'] = kernels[0]
    missing = BOOT_REQUIRED - resolved.keys()
    if missing:
        raise ValueError('缺少 CE 必需启动文件：' + ', '.join(sorted(missing)))
    return resolved


def relative_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\0' in name
            or PurePosixPath(name).is_absolute() or any(x in ('', '.', '..') for x in name.split('/'))):
        raise ValueError('无效的启动文件相对路径：' + repr(name))
    for part in name.split('/'):
        if (any(ord(c) < 32 or c in '*?<>|":' for c in part)
                or part.endswith((' ', '.'))):
            raise ValueError('启动文件名不能写入 FAT32（可能存在乱码）：' + repr(name))
        try:
            length = len(part.encode('utf-16-le')) // 2
        except UnicodeEncodeError:
            raise ValueError('启动文件名编码无效：' + repr(name)) from None
        if length > 255:
            raise ValueError('启动文件名超过 FAT32 长度限制：' + repr(name))
    return name


def scan_boot(root, exclude_device_trees=False):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('启动文件目录无效：' + str(root))
    device = root.stat().st_dev
    files, directories = {}, []

    def visit(folder):
        seen = set()
        for path in sorted(folder.iterdir()):
            name = path.relative_to(root).as_posix()
            if exclude_device_trees and name in BOOT_EXCLUDES:
                continue
            relative_name(name)
            folded = path.name.casefold()
            if folded in seen:
                raise ValueError('启动文件名在 FAT32 上大小写冲突：' + name)
            seen.add(folded)
            info = path.lstat()
            if info.st_dev != device or path.is_mount():
                raise ValueError('启动目录中存在额外挂载：' + str(path))
            if stat.S_ISDIR(info.st_mode):
                directories.append(name)
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                files[name] = info.st_size
            else:
                raise ValueError('启动目录含符号链接或特殊文件：' + str(path))
    visit(root)
    return files, sorted(directories)


def check_boot_capacity(files, directories, partition_bytes=1024**3):
    # Conservative FAT allocation estimate, including empty directories and
    # long file-name entries. Keep the existing 900 MiB ceiling for 1 GiB boot.
    unit = 64 * 1024
    allocated = sum(((size + unit - 1) // unit) * unit for size in files.values())
    allocated += sum(len(Path(name).name.encode('utf-16-le')) // 2 * 32 + 64 for name in [*files, *directories])
    allocated += (len(directories) + 1) * unit
    limit = min(900 * 1024**2, max(0, partition_bytes - 100 * 1024**2))
    if allocated > limit:
        raise ValueError('CE 启动文件超过预留容量：预计占用 %.1f MiB，可用上限 %.1f MiB' %
                         (allocated / 1024**2, limit / 1024**2))
    return allocated


def boot_manifest_inventory(manifest):
    rows = manifest['boot_files']
    names = [relative_name(row['file']) for row in rows]
    directories = manifest.get('boot_directories', [])
    for name in directories:
        relative_name(name)
    if (len(set(names)) != len(names) or len(set(directories)) != len(directories)
            or set(names) & set(directories)):
        raise ValueError('启动文件清单不完整或存在重复路径')
    resolved = required_boot_names(names)
    if len({name.casefold() for name in names + directories}) != len(names + directories):
        raise ValueError('启动文件名在 FAT32 上大小写冲突')
    if manifest.get('schema') == 3:
        if manifest.get('boot_excludes') != BOOT_EXCLUDES or 'boot_directories' not in manifest:
            raise ValueError('启动文件排除规则不匹配')
        if any(name.split('/')[0] in BOOT_EXCLUDES for name in names + directories):
            raise ValueError('启动文件清单包含已排除文件或目录')
    elif manifest.get('schema') in (1, 2):
        if directories or not {('kernel.img' if n == resolved['kernel.img'] else n) for n in names} <= LEGACY_BOOT_ALLOWED:
            raise ValueError('旧版启动文件清单不匹配')
    else:
        raise ValueError('未知启动文件清单版本')
    for name in names + directories:
        parent = PurePosixPath(name).parent.as_posix()
        if parent != '.' and parent not in directories:
            raise ValueError('启动文件清单缺少父目录：' + name)
    sizes = {row['file']: row['bytes'] for row in rows}
    if any(type(size) is not int or size < 0 for size in sizes.values()):
        raise ValueError('启动文件大小无效')
    return sizes, sorted(directories)


def verify_boot_tree(root, manifest):
    expected = boot_manifest_inventory(manifest)
    if scan_boot(root) != expected:
        raise ValueError('启动目录的文件、大小或目录清单发生变化')
