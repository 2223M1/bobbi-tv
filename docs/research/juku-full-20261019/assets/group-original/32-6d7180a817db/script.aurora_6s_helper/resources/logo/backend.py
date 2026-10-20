#!/usr/bin/env python3
"""Explicit Logo-only operations. No bootloader, environment or layout writes."""
import argparse
import contextlib
import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import time
import traceback

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'emmc'))
from aurora_emmc import parse_mpt, mountinfo
from read_hardware_model import read_models
from platform_support import branch
from block_device import BLKGETSIZE64
from layout_trial import atomic_json
from codec import PARTITION_SIZE, MAX_IMAGE, digest, gunzip, stock, unpack, boot_image, replace_boot
BASE=Path('/storage/.config/aurora-logo')
DEVICE='/dev/logo'


@contextlib.contextmanager
def locked():
    with contextlib.ExitStack() as stack:
        for name in ('submit','layout','backup'):
            f=stack.enter_context(open('/run/aurora-emmc-'+name+'.lock','a'))
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('已有 eMMC 或 Logo 操作正在进行，请稍后重试')
        from worker import status
        state=status()
        if state['phase'] not in ('none','complete','failed','cancelled'):
            raise ValueError('存在未完成或待检查的 eMMC 任务，请先处理任务状态')
        yield


def identify():
    release={}
    for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
        if '=' in line:
            k,v=line.split('=',1);release[k]=v.strip('"')
    variant=branch(release)
    models=read_models()
    if models not in (['A4111'],['A4112']):raise ValueError('只能在 Android 机型明确为 A4111/A4112 的设备上修改第一屏')
    disk=Path('/sys/block/mmcblk0');capacity=int((disk/'size').read_text())*512
    cid=(disk/'device/cid').read_text().strip()
    if not re.fullmatch('[0-9a-fA-F]{32}',cid):raise ValueError('无法确认 eMMC 身份')
    with open('/dev/mmcblk0','rb',buffering=0) as f:
        f.seek(36*1024**2);mpt=f.read(4096)
    rows=parse_mpt(mpt,capacity)['partitions'];logos=[r for r in rows if r['name']=='logo']
    if len(logos)!=1:raise ValueError('无法唯一定位 Logo 分区')
    row=logos[0];st=os.stat(DEVICE)
    if not stat.S_ISBLK(st.st_mode):raise ValueError('Logo 目标不是块设备')
    dev='%d:%d'%(os.major(st.st_rdev),os.minor(st.st_rdev));node=Path('/sys/dev/block/'+dev).resolve()
    if (node.parent!=disk.resolve() or node.name!='logo' or row['size']!=PARTITION_SIZE
        or int((node/'start').read_text())*512!=row['offset']
        or int((node/'size').read_text())*512!=row['size']):
        raise ValueError('Logo 分区与 eMMC 分区表边界不一致')
    if list((node/'holders').iterdir()) or any(m['dev']==dev for m in mountinfo()):
        raise ValueError('Logo 分区正在被挂载或映射使用')
    # Refuse writable aliases over the raw disk or the Logo partition.
    for loop in Path('/sys/block').glob('loop*/loop/backing_file'):
        target=Path(loop.read_text().strip())
        if target.exists() and target.is_block_device():
            alias=target.stat().st_rdev
            if alias in (st.st_rdev,os.stat('/dev/mmcblk0').st_rdev):raise ValueError('eMMC/Logo 正被 loop 映射使用')
    return dict(model=models[0],branch=variant,cid=cid,capacity=capacity,logo=row,
                dev=dev,mpt_sha256=digest(mpt),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())


def read_logo(fd=None):
    if fd is None:
        with open(DEVICE,'rb',buffering=0) as f:return read_logo(f.fileno())
    raw=os.pread(fd,PARTITION_SIZE,0)
    if len(raw)!=PARTITION_SIZE:raise ValueError('Logo 分区读取长度不足')
    return raw


def private_base():
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if BASE.resolve()!=BASE or BASE.is_symlink():raise ValueError('Logo 工作目录不能通过符号链接重定向')
    return BASE


def load_folder(value):
    root=private_base();folder=Path(value)
    if folder.parent!=root or folder.resolve()!=folder or not folder.is_dir():raise ValueError('无效的 Logo 任务目录')
    for name in ('plan.json','candidate.img','before.img.gz','status.json'):
        p=folder/name
        if p.is_symlink() or not p.is_file():raise ValueError('Logo 任务文件无效')
    return folder


def store(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if path.read_bytes()!=data:raise ValueError('Logo 暂存文件读回校验失败')


def prepare(mode,image=None):
    with locked():
        identity=identify();old=read_logo()
        if mode=='stock':candidate=stock(ROOT/'stock-logo.img.gz')
        elif mode=='custom':
            if image is None:raise ValueError('尚未选择图片')
            with open(image,'rb') as f:data=f.read(MAX_IMAGE+1)
            candidate=replace_boot(old,data)
        else:candidate=old
        # Decode before creating the task; invalid/custom formats fail without a write.
        preview=boot_image(candidate)
        root=private_base()
        free=os.statvfs(root)
        if free.f_bavail*free.f_frsize<32*1024**2:raise ValueError('保存 Logo 任务需至少 32 MiB 可用空间')
        folder=Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%dT%H%M%S')+'-',dir=root))
        store(folder/'before.img.gz',gzip.compress(old,mtime=0))
        if gunzip((folder/'before.img.gz').read_bytes(),PARTITION_SIZE)!=old:raise ValueError('Logo 备份校验失败')
        store(folder/'candidate.img',candidate)
        preview.save(folder/'preview.png')
        info=dict(identity=identity,mode=mode,old_sha256=digest(old),new_sha256=digest(candidate),
                  preview_sha256=digest((folder/'preview.png').read_bytes()))
        atomic_json(folder/'plan.json',info)
        atomic_json(folder/'status.json',dict(phase='prepared',device_writes_started=False))
        return dict(folder=str(folder),preview=str(folder/'preview.png'),model=identity['model'],
                    mode=mode,new_sha256=info['new_sha256'],backup=str(folder/'before.img.gz'))


def write_verified(fd,candidate):
    offset=0
    while offset<len(candidate):
        n=os.pwrite(fd,candidate[offset:offset+1024**2],offset)
        if n<=0:raise OSError('Logo 写入未取得进展')
        offset+=n
    os.fsync(fd)
    if read_logo(fd)!=candidate:raise ValueError('Logo 写入后读回校验失败，请勿重启，保留任务备份并检查日志')


def apply(value,expected,confirm):
    if not confirm:raise ValueError('必须在预览后明确确认写入第一屏')
    with locked():
        folder=load_folder(value);plan=json.loads((folder/'plan.json').read_text())
        state=json.loads((folder/'status.json').read_text())
        if state['phase']!='prepared' or plan['mode'] not in ('custom','stock'):
            raise ValueError('该 Logo 任务不可写入或已执行过')
        identity=identify()
        if plan['identity']!=identity:raise ValueError('设备或启动状态已变化，请重新预览')
        candidate=(folder/'candidate.img').read_bytes();unpack(candidate)
        if digest(candidate)!=plan['new_sha256'] or expected!=plan['new_sha256']:
            raise ValueError('待写入的 Logo 与已确认的预览不一致')
        if digest((folder/'preview.png').read_bytes())!=plan['preview_sha256']:raise ValueError('预览文件发生变化')
        if plan['mode']=='stock' and candidate!=stock(ROOT/'stock-logo.img.gz'):raise ValueError('原厂候选内容不一致')
        backup=gunzip((folder/'before.img.gz').read_bytes(),PARTITION_SIZE)
        if len(backup)!=PARTITION_SIZE or digest(backup)!=plan['old_sha256']:raise ValueError('Logo 回滚备份损坏')
        fd=os.open(DEVICE,os.O_RDWR|os.O_CLOEXEC)
        started=False
        try:
            st=os.fstat(fd)
            if not stat.S_ISBLK(st.st_mode) or '%d:%d'%(os.major(st.st_rdev),os.minor(st.st_rdev))!=identity['dev']:
                raise ValueError('Logo 写入设备身份变化')
            capacity=struct.unpack('Q',fcntl.ioctl(fd,BLKGETSIZE64,b'\0'*8))[0]
            if capacity!=PARTITION_SIZE or read_logo(fd)!=backup:raise ValueError('Logo 内容或容量已变化，请重新预览')
            atomic_json(folder/'status.json',dict(phase='writing',device_writes_started=True))
            started=True
            write_verified(fd,candidate)
            atomic_json(folder/'status.json',dict(phase='complete',device_writes_started=True,sha256=digest(candidate)))
        except BaseException as exc:
            atomic_json(folder/'status.json',dict(phase='needs-review' if started else 'failed',device_writes_started=started,error=str(exc)))
            raise
        finally:os.close(fd)
        return dict(message='第一屏已写入并读回校验。重启后生效。',backup=str(folder/'before.img.gz'))


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('mode',choices=('current','custom','stock'));p.add_argument('--image')
    p=sub.add_parser('apply');p.add_argument('folder');p.add_argument('--sha256',required=True);p.add_argument('--confirm',action='store_true')
    args=parser.parse_args()
    result=prepare(args.mode,args.image) if args.action=='prepare' else apply(args.folder,args.sha256,args.confirm)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc();sys.exit(1)
