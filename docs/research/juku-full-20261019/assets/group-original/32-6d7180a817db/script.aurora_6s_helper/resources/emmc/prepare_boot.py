#!/usr/bin/env python3
"""Stage current read-only CE /flash for future internal boot; never writes /flash or eMMC."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import uuid
import zlib

from fat_boot import boot_source
from aurora_emmc import probe, plan, read
from boot_files import BOOT_REQUIRED, BOOT_EXCLUDES, scan_boot, check_boot_capacity, required_boot_names


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(4*1024**2):h.update(b)
    return h.hexdigest()


ROOTOPT = 'BOOT_IMAGE=kernel.img boot=/dev/ce_system disk=/dev/ce_storage'
STOCK_CFGLOAD = Path('/usr/share/bootloader/Generic_cfgload')
REVIEWED_SCRIPT_SHA256 = '48297b1fbd12a37e2882a21a5f15189475937fdb7368883a1252cbe82c434b85'
REVIEWED_NG_SHA256 = '5bbb58b16e3c41081fb1b3e2abd9ddfdf0d8b0e4116e985e0500013028c39dc8'


def decode_cfgload(raw):
    if len(raw)<72 or raw[:4]!=bytes.fromhex('27051956'):
        raise ValueError('Not a legacy U-Boot script image')
    h=bytearray(raw[:64]);stored=struct.unpack_from('>I',h,4)[0];h[4:8]=b'\0'*4
    if zlib.crc32(h)!=stored:raise ValueError('Original cfgload header CRC mismatch')
    size=struct.unpack_from('>I',h,12)[0]
    if raw[30]!=6 or raw[31]!=0 or size!=len(raw)-64:
        raise ValueError('Unsupported script type/compression/size')
    payload=raw[64:]
    if zlib.crc32(payload)!=struct.unpack_from('>I',h,24)[0]:raise ValueError('Original cfgload data CRC mismatch')
    script_len,terminator=struct.unpack_from('>II',payload)
    if terminator or script_len!=len(payload)-8:raise ValueError('Unsupported multi-script payload')
    return payload[8:].decode()


def validate_stock_cfgload(raw):
    text = decode_cfgload(raw)
    if hashlib.sha256(text.encode()).hexdigest() not in (REVIEWED_SCRIPT_SHA256, REVIEWED_NG_SHA256):
        raise ValueError('Unreviewed stock cfgload; review config.ini import ordering first')
    return raw


def configure_rootopt(raw):
    text = raw.decode('utf-8')
    if '\0' in text:raise ValueError('NUL in config.ini')
    # U-Boot env import uses plain key=value lines, not shell quoting.
    lines = text.splitlines(keepends=True)
    matches = [i for i,line in enumerate(lines) if re.match(r'^\s*rootopt\s*=',line)]
    if len(matches)>1:raise ValueError('Duplicate rootopt entries')
    if matches:
        value = lines[matches[0]].strip().split('=',1)[1]
        if value != ROOTOPT:raise ValueError('Existing rootopt conflicts with internal layout')
        return raw
    ending = '\r\n' if '\r\n' in text else '\n'
    if text and not text.endswith('\n'):text += ending
    return (text + ending + '# Aurora internal CE boot paths; keep stock cfgload.' + ending +
            'rootopt=' + ROOTOPT + ending).encode('utf-8')


def modify_cfgload(raw):
    # Legacy transformation retained only for validating historical snapshots.
    text=decode_cfgload(raw)
    h=bytearray(raw[:64]);h[4:8]=b'\0'*4
    old='setenv rootopt "BOOT_IMAGE=kernel.img boot=LABEL=COREELEC disk=LABEL=STORAGE"'
    override='if test "${ce_on_emmc}" = "yes"; then setenv rootopt "BOOT_IMAGE=kernel.img boot=LABEL=CE_FLASH disk=FOLDER=/dev/CE_STORAGE"; fi'
    if text.count(old)!=1 or text.count(override)!=1:raise ValueError('Unknown cfgload version; refuse automatic patch')
    text=text.replace(old,'setenv rootopt "BOOT_IMAGE=kernel.img boot=/dev/ce_system disk=/dev/ce_storage"').replace(override+'\n','')
    body=text.encode();payload=struct.pack('>II',len(body),0)+body
    struct.pack_into('>I',h,12,len(payload));struct.pack_into('>I',h,24,zlib.crc32(payload));struct.pack_into('>I',h,4,zlib.crc32(h))
    return bytes(h)+payload


def source_inventory(root=Path('/flash'), partition_bytes=1024**3):
    with boot_source(root) as source:
        return _source_inventory(source, partition_bytes)


def _source_inventory(root, partition_bytes):
    files, directories = scan_boot(root, exclude_device_trees=True)
    required_boot_names(files)
    stock = validate_stock_cfgload(STOCK_CFGLOAD.read_bytes())
    config = configure_rootopt((Path(root)/'config.ini').read_bytes())
    sizes = dict(files, cfgload=len(stock), **{'config.ini': len(config)})
    check_boot_capacity(sizes, directories, partition_bytes)
    return files, directories


def stage_files(source, out):
    """Copy boot content except root device_trees/aml_autoscript; transform two files."""
    with boot_source(source) as view:
        return _stage_files(view, out, Path(source))


def _stage_files(source, out, logical_source):
    source, out = Path(source), Path(out)
    files, directories = _source_inventory(source, 1024**3)
    boot = out/'boot';boot.mkdir()
    for name in directories:(boot/name).mkdir()
    entries=[]
    for name in sorted(files):
        src=STOCK_CFGLOAD if name=='cfgload' else source/name
        if src.is_symlink() or not stat.S_ISREG(src.stat().st_mode):raise RuntimeError('Source not a regular file')
        before=sha(src)
        with src.open('rb') as f,(boot/name).open('xb') as target:
            while chunk:=f.read(4*1024**2):target.write(chunk)
            target.flush();os.fsync(target.fileno())
        if before!=sha(boot/name) or before!=sha(src):raise RuntimeError('Source changed or copy hash mismatch')
        entries.append(dict(file=name,source_path=str(STOCK_CFGLOAD if name=='cfgload' else logical_source/name),source_sha256=before))
    if scan_boot(source, exclude_device_trees=True)!=(files,directories):
        raise ValueError('暂存期间启动文件清单发生变化')
    raw=(boot/'config.ini').read_bytes();(out/'original-config.ini').write_bytes(raw)
    with (boot/'config.ini').open('wb') as f:
        f.write(configure_rootopt(raw));f.flush();os.fsync(f.fileno())
    for row in entries:row.update(sha256=sha(boot/row['file']),bytes=(boot/row['file']).stat().st_size)
    check_boot_capacity({r['file']:r['bytes'] for r in entries}, directories)
    return entries, directories


def stage():
    os.umask(0o077)
    report=probe();plan(report,20,1024,'reset-data',16)
    if os.statvfs('/flash').f_flag & os.ST_RDONLY == 0:raise RuntimeError('/flash must be read-only during staging')
    parent=Path('/storage/aurora-emmc-staging')
    if parent.is_symlink():raise RuntimeError('Symlink staging parent refused')
    parent.mkdir(mode=0o700,exist_ok=True)
    if parent.resolve().parent!=Path('/storage'):raise RuntimeError('External staging parent required')
    for line in read('/proc/self/mountinfo').splitlines():
        mountpoint=line.split(' - ',1)[0].split()[4]
        if mountpoint.startswith('/storage/') and (str(parent)==mountpoint or str(parent).startswith(mountpoint+'/')):
            raise RuntimeError('Nested staging mount refused')
    name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    out=parent/name;out.mkdir(mode=0o700)
    entries,directories=stage_files(Path('/flash'),out)
    manifest=dict(schema=3,boot_directories=directories,boot_excludes=BOOT_EXCLUDES,boot_strategy="stock-cfgload-config-rootopt",installation_ready=False,boot_files=entries,os_release=report['os_release'],
                  original_android_dtb_sha256=report['android_dtb_sha256'],
                  notes=['Boot files only; /storage migration is not performed',
                         'Not a mountable FAT image; not deployed to internal storage',
                         'Official cfgload is unchanged; config.ini sets internal boot/storage paths'])
    with (out/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.flush();os.fsync(f.fileno())
    return dict(directory=str(out),manifest=manifest)

if __name__=='__main__':print(json.dumps(stage()))
