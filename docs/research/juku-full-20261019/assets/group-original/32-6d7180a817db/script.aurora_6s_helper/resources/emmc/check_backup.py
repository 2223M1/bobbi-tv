#!/usr/bin/env python3
"""Inspect backup readiness without writing devices. --full-hash rereads all images."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
from aurora_emmc import parse_mpt


def safe_file(folder,name):
    p=folder/name
    if p.is_symlink() or not stat.S_ISREG(p.stat().st_mode):raise ValueError('Not a regular backup file: '+name)
    return p


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(8*1024**2):h.update(b)
    return h.hexdigest()


def inspect(folder, full_hash=False):
    folder=Path(folder)
    if folder.is_symlink():raise ValueError('Symlink backup directory refused')
    folder=folder.resolve()
    manifest=json.loads(safe_file(folder,'manifest.json').read_text())
    before=json.loads(safe_file(folder,'probe-before.json').read_text())
    after=json.loads(safe_file(folder,'probe-after.json').read_text())
    if manifest.get('schema')!=1 or manifest.get('status')!='verified':raise ValueError('Backup not completed and verified')
    if list(folder.glob('*.partial')):raise ValueError('Incomplete image present')
    for key in ('mpt_sha256','android_dtb_sha256','emmc_bytes','boot_areas'):
        if before[key]!=after[key]:raise ValueError('Source identity/metadata changed during acquisition')
    for key in ('mpt_sha256','android_dtb_sha256'):
        if manifest[key]!=before[key]:raise ValueError('Manifest differs from probe')
    expected={'mmcblk0.img':('/dev/mmcblk0',before['emmc_bytes'])}
    if set(before['boot_areas'])!={'mmcblk0boot0','mmcblk0boot1'}:raise ValueError('Missing eMMC boot areas')
    expected.update({n+'.img':('/dev/'+n,s) for n,s in before['boot_areas'].items()})
    items=manifest['artifacts']
    if len(items)!=3 or {x['file'] for x in items}!=set(expected):raise ValueError('Unexpected backup image inventory')
    for row in items:
        name=row['file'];source,size=expected[name];p=safe_file(folder,name)
        if row['source']!=source or row['bytes']!=size or p.stat().st_size!=size or row.get('readback_verified') is not True:
            raise ValueError('Image size/source/verification mismatch: '+name)
        if full_hash and sha(p)!=row['sha256']:raise ValueError('Image hash mismatch: '+name)
    dtb=safe_file(folder,'android-dtb.raw')
    if sha(dtb)!=before['android_dtb_sha256']:raise ValueError('DTB export hash mismatch')
    with safe_file(folder,'mmcblk0.img').open('rb') as f:
        f.seek(36*1024**2);mpt=f.read(4096)
    if hashlib.sha256(mpt).hexdigest()!=before['mpt_sha256']:raise ValueError('Image MPT differs from acquisition report')
    parse_mpt(mpt,before['emmc_bytes'])
    return dict(metadata_checks_passed=True,acquisition_readback_recorded=True,
                full_image_hashes_rechecked=full_hash,restore_tested=False,
                artifacts=items,notes=['No write or restore performed',
                'Metadata-only check does not verify every image byte; use --full-hash for that',
                'A complete image backup does not prove USB recovery is available'])

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('directory',type=Path);a.add_argument('--full-hash',action='store_true');x=a.parse_args()
    try:r=inspect(x.directory,x.full_hash)
    except (OSError,ValueError,KeyError,TypeError) as e:a.exit(1,'Backup not ready: '+str(e)+'\n')
    print(json.dumps(r,indent=2))
