"""Privileged eMMC operations. Entry point is worker.py, never a Kodi service."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import uuid
import sys

from aurora_emmc import probe, read, mountinfo, disk_parent, MIB
from block_device import BLKGETSIZE64
from backup_emmc import acquire, depends_on_emmc, assert_no_rw_emmc_mount
from check_backup import inspect, safe_file
from layout_trial import atomic_json, read_regions, write_regions, private_external
from prepare_boot import validate_stock_cfgload, STOCK_CFGLOAD
import prepare_boot
import stage_system
import policy
from backup_identity import read_identity

BASE = Path('/storage/aurora-emmc-jobs')
BACKUPS = Path('/storage/aurora-emmc-backups')
ENV_KEYS = ('bootcmd','cfgloademmc','bootfromemmc','storeboot','bootfromnand','active_slot')
DISK = '/dev/mmcblk0'


def run(args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, 'LC_ALL':'C'})
    if p.returncode:raise RuntimeError(' '.join(map(str,args))+'\n'+p.stderr.strip())
    return p.stdout.strip()


def environment(options=()):
    env = {}
    for key in ENV_KEYS:
        raw = run(['fw_printenv', *options, key])
        if not raw.startswith(key+'='):raise ValueError('无法读取启动环境：'+key)
        env[key] = raw[len(key)+1:]
    return env


def external(report):
    for name in ('/flash','/storage'):
        m = report['mounts'].get(name)
        if not m or depends_on_emmc(m['dev']) or m['parent_disk'] not in ('sda','sdb','sdc','sdd','mmcblk1'):
            raise ValueError('请从 SD / USB 的外置 CE 启动后操作；不能在内置 CE 上改写 eMMC')
    if report['mounts']['/storage']['fs'] != 'ext4':raise ValueError('外置 /storage 必须是 ext4')
    if os.statvfs('/flash').f_flag & os.ST_RDONLY == 0:raise ValueError('请保持 /flash 只读')
    assert_no_rw_emmc_mount()
    for line in read('/proc/swaps').splitlines()[1:]:
        info = os.stat(line.split()[0])
        node = Path('/sys/dev/block/%d:%d'%(os.major(info.st_rdev),os.minor(info.st_rdev))).resolve()
        if stat.S_ISBLK(info.st_mode) and re.fullmatch(r'zram[0-9]+',node.name) and read(node/'backing_dev') in ('','none'):
            continue
        raise ValueError('请先停用磁盘交换分区/文件再操作 eMMC；纯内存 zram 可保留')


def target_idle(report, all_parts=False):
    names = [p['name'] for p in report['mpt']['partitions'] if all_parts or p['index'] > 28]
    for name in names:
        node = Path('/sys/block/mmcblk0')/name
        dev = read(node/'dev')
        if any(m['dev'] == dev for m in mountinfo()) or list((node/'holders').glob('*')):
            raise ValueError('目标分区仍被挂载或映射使用：'+name)
    # Existing loop aliases over the raw eMMC could write outside our controlled mappings.
    for node in Path('/sys/block').glob('loop*/loop/backing_file'):
        path = read(node)
        if path and Path(path).exists():
            info = Path(path).stat()
            if stat.S_ISBLK(info.st_mode) and depends_on_emmc('%d:%d'%(os.major(info.st_rdev), os.minor(info.st_rdev))):
                raise ValueError('发现正在使用的 eMMC loop 映射')


def assess(action=None, backup=None, android_gib=None):
    if android_gib is not None and action != 'install':raise ValueError('只有安装操作可选择 Android 容量')
    report = probe(repair_identity=True) if action == 'repair' else probe()
    policy.identity(report)
    layout, stock, dual = policy.layouts(report)
    report['layout'] = layout
    with open(DISK,'rb',buffering=0) as f:regions = read_regions(f.fileno())
    if hashlib.sha256(regions['dtb']).hexdigest() != report['android_dtb_sha256']:
        raise ValueError('/dev/dtb 与原始 eMMC DTB 不一致')
    policy.validate_dtb_layout(regions['dtb'],report['mpt']['partitions'])
    if action:
        external(report);target_idle(report)
        if action == 'install' and layout != 'stock':raise ValueError('已经存在内置 CE，请勿重复安装')
        if action == 'remove' and layout != 'dual':raise ValueError('未发现本助手支持的内置 CE 布局')
        if action in ('install','remove'):
            env = environment();policy.environment_change(env,action)
        if action == 'install':
            validate_stock_cfgload(STOCK_CFGLOAD.read_bytes())
            for tool in ('losetup','mkfs.vfat','mkfs.ext4','rsync'):
                if not shutil.which(tool):raise ValueError('缺少工具：'+tool)
            if list(Path('/storage/.update').glob('*')):raise ValueError('请先完成或移走待安装的 CE 更新包')
        if action == 'repair':
            import dual_repair
            dual_repair.assess(report)
        if action == 'restore':
            if not backup:raise ValueError('未选择备份')
            folder = private_external(backup);inspect(folder)
            saved = read_identity(folder)
            policy.backup_matches(report,saved)
        # Full-image space is required only for an explicit manual backup.
        free = os.statvfs('/storage');available=free.f_bavail*free.f_frsize
        needed = 512*MIB
        if action == 'backup':
            needed += report['emmc_bytes']+sum(report['boot_areas'].values())
        if action == 'install':
            # Snapshot + reserve; exclude backups and jobs through scan policy.
            from inspect_storage import scan_tree,rsync_flags
            from storage_mounts import storage_source
            with storage_source() as source:
                inventory=scan_tree(source)
            rsync_flags(run(['rsync','--version']),inventory,metadata_fallback=True)
            usage = storage_bytes()
            choices = policy.capacity_choices(report, usage)
            selected = android_gib if android_gib is not None else min(16, choices[-1]['android_gib'])
            target = policy.install_layout(report, selected)
            if usage > policy.ce_data_limit(target[29]['size']):
                raise ValueError('所选容量无法容纳当前 CE 数据及预留空间，请减少 Android 用户区容量')
            report.update(capacity_choices=choices, android_gib=selected,
                          ce_storage_bytes=target[29]['size'], ce_system_bytes=target[28]['size'])
            boot_files,boot_dirs=prepare_boot.source_inventory(partition_bytes=target[28]['size'])
            report['boot_source_bytes']=sum(boot_files.values())
            report['boot_source_files']=len(boot_files)
            needed += usage + 1024*MIB
        if available < needed:raise ValueError('外置空间不足：需约 %.1f GiB 可用空间（本次操作暂存）'%(needed/1024**3))
        report['required_free_bytes']=needed
    return report


def storage_bytes():
    total=0
    excluded=('aurora-emmc-backups','aurora-emmc-staging','aurora-emmc-jobs','lost+found')
    for base,dirs,files in os.walk('/storage',followlinks=False):
        if base=='/storage':dirs[:]=[d for d in dirs if d not in excluded]
        for name in files:
            path=Path(base)/name
            if not path.is_symlink() and path.is_file():total+=path.stat().st_size
    return total


def same_device(saved, live):
    policy.identity(live);external(live)
    for key in ('cid','emmc_bytes','boot_areas','android_models','mpt_sha256','android_dtb_sha256'):
        if live[key] != saved[key]:raise ValueError('设备或分区状态已改变：'+key)
    for key in ('/flash','/storage'):
        if live['mounts'][key]['dev'] != saved['mounts'][key]['dev']:raise ValueError('外置启动介质已改变')


def full_backup(report, update):
    if BACKUPS.is_symlink():raise ValueError('备份路径不能是符号链接')
    BACKUPS.mkdir(mode=0o700,exist_ok=True);private_external(BACKUPS)
    folder=BACKUPS/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(mode=0o700)
    atomic_json(folder/'probe-before.json',report)
    entries=[]
    for name,size in [('mmcblk0',report['emmc_bytes']),*sorted(report['boot_areas'].items())]:
        update('backup','备份并读回校验 '+name,backup=str(folder))
        entries.append(acquire('/dev/'+name,folder/(name+'.img'),size,
            progress=lambda phase,done,total,n=name: update('backup',
                ('备份写入 ' if phase=='copy' else '备份读回校验 ')+n,
                progress_step=phase+':'+n,progress_done=done,progress_total=total)))
    with open(DISK,'rb',buffering=0) as f:regions=read_regions(f.fileno())
    (folder/'android-dtb.raw').write_bytes(regions['dtb'])
    live=probe();same_device(report,live);assert_no_rw_emmc_mount()
    atomic_json(folder/'probe-after.json',live)
    manifest=dict(schema=1,status='verified',artifacts=entries,android_dtb_sha256=report['android_dtb_sha256'],
        mpt_sha256=report['mpt_sha256'],cid=report['cid'],limitations=['不包含 RPMB、eFuse 或 eMMC 硬件配置；不是 USB 线刷包；加密数据能否恢复取决于未包含的安全状态'])
    atomic_json(folder/'manifest.json',manifest);inspect(folder)
    return folder


def make_metadata(report, target, folder):
    folder.mkdir(mode=0o700)
    with open(DISK,'rb',buffering=0) as f:old=read_regions(f.fileno())
    for key,raw in old.items():(folder/('original-'+key+'.bin')).write_bytes(raw)
    fake=folder/'simulation.img'
    with fake.open('xb') as f:
        f.truncate(report['emmc_bytes']);f.seek(36*MIB);f.write(old['mpt']);f.seek(40*MIB);f.write(old['dtb'])
    tool=Path(__file__).parent/'bin/ampart'
    args=[str(tool),str(fake),'--mode','dclone','--migrate','none']
    args += [r['name']+'::'+str(r['size'])+':'+str(r['flags']) for r in target[4:]]
    args[-1]='userdata::-1:4'
    try:
        (folder/'ampart.log').write_text(run(args))
        with fake.open('rb') as f:new=read_regions(f.fileno())
        policy.metadata_check(old['dtb'],new['dtb'],new['mpt'],report,target)
        for key,raw in new.items():(folder/('candidate-'+key+'.bin')).write_bytes(raw)
        return old,new
    finally:fake.unlink()


def backend_for(report):
    from platform_support import branch
    if branch(report['os_release']) == 'Amlogic-ng':
        import ng_backend
        return ng_backend
    import no_backend
    return no_backend


@contextlib.contextmanager
def region_loop(row, report, readonly=False):
    # Historical name retained; callers receive a bounded device on either OS.
    off,size=policy.bounded_region(row,report['emmc_bytes'],report['mpt']['partitions'][28]['offset'])
    with backend_for(report).region(sys.modules[__name__],off,size,readonly) as mapped:
        yield mapped


@contextlib.contextmanager
def region_dm(off,size,readonly=False):
    import ng_backend
    with ng_backend.region_dm(sys.modules[__name__],off,size,readonly) as mapped:
        yield mapped


def zero_userdata(row,report):
    with region_loop(row,report) as dev:
        with dev.open('r+b',buffering=0) as f:
            if f.write(b'\0'*4096)!=4096:raise OSError('userdata 头写入不完整')
            os.fsync(f.fileno());f.seek(0)
            if f.read(4096)!=b'\0'*4096:raise OSError('userdata 头读回不一致')


def commit_metadata(report, old, new, folder, update):
    # Partition view deliberately remains old until final boot. Never use it for writes.
    backend_for(report).checkpoint(sys.modules[__name__],report)
    target_idle(report)
    fd=os.open(DISK,os.O_RDWR|os.O_CLOEXEC)
    try:
        if not stat.S_ISBLK(os.fstat(fd).st_mode):raise ValueError('不是 eMMC 块设备')
        def record(phase):
            name=phase.split('-',1)[1]
            update('metadata-writing',phase,progress_step='metadata:'+name,
                   progress_done=2*len(new[name]) if phase.startswith('verified-') else 0,
                   progress_total=2*len(new[name]))
        write_regions(fd,old,new,record)
    finally:os.close(fd)


def raw_checkpoint(report):
    import ng_backend
    return ng_backend.raw_checkpoint(sys.modules[__name__],report)


@contextlib.contextmanager
def environment_options(report=None):
    if report is None:
        yield []
        return
    with backend_for(report).environment_options(sys.modules[__name__],report) as options:
        yield options


def change_environment(before, action, report=None):
    with environment_options(report) as options:
        if environment(options)!=before:raise ValueError('引导环境在操作期间发生改变')
        new=policy.environment_change(before,action)
        run(['fw_setenv',*options,'cfgloademmc',new])
        after=environment(options)
        expected=dict(before,cfgloademmc=new)
        if after!=expected:raise ValueError('引导设置读回不一致')


@contextlib.contextmanager
def android_restore_session(update):
    """Release CE's Android-backed TEE process; restart only before any write."""
    unit = 'opentee_linuxdriver.service'
    active = run(['systemctl', 'show', unit, '-p', 'ActiveState', '--value']) == 'active'
    stopped = False
    wrote = False
    failure = None

    def progress(phase, message, **extra):
        nonlocal wrote
        update(phase, message, **extra)
        if extra.get('device_writes_started'):
            wrote = True

    try:
        if active:
            update('preparing', '暂停 Android TEE 服务，释放分区占用')
            # ExecStop may partly succeed even if systemctl subsequently reports failure.
            stopped = True
            run(['systemctl', 'stop', unit])
        yield progress
    except BaseException as exc:
        failure = exc
        raise
    finally:
        if stopped and not wrote:
            try:
                run(['systemctl', 'start', unit])
            except Exception as exc:
                raise RuntimeError('%s；恢复 Android TEE 服务失败：%s' %
                                   (failure or '尚未写入 eMMC', exc)) from exc
        # Once disk content may differ, do not start Android binaries through stale
        # kernel partitions/DM mappings. The user must reboot after restore.


def detach_android(report):
    # Called only by full restore after identity/hash validation.
    mounts=[m for m in mountinfo() if depends_on_emmc(m['dev'])]
    if any(not m['mountpoint'].startswith('/android/') for m in mounts):raise ValueError('存在 Android 只读挂载以外的 eMMC 挂载，拒绝还原')
    for m in sorted(mounts,key=lambda m:len(m['mountpoint']),reverse=True):
        unit=m['mountpoint'].strip('/').replace('/','-')+'.mount'
        run(['systemctl','stop',unit])
    if any(depends_on_emmc(m['dev']) for m in mountinfo()):raise ValueError('无法完全卸载 eMMC')
    # Remove only eMMC-backed DM devices, leaf first; no global dmsetup remove_all.
    for _ in range(16):
        nodes=[n for n in Path('/sys/block').glob('dm-*') if depends_on_emmc(read(n/'dev'))]
        if not nodes:break
        leaves=[n for n in nodes if not list((n/'holders').glob('*'))]
        if not leaves:raise ValueError('无法卸载 eMMC 设备映射')
        for n in leaves:run(['dmsetup','remove',read(n/'dm/name')])
    target_idle(report,all_parts=True)


def _progress(update, phase, name, done, size):
    if update:
        labels = {'verifying': '校验备份', 'restoring': '写入', 'readback': '读回校验'}
        update(phase, '%s %s：%.1f / %.1f GiB' %
               (labels[phase], name, done / 1024**3, size / 1024**3),
               progress_step=phase+':'+name, progress_done=done, progress_total=size)


def _hash_stream(stream, size, update, phase, name):
    stream.seek(0)
    digest = hashlib.sha256()
    done = 0
    last = time.monotonic()
    _progress(update, phase, name, done, size)
    while done < size:
        data = stream.read(min(8*MIB, size-done))
        if not data:
            raise ValueError('镜像/设备读取不完整：' + name)
        digest.update(data)
        done += len(data)
        if time.monotonic()-last >= 10:
            _progress(update, phase, name, done, size)
            last = time.monotonic()
    _progress(update, phase, name, done, size)
    return digest.hexdigest()


class _VerifiedImage:
    """An open source whose complete hash was checked during this restore run."""
    def __init__(self, path, stream, size, digest):
        self.path, self.stream, self.size, self.digest = path, stream, size, digest
        self.stamp = self._stamp(os.fstat(stream.fileno()))

    @staticmethod
    def _stamp(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def check_unchanged(self):
        # Reject replacement, truncation or modification without another full read.
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode)
                or self._stamp(info) != self.stamp
                or self._stamp(os.fstat(self.stream.fileno())) != self.stamp):
            raise ValueError('还原源镜像在校验后发生变化：' + self.path.name)


@contextlib.contextmanager
def _verified_image(source, size, expected_sha256, update=None):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('还原源镜像不是普通文件')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb', buffering=0) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise ValueError('还原源镜像大小不匹配，未写入目标')
        image = _VerifiedImage(source, stream, size, expected_sha256)
        if _hash_stream(stream, size, update, 'verifying', source.name) != expected_sha256:
            raise ValueError('还原源镜像校验失败，未写入目标')
        image.check_unchanged()
        yield image


def restore_images(folder, report, update):
    update('verifying', '完整校验所有备份镜像，尚未写盘')
    folder = private_external(folder)
    check = inspect(folder)  # Metadata only; full image hashing has one owner below.
    saved = read_identity(folder)
    policy.backup_matches(report, saved)
    rows = sorted(check['artifacts'], key=lambda r: r['file'] != 'mmcblk0.img')
    with contextlib.ExitStack() as stack:
        images = [stack.enter_context(_verified_image(
            safe_file(folder, row['file']), row['bytes'], row['sha256'], update))
            for row in rows]
        # Hashing can take many minutes. Recheck metadata and device before writing.
        if inspect(folder)['artifacts'] != check['artifacts'] or read_identity(folder) != saved:
            raise ValueError('备份清单或身份在校验期间发生变化')
        same_device(report, probe())
        target_idle(report)
        for image in images:
            image.check_unchanged()
        with android_restore_session(update) as restore_update:
            restore_update('preparing', '备份校验通过，准备卸载 Android 分区')
            detach_android(report)
            # Keep verified file descriptors open; do not reopen/re-hash the sources.
            for row, image in zip(rows, images):
                dev = Path(row['source'])
                with dev.open('rb', buffering=0) as f:
                    size = struct.unpack('Q', fcntl.ioctl(f.fileno(), BLKGETSIZE64, b'\0'*8))[0]
                    if size != row['bytes']:
                        raise ValueError('还原目标容量改变')
                ro = Path('/sys/block')/dev.name/'force_ro'
                old_ro = None
                if ro.exists():
                    if dev.name in ('mmcblk0boot0', 'mmcblk0boot1'):
                        restore_update('checking', '比较硬件启动区 '+dev.name)
                        with dev.open('rb', buffering=0) as f:
                            digest = _hash_stream(f, size, None, 'readback', dev.name)
                        if digest == row['sha256']:
                            restore_update('checking', dev.name + ' 内容一致，跳过写入',
                                progress_step='restoring:'+dev.name,progress_done=size,progress_total=size)
                            restore_update('checking', dev.name + ' 内容一致，读回已通过',
                                progress_step='readback:'+dev.name,progress_done=size,progress_total=size)
                            continue
                    image.check_unchanged()
                    old_ro = ro.read_text()
                    ro.write_text('0')
                try:
                    _copy_verified_image(image, dev, restore_update)
                finally:
                    if old_ro is not None:
                        ro.write_text(old_ro)

def _copy_verified_image(image, target, update=None):
    target = Path(target)
    image.check_unchanged()
    src = image.stream
    src.seek(0)
    written = 0
    digest = hashlib.sha256()
    last = time.monotonic()
    with target.open('r+b', buffering=0) as dst:
        if update:
            # Persist the conservative recovery flag only when a write is imminent.
            update('restoring', '开始写入 ' + target.name, device_writes_started=True)
        while written < image.size:
            data = src.read(min(8*MIB, image.size-written))
            if not data:
                raise ValueError('还原源镜像读取不完整')
            digest.update(data)
            view = memoryview(data)
            while view:
                n = dst.write(view)
                if not n:
                    raise OSError('还原写入不完整')
                view = view[n:]
            written += len(data)
            if time.monotonic()-last >= 10:
                _progress(update, 'restoring', target.name, written, image.size)
                last = time.monotonic()
        os.fsync(dst.fileno())
        image.check_unchanged()
        if digest.hexdigest() != image.digest:
            raise ValueError('源镜像在写入期间发生变化')
        os.posix_fadvise(dst.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    _progress(update, 'restoring', target.name, written, image.size)
    with target.open('rb', buffering=0) as f:
        digest = _hash_stream(f, image.size, update, 'readback', target.name)
    if digest != image.digest:
        raise ValueError('还原读回校验失败：' + target.name)


def copy_image(source, target, size, expected_sha256):
    """Standalone transfer: verify once, then write and independently read back."""
    with _verified_image(source, size, expected_sha256) as image:
        _copy_verified_image(image, target)
