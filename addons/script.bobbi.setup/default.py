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
    choice = dialog.select('连接本机 bobbi 助手', [
        'Android：输入助手显示的六位配对码',
        '查看本机 BT 支持说明',
        'CoreELEC：安装本机 BT 后台（可跳过）',
        '选择助手导出的 bobbi 配对文件',
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
            dialog.ok('已连接本机助手', '后续不用重复配对。打开助手启动后台后即可使用 BT 片源。')
        except (ValueError, OSError, TorrServerError):
            dialog.ok('尚未配对', '请确认助手已启动，并重新显示配对码。原有配对未更改。')
    elif choice == 1:
        dialog.ok('可选 BT 后台', '完整 Android 影院已内含 Kodi 播放器，不是旧助手。\n'
                  '当前候选未内嵌 BT 下载后台；115 / NAS 播放不需要配对。\n'
                  '只有你另行配置了兼容的本机后台时才导入其配对文件。不会打开应用配对自身。')
    elif choice == 2:
        from bobbi_platform.native_engine import install
        if xbmc.Player().isPlaying():
            dialog.ok('请先停止播放', '后台安装不会中断你正在看的影片。')
            return
        if not dialog.yesno('安装 CoreELEC 本机后台', '将下载约 63 MB，经校验后仅在本机运行。不会改 SSH、CD2、系统服务或开放远程控制端口。继续吗？'):
            return
        progress = xbmcgui.DialogProgress()
        progress.create('安装本机后台', '正在下载固定版本并核对 SHA-256；可取消。')
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
            dialog.ok('后台已安装', '几秒后点“重新检查连接”。若服务尚未运行，下次打开 Kodi 将自动启动。')
        except (ValueError, OSError):
            dialog.ok('安装未完成', '需要 ARM CoreELEC 且能访问 GitHub；现有系统服务没有改动。可重试或只使用网盘 / NAS。')
        finally:
            progress.close()
    elif choice == 3:
        selected = dialog.browse(1, '选择 bobbi 配对文件（不用手填地址和密码）', 'files', mask='.json')
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
        dialog.ok('助手已连接', '已核对后台版本和连接，后续不用重复配对。\n'
                  '配对文件含本机凭据，不要上传或发给别人；不再需要时可自行删除。\n'
                  '这一步没有开始播放，也未连接你的网盘账号。')
    elif choice == 4:
        state = helper_status(path)
        if state.startswith('adapter_'):
            show_existing_backend(dialog, state)
            return state
        dialog.ok('连接检查', '助手已连接，下一步可试播。' if state == 'ready'
                  else '尚未连接。请先在助手启动后台；若重新安装过助手，请重新导出并导入配对文件。')
        return state


def main():
    import sys
    dialog = xbmcgui.Dialog()
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
        choice = dialog.select('bobbi TV · 跟着提示完成设置', [label for _, label in rows])
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
            manage(config['library_root'])
        elif action == 'test':
            if not capabilities['standard_playback']:
                dialog.ok('先检查播放器', summary(capabilities))
                continue
            if xbmc.Player().isPlaying():
                dialog.ok('当前正在播放', '请先手动停止，再开始测试。')
                continue
            video = dialog.browse(1, '选择你自己的视频开始测试', 'video',
                mask='.mkv|.mp4|.m4v|.mov|.avi|.webm|.ts|.m2ts', defaultt=config['library_root'])
            if video:
                identity = selected_identity(video)
                standard_handoff(identity, -1).submit(identity, {'url': video, 'title': 'bobbi 播放测试'})
                return  # Do not reopen setup over a newly started video.
        elif action == 'language':
            dialog.ok('原声与中文字幕', '下一页在“语言”里选择“原始语言”和“中文”字幕。\n'
                      '不会改分辨率、HDR、音频直通，也不进行转码。')
            xbmc.executebuiltin('ActivateWindow(playersettings)')
            return
        elif action == 'cloud':
            from bobbi_platform.cloud_ui import login
            login()
        elif action == 'catalog':
            import xbmcaddon
            from bobbi_core.project_metadata import tmdb_key, ATTRIBUTION
            addon = xbmcaddon.Addon('plugin.video.bobbi')
            choice = dialog.select('影视海报与搜索', [
                '波比专用 TMDb 配置 · ' + ('已提供，无需申请' if tmdb_key() else '尚未安装'),
                '影院高级设置 / 自选检索服务'])
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
                dialog.ok('安装尚未完成', '请先打开“波比开始使用”恢复安装。原皮肤保持不变。')
                continue
            if xbmc.Player().isPlaying():
                dialog.ok('请先停止播放', '切换皮肤会关闭当前界面。')
                continue
            if dialog.yesno('进入波比影院', '切换到波比皮肤？Kodi 会询问是否保留；未确认会自动恢复原皮肤。'):
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
            dialog.ok('波比 TV', '个人 115 / NAS、手动选源、同版续播及中文字幕共用业务核心。\n'
                      'BT / CD2 云准备为可选能力，未配置时不会阻止启动。\n'
                      '设备能力与已知问题见发行说明。不会自动刷机；未登录也可使用本地与 NAS 片库。\n'
                      + ATTRIBUTION)
        elif action == 'transport':
            from bobbi_platform.transport_preferences import load, save
            mode = load(path.parent)
            selected = dialog.select('115 传输模式 · 下次启动 Kodi 生效',
                ['整块交付（回退模式）', '渐进交付（有界 8 MiB 队列）'], preselect=1 if mode else 0)
            if selected in (0, 1):
                save(path.parent, selected == 1)
                dialog.ok('已保存，不中断当前播放', '下次启动 Kodi 后使用所选模式。\n'
                          '两种模式都保持原码流、原音轨，不转码，不整部缓存。')


def show_updates(dialog):
    """Route user-requested maintenance; never update during playback."""
    if xbmc.Player().isPlaying():
        dialog.ok('请先停止播放', '播放中不打开插件更新操作页，也不会停止影片或执行更新。')
        return False
    choice = dialog.select('更新与恢复 · 原版与定制分开维护', [
        '原版依赖 · Kodi 依赖管理 / 更新',
        '已装插件 · Kodi 我的插件 / 原仓库更新',
        '波比影院 · 本地完整包 / 回退程序',
        '波比影院 · 在线检查并安装最新正式版',
    ])
    if choice in (0, 1):
        dialog.ok('打开 Kodi 原生插件管理',
                  '原版依赖保留原 ID，由 Kodi 按可用的原仓库管理；这里不自动检查或执行更新。\n'
                  '波比定制组件不能整体用原版覆盖。已安装的旧播放组件与原版也不是一回事，请勿直接替换。')
        # Playback can start while the selector or explanation is open.
        if xbmc.Player().isPlaying():
            dialog.ok('当前已经开始播放', '本次不打开插件更新操作页，影片保持播放。')
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
    return False


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        xbmc.log('[bobbi] setup failed: ' + type(error).__name__, xbmc.LOGERROR)
        xbmcgui.Dialog().ok('这一步没有完成', '请重新打开 bobbi 设置重试。\n'
                           '已保存的步骤会保留，不需要从头配置。')
