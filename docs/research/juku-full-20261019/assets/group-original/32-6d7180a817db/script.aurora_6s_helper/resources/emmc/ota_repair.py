#!/usr/bin/env python3
"""Foreground, metadata-only OTA recovery adapted from validated standalone 0.1.2."""
import contextlib,fcntl,hashlib,json,os,re,shutil,stat,struct,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
import operations as op
import policy
from aurora_emmc import read
from layout_trial import read_regions,write_regions,atomic_json,private_external
from prepare_boot import validate_stock_cfgload,ROOTOPT
from ota_repair_core import discover_layout,select_slot,check_environment,bump_dtb,sha,geometry,validate_kernel_header,validate_env_config,android_state

PLAN_SCHEMA=2
REPAIR_MODE='layout-only'
def run(args,timeout=120):
    p=subprocess.run(args,capture_output=True,timeout=timeout)
    if p.returncode:raise RuntimeError(' '.join(map(str,args))+': '+p.stderr.decode('utf-8',errors='replace'))
    return p.stdout.decode('utf-8',errors='strict').strip()
@contextlib.contextmanager
def environment_config(report=None, *, readonly=True):
    text=validate_env_config(read('/etc/fw_env.config'))
    from platform_support import branch
    with contextlib.ExitStack() as stack:
        if report is not None and branch(report['os_release'])=='Amlogic-ng':
            # Raw writes can invalidate NG named partition nodes. The unchanged
            # first 28 boundaries were validated before writing; never re-probe
            # through /dev/env or Android after committing metadata.
            op.raw_checkpoint(report)
            policy.layouts(report)
            row=report['mpt']['partitions'][3]
            if row['name']!='env' or row['size']!=8*1024**2:raise ValueError('Unknown env region')
            dev=stack.enter_context(op.region_dm(row['offset'],row['size'],readonly=readonly))
            if readonly:require_readonly(dev)
            text='%s 0x0 0x10000 0x10000\n'%dev
        tmp=stack.enter_context(tempfile.TemporaryDirectory(prefix='aurora-repair-env-'))
        config=Path(tmp)/'fw_env.config';config.write_text(text,encoding='ascii')
        yield config


def env_dump(report=None):
    with environment_config(report) as config:
        return run(['fw_printenv','-c',str(config)])


def env_read(report=None):
    out=env_dump(report);env={}
    for line in out.splitlines():
        if '=' in line:
            k,v=line.split('=',1)
            env[k]=v
    if any(k not in env for k in op.ENV_KEYS):raise ValueError('Missing required boot environment')
    return env

def check_env_device(report, *, raw=False):
    from platform_support import branch
    if raw and branch(report['os_release'])=='Amlogic-ng':
        with environment_config(report):pass
        return
    # Use an explicit config for /dev/env; never let fw_env.config target SPI/another disk.
    dev=os.stat('/dev/env')
    if not stat.S_ISBLK(dev.st_mode):raise ValueError('Invalid env device')
    p=Path('/sys/dev/block/%d:%d'%(os.major(dev.st_rdev),os.minor(dev.st_rdev))).resolve()
    row=report['mpt']['partitions'][3]
    if row['name']!='env' or p.parent.name!='mmcblk0' or int(read(p/'start'))*512!=row['offset'] or int(read(p/'size'))*512!=row['size']:
        raise ValueError('env partition identity mismatch')
    validate_env_config(read('/etc/fw_env.config'))

def read_at(offset,size):
    with open(op.DISK,'rb',buffering=0) as f:f.seek(offset);data=f.read(size)
    if len(data)!=size:raise ValueError('Short eMMC read')
    return data

def require_readonly(dev):
    # /dev/mapper aliases need not match sysfs names (dm-N). Query the opened
    # block device itself; never interpret a missing sysfs path as its RO state.
    with Path(dev).open('rb',buffering=0) as f:
        if not stat.S_ISBLK(os.fstat(f.fileno()).st_mode):
            raise ValueError('Read-only mapping is not a block device')
        readonly=struct.unpack('I',fcntl.ioctl(f.fileno(),0x125e,b'\0'*4))[0]  # BLKROGET
        if readonly!=1:
            raise ValueError('Mapping not read-only')


@contextlib.contextmanager
def mounted(row,report,fs):
    tmp=tempfile.mkdtemp(prefix='aurora-repair-ro-');mounted_ok=False
    try:
        with op.region_loop(row,report,readonly=True) as dev:
            require_readonly(dev)
            try:
                run(['mount','-t',fs,'-o','ro,noload' if fs=='ext4' else 'ro',str(dev),tmp]);mounted_ok=True
                yield Path(tmp),dev
            finally:
                if mounted_ok or os.path.ismount(tmp):run(['umount',tmp]);mounted_ok=False
    finally:
        if not os.path.ismount(tmp):
            try:os.rmdir(tmp)
            except OSError:pass

def file_hash(p,update,prefix):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(4*1024**2):
            h.update(b);update('repair-check','校验 CE 启动文件：'+p.name,progress_step=prefix+':sha:'+p.name,progress_done=f.tell(),progress_total=p.stat().st_size)
    return h.hexdigest()

def filesystem_check(report,target,update,prefix):
    boot,data=target[-3:-1];evidence={}
    for row,fs in [(boot,'vfat'),(data,'ext4')]:
        with op.region_loop(row,report,readonly=True) as dev:
            require_readonly(dev)
            fatcheck=shutil.which('fsck.fat') or shutil.which('fsck.vfat')
            if fs=='vfat' and not fatcheck:raise ValueError('Missing read-only FAT checker (fsck.fat/fsck.vfat)')
            args=[fatcheck,'-n',str(dev)] if fs=='vfat' else ['e2fsck','-f','-n',str(dev)]
            p=run_fsck(args,update,row['name'])
            evidence[row['name']+'-fsck']={'exit':p.returncode,'log':(p.stdout+p.stderr).decode('utf-8',errors='replace')}
            if p.returncode:raise ValueError('Read-only filesystem check failed: '+row['name']+'\n'+evidence[row['name']+'-fsck']['log'])
    with mounted(boot,report,'vfat') as (path,_):
        names=['kernel.img','SYSTEM','dtb.img','config.ini','cfgload']
        for name in names:
            p=path/name
            if not p.is_file() or p.is_symlink() or p.stat().st_size==0:raise ValueError('Missing boot file: '+name)
        update('repair-check','核对 CE 启动文件',progress_plan={**{stage+':sha:'+n:(path/n).stat().st_size for stage in ('repair-prepare','repair-recheck') for n in names},'repair-metadata:dtb':1048576,'repair-metadata:mpt':8192})
        validate_stock_cfgload((path/'cfgload').read_bytes())
        roots=[l.split('=',1)[1] for l in (path/'config.ini').read_text(encoding='utf-8').splitlines() if re.match(r'^rootopt=',l)]
        if roots!=[ROOTOPT]:raise ValueError('Unexpected internal rootopt')
        for name in ('kernel.img','SYSTEM'):
            with (path/name).open('rb') as f:magic=f.read(64)
            if name=='SYSTEM' and magic[:4]!=b'hsqs':raise ValueError('Invalid SYSTEM header')
            if name=='kernel.img':validate_kernel_header(magic,(path/name).stat().st_size)
        # Fresh hashes detect changes between inspection and application, not
        # authenticity. Release MD5 sidecars may be stale after tar updates.
        evidence['boot_files']={n:file_hash(path/n,update,prefix) for n in names}
    with mounted(data,report,'ext4') as (path,_):
        if not (path/'.kodi').is_dir() or not (path/'.config').is_dir():raise ValueError('CE data directories missing')
        evidence['data']={'kodi':True,'config':True}
    return evidence

def inspect_state(update,prefix,*,boot_layout=False):
    report=op.probe(repair_identity=True) if boot_layout else op.probe()
    if not boot_layout and report['os_release'].get('DISTRO_DEVICE')!='Amlogic-no':raise ValueError('First test supports CE NO 22.x only')
    if report['blockers']:raise ValueError('; '.join(report['blockers']))
    policy.identity(report);op.external(report);op.target_idle(report);check_env_device(report,raw=boot_layout)
    with open(op.DISK,'rb',buffering=0) as f:current=read_regions(f.fileno())
    policy.validate_dtb_layout(current['dtb'],report['mpt']['partitions'])
    target,inference=discover_layout(report,read_at)
    miscrow=next(p for p in report['mpt']['partitions'] if p['name']=='misc')
    misc=read_at(miscrow['offset'],65536)
    slot=android_state(misc) if boot_layout else select_slot(misc)
    env=env_read(report if boot_layout else None)
    check_environment(env,allow_short=True)
    update('repair-check','只读检查残留 CE 文件系统；此阶段进度按检查阶段显示')
    evidence=filesystem_check(report,target,update,prefix)
    # Detect changes during the read-only checks, not just at apply time.
    if current!={k:read_at(off,n) for k,off,n in [('dtb',40*1024**2,524288),('mpt',36*1024**2,4096)]} or misc!=read_at(miscrow['offset'],65536) or env!=env_read(report if boot_layout else None):raise ValueError('Metadata changed during inspection')
    info={'schema':PLAN_SCHEMA,'repair_mode':REPAIR_MODE,'boot_layout':boot_layout,'boot_id':read('/proc/sys/kernel/random/boot_id'),'cid':report['cid'],'emmc_bytes':report['emmc_bytes'],
          'model':report['android_models'],'source_hashes':{k:sha(v) for k,v in current.items()},'slot':None if boot_layout else slot,'android_state':slot if boot_layout else None,'environment_before':env,'environment_changes':{},
          'partitions':target,'inference':inference,'filesystems':evidence}
    return report,current,info

def store(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if path.read_bytes()!=data:raise ValueError('Local readback failure')

def prepare(folder,expected,update,*,boot_layout=False):
    report,current,info=inspect_state(update,'repair-prepare',boot_layout=boot_layout)
    op.same_device(expected,report)
    if os.statvfs('/storage').f_bavail*os.statvfs('/storage').f_frsize<64*1024**2:raise ValueError('Need 64MiB free external space')
    folder.mkdir(mode=0o700);private_external(folder)
    old,new=op.make_metadata(report,info['partitions'],folder/'metadata')
    if old!=current:raise ValueError('Metadata changed while generating candidate')
    new['dtb']=bump_dtb(current['dtb'],new['dtb'])
    policy.metadata_check(current['dtb'],new['dtb'],new['mpt'],report,info['partitions'])
    for k,v in new.items():store(folder/('repair-'+k+'.bin'),v)
    preserved={}
    for row in preserved_rows(report):
        raw=read_at(row['offset'],row['size']);store(folder/('before-'+row['name']+'.bin'),raw)
        preserved[row['name']]=sha(raw)
    for key,raw in current.items():store(folder/('before-'+key+'.bin'),raw)
    info['preserved_sha256']=preserved;info['candidate_hashes']={k:sha(v) for k,v in new.items()}
    info['runtime_sha256']=runtime_hash()
    atomic_json(folder/'plan.json',info);atomic_json(folder/'status.json',{'phase':'prepared','device_writes_started':False})
    return folder

def validate_plan_scope(plan):
    if plan.get('schema')!=PLAN_SCHEMA or plan.get('repair_mode')!=REPAIR_MODE:
        raise ValueError('Requires a new layout-only plan; run inspect with this version (old plans are rejected)')
    if plan.get('environment_changes')!={}:
        raise ValueError('Layout-only repair forbids environment changes')

def preserved_rows(report):
    return [next(p for p in report['mpt']['partitions'] if p['name']==name) for name in ('env','misc')]

def verify_preserved(fd,report,plan):
    for row in preserved_rows(report):
        data=os.pread(fd,row['size'],row['offset'])
        if len(data)!=row['size'] or sha(data)!=plan['preserved_sha256'][row['name']]:
            raise ValueError('Preserved region changed: '+row['name'])


def apply(folder,confirm,update,*,boot_layout=False):
    if not confirm:raise ValueError('Explicit --confirm-repair required; inspect the plan first')
    folder=private_external(folder);plan=json.loads((folder/'plan.json').read_text())
    validate_plan_scope(plan)
    if plan.get('boot_layout',False) != boot_layout:raise ValueError('Repair context changed; prepare a new plan')
    status=json.loads((folder/'status.json').read_text())
    if status['phase']!='prepared':raise ValueError('Plan already used or interrupted; do not replay')
    if plan['runtime_sha256']!=runtime_hash():raise ValueError('Different repair runtime')
    report,current,now=inspect_state(update,'repair-recheck',boot_layout=boot_layout)
    for key in ['schema','repair_mode','boot_id','cid','emmc_bytes','model','source_hashes','slot','android_state','environment_before','environment_changes','partitions','filesystems']:
        # fsck textual logs contain elapsed time; compare actual boot hashes separately.
        if key=='filesystems':
            if now[key]['boot_files']!=plan[key]['boot_files']:raise ValueError('CE boot files changed')
        elif now[key]!=plan[key]:raise ValueError('Plan stale: '+key)
    new={k:(folder/('repair-'+k+'.bin')).read_bytes() for k in ('dtb','mpt')}
    if {k:sha(v) for k,v in new.items()}!=plan['candidate_hashes']:raise ValueError('Candidate changed')
    policy.metadata_check(current['dtb'],new['dtb'],new['mpt'],report,now['partitions'])
    for row in preserved_rows(report):
        name=row['name']
        if sha(read_at(row['offset'],row['size']))!=plan['preserved_sha256'][name] or sha((folder/('before-'+name+'.bin')).read_bytes())!=plan['preserved_sha256'][name]:
            raise ValueError('Preserved region changed or backup damaged: '+name)
    for key,raw in current.items():
        if (folder/('before-'+key+'.bin')).read_bytes()!=raw:raise ValueError('Metadata backup damaged: '+key)
    op.external(report);op.target_idle(report);check_env_device(report,raw=boot_layout)
    # Kernel partition view is intentionally NOT reloaded. Reboot required afterwards.
    def record(phase):
        update('repair-writing','恢复分区描述并读回校验（不修改槽位和用户数据）',device_writes_started=True)
        atomic_json(folder/'status.json',{'phase':phase,'device_writes_started':True,'reboot_required':True})
        if phase.startswith('verified-'):
            key=phase.split('-',1)[1]
            update('repair-writing','分区元数据已读回核对：'+key,progress_step='repair-metadata:'+key,progress_done=2*len(new[key]),progress_total=2*len(new[key]))
    update('repair-check','写入前最后核对；仅恢复 DTB/MPT',progress_plan={'repair-metadata:'+k:2*len(v) for k,v in new.items()})
    fd=None
    try:
        fd=os.open(op.DISK,os.O_RDWR|os.O_CLOEXEC)
        if not stat.S_ISBLK(os.fstat(fd).st_mode):raise ValueError('Not an eMMC block device')
        capacity=struct.unpack('Q',fcntl.ioctl(fd,op.BLKGETSIZE64,b'\0'*8))[0]
        if capacity!=plan['emmc_bytes'] or read('/sys/block/mmcblk0/device/cid')!=plan['cid']:raise ValueError('Device identity changed')
        validate_plan_scope(plan)
        if env_read(report if boot_layout else None)!=plan['environment_before']:raise ValueError('Environment changed before write')
        verify_preserved(fd,report,plan)
        write_regions(fd,current,new,record)
        verify_preserved(fd,report,plan)
        if env_read(report if boot_layout else None)!=plan['environment_before']:raise ValueError('Environment changed after metadata write')
        if read_regions(fd)!=new:raise ValueError('Final metadata readback mismatch')
        os.sync();atomic_json(folder/'status.json',{'phase':'complete','device_writes_started':True,'reboot_required':True})

    except BaseException as exc:
        prior=json.loads((folder/'status.json').read_text())
        atomic_json(folder/'status.json',{'phase':'needs-review' if prior.get('device_writes_started') else 'failed-before-write','device_writes_started':prior.get('device_writes_started',False),'error':str(exc),'backup':str(folder)})
        raise
    finally:
        if fd is not None:os.close(fd)


def runtime_hash():
    h=hashlib.sha256()
    for path in sorted(ROOT.glob('*.py'))+[ROOT/'bin/ampart']:
        h.update(path.relative_to(ROOT).as_posix().encode()+b'\0');h.update(path.read_bytes())
    return h.hexdigest()


def run_fsck(args,update,name,*,writing=False):
    # Poll only to update the foreground UI/cancellation, never invent byte counts.
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
        started=time.monotonic()
        try:
            while True:
                update('repair-writing' if writing else 'repair-check',
                       ('回放 CE 文件系统日志：' if writing else '只读检查文件系统：')+name+
                       ('（不要取消、断电或操作设备）' if writing else '（不修改文件系统）'))
                try:
                    stdout,stderr=process.communicate(timeout=1)
                    return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
                except subprocess.TimeoutExpired:
                    if time.monotonic()-started>1800:raise TimeoutError('文件系统只读检查超时：'+name)
        finally:
            if process.poll() is None:process.kill();process.communicate()


def assess(report):
    """Bounded read-only preview for UI/submit; full checks run in foreground."""
    from platform_support import branch
    if branch(report['os_release'])!='Amlogic-no':
        raise ValueError('OTA 布局修复目前仅支持 NO 22.x；尚未验证 NG')
    if report['blockers']:raise ValueError('; '.join(report['blockers']))
    check_env_device(report)
    target,inference=discover_layout(report,read_at)
    env=env_read();check_environment(env,allow_short=True)
    misc=next(p for p in report['mpt']['partitions'] if p['name']=='misc')
    slot=select_slot(read_at(misc['offset'],65536))
    report['ota_repair']={'repair_mode':REPAIR_MODE,'environment_changes':{},'partitions':target,
        'inference':inference,'misc_selected_slot':slot['selected']}
    return report


def execute(folder,report,update,*,boot_layout=False):
    # Worker owns both eMMC locks, confirmation, lifecycle and final job state.
    prepared=prepare(folder/'layout-repair',report,update,boot_layout=boot_layout)
    plan=json.loads((prepared/'plan.json').read_text())
    if geometry(plan['partitions'])!=geometry(report['ota_repair']['partitions']):
        raise ValueError('恢复布局与确认时不同，请重新检查')
    apply(prepared,True,update,boot_layout=boot_layout)
