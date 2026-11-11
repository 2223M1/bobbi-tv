"""Bounded personal-library directories. Cards describe files, never authorize them."""
import hashlib
import json
import re
import sys
from urllib.parse import urlencode


def scope_key(account):
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
    base = dict(provider=account['provider'], scope=scope_key(account))
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
        accounts = [scope(r['account'], authenticated=True)
                    for r in rpc('pan_status', {})['providers']
                    if r['provider'] != '115' and r['account'].get('authenticated')]
        if not params.get('provider') and len(accounts) == 1:
            params = dict(params, provider=accounts[0]['provider'], scope=scope_key(accounts[0]))
        if not params.get('provider'):
            for account in accounts:
                entry(NAMES.get(account['provider'], account['provider']), route(
                    action='personal_catalog', provider=account['provider'], scope=scope_key(account)))
            if not accounts:
                state = 'auth_required'
                entry('添加或管理个人网盘', route(action='personal_catalog_manage'), False,
                      '原有 CD2、NAS 和本机视频仍可从原目录浏览')
            entry('浏览原文件与已有挂载', 'plugin://plugin.video.bobbi.library/')
            entry('已有聚合片库', route(action='bobi_library'))
        else:
            account = account_for(params, accounts)
            presentation_scope = scope_key(account)
            base = dict(action='personal_catalog', provider=account['provider'], scope=scope_key(account))
            if not params.get('view') and mode != 'rail' and not params.get('search'):
                for label, values in (
                    ('全部作品', dict(view='works', sort='name')),
                    ('最近加入', dict(view='works', sort='recent_added')),
                    ('未匹配原文件', dict(view='files', review_state='unmatched')),
                    ('待确认与纠错', dict(view='files', review_state='proposed')),
                    ('搜索片库', dict(search='true'))):
                    entry(label, route(**base, **values))
                entry('继续观看', route(action='continue_watching_menu'))
                entry('整理作品与扫描任务', route(action='personal_catalog_manage'), False)
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
                    page = rpc('catalog_query', dict(expected=account, query=query, cursor=cursor, limit=20))
                except (OSError, RuntimeError, ValueError) as error:
                    if str(error) == 'CATALOG_CURSOR_STALE' and cursor:
                        xbmcgui.Dialog().notification('片库已更新', '已回到第一页，请重新选择。')
                        page = rpc('catalog_query', dict(expected=account, query=query, cursor=None, limit=20))
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
                if any(row.get('entity_kind') == 'file' for row in page['items']):
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
                    properties = {'Bobi.CardKey': 'catalog:' + scope_key(account) + ':' + card['entity_id'],
                        'Bobi.File.State': card.get('availability', 'unverified'),
                        'Bobi.Review.State': card.get('review_state', ''),
                        'Bobi.Title.zh': title}
                    if rail:
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
                if page.get('next_cursor') and mode != 'rail':
                    entry('下一页', route(**base, **query, cursor=page['next_cursor']),
                          properties={'Bobi.NextPage': 'true'})
                if not page['items']:
                    state = 'empty'
                    entry('当前筛选没有作品 · 打开整理与扫描', route(action='personal_catalog_manage'), False)
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
