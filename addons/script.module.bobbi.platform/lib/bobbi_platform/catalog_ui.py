"""Optional TV detail dialogs. Default browsing and source selection stay put."""
from bobbi_core.typed_ref import KINDS as PATH_KINDS, action_prefix, request_scope
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
SEGMENT_LABELS = {'intro': '片头', 'recap': '回顾', 'outro': '片尾', 'credits_scene': '彩蛋'}
SCAN_REASONS = {
    'PROFILE_CHANGED': '用户配置已切换，旧任务已停止；原片库的已提交记录保留。',
    'CATALOG_NETWORK_INCOMPLETE': '网络目录未提供完整直接子项列表，未推断删除。原文件浏览仍可用。',
    'CATALOG_NETWORK_METADATA_REQUIRED': '网络目录缺少文件大小或精确修改时间，未推断删除。原文件浏览仍可用。',
    'PAN_INCOMPLETE_PAGE': '网盘分页返回条数不完整，未推断删除；原已收录文件与整理记录保留。',
    'PAN_PAGE_EXPIRED': '扫描期间目录分页或总数发生变化，未推断删除；可重新扫描。',
    'SCAN_PAGE_CYCLE': '扫描期间目录出现重复分页或条目，未推断删除；可重新扫描。',
    'SCAN_INCOMPLETE_PAGE': '目录分页未完整闭合，未推断删除；原已收录文件与整理记录保留。',
}


def source_status(source):
    """One bounded source observation; task details still use the existing jobs UI."""
    observation = source.get('observation') or {}
    if not observation:
        return ''
    state = observation.get('latest_state', 'none')
    counts = observation.get('counts') or {}
    lines = [{'none': _t(None, '尚未扫描', 'Not scanned'), 'cancel_requested': _t(None, '已请求取消，等待后台确认', 'Cancel requested, awaiting confirmation')}.get(state, _lbl(state)),
        {'never': _t(None, '未观察范围', 'Scope unobserved'), 'partial': _t(None, '仅已提交部分', 'Partial committed'), 'complete': _t(None, '上次完整扫描', 'Last full scan')}.get(observation.get('coverage'), _t(None, '范围待核对', 'Scope pending')),
        _t(None, '已扫描 %s 项 / 发现 %s 文件 · 已收录 %s', 'Scanned %s / Found %s files · Indexed %s') % (counts.get('scanned', 0),
            counts.get('discovered', 0), observation.get('indexed_count', 0))]
    if observation.get('availability') == 'source_unavailable':
        lines.append(_t(None, '来源离线，保留整理记录', 'Source offline, records kept'))
    elif observation.get('recheck_required'):
        lines.append(_t(None, '观察范围待复核，可重新扫描；播放前仍核验', 'Scope needs recheck; re-verified before play'))
    return ' · '.join(lines)


def _call(action, expected, **body):
    if expected.get('reference_kind') in PATH_KINDS:
        prefix = action_prefix(expected['reference_kind'])
        return call(action.replace('catalog_', prefix, 1),
                    dict(body, **request_scope(expected)), timeout=2)
    return call(action, dict(expected=expected, **body), timeout=2)


def add_directory(expected, parent, context=None):
    import xbmcgui
    binding, invoke = context or _review_context(expected)
    binding.require_current()
    dialog = xbmcgui.Dialog()
    from .pan_accounts import SERVER_PROVIDERS
    name = dialog.input(_t(None, '片库名称', 'Library Name'), defaultt=_t(None, '我的服务器片库', 'My Server Library') if expected['provider'] in dict(SERVER_PROVIDERS) else _t(None, '我的网盘片库', 'My Cloud Library'))
    if not name or not dialog.yesno(_t(None, '索引此目录？', 'Index This Folder?'),
            _t(None, '仅扫描当前目录及其子目录，建立本地索引；不转存、不移动、不删除媒体文件。关闭页面不会取消扫描。', 'Scans only this folder and subfolders to build a local index; never transfers, moves, or deletes media. Closing does not cancel the scan.')):
        return False
    try:
        result = invoke('catalog_add', name=name, parent=parent)
        invoke('catalog_scan', source_id=result['source_id'])
        dialog.ok(_t(None, '已提交后台扫描', 'Background Scan Submitted'), _t(None, '可在“片库索引与任务”查看进度和整理作品；原文件浏览仍可使用。', 'View progress and organize works in "Library Index & Tasks"; direct browsing remains available.'))
        return True
    except (ValueError, OSError, RuntimeError):
        dialog.ok(_t(None, '未确认扫描结果', 'Scan Outcome Unconfirmed'), _t(None, '来源可能已保存，请在片库索引中刷新任务状态。不要重复提交。', 'The source may already be saved; refresh task status in Library Index rather than submitting again.'))
        return False


def _mapping(dialog, item):
    kind = dialog.select(_t(None, '选择描述方式（仅修改本地元数据）', 'Select Mapping Kind (local metadata only)'), [_t(None, '自定义名称', 'Custom Title'), _t(None, '电影 TMDb 编号', 'Movie TMDb ID'), _t(None, '剧集 TMDb 编号', 'TV Series TMDb ID')])
    if kind not in (0, 1, 2):
        return None
    current = item.get('mapping') or {}
    title = dialog.input(_t(None, '显示名称', 'Display Title'), defaultt=current.get('title') or item['file']['name'])
    if not title:
        return None
    value = dict(kind=('custom', 'movie', 'tv')[kind], title=title,
                 tmdb_id=None, season=None, episode=None, version=current.get('version'))
    if kind:
        raw = dialog.input(_t(None, 'TMDb 数字编号（人工描述，不用于自动续播证明）', 'Numeric TMDb ID (manual description only)'))
        if not raw.isdecimal():
            return None
        value['tmdb_id'] = int(raw)
    if kind == 2:
        season = dialog.input(_t(None, '季号（特别篇为 0，未知请取消）', 'Season Number (0 for specials; cancel if unknown)'))
        episode = dialog.input(_t(None, '集号（未知请取消）', 'Episode Number (cancel if unknown)'))
        if not season.isdecimal() or not episode.isdecimal():
            return None
        value['season'], value['episode'] = int(season), int(episode)
    return value


def review_item(dialog, expected, item, source_id=None, context=None, *, candidate_tools=None):
    context = context or _review_context(expected)
    binding, invoke = context
    binding.require_current()
    choice = dialog.select(item['file']['name'], [_t(None, '搜索并选择作品候选', 'Search & Choose Candidate'), _t(None, '查看原文件与建议', 'View Original File & Hint'),
        _t(None, '解除绑定', 'Unbind'), _t(None, '忽略此项', 'Ignore Item'), _t(None, '撤回上次修改', 'Undo Last Edit'), _t(None, '高级：手填编号 / 自定义名称', 'Advanced: Manual ID / Custom Title'), _t(None, '同目录分集整理（逐项预览）', 'Organize Folder Episodes (Preview)'), _t(None, '编辑文件版本备注', 'Edit Version Note'),
        _t(None, '编辑本文件片段（人工观察）', 'Edit File Segments (Manual)'), _t(None, '查看本文件片段与证据', 'View File Segments & Evidence')])
    binding.require_current()
    candidate = None
    if choice in (0, 6):
        candidate = choose_candidate(dialog, item, candidate_tools=candidate_tools)
        if candidate is None:
            return
        if choice == 6:
            return review_group(dialog, expected, item, candidate, source_id=source_id, context=context,
                                candidate_tools=candidate_tools)
        try:
            value = candidate_tools.candidate_mapping(candidate, item)
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
            detail += _t(None, '\n文件名提示 S%02dE%02d（尚未证明作品身份）', '\nFilename hint S%02dE%02d (work identity unverified)') % (evidence[0]['season'], evidence[0]['episode'])
        if item['file'].get('truncated'):
            detail += _t(None, '\n名称或目录显示已截短，原始记录保留。', '\nDisplayed name or path was truncated; original record is kept.')
        dialog.ok(_t(None, '原文件与建议', 'Original File & Hint'), detail)
        return
    elif choice == 9:
        dialog.textviewer(_t(None, '本文件片段 · 不授予自动跳过', 'File Segments · No Auto-Skip'), _segments_description(item.get('segments')))
        return
    elif choice == 8:
        value = _edit_segments(dialog, item)
        if value is None:
            return
        action = 'segments'
    elif choice == 7:
        value = dict(item.get('mapping') or dict(kind='custom', title=item['file']['name'],
            tmdb_id=None, season=None, episode=None, version=None))
        version = dialog.input(_t(None, '版本备注（最多 80 字，不作为续播证明）', 'Version Note (max 80 chars, display only)'), defaultt=value.get('version') or '').strip()
        if len(version) > 80:
            dialog.ok(_t(None, '备注过长', 'Note Too Long'), _t(None, '请缩短到 80 字以内。未修改记录。', 'Shorten to 80 characters or fewer. Record was not modified.'))
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
        file_id=item['file']['id'], expected_revision=item['revision'], action=action, mapping=value))],
        invoke=invoke, scope_check=binding.require_current, profile_root=binding.root())
    if (result and result['complete'] and candidate and candidate['media_kind'] == 'tv' and
            dialog.yesno(_t(None, '继续整理本剧？', 'Organize Rest of This Show?'), _t(None, '本集已保存。只读取同目录逐项建议，不会自动绑定其他文件。', 'Episode saved. Reads per-item proposals from the same folder without auto-binding other files.'))):
        review_group(dialog, expected, item, candidate, source_id=source_id, context=context,
                     candidate_tools=candidate_tools)
    return result


def _candidate_tools_available(dialog, candidate_tools):
    if not all(callable(getattr(candidate_tools, name, None)) for name in
               ('query_hint', 'search', 'candidate_mapping')):
        dialog.ok(_t(None, '候选搜索暂不可用', 'Candidate Search Unavailable'), _t(None, '当前入口未提供作品候选服务；可使用高级手填编号或自定义名称。未修改任何记录。', 'Candidate search is unavailable from this entry; use manual ID or custom title instead. No records modified.'))
        return False
    return True


def choose_candidate(dialog, item, *, candidate_tools=None):
    if not _candidate_tools_available(dialog, candidate_tools):
        return
    query = dialog.input(_t(None, '搜索作品（只发送关键词，不发送私有目录 / 账号）', 'Search Title (sends keywords only, never private paths/accounts)'), defaultt=candidate_tools.query_hint(item['file']['name']))
    if not query:
        return None
    evidence = (item.get('candidates') or [{}])[0]
    try:
        import xbmc
        candidates = candidate_tools.search(query, year=evidence.get('year'), cancelled=xbmc.Monitor().abortRequested)['items']
    except (ValueError, OSError, RuntimeError):
        dialog.ok(_t(None, '候选搜索未完成', 'Candidate Search Incomplete'), _t(None, '可重试或返回使用手动 TMDb 编号。未修改任何记录。', 'Retry or return to enter a manual TMDb ID. No records modified.'))
        return None
    if not candidates:
        dialog.ok(_t(None, '没有找到候选', 'No Candidates Found'), _t(None, '请修改关键词或使用高级手动编号。', 'Adjust your keywords or use manual TMDb ID entry.'))
        return None
    labels = [('%s · %s · %s\n%s\n%s' % (_t(None, '剧集', 'TV') if row['media_kind'] == 'tv' else _t(None, '电影', 'Movie'),
        row['title'], row['year'] or _t(None, '年份未知', 'Unknown year'), row['original_title'], row['basis'])) for row in candidates]
    # Native detailed select supports the same constrained public poster origin.
    try:
        import xbmcgui
        choices = []
        for label, row in zip(labels, candidates):
            choice = xbmcgui.ListItem(label=label)
            if row['poster_path']:
                choice.setArt({'thumb': 'https://image.tmdb.org/t/p/w185' + row['poster_path']})
            choices.append(choice)
        selected = dialog.select(_t(None, '选择候选（尚未确认作品）', 'Select Candidate (not confirmed yet)'), choices, useDetails=True)
    except (AttributeError, TypeError):
        selected = dialog.select(_t(None, '选择候选（尚未确认作品）', 'Select Candidate (not confirmed yet)'), labels)
    return candidates[selected] if 0 <= selected < len(candidates) else None


def _candidate_episode(dialog, candidate):
    from bobbi_core.catalog_review import mapping
    season = dialog.input(_t(None, '明确季号（特别篇为 0；合集 / 多集文件请取消）', 'Season Number (0 for specials; cancel for multi-episode packs)'))
    episode = dialog.input(_t(None, '明确单集编号（未知请取消）', 'Single Episode Number (cancel if unknown)'))
    if not season.isdecimal() or not episode.isdecimal():
        return None
    try:
        return mapping(dict(kind='tv', title=candidate['title'], tmdb_id=candidate['tmdb_id'],
                            season=int(season), episode=int(episode), version=None))
    except ValueError:
        return None


def review_group(dialog, expected, anchor, candidate, source_id=None, start=0, context=None, *, candidate_tools=None):
    context = context or _review_context(expected)
    binding, invoke = context
    binding.require_current()
    if not _candidate_tools_available(dialog, candidate_tools):
        return
    if candidate['media_kind'] != 'tv':
        dialog.ok(_t(None, '请先选择剧集候选', 'Select a TV Candidate First'), _t(None, '电影不生成季集映射。', 'Movies do not generate season/episode mappings.'))
        return
    rows, offset, group, revision = [], start, None, None
    deadline = time.monotonic() + 60
    if start:
        fresh = invoke('catalog_group', file_id=anchor['file']['id'], source_id=source_id, offset=0, limit=5)
        group, revision, source_id = fresh['group_id'], fresh['projection_revision'], fresh['source_id']
    while True:
        if time.monotonic() >= deadline:
            dialog.ok(_t(None, '目录建议未完整读取', 'Folder Proposals Timed Out'), _t(None, '请缩小索引来源并分轮整理，尚未修改记录。', 'Narrow the indexed source or organize in rounds; no records modified.'))
            return
        params = dict(file_id=anchor['file']['id'], offset=offset, limit=5)
        if source_id:
            params['source_id'] = source_id
        if revision is not None:
            params['projection_revision'] = revision
        try:
            result = invoke('catalog_group', **params)
        except ValueError as error:
            if str(error) != 'CATALOG_GROUP_AMBIGUOUS' or source_id is not None:
                raise
            # Overlapping registrations are not evidence of a trusted group.
            # Let the user choose one; core still checks anchor membership.
            sources = invoke('catalog_sources')['items']
            choice = dialog.select(_t(None, '目录被多个来源收录，请明确选择可信来源', 'Folder Indexed by Multiple Sources — Choose One'),
                                   [row['name'] + ' · ' + row['id'][:8] for row in sources])
            if not 0 <= choice < len(sources):
                return
            source_id = sources[choice]['id']
            try:
                result = invoke('catalog_group', **dict(params, source_id=source_id))
            except ValueError as changed:
                if str(changed) != 'CATALOG_SOURCE_UNAVAILABLE':
                    raise
                dialog.ok(_t(None, '所选来源不包含此文件', 'Selected Source Does Not Contain This File'), _t(None, '未扩大整理范围，请返回明确选择收录此文件的来源。', 'Scope unchanged; return and choose the source containing this file.'))
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
            value = candidate_tools.candidate_mapping(candidate, item)
        except ValueError:
            value = None
        suspicious = (not value or item['state'] == 'ambiguous' or item.get('available') is False or
            item['file'].get('truncated') or candidate_tools.query_hint(item['file']['name']).casefold() != candidate_tools.query_hint(anchor['file']['name']).casefold() or
            evidence.get('year') and candidate.get('year') and evidence['year'] != candidate['year'] or
            (item.get('mapping') or {}).get('tmdb_id') not in (None, candidate['tmdb_id']) or
            (item.get('mapping') or {}).get('kind') not in (None, 'custom', 'tv'))
        if not suspicious:
            preselect.append(index)
        proposals.append(value)
        target = _t(None, '需手动明确季集', 'Manual S/E needed') if value is None else 'S%02dE%02d' % (value['season'], value['episode'])
        labels.append(_t(None, '%s → %s %s · 修订 %s%s', '%s → %s %s · rev %s%s') % (item['file']['name'], candidate['title'], target,
            item['revision'], _t(None, ' · 存在疑点，默认未选', ' · Needs review, unselected') if suspicious else ''))
    selected = dialog.multiselect(_t(None, '逐项选择：同目录不证明同作品；排除合集 / 重制版 / 多集文件', 'Select Items: Verify same work; exclude packs & multi-episode files'), labels, preselect=preselect)
    if not selected:
        if following is not None and dialog.yesno(_t(None, '跳过本轮并查看下一轮？', 'Skip Round and View Next Batch?'), _t(None, '本轮未选择任何修改；后续仍逐项核对，每轮最多 100 项。', 'No changes selected in this batch; up to 100 items per round.')):
            return review_group(dialog, expected, anchor, candidate, source_id, start=following, context=context,
                                candidate_tools=candidate_tools)
        return
    edit_selected = dialog.yesno(_t(None, '需要逐项调整季集？', 'Adjust Season/Episode Individually?'), _t(None, '不调整则沿用上方已核对的建议。未知季集的勾选项仍需手动明确；合集 / 多集文件请排除。', 'Choose No to keep the reviewed proposals above. Unknown S/E items still prompt manually.'))
    entries = []
    for index in selected:
        item, value = rows[index], proposals[index]
        if value is None:
            value = _candidate_episode(dialog, candidate)
        elif edit_selected:
            value = _candidate_episode(dialog, candidate)
        if value is not None:
            # A new work/episode proposal changes that description only. Keep
            # each file's independent version note, as single-item and phone
            # review already do; the explicit version editor can clear it.
            value['version'] = (item.get('mapping') or {}).get('version')
            entries.append(dict(name=item['file']['name'], command=dict(file_id=item['file']['id'],
                expected_revision=item['revision'], action='confirm', mapping=value)))
    if entries:
        result = review_entries(dialog, expected, entries, invoke=invoke,
            scope_check=binding.require_current, profile_root=binding.root())
        if result and result['complete'] and following is not None and dialog.yesno(_t(None, '继续下一轮同目录整理？', 'Continue to Next Folder Batch?'),
                _t(None, '本轮真实回执已显示；下一轮重新读取当前修订，不会自动提交。', 'Receipts shown; the next batch re-reads current revisions without auto-submitting.')):
            return review_group(dialog, expected, anchor, candidate, source_id, start=following, context=context,
                                candidate_tools=candidate_tools)
        return result


def _mapping_description(value):
    """Display only; retain the Host's original mapping and review command."""
    if not value:
        return _t(None, '未设置', 'Unset')
    parts = [value.get('title') or _t(None, '未填写名称', 'Untitled'),
             {'tv': _t(None, '剧集', 'TV'), 'movie': _t(None, '电影', 'Movie'), 'custom': _t(None, '自定义名称', 'Custom')}.get(value.get('kind'), _t(None, '类型待核对', 'Unknown kind'))]
    if value.get('tmdb_id') is not None:
        parts.append('TMDb %s' % value['tmdb_id'])
    if value.get('kind') == 'tv':
        season, episode = value.get('season'), value.get('episode')
        parts.append('S%02dE%02d' % (season, episode) if type(season) is int and type(episode) is int else _t(None, '季集未明确', 'S/E unset'))
    parts.append(_t(None, '版本备注 %s', 'Version note %s') % (value.get('version') or _t(None, '未填写', 'None')))
    return ' · '.join(parts)


def _segment_seconds(value):
    return ('%.3f' % (value / 1000)).rstrip('0').rstrip('.')


def _segments_description(value):
    if value is None:
        return _t(None, '未设置片段；未知时不猜测时间范围。', 'No segments set; time ranges are never guessed.')
    lines = [_t(None, '来源：人工观察；时长为人工填写 %s 秒，并非媒体探测结果。', 'Source: manual observation; duration %s s entered manually (not media-probed).') % _segment_seconds(value['duration_ms']),
        _t(None, '记录时间（Unix 秒）：%s', 'Recorded at (Unix s): %s') % value['observed_at'], _t(None, '原文件观察证据：', 'File observation key: ') + value['observation_key'],
        _t(None, '适用状态：', 'Status: ') + (_t(None, '与当前已保存观察匹配', 'Matches current file observation') if value['state'] == 'matched' else _t(None, '文件观察已变或不可用，需重新核对；旧证据保留', 'Observation changed or unavailable; re-verify (old evidence kept)'))]
    lines.extend(_t(None, '%s (%s) · %s–%s 秒', '%s (%s) · %s–%s s') % (_seg_lbl(row['kind']), row['kind'],
        _segment_seconds(row['start_ms']), _segment_seconds(row['end_ms'])) for row in value['items'])
    lines.append(_t(None, '仅保存本文件标注，不自动跳过、不触发下一集；片尾与彩蛋不得重叠。', 'Saves file annotations only without auto-skipping or triggering next episode; outro and stinger must not overlap.'))
    return '\n'.join(lines)


def _edit_segments(dialog, item):
    from bobbi_core.catalog_segments import KINDS, descriptor
    key = item['file'].get('observation_key')
    if type(key) is not str or not re.fullmatch('[0-9a-f]{64}', key):
        dialog.ok(_t(None, '请刷新原文件', 'Refresh Original File'), _t(None, '缺少当前文件观察证据，未提交片段修改。', 'Missing current file observation key; segment edits were not submitted.'))
        return
    saved = item.get('segments')
    choice = dialog.select(_t(None, '编辑本文件片段（所有时间均需人工核对）', 'Edit File Segments (manual verification required)'),
        [_seg_lbl(kind) + ' (' + kind + ')' for kind in KINDS] + [_t(None, '删除一类片段', 'Remove One Segment Type'), _t(None, '清空全部片段', 'Clear All Segments')])
    if choice not in range(6):
        return
    if choice == 5:
        return dict(observation_key=key, duration_ms=None, items=[])
    matched = saved is not None and saved.get('state') == 'matched'
    items = [dict(row) for row in saved['items']] if matched else []
    if choice == 4:
        if not items:
            dialog.ok(_t(None, '没有当前适用片段', 'No Active Segments'), _t(None, '旧观察失效时只可清空，或重新人工填写；不会将旧时间重新绑定。', 'Stale observations can only be cleared or re-entered manually.'))
            return
        selected = dialog.select(_t(None, '删除哪一类片段？', 'Remove Which Segment?'), [_seg_lbl(row['kind']) for row in items])
        if not 0 <= selected < len(items):
            return
        items.pop(selected)
        return dict(observation_key=key, duration_ms=saved['duration_ms'] if items else None, items=items)
    if saved and not matched and not dialog.yesno(_t(None, '旧片段证据已失效', 'Previous Segment Evidence Stale'),
            _t(None, '请重新观察当前文件。本次只保存新填写的这一类片段，其他旧时间不会沿用；可在保存后撤回。', 'Re-observe the current file. Only the newly entered segment will be saved; you can undo after saving.')):
        return
    kind = KINDS[choice]
    prior = next((row for row in items if row['kind'] == kind), {})

    def read(label, value=None):
        raw = dialog.input(label, defaultt=_segment_seconds(value) if value is not None else '').strip()
        if not raw:
            return None
        if not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,3})?', raw):
            raise ValueError('CATALOG_SEGMENTS_INVALID')
        seconds, _, fraction = raw.partition('.')
        return int(seconds) * 1000 + int(fraction.ljust(3, '0') or '0')

    try:
        duration = read(_t(None, '人工观察的本文件总时长（秒，未知请取消）', 'Observed Total File Duration (seconds; cancel if unknown)'), saved['duration_ms'] if matched else None)
        if duration is None:
            return
        start = read(_seg_lbl(kind) + _t(None, '开始（秒，可填 0）', ' Start (seconds, 0 allowed)'), prior.get('start_ms'))
        if start is None:
            return
        end = read(_seg_lbl(kind) + _t(None, '结束（秒）', ' End (seconds)'), prior.get('end_ms'))
        if end is None:
            return
        return descriptor(dict(observation_key=key, duration_ms=duration,
            items=[row for row in items if row['kind'] != kind] + [dict(kind=kind, start_ms=start, end_ms=end)]))
    except ValueError:
        dialog.ok(_t(None, '片段范围无效或重叠', 'Invalid or Overlapping Segment Range'), _t(None, '请填写不超过总时长的有效秒数（最多三位小数）。片尾与彩蛋也不能重叠，未提交修改。', 'Enter valid seconds within total duration (up to 3 decimals). Outro and stinger must not overlap.'))


def _review_context(expected, *, binding=None, rpc=None):
    from .paths import ProfileBinding
    from .runtime import bind_call
    binding = binding or ProfileBinding()
    rpc = rpc or bind_call(binding.root() / 'runtime.json')

    def invoke(action, **body):
        binding.require_current()
        if expected.get('reference_kind') in PATH_KINDS:
            prefix = action_prefix(expected['reference_kind'])
            result = rpc(action.replace('catalog_', prefix, 1),
                dict(body, **request_scope(expected)), timeout=2)
        else:
            result = rpc(action, dict(expected=expected, **body), timeout=2)
        binding.require_current()
        return result

    return binding, invoke


def review_entries(dialog, expected, entries, invoke=None, scope_check=None, profile_root=None):
    """Bounded TV batch coordinator; existing Host remains the sole writer."""
    from bobbi_core.catalog_review import plan
    if invoke is None:
        binding, invoke = _review_context(expected)
        scope_check, profile_root = binding.require_current, binding.root()
    elif profile_root is None:
        from .paths import profile_root as current_root
        profile_root = current_root()
    scope_check = scope_check or (lambda: None)
    scope_check()
    chunks = plan(entries)
    previews, receipts, saved, deadline = [], [], 0, time.monotonic() + 120
    pending_request_id = None
    for chunk in chunks:
        scope_check()
        if time.monotonic() >= deadline:
            dialog.ok(_t(None, '预览已到期限', 'Preview Expired'), _t(None, '请重新预览，尚未提交修改。', 'Preview again; no changes were submitted.'))
            return
        commands = [entry['command'] for entry in chunk['entries']]
        rows = invoke('catalog_preview', commands=commands)['items']
        if len(rows) != len(commands) or any(row['status'] != 'ready' for row in rows):
            dialog.ok(_t(None, '预览包含冲突', 'Preview Contains Conflicts'), _t(None, '原记录已变化或不可用。未提交任何批次，请在当前条目重新核对。', 'The record changed or is unavailable. Nothing was saved; review this item again.'))
            return {'complete': False, 'saved': 0, 'refresh_required': True}
        for entry, row in zip(chunk['entries'], rows):
            action = {'confirm': _t(None, '保存描述', 'Save Mapping'), 'unbind': _t(None, '解除绑定', 'Unbind'), 'ignore': _t(None, '忽略此项', 'Ignore'), 'undo': _t(None, '撤回上次修改', 'Undo'),
                      'supplement': _t(None, '关联补充内容', 'Link Extra'), 'detach_supplement': _t(None, '移除补充内容关联', 'Unlink Extra'), 'segments': _t(None, '保存人工片段', 'Save Segments'),
                      'restore_description': _t(None, '导入人工描述与片段证据', 'Restore Mapping & Segments')}
            previews.append(_t(None, '%s\n记录修订 %s\n修改前描述 %s\n修改后描述 %s\n操作 %s · 整理状态 %s → %s', '%s\nRevision %s\nBefore %s\nAfter %s\nAction %s · State %s → %s') % (
                entry['name'], entry['command']['expected_revision'], _mapping_description(row.get('before')),
                _mapping_description(row.get('after')), action.get(entry['command']['action'], _t(None, '待核对', 'Pending')),
                _lbl(row.get('before_state', 'unknown')), _lbl(row.get('after_state', 'unknown'))))
            if 'after_supplement' in row:
                def relation_label(value):
                    if not value:
                        return _t(None, '无补充关系', 'No extra link')
                    return '%s · %s · %s · %s' % (value['metadata_key'], value['kind'], value['title'],
                        _t(None, '指定文件版本 ', 'File version ') + value['parent_file_id'][:12] if value.get('parent_file_id') else _t(None, '整个作品', 'Whole work'))
                previews[-1] += _t(None, '\n原补充关系 %s\n修改后补充关系 %s', '\nExtra before %s\nExtra after %s') % (
                    relation_label(row.get('before_supplement')), relation_label(row.get('after_supplement')))
            if 'after_segments' in row:
                previews[-1] += _t(None, '\n原片段\n%s\n修改后片段\n%s', '\nSegments before\n%s\nSegments after\n%s') % (
                    _segments_description(row.get('before_segments')), _segments_description(row.get('after_segments')))
    scope_check()
    scope_text = (_t(None, '本次只整理当前登记来源的本地记录。', 'Local records of this registered source only.')
                  if expected.get('reference_kind') else _t(None, '本次只整理当前账号的本地记录。', 'Local records of the current account only.'))
    dialog.textviewer(_t(None, '逐项预览（尚未保存）', 'Item Preview (Not Saved Yet)'), scope_text + '\n\n' + '\n\n'.join(previews))
    if not dialog.yesno(_t(None, '确认分批保存？', 'Save in Batches?'), _t(None, '%s 项将分 %s 批。已保存批次不会因后续冲突自动回滚；每批开始前仍会检查修订。', 'Saves %s items across %s batches. Committed batches do not roll back on later conflicts; revisions are rechecked per batch.') % (len(entries), len(chunks))):
        return
    for number, chunk in enumerate(chunks):
        scope_check()
        if time.monotonic() >= deadline:
            receipts.append(_t(None, '已到本轮等待期限，请重新读取剩余条目并预览。', 'Batch deadline reached; reload remaining items and preview again.'));break
        if number and not dialog.yesno(_t(None, '继续下一批？', 'Continue Next Batch?'), _t(None, '已保存 %s/%s。可停止未开始批次，已保存结果保留。', 'Saved %s/%s. You can stop unstarted batches while keeping saved edits.') % (saved, len(entries))):
            break
        commands = [entry['command'] for entry in chunk['entries']]
        preview = invoke('catalog_preview', commands=commands)['items']
        if len(preview) != len(commands) or any(row['status'] != 'ready' for row in preview):
            receipts.append(_t(None, '后续批次出现冲突，停止提交。', 'Conflict detected in subsequent batch; submission stopped.'));break
        try:
            rows = invoke('catalog_apply', request_id=chunk['request_id'], commands=commands)['items']
            results = dict(enumerate(rows))
        except (ValueError, OSError, RuntimeError):
            # A read-only receipt lookup never repeats a write on timeout.
            try:
                receipt = invoke('catalog_receipt', request_id=chunk['request_id'])
                results = {row['index']: row for row in receipt.get('items', [])}
            except (ValueError, OSError, RuntimeError):
                results = {}
        try:
            scope_check()
        except (ValueError, OSError, RuntimeError):
            # The write may have committed before a profile switch hid its
            # reply. Keep only the original ID under the admission profile;
            # never display its result or redirect its receipt lookup to B.
            if any(index not in results for index in range(len(chunk['entries']))):
                _pending_receipts(expected, request_id=chunk['request_id'], count=len(chunk['entries']),
                                  profile_root=profile_root)
            raise
        complete = True
        for index, entry in enumerate(chunk['entries']):
            state = results.get(index, {}).get('status')
            saved += state == 'applied'
            complete = complete and state == 'applied'
            receipts.append(entry['name'] + ' · ' + {'applied': _t(None, '已保存', 'Saved'), 'conflict': _t(None, '版本冲突', 'Revision conflict'), 'failed': _t(None, '未保存', 'Not saved')}.get(state, _t(None, '提交结果待核对；请读取当前修订人工核对', 'Outcome pending; reload current revision to verify')))
        if not complete:
            if any(index not in results for index in range(len(chunk['entries']))):
                receipts.append(_t(None, '待核对的原提交编号：', 'Pending request ID: ') + chunk['request_id'])
                pending_request_id = chunk['request_id']
                _pending_receipts(expected, request_id=pending_request_id, count=len(chunk['entries']), profile_root=profile_root)
            break
    dialog.textviewer(_t(None, '真实回执 · 已保存 %s/%s', 'Receipts · Saved %s/%s') % (saved, len(entries)), '\n'.join(receipts) + _t(None, '\n未开始批次未提交，不自动回滚此前结果。', '\nUnstarted batches were not submitted; prior commits remain saved.'))
    return dict(saved=saved, total=len(entries), complete=saved == len(entries),
                pending_request_id=pending_request_id)


def _open_catalog(expected, **query):
    """Legacy management URLs enter the sole cursor-based directory renderer."""
    import xbmc
    from .catalog_routes import route, scope_params
    xbmc.executebuiltin('ActivateWindow(Videos,"' + route(
        action='personal_catalog', **scope_params(expected), **query) + '",return)')


def _pending_receipts(expected, request_id=None, count=None, remove=False, profile_root=None):
    """A bounded UI reminder, not a receipt or mutation authority."""
    try:
        import xbmcgui
        from bobbi_core.catalog_query import opaque, scope_key
        if profile_root is None:
            from .paths import profile_root as current_root
            profile_root = current_root()
        window = xbmcgui.Window(10000)
        key = 'Bobbi.Catalog.Pending.' + opaque(str(profile_root), *scope_key(expected))
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


def query_receipt(dialog, expected, request_id=None, context=None):
    """Recover only the original request. Never make a new plan or write."""
    binding, invoke = context or _review_context(expected)
    binding.require_current()
    pending = _pending_receipts(expected, profile_root=binding.root())
    if request_id is None:
        if pending:
            choice = dialog.select(_t(None, '查询待核对的原提交', 'Select Pending Request Receipt'), [row['request_id'] for row in pending])
            if not 0 <= choice < len(pending):
                return
            request_id = pending[choice]['request_id']
        else:
            request_id = dialog.input(_t(None, '原提交编号（仅查询，不重新提交）', 'Original Request ID (read-only lookup)')).strip()
    if type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id):
        return
    try:
        binding.require_current()
        receipt = invoke('catalog_receipt', request_id=request_id)
    except (ValueError, OSError, RuntimeError):
        dialog.ok(_t(None, '原提交仍待核对', 'Receipt Still Pending'), _t(None, '暂未读取到回执，未重新提交。可稍后在当前片库管理中继续查询。', 'Receipt could not be read yet; nothing was resubmitted. Check again later.'))
        return
    rows = receipt.get('items', [])
    lines = [_t(None, '原提交编号：', 'Original Request ID: ') + request_id]
    lines.extend(_t(None, '第 %s 项 · %s', 'Item %s · %s') % (row['index'] + 1,
        {'applied': _t(None, '已保存', 'Saved'), 'conflict': _t(None, '修订冲突', 'Revision conflict'), 'failed': _t(None, '未保存', 'Not saved')}.get(row['status'], _t(None, '待核对', 'Pending'))) for row in rows)
    if not rows:
        lines.append(_t(None, '尚未查到回执，不能据此认定未写入；未重新提交。', 'No receipt found yet (does not prove absence of write); nothing resubmitted.'))
    expected_count = next((row['count'] for row in pending if row['request_id'] == request_id), None)
    if expected_count and {row['index'] for row in rows if row['status'] in ('applied', 'conflict', 'failed')} == set(range(expected_count)):
        binding.require_current()
        _pending_receipts(expected, request_id=request_id, remove=True, profile_root=binding.root())
    dialog.textviewer(_t(None, '原提交回执', 'Original Request Receipt'), '\n'.join(lines))
    return receipt


def _jobs(dialog, expected, context=None):
    context = context or _review_context(expected)
    binding, invoke = context
    binding.require_current()
    offset = 0
    while True:
        result = invoke('catalog_jobs', offset=offset)
        rows = result['items']
        if not rows:
            dialog.ok(_t(None, '暂无后台任务', 'No Background Tasks'), _t(None, '尚未提交目录扫描。', 'No folder scans have been submitted yet.'))
            return
        choice = dialog.select(_t(32086, '扫描任务', 'Scan Tasks'), [
            _t(None, '%s · 已扫描 %d / 已发现 %d%s', '%s · Scanned %d / Discovered %d%s') % (_lbl(r['state']),
                r['counts']['scanned'], r['counts']['discovered'], _t(None, ' · 正在取消', ' · Cancelling') if r['cancel_requested'] and r['state'] in ('queued', 'running') else '')
            for r in rows] + ([_t(None, '下一页', 'Next Page')] if result['next_offset'] is not None else []) + [_t(None, '实时查看本页任务（最长 2 分钟）', 'Watch Current Page Live (up to 2 min)')])
        binding.require_current()
        if choice < 0:
            return
        if choice == len(rows) + int(result['next_offset'] is not None):
            _watch_jobs(expected, offset=offset, context=context)
            continue
        if choice == len(rows) and result['next_offset'] is not None:
            offset = result['next_offset']
            continue
        row = rows[choice]
        if row['state'] in ('running', 'queued') and dialog.yesno(_t(None, '请求取消扫描？', 'Request Scan Cancellation?'), _t(None, '仅停止本次扫描，已有索引和云端文件保留；后台确认停止后才会显示已取消。', 'Stops only this scan while keeping existing index and cloud files; shows Cancelled once confirmed by the worker.')):
            invoke('catalog_cancel', task_id=row['task_id'])
        else:
            dialog.ok(_t(None, '任务状态', 'Task Status'), _lbl(row['state']) + '\n' +
                      _reason_lbl(row['result_summary']))


def watch_preparation(expected=None, dialog=None):
    """Existing 115 authority, separate from native-pan phone/catalog sessions."""
    import xbmcgui
    from bobbi_core.account_scope import validate_snapshot
    dialog = dialog or xbmcgui.Dialog()
    try:
        current = validate_snapshot(call('account_status', {}, timeout=2), authenticated=True)
        if expected is not None and expected != current:
            raise ValueError('ACCOUNT_CHANGED')
        _watch_jobs(current, kind='preparation')
    except (ValueError, OSError, RuntimeError):
        dialog.ok(_t(None, '准备任务暂不可读', 'Preparation Tasks Unavailable'), _t(None, '请检查当前 115 登录和后台状态。未重新登录、创建或重试任何准备任务。', 'Check current 115 sign-in and background service status. No tasks were created or retried.'))


def _watch_jobs(expected, offset=0, kind='scan', context=None):
    """Visible, single-flight observation; closing never cancels a Host job."""
    import xbmc
    import xbmcgui
    progress, monitor = xbmcgui.DialogProgress(), xbmc.Monitor()
    progress.create(_t(None, '任务实时状态 · 返回仅停止查看', 'Live Task Status · Back Stops Viewing Only'), _t(None, '只显示真实已扫描 / 已发现数量；总数未知，不估算完成百分比。', 'Displays actual scanned/discovered counts without guessing percentages.'))
    deadline, delay = time.monotonic() + 120, 5
    try:
        while time.monotonic() < deadline and not progress.iscanceled() and not monitor.abortRequested():
            try:
                if kind == 'preparation':
                    # Read current authority every observation. No pan scope is
                    # substituted for the 115 account's independent generation.
                    from bobbi_core.account_scope import validate_snapshot
                    current = validate_snapshot(call('account_status', {}, timeout=2), authenticated=True)
                    if current != expected:
                        raise ValueError('CATALOG_ACCOUNT_MISMATCH')
                    value = _call('jobs', expected, kind='preparation', offset=offset, limit=5)
                else:
                    value = (context[1]('catalog_jobs', offset=offset, limit=5) if context else
                             _call('catalog_jobs', expected, offset=offset, limit=5))
                rows = value['items']
            except (ValueError, OSError, RuntimeError) as error:
                if str(error) in ('CATALOG_ACCOUNT_MISMATCH', 'CATALOG_SERVICE_CLOSED', 'ACCOUNT_SCOPE_INVALID',
                                  'PROFILE_CHANGED', 'CATALOG_PROFILE_CHANGED', 'RUNTIME_INSTANCE_CHANGED'):
                    progress.update(0, _t(None, '账号或服务已变化，已停止读取。请返回重新选择账号。', 'Account or service changed; stopped reading. Return and reselect your account.'))
                    return
                progress.update(0, _t(None, '暂未取得新状态，后台任务保持原状态。返回不会取消任务。', 'Could not fetch fresh status yet; background tasks continue. Pressing Back does not cancel tasks.'))
                delay = min(30, delay * 2)
            else:
                delay = 5
                lines = []
                for row in rows:
                    counts = row.get('counts') or {}
                    state = (_prep_lbl(row['state']) if kind == 'preparation' else _lbl(row['state']))
                    if row.get('cancel_requested') and row['state'] in ('queued', 'running'):
                        state += _t(None, ' · 已请求取消，等待后台确认', ' · Cancel requested, awaiting confirmation')
                    lines.append(_t(None, '%s · 阶段 %s（不自动重试未知结果）', '%s · Stage %s (no automatic retry)') % (state, row.get('stage', 'unknown')) if kind == 'preparation' else
                                 _t(None, '%s · 已扫描 %s / 已发现 %s', '%s · Scanned %s / Discovered %s') % (state, counts.get('scanned', 0), counts.get('discovered', 0)))
                # The native widget requires a numeric argument. Keep its bar
                # at zero; no invented completion percentage enters the text.
                progress.update(0, '\n'.join(lines or [_t(None, '当前页暂无任务。', 'No tasks on this page.')]) + _t(None, '\n返回只停止查看，不取消后台任务。', '\nPressing Back stops viewing only without cancelling tasks.'))
                if not rows or all(row['state'] not in ('queued', 'running') for row in rows):
                    return
            until = min(deadline, time.monotonic() + delay)
            while time.monotonic() < until and not progress.iscanceled():
                if monitor.waitForAbort(min(.1, until - time.monotonic())):
                    return
    finally:
        progress.close()


def manage_scope(expected, dialog=None, context=None, *, phone_launcher=None):
    """One scoped management entry for native and registered mounted catalogs."""
    import xbmcgui
    context = context or _review_context(expected)
    binding, _ = context
    binding.require_current()
    dialog = dialog or xbmcgui.Dialog()
    choice = dialog.select(_t(32085, '当前片库管理', 'Current Library Management'), [_t(32110, '后台任务', 'Background Tasks'), _t(32111, '实时查看任务', 'Live Task Status'), _t(32112, '手机详细管理', 'Phone Management'),
        _t(32113, '待整理工作台', 'Organize Workbench'), _t(32114, '查询待核对的原提交', 'Check Pending Receipts'), _t(32115, '管理索引来源', 'Manage Indexed Sources')])
    binding.require_current()
    if choice == 0:
        return _jobs(dialog, expected, context=context)
    if choice == 1:
        return _watch_jobs(expected, context=context)
    if choice == 2:
        if not callable(phone_launcher):
            dialog.ok(_t(None, '手机管理暂不可用', 'Phone Management Unavailable'), _t(None, '当前入口未提供手机管理组件；未创建授权。电视片库与原文件浏览仍可使用。', 'Phone management is not wired in this entry; no session was created. TV library browsing remains available.'))
            return
        return phone_launcher(expected)
    if choice == 3:
        return _open_catalog(expected, mode='review')
    if choice == 4:
        return query_receipt(dialog, expected, context=context)
    if choice == 5:
        return manage_sources(expected, dialog, context=context)


def manage_sources(expected, dialog, context=None):
    context = context or _review_context(expected)
    binding, invoke = context
    binding.require_current()
    if expected.get('reference_kind') in PATH_KINDS:
        from .library_ui import open_library
        return open_library(dialog)
    sources = invoke('catalog_sources')['items']
    selected = dialog.select(_t(None, '索引来源（新增来源请在原文件目录操作）', 'Indexed Sources (add new folders while browsing files)'),
        [row['name'] + ('\n' + source_status(row) if source_status(row) else '') for row in sources])
    if not 0 <= selected < len(sources):
        return
    source = sources[selected]
    choice = dialog.select(source['name'], [_t(None, '查看作品', 'View Works'), _t(None, '待整理工作台', 'Organize Workbench'), _t(None, '重新完整扫描', 'Run Full Rescan'), _t(None, '移除此索引来源', 'Remove Indexed Source')])
    binding.require_current()
    if choice in (0, 1):
        return _open_catalog(expected, source_id=source['id'],
                             **(dict(mode='review') if choice == 1 else dict(view='works')))
    if choice == 2:
        invoke('catalog_scan', source_id=source['id'])
        dialog.ok(_t(None, '已提交扫描', 'Scan Submitted'), _t(None, '关闭此页面不影响后台任务。', 'Closing this screen does not interrupt background tasks.'))
    elif choice == 3 and dialog.yesno(_t(None, '移除此索引来源？', 'Remove Indexed Source?'), _t(None, '请先停止扫描。仅移除本机目录登记；网盘文件、观看历史和人工描述保留。', 'Stop active scans first. Removes only the local folder registration; cloud files, history, and manual descriptions are kept.')):
        invoke('catalog_remove', source_id=source['id'])


def manage(scope_check=None):
    import xbmcgui
    from .pan_ui import _status, provider_display_name
    dialog = xbmcgui.Dialog()
    try:
        if scope_check is None:
            from .paths import ProfileBinding
            scope_check = ProfileBinding().require_current
        scope_check()
        accounts = [r for r in _status() if 'list_files' in r['capabilities'] and r['account']['authenticated']]
        scope_check()
        if not accounts:
            from .library_ui import cd2_mounts, open_library
            mounted = bool(cd2_mounts.discover())
            if dialog.yesno(_t(None, '目录索引支持范围', 'Folder Indexing Support Scope'),
                    _t(None, '个人网盘作品索引需要原生登录（115 私盘实验接入，待实机验证）。现有 CD2 本机挂载先在“管理片库来源”中登记，随后在“我的作品片库”选择 CD2 来源并扫描。\n普通本机目录可直接索引；SMB / NFS / WebDAV 目录索引为实验功能，需要完整列表与大小/修改时间。原文件浏览保留；已有挂载无需再次扫码。',
                       'Personal cloud indexing requires native sign-in (115 personal drive experimental). Register existing local CD2 mounts in My Library first, then scan them.\nLocal folders index directly; SMB / NFS / WebDAV indexing is experimental. Direct file browsing remains available.'),
                    yeslabel=(_t(None, '片库与 CD2 索引', 'Library & CD2 Index') if mounted else _t(None, '浏览片库', 'Browse Library')), nolabel=_t(None, '返回', 'Back')):
                scope_check()
                return open_library(dialog)
            return
        selected = dialog.select(_t(None, '选择当前账号的片库', 'Select Account Library'), [provider_display_name(r['provider']) for r in accounts]) if len(accounts) > 1 else 0
        if not 0 <= selected < len(accounts):
            return
        scope_check()
        expected = accounts[selected]['account']
        return _open_catalog(expected, mode='review')
    except (ValueError, OSError, RuntimeError, ImportError):
        dialog.ok(_t(None, '片库管理暂不可用', 'Library Management Unavailable'), _t(None, '请检查服务和当前账号后重试。索引、文件和已保存的修改均保留。', 'Check service and active account, then retry. Index, files, and saved edits are kept.'))


LABELS_EN = {
    'queued': 'Queued',
    'running': 'Scanning',
    'completed': 'Completed',
    'interrupted': 'Interrupted, can rescan',
    'failed': 'Incomplete',
    'canceled': 'Cancelled',
    'unmatched': 'Unmatched',
    'ambiguous': 'Ambiguous identity',
    'proposed': 'Proposed',
    'confirmed': 'Confirmed',
    'ignored': 'Ignored',
    'uncertain': 'Needs verification',
    'unknown': 'Unknown state',
    'suppressed': 'Preparation stopped',
}
PREPARATION_LABELS_EN = dict(LABELS_EN, running='Preparing', completed='Prepared')
SEGMENT_LABELS_EN = {'intro': 'Intro', 'recap': 'Recap', 'outro': 'Outro', 'credits_scene': 'Stinger'}
SCAN_REASONS_EN = {
    'PROFILE_CHANGED': 'Profile switched and previous task stopped; committed records in the original library are kept.',
    'CATALOG_NETWORK_INCOMPLETE': 'Network folder did not return a complete child listing; no deletions inferred.',
    'CATALOG_NETWORK_METADATA_REQUIRED': 'Network folder lacked file size or exact mtime; no deletions inferred.',
    'PAN_INCOMPLETE_PAGE': 'Cloud page returned incomplete item count; no deletions inferred and indexed records are kept.',
    'PAN_PAGE_EXPIRED': 'Folder pagination or total changed mid-scan; no deletions inferred. You can rescan.',
    'SCAN_PAGE_CYCLE': 'Duplicate page or entry cycle detected during scan; no deletions inferred. You can rescan.',
    'SCAN_INCOMPLETE_PAGE': 'Folder pagination did not close cleanly; no deletions inferred and indexed records are kept.',
}


def _t(msg_id, zh_text, en_text):
    from .i18n import tr
    return tr(msg_id, zh_text, en_text)


def _lbl(state):
    from .i18n import is_english
    return (LABELS_EN if is_english() else LABELS).get(state, state)


def _prep_lbl(state):
    from .i18n import is_english
    return (PREPARATION_LABELS_EN if is_english() else PREPARATION_LABELS).get(state, state)


def _seg_lbl(kind):
    from .i18n import is_english
    return (SEGMENT_LABELS_EN if is_english() else SEGMENT_LABELS)[kind]


def _reason_lbl(reason):
    from .i18n import is_english
    return (SCAN_REASONS_EN if is_english() else SCAN_REASONS).get(reason, reason)
