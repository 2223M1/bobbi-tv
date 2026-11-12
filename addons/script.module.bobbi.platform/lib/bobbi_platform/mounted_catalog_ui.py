"""Thin Kodi consumer for the one supported typed CD2 index source."""
from urllib.parse import urlencode
from uuid import uuid4
from hashlib import sha256
from threading import Event, Thread
import time

from .runtime import call

SELECTION = 'bobbi.portable_selection'
MESSAGES = {
    'CATALOG_CURSOR_STALE': '片库已更新，请返回刷新后继续。',
    'CATALOG_RECHECK_INCOMPLETE': '有限检查内未找到原文件，请回原目录选择。',
    'CATALOG_SOURCE_UNAVAILABLE': 'CD2 挂载或来源不可用，原有索引已保留。',
    'CATALOG_AUTHORITY_CHANGED': '挂载已变化，请重新扫描；不会继承旧文件进度。',
    'CATALOG_FILE_CHANGED': '原路径的文件或挂载已变化，请重新扫描后选择。',
    'CATALOG_SOURCE_UNSUPPORTED': '此入口仅支持现有 CD2 本机挂载，不跟随符号链接。',
    'CATALOG_SCAN_BUSY': '已有扫描正在进行，可在扫描进度中查看或取消。',
}


def route(**values):
    return 'plugin://plugin.video.bobbi.library/?' + urlencode(values)


def _wait(action, body, timeout, progress, current):
    """Bounded one-shot IO; workers return data and never operate Kodi UI."""
    finished, result = Event(), {}
    def run():
        try:
            result['value'] = call(action, body, timeout=timeout)
        except Exception as error:
            result['error'] = error
        finally:
            finished.set()
    if progress.iscanceled() or not current():
        raise ValueError('CATALOG_SELECTION_CANCELLED')
    worker = Thread(target=run, name='bobbi-mounted-file-verify', daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout + 1
    while not finished.wait(.1):
        if progress.iscanceled() or not current() or time.monotonic() >= deadline:
            raise ValueError('CATALOG_SELECTION_CANCELLED')
    if progress.iscanceled() or not current():
        raise ValueError('CATALOG_SELECTION_CANCELLED')
    if 'error' in result:
        raise result['error']
    return result['value']


def _reserve(request, source_id, object_id):
    """Reuse the resident selection barrier, never claim native AV ownership."""
    snapshot = call('playback', dict(operation='snapshot'), timeout=2)
    if snapshot.get('adapter') == 'standard':
        # A real, possibly unauthenticated Host scope guards this lifecycle.
        # It is not a CD2 credential and no second cloud login is required.
        account = call('account_status', {}, timeout=2)
        call('playback', dict(operation='select', request_id=request, account=account), timeout=2)
        return dict(adapter='standard', request_id=request)
    identity = 'transport:' + sha256(('mounted:' + source_id + ':' + object_id).encode()).hexdigest()
    selected = call('playback', dict(operation='select', boot_id=snapshot['boot_id'],
        epoch=snapshot['epoch'], request_id=request, selection_identity=identity), timeout=2)
    from bobbi_core.playback_request import context
    return dict(context(selected, request), adapter='native')


def _owner_current(selection):
    snapshot = call('playback', dict(operation='snapshot'), timeout=2)
    desired = snapshot.get('desired') or {}
    if desired.get('request_id') != selection['request_id'] or desired.get('cancelled') is not False:
        return False
    if selection['adapter'] == 'standard':
        return snapshot.get('adapter') == 'standard'
    return all(snapshot.get(key) == selection[key] for key in ('boot_id', 'epoch'))


def _cancel_owner(request):
    # A lost select reply is not retried. Read once to cancel only our own
    # accepted request if present; never cancel a newer owner or global player.
    snapshot = call('playback', dict(operation='snapshot'), timeout=2)
    desired = snapshot.get('desired') or {}
    if desired.get('request_id') != request or desired.get('cancelled'):
        return
    body = dict(operation='cancel', request_id=request)
    if snapshot.get('adapter') != 'standard':
        body.update(boot_id=snapshot['boot_id'], epoch=snapshot['epoch'])
    call('playback', body, timeout=2)


def execute(handle, params, item):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from .catalog_ui import LABELS
    action, source = params.get('action'), params.get('source', '')
    if action == 'mounted_play':
        return play(handle, source, params.get('object', ''))
    try:
        rows = []
        if action == 'mounted_root':
            for entry in call('catalog_mount_sources', {})['items']:
                offline = entry.get('available') is False
                rows.append(item(entry['name'], route(action='mounted_jobs' if offline else 'mounted_browse', source=entry['id']),
                    label2='挂载暂不可用 · 查看扫描任务' if offline else '已检测 CD2 挂载 · 打开时核验目录'))
                if not offline and entry.get('has_jobs'):
                    rows.append(item(entry['name'] + ' · 扫描任务', route(action='mounted_jobs', source=entry['id']),
                        label2='直接查看或请求取消 · 无需读取挂载目录'))
            if not rows:
                xbmcgui.Dialog().ok('CD2 索引片库', '先在“管理片库来源”选择现有 CD2 本机挂载目录。无需重新登录网盘；SMB/WebDAV 仍使用原浏览入口。')
        elif action == 'mounted_scan':
            if xbmcgui.Dialog().yesno('扫描 CD2 来源', '只建立本地索引，不修改网盘文件。路径与文件属性仅用于复核，不提供跨挂载精确续播。'):
                call('catalog_mount_scan', dict(source_id=source))
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            xbmc.executebuiltin('Container.Update(' + route(action='mounted_browse', source=source) + ',replace)')
            return
        elif action == 'mounted_jobs':
            jobs = call('catalog_mount_jobs', dict(source_id=source))['items']
            for job in jobs:
                label = '%s · 已发现 %d 个文件' % (LABELS.get(job['state'], job['state']), job['counts']['discovered'])
                target = route(action='mounted_jobs', source=source)
                if job['state'] in ('queued', 'running'):
                    if job.get('cancel_requested'):
                        label += ' · 已请求取消，等待后台确认'
                    else:
                        label += ' · 选择取消'
                        target = route(action='mounted_cancel', source=source, task=job['task_id'])
                rows.append(item(label, target))
        elif action == 'mounted_cancel':
            call('catalog_mount_cancel', dict(source_id=source, task_id=params.get('task', '')))
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            xbmc.executebuiltin('Container.Update(' + route(action='mounted_jobs', source=source) + ',replace)')
            return
        elif action in ('mounted_browse', 'mounted_search'):
            view = params.get('view', 'works')
            text = params.get('text', '')
            if action == 'mounted_search':
                text = xbmcgui.Dialog().input('搜索当前 CD2 索引', defaultt=text)[:160]
            query = dict(view=view, text=text, sort='name')
            if params.get('parent'):
                query['parent_entity_id'] = params['parent']
            body = dict(source_id=source, query=query)
            if params.get('cursor') and action != 'mounted_search':
                body['cursor'] = params['cursor']
            result = call('catalog_mount_query', body)
            if view == 'works':
                rows.extend([item('扫描 / 更新此来源', route(action='mounted_scan', source=source)),
                    item('扫描进度', route(action='mounted_jobs', source=source)),
                    item('搜索索引', route(action='mounted_search', source=source))])
            for card in result['items']:
                if view == 'files':
                    target = route(action='mounted_play', source=source, object=card['entity_id'])
                    rows.append(item(card['display_title'], target, False,
                        label2='原文件复核后播放 · 路径来源从头播放'))
                else:
                    child = 'seasons' if view == 'works' and card['media_kind'] == 'tv' else 'episodes' if view == 'seasons' else 'files'
                    rows.append(item(card['display_title'], route(action='mounted_browse', source=source,
                        view=child, parent=card['entity_id']), label2='%d 个原文件 · %s' % (card['variant_count'], card['availability'])))
            if result['next_cursor']:
                values = dict(action='mounted_browse', source=source, view=view, text=text,
                    cursor=result['next_cursor'])
                if params.get('parent'):
                    values['parent'] = params['parent']
                rows.append(item('下一页', route(**values), properties={'Bobi.NextPage': 'true'}))
        else:
            raise ValueError('CATALOG_ACTION_INVALID')
        xbmcplugin.setPluginCategory(handle, 'CD2 索引片库')
        xbmcplugin.setContent(handle, 'files')
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (ValueError, OSError, RuntimeError) as error:
        xbmcgui.Dialog().ok('CD2 索引片库', MESSAGES.get(str(error), '操作未完成，索引与原文件均已保留。请返回刷新或使用原目录浏览。'))
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def play(handle, source_id, object_id):
    import xbmc
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
    from .library_ui import registry
    from .libraries import joined_path
    from .kodi import standard_handoff
    request = uuid4().hex
    window = xbmcgui.Window(10000)
    window.setProperty(SELECTION, request)
    progress, monitor = xbmcgui.DialogProgress(), xbmc.Monitor()
    handoff = None
    store = None
    failure = None
    def current():
        return not monitor.abortRequested() and window.getProperty(SELECTION) == request
    try:
        progress.create('正在核验 CD2 原文件', '核对当前挂载与文件，可按返回取消。')
        selection = _reserve(request, source_id, object_id)
        ticket = _wait('catalog_mount_prepare', dict(source_id=source_id, object_id=object_id,
            request_id=request, intent='play'), 28, progress, current)['ticket']
        if ticket != request or not current() or not _owner_current(selection):
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        selected = _wait('catalog_mount_claim', dict(ticket=ticket), 28, progress, current)
        if (selected['source_id'] != source_id or selected['object_id'] != object_id
                or not current() or not _owner_current(selection)):
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        store = registry(xbmcvfs.translatePath)
        source = store.get(source_id)
        url = joined_path(source, selected['relative'])
        def ready():
            if not current() or not _owner_current(selection) or store.get(source_id) != source:
                return False
            valid = _wait('catalog_mount_verify', dict(source_id=source_id, object_id=object_id,
                request_id=request), 8, progress, current)
            return (valid.get('valid') is True and current() and _owner_current(selection)
                    and store.get(source_id) == source and current() and not progress.iscanceled())
        handoff = standard_handoff(selected['identity'], handle, ready=ready)
        result = handoff.submit(selected['identity'], dict(url=url, title=selected['title'], _mounted_path=True))
        if not result['opened']:
            raise ValueError('CATALOG_SELECTION_CANCELLED')
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        if handoff is None or handoff.state in ('selected', 'cancelled'):
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        failure = str(error)
    finally:
        progress.close()
        if handoff is None or handoff.state in ('selected', 'cancelled'):
            for cancel in (
                lambda: call('catalog_mount_cancel_play', dict(source_id=source_id, request_id=request), timeout=2),
                lambda: _cancel_owner(request)):
                try:
                    cancel()
                except (ValueError, OSError, RuntimeError, KeyError, TypeError):
                    pass
        if store is not None:
            store.close()
    if failure is not None and failure != 'CATALOG_SELECTION_CANCELLED':
        xbmcgui.Dialog().ok('CD2 原文件播放', MESSAGES.get(failure, '本次未确认打开原文件；不会自动换源或重复提交。'))
