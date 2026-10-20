#!/usr/bin/env python3
"""CE-only job runner. No operation executes without an explicit UI/CLI action."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
import signal
import ctypes
import traceback
from progress import ByteProgress

import operations as op
import policy
from backup_identity import read_identity
from aurora_emmc import read
from layout_trial import atomic_json, private_external
from check_backup import inspect, safe_file
import prepare_boot
import stage_system

TERMINAL = ('complete','failed','needs-recovery','cancelled')

class Cancelled(Exception):
    pass


def process_start(pid):
    try:return (Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()[19]
    except (OSError,IndexError):return None


def status():
    pointer=op.BASE/'current.json'
    if not pointer.exists():return {'phase':'none','message':'暂无 eMMC 任务'}
    job=private_external(json.loads(pointer.read_text())['job'])
    value=json.loads((job/'status.json').read_text());value['job']=str(job)
    stale_process = (value.get('foreground_pid') is not None and
                     process_start(value['foreground_pid']) != value.get('foreground_start'))
    if value['phase'] not in TERMINAL and (value['boot_id']!=read('/proc/sys/kernel/random/boot_id') or stale_process):
        value.update(phase='needs-recovery' if value.get('device_writes_started') else 'failed',
                     message='上次前台操作或系统被中断，未自动继续写盘；请查看日志')
    return value


def list_backups():
    result=[]
    if not op.BACKUPS.is_dir():return result
    for folder in sorted(op.BACKUPS.iterdir(),reverse=True):
        if folder.is_symlink() or not folder.is_dir():continue
        try:
            inspect(folder)
            report=read_identity(folder)
            result.append(dict(path=str(folder),model='/'.join(report.get('android_models',[])),
                cid_present=bool(report.get('cid')),bytes=report['emmc_bytes']))
        except (OSError,ValueError,KeyError,TypeError):continue
    return result


def submit(action, backup=None, reset=False, risk=False, android_gib=None, repair_digest=None):
    policy.confirmation(action,reset,risk)
    report=op.assess(action,backup,android_gib)
    if action=='repair':
        evidence=report['ota_repair']
        digest=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode('utf-8')).hexdigest()
        if (repair_digest is not None and repair_digest!=digest) or (evidence.get('ota_resume',{}).get('state')=='ready' and repair_digest is None):
            raise ValueError('修复方案与确认界面不一致，请重新检查并确认；未写入 eMMC')
    if op.BASE.is_symlink():raise ValueError('任务目录不能是符号链接')
    op.BASE.mkdir(mode=0o700,exist_ok=True);private_external(op.BASE)
    with open('/run/aurora-emmc-submit.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous=status()
        if previous.get('job'):
            unit='aurora-emmc-'+Path(previous['job']).name
            import subprocess
            if subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0:
                raise ValueError('上一个后台任务仍在运行或清理，请稍后查看状态')
        if previous['phase'] not in ('none',*TERMINAL):raise ValueError('已有任务正在执行，请查看进度')
        if previous['phase']=='needs-recovery' and action!='restore':raise ValueError('上次写入中断，只允许先用完整备份还原')
        job=op.BASE/uuid.uuid4().hex;job.mkdir(mode=0o700)
        # Pin this run to a private copy, so an add-on upgrade cannot replace active code.
        runtime=job/'runtime'
        shutil.copytree(Path(__file__).parent,runtime,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for path in runtime.rglob('*'):
            if path.is_file():path.chmod(0o700 if path.name=='ampart' else 0o600)
        request=dict(action=action,source_backup=str(private_external(backup)) if backup else None,
                     android_gib=report.get('android_gib') if action=='install' else None,
                     reset_accepted=reset,risk_accepted=risk,report=report,boot_id=read('/proc/sys/kernel/random/boot_id'))
        atomic_json(job/'request.json',request)
        atomic_json(job/'status.json',dict(phase='queued',message='等待前台操作开始',action=action,
            boot_id=request['boot_id'],device_writes_started=False,
            foreground_pid=os.getppid(),foreground_start=process_start(os.getppid())))
        atomic_json(op.BASE/'current.json',dict(job=str(job)))
        return dict(job=str(job),runtime=str(runtime/'worker.py'))


def execute(folder):
    folder=private_external(folder)
    request=json.loads(safe_file(folder,'request.json').read_text())
    state=json.loads(safe_file(folder,'status.json').read_text())
    if state['phase']!='queued':raise ValueError('任务已执行过，禁止自动重复格式化或还原')
    progress=ByteProgress()
    def update(phase,message,**extra):
        if phase not in TERMINAL and not state.get('device_writes_started') and (folder/'cancel').exists():
            raise Cancelled('用户取消；尚未写入 eMMC')
        if 'progress_plan' in extra:progress.plan(extra.pop('progress_plan'))
        if 'progress_step' in extra:
            progress.advance(extra.pop('progress_step'),extra.pop('progress_done'),extra.pop('progress_total'))
        extra.update(progress.fields(phase=='complete'))
        state.update(phase=phase,message=message,updated=time.time(),**extra)
        atomic_json(folder/'status.json',state)
    snapshot=None
    lock=backup_lock=None
    try:
        lock=open('/run/aurora-emmc-layout.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        backup_lock=open('/run/aurora-emmc-backup.lock','a');fcntl.flock(backup_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        action=request['action'];policy.confirmation(action,request['reset_accepted'],request['risk_accepted'])
        if request['boot_id']!=read('/proc/sys/kernel/random/boot_id'):raise ValueError('开始任务前系统已重启，请重新检查')
        update('preparing','核对操作条件',foreground_pid=os.getpid(),foreground_start=process_start(os.getpid()))
        live=op.assess(action,request['source_backup'],request.get('android_gib'));op.same_device(request['report'],live)
        if action=='repair':
            import dual_repair
            if live['ota_repair']!=request['report']['ota_repair']:
                raise ValueError('修复范围或启动环境已改变，请重新检查并确认')
            result=dual_repair.execute(folder,live,update)
            update('complete',result['message'],reboot_required=result['changed'])
            return
        if action in ('backup','restore'):
            sizes={'mmcblk0':live['emmc_bytes'],**live['boot_areas']}
            plan={((phase+':'+name+'.img') if phase=='verifying' else phase+':'+name):size
                  for name,size in sizes.items() for phase in (('copy','verify') if action=='backup' else ('verifying','restoring','readback'))}
            update('preparing','准备前台操作',progress_plan=plan)
        if action=='backup':
            backup=op.full_backup(live,update)
            atomic_json(folder/'backup.json',dict(path=str(backup)))
            update('complete','完整备份及独立读回校验完成；不包含 RPMB/eFuse',backup=str(backup));return
        _,stock,dual=policy.layouts(live)
        if action=='restore':
            op.restore_images(request['source_backup'],live,update)
            os.sync();update('complete','完整镜像还原并读回校验完成。请重启；备份之后的数据已被覆盖。',reboot_required=True);return
        env=op.environment();policy.environment_change(env,action)
        atomic_json(folder/'environment-before.json',env)
        target=policy.install_layout(live,request.get('android_gib',16)) if action=='install' else stock
        update('preparing','生成并核对本机 MPT / DTB 候选')
        old,new=op.make_metadata(live,target,folder/'metadata')
        update('preparing','分区候选已核对',progress_plan={'userdata-header':8192,**{'metadata:'+k:2*len(v) for k,v in new.items()}})
        if action=='install':
            update('snapshot','暂存当前 CE，保持 Kodi 前台运行')
            boot=prepare_boot.stage()
            snapshot=Path('/storage/aurora-emmc-staging')/('snapshot-'+folder.name)
            usage=op.storage_bytes();bootbytes=sum(r['bytes'] for r in boot['manifest']['boot_files'])
            update('snapshot','复制当前 CE 文件',progress_plan={**{k:usage for k in ('snapshot-copy','snapshot-verify','install-datacopy','install-dataverify')},**{k:bootbytes for k in ('install-bootcopy','install-bootverify')}})
            stage_system.snapshot(snapshot,boot['directory'],live=True,update=update)
            manifest=stage_system.validate_snapshot(snapshot)
            update('snapshot','CE 暂存已核对',progress_plan={k:manifest['regular_file_bytes'] for k in ('install-datacopy','install-dataverify')})
            if manifest['regular_file_bytes']>policy.ce_data_limit(target[29]['size']):raise ValueError('快照超过内置 CE 数据区容量')
            prepare_boot.check_boot_capacity({r['file']:r['bytes'] for r in manifest['boot_files']},boot['manifest'].get('boot_directories',[]),target[28]['size'])
            atomic_json(folder/'snapshot.json',dict(path=str(snapshot),boot=boot['directory']))
        # Recheck all evidence immediately before first disk write.
        op.same_device(live,op.probe());op.target_idle(live)
        if op.environment()!=env:raise ValueError('引导环境已改变')
        with open(op.DISK,'rb',buffering=0) as f:
            if op.read_regions(f.fileno())!=old:raise ValueError('原分区元数据已改变')
        update('writing','开始写入，Android 用户数据将被重置',device_writes_started=True)
        if action=='install':
            rows={r['name']:r for r in target}
            with op.region_loop(rows['ce_system'],live) as bootdev, op.region_loop(rows['ce_storage'],live) as datadev:
                stage_system.format_devices(bootdev,datadev)
                update('copying','复制 CE 并读回核对')
                verified=stage_system.copy_and_verify(snapshot,bootdev,datadev,update=update)
                atomic_json(folder/'copy-result.json',verified)
        op.zero_userdata(target[-1],live)
        update('writing','用户区头已写入并校验',progress_step='userdata-header',progress_done=8192,progress_total=8192)
        op.commit_metadata(live,old,new,folder,update)
        update('activating','保存引导配置')
        op.change_environment(env,action,live)
        os.sync()
        msg=('安装完成。请关机后移除外置启动盘再开机，进入内置 CE；Android 下次启动将重新初始化。'
             if action=='install' else '已移除 eMMC CE，Android 用户区已恢复容量。请关机后移除外置启动盘再开机，Android 将重新初始化。')
        update('complete',msg,reboot_required=True)
    except Cancelled as exc:
        update('cancelled',str(exc))
    except Exception as exc:
        update('needs-recovery' if state.get('device_writes_started') else 'failed',str(exc))
        raise
    finally:
        try:
            if snapshot and (snapshot/'services.json').exists():
                # Also needed when the snapshot routine fails before completing cleanup.
                stage_system.restore_services(snapshot)
        finally:
            for handle in (backup_lock,lock):
                if handle is not None:handle.close()


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('probe');a.add_argument('--action',choices=('install','remove','backup','restore','repair'));a.add_argument('--backup');a.add_argument('--android-gib',type=int)
    a=sub.add_parser('submit');a.add_argument('action',choices=('install','remove','backup','restore','repair'));a.add_argument('--backup');a.add_argument('--android-gib',type=int);a.add_argument('--reset-android',action='store_true');a.add_argument('--accept-risk',action='store_true');a.add_argument('--repair-digest')
    a=sub.add_parser('run');a.add_argument('folder');a.add_argument('--parent-pid',type=int)
    sub.add_parser('status');sub.add_parser('backups');sub.add_parser('health')
    args=parser.parse_args()
    if args.command=='probe':result=op.assess(args.action,args.backup,args.android_gib)
    elif args.command=='submit':result=submit(args.action,args.backup,args.reset_android,args.accept_risk,args.android_gib,args.repair_digest)
    elif args.command=='run':
        if args.parent_pid:
            # This child belongs to the foreground Kodi process, not a daemon.
            if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGTERM,0,0,0)!=0:raise OSError('无法绑定前台进程生命周期')
            if os.getppid()!=args.parent_pid:raise RuntimeError('Kodi 前台进程已退出')
            def interrupted(signum,frame):raise RuntimeError('Kodi 前台进程中断')
            signal.signal(signal.SIGTERM,interrupted)
        execute(args.folder);return
    elif args.command=='health':
        from health import probe as health_probe
        result=health_probe()
    elif args.command=='status':result=status()
    else:result=list_backups()
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        traceback.print_exc();sys.exit(1)
