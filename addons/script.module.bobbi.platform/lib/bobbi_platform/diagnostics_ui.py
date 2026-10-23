"""On-demand, local-only reports using the active skin's native dialogs."""
import json
import time
from uuid import uuid4

PROVIDERS = {'setup': '查询准备', 'coordinator': '查询调度', 'preferred': '上次选择',
    'local-entry': '本地候选', '115-local-index': '115 本地索引', '漫迪 mdsub': '漫迪',
    'qqdocs': '115 资源目录', 'juku': '115 资源目录', 'jackett': 'BT 检索',
    'animegarden': '动漫检索', 'other': '其他来源'}
STATES = {'PENDING': '等待中', 'RUNNING': '查询中', 'COMPLETE': '已完成',
    'PARTIAL': '部分结果', 'FAILED': '失败', 'TIMEOUT': '超时', 'CANCELLED': '已结束等待'}
STAGES = {'rss_parsed': '索引解析', 'catalog_input': '身份过滤前',
    'catalog_kept': '身份过滤后', 'provider_return': '来源返回', 'processed': '处理后',
    'session_pool': '候选池', 'ranked': '排序 / 合并后', 'visible': '提供给界面的候选'}


def report_text(report):
    lines = ['本地搜索诊断 · 不含片名、账号、Cookie 或播放地址。',
             '阶段数量是最近一次观测，不是各来源合计；界面手动筛选不在此记录中。',
             '提前选源、返回或超时均可能结束等待；这不是播放成功证明。', '']
    stages, providers = {}, []
    for event in report['events']:
        if event['stage'] == 'providers':
            providers = event['providers']
        else:
            stages[event['stage']] = event
    for key, event in stages.items():
        origin = {'cache': '（本地缓存）', 'network': '（本次查询）'}.get(event['state'], '')
        lines.append('{}：{} 条{}'.format(STAGES.get(key, '阶段'), event['count'], origin))
    if not report['events']:
        lines.append('尚无可读取的事件，请开启记录后重新进入一次选源。')
    for row in providers:
        lines.append('\n{} · {} · 最近批次 {} 条'.format(
            PROVIDERS.get(row['provider'], '其他来源'), STATES.get(row['state'], '未知'), row['count']))
        counts = row['completion']
        if counts:
            lines.append('查询 {}/{}；失败 {}；超时 {}；未执行 {}'.format(
                counts.get('succeeded', 0), counts.get('planned', 0), counts.get('failed', 0),
                counts.get('timed_out', 0), counts.get('skipped', 0)))
        if counts.get('stale'):
            lines.append('正在使用旧快照；距快照约 {} 分钟，不等于当前资源已验证可读。'.format(
                counts.get('snapshot_age', 0)//60))
        if counts.get('truncated'):
            lines.append('达到查询 / 分页上限，尚未搜遍该来源。')
        if row['state'] in ('FAILED', 'TIMEOUT') or counts.get('failed') or counts.get('timed_out'):
            lines.append('可返回选源重试；查询失败不等于没有资源。')
    if report['incomplete']:
        lines.append('\n记录已达上限或部分记录不可读；不能将最后观测当作最终结果。')
    return '\n'.join(lines)


def _select_report(dialog, directory):
    from bobbi_core.search_trace import reports, read_report
    paths = reports(directory)
    if not paths:
        dialog.ok('尚无搜索记录', '先开启记录，再重新进入一次影片选源。不会自动搜索或播放。')
        return None
    labels = [time.strftime('%m-%d %H:%M:%S', time.localtime(path.stat().st_mtime))
              + ' · 搜索记录 {}'.format(index+1) for index, path in enumerate(paths)]
    selected = dialog.select('选择本地搜索记录', labels)
    if selected < 0 or selected >= len(paths):
        return None
    return read_report(paths[selected])


def _export(dialog, report):
    import xbmcvfs
    dialog.textviewer('导出前预览', report_text(report))
    if not dialog.yesno('导出这份诊断？', '仅保存上面预览的事件数量和来源状态，不导出 Kodi 日志、片名、账号或配置。\n'
                       '不会自动上传。下一步选择 USB / 本地目录，也可主动选择自己的网络目录。'):
        return
    folder = dialog.browse(0, '选择诊断保存目录', 'files')
    if not folder:
        return
    name = 'BobbiTV-search-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.json'
    target = folder.rstrip('/\\') + '/' + name
    if xbmcvfs.exists(target):
        raise OSError('Export destination exists')
    raw = (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    stream = xbmcvfs.File(target, 'w')
    try:
        written = stream.write(raw)
        if written is not True and not (type(written) is int and written == len(raw)):
            raise OSError('Incomplete diagnostic export')
    finally:
        stream.close()
    dialog.ok('诊断已保存', name + '\n未自动上传；可自行发给维护者。')


def show(dialog):
    import xbmc
    import xbmcvfs
    from bobbi_core import search_trace
    from .paths import profile
    directory = profile('script.module.bobbi.core')
    while not xbmc.Monitor().abortRequested():
        try:
            active = search_trace.enabled(directory)
            count = len(search_trace.reports(directory))
            state = ('记录已满' if count >= search_trace.MAX_REPORTS else
                     '已开启，15 分钟内自动结束' if active else '未开启')
            choice = dialog.select('检查与诊断 · 不影响播放', [
                '检查本机状态（不联网）',
                '关闭搜索记录' if active else '开启搜索记录（15 分钟）',
                '查看搜索记录 · {} 份 · {}'.format(count, state),
                '预览并导出一份诊断（不自动上传）',
                '清除本地诊断记录（不清缓存或账号）',
            ])
            if choice < 0:
                return
            if choice == 0:
                from .capabilities import probe
                from .kodi import rpc
                from .onboarding import summary, steps
                from .bt_setup import helper_state
                from .environment import private_path
                capability = probe(rpc, 'kodi')
                state = helper_state(xbmcvfs.translatePath, private_path(xbmcvfs.translatePath, 'helper-pairing.json'))
                bt = dict(steps(capability, helper_state=state))['helper']
                dialog.textviewer('本机只读检查', summary(capability) + '\n\n' + bt
                    + '\n\n没有联网验证来源，也未改动音画设置、账号或播放。')
            elif choice == 1:
                if not active and count >= search_trace.MAX_REPORTS:
                    dialog.ok('本地记录已满', '最多保留 8 次搜索，每次最多 256 KiB。可先导出，再清除诊断记录后开启。')
                    continue
                search_trace.set_enabled(directory, not active)
                dialog.ok('搜索记录已关闭' if active else '搜索记录已开启',
                    '已有记录仍保留，正在进行的搜索也会停止记录。' if active else
                    '请重新进入影片选源；无需输入种子哈希。15 分钟后自动停止，最多记录 8 次。\n'
                    '不会开启 Kodi 全局调试、自动播放或上传。')
            elif choice in (2, 3):
                report = _select_report(dialog, directory)
                if report is not None:
                    if choice == 2:
                        dialog.textviewer('本地搜索诊断', report_text(report))
                    else:
                        _export(dialog, report)
            elif choice == 4 and dialog.yesno('清除本地诊断记录？',
                    '将关闭记录并删除最近最多 8 份搜索诊断。此操作不可撤销；需要的请先导出。\n'
                    '不会删除影片、搜索缓存、账号、设置或观看进度。'):
                search_trace.clear(directory)
        except (ValueError, OSError, RuntimeError):
            dialog.ok('诊断暂不可用', '本次诊断未完成。可以返回后重试；播放、账号和已有缓存没有被更改。')
