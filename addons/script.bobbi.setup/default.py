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


def helper_status(path):
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
    choice = dialog.select('连接本机 bobbi 助手', [
        'Android：输入助手显示的六位配对码',
        '查看本机 BT 支持说明',
        'CoreELEC：安装本机 BT 后台（可跳过）',
        '选择助手导出的 bobbi 配对文件',
        '重新检查连接',
    ])
    if choice == 0:
        from bobbi_platform.pair_code import exchange
        code = dialog.input('助手配对码（六位数字）', type=xbmcgui.INPUT_NUMERIC)
        if not code:
            return
        try:
            pairing = exchange(code)
            TorrServerClient(engine_document(pairing)).ready(cancelled=xbmc.Monitor().abortRequested)
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
        stream = xbmcvfs.File(selected)
        try:
            raw = stream.readBytes(4097)
        finally:
            stream.close()
        try:
            pairing = from_export(bytes(raw))
            TorrServerClient(engine_document(pairing)).ready(cancelled=xbmc.Monitor().abortRequested)
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
        dialog.ok('连接检查', '助手已连接，下一步可试播。' if state == 'ready'
                  else '尚未连接。请先在助手启动后台；若重新安装过助手，请重新导出并导入配对文件。')


def main():
    import sys
    dialog = xbmcgui.Dialog()
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
    helper = helper_status(pair_path)
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
            pair_helper(dialog, pair_path)
            helper = helper_status(pair_path)
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
            addon = xbmcaddon.Addon('plugin.video.bobbi')
            choice = dialog.select('影视海报与搜索', ['设置自己的 TMDb API Key', '影院高级设置 / 自选检索服务'])
            if choice == 0:
                import re
                key = dialog.input('TMDb API Key（在 themoviedb.org 个人设置申请，可跳过）', option=xbmcgui.ALPHANUM_HIDE_INPUT)
                if key and re.fullmatch('[a-fA-F0-9]{32}', key):
                    addon.setSetting('tmdb_api_key', key)
                    xbmcgui.Window(10000).clearProperty('bobbi.settings')
                    dialog.ok('已保存', '海报目录使用你自己的 TMDb 账号。NAS / 直链片库不需要这个 Key。')
                elif key:
                    dialog.ok('格式不匹配', '请填写 API Key，不是读取访问令牌。原值未更改。')
            elif choice == 1:
                addon.openSettings()
        elif action == 'cinema':
            if xbmc.Player().isPlaying():
                dialog.ok('请先停止播放', '切换皮肤会关闭当前界面。')
                continue
            if dialog.yesno('进入波比影院', '切换到波比皮肤？Kodi 会询问是否保留；未确认会自动恢复原皮肤。'):
                rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.bobbi.cinema'})
                return
        elif action == 'updates':
            if show_updates(dialog):
                return  # Do not reopen setup over Kodi's native add-on browser.
        elif action == 'status':
            dialog.ok('波比 TV · 私人候选版', '新影院、个人 115 / NAS、手动选源、同版续播及中文字幕共用业务核心。\n'
                      'BT / CD2 云准备为可选能力，未配置时不会阻止启动。\n'
                      '原生构建成功不代表每种设备都已实播验收；以随包验收记录为准。不会自动刷机。')


def show_updates(dialog):
    """Open native management only; never start an update or refresh a repo."""
    if xbmc.Player().isPlaying():
        dialog.ok('请先停止播放', '播放中不打开插件更新操作页，也不会停止影片或执行更新。')
        return False
    choice = dialog.select('更新与恢复 · 原版与定制分开维护', [
        '原版依赖 · Kodi 依赖管理 / 更新',
        '已装插件 · Kodi 我的插件 / 原仓库更新',
        '波比定制组件 · 签名包更新与回退说明',
    ])
    if choice in (0, 1):
        dialog.ok('打开 Kodi 原生插件管理',
                  '原版依赖保留原 ID，由 Kodi 按可用的原仓库管理；这里不自动检查或执行更新。\n'
                  '波比定制组件不能整体用原版覆盖。旧定制 JackTorr 与原版也不是一回事，请勿直接替换。')
        # Playback can start while the selector or explanation is open.
        if xbmc.Player().isPlaying():
            dialog.ok('当前已经开始播放', '本次不打开插件更新操作页，影片保持播放。')
            return False
        target = 'addons://dependencies/' if choice == 0 else 'addons://user/all/'
        xbmc.executebuiltin('ActivateWindow(addonbrowser,%s,return)' % target)
        return True
    if choice == 2:
        dialog.ok('波比定制组件 · 私人签名包',
                  '原版依赖使用 Kodi 原生管理；波比定制组件使用维护者提供的同代完整签名包。\n'
                  '这里只提供说明，不下载、不安装，也不刷新仓库。先校验完整签名包，再退出播放器切换。\n'
                  'Windows：退出影院后使用 bobbi.exe --apply 签名包；--rollback 回退程序。\n'
                  'CE：由维护工具停播校验后切换；Android：安装同签名完整 APK，不要卸载原应用。\n'
                  '回退仅恢复波比程序，不覆盖账号、片库和观看数据；不代替原版插件的更新管理。')
    return False


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        xbmc.log('[bobbi] setup failed: ' + type(error).__name__, xbmc.LOGERROR)
        xbmcgui.Dialog().ok('这一步没有完成', '请重新打开 bobbi 设置重试。\n'
                           '已保存的步骤会保留，不需要从头配置。')
