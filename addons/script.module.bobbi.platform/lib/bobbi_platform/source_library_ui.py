"""The existing cinema dialogs own URL entry and cancellable connection checks."""
from threading import Event, Thread
import re
import time
from urllib.parse import urlsplit


def message(error):
    code = getattr(error, 'code', '')
    # Stable classification only; never URL, response body, token or exception text.
    try:
        import xbmc
        safe = code if isinstance(code, str) and re.fullmatch('[A-Za-z0-9_]{1,80}', code) else type(error).__name__
        xbmc.log('[bobbi] source-library ' + safe, xbmc.LOGWARNING)
    except (ImportError, AttributeError):
        pass
    if code == 'SOURCE_URL':
        return '请填写 HTTPS 源库接口地址，或片库 JSON 网址，不要带账号密码。'
    if code in ('SOURCE_FORMAT', 'RESPONSE_SCHEMA', 'API_REJECTED', 'HTTP_404',
                'INVALID_DOCUMENT', 'REDIRECT'):
        return '此地址不是支持的源库。请填写源库接口地址或 bobbi-library-v1 片库 JSON 网址。'
    if code in ('HTTP_401', 'HTTP_403', 'AUTH_REAUTHORIZE'):
        return '源库拒绝了连接，请向提供者确认访问权限。'
    if code in ('HTTP_429', 'AUTH_RETRY_LATER'):
        return '请求太频繁，请稍后重试。原来源保留。'
    if code in ('RESPONSE_LIMIT', 'CATALOG_TOO_LARGE'):
        return '片库过大。直链片库每份最多 2 MB、2000 个条目。'
    if code == 'CRYPTO_UNAVAILABLE':
        return '缺少连接组件，请用完整安装包修复后重试。'
    return '暂时连不上，请检查网址和网络后重试。原来源保留。'


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
    progress.create('连接源库', '正在读取，可以取消。')
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


def add(dialog, store, previous=None):
    from bobbi_core import source_library as source
    starting = source.current()
    value = dialog.input('源库接口或片库 JSON 网址', defaultt=previous.endpoint if previous else '')
    if not value:
        return False
    try:
        url = source.normalize(value, document=True)
        # Root URLs are catalogue APIs. A document path is fetched as bounded
        # JSON, never guessed as HTML, a script, or an executable repository.
        if urlsplit(url).path:
            imported = operation(lambda deadline, cancelled: source.read_document(url, deadline, cancelled))
            if imported is None:
                return False
            store.save(imported)
            dialog.ok('片库已导入', '共 %d 个视频，可到“我的片库”打开。' % len(imported.items))
        else:
            endpoint = operation(lambda deadline, cancelled: source.check(url, deadline, cancelled))
            if endpoint is None:
                return False
            if source.current() != starting:
                dialog.ok('来源已变化', '请重新打开源库设置后再试。')
                return False
            source.save(endpoint)
            dialog.ok('源库已连接', '现在会一起搜索这套片源。共享目录将在空闲时加载。')
        return True
    except Exception as error:
        dialog.ok('未能添加源库', message(error))
        return False


def manage(dialog, store, source):
    from bobbi_core import source_library
    choice = dialog.select(source.name, ['检查连接', '更换网址', '移除来源'])
    if choice == 0:
        try:
            if operation(lambda deadline, cancelled: source_library.check(source.endpoint, deadline, cancelled)):
                dialog.ok('连接正常', '搜索影片时会一起查找这套片源。')
        except Exception as error:
            dialog.ok('未能连接源库', message(error))
    elif choice == 1:
        return add(dialog, store, source)
    elif choice == 2 and dialog.yesno('移除来源？', '此后不再连接这套源库。网盘账号和媒体文件保留。'):
        source_library.remove()
        return True
    return False
