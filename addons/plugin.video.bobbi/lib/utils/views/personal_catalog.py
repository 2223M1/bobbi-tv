"""Bounded personal-library directories. Cards describe files, never authorize them."""
import hashlib
import json
import re
import sys
from bobbi_platform.catalog_routes import route, scope_key, scope_params

FILTER_FIELDS = ('source_id', 'review_state', 'availability', 'media_kind', 'text', 'sort')
from bobbi_core.typed_ref import KINDS as TYPED_KINDS, action_prefix, request_scope
from bobbi_core.server_ref import PROVIDERS as SERVER_PROVIDERS
FILTER_CHOICES = {
    'media_kind': ('作品类型', ((None, '全部类型'), ('movie', '电影'), ('tv', '剧集'), ('unknown', '尚未确认作品'))),
    'review_state': ('整理状态', ((None, '全部状态'), ('unmatched', '待匹配'), ('ambiguous', '身份不明确'),
        ('proposed', '待确认建议'), ('confirmed', '人工确认'), ('ignored', '已忽略'))),
    'availability': ('来源观察', ((None, '全部观察状态'), ('observed_present', '已收录 · 播放前核验'),
        ('observed_absent', '来源未发现此文件'), ('source_unavailable', '来源暂不可用'), ('unverified', '待确认来源'))),
    'sort': ('排序', (('name', '按名称'), ('recent_added', '最近加入'), ('recent_edited', '最近整理'))),
}


def filter_target(expected, query=None, review=False):
    return route(action='personal_catalog_manage', mode='filters', review='true' if review else None,
                 **scope_params(expected), **{key: value for key, value in (query or {}).items()
                    if key in FILTER_FIELDS + ('view', 'parent_entity_id')})


def filter_summary(query):
    labels = [dict(choices).get(query.get(key), '') for key, (_, choices) in _filter_choices().items()
              if query.get(key) and not (key == 'sort' and query[key] == 'name')]
    if query.get('source_id'):
        labels.insert(0, _tr(91551, '已选来源'))
    if query.get('text'):
        text = query['text']
        labels.append(_tr(91552, '关键词：%s') % (text[:24] + ('…' if len(text) > 24 else '')))
    return ' · '.join(labels)


def filters(dialog, params, expected, origin, rpc, scope_check=None):
    """Edit existing query fields, then open one stable scope-bound directory."""
    import xbmc
    from bobbi_core.catalog_query import parameters
    scope_check = scope_check or (lambda: None)
    scope_check()
    mounted = expected.get('reference_kind') in TYPED_KINDS
    selected = {key: params[key] for key in FILTER_FIELDS if params.get(key)}
    selected.setdefault('sort', 'name')
    if mounted:
        selected['source_id'] = expected['source_id']
    source_name = _tr(91553, '当前已登记来源') if mounted else _tr(91551, '已选来源') if selected.get('source_id') else _tr(91554, '当前账号全部来源')
    while True:
        fields = ([] if mounted else ['source_id']) + list(_filter_choices()) + ['text']
        labels = []
        for key in fields:
            if key == 'source_id':
                labels.append(_tr(91555, '目录来源 · %s') % source_name)
            elif key == 'text':
                labels.append(_tr(91556, '关键词 · %s') % (selected.get('text') or _tr(91557, '全部作品 / 原文件 / 版本备注')))
            else:
                title, choices = _filter_choices()[key]
                labels.append(title + ' · ' + dict(choices).get(selected.get(key), choices[0][1]))
        action = dialog.select(_tr(91558, '片库筛选与排序') + (_tr(91559, ' · 当前已登记来源') if mounted else ''),
            labels + [_tr(91560, '应用筛选'), _tr(91561, '清除筛选（保留当前来源）'), _tr(91562, '保存为常用视图')])
        scope_check()
        if action < 0:
            return
        if action == len(fields) + 1:
            selected = {key: value for key, value in selected.items() if key == 'source_id'}
            selected['sort'] = 'name'
            continue
        if action == len(fields) + 2:
            from lib.utils.views.catalog_saved_views import save
            # Cleared fields must not reappear from the original directory URL.
            saved_params = {key: value for key, value in params.items() if key not in FILTER_FIELDS}
            save(dialog, dict(saved_params, **selected), expected, origin, rpc)
            continue
        if action == len(fields):
            # Start this directory at page one. Keep its work/season parent so
            # sorting a file-version page does not jump out to the whole library.
            review = params.get('review') == 'true'
            query = parameters(dict(selected, view=params.get('view') or ('files' if review else 'works'),
                                    parent_entity_id=params.get('parent_entity_id')))
            if origin_is_current(params, expected, origin, rpc):
                target = route(action='personal_catalog', mode='review' if review else None,
                               **scope_params(expected), **query)
                xbmc.executebuiltin('Container.Update("' + target + '")')
            return
        if not 0 <= action < len(fields):
            return
        key = fields[action]
        if key == 'source_id':
            rows = rpc('catalog_sources', dict(expected=expected))['items']
            options = [(None, _tr(91554, '当前账号全部来源'))] + [(row['id'], row['name']) for row in rows]
        elif key == 'text':
            text = dialog.input(_tr(91563, '搜索作品 / 原文件 / 版本备注（最多 160 字）'), defaultt=selected.get('text', '')).strip()
            scope_check()
            if text:
                if len(text) > 160 or re.search(r'[\x00-\x1f\x7f]', text):
                    dialog.ok(_tr(91564, '关键词过长或含控制字符'), _tr(91565, '请使用 160 字以内的关键词。当前筛选保留。'))
                else:
                    selected['text'] = text
            continue
        else:
            options = _filter_choices()[key][1]
        chosen = dialog.select(_tr(91566, '选择目录来源') if key == 'source_id' else (_tr(91567, '选择%s') % _filter_choices()[key][0]),
                               [label for _, label in options])
        scope_check()
        if 0 <= chosen < len(options):
            selected[key] = options[chosen][0]
            if key == 'source_id':
                source_name = options[chosen][1]


def account_for(params, accounts):
    """A cached route cannot silently change to another account of the same provider."""
    matches = [a for a in accounts if a['provider'] == params.get('provider')]
    if len(matches) != 1 or params.get('scope') != scope_key(matches[0]):
        raise ValueError('PAN_ACCOUNT_CHANGED')
    return matches[0]


def typed_action(expected, suffix):
    return action_prefix(expected.get('reference_kind', 'mounted_path')) + suffix


def mounted_for(params, rpc):
    """Resolve a registered descriptor without turning its old observation into a permit."""
    expected = rpc(typed_action(params, 'scope'), dict(source_id=params['source']))
    if (params.get('namespace') not in (None, expected['namespace'])
            or params.get('scope') not in (None, scope_key(expected))):
        raise ValueError('CATALOG_AUTHORITY_CHANGED')
    return expected


def query_page(rpc, expected, **values):
    if expected.get('reference_kind') in TYPED_KINDS:
        return rpc(typed_action(expected, 'query'), dict(request_scope(expected), **values))
    return rpc('catalog_query', dict(expected=expected, **values))


def decorate(item, card, projections=None):
    """Public descriptions only, using the existing cache and bounded metadata queue."""
    if card.get('server_description') is not None:
        from bobbi_core.server_description import checked, text
        try:
            description = checked(card['server_description'])
        except (ValueError, TypeError, KeyError):
            description = None
        if description:
            tag = item.getVideoInfoTag()
            tag.setPlot(text(description))
            if description['year'] is not None:
                tag.setYear(description['year'])
    key = card.get('metadata_key')
    if type(key) is not str or not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', key):
        return
    _, kind, identifier = key.split(':')
    item.setProperty('Bobbi.Metadata.Key', kind + ':' + identifier)
    mode = {'season': 'season', 'episode': 'episode'}.get(card['entity_kind'], kind)
    season = card.get('season')
    if kind == 'tv' and mode in ('season', 'episode') and type(season) is int and 0 <= season <= 999:
        item.setProperty('Bobbi.Metadata.SeasonKey', 'tv:{}:season:{}'.format(identifier, season))
    from lib.clients.tmdb.frontend_metadata import apply
    data = dict(title=card['display_title'], year=card.get('year'),
                season=card.get('season'), episode=card.get('episode'))
    options = {}
    if mode == 'episode' and projections is not None:
        from lib.clients.tmdb.frontend_metadata import episode_projection
        projection_key = (int(identifier), season)
        if projection_key not in projections:
            projections[projection_key] = episode_projection(*projection_key)
        options['projection'] = projections[projection_key]
    file_card = card['entity_kind'] == 'file'
    detail = item.getLabel2() if file_card else ''
    try:
        apply(item, int(identifier), mode, data=data, **options)
    finally:
        if file_card:
            # The skin prefers title properties to Label and original titles to
            # Label2. Keep real file variants and source evidence distinguishable.
            title = card['display_title']
            item.setLabel(title)
            item.setLabel2(detail)
            tag = item.getVideoInfoTag()
            tag.setTitle(title)
            tag.setOriginalTitle('')
            for prefix in ('Bobbi', 'AM6B'):
                item.setProperty(prefix + '.Title.zh', title)
                item.setProperty(prefix + '.Title.en', '')
            item.setProperty('AM6B.Title.original', '')


def origin_is_current(params, expected, origin, rpc):
    """Dialogs may return only to their original directory and account/root."""
    import xbmc
    from bobbi_platform.pan_accounts import scope
    if not origin or xbmc.getInfoLabel('Container.FolderPath') != origin:
        return False
    if expected.get('reference_kind') in TYPED_KINDS:
        mounted_for(dict(params, **scope_params(expected)), rpc)
    else:
        account_for(params, [scope(row['account'], authenticated=True)
            for row in rpc('pan_status', {})['providers']
            if 'provider' in row['account'] and row['account'].get('authenticated')])
    return xbmc.getInfoLabel('Container.FolderPath') == origin


def _profile_rpc(rpc=None):
    """Capture profile/runtime once, before directory IO or modal interaction."""
    from bobbi_platform.paths import ProfileBinding
    from bobbi_platform.runtime import bind_call
    binding = ProfileBinding()
    supplied = rpc is not None
    transport = rpc if supplied else bind_call(binding.root() / 'runtime.json')

    def guarded(action, body, **options):
        binding.require_current()
        result = transport(action, body) if supplied else transport(action, body, **options)
        binding.require_current()
        return result

    return binding, guarded


def manage(params=None, rpc=None):
    import xbmc
    import xbmcgui
    from bobbi_platform import catalog_ui
    from bobbi_platform.pan_accounts import scope
    params = params or {}
    origin = xbmc.getInfoLabel('Container.FolderPath')
    if params.get('mode') in ('view_edit', 'view_default'):
        try:
            from bobbi_platform.runtime import call
            from lib.utils.views.catalog_saved_views import manage as manage_view
            # This local CAS store captures its own profile; deleting/renaming
            # a stale view must remain possible while the Host is unavailable.
            return manage_view(params, rpc or call)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
            xbmcgui.Dialog().ok(_tr(91568, '常用视图未修改'), _tr(91569, '记录已变化，请重新打开后再操作。') if
                str(error) == 'CATALOG_VIEW_CONFLICT' else _tr(91570, '来源或记录暂不可用，可重试、删除或重新保存筛选。'))
            return
    try:
        binding, rpc = _profile_rpc(rpc)
    except (ValueError, OSError, RuntimeError):
        xbmcgui.Dialog().ok(_tr(91571, '片库范围已变化'), _tr(91572, '请返回重新选择来源。已保存的整理与原文件均保留。'))
        return
    if not params.get('provider') and not params.get('source'):
        return catalog_ui.manage(scope_check=binding.require_current)
    try:
        expected = (mounted_for(params, rpc) if params.get('source') else account_for(params,
            [scope(row['account'], authenticated=True) for row in rpc('pan_status', {})['providers']
             if 'provider' in row['account'] and row['account'].get('authenticated')]))
        context = catalog_ui._review_context(expected, binding=binding, rpc=rpc)
        if params.get('mode') == 'filters':
            return filters(xbmcgui.Dialog(), params, expected, origin, rpc, scope_check=binding.require_current)
        if params.get('mode') == 'view_save':
            from lib.utils.views.catalog_saved_views import save
            return save(xbmcgui.Dialog(), params, expected, origin, rpc)
        if params.get('mode') == 'file_facts':
            if expected.get('reference_kind') in TYPED_KINDS:
                page = rpc(typed_action(expected, 'describe'), dict(request_scope(expected), file_ids=[params['object_id']]))
            else:
                page = rpc('catalog_describe', dict(expected=expected, file_ids=[params['object_id']]))
            if not page['items']:
                raise ValueError('CATALOG_FILE_NOT_FOUND')
            if origin_is_current(params, expected, origin, rpc):
                from bobbi_core.catalog_display import media_facts_text
                xbmcgui.Dialog().textviewer(_tr(91573, '本文件信息与依据'), media_facts_text(page['items'][0]))
            return
        if params.get('mode') == 'search':
            text = xbmcgui.Dialog().input(_tr(91574, '搜索自己的片库'), defaultt=params.get('text', '')).strip()
            if text and origin_is_current(params, expected, origin, rpc):
                query = {key: params[key] for key in ('view', 'source_id', 'review_state',
                    'availability', 'media_kind', 'parent_entity_id', 'sort') if params.get(key)}
                query.setdefault('view', 'works')
                query.setdefault('sort', 'name')
                # Only this stable, scope-bound URL enters directory history.
                target = route(action='personal_catalog', text=text, **scope_params(expected), **query)
                xbmc.executebuiltin('Container.Update("' + target + '")')
            return
        if params.get('object_id'):
            values = dict(file_id=params['object_id'])
            if expected.get('reference_kind') in TYPED_KINDS:
                record = rpc(typed_action(expected, 'item'), dict(request_scope(expected), **values))
            else:
                record = rpc('catalog_item', dict(expected=expected, **values))
            if params.get('mode') == 'supplement':
                from lib.utils.views.catalog_supplement_ui import edit
                result = edit(xbmcgui.Dialog(), expected, record, rpc, context=context)
            else:
                try:
                    from lib.clients.tmdb import catalog_candidates
                except ImportError:
                    # The existing manual/receipt UI remains useful when an
                    # optional metadata adapter is unavailable at this entry.
                    catalog_candidates = None
                result = catalog_ui.review_item(xbmcgui.Dialog(), expected, record,
                    source_id=params.get('source_id'), context=context, candidate_tools=catalog_candidates)
            if result:
                if result.get('pending_request_id') and xbmcgui.Dialog().yesno(
                        _tr(91575, '查询原提交回执？'),
                        _tr(91576, '结果尚待核对。只查询原提交编号，不重新写入；也可稍后从片库管理继续查询。')):
                    catalog_ui.query_receipt(xbmcgui.Dialog(), expected, result['pending_request_id'], context=context)
                if origin_is_current(params, expected, origin, rpc):
                    xbmc.executebuiltin('Container.Refresh')
            return result
        mode = params.get('mode')
        if mode in ('scan', 'cancel') and expected.get('reference_kind') in TYPED_KINDS:
            body = request_scope(expected)
            if mode == 'scan':
                if not xbmcgui.Dialog().yesno(_tr(91577, '扫描当前已登记来源？'),
                                              _tr(91578, '只建立本机作品索引，不移动或修改原文件。')):
                    return
                rpc(typed_action(expected, 'scan'), body)
            else:
                rpc(typed_action(expected, 'cancel'), dict(body, task_id=params.get('task', '')))
            return catalog_ui._jobs(xbmcgui.Dialog(), expected, context=context)
        if mode == 'jobs':
            return catalog_ui._jobs(xbmcgui.Dialog(), expected, context=context)
        def launch_phone(account):
            # Optional presentation is composed here, never discovered by the
            # shared platform UI or loaded for ordinary catalog browsing.
            try:
                from lib.clients.stremio.manage_phone import catalog_manage_phone
            except ImportError:
                xbmcgui.Dialog().ok(_tr(91279, '手机管理暂不可用'),
                                    _tr(91579, '手机管理组件未就绪；未创建授权。电视片库与原文件浏览仍可使用。'))
                return
            return catalog_manage_phone(account)
        return catalog_ui.manage_scope(expected, context=context, phone_launcher=launch_phone)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        xbmcgui.Dialog().ok(_tr(91571, '片库范围已变化'), _tr(91572, '请返回重新选择来源。已保存的整理与原文件均保留。'))


def file_progress(items, account, history):
    if not history:
        return {}
    from lib.db.file_history import record
    result = {}
    for item in items:
        identifier = item.get('entity_id')
        if item.get('entity_kind') != 'file' or identifier not in history:
            continue
        try:
            row = record(history[identifier])
            ref = row['file_ref']
            if (ref['id'] != identifier or ref['provider'] != account['provider']
                    or ref['account_id'] != account['account_id']):
                continue
            if item.get('history_key'):
                from bobbi_core.catalog_query import opaque
                # Mirror same_file: a previously known hash must still match;
                # learning a hash for the first time does not invalidate progress.
                same = (ref['size'] == item.get('file_size') if ref.get('fingerprint') is None else
                        item['history_key'] == opaque(ref['id'], ref['size'], ref['fingerprint']))
                if not same:
                    continue  # A known replacement must not display the old file's progress.
            if row['duration']:
                result[identifier] = min(100, round(100 * row['position'] / row['duration']))
        except (ValueError, TypeError, KeyError):
            continue
    return result


def card_target(card, account, query=None):
    identifier, kind = card.get('entity_id'), card.get('entity_kind')
    if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('CATALOG_REPLY_INVALID')
    base = scope_params(account)
    if kind == 'file':
        return route(action='personal_catalog_play', object_id=identifier, **base), False
    views = {'work': 'seasons' if card.get('media_kind') == 'tv' else 'files',
             'season': 'episodes', 'episode': 'files'}
    if kind not in views:
        raise ValueError('CATALOG_REPLY_INVALID')
    filters = {key: value for key, value in (query or {}).items() if key in FILTER_FIELDS}
    return route(action='personal_catalog', view=views[kind], parent_entity_id=identifier,
                 **base, **filters), True


def variants_target(card, account, query=None):
    if card['entity_kind'] not in ('work', 'episode') or card.get('media_kind') not in ('movie', 'tv'):
        return None
    filters = {key: value for key, value in (query or {}).items() if key in FILTER_FIELDS}
    return route(action='personal_catalog', view='files', parent_entity_id=card['entity_id'],
                 **scope_params(account), **filters)


def file_size(value):
    from bobbi_core.catalog_display import size_label
    return size_label(value)


def execute(params, handle=None, rpc=None, rail_cache=None):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from bobbi_platform.pan_accounts import ALL_NAMES as NAMES, scope
    handle = int(sys.argv[1]) if handle is None else handle
    rows, category, content = [], _tr(91580, '我的作品片库'), 'videos'
    mode = params.get('mode', '')
    rail = mode == 'rail'
    state, revision, presentation_scope = 'ready', '', 'local-profile'
    if rail and rail_cache is None:
        try:
            from lib.db.cached import cache as rail_cache
        except ImportError:
            pass  # Optional same-scope fallback, never required for fresh data.

    def entry(label, target, folder=True, detail='', properties=None):
        item = xbmcgui.ListItem(label=label)
        item.setContentLookup(False)
        item.setProperty('IsPlayable', 'false')
        item.setArt({'icon': 'DefaultFolder.png' if folder else 'DefaultVideo.png'})
        if detail:
            item.setLabel2(detail)
            item.setProperty('Bobbi.Library.Location', detail)
        for key, value in (properties or {}).items():
            item.setProperty(key, str(value))
        rows.append((target, item, folder))
        return item

    try:
        if mode == 'views':
            from bobbi_platform.paths import ProfileBinding
            from lib.utils.views.catalog_saved_views import entries
            binding = ProfileBinding()
            entries(entry)
            binding.require_current()
            xbmcplugin.setPluginCategory(handle, _tr(91581, '常用视图'))
            xbmcplugin.setContent(handle, 'files')
            xbmcplugin.addDirectoryItems(handle, rows, len(rows))
            xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
            return
        binding, rpc = _profile_rpc(rpc)
        if (rail and not params.get('provider') and not params.get('source')) or mode == 'saved':
            from lib.utils.views.catalog_saved_views import current, resolve
            saved = current(params.get('view_id') if mode == 'saved' else None)
            if saved is not None:
                expected, saved_query = resolve(saved, rpc)
                params = dict(mode='rail' if rail else '', **scope_params(expected), **saved_query)
                category = saved['title']
            elif mode == 'saved':
                raise ValueError('CATALOG_VIEW_CHANGED')
        mounted = bool(params.get('source'))
        accounts = [] if mounted else [scope(r['account'], authenticated=True)
                    for r in rpc('pan_status', {})['providers']
                    if 'provider' in r['account'] and r['account'].get('authenticated')]
        mounts = []
        if not mounted and not params.get('provider'):
            mounts = rpc('catalog_mount_sources', {})['items']
            mounts += rpc('catalog_local_sources', {})['items']
            mounts += rpc('catalog_network_sources', {})['items']
        if not mounted and not params.get('provider') and len(accounts) == 1 and not mounts:
            params = dict(params, provider=accounts[0]['provider'], scope=scope_key(accounts[0]))
        if not mounted and not params.get('provider'):
            if not rail:
                entry(_tr(91581, '常用视图'), route(action='personal_catalog', mode='views'))
            for account in accounts:
                entry(NAMES.get(account['provider'], account['provider']), route(
                    action='personal_catalog', provider=account['provider'], scope=scope_key(account),
                    mode='owned' if mode == 'owned' else None, metadata_key=params.get('metadata_key') if mode == 'owned' else None,
                    section=params.get('section') if mode == 'owned' else None))
            for source in mounts:
                from bobbi_platform.catalog_ui import source_status
                observed = source_status(source)
                entry(source['name'] + {'local_path': _tr(91582, ' · 本地'), 'network_path': _tr(91583, ' · 网络目录（实验）')}.get(source.get('reference_kind'), _tr(91584, ' · CD2')), route(action='personal_catalog', source=source['id'],
                    reference_kind=source.get('reference_kind') if source.get('reference_kind') != 'mounted_path' else None,
                    section=params.get('section') if mode == 'owned' else None,
                    mode='owned' if mode == 'owned' else None, metadata_key=params.get('metadata_key') if mode == 'owned' else None),
                      detail=observed or (_tr(91585, '复用已有挂载 · 描述保留，播放时复核') if source.get('available') else
                             _tr(91586, '挂载暂不可用 · 已有作品和任务仍可查看')))
                if source.get('has_jobs'):
                    entry(source['name'] + _tr(91587, ' · 扫描任务'), route(action='personal_catalog_manage',
                        source=source['id'], mode='jobs', reference_kind=source.get('reference_kind') if source.get('reference_kind') != 'mounted_path' else None),
                        False, _tr(91588, '直接查看或取消，无需读取挂载目录'))
            if not accounts and not mounts:
                state = 'auth_required'
                entry(_tr(91589, '添加或管理个人网盘'), route(action='personal_catalog_manage'), False,
                      _tr(91590, '原有 CD2、NAS 和本机视频仍可从原目录浏览'))
            entry(_tr(91591, '浏览原文件与已有挂载'), 'plugin://plugin.video.bobbi.library/')
            entry(_tr(91592, '已有聚合片库'), route(action='bobbi_library'))
        else:
            account = mounted_for(params, rpc) if mounted else account_for(params, accounts)
            if mode == 'owned':
                identity = params.get('metadata_key', '')
                if not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', identity):
                    raise ValueError('CATALOG_QUERY_INVALID')
                if mounted:
                    page = rpc(typed_action(account, 'holdings'), dict(request_scope(account), identities=[identity]))
                else:
                    page = rpc('catalog_holdings', dict(expected=account, identities=[identity]))
                owned = page['items'][0]
                if owned.get('state') == 'observed':
                    params = dict(params, view='supplements' if params.get('section') == 'supplements' else
                                  'seasons' if owned['media_kind'] == 'tv' else 'files',
                                  parent_entity_id=owned['entity_id'])
                else:
                    entry(_tr(91593, '当前片库未确认收录此作品') if owned.get('state') == 'not_indexed' else _tr(91594, '当前来源收录状态未知'),
                          route(action='personal_catalog', **scope_params(account)),
                          detail=_tr(91595, '公共作品可继续浏览；可进入片库扫描或整理原文件。'))
                    # Keep the original public page in navigation history.
                    if mounted:
                        mounted_for(dict(params, **scope_params(account)), rpc)
                    else:
                        account_for(params, [scope(r['account'], authenticated=True)
                            for r in rpc('pan_status', {})['providers']
                            if 'provider' in r['account'] and r['account'].get('authenticated')])
                    xbmcplugin.addDirectoryItems(handle, rows, len(rows))
                    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
                    return
            presentation_scope = scope_key(account)
            base = dict(action='personal_catalog', **scope_params(account))
            if params.get('search') == 'true':
                # Legacy search folders are one-shot actions too. End their
                # pending listing before opening the stable results directory.
                if handle >= 0:
                    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
                return manage(dict(params, mode='search', **scope_params(account)), rpc)
            if mode == 'review':
                base['mode'] = 'review'
            if mode == 'review' and not params.get('view'):
                category = _tr(91596, '待整理工作台')
                for state_name, label in (('unmatched', _tr(91597, '未匹配原文件')), ('ambiguous', _tr(91324, '身份不明确')),
                        ('proposed', _tr(91325, '待确认建议')), ('ignored', _tr(91598, '已忽略原文件'))):
                    entry(label, route(**base, view='files', review_state=state_name, source_id=params.get('source_id')))
                entry(_tr(91599, '筛选与排序'), filter_target(account, params, review=True), False)
                entry(_tr(91600, '当前片库管理与原提交查询'), route(action='personal_catalog_manage', **scope_params(account)), False)
            elif not params.get('view') and mode != 'rail' and not params.get('search'):
                for label, values in (
                    (_tr(91601, '全部作品'), dict(view='works', sort='name')),
                    (_tr(91336, '最近加入'), dict(view='works', sort='recent_added')),
                    (_tr(91597, '未匹配原文件'), dict(view='files', review_state='unmatched')),
                    (_tr(91324, '身份不明确'), dict(view='files', review_state='ambiguous')),
                    (_tr(91325, '待确认建议'), dict(view='files', review_state='proposed')),
                    (_tr(91598, '已忽略原文件'), dict(view='files', review_state='ignored'))):
                    entry(label, route(**base, **values, **(dict(mode='review') if values.get('review_state') else {})))
                entry(_tr(91602, '搜索片库'), route(action='personal_catalog_manage', mode='search',
                    source_id=params.get('source_id'), **scope_params(account)), False)
                entry(_tr(91599, '筛选与排序'), filter_target(account, params), False)
                entry(_tr(91581, '常用视图'), route(action='personal_catalog', mode='views'))
                entry(_tr(90200, '继续观看'), route(action='continue_watching_menu'))
                if mounted:
                    entry(_tr(91603, '扫描 / 更新当前已登记来源'), route(action='personal_catalog_manage',
                        mode='scan', **scope_params(account)), False)
                entry(_tr(91604, '整理作品与扫描任务'), route(action='personal_catalog_manage', **scope_params(account)), False)
                entry(_tr(91591, '浏览原文件与已有挂载'), 'plugin://plugin.video.bobbi.library/')
                entry(_tr(91592, '已有聚合片库'), route(action='bobbi_library'))
            else:
                query = {key: params[key] for key in ('view', 'source_id', 'review_state',
                    'availability', 'media_kind', 'text', 'parent_entity_id', 'sort') if params.get(key)}
                query.setdefault('view', 'works')
                query.setdefault('sort', 'recent_added' if mode == 'rail' else 'name')
                summary = filter_summary(query)
                if summary and not rail:
                    category += ' · ' + summary
                # Reuse the skin's season captions and episode rows. Public
                # metadata may give every card the same work title; the native
                # content type supplies the visible season/episode distinction.
                content = {'seasons': 'seasons', 'episodes': 'episodes'}.get(query['view'], 'videos')
                cursor = params.get('cursor')
                cache_key = 'bobbi.catalog.rail.' + scope_key(account) + ':' + hashlib.sha256(
                    json.dumps(query, sort_keys=True).encode()).hexdigest()
                try:
                    page = query_page(rpc, account, query=query, cursor=cursor, limit=20)
                except (OSError, RuntimeError, ValueError) as error:
                    if str(error) == 'CATALOG_CURSOR_STALE' and cursor:
                        xbmcgui.Dialog().notification(_tr(91605, '片库已更新'), _tr(91606, '已回到第一页，请重新选择。'))
                        page = query_page(rpc, account, query=query, cursor=None, limit=20)
                    elif (rail and rail_cache is not None and not cursor
                          and str(error) not in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED', 'PAN_SCOPE_INVALID')):
                        page = rail_cache.get(cache_key)
                        if not isinstance(page, dict) or not page.get('items'):
                            raise
                        state = 'stale'
                    else:
                        raise
                if rail and rail_cache is not None and state != 'stale':
                    from datetime import timedelta
                    try:
                        rail_cache.set(cache_key, page, timedelta(minutes=15))
                    except (OSError, ValueError, RuntimeError):
                        pass  # A cache write cannot discard a fresh directory.
                revision = page.get('projection_revision', '')
                history = {}
                if not mounted and any(row.get('entity_kind') == 'file' for row in page['items']):
                    from lib.db.file_history import FileHistory, KEY
                    try:
                        history = FileHistory().database.get_key_checked(KEY) or {}
                    except (OSError, ValueError, TypeError):
                        pass
                progress = file_progress(page['items'], account, history) if type(history) is dict else {}
                availability = {'observed_present': _tr(91330, '已收录 · 播放前核验'),
                    'observed_absent': _tr(91331, '来源未发现此文件'), 'source_unavailable': _tr(91332, '来源暂不可用'),
                    'unverified': _tr(91333, '待确认来源')}
                projections = {}  # One immutable work/season view per directory render.
                for card in page['items']:
                    target, folder = card_target(card, account, query)
                    if mode == 'review' and card['entity_kind'] == 'file':
                        target = route(action='personal_catalog_manage', object_id=card['entity_id'],
                                       source_id=query.get('source_id'), **scope_params(account))
                    title = card['display_title']
                    detail = availability.get(card.get('availability'), _tr(91333, '待确认来源'))
                    if mode == 'review':
                        detail = _review_label(card.get('review_state')) + ' · ' + detail
                    if card['entity_kind'] != 'file':
                        detail += _tr(91608, ' · %d 个文件版本') % card.get('variant_count', 0)
                    else:
                        detail += ' · ' + ({'local_path': _tr(91609, '本地'), 'network_path': _tr(91610, '网络目录（实验）')}.get(account.get('reference_kind'), 'CD2') + _tr(91611, ' · 从头播放，不继承旧路径进度') if mounted else
                                          NAMES.get(account['provider'], account['provider']))
                        if account.get('provider') in SERVER_PROVIDERS:
                            detail += _tr(91612, ' · 从头播放，历史进度仅供查看')
                        from bobbi_core.catalog_display import file_description
                        descriptions = [file_description(card)]
                        sources = card.get('sources') or []
                        descriptions.extend(row['name'] for row in sources)
                        if card.get('source_total', 0) > len(sources):
                            descriptions.append(_tr(91613, '等 %d 个来源') % card['source_total'])
                        detail += ''.join(' · ' + value for value in descriptions if value)
                        if card.get('truncated'):
                            detail += _tr(91614, ' · 显示已截短，原记录保留')
                    properties = {'Bobbi.CardKey': 'catalog:' + scope_key(account) + ':' + card['entity_id'],
                        'Bobbi.File.State': card.get('availability', 'unverified'),
                        'Bobbi.Review.State': card.get('review_state', ''),
                        'Bobbi.Catalog.MediaKind': card.get('media_kind', 'unknown'),
                        'Bobbi.Title.zh': title}
                    variants = variants_target(card, account, query)
                    if variants:
                        properties['Bobbi.Catalog.Variants'] = variants
                    if card['entity_kind'] in ('file', 'work') and not card.get('supplement'):
                        properties['Bobbi.Catalog.Supplements'] = route(action='personal_catalog', view='supplements',
                            parent_entity_id=card['entity_id'], **scope_params(account))
                    if card.get('supplement'):
                        from lib.utils.views.catalog_supplement_ui import supplement_label
                        supplement = card['supplement']
                        detail += _tr(91615, ' · %s：%s') % (supplement_label(supplement['kind']), supplement['title'])
                        if supplement.get('state') != 'confirmed':
                            detail += _tr(91616, ' · 主作品或版本已变化，请核对关联')
                    if rail and not mounted:
                        properties['node.visible'] = ('String.IsEqual(Window(Home).Property(Bobbi.Rail.Scope.%s),%s)'
                            % ('115.personal' if account['provider'] == '115' else account['provider'], presentation_scope))
                    if card['entity_id'] in progress:
                        properties['PercentPlayed'] = progress[card['entity_id']]
                        detail += _tr(91617, ' · 本文件已观看 %d%%') % progress[card['entity_id']]
                    properties['Bobbi.Catalog.ActionLabel'] = (
                        _tr(91618, '整理原文件') if mode == 'review' and card['entity_kind'] == 'file' else
                        (_tr(91619, '从头播放本文件') if mounted or account.get('provider') in SERVER_PROVIDERS else
                         _tr(91620, '继续播放本文件') if card['entity_id'] in progress else _tr(91621, '播放本文件'))
                        if card['entity_kind'] == 'file' else
                        _tr(91622, '选择文件版本') if card['entity_kind'] == 'episode' or card.get('media_kind') == 'movie' else
                        _tr(91623, '选择分集') if card['entity_kind'] == 'season' else
                        _tr(91624, '选择季集') if card.get('media_kind') == 'tv' else _tr(91625, '查看原文件'))
                    item = entry(title, target, folder, detail, properties)
                    info = dict(title=title, mediatype={'work': {'tv': 'tvshow', 'movie': 'movie'}.get(
                        card.get('media_kind'), 'video'), 'season': 'season', 'episode': 'episode'}.get(card['entity_kind'], 'video'))
                    for field in ('season', 'episode', 'year'):
                        if type(card.get(field)) is int:
                            info[field] = card[field]
                    item.setInfo('video', info)
                    try:
                        decorate(item, card, projections)
                    except (ImportError, AttributeError, ValueError, TypeError, KeyError, RuntimeError):
                        pass  # Missing public metadata cannot hide a real local file.
                    if card['entity_kind'] == 'file' and hasattr(item, 'addContextMenuItems'):
                        item.addContextMenuItems([(_tr(91626, '整理这个原文件'), 'RunPlugin(' + route(
                            action='personal_catalog_manage', object_id=card['entity_id'],
                            source_id=query.get('source_id'), **scope_params(account)) + ')'),
                            (_tr(91627, '查看文件与媒体信息'), 'RunPlugin(' + route(action='personal_catalog_manage',
                                mode='file_facts', object_id=card['entity_id'], **scope_params(account)) + ')'),
                            (_tr(91628, '整理补充内容关联'), 'RunPlugin(' + route(action='personal_catalog_manage',
                                mode='supplement', object_id=card['entity_id'], **scope_params(account)) + ')')])
                    elif variants and hasattr(item, 'addContextMenuItems'):
                        item.addContextMenuItems([(_tr(91622, '选择文件版本'), 'ActivateWindow(Videos,"' + variants + '",return)')])
                    if properties.get('Bobbi.Catalog.Supplements') and hasattr(item, 'addContextMenuItems'):
                        item.addContextMenuItems([(_tr(91629, '我的补充内容'), 'ActivateWindow(Videos,"' + properties['Bobbi.Catalog.Supplements'] + '",return)')])
                    if not rail and hasattr(item, 'addContextMenuItems'):
                        item.addContextMenuItems([(_tr(91599, '筛选与排序'), 'RunPlugin(' + filter_target(
                            account, query, review=mode == 'review') + ')'),
                            (_tr(91562, '保存为常用视图'), 'RunPlugin(' + route(action='personal_catalog_manage',
                                mode='view_save', **scope_params(account), **query) + ')')])
                if page.get('next_cursor') and mode != 'rail':
                    entry(_tr(91255, '下一页'), route(**base, **query, cursor=page['next_cursor']),
                          properties={'Bobbi.NextPage': 'true'})
                if not page['items']:
                    state = 'empty'
                    if query.get('parent_entity_id'):
                        recovery = dict(action='personal_catalog', source_id=query.get('source_id'),
                            **scope_params(account))
                        entry(_tr(91630, '返回当前来源作品'), route(**recovery, view='works', sort='name'),
                              detail=_tr(91631, '此分组暂时没有文件，整理后的作品可能已归入新分组'))
                        entry(_tr(91632, '继续整理当前来源'), route(**recovery, mode='review'))
                    else:
                        entry(_tr(91633, '当前筛选没有作品 · 调整筛选'), filter_target(account, query, review=mode == 'review'), False)
                    if not rail and not query.get('parent_entity_id'):
                        entry(_tr(91562, '保存为常用视图'), route(action='personal_catalog_manage', mode='view_save',
                            **scope_params(account), **query), False)
                try:
                    from lib.clients.tmdb.frontend_metadata import flush
                    flush()
                except (ImportError, AttributeError, ValueError, RuntimeError):
                    pass
        if mounted:
            # Re-read the fixed local namespace after IO; an edited root cannot
            # publish a stale page or silently turn it into the replacement root.
            mounted_for(dict(params, **scope_params(account)), rpc)
        if params.get('provider'):
            # A slow query/history read must not publish the old account's cards
            # after logout or an epoch change. Cached routes remain scope-bound.
            current = [scope(r['account'], authenticated=True)
                       for r in rpc('pan_status', {})['providers']
                       if 'provider' in r['account'] and r['account'].get('authenticated')]
            account_for(params, current)
        binding.require_current()
        if xbmc.Monitor().abortRequested():
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            return
        xbmcplugin.setPluginCategory(handle, category)
        xbmcplugin.setContent(handle, content)
        if rail:
            from lib.cinema.frontend_contract import apply_rail_state
            apply_rail_state(rows, state, revision=revision, scope=presentation_scope)
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        saved_error = str(error).startswith(('CATALOG_VIEW_', 'CATALOG_PARENT_'))
        if rail:
            from lib.cinema.frontend_contract import apply_rail_state
            rows.clear()
            auth = str(error) in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED', 'PAN_SCOPE_INVALID')
            entry(_tr(91634, '常用视图需重新选择来源') if saved_error else _tr(91635, '登录或重新选择网盘') if auth else _tr(91636, '片库暂不可用 · 选择重试'),
                  route(action='personal_catalog', mode='views') if saved_error else route(action='personal_catalog_manage') if auth else
                  route(action='bobbi_retry_rail', rail='personal_library'), False)
            apply_rail_state(rows, 'auth_required' if auth else 'error',
                             reason='ACCOUNT_CHANGED' if auth else 'CATALOG_UNAVAILABLE')
            xbmcplugin.addDirectoryItems(handle, rows, len(rows))
            xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
            return
        message = (_tr(91637, '常用视图仍保留；请从常用视图管理重命名或删除，或在当前来源重新筛选并更新此视图。') if saved_error else
                   _tr(91638, '账号已变化，请返回片库重新选择。') if str(error) in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED')
                   else _tr(91639, '片库暂不可用，原文件、观看记录与已保存的整理结果仍保留。'))
        xbmcgui.Dialog().ok(_tr(91640, '未读取片库'), message)
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def _tr(po_id, zh_text):
    try:
        from bobbi_platform.i18n import tr
        return tr(po_id, zh_text, '', addon_id='plugin.video.bobbi')
    except Exception:
        return zh_text


def _review_label(state_key):
    mapping = {
        'unmatched': (91323, '待匹配'),
        'ambiguous': (91324, '身份不明确'),
        'proposed': (91325, '待确认建议'),
        'confirmed': (91326, '人工确认'),
        'ignored': (91327, '已忽略'),
    }
    if state_key in mapping:
        return _tr(*mapping[state_key])
    from bobbi_platform.catalog_ui import LABELS
    return LABELS.get(state_key, _tr(91607, '待整理'))


def _filter_choices():
    return {
        'media_kind': (_tr(91316, '作品类型'), (
            (None, _tr(91317, '全部类型')),
            ('movie', _tr(91318, '电影')),
            ('tv', _tr(91319, '剧集')),
            ('unknown', _tr(91320, '尚未确认作品')),
        )),
        'review_state': (_tr(91321, '整理状态'), (
            (None, _tr(91322, '全部状态')),
            ('unmatched', _tr(91323, '待匹配')),
            ('ambiguous', _tr(91324, '身份不明确')),
            ('proposed', _tr(91325, '待确认建议')),
            ('confirmed', _tr(91326, '人工确认')),
            ('ignored', _tr(91327, '已忽略')),
        )),
        'availability': (_tr(91328, '来源观察'), (
            (None, _tr(91329, '全部观察状态')),
            ('observed_present', _tr(91330, '已收录 · 播放前核验')),
            ('observed_absent', _tr(91331, '来源未发现此文件')),
            ('source_unavailable', _tr(91332, '来源暂不可用')),
            ('unverified', _tr(91333, '待确认来源')),
        )),
        'sort': (_tr(91334, '排序'), (
            ('name', _tr(91335, '按名称')),
            ('recent_added', _tr(91336, '最近加入')),
            ('recent_edited', _tr(91337, '最近整理')),
        )),
    }
