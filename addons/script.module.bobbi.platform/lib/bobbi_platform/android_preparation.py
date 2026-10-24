"""Optional local CloudDrive connection; no Android mount/root requirement."""
import json
import os
from pathlib import Path
import tempfile


def write_private(path, value):
    path = Path(path)
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('ANDROID_PREPARATION_STORAGE')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.preparation-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def destination(dialog, provider, cancelled=lambda: False):
    from bobbi_core.preparation import scope_path
    path = '/115open'
    while not cancelled():
        rows = sorted((item for item in provider.files(path) if item['directory'] and not item['forbidden']),
                      key=lambda item: item['name'].casefold())[:256]
        choices = [('use', '存到当前文件夹')] if path != '/115open' else []
        if path != '/115open':
            choices.append(('parent', '上一级'))
        choices += [(item['path'], item['name']) for item in rows]
        index = dialog.select('选择存片文件夹', [label for _, label in choices])
        if index < 0 or index >= len(choices):
            return None
        selected = choices[index][0]
        if selected == 'use':
            scope_path(path)
            return path
        if selected == 'parent':
            path = path.rsplit('/', 1)[0]
        else:
            scope_path(selected)
            if selected.rsplit('/', 1)[0] != path:
                raise ValueError('ANDROID_PREPARATION_DIRECTORY')
            path = selected
    return None


def show(dialog):
    import xbmc
    import xbmcgui
    import xbmcvfs
    from bobbi_core.cd2 import CD2
    from .android_engine import request, configuration
    from .runtime import call
    from .account_manager import validate_snapshot
    from .environment import private_path
    from .pairing import Pairing, save
    provider = None
    try:
        if xbmc.Player().isPlaying():
            dialog.ok('请先停止播放', '停止影片后再设置提前存片。')
            return False
        scope = validate_snapshot(call('account_status', {}), authenticated=True)
        info = request('info')
        private = Path(info['private_directory'])
        binary = Path(info['native_directory'])/'libbobbi_ffprobe.so'
        if info['state'] != 'READY' or not binary.is_file() or not private.is_absolute():
            raise ValueError('ANDROID_PREPARATION_TOOLS')
        choice = dialog.select('提前存到 115', ['连接本机 CloudDrive', '如何准备'])
        if choice == 1:
            dialog.ok('准备 CloudDrive', '请先运行 Android 版 CloudDrive，登录与影院相同的 115 账号，并建好存片文件夹。无需 root 或挂载。')
            return False
        if choice != 0:
            return False
        port = dialog.input('本机 CloudDrive 端口', defaultt='19798', type=xbmcgui.INPUT_NUMERIC)
        if not port:
            return False
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError('ANDROID_PREPARATION_PORT')
        endpoint = 'http://127.0.0.1:'+str(int(port))
        username = dialog.input('CloudDrive 登录账号')
        if not username:
            return False
        password = dialog.input('CloudDrive 密码', option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not password:
            return False
        provider = CD2(base=endpoint+'/clouddrive.CloudDriveFileSrv/')
        token = provider.login(username, password)
        identity = provider.provider_identity()
        if identity['account_id'] != scope['account_id']:
            dialog.ok('115 账号不一致', '请让 CloudDrive 和影院登录同一个 115 账号，再试一次。')
            return False
        cancelled = xbmc.Monitor().abortRequested
        folder = destination(dialog, provider, cancelled)
        if not folder:
            return False
        # Explicit setup may start the local engine; ordinary host startup never does.
        backend = configuration(cancelled=cancelled)
        if call('account_status', {}) != scope or cancelled():
            raise ValueError('ANDROID_PREPARATION_ACCOUNT_CHANGED')
        root = private/'preparation-credentials'
        root.mkdir(parents=True, exist_ok=True)
        # Keep previous configuration's credential generation usable until the
        # final config replace. A failed setup never changes a running session.
        generation = Path(tempfile.mkdtemp(prefix='generation-', dir=root))
        write_private(generation/'token', token)
        write_private(generation/'login.json', {'username': username, 'password': password})
        config = dict(schema=1, enabled=True, cd2_endpoint=endpoint,
            cd2_token_file=str(generation/'token'), cd2_login_file=str(generation/'login.json'),
            account=identity['legacy_scope'], destination=folder, ffprobe=str(binary),
            download_capability='GetDownloadUrlPath', torrserver_endpoint=backend['endpoint'],
            playback_transport='http')
        config.update(font_tool=str(Path(info['native_directory'])/'libbobbi_7zip.so'),
            font_native_directory=info['font_directory'], font_cache_directory=info['font_cache_directory'],
            font_work_directory=str(private/'font-work'), font_decoder='android')
        if backend['auth']:
            save(generation/'torrserver.json', Pairing(backend['endpoint'], **backend['auth']))
            config['torrserver_pairing_file'] = str(generation/'torrserver.json')
        candidate = generation/'preparation.json'
        write_private(candidate, config)
        from bobbi_core.preparation_host import configuration as checked
        checked(candidate)
        if call('account_status', {}) != scope or cancelled():
            raise ValueError('ANDROID_PREPARATION_ACCOUNT_CHANGED')
        write_private(private_path(xbmcvfs.translatePath, 'preparation.json'), config)
        dialog.ok('已连接 CloudDrive', '重新打开波比 TV 后生效。观看 BT 时会提前存片，文件确认就绪后才会切到 115。请保持 CloudDrive 运行。')
        return True
    except (OSError, ValueError, RuntimeError, KeyError):
        dialog.ok('暂未连接', '请检查影院 115 登录、本机 CloudDrive 服务、账号和端口。原配置保留。')
        return False
    finally:
        if provider is not None:
            provider.session.close()
