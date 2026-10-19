#!/usr/bin/env python3
"""Guarded metadata-only layout trial. No formatting, boot-env changes or reboot.
prepare/verify are read-only for eMMC; apply/rollback require a reviewed token.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile

from aurora_emmc import probe, plan, parse_mpt, read, props, mountinfo, disk_parent, command, MIB
from backup_emmc import assert_no_rw_emmc_mount
from block_device import BLKGETSIZE64
from check_backup import inspect, safe_file
from extract_recovery_metadata import validate_dtb_slots
from prepare_boot_environment import BOOTCMD

REGIONS = [('dtb', 40*MIB, 512*1024), ('mpt', 36*MIB, 4096)]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fdt(raw):
    if len(raw) < 40:
        raise ValueError('Short FDT header')
    magic,total,so,st,mo,ver,compat,cpu,ss,sz = struct.unpack_from('>10I',raw)
    if magic != 0xd00dfeed or total > len(raw) or ver != 17 or compat > 17:
        raise ValueError('Unsupported FDT header')
    if so+sz > total or st+ss > total or min(so,st,mo) < 40:
        raise ValueError('FDT area out of bounds')
    strings=raw[st:st+ss]; data=raw[so:so+sz]; stack=[]; nodes={}; pos=0
    while pos+4 <= len(data):
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token==1:
            end=data.index(b'\0',pos);name=data[pos:end].decode('ascii');pos=(end+4)&~3
            if '/' in name or (not stack and name):raise ValueError('Invalid FDT node name')
            stack.append(name);path='/'.join(stack) or '/'
            if path in nodes:raise ValueError('Duplicate FDT node')
            nodes[path]={}
        elif token==2:
            if not stack:raise ValueError('Unbalanced FDT')
            stack.pop()
        elif token==3:
            if not stack or pos+8>len(data):raise ValueError('Invalid FDT property')
            size,nameoff=struct.unpack_from('>II',data,pos);pos+=8
            if pos+size>len(data) or nameoff>=len(strings):raise ValueError('FDT property out of bounds')
            end=strings.index(b'\0',nameoff);name=strings[nameoff:end].decode('ascii');path='/'.join(stack) or '/'
            if name in nodes[path]:raise ValueError('Duplicate FDT property')
            nodes[path][name]=data[pos:pos+size];pos=(pos+size+3)&~3
        elif token==4:continue
        elif token==9:
            if stack:raise ValueError('Unbalanced FDT end')
            break
        else:raise ValueError('Unsupported FDT token')
    else:raise ValueError('No FDT end marker')
    reservations=[]
    while mo+16<=total:
        pair=struct.unpack_from('>QQ',raw,mo);mo+=16
        if pair==(0,0):break
        reservations.append(pair)
    else:raise ValueError('Unterminated FDT reserve map')
    return nodes,(ver,compat,cpu,reservations)


def validate_candidate(old_dtb,new_dtb,new_mpt,report):
    validate_dtb_slots(old_dtb);validate_dtb_slots(new_dtb)
    if any(new_dtb[p+262128:p+262136]!=old_dtb[262128:262136] for p in (0,262144)):
        raise ValueError('DTB footer magic/version changed')
    expected=plan(report,20,1024,'reset-data',16)['partitions']
    actual=parse_mpt(new_mpt,report['emmc_bytes'])['partitions']
    fields=('index','name','offset','size','flags')
    if len(actual)!=len(expected) or any(any(a[k]!=b[k] for k in fields) for a,b in zip(actual,expected)):
        raise ValueError('Candidate MPT differs from independently calculated layout')
    old,_=fdt(old_dtb)
    old_hw={p:v for p,v in old.items() if p!='/partitions' and not p.startswith('/partitions/')}
    first=None
    for start in (0,262144):
        nodes,header=fdt(new_dtb[start:start+262144])
        if header!=fdt(old_dtb)[1]:raise ValueError('Nonpartition FDT header/reservations changed')
        if {p:v for p,v in nodes.items() if p!='/partitions' and not p.startswith('/partitions/')}!=old_hw:
            raise ValueError('Hardware properties changed outside /partitions')
        if first is not None and nodes!=first:raise ValueError('DTB copies disagree')
        first=nodes;parts=nodes['/partitions'];count=struct.unpack('>I',parts['parts'])[0]
        explicit=expected[4:]
        if count!=len(explicit):raise ValueError('Wrong DT partition count')
        handles={}
        for path,props in nodes.items():
            if 'phandle' in props:
                key=props['phandle']
                if key in handles:raise ValueError('Duplicate phandle')
                handles[key]=path
        for i,row in enumerate(explicit):
            path=handles[parts['part-'+str(i)]];props=nodes[path]
            wanted_size=0xffffffffffffffff if i==len(explicit)-1 else row['size']
            if path!='/partitions/'+row['name'] or props['pname']!=row['name'].encode()+b'\0' or props['size']!=struct.pack('>Q',wanted_size) or props['mask']!=struct.pack('>I',row['flags']):
                raise ValueError('DTB partition disagrees with MPT: '+row['name'])
    return expected


def atomic_json(path,value):
    path=Path(path)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def private_external(path,create=False):
    path=Path(path)
    if path.is_symlink() or not str(path.resolve()).startswith('/storage/aurora-emmc-'):
        raise ValueError('Use a real /storage/aurora-emmc-* directory')
    if create:path.mkdir(mode=0o700,parents=False)
    if not path.is_dir() or path.stat().st_dev!=Path('/storage').stat().st_dev:
        raise ValueError('Ticket must remain on external /storage filesystem')
    for line in read('/proc/self/mountinfo').splitlines():
        mount=line.split(' - ',1)[0].split()[4]
        if mount.startswith('/storage/') and (str(path.resolve())==mount or str(path.resolve()).startswith(mount+'/')):
            raise ValueError('Nested ticket/backup mount refused')
    return path.resolve()


def live_check(ticket=None,recovery=False):
    if recovery:
        # Do not parse an interrupted MPT or require a reread before rollback.
        release={k:v.strip('"') for k,v in props('/etc/os-release').items()}
        models=set()
        for path in ('/android/system/system/build.prop','/android/vendor/build.prop'):
            models.update(v for k,v in props(path).items() if k.startswith('ro.product.') and k.endswith('.model'))
        roots={m['mountpoint']:m for m in mountinfo() if m['mountpoint'] in ('/flash','/storage')}
        if release.get('ID')!='coreelec' or release.get('DISTRO_DEVICE')!='Amlogic-no' or models not in ({'A4111'}, {'A4112'}):
            raise ValueError('Recovery requires A4111/A4112 on CE NO')
        if any(p not in roots or disk_parent(roots[p]['dev'])=='mmcblk0' for p in ('/flash','/storage')):
            raise ValueError('Recovery requires external CE')
        for row in ticket['partitions'][:28]:
            base=Path('/sys/block/mmcblk0')/row['name']
            if read(base/'start')!=str(row['offset']//512) or read(base/'size')!=str(row['size']//512):
                raise ValueError('Original system partition kernel boundaries changed')
        report={'blockers':[],'android_models':sorted(models),'os_release':release,
                'emmc_bytes':int(read('/sys/block/mmcblk0/size'))*512}
    else:
        report=probe()
    if report['blockers'] or report['android_models'] not in (['A4111'], ['A4112']) or report['os_release'].get('DISTRO_DEVICE')!='Amlogic-no':
        raise ValueError('Wrong board/OS/boot device or inconsistent kernel partition state')
    if read('/proc/sys/kernel/random/boot_id')=='':raise ValueError('Missing boot ID')
    assert_no_rw_emmc_mount()
    cid=read('/sys/block/mmcblk0/device/cid')
    if not cid:raise ValueError('Missing eMMC identity')
    if ticket and (cid!=ticket['cid'] or report['emmc_bytes']!=ticket['emmc_bytes']):
        raise ValueError('eMMC identity/capacity differs from prepared transaction')
    return report,cid


def boot_environment():
    result={}
    for key in ('bootcmd','bootfromemmc','cfgloademmc','bootfromnand'):
        found=command('fw_printenv',key)
        if found['returncode'] or not found['stdout'].startswith(key+'='):
            raise ValueError('Cannot inspect boot environment: '+key)
        result[key]=found['stdout'][len(key)+1:]
    if result['bootcmd']!=BOOTCMD or result['bootfromnand']!='0' or result['bootfromemmc']!='run cfgloademmc':
        raise ValueError('External boot priority or Android boot selection changed')
    return result


def read_regions(fd):
    result={}
    for name,offset,size in REGIONS:
        data=os.pread(fd,size,offset)
        if len(data)!=size:raise ValueError('Short device read')
        result[name]=data
    return result


def load_ticket(folder):
    folder=private_external(folder)
    ticket=json.loads(safe_file(folder,'ticket.json').read_text())
    original={};candidate={}
    for name,offset,size in REGIONS:
        for group,into in [('original',original),('candidate',candidate)]:
            raw=safe_file(folder,group+'-'+name+'.bin').read_bytes()
            if len(raw)!=size or digest(raw)!=ticket['hashes'][group][name]:raise ValueError('Ticket artifact changed')
            into[name]=raw
    report_raw=safe_file(folder,'original-probe.json').read_bytes()
    if digest(report_raw)!=ticket['original_probe_sha256']:raise ValueError('Original probe artifact changed')
    report=json.loads(report_raw)
    validate_candidate(original['dtb'],candidate['dtb'],candidate['mpt'],report)
    # Token covers immutable evidence, including disk identity and all proposed bytes.
    token=ticket.pop('token');calculated=digest(json.dumps(ticket,sort_keys=True).encode())
    ticket['token']=token
    if token!=calculated:raise ValueError('Ticket digest mismatch')
    return folder,ticket,original,candidate


def prepare(backup,candidate,folder):
    report,cid=live_check();plan(report,20,1024,'reset-data',16)
    backup=private_external(backup);inspect(backup)
    backed=json.loads(safe_file(backup,'probe-before.json').read_text())
    for key in ('mpt_sha256','android_dtb_sha256','emmc_bytes'):
        if report[key]!=backed[key]:raise ValueError('Backup differs from current source')
    # Independently obtain original bytes from full verified backup, not a regenerated DTS.
    with safe_file(backup,'mmcblk0.img').open('rb') as f:original=read_regions(f.fileno())
    new={name:safe_file(Path(candidate),filename).read_bytes() for name,filename in [('dtb','dtb-two-slots.bin'),('mpt','mpt-4k.bin')]}
    layout=validate_candidate(original['dtb'],new['dtb'],new['mpt'],report)
    with open('/dev/mmcblk0','rb',buffering=0) as f:
        if read_regions(f.fileno())!=original:raise ValueError('Live metadata differs from full backup')
    folder=private_external(folder,create=True)
    for group,data in [('original',original),('candidate',new)]:
        for name,raw in data.items():
            with (folder/(group+'-'+name+'.bin')).open('xb') as f:
                os.chmod(f.name,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
    atomic_json(folder/'original-probe.json',report)
    ticket=dict(boot_environment=boot_environment(),original_probe_sha256=digest((folder/'original-probe.json').read_bytes()),schema=1,kind='metadata-only-reset-layout-trial',cid=cid,emmc_bytes=report['emmc_bytes'],
                prepared_boot_id=read('/proc/sys/kernel/random/boot_id'),backup=str(backup),
                hashes={g:{k:digest(v) for k,v in data.items()} for g,data in [('original',original),('candidate',new)]},
                partitions=layout,forbidden_actions=['format','wipe userdata','write bootloader','write boot0/1','change boot environment','automatic reboot'],
                notes=['Only 4 KiB MPT and two 256 KiB DTB copies may be written.',
                       'Metadata changes are not atomic across power loss.',
                       'Keep external CE attached. Do not boot Android before rollback or later installation review.',
                       'Rollback restores metadata only, not overwritten userdata or hardware-secured key state.'])
    ticket['token']=digest(json.dumps(ticket,sort_keys=True).encode())
    atomic_json(folder/'ticket.json',ticket);atomic_json(folder/'state.json',dict(phase='prepared'))
    return ticket


def owned_bytes(current,old,new):
    return len(current)==len(old)==len(new) and all(current[i:i+512] in (old[i:i+512],new[i:i+512]) for i in range(0,len(old),512))


def write_regions(fd,before,after,record):
    # All regions checked before the first write; never silently overwrite an unrelated change.
    if read_regions(fd)!=before:raise ValueError('Device changed before first write')
    for name,offset,size in REGIONS:
        record('writing-'+name)
        data=after[name]
        for pos in range(0,size,512):
            if os.pwrite(fd,data[pos:pos+512],offset+pos)!=512:raise OSError('Short metadata write')
        os.fsync(fd)
        if os.pread(fd,size,offset)!=data:raise OSError('Metadata write readback mismatch')
        record('verified-'+name)


def inspect_live(folder):
    folder,ticket,old,new=load_ticket(folder);report,_=live_check(ticket)
    with open('/dev/mmcblk0','rb',buffering=0) as f:current=read_regions(f.fileno())
    raw_state='original' if current==old else 'candidate' if current==new else 'mixed-or-unexpected'
    expected_rows=ticket['partitions'] if raw_state=='candidate' else json.loads(safe_file(folder,'original-probe.json').read_text())['mpt']['partitions']
    actual=report['mpt']['partitions'];fields=('index','name','offset','size','flags')
    geometry=(raw_state!='mixed-or-unexpected' and len(actual)==len(expected_rows) and
              all(all(a[k]==b[k] for k in fields) for a,b in zip(actual,expected_rows)))
    return dict(raw_state=raw_state,kernel_geometry_matches=geometry,
                rebooted_since_prepare=read('/proc/sys/kernel/random/boot_id')!=ticket['prepared_boot_id'],
                sysfs_matches=all(p['sysfs_matches'] for p in actual),writes_performed=False)


def change(folder,token,rollback=False):
    folder,ticket,old,new=load_ticket(folder)
    if token!=ticket['token']:raise ValueError('Explicit reviewed transaction token required')
    # probe detects stale geometry after a layout write: reboot to external CE is mandatory.
    live_check(ticket,recovery=rollback)
    if not rollback and read('/proc/sys/kernel/random/boot_id')!=ticket['prepared_boot_id']:
        raise ValueError('Prepare a new transaction after reboot before applying')
    state=json.loads(safe_file(folder,'state.json').read_text())
    if not rollback and boot_environment()!=ticket['boot_environment']:
        raise ValueError('Boot environment changed since preparation')
    if not rollback and state['phase']!='prepared':raise ValueError('Apply requires an unused prepared transaction')
    if rollback and state['phase'] not in ('applied-awaiting-reboot','writing-dtb','verified-dtb','writing-mpt','verified-mpt','rollback-writing-dtb','rollback-verified-dtb','rollback-writing-mpt','rollback-verified-mpt'):
        raise ValueError('No owned layout write to roll back')
    inspect(private_external(ticket['backup']))
    fd=os.open('/dev/mmcblk0',os.O_RDWR|os.O_CLOEXEC)
    try:
        if not stat.S_ISBLK(os.fstat(fd).st_mode):raise ValueError('Not an eMMC block device')
        if struct.unpack('Q',fcntl.ioctl(fd,BLKGETSIZE64,b'\0'*8))[0]!=ticket['emmc_bytes']:raise ValueError('Device capacity changed')
        current=read_regions(fd)
        if rollback:
            if not all(owned_bytes(current[k],old[k],new[k]) for k in old):raise ValueError('Unknown metadata changes; manual recovery review required')
        elif current!=old:raise ValueError('Original metadata changed')
        target=old if rollback else new
        prefix='rollback-' if rollback else ''
        def record(phase):atomic_json(folder/'state.json',dict(phase=prefix+phase,boot_id=read('/proc/sys/kernel/random/boot_id')))
        write_regions(fd,current,target,record)
        final='rolled-back-awaiting-reboot' if rollback else 'applied-awaiting-reboot'
        atomic_json(folder/'state.json',dict(phase=final,boot_id=read('/proc/sys/kernel/random/boot_id')))
        return dict(phase=final,reboot_executed=False,formatted=False)
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('backup');p.add_argument('candidate');p.add_argument('folder')
    p=sub.add_parser('verify');p.add_argument('folder')
    for action in ('apply','rollback'):
        p=sub.add_parser(action);p.add_argument('folder');p.add_argument('--confirm-token',required=True)
    args=parser.parse_args()
    lock=open('/run/aurora-emmc-layout.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if args.action=='prepare':result=prepare(args.backup,args.candidate,args.folder)
        elif args.action=='verify':result=inspect_live(args.folder)
        else:result=change(args.folder,args.confirm_token,args.action=='rollback')
        print(json.dumps(result,indent=2))
    except (OSError,ValueError,KeyError,TypeError,struct.error) as exc:parser.exit(1,'Layout trial refused/stopped: '+str(exc)+'\n')

if __name__=='__main__':main()
