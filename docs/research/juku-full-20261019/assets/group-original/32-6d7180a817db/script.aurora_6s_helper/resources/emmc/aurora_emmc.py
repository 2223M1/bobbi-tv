#!/usr/bin/env python3
"""Aurora eMMC research frontend. probe/plan only: never writes block devices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys

MIB = 1024 ** 2
GIB = 1024 ** 3


def read(path):
    try:
        return Path(path).read_text().strip('\x00\n')
    except (OSError, UnicodeError):
        return ''


def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {'returncode': p.returncode, 'stdout': p.stdout.strip(),
                'stderr': p.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'returncode': -1, 'stdout': '', 'stderr': str(exc)}


def parse_mpt(raw, capacity):
    if len(raw) < 24:
        raise ValueError('Truncated MPT header')
    magic, version_raw, count, checksum = struct.unpack_from('<4s12sII', raw)
    version = version_raw.rstrip(b'\0').decode('ascii')
    if magic != b'MPT\0' or not 1 <= count <= 32 or len(raw) < 24 + count * 40:
        raise ValueError('Invalid MPT magic/count/length')
    if version == '01.00.00':
        expected = sum(struct.unpack_from('<10I', raw, 24)) * count & 0xffffffff
    elif version == '02.00.00':
        expected = sum(struct.unpack_from('<' + str(count * 10) + 'I', raw, 24)) & 0xffffffff
    else:
        raise ValueError('Unknown MPT checksum version')
    if expected != checksum:
        raise ValueError('MPT checksum mismatch')
    rows = []
    for i in range(count):
        name, size, offset, flags, padding = struct.unpack_from('<16sQQII', raw, 24 + i * 40)
        name = name.split(b'\0')[0].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_]+', name) or any(x['name'] == name for x in rows):
            raise ValueError('Invalid/duplicate partition name')
        if (size | offset) % 512 or offset + size > capacity:
            raise ValueError('Invalid partition boundary')
        if any(size and x['size'] and offset < x['offset'] + x['size'] and
               x['offset'] < offset + size for x in rows):
            raise ValueError('Overlapping MPT partitions')
        rows.append(dict(index=i+1, name=name, size=size, offset=offset, flags=flags,
                         padding=padding))
    return dict(version=version, checksum=checksum, partitions=rows)


def mountinfo():
    rows = []
    for line in read('/proc/self/mountinfo').splitlines():
        a, b = line.split(' - ', 1)
        left, right = a.split(), b.split()
        rows.append(dict(dev=left[2], mountpoint=left[4], source=right[1], fs=right[0]))
    return rows


def disk_parent(major_minor):
    p = Path('/sys/dev/block/' + major_minor).resolve()
    if (p/'partition').exists():
        p = p.parent
    return p.name


def props(path):
    return dict(line.split('=', 1) for line in read(path).splitlines()
                if '=' in line and not line.startswith('#'))


def probe(*, repair_identity=False):
    if os.geteuid() != 0:
        raise ValueError('Run probe as root on CoreELEC')
    os_release = {k: v.strip('"') for k, v in props('/etc/os-release').items()}
    if os_release.get('ID') != 'coreelec':
        raise ValueError('probe requires CoreELEC; use plan on a saved report elsewhere')
    disk = Path('/sys/block/mmcblk0')
    if not disk.exists():
        raise ValueError('No supported mmcblk0 layout detected')
    capacity = int(read(disk/'size')) * 512
    dev = os.stat('/dev/mmcblk0')
    if not stat.S_ISBLK(dev.st_mode):
        raise ValueError('eMMC path is not a block device')
    # Open backing disk read-only and read MPT at the verified SC2 reserved offset.
    with open('/dev/mmcblk0', 'rb', buffering=0) as f:
        f.seek(36*MIB)
        raw = f.read(4096)
    table = parse_mpt(raw, capacity)
    for p in table['partitions']:
        d = disk/p['name']
        p['sysfs_matches'] = (read(d/'start') == str(p['offset']//512) and
                              read(d/'size') == str(p['size']//512) and
                              read(d/'partition') == str(p['index']))
    mounts = mountinfo()
    roots = {m['mountpoint']: m for m in mounts if m['mountpoint'] in ('/flash', '/storage')}
    for m in roots.values():
        m['parent_disk'] = disk_parent(m['dev'])
    android_model = []
    for path in ('/android/system/system/build.prop', '/android/system/build.prop', '/android/vendor/build.prop'):
        for k, v in props(path).items():
            if k.startswith('ro.product.') and k.endswith('.model'):
                android_model.append(v)
    from platform_support import branch
    detected_branch = branch(os_release)
    identity_evidence = None
    if repair_identity:
        from repair_identity import read_models
        super_rows = [p for p in table['partitions'] if p['name']=='super' and p['sysfs_matches']]
        if len(super_rows)!=1:raise ValueError('Cannot verify original super partition')
        android_model, identity_evidence = read_models(super_rows[0])
    elif not android_model and detected_branch == 'Amlogic-ng':
        from repair_identity import read_models_for_environment
        super_rows = [p for p in table['partitions'] if p['name']=='super' and p['sysfs_matches']]
        if len(super_rows)!=1:raise ValueError('Cannot verify original super partition')
        slot_env = command('fw_printenv', 'active_slot')
        if slot_env['returncode']:
            raise ValueError('Android 启动环境读取失败：'+slot_env['stderr'])
        android_model, identity_evidence = read_models_for_environment(super_rows[0], slot_env['stdout'])
    fs = os.statvfs('/storage')
    tools = {x: shutil.which(x) for x in ('python3', 'fw_printenv', 'fw_setenv', 'mkfs.vfat',
             'mkfs.ext4', 'rsync', 'sha256sum', 'e2fsck', 'resize2fs', 'dmsetup', 'ampart')}
    env = {k: command('fw_printenv', k) for k in ('bootcmd', 'cfgloademmc', 'active_slot')}
    crypto_fstab = '\n'.join(x for x in read('/android/vendor/etc/fstab.amlogic').splitlines()
                             if not x.startswith('#') and re.search(r'\s/data\s', x))
    # /dev/dtb exports only one 256 KiB slot on some CE kernels.
    # Transactions must bind to both physical copies, not that virtual view.
    with open('/dev/mmcblk0', 'rb', buffering=0) as f:
        f.seek(40*MIB)
        dtb = f.read(512*1024)
    boot_areas = {p.name: int(read(p/'size'))*512 for p in disk.glob('mmcblk0boot*')
                  if (p/'size').exists()}
    result = dict(schema=1, readonly=True, os_release=os_release,
                  machine_model=read('/proc/device-tree/model'), cid=read('/sys/block/mmcblk0/device/cid'),
                  android_models=sorted(set(android_model)), emmc_bytes=capacity,
                  mpt=table, mpt_sha256=hashlib.sha256(raw).hexdigest(),
                  android_dtb_sha256=hashlib.sha256(dtb).hexdigest(),
                  mounts=roots, storage_free_bytes=fs.f_bavail*fs.f_frsize,
                  boot_areas=boot_areas, tools=tools, boot_environment=env,
                  android_data_fstab=crypto_fstab, dm_targets=command('dmsetup','targets'))
    if identity_evidence is not None:
        result['repair_identity' if repair_identity else 'android_identity'] = identity_evidence
    result['blockers'] = []
    if result['android_models'] not in (['A4111'], ['A4112']):
        result['blockers'].append('Original Android model is not unambiguously A4111/A4112')
    if not all(p['sysfs_matches'] for p in table['partitions']):
        result['blockers'].append('MPT differs from live sysfs')
    if any(x not in roots or roots[x]['parent_disk'] == 'mmcblk0' for x in ('/flash','/storage')):
        result['blockers'].append('Both /flash and /storage must be external')
    result['full_backup_required_bytes'] = capacity + sum(boot_areas.values()) + 256*MIB
    result['backup_space_sufficient'] = result['storage_free_bytes'] >= result['full_backup_required_bytes']
    result['installation_ready'] = False
    return result


def plan(report, ce_gib, flash_mib, mode, android_gib, *, ce_bytes=None):
    if report.get('schema') != 1 or report.get('blockers'):
        raise ValueError('Probe schema invalid or probe has blockers')
    from platform_support import branch
    branch(report['os_release'])
    if report.get('android_models') not in (['A4111'], ['A4112']):
        raise ValueError('Unsupported board or CoreELEC branch')
    old = report['mpt']['partitions']
    names = ['bootloader','reserved','cache','env','frp','factory','vendor_boot_a','vendor_boot_b',
             'tee','logo','misc','dtbo_a','dtbo_b','cri_data','param','odm_ext_a','odm_ext_b',
             'oem_a','oem_b','boot_a','boot_b','rsv','metadata','vbmeta_a','vbmeta_b',
             'vbmeta_system_a','vbmeta_system_b','super','userdata']
    sizes = [4,64,0,8,2,8,24,24,32,8,2,2,2,8,16,16,16,32,32,64,64,16,16,2,2,2,2,1800]
    cursor = 0
    if [p['name'] for p in old] != names or not all(p.get('sysfs_matches') for p in old):
        raise ValueError('Unsupported original partition list or stale/inconsistent probe')
    for i, (p, size) in enumerate(zip(old, sizes)):
        if i == 1:
            cursor = 36*MIB
        elif i:
            cursor = old[i-1]['offset'] + old[i-1]['size'] + 8*MIB
        if p['offset'] != cursor or p['size'] != size*MIB:
            raise ValueError('Original system partition boundaries differ from tested layout')
    capacity = report['emmc_bytes']
    if old[-1]['offset'] != old[-2]['offset']+old[-2]['size']+8*MIB or old[-1]['offset']+old[-1]['size'] != capacity:
        raise ValueError('Unexpected userdata boundary')
    if flash_mib < 512 or ce_gib < 1 or android_gib < 8:
        raise ValueError('Candidate sizes below research minimums')
    if ce_bytes is not None and (type(ce_bytes) is not int or ce_bytes < GIB or ce_bytes % 512):
        raise ValueError('Invalid CE data size or sector alignment')
    rows = [{k:p[k] for k in ('index','name','offset','size','flags')} for p in old[:-1]]
    cursor = old[-1]['offset']
    if mode == 'reset-data':
        additions = [('ce_system',flash_mib*MIB,2),('ce_storage',ce_gib*GIB if ce_bytes is None else ce_bytes,4),('userdata',None,4)]
    else:
        additions = [('userdata',android_gib*GIB,4),('ce_system',flash_mib*MIB,2),('ce_storage',None,4)]
    for name, size, flag in additions:
        if size is None:
            size = capacity-cursor
        if size < (512*MIB if name=='ce_system' else GIB) or cursor+size > capacity:
            raise ValueError('Not enough space for candidate partitions')
        rows.append(dict(index=len(rows)+1,name=name,offset=cursor,size=size,flags=flag))
        cursor += size + 8*MIB
    if len(rows)>32:
        raise ValueError('MPT count exceeds32')
    needed = next(p['index'] for p in rows if p['name']=='ce_system')
    blockers = ['No on-device validation of original-DTB/MPT rewrite and recovery yet',
                'Must verify full backup and restore path before any partition write',
                'Must adapt eMMC boot scan to partition %d (hex %X)' % (needed,needed),
                'CE/Android OTA compatibility not yet verified']
    blockers.append('No CE-only decrypt-and-shrink implementation; this is a geometric plan, NOT a lossless procedure'
                    if mode=='preserve-offset' else
                    'Android userdata reinitialization and encryption-key handling not yet validated')
    return dict(schema=1,mode=mode,installation_ready=False,partitions=rows,
                preserves_first_28=True,erases_android_userdata=mode=='reset-data',
                preserves_existing_userdata_offset=mode=='preserve-offset',
                userdata_preservation_verified=False,blockers=blockers,
                source_mpt_sha256=report['mpt_sha256'],source_android_dtb_sha256=report['android_dtb_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='action',required=True)
    subs.add_parser('probe',help='read-only CoreELEC inspection to JSON on stdout')
    p=subs.add_parser('plan',help='offline, non-executable layout proposal')
    p.add_argument('report',type=Path)
    p.add_argument('--mode',choices=('reset-data','preserve-offset'),required=True)
    p.add_argument('--ce-gib',type=int,default=20)
    p.add_argument('--flash-mib',type=int,default=1024)
    p.add_argument('--android-gib',type=int,default=16)
    a=parser.parse_args()
    try:
        result=probe() if a.action=='probe' else plan(json.loads(a.report.read_text()),a.ce_gib,a.flash_mib,a.mode,a.android_gib)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.exit(1,'Refused: '+str(exc)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
