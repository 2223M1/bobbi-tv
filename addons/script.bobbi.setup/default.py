"""Remote-friendly, repeatable setup. Account/installation gates stay honest."""
import xbmc
import xbmcgui
import xbmcvfs
from bobbi_platform.capabilities import probe
from bobbi_platform.android_ui import bundled_host
from bobbi_platform.environment import load_config, private_path, save_config
from bobbi_platform.i18n import tr as _plat_tr
from bobbi_platform.kodi import rpc, standard_handoff
from bobbi_platform.playback import selected_identity
from bobbi_platform.pairing import load as load_pairing, save as save_pairing
from bobbi_platform.pairing import from_export, engine_document
from bobbi_platform.torrserver import TorrServerClient, TorrServerError, Cancelled
from bobbi_platform.onboarding import steps, summary, engine_message


def _tr(msg_id, zh_text, en_text):
    return _plat_tr(msg_id, zh_text, en_text, addon_id='script.bobbi.setup')


def existing_backend_status():
    from bobbi_platform.bt_setup import adapter_status
    return adapter_status(xbmcvfs.translatePath, cancelled=xbmc.Monitor().abortRequested)


def existing_backend_state():
    from bobbi_platform.bt_setup import adapter_state
    return adapter_state(xbmcvfs.translatePath)


def helper_state(path):
    from bobbi_platform.bt_setup import helper_state as configured_state
    if bundled_host() and existing_backend_state() is None:
        return 'android_builtin'
    return configured_state(xbmcvfs.translatePath, path)


def show_existing_backend(dialog, state):
    from bobbi_platform.bt_setup import adapter_message
    dialog.ok(_tr(32002, '现有 BT 后台', 'Existing BT Backend'), adapter_message(state))


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
    if bundled_host():
        from bobbi_platform.android_engine import show
        return show(dialog)
    existing = existing_backend_state()
    if existing is not None:
        existing = existing_backend_status() or existing
        show_existing_backend(dialog, existing)
        return existing
    actions = [
        (0, _tr(32003, 'Android 助手配对', 'Pair Android Helper')),
        (1, _tr(32004, '使用说明', 'Usage Guide')),
        (2, _tr(32005, '安装 CoreELEC BT 后台', 'Install CoreELEC BT Backend')),
        (3, _tr(32006, '导入助手配对文件', 'Import Helper Pairing File')),
        (4, _tr(32007, '重新检查连接', 'Recheck Connection')),
    ]
    from bobbi_platform.ce_update_notice import coreelec
    if not coreelec():
        actions = [entry for entry in actions if entry[0] != 2]
    selected = dialog.select(_tr(32008, '设置 BT 播放', 'Configure BT Playback'), [label for _, label in actions])
    if selected < 0 or selected >= len(actions):
        return
    choice = actions[selected][0]
    if choice in (0, 2, 3):
        # Another entry may have configured the cinema adapter while this
        # selector was open. Do not create a second pairing or engine then.
        existing = existing_backend_state()
        if existing is not None:
            show_existing_backend(dialog, existing)
            return
    if choice == 0:
        from bobbi_platform.pair_code import exchange
        code = dialog.input(_tr(32009, '助手配对码（六位数字）', 'Helper Pairing Code (6 digits)'), type=xbmcgui.INPUT_NUMERIC)
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
            dialog.ok(
                _tr(32010, '助手已连接', 'Helper Connected'),
                _tr(32011, '以后打开助手并启动后台，就可以使用 BT 片源。',
                    'Open Helper and start the backend whenever you want to play BT sources.'),
            )
        except (ValueError, OSError, TorrServerError):
            dialog.ok(
                _tr(32012, '配对未完成', 'Pairing Incomplete'),
                _tr(32013, '请打开助手，获取新的配对码后重试。原有配对保留。',
                    'Open Helper to get a new pairing code and try again. Previous pairing is kept.'),
            )
    elif choice == 1:
        dialog.ok(
            _tr(32014, 'BT 播放说明', 'BT Playback Guide'),
            _tr(32015,
                '看 BT 片源需要连接下载后台。CoreELEC 可在这里安装，Android 需另配兼容的本机助手。\n只看 115 或本地 / NAS 片库，可以跳过。',
                'BT sources require a torrent backend. CoreELEC can install it here; Android uses the companion local Helper.\nSkip this if you only use 115 or local / NAS libraries.'),
        )
    elif choice == 2:
        from bobbi_platform.native_engine import install
        if xbmc.Player().isPlaying():
            dialog.ok(
                _tr(32016, '请先停止播放', 'Stop Playback First'),
                _tr(32017, '停止影片后再安装 BT 后台。', 'Stop video playback before installing the BT backend.'),
            )
            return
        if not dialog.yesno(
            _tr(32018, '安装 BT 后台？', 'Install BT Backend?'),
            _tr(32019, '需下载约 63 MB，仅在本机运行。不改 CD2 或系统服务。',
                'Downloads about 63 MB and runs locally only. Does not modify CD2 or system services.'),
        ):
            return
        progress = xbmcgui.DialogProgress()
        progress.create(
            _tr(32020, '安装 BT 后台', 'Installing BT Backend'),
            _tr(32021, '正在下载，可随时取消。', 'Downloading; you can cancel at any time.'),
        )
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
            dialog.ok(
                _tr(32022, 'BT 后台已安装', 'BT Backend Installed'),
                _tr(32023, '稍后选择“重新检查连接”。若仍未启动，请重启 Kodi。',
                    'Select "Recheck Connection" shortly. Restart Kodi if it still has not started.'),
            )
        except (ValueError, OSError):
            dialog.ok(
                _tr(32024, '安装未完成', 'Installation Incomplete'),
                _tr(32025, '此后台需要 ARM 版 CoreELEC，并能连接 GitHub。请检查网络后重试，网盘与 NAS 仍可使用。',
                    'Requires ARM CoreELEC and GitHub access. Check your network and retry; cloud and NAS libraries remain available.'),
            )
        finally:
            progress.close()
    elif choice == 3:
        selected = dialog.browse(1, _tr(32026, '选择助手导出的配对文件', 'Select Pairing File Exported by Helper'), 'files', mask='.json')
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
            dialog.ok(
                _tr(32027, '尚未连接', 'Not Connected Yet'),
                _tr(32028, '%s\n原有配对没有更改。', '%s\nPrevious pairing was not changed.') % engine_message(error.code),
            )
            return
        except ValueError:
            dialog.ok(
                _tr(32029, '配对文件不可用', 'Invalid Pairing File'),
                _tr(32030, '请使用这台盒子上的 bobbi 助手导出的文件。原有配对没有更改。',
                    'Use the file exported by bobbi Helper on this device. Previous pairing was not changed.'),
            )
            return
        dialog.ok(
            _tr(32010, '助手已连接', 'Helper Connected'),
            _tr(32031, '可以返回选片。配对文件含登录信息，请勿分享给别人。',
                'You can return to select media. The pairing file contains credentials; do not share it.'),
        )
    elif choice == 4:
        state = helper_status(path)
        if state.startswith('adapter_'):
            show_existing_backend(dialog, state)
            return state
        dialog.ok(
            _tr(32032, '连接检查', 'Connection Check'),
            _tr(32033, '助手已连接，可以选择视频试播。', 'Helper is connected and ready for test playback.')
            if state == 'ready' else
            _tr(32034, '未连接。请先打开助手并启动后台；重装过助手则需重新配对。',
                'Not connected. Open Helper and start the backend first; re-pair if Helper was reinstalled.'),
        )
        return state


def main():
    import sys
    if sys.argv[1:] == ['liquid_glass_status']:
        from bobbi_platform.glass_settings import sync_runtime_property
        sync_runtime_property()
        return
    dialog = xbmcgui.Dialog()
    if sys.argv[1:] == ['liquid_glass']:
        from bobbi_platform.glass_settings import show
        show(dialog)
        return
    if sys.argv[1:] == ['home_rails']:
        from bobbi_platform.glass_settings import show_home_rails
        show_home_rails(dialog)
        return
    if sys.argv[1:] == ['home_rails_reset']:
        from bobbi_platform.glass_settings import reset_home_rails
        reset_home_rails(dialog)
        return
    if sys.argv[1:] == ['home_spaces']:
        from bobbi_platform.glass_settings import show_home_spaces
        show_home_spaces(dialog)
        return
    if sys.argv[1:] == ['home_spaces_reset']:
        from bobbi_platform.glass_settings import reset_home_spaces
        reset_home_spaces(dialog)
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'power_action':
        if len(sys.argv) != 3:
            raise ValueError('INVALID_POWER_ACTION')
        from bobbi_platform.power_menu import run_power_action
        run_power_action(dialog, sys.argv[2])
        return
    if sys.argv[1:] == ['interface_language']:
        from bobbi_platform.power_menu import open_interface_language
        open_interface_language()
        return
    if sys.argv[1:] == ['display_adaptation']:
        from bobbi_platform.power_menu import show_display_adaptation
        show_display_adaptation(dialog)
        return
    if sys.argv[1:] == ['language_guide']:
        dialog.ok(
            _tr(32042, '原声与中文字幕', 'Original Audio & Subtitles'),
            _tr(32043,
                '下一页进入“语言”，将音轨首选语言设为“原始语言”，字幕首选语言设为“中文”。',
                'Open "Language" on the next screen to set Preferred Audio Language to "Original language" and Preferred Subtitle Language.'),
        )
        xbmc.executebuiltin('ActivateWindow(playersettings)')
        return
    if sys.argv[1:] == ['transport']:
        from bobbi_platform.cloud_hub import transport
        transport(dialog)
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'accounts':
        if len(sys.argv) > 3:
            raise ValueError('INVALID_ACCOUNT_DOMAIN')
        from bobbi_platform.cloud_hub import show_accounts, validate_account_domain
        domain = validate_account_domain(sys.argv[2] if len(sys.argv) == 3 else None)
        show_accounts(dialog, domain=domain)
        return
    if sys.argv[1:] in (['about'], ['version_notes']):
        from bobbi_platform.version_notes import show_about
        show_about(dialog)
        return
    if sys.argv[1:] in (['helper'], ['bt_helper']):
        pair_helper(dialog, private_path(xbmcvfs.translatePath, 'helper-pairing.json'))
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'cloud':
        from bobbi_platform.cloud_hub import show
        show(dialog)
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'diagnostics':
        from bobbi_platform.diagnostics_ui import show
        show(dialog)
        return
    try:
        from bobbi_platform.glass_settings import refresh_owned
        refresh_owned()
    except (OSError, RuntimeError, ValueError):
        xbmc.log('[bobbi] optional glass launcher unchanged', xbmc.LOGWARNING)
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
        choice = dialog.select(_tr(32035, '影院设置', 'Cinema Setup'), [label for _, label in rows])
        if choice < 0:
            return
        action = rows[choice][0]
        if action == 'check':
            capabilities = probe(rpc, system)
            dialog.ok(_tr(32036, '播放器检查', 'Player Check'), summary(capabilities))
        elif action == 'helper':
            helper = pair_helper(dialog, pair_path) or helper_state(pair_path)
        elif action == 'library':
            from bobbi_platform.library_ui import manage
            if manage(config['library_root']):
                return
        elif action == 'test':
            if not capabilities['standard_playback']:
                dialog.ok(_tr(32037, '先检查播放器', 'Check Player First'), summary(capabilities))
                continue
            if xbmc.Player().isPlaying():
                dialog.ok(
                    _tr(32038, '当前正在播放', 'Playback in Progress'),
                    _tr(32039, '请先手动停止，再开始测试。', 'Stop playback manually before starting test playback.'),
                )
                continue
            video = dialog.browse(1, _tr(32040, '选择视频试播', 'Select Video for Test Playback'), 'video',
                mask='.mkv|.mp4|.m4v|.mov|.avi|.webm|.ts|.m2ts', defaultt=config['library_root'])
            if video:
                identity = selected_identity(video)
                standard_handoff(identity, -1).submit(identity, {'url': video, 'title': _tr(32041, 'bobbi 播放测试', 'bobbi Playback Test')})
                return  # Do not reopen setup over a newly started video.
        elif action == 'language':
            dialog.ok(
                _tr(32042, '原声与中文字幕', 'Original Audio & Subtitles'),
                _tr(32043,
                    '下一页进入“语言”，将音轨首选语言设为“原始语言”，字幕首选语言设为“中文”。',
                    'Open "Language" on the next screen to set Preferred Audio Language to "Original language" and Preferred Subtitle Language.'),
            )
            xbmc.executebuiltin('ActivateWindow(playersettings)')
            return
        elif action == 'cloud':
            from bobbi_platform.cloud_hub import NAVIGATED, show_outcome
            if show_outcome(dialog) == NAVIGATED:
                return
        elif action == 'catalog':
            import xbmcaddon
            from bobbi_core.project_metadata import tmdb_key
            addon = xbmcaddon.Addon('plugin.video.bobbi')
            choice = dialog.select(_tr(32044, '影视海报与搜索', 'Posters & Search'), [
                (_tr(32045, '影视资料服务 · 已配置', 'Metadata Service · Configured')
                 if tmdb_key() else
                 _tr(32046, '影视资料服务 · 未配置', 'Metadata Service · Not Configured')),
                _tr(32047, '搜索与高级设置', 'Search & Advanced Settings'),
            ])
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
                dialog.ok(
                    _tr(32048, '安装尚未完成', 'Setup Incomplete'),
                    _tr(32049, '请打开“波比 TV · 开始使用”，完成恢复后再进入影院。',
                        'Open "bobbi TV · Get Started" and finish recovery before entering Cinema.'),
                )
                continue
            if xbmc.Player().isPlaying():
                dialog.ok(
                    _tr(32016, '请先停止播放', 'Stop Playback First'),
                    _tr(32050, '切换皮肤会关闭当前界面。', 'Switching skins will close the current playback screen.'),
                )
                continue
            if dialog.yesno(
                _tr(32051, '切换到波比影院？', 'Switch to bobbi Cinema?'),
                _tr(32052, '切换后请选择“保留”。未确认会自动返回原皮肤。',
                    'Choose "Yes" to keep the skin after switching. Unconfirmed changes revert automatically.'),
            ):
                rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.bobbi.cinema'})
                return
        elif action == 'updates':
            if show_updates(dialog):
                return  # Do not reopen setup over Kodi's native add-on browser.
        elif action == 'diagnostics':
            from bobbi_platform.diagnostics_ui import show
            show(dialog)
        elif action == 'status':
            from bobbi_platform.version_notes import show_about
            show_about(dialog)
        elif action == 'transport':
            from bobbi_platform.cloud_hub import transport
            transport(dialog)


def show_updates(dialog):
    """Route user-requested maintenance; never update during playback."""
    if bundled_host():
        from bobbi_platform.android_ui import show_updates as android_updates
        return android_updates(dialog)
    if xbmc.Player().isPlaying():
        dialog.ok(
            _tr(32016, '请先停止播放', 'Stop Playback First'),
            _tr(32053, '停止影片后再更新程序。', 'Stop video playback before updating.'),
        )
        return False
    choice = dialog.select(_tr(32054, '更新与恢复', 'Updates & Recovery'), [
        _tr(32055, '管理 Kodi 依赖', 'Manage Kodi Dependencies'),
        _tr(32056, '管理已安装插件', 'Manage Installed Add-ons'),
        _tr(32057, '本地安装与版本恢复', 'Local Install & Version Recovery'),
        _tr(32058, '检查波比 TV 更新', 'Check for bobbi TV Updates'),
        _tr(32059, '存储空间与清理', 'Storage Space & Cleanup'),
        _tr(32060, '新版本提醒', 'Update Notifications'),
    ])
    if choice in (0, 1):
        dialog.ok(
            _tr(32061, 'Kodi 插件管理', 'Kodi Add-on Management'),
            _tr(32062, '下一页可管理插件和依赖。波比影院请使用整包更新，勿用其他插件覆盖其组件。',
                'Manage add-ons and dependencies on the next screen. Update bobbi Cinema using full release bundles rather than overriding individual components.'),
        )
        # Playback can start while the selector or explanation is open.
        if xbmc.Player().isPlaying():
            dialog.ok(
                _tr(32038, '当前正在播放', 'Playback in Progress'),
                _tr(32063, '已取消打开更新页，请看完后再操作。',
                    'Cancelled opening updates while playback is active. Try again after watching.'),
            )
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
    if choice == 5:
        from bobbi_platform.ce_update_notice import NoticeProfile, enabled
        binding = NoticeProfile()
        work = binding.root('script.bobbi.start')
        index = dialog.select(_tr(32060, '新版本提醒', 'Update Notifications'), [
            _tr(32064, '空闲时提醒', 'Notify when idle'),
            _tr(32065, '关闭提醒', 'Disable notifications'),
        ], preselect=0 if enabled(work) else 1)
        if index in (0, 1) and binding.is_current():
            enabled(work, index == 0)
            return True
        return False
    return False


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        xbmc.log('[bobbi] setup failed: ' + type(error).__name__, xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            _tr(32066, '操作未完成', 'Action Not Completed'),
            _tr(32067, '请重新打开“影院设置”重试，已保存的设置保留。',
                'Reopen "Cinema Setup" and try again; saved settings are kept.'),
        )
