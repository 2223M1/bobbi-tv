"""Optional TV detail dialogs. Default browsing and source selection stay put."""
import json
import re
import time
from .runtime import call

LABELS = {'queued': '排队中', 'running': '扫描中', 'completed': '扫描完成',
          'interrupted': '已中断，可重新扫描', 'failed': '未完整完成', 'canceled': '已取消',
          'unmatched': '待匹配', 'ambiguous': '身份不明确', 'proposed': '待确认建议',
          'confirmed': '人工确认', 'ignored': '已忽略', 'uncertain': '结果待核对',
          'unknown': '状态未知', 'suppressed': '已停止准备'}
PREPARATION_LABELS = dict(LABELS, running='准备中', completed='准备完成')


def source_status(source):
    """One bounded source observation; task details still use the existing jobs UI."""
    observation = source.get('observation') or {}
    if not observation:
        return ''
    state = observation.get('latest_state', 'none')
    counts = observation.get('counts') or {}
    lines = [{'none': '尚未扫描', 'cancel_requested': '已请求取消，等待后台确认'}.get(state, LABELS.get(state, state)),
        {'never': '未观察范围', 'partial': '仅已提交部分', 'complete': '上次完整扫描'}.get(observation.get('coverage'), '范围待核对'),
        '已扫描 %s 项 / 发现 %s 文件 · 已收录 %s' % (counts.get('scanned', 0),
            counts.get('discovered', 0), observation.get('indexed_count', 0))]
    if observation.get('availability') == 'source_unavailable':
        lines.append('来源离线，保留整理记录')
    elif observation.get('recheck_required'):
        lines.append('观察范围待复核，可重新扫描；播放前仍核验')
    return ' · '.join(lines)


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
                 tmdb_id=None, season=None, episode=None, version=current.get('version'))
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
        '解除绑定', '忽略此项', '撤回上次修改', '高级：手填编号 / 自定义名称', '同目录分集整理（逐项预览）', '编辑文件版本备注'])
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
        value['version'] = (item.get('mapping') or {}).get('version')
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
    elif choice == 7:
        value = dict(item.get('mapping') or dict(kind='custom', title=item['file']['name'],
            tmdb_id=None, season=None, episode=None, version=None))
        version = dialog.input('版本备注（最多 80 字，不作为续播证明）', defaultt=value.get('version') or '').strip()
        if len(version) > 80:
            dialog.ok('备注过长', '请缩短到 80 字以内。未修改记录。')
            return
        value['version'], action = version or None, 'confirm'
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
        try:
            result = _call('catalog_group', expected, **params)
        except ValueError as error:
            if str(error) != 'CATALOG_GROUP_AMBIGUOUS' or source_id is not None:
                raise
            # Overlapping registrations are not evidence of a trusted group.
            # Let the user choose one; core still checks anchor membership.
            sources = _call('catalog_sources', expected)['items']
            choice = dialog.select('目录被多个来源收录，请明确选择可信来源',
                                   [row['name'] + ' · ' + row['id'][:8] for row in sources])
            if not 0 <= choice < len(sources):
                return
            source_id = sources[choice]['id']
            try:
                result = _call('catalog_group', expected, **dict(params, source_id=source_id))
            except ValueError as changed:
                if str(changed) != 'CATALOG_SOURCE_UNAVAILABLE':
                    raise
                dialog.ok('所选来源不包含此文件', '未扩大整理范围，请返回明确选择收录此文件的来源。')
                return
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


def _mapping_description(value):
    """Display only; retain the Host's original mapping and review command."""
    if not value:
        return '未设置'
    parts = [value.get('title') or '未填写名称',
             {'tv': '剧集', 'movie': '电影', 'custom': '自定义名称'}.get(value.get('kind'), '类型待核对')]
    if value.get('tmdb_id') is not None:
        parts.append('TMDb %s' % value['tmdb_id'])
    if value.get('kind') == 'tv':
        season, episode = value.get('season'), value.get('episode')
        parts.append('S%02dE%02d' % (season, episode) if type(season) is int and type(episode) is int else '季集未明确')
    parts.append('版本备注 %s' % (value.get('version') or '未填写'))
    return ' · '.join(parts)


def review_entries(dialog, expected, entries):
    """Bounded TV batch coordinator; existing Host remains the sole writer."""
    from bobbi_core.catalog_review import plan
    chunks = plan(entries)
    previews, receipts, saved, deadline = [], [], 0, time.monotonic() + 120
    pending_request_id = None
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
            action = {'confirm': '保存描述', 'unbind': '解除绑定', 'ignore': '忽略此项', 'undo': '撤回上次修改'}
            previews.append('%s\n记录修订 %s\n原描述 %s\n修改后描述 %s\n操作 %s · 修改后状态 %s' % (
                entry['name'], entry['command']['expected_revision'], _mapping_description(row.get('before')),
                _mapping_description(row.get('after')), action.get(entry['command']['action'], '待核对'),
                LABELS.get(row.get('after_state'), '状态未知')))
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
                pending_request_id = chunk['request_id']
                _pending_receipts(expected, request_id=pending_request_id, count=len(chunk['entries']))
            break
    dialog.textviewer('真实回执 · 已保存 %s/%s' % (saved, len(entries)), '\n'.join(receipts) + '\n未开始批次未提交，不自动回滚此前结果。')
    return dict(saved=saved, total=len(entries), complete=saved == len(entries),
                pending_request_id=pending_request_id)


def _open_catalog(expected, **query):
    """Legacy management URLs enter the sole cursor-based directory renderer."""
    import xbmc
    from lib.utils.views.personal_catalog import route, scope_params
    xbmc.executebuiltin('ActivateWindow(Videos,"' + route(
        action='personal_catalog', **scope_params(expected), **query) + '",return)')


def _pending_receipts(expected, request_id=None, count=None, remove=False):
    """A bounded UI reminder, not a receipt or mutation authority."""
    try:
        import xbmcgui
        from bobbi_core.catalog_query import opaque, scope_key
        window = xbmcgui.Window(10000)
        key = 'Bobi.Catalog.Pending.' + opaque(*scope_key(expected))
        raw = window.getProperty(key)
        rows = json.loads(raw) if raw else []
        if type(rows) is not list:
            rows = []
        rows = [row for row in rows if type(row) is dict and
                re.fullmatch('[0-9a-f]{32}', str(row.get('request_id', ''))) and
                type(row.get('count')) is int and 1 <= row['count'] <= 5]
        if request_id:
            rows = [row for row in rows if row['request_id'] != request_id]
            if not remove:
                rows.append(dict(request_id=request_id, count=count))
            rows = rows[-20:]
            window.setProperty(key, json.dumps(rows))
        return rows
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        return []


def query_receipt(dialog, expected, request_id=None):
    """Recover only the original request. Never make a new plan or write."""
    pending = _pending_receipts(expected)
    if request_id is None:
        if pending:
            choice = dialog.select('查询待核对的原提交', [row['request_id'] for row in pending])
            if not 0 <= choice < len(pending):
                return
            request_id = pending[choice]['request_id']
        else:
            request_id = dialog.input('原提交编号（仅查询，不重新提交）').strip()
    if type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id):
        return
    try:
        receipt = _call('catalog_receipt', expected, request_id=request_id)
    except (ValueError, OSError, RuntimeError):
        dialog.ok('原提交仍待核对', '暂未读取到回执，未重新提交。可稍后在当前片库管理中继续查询。')
        return
    rows = receipt.get('items', [])
    lines = ['原提交编号：' + request_id]
    lines.extend('第 %s 项 · %s' % (row['index'] + 1,
        {'applied': '已保存', 'conflict': '修订冲突', 'failed': '未保存'}.get(row['status'], '待核对')) for row in rows)
    if not rows:
        lines.append('尚未查到回执，不能据此认定未写入；未重新提交。')
    expected_count = next((row['count'] for row in pending if row['request_id'] == request_id), None)
    if expected_count and {row['index'] for row in rows if row['status'] in ('applied', 'conflict', 'failed')} == set(range(expected_count)):
        _pending_receipts(expected, request_id=request_id, remove=True)
    dialog.textviewer('原提交回执', '\n'.join(lines))
    return receipt


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
    choice = dialog.select('当前片库管理', ['后台任务', '实时查看任务', '手机详细管理',
        '待整理工作台', '查询待核对的原提交', '管理索引来源'])
    if choice == 0:
        return _jobs(dialog, expected)
    if choice == 1:
        return _watch_jobs(expected)
    if choice == 2:
        from lib.clients.stremio.manage_phone import catalog_manage_phone
        return catalog_manage_phone(expected)
    if choice == 3:
        return _open_catalog(expected, mode='review')
    if choice == 4:
        return query_receipt(dialog, expected)
    if choice == 5:
        return manage_sources(expected, dialog)


def manage_sources(expected, dialog):
    if expected.get('reference_kind') == 'mounted_path':
        from .library_ui import open_library
        return open_library(dialog)
    sources = _call('catalog_sources', expected)['items']
    selected = dialog.select('索引来源（新增来源请在原文件目录操作）',
        [row['name'] + ('\n' + source_status(row) if source_status(row) else '') for row in sources])
    if not 0 <= selected < len(sources):
        return
    source = sources[selected]
    choice = dialog.select(source['name'], ['查看作品', '待整理工作台', '重新完整扫描', '移除此索引来源'])
    if choice in (0, 1):
        return _open_catalog(expected, source_id=source['id'],
                             **(dict(mode='review') if choice == 1 else dict(view='works')))
    if choice == 2:
        _call('catalog_scan', expected, source_id=source['id'])
        dialog.ok('已提交扫描', '关闭此页面不影响后台任务。')
    elif choice == 3 and dialog.yesno('移除此索引来源？', '请先停止扫描。仅移除本机目录登记；网盘文件、观看历史和人工描述保留。'):
        _call('catalog_remove', expected, source_id=source['id'])


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
                    '个人网盘作品索引需要原生登录（115 除外）。现有 CD2 本机挂载先在“管理片库来源”中登记，'
                    '随后在“我的作品片库”选择 CD2 来源并扫描。'
                    '\nWebDAV / SMB / NFS / 普通本机目录仍使用原文件浏览；已有挂载无需为此再次扫码。',
                    yeslabel='片库与 CD2 索引' if mounted else '浏览片库', nolabel='返回'):
                return open_library(dialog)
            return
        selected = dialog.select('选择当前账号的片库', [NAMES[r['provider']] for r in accounts]) if len(accounts) > 1 else 0
        if not 0 <= selected < len(accounts):
            return
        expected = accounts[selected]['account']
        return _open_catalog(expected, mode='review')
    except (ValueError, OSError, RuntimeError, ImportError):
        dialog.ok('片库管理暂不可用', '请检查服务和当前账号后重试。索引、文件和已保存的修改均保留。')
