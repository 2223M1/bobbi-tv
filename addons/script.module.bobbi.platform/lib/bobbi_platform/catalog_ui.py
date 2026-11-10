"""Optional TV detail dialogs. Default browsing and source selection stay put."""
from uuid import uuid4
from .runtime import call

LABELS = {'queued': '排队中', 'running': '扫描中', 'completed': '扫描完成',
          'interrupted': '已中断，可重新扫描', 'failed': '未完整完成', 'canceled': '已取消',
          'unmatched': '待匹配', 'ambiguous': '身份不明确', 'proposed': '待确认建议',
          'confirmed': '人工确认', 'ignored': '已忽略'}


def _call(action, expected, **body):
    return call(action, dict(expected=expected, **body), timeout=2)


def add_directory(expected, parent):
    import xbmcgui
    dialog = xbmcgui.Dialog()
    name = dialog.input('片库名称', defaultt='我的网盘片库')
    if not name or not dialog.yesno('索引此目录？',
            '仅扫描当前目录及其子目录，建立本地索引；不转存、不移动、不删除网盘文件。关闭页面不会取消扫描。'):
        return False
    try:
        result = _call('catalog_add', expected, name=name, parent=parent)
        _call('catalog_scan', expected, source_id=result['source_id'])
        dialog.ok('已提交后台扫描', '可在“片库索引与任务”查看进度和整理作品；原文件浏览仍可使用。')
        return True
    except (ValueError, OSError, RuntimeError):
        dialog.ok('未确认扫描结果', '来源可能已保存，请在片库索引中刷新任务状态。不要重复提交。')
        return False


def _mapping(dialog, item):
    kind = dialog.select('选择描述方式（仅修改本地元数据）', ['自定义名称', '电影 TMDb 编号', '剧集 TMDb 编号'])
    if kind not in (0, 1, 2):
        return None
    current = item.get('mapping') or {}
    title = dialog.input('显示名称', defaultt=current.get('title') or item['file']['name'])
    if not title:
        return None
    value = dict(kind=('custom', 'movie', 'tv')[kind], title=title,
                 tmdb_id=None, season=None, episode=None, version=None)
    if kind:
        raw = dialog.input('TMDb 数字编号（人工描述，不用于自动续播证明）')
        if not raw.isdecimal():
            return None
        value['tmdb_id'] = int(raw)
    if kind == 2:
        season = dialog.input('季号（特别篇为 0，未知请取消）')
        episode = dialog.input('集号（未知请取消）')
        if not season.isdecimal() or not episode.isdecimal():
            return None
        value['season'], value['episode'] = int(season), int(episode)
    return value


def review_item(dialog, expected, item):
    choice = dialog.select(item['file']['name'], ['查看原文件与建议', '设置作品 / 自定义名称',
        '解除绑定', '忽略此项', '撤回上次修改'])
    if choice == 0:
        evidence = item.get('candidates') or []
        detail = item['file']['parent'] + '\n' + item['reason']
        if evidence and evidence[0].get('season') is not None:
            detail += '\n文件名提示 S%02dE%02d（尚未证明作品身份）' % (evidence[0]['season'], evidence[0]['episode'])
        if item['file'].get('truncated'):
            detail += '\n名称或目录显示已截短，原始记录保留。'
        dialog.ok('原文件与建议', detail)
        return
    if choice not in (1, 2, 3, 4):
        return
    value = _mapping(dialog, item) if choice == 1 else None
    if choice == 1 and value is None:
        return
    command = dict(file_id=item['file']['id'], expected_revision=item['revision'],
        action={1: 'confirm', 2: 'unbind', 3: 'ignore', 4: 'undo'}[choice], mapping=value)
    preview = _call('catalog_preview', expected, commands=[command])['items'][0]
    if preview['status'] != 'ready':
        dialog.ok('记录已变化', '请刷新后重新选择，未覆盖较新的修改。')
        return
    if not dialog.yesno('确认修改本地描述？', item['file']['name'] + '\n' +
            (preview['after']['title'] if preview['after'] else '解除描述 / ' + preview['after_state']) + '\n不修改文件、观看进度或播放授权。'):
        return
    result = _call('catalog_apply', expected, request_id=uuid4().hex, commands=[command])['items'][0]
    dialog.ok('已保存' if result['status'] == 'applied' else '未保存',
              '仅修改本地元数据。' if result['status'] == 'applied' else '记录已变化或输入无效，请刷新后重试。')


def _items(dialog, expected, source=None, state=None):
    offset = 0
    while True:
        result = _call('catalog_items', expected, source=source, state=state, offset=offset)
        rows = result['items']
        if not rows:
            dialog.ok('当前筛选暂无条目' if state else '尚无索引条目',
                '可返回查看全部条目。' if state else '先在网盘文件目录选择“将此目录加入片库”。扫描未完成时只显示已提交部分。')
            return
        labels = [('来源已不包含 · ' if not r['available'] else '') +
                  LABELS.get(r['state'], r['state']) + ' · ' + r['file']['name'] for r in rows]
        if result['next_offset'] is not None:
            labels.append('下一页')
        choice = dialog.select('片库整理 · 元数据不代表已可播', labels)
        if choice < 0:
            return
        if choice == len(rows):
            offset = result['next_offset']
        elif choice < len(rows):
            review_item(dialog, expected, rows[choice])


def _jobs(dialog, expected):
    offset = 0
    while True:
        result = _call('catalog_jobs', expected, offset=offset)
        rows = result['items']
        if not rows:
            dialog.ok('暂无后台任务', '尚未提交目录扫描。')
            return
        choice = dialog.select('扫描任务（重新进入即可刷新）', [
            '%s · 已扫描 %d / 已发现 %d%s' % (LABELS.get(r['state'], r['state']),
                r['counts']['scanned'], r['counts']['discovered'], ' · 正在取消' if r['cancel_requested'] and r['state'] in ('queued', 'running') else '')
            for r in rows] + (['下一页'] if result['next_offset'] is not None else []))
        if choice < 0:
            return
        if choice == len(rows):
            offset = result['next_offset']
            continue
        row = rows[choice]
        if row['state'] in ('running', 'queued') and dialog.yesno('请求取消扫描？', '仅停止本次扫描，已有索引和云端文件保留；后台确认停止后才会显示已取消。'):
            _call('catalog_cancel', expected, task_id=row['task_id'])
        else:
            dialog.ok('任务状态', LABELS.get(row['state'], row['state']) + '\n' + row['result_summary'])


def manage():
    import xbmcgui
    from .pan_ui import _status
    from .pan_accounts import NAMES
    dialog = xbmcgui.Dialog()
    try:
        accounts = [r for r in _status() if r['provider'] != '115' and r['account']['authenticated']]
        if not accounts:
            from .library_ui import cd2_mounts, open_existing_cd2, open_library
            mounted = bool(cd2_mounts.discover())
            if dialog.yesno('目录索引支持范围',
                    '当前索引仅支持已原生登录的个人网盘（115 除外）。CD2 / WebDAV / SMB / NFS / 本机目录暂不支持此索引。'
                    '\n已有挂载和片库可直接浏览、播放，无需为此再次扫码。',
                    yeslabel='浏览 CD2' if mounted else '浏览片库', nolabel='返回'):
                return open_existing_cd2(dialog) if mounted else open_library(dialog)
            return
        selected = dialog.select('选择当前账号的片库', [NAMES[r['provider']] for r in accounts]) if len(accounts) > 1 else 0
        if not 0 <= selected < len(accounts):
            return
        expected = accounts[selected]['account']
        while True:
            sources = _call('catalog_sources', expected)['items']
            choice = dialog.select('片库索引与任务', ['查看全部 / 待确认', '后台任务', '手机详细管理'] +
                [s['name'] for s in sources])
            if choice < 0:
                return
            if choice == 0:
                states = [None, 'unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored']
                selected_state = dialog.select('查看范围', ['全部条目'] + [LABELS[s] for s in states[1:]])
                if 0 <= selected_state < len(states):
                    _items(dialog, expected, state=states[selected_state])
            elif choice == 1:
                _jobs(dialog, expected)
            elif choice == 2:
                from lib.clients.stremio.manage_phone import catalog_manage_phone
                catalog_manage_phone(expected)
            else:
                source = sources[choice - 3]
                action = dialog.select(source['name'], ['查看已索引条目', '重新完整扫描', '移除此索引来源'])
                if action == 0:
                    _items(dialog, expected, source['id'])
                elif action == 1:
                    _call('catalog_scan', expected, source_id=source['id'])
                    dialog.ok('已提交扫描', '关闭此页面不影响后台任务。')
                elif action == 2 and dialog.yesno('移除此索引来源？', '请先停止扫描。仅移除本机目录登记；网盘文件、观看历史和人工描述保留。'):
                    _call('catalog_remove', expected, source_id=source['id'])
    except (ValueError, OSError, RuntimeError, ImportError):
        dialog.ok('片库管理暂不可用', '请检查服务和当前账号后重试。索引、文件和已保存的修改均保留。')
