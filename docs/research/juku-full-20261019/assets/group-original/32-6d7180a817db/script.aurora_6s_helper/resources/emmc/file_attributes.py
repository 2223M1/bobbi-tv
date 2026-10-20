"""Preserve Linux extended attributes when the system rsync lacks -A/-X."""
import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ignored_attribute_names():
    """CE without an active SELinux subsystem does not use inherited labels.

    Permissive SELinux is still active: keep its labels. Unknown OS / unreadable
    runtime evidence falls back to preserving every attribute.
    """
    try:
        release=Path('/etc/os-release').read_text()
        values=dict(line.split('=',1) for line in release.splitlines()
                    if '=' in line and not line.startswith('#'))
        if values.get('ID','').strip('"\'')!='coreelec':return ()
        if any(Path(p).exists() for p in ('/sys/fs/selinux/enforce','/selinux/enforce')):return ()
        lsm=Path('/sys/kernel/security/lsm')
        if lsm.exists() and 'selinux' in lsm.read_text().strip().split(','):return ()
        mounts=Path('/proc/self/mountinfo').read_text()
        if any(' - selinuxfs ' in line for line in mounts.splitlines()):return ()
    except OSError:
        return ()
    return ('security.selinux',)


def rsync_xattr_filters(flags):
    # Keep the native -X path consistent with the Python fallback and inventory.
    return ['--filter=-x '+name for name in ignored_attribute_names()] if 'X' in flags else []


def attributes(path):
    return {name:os.getxattr(path,name,follow_symlinks=False).hex()
            for name in sorted(os.listxattr(path,follow_symlinks=False))
            if name not in ignored_attribute_names()}


def copy_attributes(source,dest,update=None):
    source=Path(source);dest=Path(dest)
    if source.is_symlink() or dest.is_symlink():raise ValueError('Unsafe attribute-copy root')
    def copy(relative):
        src=source/relative;dst=dest/relative
        if src.is_symlink()!=dst.is_symlink():raise ValueError('属性复制时文件类型不一致：'+str(relative))
        wanted=attributes(src);existing=attributes(dst)
        for name in existing.keys()-wanted.keys():
            try:os.removexattr(dst,name,follow_symlinks=False)
            except OSError as exc:
                raise OSError(exc.errno,'移除扩展属性 '+name+' 失败：'+str(exc),str(dst)) from exc
        for name,value in wanted.items():
            if existing.get(name)!=value:
                try:os.setxattr(dst,name,bytes.fromhex(value),follow_symlinks=False)
                except OSError as exc:
                    raise OSError(exc.errno,'复制扩展属性 '+name+' 失败：'+str(exc),str(dst)) from exc
        if attributes(dst)!=wanted:raise ValueError('扩展属性读回不一致：'+str(relative))
    if update and ignored_attribute_names():
        update('copying','CE 未启用 SELinux，忽略 security.selinux 标签；其余扩展属性仍逐项核对')
    # Walk the copied destination: excluded files must not be resurrected.
    copy(Path('.'));count=0
    def fail(error):raise error
    for base,dirs,files in os.walk(dest,followlinks=False,onerror=fail):
        if Path(base)==dest:dirs[:]=[n for n in dirs if n!='lost+found']
        for name in dirs+files:
            copy((Path(base)/name).relative_to(dest));count+=1
            if update and count%100==0:update('copying','复制并核对扩展属性：%d 项'%count)
    if update:update('copying','扩展属性复制与核对完成')
