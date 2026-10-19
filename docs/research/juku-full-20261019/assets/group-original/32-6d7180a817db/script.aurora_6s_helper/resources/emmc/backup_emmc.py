#!/usr/bin/env python3
"""Read-only eMMC acquisition to external /storage; no restore/write-device mode."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time
import uuid
import traceback

from block_device import BLKGETSIZE64

from aurora_emmc import probe, plan, read, disk_parent

CHUNK=8*1024**2


def depends_on_emmc(dev, seen=None):
    seen=set() if seen is None else seen
    if dev in seen:return False
    seen.add(dev)
    p=Path('/sys/dev/block/'+dev).resolve()
    if disk_parent(dev) in ('mmcblk0','mmcblk0boot0','mmcblk0boot1'):return True
    return any(depends_on_emmc(read(x/'dev'),seen) for x in (p/'slaves').glob('*'))


def assert_no_rw_emmc_mount():
    for line in read('/proc/self/mountinfo').splitlines():
        a,b=line.split(' - ',1);fields=a.split();superopts=b.split()[2].split(',')
        if ('rw' in fields[5].split(',') and 'rw' in superopts and depends_on_emmc(fields[2])):
            raise RuntimeError('Writable eMMC-backed mount: '+fields[4])


def hash_file(path, expected, progress=None):
    h=hashlib.sha256();total=0;last=time.monotonic()
    if progress:progress('verify',0,expected)
    with path.open('rb',buffering=0) as f:
        while data:=f.read(CHUNK):
            h.update(data);total+=len(data)
            if time.monotonic()-last>1:
                if progress:progress('verify',total,expected)
                last=time.monotonic()
    if total!=expected:raise RuntimeError('Unexpected backup length')
    if progress:progress('verify',total,expected)
    return h.hexdigest()


def acquire(device, destination, expected, progress=None):
    if os.path.lexists(destination):raise FileExistsError(str(destination))
    h=hashlib.sha256();total=0;last=time.monotonic();start=last
    partial=destination.with_name(destination.name+'.partial')
    if progress:progress('copy',0,expected)
    with open(device,'rb',buffering=0) as source:
        if not stat.S_ISBLK(os.fstat(source.fileno()).st_mode):raise RuntimeError('Not a block device')
        try:
            size=struct.unpack('Q',fcntl.ioctl(source,BLKGETSIZE64,b'\0'*8))[0]
        except OSError as exc:
            raise OSError(exc.errno, '查询设备容量失败（ioctl=%#x）：%s' % (BLKGETSIZE64, exc.strerror), str(device)) from exc
        if size!=expected:raise RuntimeError('Device size changed')
        with partial.open('xb',buffering=0) as output:
            while total<expected:
                data=source.read(min(CHUNK,expected-total))
                if not data:raise RuntimeError('Short read from '+str(device))
                h.update(data)
                view=memoryview(data)
                while view:
                    written=output.write(view)
                    if not written:raise RuntimeError('Short write to backup')
                    view=view[written:]
                total+=len(data)
                if time.monotonic()-last>1:
                    if progress:progress('copy',total,expected)
                    last=time.monotonic()
            os.fsync(output.fileno())
    if progress:progress('copy',total,expected)
    digest=hash_file(partial,expected,progress)
    if digest!=h.hexdigest():raise RuntimeError('Backup readback hash mismatch')
    os.rename(partial,destination)
    return dict(file=destination.name,source=device,bytes=expected,sha256=digest,
                readback_verified=True,seconds=round(time.monotonic()-start,2))


def main():
    os.umask(0o077)
    lock=open('/run/aurora-emmc-backup.lock','w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    report=probe();plan(report,20,1024,'reset-data',16)
    if not report['backup_space_sufficient']:raise RuntimeError('Insufficient backup space')
    if set(report['boot_areas'])!={'mmcblk0boot0','mmcblk0boot1'}:raise RuntimeError('Unexpected eMMC boot areas')
    assert_no_rw_emmc_mount()
    parent=Path('/storage/aurora-emmc-backups')
    # No symlink destination or hidden mount redirect into eMMC allowed.
    if parent.is_symlink():raise RuntimeError('Symlink backup directory refused')
    parent.mkdir(mode=0o700,exist_ok=True)
    target=parent.resolve()
    if target.parent!=Path('/storage'):raise RuntimeError('Destination outside external storage')
    for line in read('/proc/self/mountinfo').splitlines():
        a=line.split(' - ',1)[0].split()
        if a[4].startswith('/storage/') and (str(target)==a[4] or str(target).startswith(a[4]+'/')):
            raise RuntimeError('Nested backup destination mount refused')
    name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    folder=parent/name;folder.mkdir(mode=0o700)
    (folder/'probe-before.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(phase='begin',directory=str(folder))),flush=True)
    entries=[]
    for dev,size in [('mmcblk0',report['emmc_bytes']),*sorted(report['boot_areas'].items())]:
        entries.append(acquire('/dev/'+dev,folder/(dev+'.img'),size))
    with open('/dev/dtb','rb',buffering=0) as f:dtb=f.read(512*1024)
    if hashlib.sha256(dtb).hexdigest()!=report['android_dtb_sha256']:raise RuntimeError('DTB changed during acquisition')
    with (folder/'android-dtb.raw').open('xb') as f:f.write(dtb);f.flush();os.fsync(f.fileno())
    after=probe();assert_no_rw_emmc_mount()
    if report['mpt_sha256']!=after['mpt_sha256']:raise RuntimeError('MPT changed during backup')
    (folder/'probe-after.json').write_text(json.dumps(after,indent=2))
    manifest=dict(schema=1,status='verified',artifacts=entries,
                  android_dtb_sha256=report['android_dtb_sha256'],mpt_sha256=report['mpt_sha256'],
                  limitations=['Does not include RPMB, eFuses, or eMMC hardware configuration',
                               'Verified acquisition is not a tested USB recovery/burning package'])
    with (folder/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.flush();os.fsync(f.fileno())
    d=os.open(folder,os.O_RDONLY|os.O_DIRECTORY);os.fsync(d);os.close(d)
    print(json.dumps(dict(phase='complete',directory=str(folder),manifest=manifest)),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        traceback.print_exc()
        print(json.dumps(dict(phase='failed',error=str(e))),flush=True);sys.exit(1)
