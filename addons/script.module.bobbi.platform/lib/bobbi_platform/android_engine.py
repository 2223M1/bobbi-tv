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
        from .android_ui import bundled_host
        return bundled_host()
    except (ImportError, AttributeError):
        return False


def sync_ui_locale(locale_code=None, *, call=None):
    from .i18n import current_locale, normalize_locale
    active_call = request if call is None else call
    target = (normalize_locale(locale_code) if locale_code is not None else current_locale()) or 'zh_cn'
    expected = 'en' if target == 'en_gb' else 'zh'
    reply = active_call('ui_locale', target)
    if not isinstance(reply, dict) or reply.get('state') != 'APPLIED' or reply.get('ui_locale') != expected:
        raise RuntimeError('ANDROID_LOCALE_SYNC_FAILED')
    return reply


def configuration(cancelled=lambda: False, clock=time.monotonic, wait=None, call=None):
    use_default_call = call is None or call is request
    active_call = request if call is None else call
    if wait is None:
        import xbmc
        monitor = xbmc.Monitor()
        wait = monitor.waitForAbort
    deadline = clock() + 32
    if cancelled():
        raise RuntimeError('ANDROID_ENGINE_CANCELLED')
    if use_default_call and available():
        try:
            sync_ui_locale(call=active_call)
        except Exception:
            pass
    status = active_call('engine_status')
    if status['state'] not in ('RUNNING', 'STARTING'):
        if status['state'] in ('STOPPING', 'STOP_UNCONFIRMED'):
            raise RuntimeError('ANDROID_ENGINE_STOPPING')
        if active_call('engine_start')['state'] != 'REQUESTED':
            raise RuntimeError('ANDROID_ENGINE_START_DENIED')
    while clock() < deadline:
        if cancelled():
            raise RuntimeError('ANDROID_ENGINE_CANCELLED')
        status = active_call('engine_status')
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
    from .i18n import tr
    import xbmc
    import xbmcvfs
    existing = adapter_state(xbmcvfs.translatePath)
    if existing is not None:
        dialog.ok(tr(32060, 'BT 播放', 'BT Playback'), adapter_message(existing))
        return False
    try:
        state = request('engine_status')['state']
        choice = dialog.select(
            tr(32061, '本机 BT', 'Local BT Engine'),
            [
                tr(32062, '检查连接', 'Check connection') if state == 'RUNNING'
                else tr(32063, '启动 BT 播放', 'Start BT playback'),
                tr(32064, '停止本机 BT', 'Stop local BT'),
            ],
        )
        if choice == 0:
            config = configuration(cancelled=xbmc.Monitor().abortRequested)
            # Use the same control/version validation as the cinema adapter.
            from .bt_setup import _backend_module
            backend = _backend_module().Backend(config)
            try:
                backend.ready(lambda: None)
            finally:
                backend.close()
            dialog.ok(
                tr(32065, 'BT 已就绪', 'BT Ready'),
                tr(32066, '以后选择 BT 片源时会自动启动，无需配对。',
                   'BT sources will start automatically when selected; no pairing needed.'),
            )
            return True
        if choice == 1:
            if xbmc.Player().isPlaying():
                dialog.ok(
                    tr(32067, '请先停止播放', 'Stop playback first'),
                    tr(32068, '停止影片后再关闭 BT。', 'Stop video playback before turning off BT.'),
                )
                return False
            request('engine_stop')
            dialog.ok(
                tr(32069, '正在停止 BT', 'Stopping BT'),
                tr(None, '下次选择 BT 片源时会重新启动。', 'It will start again next time you select a BT source.'),
            )
    except (OSError, ValueError, RuntimeError):
        dialog.ok(
            tr(None, 'BT 暂不可用', 'BT Unavailable'),
            tr(None, '请保持波比 TV 在前台，再试一次。已有连接设置没有更改。',
               'Keep Bobbi TV in the foreground and try again. Existing connection settings were unchanged.'),
        )
    return False
