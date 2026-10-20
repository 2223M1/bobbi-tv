"""Read-only evidence collection and narrowly scoped Virtual A/B retry writes.

Called only by the explicit external-CE repair flow under worker locks.
Never mounts userdata, writes snapshots, marks success, or runs on startup.
"""
import contextlib
import fcntl
import json
import os
import re
from pathlib import Path
import stat
import struct
import tempfile
import time
import operations as op
import ota_repair as layout
import ota_resume_core as core
from android_identity import metadata_geometry
from ota_snapshot import Reader, exceptions, digest_snapshot
from layout_trial import atomic_json


def rows(report):
    return {p['name']:p for p in report['mpt']['partitions']}


def sources_idle(report):
    """Allow only CE's bounded read-only super views, keeping write targets idle.

    NO loads Android libraries through these mounts. Neither repair stage
    writes super or logical partition contents. Unknown or writable users of
    super, and every user of other partitions, remain a refusal.
    """
    op.target_idle(report)
    mounts=op.mountinfo()
    for row in report['mpt']['partitions']:
        node=Path('/sys/block/mmcblk0')/row['name']
        dev=op.read(node/'dev');holders=list((node/'holders').glob('*'))
        if any(m['dev']==dev for m in mounts):
            raise ValueError('OTA 来源分区仍被直接挂载：'+row['name'])
        if not holders:continue
        if row['name']!='super':
            raise ValueError('OTA 来源分区仍被映射使用：'+row['name'])
        for holder in holders:
            name=op.read(holder/'dm/name')
            if not re.fullmatch(r'dynpart-(odm|product|system|system_ext|vendor)_[ab]',name):
                raise ValueError('未知的 super 映射：'+name)
            if list((holder/'holders').glob('*')):
                raise ValueError('super 映射仍有下级使用者：'+name)
            layout.require_readonly(Path('/dev')/holder.name)
            mapped_dev=op.read(holder/'dev')
            point='/android/'+name[len('dynpart-'):-2]
            if any(m['mountpoint']!=point or not os.statvfs(point).f_flag & os.ST_RDONLY
                   for m in mounts if m['dev']==mapped_dev):
                raise ValueError('super 映射存在非预期挂载：'+name)
            table=op.run(['dmsetup','table',name]);end=0
            for line in table.splitlines():
                fields=line.split()
                if len(fields)!=5 or fields[2]!='linear' or fields[3]!=dev:
                    raise ValueError('super 映射不是本分区的线性只读视图：'+name)
                start,length,offset=map(int,(fields[0],fields[1],fields[4]))
                if start!=end or length<=0 or offset<0 or (offset+length)*512>row['size']:
                    raise ValueError('super 映射范围异常：'+name)
                end+=length
            if not end:raise ValueError('super 映射为空：'+name)


def read_file(root,rel,limit=2*1024**2,optional=False):
    path=root
    for part in Path(rel).parts:
        path=path/part
        if path.is_symlink():raise ValueError('OTA 元数据路径不能是符号链接')
    if optional and not path.exists():return None
    if not path.is_file() or path.stat().st_size>limit:raise ValueError('OTA 元数据文件缺失或过大：'+rel)
    return path.read_bytes()


@contextlib.contextmanager
def metadata_mount(report):
    row=rows(report)['metadata']
    if not row.get('sysfs_matches') or row['size']!=16*1024**2:raise ValueError('metadata 边界未通过验证')
    # NO must not claim the whole MMC with dm-linear while its partitions
    # are mapped. Use its verified loop backend; NG keeps dm-linear.
    import policy
    policy.layouts(report)
    if row not in report['mpt']['partitions'][:28]:raise ValueError('metadata 不是原厂固定分区')
    with op.backend_for(report).region(op,row['offset'],row['size'],readonly=True) as dev:
        layout.require_readonly(dev)
        with tempfile.TemporaryDirectory(prefix='aurora-ota-ro-') as tmp:
            mounted=False
            try:
                try:layout.run(['mount','-t','ext4','-o','ro,noload',str(dev),tmp]);mounted=True
                except RuntimeError as exc:raise ValueError('metadata 无法只读挂载：'+str(exc)) from exc
                yield Path(tmp)
            finally:
                if mounted:
                    try:layout.run(['umount',tmp])
                    except Exception as exc:raise RuntimeError('OTA 只读映射卸载失败，停止修复') from exc


def records(root):
    state=read_file(root,'ota/state',4096,optional=True)
    if state is None:return {'state':0,'snapshots':[]}
    p=core.protobuf(state,{i:0 for i in range(1,5)})
    value=p.get(1,0)
    if value!=2:
        if value==0:return {'state':0,'snapshots':[]}
        raise ValueError('OTA 不处于尚未验证状态（state=%s），不切换槽位'%value)
    if any(p.get(i,0) for i in (2,3,4)):raise ValueError('OTA 已有合并统计，不重复恢复目标槽')
    source=read_file(root,'ota/snapshot-boot',16).decode('ascii').strip()
    if source not in ('_a','_b'):raise ValueError('无法确认 OTA 来源槽')
    directory=root/'ota/snapshots'
    if directory.is_symlink() or not directory.is_dir():raise ValueError('OTA 快照目录不存在')
    names=sorted(p.name for p in directory.iterdir())
    target='_b' if source=='_a' else '_a'
    if names!=sorted(n+target for n in core.PARTITIONS):raise ValueError('OTA 快照集合不完整或存在其他快照')
    snapshots=[core.snapshot(read_file(root,'ota/snapshots/'+name,4096),name) for name in names]
    image=read_file(root,'gsi/ota/lp_metadata') if any(s['cow_file_size'] for s in snapshots) else None
    return {'state':2,'source':source,'target':target,'snapshots':snapshots,'image':image}


def super_metadata(report):
    row=rows(report)['super'];prefix=layout.read_at(row['offset'],12288)
    maximum,slots,_=metadata_geometry(prefix)
    size=12288+2*maximum*slots
    if size>row['size']:raise ValueError('super 元数据越界')
    return layout.read_at(row['offset'],size)


def mappings(record,superraw,report,target):
    superrow=rows(report)['super'];userdata=target[-1]
    table=core.super_table(superraw,superrow['size'],'ab'.index(record['target'][1]))
    images=core.image_table(record['image'],userdata['size']) if record['image'] is not None else {}
    expected={s['name'] for s in record['snapshots']}
    expected_cow={s['name']+'-cow' for s in record['snapshots'] if s['cow_partition_size']}
    if set(table)!=expected|expected_cow:raise ValueError('目标槽 LP 分区集合与快照记录不一致')
    if set(images)!={s['name']+'-cow-img' for s in record['snapshots'] if s['cow_file_size']}:raise ValueError('userdata COW 映射集合不一致')
    def mapped(table,name,size,region):
        item=table[name]
        if item['size']!=size:raise ValueError('快照映射长度不一致：'+name)
        return [[region['offset']+off,n] for off,n in item['extents']]
    result=[]
    for s in record['snapshots']:
        name=s['name'];origin=mapped(table,name,s['device_size'],superrow);cow=[]
        if s['cow_partition_size']:cow+=mapped(table,name+'-cow',s['cow_partition_size'],superrow)
        if s['cow_file_size']:cow+=mapped(images,name+'-cow-img',s['cow_file_size'],userdata)
        result.append({'name':name,'size':s['device_size'],'origin':origin,'cow':cow})
    return result


def inspect(report,target,raw):
    """No changes. Errors are explicit, and cannot enable a write operation."""
    # Idle devices need no metadata mount; damaged/unknown markers do not qualify.
    state=layout.android_state(raw)
    if state['virtual_ab_status']==0 and not any(raw[:32]):return {'state':'none'}
    try:
        sources_idle(report)
        row=rows(report)['metadata'];before=core.sha(layout.read_at(row['offset'],row['size']))
        with metadata_mount(report) as root:record=records(root)
        if core.sha(layout.read_at(row['offset'],row['size']))!=before:raise ValueError('读取期间 metadata 已变化')
        if record['state']==0:
            if any(raw[:32]):raise ValueError('存在 Recovery 请求但没有可恢复的 OTA，保留请求供人工检查')
            if state['virtual_ab_status']!=0:raise ValueError('misc 与 metadata 的 OTA 状态不一致')
            return {'state':'none'}
        status=core.boot_control(raw,record['source'])
        clear=core.recovery_command(raw)
        if status=='already-selected':
            return {'state':'already-selected','target':record['target'],'reason':'OTA 目标槽已设为优先启动；不会重复补充尝试次数。若仍无法启动，请保留现场日志。'}
        preserve_target=status=='target-confirmed'
        if preserve_target and not report['ota_repair']['layout_needed'] and not clear:
            return {'state':'already-selected','target':record['target'],'reason':'OTA 目标槽已被 Android 标记成功，布局和 Recovery 请求均已正常；未修改 A/B。请启动 Android 完成验证与快照合并。'}
        superraw=super_metadata(report);maps=mappings(record,superraw,report,target)
        with open(op.DISK,'rb',buffering=0) as f:
            read=lambda off,n:os.pread(f.fileno(),n,off)
            for m in maps:
                chunk,exc=exceptions(Reader(read,m['cow']),m['size'])
                if len(exc)*chunk!=m['size']:raise ValueError('存在依赖旧分区的快照块；当前只支持完整快照，拒绝猜测旧数据')
            for name,magic in [('boot',b'ANDROID!'),('vendor_boot',b'VNDRBOOT'),('vbmeta',b'AVB0'),('vbmeta_system',b'AVB0')]:
                r=rows(report)[name+record['target']]
                if read(r['offset'],len(magic))!=magic:raise ValueError('目标启动镜像头无效：'+name)
        if super_metadata(report)!=superraw or core.sha(layout.read_at(row['offset'],row['size']))!=before:raise ValueError('检查期间 OTA 元数据发生变化')
        return {'state':'ready','source':record['source'],'target':record['target'],'clear_recovery':clear,
                'metadata_sha256':before,'super_lp_sha256':core.sha(superraw),'super_lp_bytes':len(superraw),
                'maps':maps,'snapshot_bytes':sum(m['size'] for m in maps),
                'preserve_target':preserve_target,
                'mode':'layout-first' if report['ota_repair']['layout_needed'] else ('recovery-only' if preserve_target else 'target-retry')}
    except (ValueError,OSError,UnicodeError) as exc:
        return {'state':'unsupported','reason':str(exc)}


def guards(report,evidence):
    r=rows(report)
    for name,size,key in [('metadata',r['metadata']['size'],'metadata_sha256'),('super',evidence['super_lp_bytes'],'super_lp_sha256')]:
        if core.sha(layout.read_at(r[name]['offset'],size))!=evidence[key]:raise ValueError('OTA 现场已变化：'+name)


def prepare(folder,report,evidence,before_misc,update):
    """Verify all virtual bytes before ANY layout/env/misc write."""
    op.external(report);sources_idle(report);op.raw_checkpoint(report)
    guards(report,evidence)
    activate=evidence['mode']=='target-retry'
    candidate=core.misc_candidate(before_misc,evidence['source'],activate)
    root=folder/'ota-resume';root.mkdir(mode=0o700)
    r=rows(report)
    layout.store(root/'before-misc.bin',before_misc)
    layout.store(root/'before-metadata.bin',layout.read_at(r['metadata']['offset'],r['metadata']['size']))
    layout.store(root/'before-super-lp.bin',layout.read_at(r['super']['offset'],evidence['super_lp_bytes']))
    layout.store(root/'candidate-misc.bin',candidate)
    atomic_json(root/'plan.json',{'evidence':evidence,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'cid':report['cid'],'activate_target':activate,'before_sha256':core.sha(before_misc),'after_sha256':core.sha(candidate),
        'note':'Android merge changes super/metadata. These are not a whole-device backup or a post-merge rollback plan.'})
    update('repair-check','完整读取 OTA 快照，核对结构和可读性（不依赖 update.zip）',
           progress_plan={'ota:'+m['name']:m['size'] for m in evidence['maps']})
    results=[]
    with open(op.DISK,'rb',buffering=0) as f:
        read=lambda off,n:os.pread(f.fileno(),n,off)
        for m in evidence['maps']:
            last=[0]
            def progress(done,total):
                now=time.monotonic()
                if done==total or now-last[0]>=0.25:
                    last[0]=now;update('repair-check','读取 OTA 目标快照：'+m['name'],progress_step='ota:'+m['name'],progress_done=done,progress_total=total)
            result=digest_snapshot(Reader(read,m['origin']),Reader(read,m['cow']),m['size'],progress)
            if result['origin_chunks']:raise ValueError('快照不再是完整快照')
            results.append(dict(result,name=m['name']))
    guards(report,evidence)
    if layout.read_at(r['misc']['offset'],r['misc']['size'])!=before_misc:raise ValueError('检查期间 misc 已变化')
    atomic_json(root/'verified.json',results);os.sync()
    return candidate


def commit(report,evidence,before,after,expected_metadata,expected_env,update):
    """Write at most the BCB command sector and one A/B control sector."""
    if core.misc_candidate(before,evidence['source'],evidence['mode']=='target-retry')!=after:raise ValueError('misc 候选不一致')
    op.external(report);sources_idle(report);op.raw_checkpoint(report)
    guards(report,evidence)
    for k,off,n in [('dtb',40*1024**2,524288),('mpt',36*1024**2,4096)]:
        if layout.read_at(off,n)!=expected_metadata[k]:raise ValueError('写入 misc 前布局已变化')
    if layout.env_read(report)!=expected_env:raise ValueError('写入 misc 前启动环境已变化')
    r=rows(report)['misc']
    if r['size']!=len(before) or len(before)!=2*1024**2:raise ValueError('misc 边界不一致')
    fd=os.open(op.DISK,os.O_RDWR|os.O_CLOEXEC)
    try:
        if not stat.S_ISBLK(os.fstat(fd).st_mode):raise ValueError('目标不是块设备')
        if struct.unpack('Q',fcntl.ioctl(fd,op.BLKGETSIZE64,b'\0'*8))[0]!=report['emmc_bytes'] or Path('/sys/block/mmcblk0/device/cid').read_text().strip()!=report['cid']:raise ValueError('eMMC 身份变化')
        if os.pread(fd,len(before),r['offset'])!=before:raise ValueError('misc 已变化，拒绝写入')
        for offset in (0,2048):
            if before[offset:offset+512]==after[offset:offset+512]:continue
            update('repair-writing','恢复 OTA 启动状态并读回核对',device_writes_started=True)
            if os.pwrite(fd,after[offset:offset+512],r['offset']+offset)!=512:raise OSError('misc 写入不完整')
            os.fsync(fd)
        if os.pread(fd,len(after),r['offset'])!=after:raise ValueError('misc 完整读回不一致，请勿重启或重复修复')
    finally:os.close(fd)
    guards(report,evidence)
    if layout.env_read(report)!=expected_env:raise ValueError('misc 写入后启动环境改变')
    os.sync()
