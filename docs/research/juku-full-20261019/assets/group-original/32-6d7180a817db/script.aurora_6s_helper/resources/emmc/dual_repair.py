"""Repair supported boot scanning and/or the CE-first NG/NO dual layout.

The worker holds exclusive locks. Never formats or writes firmware.
A verified pending full OTA can request a bounded target-slot retry.
Unknown environment scripts remain a refusal, not a template to overwrite.
"""
import json
import os
from pathlib import Path
import operations as op
import policy
import ota_repair as layout
import ota_resume
import ce_journal
from layout_trial import atomic_json
from ota_repair_core import (check_environment, discover_layout, android_state,
                             sha)
from prepare_boot_environment import scan_through


def environment_changes(env, target):
    check_environment(env, allow_short=True)
    boot = next(p for p in target if p['name'] == 'ce_system')
    count, source = policy.scanner(env['cfgloademmc'])
    if count >= boot['index']:
        return {}
    new = scan_through(boot['index'])
    if source:
        new = new.replace('autoscr ${loadaddr}', 'source ${loadaddr}; autoscr ${loadaddr}')
    return {'cfgloademmc': new}


def assess(report):
    policy.identity(report)
    if report['blockers']:
        raise ValueError('; '.join(report['blockers']))
    kind, _, _ = policy.layouts(report)
    layout_needed = kind == 'stock'
    if layout_needed:
        target, inference = discover_layout(report, layout.read_at)
    else:
        target = report['mpt']['partitions']
        inference = {'method': 'existing-validated-dual-layout'}
    layout.check_env_device(report,raw=True)
    env = layout.env_read(report)
    changes = environment_changes(env, target)
    misc = next(p for p in report['mpt']['partitions'] if p['name'] == 'misc')
    raw_misc = layout.read_at(misc['offset'], 65536)
    state = android_state(raw_misc)
    report['ota_repair'] = {
        'repair_mode': 'boot-layout', 'layout_needed': layout_needed,
        'environment_changes': changes,
        'environment_sha256': sha(json.dumps(env, sort_keys=True).encode()),
        'partitions': target, 'inference': inference, 'android_state': state,
        'misc_header_sha256': state['misc_sha256'],
    }
    report['ota_repair']['ota_resume'] = ota_resume.inspect(report, target, raw_misc)
    resume = report['ota_repair']['ota_resume']
    if resume['state'] == 'ready':
        state['policy'] = 'guarded-full-snapshot-ota-retry: '+resume['mode']
        state['warnings'] = ['现场完整快照符合受限 OTA 恢复条件；需按界面分阶段确认，Android 启动及合并仍由原系统完成。']
    if layout.read_at(misc['offset'], 65536) != raw_misc:
        raise ValueError('读取 OTA 证据期间 misc 已改变')
    return report


def write_environment(before, changes, report=None):
    if set(changes) != {'cfgloademmc'}:
        raise ValueError('修复只允许修改 cfgloademmc')
    if layout.env_read(report) != before:
        raise ValueError('写入前启动环境已改变')
    with layout.environment_config(report,readonly=False) as config:
        layout.run(['fw_setenv', '-c', str(config), 'cfgloademmc', changes['cfgloademmc']])
    if layout.env_read(report) != dict(before, **changes):
        raise ValueError('启动环境读回不一致，请保留外置盘并检查日志')


def execute(folder, report, update):
    # Reassess scope, then verify all payloads before allowing either write path.
    original = report['ota_repair']
    live = op.assess('repair')
    op.same_device(report, live)
    if live['ota_repair'] != original:
        raise ValueError('修复范围或启动环境已改变，请重新检查并确认')
    changes = original['environment_changes']
    layout_needed = original['layout_needed']
    resume = original.get('ota_resume', {'state': 'none'})
    retry = resume['state'] == 'ready'
    if not layout_needed and not changes and not retry:
        return {'changed': False, 'message': '双系统分区布局和启动扫描范围正常，未写入 eMMC。'+resume.get('reason','此检查不代表已验证实际开机。')}
    target = original['partitions']
    before = layout.env_read(live)
    current = {k: layout.read_at(off, n) for k, off, n in
               [('dtb', 40*1024**2, 524288), ('mpt', 36*1024**2, 4096)]}
    if sha(current['dtb']) != live['android_dtb_sha256'] or sha(current['mpt']) != live['mpt_sha256']:
        raise ValueError('检查后分区元数据已改变')
    if sha(json.dumps(before, sort_keys=True).encode()) != original['environment_sha256']:
        raise ValueError('检查后启动环境已改变')
    policy.validate_dtb_layout(current['dtb'], live['mpt']['partitions'])
    preserved = {p['name']: layout.read_at(p['offset'], p['size'])
                 for p in layout.preserved_rows(live)}
    if sha(preserved['misc'][:65536]) != original['misc_header_sha256']:
        raise ValueError('检查后 Android 启动状态已改变')
    backup = folder/'boot-layout-repair'
    backup.mkdir(mode=0o700)
    for name, data in dict(current, **preserved).items():
        layout.store(backup/('before-'+name+'.bin'), data)
    atomic_json(backup/'environment-before.json', before)
    atomic_json(backup/'plan.json', original)
    os.sync()
    candidate = ota_resume.prepare(folder, live, resume, preserved['misc'], update) if retry else None
    journal_replayed = ce_journal.replay_if_needed(folder, live, target, update)
    if layout_needed:
        # This path retains its own prepare/recheck/metadata and preservation guards.
        # It deliberately leaves env and misc unchanged; scanner repair follows it.
        layout.execute(folder, live, update, boot_layout=True)
    else:
        layout.filesystem_check(live, target, update, 'repair-prepare')
    op.external(live)
    op.target_idle(live)
    layout.check_env_device(live,raw=True)
    if layout.env_read(live) != before:
        raise ValueError('检查过程中启动环境已改变')
    for row in layout.preserved_rows(live):
        if layout.read_at(row['offset'], row['size']) != preserved[row['name']]:
            raise ValueError('检查过程中 env/misc 已改变')
    after_metadata = {k: layout.read_at(off, n) for k, off, n in
                      [('dtb', 40*1024**2, 524288), ('mpt', 36*1024**2, 4096)]}
    expected_metadata = ({k: (folder/'layout-repair'/('repair-'+k+'.bin')).read_bytes()
                          for k in ('dtb', 'mpt')} if layout_needed else current)
    if after_metadata != expected_metadata:
        raise ValueError('写入启动环境前分区元数据已改变')
    if changes:
        # Derive again from the verified target, never trust a stored arbitrary command.
        if changes != environment_changes(before, target):
            raise ValueError('启动修复候选不一致')
        update('repair-writing', '修复内置 CE 启动扫描范围并读回核对', device_writes_started=True)
        write_environment(before, changes, live)
        for k, off, n in [('dtb', 40*1024**2, 524288), ('mpt', 36*1024**2, 4096)]:
            if layout.read_at(off, n) != expected_metadata[k]:
                raise ValueError('启动修复后分区元数据发生变化')
        misc = next(p for p in layout.preserved_rows(live) if p['name'] == 'misc')
        if layout.read_at(misc['offset'], misc['size']) != preserved['misc']:
            raise ValueError('启动修复后 misc 发生变化')
    if retry:
        ota_resume.commit(live, resume, preserved['misc'], candidate, expected_metadata, dict(before, **changes), update)
        atomic_json(folder/'ota-resume/result.json', {'complete': True, 'mode': resume['mode'], 'target': resume['target'], 'misc_sha256': sha(candidate)})
    os.sync()
    atomic_json(backup/'result.json', {'complete': True, 'layout_changed': layout_needed,
                                    'environment_changes': changes, 'ce_journal_replayed': journal_replayed})
    if layout_needed:
        message = '双系统布局'+('和启动入口' if changes else '')+'修复完成。请正常关机，关机后拔掉 U 盘/SD 卡，再开机验证内置 CE；不要按 AV 复位键，也不要在本次启动中继续安装、移除或修复。'
    else:
        message = '内置 CE 启动扫描范围已修复并读回核对；分区和 A/B 槽位未修改。请关机后拔下外置启动盘，再正常开机测试（不按复位键）。'
    if retry:
        if layout_needed:
            message = '第一阶段完成：布局和启动入口已恢复，已处理符合条件的 Recovery 命令；A/B 槽位未修改。请保持 U 盘连接，正常重启到外置 CE，再运行“修复双系统启动/布局”完成目标槽恢复。此时不要进入旧 Android，也不要按复位键。'
            if resume.get('preserve_target'):
                message = '布局及已确认的 Recovery 请求已修复，Android 已标记成功的目标槽 '+resume['target']+' 和全部 A/B 信息均保留。本次无需第二阶段修复。请正常关机，关机后拔掉 U 盘/SD 卡，再开机验证内置 CE，不要按 AV 复位键。进入内置 CE 后，选择“从内部存储启动”进入 Android，等待其完成验证和快照合并；不要再次检查更新或恢复出厂。'
        elif resume['mode']=='recovery-only':
            message = '已清除核验过的 Recovery 命令；保留 Android 已标记成功的目标槽 '+resume['target']+'，A/B 信息和快照均未修改。请正常关机，关机后拔掉 U 盘/SD 卡，再开机验证内置 CE，不要按 AV 复位键。随后从内置 CE 菜单选择“从内部存储启动”进入 Android，等待其验证及合并。插件不会自动重启。'
        else:
            message = 'OTA 目标槽 '+resume['target']+' 已设为优先启动，最多 6 次尝试；来源槽和快照未改动，未伪造启动成功。请从 CE 菜单选择“从内部存储启动”进入 Android，等待启动及快照合并完成；不要重复修复、检查更新或恢复出厂。插件不会自动重启。'
    elif resume.get('reason'):
        message += '\nOTA 目标槽未修改：'+resume['reason']
    return {'changed': True, 'message': message}
