#!/usr/bin/env python3
"""Prepare a quiesced CE snapshot and rehearse installation in new loop images only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

from aurora_emmc import probe,plan,read
from layout_trial import atomic_json,private_external
from inspect_storage import scan_tree,rsync_flags
from storage_mounts import storage_source
from live_snapshot import copy_live_storage,rsync_copy
from file_attributes import attributes,copy_attributes,ignored_attribute_names,rsync_xattr_filters
from prepare_boot import sha,modify_cfgload,configure_rootopt,validate_stock_cfgload,STOCK_CFGLOAD
from fat_boot import boot_source, FAT_RW_OPTIONS, FAT_RO_OPTIONS
from boot_files import boot_manifest_inventory, scan_boot, verify_boot_tree

EXCLUDES=['/aurora-emmc-backups/','/aurora-emmc-staging/','/aurora-emmc-jobs/','/lost+found/',
          '/.kodi/temp/','/.cache/log/','/.cache/cores/','/logfiles/']
SERVICES=['kodi.service','bluetooth.service','cron.service','smbd.service','nmbd.service','connman.service']


def run(args,timeout=120):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env={**os.environ,'LC_ALL':'C'})
    if p.returncode:raise RuntimeError('Command failed: '+repr(args)+'\n'+p.stdout+p.stderr)
    return p.stdout


def validate_boot(stage, source_root=Path('/flash')):
    with boot_source(source_root) as view:
        return _validate_boot(stage, view, Path(source_root))


def _validate_boot(stage, source_root, logical_source):
    stage=private_external(stage)
    manifest=json.loads((stage/'manifest.json').read_text());rows=manifest['boot_files']
    files,directories=boot_manifest_inventory(manifest)
    verify_boot_tree(stage/'boot',manifest)
    if manifest.get('schema')==3:
        source_files,source_dirs=scan_boot(source_root,exclude_device_trees=True)
        if set(source_files)!=set(files) or source_dirs!=directories:
            raise ValueError('源启动目录清单发生变化')
    strategy=manifest.get('boot_strategy')
    if strategy not in (None,'stock-cfgload-config-rootopt'):raise ValueError('Unknown boot strategy')
    for row in rows:
        source=STOCK_CFGLOAD if strategy and row['file']=='cfgload' else Path(source_root)/row['file']
        if strategy and row.get('source_path')!=str(STOCK_CFGLOAD if strategy and row['file']=='cfgload' else logical_source/row['file']):raise ValueError('Unexpected boot source path')
        copy=stage/'boot'/row['file']
        if source.is_symlink() or copy.is_symlink() or not copy.is_file():raise ValueError('Unsafe boot file')
        if copy.stat().st_size!=row['bytes'] or sha(copy)!=row['sha256'] or sha(source)!=row['source_sha256']:
            raise ValueError('Boot files changed since staging: '+row['file'])
    if strategy:
        expected=validate_stock_cfgload(STOCK_CFGLOAD.read_bytes())
        if (stage/'boot/cfgload').read_bytes()!=expected:raise ValueError('Stock boot script differs')
        if (stage/'boot/config.ini').read_bytes()!=configure_rootopt((Path(source_root)/'config.ini').read_bytes()):
            raise ValueError('Internal config transformation differs')
    elif (stage/'boot/cfgload').read_bytes()!=modify_cfgload((Path(source_root)/'cfgload').read_bytes()):
        raise ValueError('Legacy boot script transformation differs')
    return manifest


def snapshot_inventory(root, update=None, step=None, include_xattrs=False):
    root=Path(root);result={}
    if root.is_symlink() or not root.is_dir():raise ValueError('Unsafe snapshot root')
    done=0
    total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) if update else 0
    def fail(error):raise error
    for base,dirs,files in os.walk(root,followlinks=False,onerror=fail):
        if Path(base)==root:dirs[:]=[x for x in dirs if x!='lost+found']
        for name in dirs+files:
            path=Path(base)/name;info=path.lstat();entry={'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
            if stat.S_ISLNK(info.st_mode):entry.update(type='link',target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):entry.update(type='dir')
            elif stat.S_ISREG(info.st_mode):entry.update(type='file',bytes=info.st_size,sha256=sha(path))
            else:raise ValueError('Unsupported snapshot object: '+str(path))
            if include_xattrs:entry['xattrs']=attributes(path)
            result[str(path.relative_to(root))]=entry
            if update and entry['type']=='file':
                done+=entry['bytes'];update('checking','核对 '+name,progress_step=step,progress_done=done,progress_total=total)
    return result


def snapshot(folder,boot_stage, live=False, update=None):
    report=probe();plan(report,20,1024,'reset-data',16)
    boot=validate_boot(boot_stage)
    if any(Path('/storage/.update').iterdir()):raise ValueError('Pending CE update must be handled first')
    folder=private_external(folder,create=True);dest=folder/'storage';dest.mkdir(mode=0o700)
    active=[] if live else [s for s in SERVICES if subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0]
    atomic_json(folder/'services.json',{'originally_active':active})
    # ExecStopPost of the supervising oneshot also calls restore_services on errors/timeouts.
    try:
        for service in active:run(['systemctl','stop',service],timeout=60)
        with storage_source() as source:
            inventory=scan_tree(source);version=run(['rsync','--version']);flags=rsync_flags(version,inventory,metadata_fallback=True).replace('n','')
            if live:
                copy_live_storage(source,dest,flags,EXCLUDES,run,update)
            else:
                args=['rsync',flags,'--numeric-ids']+rsync_xattr_filters(flags)+['--exclude='+p for p in EXCLUDES]+[str(source)+'/',str(dest)+'/']
                run(args,timeout=7200);os.sync()
                changes=run(['rsync',flags+'nc','--numeric-ids','--itemize-changes']+rsync_xattr_filters(flags)+['--exclude='+p for p in EXCLUDES]+[str(source)+'/',str(dest)+'/'],timeout=7200)
                if changes.strip():raise ValueError('Source changed during quiesced snapshot: '+changes[:2000])
            copy_attributes(source,dest,update)
        data=snapshot_inventory(dest,update,'snapshot-verify',include_xattrs=True)
        atomic_json(folder/'manifest.json',dict(schema=1,kind='live-ce-snapshot' if live else 'quiesced-ce-snapshot',boot_stage=str(Path(boot_stage).resolve()),
            boot_manifest_sha256=sha(Path(boot_stage)/'manifest.json'),boot_files=boot['boot_files'],storage=data,
            excludes=EXCLUDES,source_inventory=inventory,services_paused=active,
            snapshot_xattrs=True,storage_root_xattrs=attributes(dest),ignored_xattrs=list(ignored_attribute_names()),
            regular_file_bytes=sum(x.get('bytes',0) for x in data.values()),
            notes=['Snapshot excludes logs/coredumps/Kodi temp and external backup/staging directories.',
                   'Running OS and Android partitions are not modified.']))
        return dict(directory=str(folder),files=len(data),bytes=sum(x.get('bytes',0) for x in data.values()))
    finally:restore_services(folder)


def restore_services(folder):
    if not Path(folder).exists():return
    folder=private_external(folder)
    path=folder/'services.json'
    if not path.exists():return
    active=json.loads(path.read_text())['originally_active']
    if not set(active)<=set(SERVICES):raise ValueError('Invalid saved service list')
    errors=[]
    for service in sorted(active,key=lambda x:(x!='connman.service',x=='kodi.service')):
        try:run(['systemctl','start',service],timeout=60)
        except Exception as e:errors.append(str(e))
    atomic_json(folder/'services-restored.json',{'success':not errors,'errors':errors})
    if errors:raise RuntimeError('Could not restore services: '+repr(errors))


def validate_snapshot(folder):
    folder=private_external(folder);manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('kind') not in ('quiesced-ce-snapshot','live-ce-snapshot') or snapshot_inventory(folder/'storage',include_xattrs=manifest.get('snapshot_xattrs',False))!=manifest['storage']:
        raise ValueError('Snapshot content/metadata changed')
    if manifest.get('snapshot_xattrs') and attributes(folder/'storage')!=manifest['storage_root_xattrs']:
        raise ValueError('Snapshot root extended attributes changed')
    stage=Path(manifest['boot_stage']);boot=validate_boot(stage)
    if sha(stage/'manifest.json')!=manifest['boot_manifest_sha256']:raise ValueError('Boot staging manifest changed')
    return manifest


def format_devices(bootdev,datadev):
    run(['mkfs.vfat','-F','32','-n','CE_AURORA',str(bootdev)],timeout=120)
    run(['mkfs.ext4','-F','-m','0','-L','CE_AURORA_DATA','-E','lazy_itable_init=0,lazy_journal_init=0',str(datadev)],timeout=7200)


def copy_and_verify(snapshot_path,bootdev,datadev,update=None):
    manifest=validate_snapshot(snapshot_path);stage=Path(manifest['boot_stage'])
    with tempfile.TemporaryDirectory(prefix='aurora-install-',dir='/run') as tmp:
        mounts=[]
        try:
            boot=Path(tmp)/'boot';data=Path(tmp)/'storage';boot.mkdir();data.mkdir()
            for device,target,fs in [(bootdev,boot,'vfat'),(datadev,data,'ext4')]:
                run(['mount','-t',fs,'-o',FAT_RW_OPTIONS if fs=='vfat' else 'rw,noatime',str(device),str(target)]);mounts.append(target)
            rsync_copy(['rsync','-rt','--modify-window=1',str(stage/'boot')+'/',str(boot)+'/'],update,'install-bootcopy',sum(r['bytes'] for r in manifest['boot_files']))
            flags=rsync_flags(run(['rsync','--version']),manifest['source_inventory'],metadata_fallback=True).replace('n','')
            rsync_copy(['rsync',flags,'--numeric-ids',*rsync_xattr_filters(flags),str(Path(snapshot_path)/'storage')+'/',str(data)+'/'],update,'install-datacopy',manifest['regular_file_bytes'])
            copy_attributes(Path(snapshot_path)/'storage',data,update)
            os.sync()
            for target in reversed(mounts):run(['umount',str(target)])
            mounts=[]
            for device,target,fs in [(bootdev,boot,'vfat'),(datadev,data,'ext4')]:
                run(['mount','-t',fs,'-o',FAT_RO_OPTIONS if fs=='vfat' else 'ro',str(device),str(target)]);mounts.append(target)
            verify_boot_tree(boot,json.loads((stage/'manifest.json').read_text()))
            checked=0
            for row in manifest['boot_files']:
                if sha(boot/row['file'])!=row['sha256']:raise ValueError('Boot copy hash mismatch: '+row['file'])
                checked+=row['bytes']
                if update:update('readback','启动文件读回校验',progress_step='install-bootverify',progress_done=checked,progress_total=sum(r['bytes'] for r in manifest['boot_files']))
            if snapshot_inventory(data,update,'install-dataverify',include_xattrs=manifest.get('snapshot_xattrs',False))!=manifest['storage']:raise ValueError('Installed storage differs from snapshot')
            if manifest.get('snapshot_xattrs') and attributes(data)!=manifest['storage_root_xattrs']:
                raise ValueError('Installed root extended attributes differ')
            return dict(boot_files_verified=len(manifest['boot_files']),storage_entries_verified=len(manifest['storage']))
        finally:
            for target in reversed(mounts):run(['umount',str(target)])


def rehearse(snapshot_path,output):
    validate_snapshot(snapshot_path);output=private_external(output,create=True);loops=[]
    try:
        for name,size in [('ce_system.img',1024**3),('ce_storage.img',20*1024**3)]:
            path=output/name
            with path.open('xb') as f:f.truncate(size)
            device=run(['losetup','--find','--show',str(path)]).strip()
            if not device.startswith('/dev/loop'):raise ValueError('Unexpected loop device')
            loops.append(device)
        format_devices(*loops);verified=copy_and_verify(snapshot_path,*loops)
        result=dict(schema=1,kind='filesystem-image-rehearsal',passed=True,emmc_written=False,snapshot=str(Path(snapshot_path).resolve()),**verified)
        atomic_json(output/'result.json',result);return result
    finally:
        for device in reversed(loops):run(['losetup','-d',device])


def main():
    a=argparse.ArgumentParser(description=__doc__);sub=a.add_subparsers(dest='action',required=True)
    p=sub.add_parser('snapshot');p.add_argument('folder');p.add_argument('boot_stage')
    p=sub.add_parser('restore-services');p.add_argument('folder')
    p=sub.add_parser('rehearse');p.add_argument('snapshot');p.add_argument('output')
    args=a.parse_args()
    if args.action=='snapshot':result=snapshot(args.folder,args.boot_stage)
    elif args.action=='restore-services':result=restore_services(args.folder)
    else:result=rehearse(args.snapshot,args.output)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
