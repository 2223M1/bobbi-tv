"""Lazy, same-APK Android engine. Existing explicit backend settings always win."""
import json
from pathlib import Path
import time


def request(action, argument=''):
    from .kodi import rpc
    result = rpc('System.BobiAndroid', {'action': action, 'argument': argument})
    if not isinstance(result, dict) or not isinstance(result.get('state'), str):
        raise RuntimeError('ANDROID_HOST_UNAVAILABLE')
    return result


def available():
    try:
        import xbmc
        return xbmc.getCondVisibility('System.Platform.Android') is True
    except (ImportError, AttributeError):
        return False


def configuration(cancelled=lambda: False, clock=time.monotonic, wait=None, call=request):
    if wait is None:
        import xbmc
        monitor = xbmc.Monitor()
        wait = monitor.waitForAbort
    deadline = clock() + 32
    if cancelled():
        raise RuntimeError('ANDROID_ENGINE_CANCELLED')
    status = call('engine_status')
    if status['state'] not in ('RUNNING', 'STARTING'):
        if status['state'] in ('STOPPING', 'STOP_UNCONFIRMED'):
            raise RuntimeError('ANDROID_ENGINE_STOPPING')
        if call('engine_start')['state'] != 'REQUESTED':
            raise RuntimeError('ANDROID_ENGINE_START_DENIED')
    while clock() < deadline:
        if cancelled():
            raise RuntimeError('ANDROID_ENGINE_CANCELLED')
        status = call('engine_status')
        if status['state'] == 'RUNNING':
            path = Path(status.get('config_path', ''))
            if (not path.is_absolute() or path.name != 'engine-backend.json' or
                    path.parent.name != 'no_backup' or not path.is_file() or
                    path.is_symlink() or path.stat().st_size > 4096):
                raise RuntimeError('ANDROID_ENGINE_CONFIG_INVALID')
            result = json.loads(path.read_text(encoding='utf-8'))
            if cancelled():
                raise RuntimeError('ANDROID_ENGINE_CANCELLED')
            return result
        if status['state'] in ('FAILED', 'STOP_UNCONFIRMED', 'UNAVAILABLE', 'UNSUPPORTED'):
            raise RuntimeError('ANDROID_ENGINE_UNAVAILABLE')
        if wait(.15):
            raise RuntimeError('ANDROID_ENGINE_CANCELLED')
    raise RuntimeError('ANDROID_ENGINE_TIMEOUT')


def show(dialog):
    from .bt_setup import adapter_state, adapter_message
    import xbmc
    import xbmcvfs
    existing = adapter_state(xbmcvfs.translatePath)
    if existing is not None:
        dialog.ok('BT 播放', adapter_message(existing))
        return False
    try:
        state = request('engine_status')['state']
        choice = dialog.select('本机 BT', [
            '检查连接' if state == 'RUNNING' else '启动 BT 播放', '停止本机 BT'])
        if choice == 0:
            config = configuration(cancelled=xbmc.Monitor().abortRequested)
            # Use the same control/version validation as the cinema adapter.
            from .bt_setup import _backend_module
            backend = _backend_module().Backend(config)
            try:
                backend.ready(lambda: None)
            finally:
                backend.close()
            dialog.ok('BT 已就绪', '以后选择 BT 片源时会自动启动，无需配对。')
            return True
        if choice == 1:
            if xbmc.Player().isPlaying():
                dialog.ok('请先停止播放', '停止影片后再关闭 BT。')
                return False
            request('engine_stop')
            dialog.ok('正在停止 BT', '下次选择 BT 片源时会重新启动。')
    except (OSError, ValueError, RuntimeError):
        dialog.ok('BT 暂不可用', '请保持波比 TV 在前台，再试一次。已有连接设置没有更改。')
    return False
