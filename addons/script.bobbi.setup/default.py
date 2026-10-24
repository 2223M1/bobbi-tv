"""Remote-friendly, repeatable setup. Account/installation gates stay honest."""
import xbmc
import xbmcgui
import xbmcvfs
from bobbi_platform.capabilities import probe
from bobbi_platform.environment import load_config, private_path, save_config
from bobbi_platform.kodi import rpc, standard_handoff
from bobbi_platform.playback import selected_identity
from bobbi_platform.pairing import load as load_pairing, save as save_pairing
from bobbi_platform.pairing import from_export, engine_document
from bobbi_platform.torrserver import TorrServerClient, TorrServerError, Cancelled
from bobbi_platform.onboarding import steps, summary, engine_message


def existing_backend_status():
    from bobbi_platform.bt_setup import adapter_status
    return adapter_status(xbmcvfs.translatePath, cancelled=xbmc.Monitor().abortRequested)


def existing_backend_state():
    from bobbi_platform.bt_setup import adapter_state
    return adapter_state(xbmcvfs.translatePath)


def helper_state(path):
    from bobbi_platform.bt_setup import helper_state as configured_state
    return configured_state(xbmcvfs.translatePath, path)


def show_existing_backend(dialog, state):
    from bobbi_platform.bt_setup import adapter_message
    dialog.ok('现有 BT 后台', adapter_message(state))


def helper_status(path):
    existing = existing_backend_status()
    if existing is not None:
        return existing
    try:
        pairing = load_pairing(path)
        if pairing is None:
            return 'not_paired'
        TorrServerClient(engine_document(pairing)).ready(cancelled=xbmc.Monitor().abortRequested)
        return 'ready'
    except ValueError:
        return 'invalid'
    except TorrServerError:
        return 'offline'


def pair_helper(dialog, path):
    existing = existing_backend_state()
    if existing is not None:
        existing = existing_backend_status() or existing
        show_existing_backend(dialog, existing)
        return existing
    choice = dialog.select('设置 BT 播放', [
        'Android 助手配对',
        '使用说明',
        '安装 CoreELEC BT 后台',
        '导入助手配对文件',
        '重新检查连接',
    ])
    if choice in (0, 2, 3):
        # Another entry may have configured the cinema adapter while this
        # selector was open. Do not create a second pairing or engine then.
        existing = existing_backend_state()
        if existing is not None:
            show_existing_backend(dialog, existing)
            return
    if choice == 0:
        from bobbi_platform.pair_code import exchange
        code = dialog.input('助手配对码（六位数字）', type=xbmcgui.INPUT_NUMERIC)
        if not code:
            return
        existing = existing_backend_state()
        if existing is not None:
            show_existing_backend(dialog, existing)
            return
        try:
            pairing = exchange(code)
            TorrServerClient(engine_document(pairing)).ready(cancelled=xbmc.Monitor().abortRequested)
            existing = existing_backend_state()
            if existing is not None:
                show_existing_backend(dialog, existing)
                return
            save_pairing(path, pairing)
            dialog.ok('助手已连接', '以后打开助手并启动后台，就可以使用 BT 片源。')
        except (ValueError, OSError, TorrServerError):
            dialog.ok('配对未完成', '请打开助手，获取新的配对码后重试。原有配对保留。')
    elif choice == 1:
        dialog.ok('BT 播放说明', '看 BT 片源需要连接下载后台。CoreELEC 可在这里安装，Android 需另配兼容的本机助手。\n'
                  '只看 115 或本地 / NAS 片库，可以跳过。')
    elif choice == 2:
        from bobbi_platform.native_engine import install
        if xbmc.Player().isPlaying():
            dialog.ok('请先停止播放', '停止影片后再安装 BT 后台。')
            return
        if not dialog.yesno('安装 BT 后台？', '需下载约 63 MB，仅在本机运行。不改 CD2 或系统服务。'):
            return
        progress = xbmcgui.DialogProgress()
        progress.create('安装 BT 后台', '正在下载，可随时取消。')
        try:
            monitor = xbmc.Monitor()
            # The confirmation/progress dialog may outlive the initial check.
            # Recheck at the final effect, not only when entering this menu.
            existing = existing_backend_state()
            if existing is not None:
                progress.close()
                show_existing_backend(dialog, existing)
                return
            install(cancelled=lambda: monitor.abortRequested() or progress.iscanceled(), progress=progress.update)
            progress.close()
            dialog.ok('BT 后台已安装', '稍后选择“重新检查连接”。若仍未启动，请重启 Kodi。')
        except (ValueError, OSError):
            dialog.ok('安装未完成', '此后台需要 ARM 版 CoreELEC，并能连接 GitHub。请检查网络后重试，网盘与 NAS 仍可使用。')
        finally:
            progress.close()
    elif choice == 3:
        selected = dialog.browse(1, '选择助手导出的配对文件', 'files', mask='.json')
        if not selected:
            return
        existing = existing_backend_state()
        if existing is not None:
            show_existing_backend(dialog, existing)
            return
        stream = xbmcvfs.File(selected)
        try:
            raw = stream.readBytes(4097)
        finally:
            stream.close()
        try:
            pairing = from_export(bytes(raw))
            TorrServerClient(engine_document(pairing)).ready(cancelled=xbmc.Monitor().abortRequested)
            existing = existing_backend_state()
            if existing is not None:
                show_existing_backend(dialog, existing)
                return
            save_pairing(path, pairing)
        except Cancelled:
            return
        except TorrServerError as error:
            dialog.ok('尚未连接', engine_message(error.code) + '\n原有配对没有更改。')
            return
        except ValueError:
            dialog.ok('配对文件不可用', '请使用这台盒子上的 bobbi 助手导出的文件。原有配对没有更改。')
            return
        dialog.ok('助手已连接', '可以返回选片。配对文件含登录信息，请勿分享给别人。')
    elif choice == 4:
        state = helper_status(path)
        if state.startswith('adapter_'):
            show_existing_backend(dialog, state)
            return state
        dialog.ok('连接检查', '助手已连接，可以选择视频试播。' if state == 'ready'
                  else '未连接。请先打开助手并启动后台；重装过助手则需重新配对。')
        return state


def main():
    import sys
    dialog = xbmcgui.Dialog()
    if len(sys.argv) > 1 and sys.argv[1] == 'cloud':
        from bobbi_platform.cloud_hub import show
        show(dialog)
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'diagnostics':
        from bobbi_platform.diagnostics_ui import show
        show(dialog)
        return
    path = private_path(xbmcvfs.translatePath, 'config.json')
    pair_path = private_path(xbmcvfs.translatePath, 'helper-pairing.json')
    config = load_config(path)
    if len(sys.argv) > 1 and sys.argv[1] == 'libraries':
        from bobbi_platform.library_ui import manage
        manage(config['library_root'])
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'updates':
        show_updates(dialog)
        return
    system = 'android' if xbmc.getCondVisibility('System.Platform.Android') else 'kodi'
    capabilities = probe(rpc, system)
    helper = helper_state(pair_path)
    while not xbmc.Monitor().abortRequested():
        from bobbi_platform.library_ui import registry
        library_store = None
        try:
            library_store = registry(xbmcvfs.translatePath)
            library_count = len(library_store.sources())
        except (ValueError, OSError, RuntimeError):
            library_count = None
        finally:
            if library_store is not None:
                library_store.close()
        rows = steps(capabilities, config['library_root'], helper, library_count)
        choice = dialog.select('影院设置', [label for _, label in rows])
        if choice < 0:
            return
        action = rows[choice][0]
        if action == 'check':
            capabilities = probe(rpc, system)
            dialog.ok('播放器检查', summary(capabilities))
        elif action == 'helper':
            helper = pair_helper(dialog, pair_path) or helper_state(pair_path)
        elif action == 'library':
            from bobbi_platform.library_ui import manage
            if manage(config['library_root']):
                return
        elif action == 'test':
            if not capabilities['standard_playback']:
                dialog.ok('先检查播放器', summary(capabilities))
                continue
            if xbmc.Player().isPlaying():
                dialog.ok('当前正在播放', '请先手动停止，再开始测试。')
                continue
            video = dialog.browse(1, '选择视频试播', 'video',
                mask='.mkv|.mp4|.m4v|.mov|.avi|.webm|.ts|.m2ts', defaultt=config['library_root'])
            if video:
                identity = selected_identity(video)
                standard_handoff(identity, -1).submit(identity, {'url': video, 'title': 'bobbi 播放测试'})
                return  # Do not reopen setup over a newly started video.
        elif action == 'language':
            dialog.ok('原声与中文字幕', '下一页进入“语言”，将音轨首选语言设为“原始语言”，字幕首选语言设为“中文”。')
            xbmc.executebuiltin('ActivateWindow(playersettings)')
            return
        elif action == 'cloud':
            from bobbi_platform.cloud_hub import show
            if show(dialog):
                return
        elif action == 'catalog':
            import xbmcaddon
            from bobbi_core.project_metadata import tmdb_key, ATTRIBUTION
            addon = xbmcaddon.Addon('plugin.video.bobbi')
            choice = dialog.select('影视海报与搜索', [
                '影视资料服务 · ' + ('已配置' if tmdb_key() else '未配置'),
                '搜索与高级设置'])
            if choice == 0:
                from metadata_credits import MetadataCredits
                credits = MetadataCredits('tmdb-attribution.xml', xbmcaddon.Addon('script.bobbi.setup').getAddonInfo('path'), 'Default', '1080i')
                credits.doModal()
            elif choice == 1:
                addon.openSettings()
        elif action == 'cinema':
            from bobbi_platform.ce_installer import blocked
            from bobbi_platform.paths import profile
            if blocked(profile('script.bobbi.start')):
                dialog.ok('安装尚未完成', '请打开“波比 TV · 开始使用”，完成恢复后再进入影院。')
                continue
            if xbmc.Player().isPlaying():
                dialog.ok('请先停止播放', '切换皮肤会关闭当前界面。')
                continue
            if dialog.yesno('切换到波比影院？', '切换后请选择“保留”。未确认会自动返回原皮肤。'):
                rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.bobbi.cinema'})
                return
        elif action == 'updates':
            if show_updates(dialog):
                return  # Do not reopen setup over Kodi's native add-on browser.
        elif action == 'diagnostics':
            from bobbi_platform.diagnostics_ui import show
            show(dialog)
        elif action == 'status':
            from bobbi_core.project_metadata import ATTRIBUTION
            dialog.ok('波比 TV', '支持 115、本地和 NAS 片库。BT 播放与 CD2 提前存片可按需配置。\n'
                      '设备支持情况和已知问题见发行说明。\n'
                      + ATTRIBUTION)
        elif action == 'transport':
            from bobbi_platform.cloud_hub import transport
            transport(dialog)


def show_updates(dialog):
    """Route user-requested maintenance; never update during playback."""
    if xbmc.Player().isPlaying():
        dialog.ok('请先停止播放', '停止影片后再更新程序。')
        return False
    choice = dialog.select('更新与恢复', [
        '管理 Kodi 依赖',
        '管理已安装插件',
        '本地安装与版本恢复',
        '检查波比 TV 更新',
        '存储空间与清理',
    ])
    if choice in (0, 1):
        dialog.ok('Kodi 插件管理',
                  '下一页可管理插件和依赖。波比影院请使用整包更新，勿用其他插件覆盖其组件。')
        # Playback can start while the selector or explanation is open.
        if xbmc.Player().isPlaying():
            dialog.ok('当前正在播放', '已取消打开更新页，请看完后再操作。')
            return False
        target = 'addons://dependencies/' if choice == 0 else 'addons://user/all/'
        xbmc.executebuiltin('ActivateWindow(addonbrowser,%s,return)' % target)
        return True
    if choice == 2:
        if xbmc.Player().isPlaying():
            return False
        xbmc.executebuiltin('RunScript(script.bobbi.start)')
        return True  # The installer asks before applying any signed package.
    if choice == 3:
        if xbmc.Player().isPlaying():
            return False
        xbmc.executebuiltin('RunScript(script.bobbi.start,online)')
        return True
    if choice == 4:
        if xbmc.Player().isPlaying():
            return False
        xbmc.executebuiltin('RunScript(script.bobbi.start,storage)')
        return True
    return False


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        xbmc.log('[bobbi] setup failed: ' + type(error).__name__, xbmc.LOGERROR)
        xbmcgui.Dialog().ok('操作未完成', '请重新打开“影院设置”重试，已保存的设置保留。')
