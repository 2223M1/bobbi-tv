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
        '打开 Android 助手',
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
        if xbmc.getCondVisibility('System.Platform.Android'):
            xbmc.executebuiltin('StartAndroidActivity(org.bobbi.helper)')
        else:
            dialog.ok('bobbi', 'Android 助手仅适用于 Android。CoreELEC 后台安装仍在集成中。')
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
            show_updates(dialog)
        elif action == 'status':
            dialog.ok('bobbi TV · 公开测试版', '支持新影院、个人 115 分享读取、网盘 / NAS、手选片源和本机 BT。\n'
                      '不包含私人后台账号或定制内核；自动字幕与自动续播尚未完成通用版适配。\n'
                      'Android / 全新安装仍待真实设备验收。不会刷机或替换原系统。')


def show_updates(dialog):
    dialog.ok('更新与恢复', '通过 Kodi 的 bobbi TV 仓库接收组件更新。\n'
              '建议在 Kodi 插件设置中选择“通知，但不要安装更新”，停止播放后再更新。\n'
              'APK 新版见 github.com/2223M1/bobbi-tv/releases，安装时保留原应用，不要卸载。\n'
              '回退：先切回 Estuary，退出 Kodi，备份用户数据，再从旧发行安装相同版本整套组件。')
    xbmc.executebuiltin('UpdateAddonRepos')
    xbmc.executebuiltin('ActivateWindow(addonbrowser)')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        xbmc.log('[bobbi] setup failed: ' + type(error).__name__, xbmc.LOGERROR)
        xbmcgui.Dialog().ok('这一步没有完成', '请重新打开 bobbi 设置重试。\n'
                           '已保存的步骤会保留，不需要从头配置。')
