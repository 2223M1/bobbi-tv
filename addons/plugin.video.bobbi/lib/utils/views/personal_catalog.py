"""Bounded personal-library directories. Cards describe files, never authorize them."""
import hashlib
import json
import re
import sys
from urllib.parse import urlencode


def scope_key(account):
    if account.get('reference_kind') == 'mounted_path':
        checked = {key: account[key] for key in ('reference_kind', 'source_id', 'namespace')}
        return hashlib.sha256(json.dumps(checked, sort_keys=True).encode('utf-8')).hexdigest()
    from bobbi_platform.pan_accounts import scope
    checked = scope(account, authenticated=True)
    return hashlib.sha256(json.dumps(checked, sort_keys=True).encode('utf-8')).hexdigest()


def route(**params):
    return 'plugin://plugin.video.bobbi/?' + urlencode(
        {key: value for key, value in params.items() if value is not None})


def account_for(params, accounts):
    """A cached route cannot silently change to another account of the same provider."""
    matches = [a for a in accounts if a['provider'] == params.get('provider')]
    if len(matches) != 1 or params.get('scope') != scope_key(matches[0]):
        raise ValueError('PAN_ACCOUNT_CHANGED')
    return matches[0]


def scope_params(expected):
    if expected.get('reference_kind') == 'mounted_path':
        return dict(source=expected['source_id'], namespace=expected['namespace'], scope=scope_key(expected))
    return dict(provider=expected['provider'], scope=scope_key(expected))


def mounted_for(params, rpc):
    """Resolve a registered descriptor without turning its old observation into a permit."""
    expected = rpc('catalog_mount_scope', dict(source_id=params['source']))
    if (params.get('namespace') not in (None, expected['namespace'])
            or params.get('scope') not in (None, scope_key(expected))):
        raise ValueError('CATALOG_AUTHORITY_CHANGED')
    return expected


def query_page(rpc, expected, **values):
    if expected.get('reference_kind') == 'mounted_path':
        return rpc('catalog_mount_query', dict(source_id=expected['source_id'],
            namespace=expected['namespace'], **values))
    return rpc('catalog_query', dict(expected=expected, **values))


def decorate(item, card):
    """Public descriptions only, using the existing cache and bounded metadata queue."""
    key = card.get('metadata_key')
    if type(key) is not str or not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', key):
        return
    _, kind, identifier = key.split(':')
    item.setProperty('Bobi.Metadata.Key', kind + ':' + identifier)
    mode = {'season': 'season', 'episode': 'episode'}.get(card['entity_kind'], kind)
    season = card.get('season')
    if kind == 'tv' and mode in ('season', 'episode') and type(season) is int and 0 <= season <= 999:
        item.setProperty('Bobi.Metadata.SeasonKey', 'tv:{}:season:{}'.format(identifier, season))
    from lib.clients.tmdb.frontend_metadata import apply
    data = dict(title=card['display_title'], year=card.get('year'),
                season=card.get('season'), episode=card.get('episode'))
    file_card = card['entity_kind'] == 'file'
    detail = item.getLabel2() if file_card else ''
    try:
        apply(item, int(identifier), mode, data=data)
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
            for prefix in ('Bobi', 'AM6B'):
                item.setProperty(prefix + '.Title.zh', title)
                item.setProperty(prefix + '.Title.en', '')
            item.setProperty('AM6B.Title.original', '')


def manage(params=None, rpc=None):
    import xbmcgui
    from bobbi_platform import catalog_ui
    from bobbi_platform.runtime import call
    from bobbi_platform.pan_accounts import scope
    params, rpc = params or {}, rpc or call
    if not params.get('provider') and not params.get('source'):
        return catalog_ui.manage()
    try:
        expected = (mounted_for(params, rpc) if params.get('source') else account_for(params,
            [scope(row['account'], authenticated=True) for row in rpc('pan_status', {})['providers']
             if row['provider'] != '115' and row['account'].get('authenticated')]))
        if params.get('object_id'):
            values = dict(file_id=params['object_id'])
            if expected.get('reference_kind') == 'mounted_path':
                record = rpc('catalog_mount_item', dict(source_id=expected['source_id'],
                    namespace=expected['namespace'], **values))
            else:
                record = rpc('catalog_item', dict(expected=expected, **values))
            return catalog_ui.review_item(xbmcgui.Dialog(), expected, record)
        mode = params.get('mode')
        if mode in ('scan', 'cancel') and expected.get('reference_kind') == 'mounted_path':
            body = dict(source_id=expected['source_id'], namespace=expected['namespace'])
            if mode == 'scan':
                if not xbmcgui.Dialog().yesno('扫描当前 CD2 来源？', '只建立本机作品索引，不移动或修改网盘文件。'):
                    return
                rpc('catalog_mount_scan', body)
            else:
                rpc('catalog_mount_cancel', dict(body, task_id=params.get('task', '')))
            return catalog_ui._jobs(xbmcgui.Dialog(), expected)
        if mode == 'jobs':
            return catalog_ui._jobs(xbmcgui.Dialog(), expected)
        return catalog_ui.manage_scope(expected)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        xbmcgui.Dialog().ok('片库范围已变化', '请返回重新选择来源。已保存的整理与原文件均保留。')


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
            if row['duration']:
                result[identifier] = min(100, round(100 * row['position'] / row['duration']))
        except (ValueError, TypeError, KeyError):
            continue
    return result


def card_target(card, account):
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
    return route(action='personal_catalog', view=views[kind], parent_entity_id=identifier, **base), True


def execute(params, handle=None, rpc=None, rail_cache=None):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from bobbi_platform.pan_accounts import NAMES, scope
    from bobbi_platform.runtime import call
    handle = int(sys.argv[1]) if handle is None else handle
    rpc = call if rpc is None else rpc
    rows, category = [], '我的作品片库'
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
            item.setProperty('Bobi.Library.Location', detail)
        for key, value in (properties or {}).items():
            item.setProperty(key, str(value))
        rows.append((target, item, folder))
        return item

    try:
        mounted = bool(params.get('source'))
        accounts = [] if mounted else [scope(r['account'], authenticated=True)
                    for r in rpc('pan_status', {})['providers']
                    if r['provider'] != '115' and r['account'].get('authenticated')]
        mounts = []
        if not mounted and not params.get('provider'):
            mounts = rpc('catalog_mount_sources', {})['items']
        if not mounted and not params.get('provider') and len(accounts) == 1 and not mounts:
            params = dict(params, provider=accounts[0]['provider'], scope=scope_key(accounts[0]))
        if not mounted and not params.get('provider'):
            for account in accounts:
                entry(NAMES.get(account['provider'], account['provider']), route(
                    action='personal_catalog', provider=account['provider'], scope=scope_key(account)))
            for source in mounts:
                entry(source['name'] + ' · CD2', route(action='personal_catalog', source=source['id']),
                      detail='复用已有挂载 · 描述保留，播放时复核' if source.get('available') else
                             '挂载暂不可用 · 已有作品和任务仍可查看')
                if source.get('has_jobs'):
                    entry(source['name'] + ' · 扫描任务', route(action='personal_catalog_manage',
                        source=source['id'], mode='jobs'), False, '直接查看或取消，无需读取挂载目录')
            if not accounts and not mounts:
                state = 'auth_required'
                entry('添加或管理个人网盘', route(action='personal_catalog_manage'), False,
                      '原有 CD2、NAS 和本机视频仍可从原目录浏览')
            entry('浏览原文件与已有挂载', 'plugin://plugin.video.bobbi.library/')
            entry('已有聚合片库', route(action='bobi_library'))
        else:
            account = mounted_for(params, rpc) if mounted else account_for(params, accounts)
            presentation_scope = scope_key(account)
            base = dict(action='personal_catalog', **scope_params(account))
            if not params.get('view') and mode != 'rail' and not params.get('search'):
                for label, values in (
                    ('全部作品', dict(view='works', sort='name')),
                    ('最近加入', dict(view='works', sort='recent_added')),
                    ('未匹配原文件', dict(view='files', review_state='unmatched')),
                    ('待确认与纠错', dict(view='files', review_state='proposed')),
                    ('搜索片库', dict(search='true'))):
                    entry(label, route(**base, **values))
                entry('继续观看', route(action='continue_watching_menu'))
                if mounted:
                    entry('扫描 / 更新当前 CD2 来源', route(action='personal_catalog_manage',
                        mode='scan', **scope_params(account)), False)
                entry('整理作品与扫描任务', route(action='personal_catalog_manage', **scope_params(account)), False)
                entry('浏览原文件与已有挂载', 'plugin://plugin.video.bobbi.library/')
                entry('已有聚合片库', route(action='bobi_library'))
            else:
                query = {key: params[key] for key in ('view', 'source_id', 'review_state',
                    'availability', 'media_kind', 'text', 'parent_entity_id', 'sort') if params.get(key)}
                query.setdefault('view', 'works')
                query.setdefault('sort', 'recent_added' if mode == 'rail' else 'name')
                cursor = params.get('cursor')
                cache_key = 'bobi.catalog.rail.' + scope_key(account) + ':' + hashlib.sha256(
                    json.dumps(query, sort_keys=True).encode()).hexdigest()
                if params.get('search') == 'true':
                    text = xbmcgui.Dialog().input('搜索自己的片库', defaultt=params.get('text', ''))
                    if not text.strip():
                        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
                        return
                    query['text'], cursor = text.strip(), None
                try:
                    page = query_page(rpc, account, query=query, cursor=cursor, limit=20)
                except (OSError, RuntimeError, ValueError) as error:
                    if str(error) == 'CATALOG_CURSOR_STALE' and cursor:
                        xbmcgui.Dialog().notification('片库已更新', '已回到第一页，请重新选择。')
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
                availability = {'observed_present': '已收录 · 播放前核验',
                    'observed_absent': '来源未发现此文件', 'source_unavailable': '来源暂不可用',
                    'unverified': '待确认来源'}
                for card in page['items']:
                    target, folder = card_target(card, account)
                    title = card['display_title']
                    detail = availability.get(card.get('availability'), '待确认来源')
                    if card['entity_kind'] != 'file':
                        detail += ' · %d 个文件版本' % card.get('variant_count', 0)
                    else:
                        detail += ' · ' + ('CD2 · 从头播放，不继承旧路径进度' if mounted else
                                          NAMES.get(account['provider'], account['provider']))
                    properties = {'Bobi.CardKey': 'catalog:' + scope_key(account) + ':' + card['entity_id'],
                        'Bobi.File.State': card.get('availability', 'unverified'),
                        'Bobi.Review.State': card.get('review_state', ''),
                        'Bobi.Title.zh': title}
                    if rail and not mounted:
                        properties['node.visible'] = ('String.IsEqual(Window(Home).Property(Bobi.Rail.Scope.%s),%s)'
                            % (account['provider'], presentation_scope))
                    if card['entity_id'] in progress:
                        properties['PercentPlayed'] = progress[card['entity_id']]
                    item = entry(title, target, folder, detail, properties)
                    info = dict(title=title, mediatype={'work': 'tvshow' if card.get('media_kind') == 'tv'
                        else 'movie', 'season': 'season', 'episode': 'episode'}.get(card['entity_kind'], 'video'))
                    for field in ('season', 'episode', 'year'):
                        if type(card.get(field)) is int:
                            info[field] = card[field]
                    item.setInfo('video', info)
                    try:
                        decorate(item, card)
                    except (ImportError, AttributeError, ValueError, TypeError, KeyError, RuntimeError):
                        pass  # Missing public metadata cannot hide a real local file.
                    if card['entity_kind'] == 'file' and hasattr(item, 'addContextMenuItems'):
                        item.addContextMenuItems([('整理这个原文件', 'RunPlugin(' + route(
                            action='personal_catalog_manage', object_id=card['entity_id'],
                            **scope_params(account)) + ')')])
                if page.get('next_cursor') and mode != 'rail':
                    entry('下一页', route(**base, **query, cursor=page['next_cursor']),
                          properties={'Bobi.NextPage': 'true'})
                if not page['items']:
                    state = 'empty'
                    entry('当前筛选没有作品 · 打开整理与扫描', route(
                        action='personal_catalog_manage', **scope_params(account)), False)
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
                       if r['provider'] != '115' and r['account'].get('authenticated')]
            account_for(params, current)
        if xbmc.Monitor().abortRequested():
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            return
        xbmcplugin.setPluginCategory(handle, category)
        xbmcplugin.setContent(handle, 'videos')
        if rail:
            from lib.cinema.frontend_contract import apply_rail_state
            apply_rail_state(rows, state, revision=revision, scope=presentation_scope)
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        if rail:
            from lib.cinema.frontend_contract import apply_rail_state
            rows.clear()
            auth = str(error) in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED', 'PAN_SCOPE_INVALID')
            entry('登录或重新选择网盘' if auth else '片库暂不可用 · 选择重试',
                  route(action='personal_catalog_manage') if auth else
                  route(action='bobi_retry_rail', rail='personal_library'), False)
            apply_rail_state(rows, 'auth_required' if auth else 'error',
                             reason='ACCOUNT_CHANGED' if auth else 'CATALOG_UNAVAILABLE')
            xbmcplugin.addDirectoryItems(handle, rows, len(rows))
            xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
            return
        message = ('账号已变化，请返回片库重新选择。' if str(error) in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED')
                   else '片库暂不可用，原文件、观看记录与已保存的整理结果仍保留。')
        xbmcgui.Dialog().ok('未读取片库', message)
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
