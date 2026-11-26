"""Local search reports and a separate, user-controlled optimization outbox."""
import json
import shutil
import sqlite3
import time
from uuid import uuid4
from .i18n import is_english, tr

PROVIDERS = {'setup': '查询准备', 'coordinator': '查询调度', 'preferred': '上次选择',
    'local-entry': '本地候选', '115-local-index': '115 本地索引', '漫迪 mdsub': '漫迪',
    'qqdocs': '115 资源目录', 'sharelib': '115 资源目录', 'jackett': 'BT 检索',
    'animegarden': '动漫检索', 'other': '其他来源'}
PROVIDERS_EN = {'setup': 'Search Setup', 'coordinator': 'Search Coordinator', 'preferred': 'Preferred Source',
    'local-entry': 'Local Candidate', '115-local-index': '115 Local Index', '漫迪 mdsub': 'MDsub',
    'qqdocs': '115 Share Catalog', 'sharelib': '115 Share Catalog', 'jackett': 'Jackett BT',
    'animegarden': 'AnimeGarden', 'other': 'Other Source'}
STATES = {'PENDING': '等待中', 'RUNNING': '查询中', 'COMPLETE': '已完成',
    'PARTIAL': '部分结果', 'FAILED': '失败', 'TIMEOUT': '超时', 'CANCELLED': '已结束等待'}
STATES_EN = {'PENDING': 'Pending', 'RUNNING': 'Running', 'COMPLETE': 'Completed',
    'PARTIAL': 'Partial', 'FAILED': 'Failed', 'TIMEOUT': 'Timed Out', 'CANCELLED': 'Cancelled'}
STAGES = {'rss_parsed': '索引解析', 'catalog_input': '身份过滤前',
    'catalog_kept': '身份过滤后', 'provider_return': '来源返回', 'processed': '处理后',
    'session_pool': '候选池', 'ranked': '排序 / 合并后', 'visible': '提供给界面的候选'}
STAGES_EN = {'rss_parsed': 'Feed Parsed', 'catalog_input': 'Pre-Identity Filter',
    'catalog_kept': 'Post-Identity Filter', 'provider_return': 'Provider Return', 'processed': 'Processed',
    'session_pool': 'Session Pool', 'ranked': 'Ranked / Merged', 'visible': 'Visible Candidates'}
ERRORS = {'PREVIOUS_SEARCH_IO_BUSY': '上次查询仍在收尾，请稍后补查。',
          'SEARCH_DEADLINE': '已达到本轮查询时间上限；已有片源仍可选择。',
          'CANDIDATE_CAPACITY_EXCEEDED': '片源数量已达上限，部分结果未列出。',
          'RETRY_PROVIDER_UNAVAILABLE': '此来源未启用或暂时无法查询。'}
ERRORS_EN = {'PREVIOUS_SEARCH_IO_BUSY': 'Previous search I/O is still draining; retry shortly.',
             'SEARCH_DEADLINE': 'Search time budget reached; discovered sources remain selectable.',
             'CANDIDATE_CAPACITY_EXCEEDED': 'Candidate cap reached; some results were omitted.',
             'RETRY_PROVIDER_UNAVAILABLE': 'This source is disabled or temporarily unavailable.'}


def storage_text(directory):
    en = is_english()
    try:
        usage = shutil.disk_usage(directory)
    except OSError:
        return ('Cannot read free storage space right now; no files were deleted.'
                if en else '暂时无法读取可用空间，未清理文件。')
    if en:
        return ('Free {} MiB of {} MiB total.\n'
                'Required install space is verified separately; this screen never deletes files.').format(
                    usage.free // (1024 * 1024), usage.total // (1024 * 1024))
    return ('可用 {} MiB，总计 {} MiB。\n'
            '安装时会另行计算所需空间，本页不会清理文件。').format(
                usage.free // (1024 * 1024), usage.total // (1024 * 1024))


def report_text(report):
    en = is_english()
    prov_map = PROVIDERS_EN if en else PROVIDERS
    state_map = STATES_EN if en else STATES
    stage_map = STAGES_EN if en else STAGES
    err_map = ERRORS_EN if en else ERRORS
    lines = (
        ['Records search status only — never titles, accounts, or playback URLs.',
         'Stages reflect the latest snapshot (non-additive) and exclude manual filters or playback outcomes.', '']
        if en else
        ['仅记录搜索状态，不含片名、账号或播放地址。',
         '各阶段为最近一次统计，不能相加；不包含手动筛选和播放结果。', '']
    )
    stages, providers = {}, []
    for event in report['events']:
        if event['stage'] == 'providers':
            providers = event['providers']
        else:
            stages[event['stage']] = event
    for key, event in stages.items():
        if en:
            origin = {'cache': ' (local cache)', 'network': ' (live query)'}.get(event['state'], '')
            lines.append('{} · {} items{}'.format(stage_map.get(key, 'Stage'), event['count'], origin))
        else:
            origin = {'cache': '（本地缓存）', 'network': '（本次查询）'}.get(event['state'], '')
            lines.append('{} · {} 条{}'.format(stage_map.get(key, '阶段'), event['count'], origin))
    if not report['events']:
        lines.append('No recorded events yet; enable recording and open source selection once.'
                     if en else '尚无可读取的事件，请开启记录后重新进入一次选源。')
    for row in providers:
        if en:
            lines.append('\n{} · {} · Last batch {} items'.format(
                prov_map.get(row['provider'], 'Other Source'), state_map.get(row['state'], 'Unknown'), row['count']))
        else:
            lines.append('\n{} · {} · 最近批次 {} 条'.format(
                prov_map.get(row['provider'], '其他来源'), state_map.get(row['state'], '未知'), row['count']))
        counts = row['completion']
        if counts:
            if en:
                lines.append('Queries {}/{}; failed {}; timed out {}; skipped {}'.format(
                    counts.get('succeeded', 0), counts.get('planned', 0), counts.get('failed', 0),
                    counts.get('timed_out', 0), counts.get('skipped', 0)))
            else:
                lines.append('查询 {}/{}；失败 {}；超时 {}；未执行 {}'.format(
                    counts.get('succeeded', 0), counts.get('planned', 0), counts.get('failed', 0),
                    counts.get('timed_out', 0), counts.get('skipped', 0)))
        if counts.get('stale'):
            lines.append(('Using cache from ~{} min ago; sources may have changed.' if en else
                          '使用约 {} 分钟前的缓存，资源可能已变化。').format(counts.get('snapshot_age', 0) // 60))
        if counts.get('truncated'):
            lines.append('Reached query or page limit; provider was not exhaustively searched.'
                         if en else '达到查询 / 分页上限，尚未搜遍该来源。')
        if row.get('error') in err_map:
            lines.append(err_map[row['error']])
        if row['state'] in ('FAILED', 'TIMEOUT') or counts.get('failed') or counts.get('timed_out'):
            lines.append('Use "Retry Failed Sources" on the source picker while keeping discovered items.'
                         if en else '可在选源页“补查失败来源”，保留已有片源与筛选。')
    if report['incomplete']:
        lines.append('\nLog is incomplete; only partial recorded events are shown above.'
                     if en else '\n记录不完整，以上仅为已记录的部分结果。')
    return '\n'.join(lines)


def _select_report(dialog, directory):
    from bobbi_core.search_trace import reports, read_report
    en = is_english()
    paths = reports(directory)
    if not paths:
        dialog.ok(
            tr(None, '尚无搜索记录', 'No Search Logs Yet'),
            tr(None, '先开启记录，再重新进入影片选源页。', 'Enable recording first, then open source selection for a title.'),
        )
        return None
    labels = [
        time.strftime('%m-%d %H:%M:%S', time.localtime(path.stat().st_mtime))
        + (' · Search Log {}'.format(index + 1) if en else ' · 搜索记录 {}'.format(index + 1))
        for index, path in enumerate(paths)
    ]
    selected = dialog.select(tr(None, '选择本地搜索记录', 'Select Local Search Log'), labels)
    if selected < 0 or selected >= len(paths):
        return None
    return read_report(paths[selected])


def _export(dialog, report):
    import xbmcvfs
    dialog.textviewer(tr(None, '导出前预览', 'Preview Before Export'), report_text(report))
    if not dialog.yesno(
        tr(None, '导出这份诊断？', 'Export This Diagnostic Report?'),
        tr(None, '仅保存刚才预览的搜索状态，不含账号、片名或播放地址。\n下一步选择保存目录，不会自动上传。',
           'Saves only the previewed search status — no accounts, titles, or URLs.\nChoose a folder next; nothing is uploaded automatically.'),
    ):
        return
    folder = dialog.browse(0, tr(None, '选择诊断保存目录', 'Select Export Folder'), 'files')
    if not folder:
        return
    name = 'BobbiTV-search-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.json'
    target = folder.rstrip('/\\') + '/' + name
    if xbmcvfs.exists(target):
        raise OSError('Export destination exists')
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    stream = xbmcvfs.File(target, 'w')
    try:
        written = stream.write(raw)
        if written is not True and not (type(written) is int and written == len(raw)):
            raise OSError('Incomplete diagnostic export')
    finally:
        stream.close()
    dialog.ok(
        tr(None, '诊断已保存', 'Diagnostic Saved'),
        name + '\n' + tr(None, '可将此文件发给维护者，不会自动上传。', 'You may share this file with maintainers; it is never uploaded automatically.'),
    )


def show(dialog):
    import xbmc
    import xbmcvfs
    from bobbi_core import search_trace
    from .paths import profile, ProfileBinding
    from . import optimization
    binding = ProfileBinding()
    directory = profile('script.module.bobbi.core')
    while binding.is_current() and not xbmc.Monitor().abortRequested():
        try:
            en = is_english()
            active = search_trace.enabled(directory)
            count = len(search_trace.reports(directory))
            if en:
                state = ('Quota full' if count >= search_trace.MAX_REPORTS else
                         'Recording (stops in 15 min)' if active else 'Off')
            else:
                state = ('记录已满' if count >= search_trace.MAX_REPORTS else
                         '已开启，15 分钟内自动结束' if active else '未开启')
            enabled, pending = optimization.status(binding.root())
            choice = dialog.select(tr(32089, '检查与诊断', 'Check & Diagnostics'), [
                tr(32090, '检查本机状态', 'Check Local Status'),
                (tr(None, '关闭搜索记录', 'Stop Search Recording') if active else
                 tr(None, '开启搜索记录（15 分钟）', 'Start Search Recording (15 min)')),
                ('{} · {}'.format(f'View Search Logs · {count}', state) if en else
                 '查看搜索记录 · {} 份 · {}'.format(count, state)),
                tr(None, '导出搜索记录', 'Export Search Log'),
                tr(None, '清除搜索记录', 'Clear Search Logs'),
                (('System Optimization · Auto Telemetry: ' + ('On' if enabled else 'Off')) if en else
                 ('系统优化 · 自动回传诊断：' + ('开' if enabled else '关'))),
            ])
            if choice < 0:
                return
            binding.require_current()
            if choice == 0:
                from .capabilities import probe
                from .kodi import rpc
                from .onboarding import summary, steps
                from .bt_setup import helper_state
                from .environment import private_path
                capability = probe(rpc, 'kodi')
                state = helper_state(xbmcvfs.translatePath, private_path(xbmcvfs.translatePath, 'helper-pairing.json'))
                bt = dict(steps(capability, helper_state=state))['helper']
                glass_extra = ''
                try:
                    from .glass_settings import runtime_summary_line
                    glass_line = runtime_summary_line()
                    if glass_line:
                        glass_extra = '\n\n' + glass_line
                except Exception:
                    glass_extra = ''
                footer = tr(None, '仅检查本机，未连接片源或更改设置。',
                            'Checked local device only; no sources contacted or settings changed.')
                dialog.textviewer(
                    tr(32091, '本机状态', 'Local Status'),
                    summary(capability) + '\n\n' + bt + '\n\n' + storage_text(directory) + glass_extra + '\n\n' + footer,
                )
            elif choice == 1:
                if not active and count >= search_trace.MAX_REPORTS:
                    dialog.ok(
                        tr(None, '本地记录已满', 'Local Log Quota Full'),
                        tr(None, '最多保留 8 次搜索，每次最多 256 KiB。可先导出，再清除诊断记录后开启。',
                           'Up to 8 search logs (256 KiB each) are kept. Export if needed, then clear logs before recording again.'),
                    )
                    continue
                search_trace.set_enabled(directory, not active)
                dialog.ok(
                    tr(None, '搜索记录已关闭', 'Search Recording Stopped') if active else tr(None, '搜索记录已开启', 'Search Recording Started'),
                    tr(None, '已有记录仍保留，正在进行的搜索也会停止记录。',
                       'Existing logs are kept and any active search stops recording.') if active else
                    tr(None, '请重新进入影片选源页。15 分钟后自动停止，最多保留 8 次搜索，不会自动上传。',
                       'Open source selection for a title. Stops automatically after 15 minutes (max 8 logs, never uploaded automatically).'),
                )
            elif choice in (2, 3):
                report = _select_report(dialog, directory)
                if report is not None:
                    if choice == 2:
                        dialog.textviewer(tr(None, '本地搜索诊断', 'Local Search Diagnostic'), report_text(report))
                    else:
                        _export(dialog, report)
            elif choice == 4 and dialog.yesno(
                tr(None, '清除本地诊断记录？', 'Clear Local Diagnostic Logs?'),
                tr(None, '将关闭记录并删除最多 8 份搜索诊断，无法撤销，需要的请先导出。\n影片、缓存、账号与观看进度保留。',
                   'Stops recording and permanently deletes up to 8 local search logs. Export first if needed.\nMedia, caches, accounts, and watch history are kept.'),
            ):
                search_trace.clear(directory)
            elif choice == 5:
                index = dialog.select(tr(None, '系统优化 · 诊断日志', 'System Optimization · Telemetry'), [
                    (tr(None, '关闭并清空待发记录', 'Disable & Clear Pending Outbox') if enabled else
                     tr(None, '开启自动回传', 'Enable Auto Telemetry')),
                    ('View Scope · {} pending'.format(pending) if en else '查看收集范围 · 待发 {} 条'.format(pending)),
                ])
                if index == 0:
                    binding.require_current()
                    optimization.set_enabled(binding.root(), not enabled)
                elif index == 1:
                    dialog.textviewer(
                        tr(None, '诊断日志 · 默认开启', 'Diagnostic Telemetry · Enabled by Default'),
                        tr(None,
                           '安装和 Emby 浏览、交接播放时，只回传组件版本、步骤、结果类别和粗略耗时。'
                           '不读取 Kodi 日志、账号、片名、搜索词或地址。每条记录独立编号，不标识设备。\n'
                           '本机最多保留 100 条、7 天，联网后后台重试。关闭即清空待发记录；已经发出的请求不能撤回。'
                           '维护者的 Bobbi 专用服务保留约 14 天。搜索记录仍只在本机。',
                           'During setup and Emby browse/playback handoff, sends only component version, stage, outcome class, and coarse duration. '
                           'Never reads Kodi logs, accounts, titles, queries, or URLs. Each event uses an independent ID with no device fingerprint.\n'
                           'Buffers up to 100 events for 7 days locally. Disabling clears pending events immediately; sent events remain ~14 days on the Bobbi telemetry service. Search logs stay strictly local.'),
                    )
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            dialog.ok(
                tr(None, '诊断未完成', 'Diagnostic Incomplete'),
                tr(None, '请返回后重试，不影响当前播放。', 'Go back and try again; active playback is unaffected.'),
            )
