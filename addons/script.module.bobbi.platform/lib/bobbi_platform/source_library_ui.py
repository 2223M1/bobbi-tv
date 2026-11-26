"""The existing cinema dialogs own URL entry and cancellable connection checks."""
from threading import Event, Thread
import re
import time
from urllib.parse import urlsplit
from .i18n import is_english, tr


def message(error):
    code = getattr(error, 'code', '')
    # Stable classification only; never URL, response body, token or exception text.
    try:
        import xbmc
        safe = code if isinstance(code, str) and re.fullmatch('[A-Za-z0-9_]{1,80}', code) else type(error).__name__
        xbmc.log('[bobbi] source-library ' + safe, xbmc.LOGWARNING)
    except (ImportError, AttributeError):
        pass
    en = is_english()
    if code == 'SOURCE_URL':
        return ('Enter an HTTPS source-library API URL or JSON catalog URL without embedded credentials.'
                if en else '请填写 HTTPS 源库接口地址，或片库 JSON 网址，不要带账号密码。')
    if code in ('SOURCE_FORMAT', 'RESPONSE_SCHEMA', 'API_REJECTED', 'HTTP_404',
                'INVALID_DOCUMENT', 'REDIRECT'):
        return ('Unsupported source-library URL. Enter a supported source-library API URL or a bobbi-library-v1 JSON URL.'
                if en else '此地址不是支持的源库。请填写源库接口地址或 bobbi-library-v1 片库 JSON 网址。')
    if code in ('HTTP_401', 'HTTP_403', 'AUTH_REAUTHORIZE'):
        return ('The source library refused access. Confirm your permissions with the provider.'
                if en else '源库拒绝了连接，请向提供者确认访问权限。')
    if code in ('HTTP_429', 'AUTH_RETRY_LATER'):
        return ('Too many requests; please try again later. Existing source is kept.'
                if en else '请求太频繁，请稍后重试。原来源保留。')
    if code in ('RESPONSE_LIMIT', 'CATALOG_TOO_LARGE'):
        return ('Catalog is too large. Each direct-link catalog supports up to 2 MB and 2000 items.'
                if en else '片库过大。直链片库每份最多 2 MB、2000 个条目。')
    if code == 'CRYPTO_UNAVAILABLE':
        return ('Required connection component is missing. Repair using the full release package and retry.'
                if en else '缺少连接组件，请用完整安装包修复后重试。')
    return ('Cannot connect right now. Check the URL and network, then retry. Existing source is kept.'
            if en else '暂时连不上，请检查网址和网络后重试。原来源保留。')


def operation(action):
    import xbmc
    import xbmcgui
    from bobbi_core.source_library import SourceLibraryError
    stopped, done, result = Event(), Event(), {}
    deadline = time.monotonic() + 18
    def work():
        try:
            result['value'] = action(deadline, stopped.is_set)
        except Exception as error:
            result['error'] = error
        finally:
            done.set()
    progress = xbmcgui.DialogProgress()
    progress.create(
        tr(32092, '连接源库', 'Connect Source Library'),
        tr(None, '正在读取，可以取消。', 'Reading; press Back to cancel.'),
    )
    monitor = xbmc.Monitor()
    worker = Thread(target=work, name='bobbi-source-check', daemon=True)
    worker.start()
    try:
        while not done.wait(.1):
            if progress.iscanceled() or monitor.abortRequested():
                return None
            if time.monotonic() >= deadline:
                raise SourceLibraryError('DEADLINE')
        if progress.iscanceled() or monitor.abortRequested():
            return None
        if 'error' in result:
            raise result['error']
        return result.get('value')
    finally:
        stopped.set()
        progress.close()


def add(dialog, store, previous=None, *, source_store=None):
    from bobbi_core import source_library as source
    from .source_libraries import capture
    source_store = source_store or (previous.owner if previous is not None else capture())
    starting = source_store.current()
    value = dialog.input(
        tr(32093, '源库接口或片库 JSON 网址', 'Source Library API or JSON URL'),
        defaultt=previous.endpoint if previous else '',
    )
    if not value:
        return False
    try:
        url = source.normalize(value, document=True)
        # Root URLs are catalogue APIs. A document path is fetched as bounded
        # JSON, never guessed as HTML, a script, or an executable repository.
        if urlsplit(url).path:
            imported = operation(lambda deadline, cancelled: source.read_document(
                url, deadline, source_store.cancelled(cancelled)))
            if imported is None:
                return False
            source_store.require_current()
            store.save(imported)
            dialog.ok(
                tr(None, '片库已导入', 'Catalog Imported'),
                (tr(None, '共 %d 个视频，可到“我的片库”打开。', '%d videos imported; open them in "My Library".')
                 % len(imported.items)),
            )
        else:
            endpoint = operation(lambda deadline, cancelled: source_store.check(url, deadline, cancelled))
            if endpoint is None:
                return False
            source_store.require_current()
            if source_store.current() != starting:
                dialog.ok(
                    tr(None, '来源已变化', 'Source Changed'),
                    tr(None, '请重新打开源库设置后再试。', 'Reopen Source Library settings and try again.'),
                )
                return False
            source_store.save(endpoint)
            dialog.ok(
                tr(None, '源库已连接', 'Source Library Connected'),
                tr(None, '现在会一起搜索这套片源。共享目录将在空闲时加载。',
                   'Searches will now include this source library. Shared catalogs load when idle.'),
            )
        return True
    except Exception as error:
        dialog.ok(tr(None, '未能添加源库', 'Could Not Add Source Library'), message(error))
        return False


def manage(dialog, store, source):
    source_store = source.owner
    choice = dialog.select(source.name, [
        tr(None, '检查连接', 'Check Connection'),
        tr(None, '更换网址', 'Change URL'),
        tr(None, '移除来源', 'Remove Source'),
    ])
    if choice == 0:
        try:
            if operation(lambda deadline, cancelled: source_store.check(source.endpoint, deadline, cancelled)):
                dialog.ok(
                    tr(None, '连接正常', 'Connection OK'),
                    tr(None, '搜索影片时会一起查找这套片源。', 'This source library will be queried when searching for titles.'),
                )
        except Exception as error:
            dialog.ok(tr(None, '未能连接源库', 'Could Not Connect Source Library'), message(error))
    elif choice == 1:
        return add(dialog, store, source)
    elif choice == 2 and dialog.yesno(
        tr(None, '移除来源？', 'Remove Source?'),
        tr(None, '此后不再连接这套源库。网盘账号和媒体文件保留。',
           'Stops connecting to this source library. Cloud accounts and media files are kept.'),
    ):
        if source_store.current() != source:
            return False
        source_store.remove()
        return True
    return False
