"""Optional TV detail dialogs. Default browsing and source selection stay put."""
import time
from .runtime import call

LABELS = {'queued': '排队中', 'running': '扫描中', 'completed': '扫描完成',
          'interrupted': '已中断，可重新扫描', 'failed': '未完整完成', 'canceled': '已取消',
          'unmatched': '待匹配', 'ambiguous': '身份不明确', 'proposed': '待确认建议',
          'confirmed': '人工确认', 'ignored': '已忽略', 'uncertain': '结果待核对',
          'unknown': '状态未知', 'suppressed': '已停止准备'}
PREPARATION_LABELS = dict(LABELS, running='准备中', completed='准备完成')


def _call(action, expected, **body):
    if expected.get('reference_kind') == 'mounted_path':
        return call(action.replace('catalog_', 'catalog_mount_', 1),
                    dict(body, source_id=expected['source_id'], namespace=expected['namespace']), timeout=2)
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


def review_item(dialog, expected, item, source_id=None):
    choice = dialog.select(item['file']['name'], ['搜索并选择作品候选', '查看原文件与建议',
        '解除绑定', '忽略此项', '撤回上次修改', '高级：手填编号 / 自定义名称', '同目录分集整理（逐项预览）'])
    candidate = None
    if choice in (0, 6):
        candidate = choose_candidate(dialog, item)
        if candidate is None:
            return
        if choice == 6:
            return review_group(dialog, expected, item, candidate, source_id=source_id)
        from lib.clients.tmdb.catalog_candidates import candidate_mapping
        try:
            value = candidate_mapping(candidate, item)
        except ValueError:
            value = _candidate_episode(dialog, candidate)
        if value is None:
            return
        action = 'confirm'
    elif choice == 1:
        evidence = item.get('candidates') or []
        detail = item['file']['parent'] + '\n' + item['reason']
        if evidence and evidence[0].get('season') is not None:
            detail += '\n文件名提示 S%02dE%02d（尚未证明作品身份）' % (evidence[0]['season'], evidence[0]['episode'])
        if item['file'].get('truncated'):
            detail += '\n名称或目录显示已截短，原始记录保留。'
        dialog.ok('原文件与建议', detail)
        return
    elif choice in (2, 3, 4, 5):
        value = _mapping(dialog, item) if choice == 5 else None
        if choice == 5 and value is None:
            return
        action = {5: 'confirm', 2: 'unbind', 3: 'ignore', 4: 'undo'}[choice]
    else:
        return
    result = review_entries(dialog, expected, [dict(name=item['file']['name'], command=dict(
        file_id=item['file']['id'], expected_revision=item['revision'], action=action, mapping=value))])
    if (result and result['complete'] and candidate and candidate['media_kind'] == 'tv' and
            dialog.yesno('继续整理本剧？', '本集已保存。只读取同目录逐项建议，不会自动绑定其他文件。')):
        review_group(dialog, expected, item, candidate, source_id=source_id)
    return result


def choose_candidate(dialog, item):
    from lib.clients.tmdb.catalog_candidates import query_hint, search
    query = dialog.input('搜索作品（只发送关键词，不发送私有目录 / 账号）', defaultt=query_hint(item['file']['name']))
    if not query:
        return None
    evidence = (item.get('candidates') or [{}])[0]
    try:
        import xbmc
        candidates = search(query, year=evidence.get('year'), cancelled=xbmc.Monitor().abortRequested)['items']
    except (ValueError, OSError, RuntimeError):
        dialog.ok('候选搜索未完成', '可重试或返回使用手动 TMDb 编号。未修改任何记录。')
        return None
    if not candidates:
        dialog.ok('没有找到候选', '请修改关键词或使用高级手动编号。')
        return None
    labels = [('%s · %s · %s\n%s\n%s' % ('剧集' if row['media_kind'] == 'tv' else '电影',
        row['title'], row['year'] or '年份未知', row['original_title'], row['basis'])) for row in candidates]
    # Native detailed select supports the same constrained public poster origin.
    try:
        import xbmcgui
        choices = []
        for label, row in zip(labels, candidates):
            choice = xbmcgui.ListItem(label=label)
            if row['poster_path']:
                choice.setArt({'thumb': 'https://image.tmdb.org/t/p/w185' + row['poster_path']})
            choices.append(choice)
        selected = dialog.select('选择候选（尚未确认作品）', choices, useDetails=True)
    except (AttributeError, TypeError):
        selected = dialog.select('选择候选（尚未确认作品）', labels)
    return candidates[selected] if 0 <= selected < len(candidates) else None


def _candidate_episode(dialog, candidate):
    from bobbi_core.catalog_review import mapping
    season = dialog.input('明确季号（特别篇为 0；合集 / 多集文件请取消）')
    episode = dialog.input('明确单集编号（未知请取消）')
    if not season.isdecimal() or not episode.isdecimal():
        return None
    try:
        return mapping(dict(kind='tv', title=candidate['title'], tmdb_id=candidate['tmdb_id'],
                            season=int(season), episode=int(episode), version=None))
    except ValueError:
        return None


def review_group(dialog, expected, anchor, candidate, source_id=None, start=0):
    from lib.clients.tmdb.catalog_candidates import candidate_mapping, query_hint
    if candidate['media_kind'] != 'tv':
        dialog.ok('请先选择剧集候选', '电影不生成季集映射。')
        return
    rows, offset, group, revision = [], start, None, None
    deadline = time.monotonic() + 60
    if start:
        fresh = _call('catalog_group', expected, file_id=anchor['file']['id'], source_id=source_id, offset=0, limit=5)
        group, revision, source_id = fresh['group_id'], fresh['projection_revision'], fresh['source_id']
    while True:
        if time.monotonic() >= deadline:
            dialog.ok('目录建议未完整读取', '请缩小索引来源并分轮整理，尚未修改记录。')
            return
        params = dict(file_id=anchor['file']['id'], offset=offset, limit=5)
        if source_id:
            params['source_id'] = source_id
        if revision is not None:
            params['projection_revision'] = revision
        result = _call('catalog_group', expected, **params)
        if group is not None and (group != result['group_id'] or revision != result['projection_revision']):
            raise ValueError('CATALOG_CURSOR_STALE')
        group, revision, source_id = result['group_id'], result['projection_revision'], result['source_id']
        rows.extend(result['items'])
        following = result['next_offset']
        if following is None or len(rows) >= 100:
            break
        if type(following) is not int or following <= offset:
            raise ValueError('CATALOG_CURSOR_STALE')
        offset = following
    proposals, labels, preselect = [], [], []
    for index, item in enumerate(rows):
        evidence = (item.get('candidates') or [{}])[0]
        try:
            value = candidate_mapping(candidate, item)
        except ValueError:
            value = None
        suspicious = (not value or item['state'] == 'ambiguous' or item.get('available') is False or
            item['file'].get('truncated') or query_hint(item['file']['name']).casefold() != query_hint(anchor['file']['name']).casefold() or
            evidence.get('year') and candidate.get('year') and evidence['year'] != candidate['year'] or
            (item.get('mapping') or {}).get('tmdb_id') not in (None, candidate['tmdb_id']) or
            (item.get('mapping') or {}).get('kind') not in (None, 'custom', 'tv'))
        if not suspicious:
            preselect.append(index)
        proposals.append(value)
        target = '需手动明确季集' if value is None else 'S%02dE%02d' % (value['season'], value['episode'])
        labels.append('%s → %s %s · 修订 %s%s' % (item['file']['name'], candidate['title'], target,
            item['revision'], ' · 存在疑点，默认未选' if suspicious else ''))
    selected = dialog.multiselect('逐项选择：同目录不证明同作品；排除合集 / 重制版 / 多集文件', labels, preselect=preselect)
    if not selected:
        if following is not None and dialog.yesno('跳过本轮并查看下一轮？', '本轮未选择任何修改；后续仍逐项核对，每轮最多 100 项。'):
            return review_group(dialog, expected, anchor, candidate, source_id, start=following)
        return
    edit_selected = dialog.yesno('需要逐项调整季集？', '不调整则沿用上方已核对的建议。未知季集的勾选项仍需手动明确；合集 / 多集文件请排除。')
    entries = []
    for index in selected:
        item, value = rows[index], proposals[index]
        if value is None:
            value = _candidate_episode(dialog, candidate)
        elif edit_selected:
            value = _candidate_episode(dialog, candidate)
        if value is not None:
            entries.append(dict(name=item['file']['name'], command=dict(file_id=item['file']['id'],
                expected_revision=item['revision'], action='confirm', mapping=value)))
    if entries:
        result = review_entries(dialog, expected, entries)
        if result and result['complete'] and following is not None and dialog.yesno('继续下一轮同目录整理？',
                '本轮真实回执已显示；下一轮重新读取当前修订，不会自动提交。'):
            return review_group(dialog, expected, anchor, candidate, source_id, start=following)
        return result


def review_entries(dialog, expected, entries):
    """Bounded TV batch coordinator; existing Host remains the sole writer."""
    from bobbi_core.catalog_review import plan
    chunks = plan(entries)
    previews, receipts, saved, deadline = [], [], 0, time.monotonic() + 120
    for chunk in chunks:
        if time.monotonic() >= deadline:
            dialog.ok('预览已到期限', '请重新预览，尚未提交修改。')
            return
        commands = [entry['command'] for entry in chunk['entries']]
        rows = _call('catalog_preview', expected, commands=commands)['items']
        if len(rows) != len(commands) or any(row['status'] != 'ready' for row in rows):
            dialog.ok('预览包含冲突', '未提交任何批次，请刷新后重新选择。')
            return
        for entry, row in zip(chunk['entries'], rows):
            after = row.get('after') or {}
            previews.append('%s · 修订 %s\n原描述 %s\n拟绑定 %s · S%sE%s · 版本备注 %s\n操作 %s · 修改后状态 %s' % (
                entry['name'], entry['command']['expected_revision'], row.get('before'), after.get('title'),
                after.get('season'), after.get('episode'), after.get('version'), entry['command']['action'], row.get('after_state')))
    dialog.textviewer('逐项预览（尚未保存）', '\n\n'.join(previews))
    if not dialog.yesno('确认分批保存？', '%s 项将分 %s 批。已保存批次不会因后续冲突自动回滚；每批开始前仍会检查修订。' % (len(entries), len(chunks))):
        return
    for number, chunk in enumerate(chunks):
        if time.monotonic() >= deadline:
            receipts.append('已到本轮等待期限，请重新读取剩余条目并预览。');break
        if number and not dialog.yesno('继续下一批？', '已保存 %s/%s。可停止未开始批次，已保存结果保留。' % (saved, len(entries))):
            break
        commands = [entry['command'] for entry in chunk['entries']]
        preview = _call('catalog_preview', expected, commands=commands)['items']
        if len(preview) != len(commands) or any(row['status'] != 'ready' for row in preview):
            receipts.append('后续批次出现冲突，停止提交。');break
        try:
            rows = _call('catalog_apply', expected, request_id=chunk['request_id'], commands=commands)['items']
            results = dict(enumerate(rows))
        except (ValueError, OSError, RuntimeError):
            # A read-only receipt lookup never repeats a write on timeout.
            try:
                receipt = _call('catalog_receipt', expected, request_id=chunk['request_id'])
                results = {row['index']: row for row in receipt.get('items', [])}
            except (ValueError, OSError, RuntimeError):
                results = {}
        complete = True
        for index, entry in enumerate(chunk['entries']):
            state = results.get(index, {}).get('status')
            saved += state == 'applied'
            complete = complete and state == 'applied'
            receipts.append(entry['name'] + ' · ' + {'applied': '已保存', 'conflict': '版本冲突', 'failed': '未保存'}.get(state, '提交结果待核对；请读取当前修订人工核对'))
        if not complete:
            if any(index not in results for index in range(len(chunk['entries']))):
                receipts.append('待核对的原提交编号：' + chunk['request_id'])
            break
    dialog.textviewer('真实回执 · 已保存 %s/%s' % (saved, len(entries)), '\n'.join(receipts) + '\n未开始批次未提交，不自动回滚此前结果。')
    return dict(saved=saved, total=len(entries), complete=saved == len(entries))


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
            review_item(dialog, expected, rows[choice], source_id=source)


def _jobs(dialog, expected):
    offset = 0
    while True:
        result = _call('catalog_jobs', expected, offset=offset)
        rows = result['items']
        if not rows:
            dialog.ok('暂无后台任务', '尚未提交目录扫描。')
            return
        choice = dialog.select('扫描任务', [
            '%s · 已扫描 %d / 已发现 %d%s' % (LABELS.get(r['state'], r['state']),
                r['counts']['scanned'], r['counts']['discovered'], ' · 正在取消' if r['cancel_requested'] and r['state'] in ('queued', 'running') else '')
            for r in rows] + (['下一页'] if result['next_offset'] is not None else []) + ['实时查看本页任务（最长 2 分钟）'])
        if choice < 0:
            return
        if choice == len(rows) + int(result['next_offset'] is not None):
            _watch_jobs(expected, offset=offset)
            continue
        if choice == len(rows) and result['next_offset'] is not None:
            offset = result['next_offset']
            continue
        row = rows[choice]
        if row['state'] in ('running', 'queued') and dialog.yesno('请求取消扫描？', '仅停止本次扫描，已有索引和云端文件保留；后台确认停止后才会显示已取消。'):
            _call('catalog_cancel', expected, task_id=row['task_id'])
        else:
            dialog.ok('任务状态', LABELS.get(row['state'], row['state']) + '\n' + row['result_summary'])


def watch_preparation(expected=None, dialog=None):
    """Existing 115 authority, separate from native-pan phone/catalog sessions."""
    import xbmcgui
    from .account_manager import validate_snapshot
    dialog = dialog or xbmcgui.Dialog()
    try:
        current = validate_snapshot(call('account_status', {}, timeout=2), authenticated=True)
        if expected is not None and expected != current:
            raise ValueError('ACCOUNT_CHANGED')
        _watch_jobs(current, kind='preparation')
    except (ValueError, OSError, RuntimeError):
        dialog.ok('准备任务暂不可读', '请检查当前 115 登录和后台状态。未重新登录、创建或重试任何准备任务。')


def _watch_jobs(expected, offset=0, kind='scan'):
    """Visible, single-flight observation; closing never cancels a Host job."""
    import xbmc
    import xbmcgui
    progress, monitor = xbmcgui.DialogProgress(), xbmc.Monitor()
    progress.create('任务实时状态 · 返回仅停止查看', '只显示真实已扫描 / 已发现数量；总数未知，不估算完成百分比。')
    deadline, delay = time.monotonic() + 120, 5
    try:
        while time.monotonic() < deadline and not progress.iscanceled() and not monitor.abortRequested():
            try:
                if kind == 'preparation':
                    # Read current authority every observation. No pan scope is
                    # substituted for the 115 account's independent generation.
                    from .account_manager import validate_snapshot
                    current = validate_snapshot(call('account_status', {}, timeout=2), authenticated=True)
                    if current != expected:
                        raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                    value = _call('jobs', expected, kind='preparation', offset=offset, limit=5)
                else:
                    value = _call('catalog_jobs', expected, offset=offset, limit=5)
                rows = value['items']
            except (ValueError, OSError, RuntimeError) as error:
                if str(error) in ('CATALOG_ACCOUNT_MISMATCH', 'CATALOG_SERVICE_CLOSED', 'ACCOUNT_SCOPE_INVALID'):
                    progress.update(0, '账号或服务已变化，已停止读取。请返回重新选择账号。')
                    return
                progress.update(0, '暂未取得新状态，后台任务保持原状态。返回不会取消任务。')
                delay = min(30, delay * 2)
            else:
                delay = 5
                lines = []
                for row in rows:
                    counts = row.get('counts') or {}
                    state = (PREPARATION_LABELS if kind == 'preparation' else LABELS).get(row['state'], row['state'])
                    if row.get('cancel_requested') and row['state'] in ('queued', 'running'):
                        state += ' · 已请求取消，等待后台确认'
                    lines.append('%s · 阶段 %s（不自动重试未知结果）' % (state, row.get('stage', 'unknown')) if kind == 'preparation' else
                                 '%s · 已扫描 %s / 已发现 %s' % (state, counts.get('scanned', 0), counts.get('discovered', 0)))
                # The native widget requires a numeric argument. Keep its bar
                # at zero; no invented completion percentage enters the text.
                progress.update(0, '\n'.join(lines or ['当前页暂无任务。']) + '\n返回只停止查看，不取消后台任务。')
                if not rows or all(row['state'] not in ('queued', 'running') for row in rows):
                    return
            until = min(deadline, time.monotonic() + delay)
            while time.monotonic() < until and not progress.iscanceled():
                if monitor.waitForAbort(min(.1, until - time.monotonic())):
                    return
    finally:
        progress.close()


def manage_scope(expected, dialog=None):
    """One scoped management entry for native and registered mounted catalogs."""
    import xbmcgui
    dialog = dialog or xbmcgui.Dialog()
    choice = dialog.select('当前片库管理', ['后台任务', '实时查看任务', '手机详细管理'])
    if choice == 0:
        return _jobs(dialog, expected)
    if choice == 1:
        return _watch_jobs(expected)
    if choice == 2:
        from lib.clients.stremio.manage_phone import catalog_manage_phone
        return catalog_manage_phone(expected)


def manage():
    import xbmcgui
    from .pan_ui import _status
    from .pan_accounts import NAMES
    dialog = xbmcgui.Dialog()
    try:
        accounts = [r for r in _status() if r['provider'] != '115' and r['account']['authenticated']]
        if not accounts:
            from .library_ui import cd2_mounts, open_library
            mounted = bool(cd2_mounts.discover())
            if dialog.yesno('目录索引支持范围',
                    '个人网盘作品索引需要原生登录（115 除外）。现有 CD2 本机挂载可在片库的“CD2 索引片库”中登记与扫描。'
                    '\nWebDAV / SMB / NFS / 普通本机目录仍使用原文件浏览；已有挂载无需为此再次扫码。',
                    yeslabel='片库与 CD2 索引' if mounted else '浏览片库', nolabel='返回'):
                return open_library(dialog)
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
