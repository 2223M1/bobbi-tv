"""Capability-gated power actions, UI language handoff, and read-only display adaptation help."""
from __future__ import annotations

from pathlib import Path
import threading

from .paths import ProfileBinding

_ACTION_LOCK = threading.Lock()

POWER_CAPABILITIES = {
    'powerdown': ('System.CanPowerDown', 'Powerdown()'),
    'reboot': ('System.CanReboot', 'Reset()'),
    'quit': ('System.ShowExitButton', 'Quit()'),
}


def is_english_ui(get_info=None) -> bool:
    if get_info is None:
        try:
            import xbmc
            get_info = xbmc.getInfoLabel
        except ImportError:
            return False
    lang = (get_info('System.Language') or '').strip().lower()
    if not lang:
        return False
    return 'chinese' not in lang and '中文' not in lang and 'zh' not in lang


def _power_copy(action: str, *, playing: bool, english: bool) -> tuple[str, str]:
    if english:
        titles = {
            'powerdown': 'Shut Down Host?',
            'reboot': 'Restart Host?',
            'quit': 'Quit Kodi?',
        }
        bodies = {
            'powerdown': 'Power off this device completely.',
            'reboot': 'Restart the host operating system.',
            'quit': 'Exit the Kodi application (managed systems such as CoreELEC may relaunch the UI automatically).',
        }
        prefix = 'Playback is currently active and will be ended if you continue.\n' if playing else ''
        return titles[action], prefix + bodies[action]
    titles = {
        'powerdown': '确定关闭主机？',
        'reboot': '确定重启主机？',
        'quit': '确定退出 Kodi？',
    }
    bodies = {
        'powerdown': '将关闭当前主机电源。取消或按返回键不会产生任何影响。',
        'reboot': '将重新启动当前主机系统。取消或按返回键不会产生任何影响。',
        'quit': '仅退出 Kodi 应用本身（在 CoreELEC 等托管系统上，系统服务可能会自动重新拉起界面；如需断电请选择“关闭主机”）。',
    }
    prefix = '当前正在播放媒体，继续操作将结束当前播放。\n' if playing else ''
    return titles[action], prefix + bodies[action]


def execute_power_action(
    action: str,
    *,
    dialog,
    get_cond,
    is_playing,
    execute,
    is_current=lambda: True,
    english: bool = False,
) -> str:
    """Validate host capability, ask explicit confirmation, and dispatch at most one power builtin."""
    if action not in POWER_CAPABILITIES:
        raise ValueError(f'INVALID_POWER_ACTION:{action}')
    if not _ACTION_LOCK.acquire(blocking=False):
        return 'BUSY'
    try:
        if not is_current():
            return 'ABORTED'
        cap_cond, builtin = POWER_CAPABILITIES[action]
        if not get_cond(cap_cond):
            if english:
                dialog.ok('Action Unavailable', 'This power action is not supported by the current host.')
            else:
                dialog.ok('当前设备不支持', '当前宿主环境未提供该电源能力。')
            return 'UNSUPPORTED'
        playing = bool(is_playing())
        title, message = _power_copy(action, playing=playing, english=english)
        confirmed = bool(dialog.yesno(title, message))
        if not confirmed:
            return 'CANCELLED'
        if not is_current() or not get_cond(cap_cond):
            return 'ABORTED'
        try:
            if get_cond('Window.IsVisible(shutdownmenu)'):
                execute('Dialog.Close(shutdownmenu)')
            if get_cond('Window.IsVisible(1114)'):
                execute('Dialog.Close(1114)')
            execute(builtin)
        except OSError:
            return 'SUBMISSION_UNKNOWN'
        return 'EXECUTED'
    finally:
        _ACTION_LOCK.release()


def run_power_action(dialog, action: str) -> str:
    import xbmc

    binding = ProfileBinding()
    eng = is_english_ui(xbmc.getInfoLabel)
    return execute_power_action(
        action,
        dialog=dialog,
        get_cond=lambda expr: bool(xbmc.getCondVisibility(expr)),
        is_playing=lambda: bool(xbmc.Player().isPlaying()),
        execute=lambda cmd: xbmc.executebuiltin(cmd),
        is_current=binding.is_current,
        english=eng,
    )


def open_interface_language() -> bool:
    import xbmc

    binding = ProfileBinding()
    if not binding.is_current():
        return False
    xbmc.executebuiltin('ActivateWindow(InterfaceSettings)')
    return True


def _read_sysfs_line(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding='utf-8', errors='replace').splitlines()[0].strip()
    except OSError:
        pass
    return ''


def collect_display_summary(*, get_info=None, rpc_call=None, sysfs_root: Path = Path('/sys/class')) -> dict[str, str]:
    """Read-only snapshot of GUI plane, HDMI mode, Skin Zoom, and framebuffer axis (zero writes)."""
    if get_info is None:
        try:
            import xbmc
            get_info = xbmc.getInfoLabel
        except ImportError:
            get_info = lambda _k: ''
    gui_res = (get_info('System.ScreenResolution') or '').strip() or 'UNKNOWN'
    skin_zoom = 'UNKNOWN'
    screen_mode = 'UNKNOWN'
    if rpc_call is not None:
        try:
            zoom_val = rpc_call('Settings.GetSettingValue', {'setting': 'lookandfeel.skinzoom'})
            if isinstance(zoom_val, dict) and 'value' in zoom_val:
                skin_zoom = f"{zoom_val['value']}%"
        except (OSError, RuntimeError, ValueError):
            pass
        try:
            mode_val = rpc_call('Settings.GetSettingValue', {'setting': 'videoscreen.screenmode'})
            if isinstance(mode_val, dict) and mode_val.get('value'):
                screen_mode = str(mode_val['value'])
        except (OSError, RuntimeError, ValueError):
            pass
    hdmi_mode = _read_sysfs_line(sysfs_root / 'amhdmitx/amhdmitx0/disp_mode') or 'N/A'
    fb_axis = _read_sysfs_line(sysfs_root / 'graphics/fb0/window_axis') or 'N/A'
    return {
        'gui_resolution': gui_res,
        'hdmi_mode': hdmi_mode,
        'fb0_window_axis': fb_axis,
        'skin_zoom': skin_zoom,
        'screen_mode': screen_mode,
    }


def show_display_adaptation(dialog, *, get_info=None, rpc_call=None, execute=None, is_current=None) -> str:
    """Interactive read-only display diagnostic & native Kodi display deep links.

    Returns 'NAVIGATED' if a native Kodi window was opened, else 'CANCELLED'.
    Never writes HDMI registers, EDID, Skin Zoom, or calibration files.
    """
    if get_info is None or execute is None or rpc_call is None or is_current is None:
        import xbmc
        from .kodi import rpc as default_rpc

        binding = ProfileBinding()
        get_info = get_info or xbmc.getInfoLabel
        execute = execute or xbmc.executebuiltin
        rpc_call = rpc_call or default_rpc
        is_current = is_current or binding.is_current

    english = is_english_ui(get_info)
    while is_current():
        snap = collect_display_summary(get_info=get_info, rpc_call=rpc_call)
        if english:
            status_row = f"Current Chain: GUI {snap['gui_resolution']} · HDMI {snap['hdmi_mode']} · Zoom {snap['skin_zoom']}"
            rows = [
                status_row,
                'TV Overscan & Cropped Sidebar Guide (LG Just Scan = On)',
                'Open Kodi System Display & Whitelist Settings',
                'Open Kodi Interface & Skin Zoom Settings',
                'Open Video Calibration (only if TV overscan cannot be turned off)',
            ]
            heading = 'Display Fit & Overscan Check'
        else:
            status_row = f"当前显示链：GUI {snap['gui_resolution']} · HDMI {snap['hdmi_mode']} · 缩放 {snap['skin_zoom']}"
            rows = [
                status_row,
                '侧栏贴边 / 四边被裁切排查说明（电视开启点对点 Just Scan）',
                '打开系统显示与分辨率白名单设置',
                '打开界面与皮肤缩放设置',
                '打开屏幕边界校准（仅电视无法关闭过扫描时使用）',
            ]
            heading = '显示适配与过扫描检查'

        pick = dialog.select(heading, rows)
        if pick < 0 or not is_current():
            return 'CANCELLED'
        if pick == 0:
            if english:
                detail = (
                    f"GUI Plane: {snap['gui_resolution']} (Mode: {snap['screen_mode']})\n"
                    f"HDMI mode reported by the box: {snap['hdmi_mode']}   ·   OSD Axis: {snap['fb0_window_axis']}\n"
                    "TV/AVR received signal: unknown (receiver not measured).\n"
                    f"Skin Zoom: {snap['skin_zoom']} (read-only check; existing calibration is preserved)."
                )
                dialog.ok('Live Display Chain', detail)
            else:
                detail = (
                    f"Kodi 界面平面：{snap['gui_resolution']}（模式：{snap['screen_mode']}）\n"
                    f"盒端 HDMI 模式：{snap['hdmi_mode']}   ·   OSD 坐标轴：{snap['fb0_window_axis']}\n"
                    "电视／功放接收信号：未知（未读取接收端）。\n"
                    f"当前皮肤缩放：{snap['skin_zoom']}（只读检查，不自动修改任何已有校准配置）。"
                )
                dialog.ok('当前显示链路状态', detail)
        elif pick == 1:
            if english:
                guide = (
                    'If Kodi screenshots show complete 35px margins while your TV crops all 4 edges:\n'
                    '1. On LG TVs: Settings -> Picture -> Aspect Ratio -> 16:9 / Original, and set Just Scan = On (not Auto).\n'
                    '2. On Sony / Samsung / TCL: enable Full Pixel / Fit to Screen / Overscan Off for this HDMI port.\n'
                    'Disable TV overscan first instead of applying negative Skin Zoom so video planes stay unscaled.'
                )
                dialog.ok('TV Overscan Checklist', guide)
            else:
                guide = (
                    '若内置截图完整（侧栏距左/上各 35px），但电视实拍四边被裁切：\n'
                    '1. LG 电视：进入「设置 → 画面 → 画面比例」，保持 16:9 / 原始比例，将「点对点显示（Just Scan）」从自动改为「开（On）」。\n'
                    '2. 索尼 / 三星 / 国产电视：开启当前 HDMI 口的「全像素 / 适配屏幕 / 关闭过扫描」。\n'
                    '优先关闭电视过扫描，可同时恢复界面与视频真实边缘，无需负向缩小皮肤。'
                )
                dialog.ok('电视过扫描排查说明', guide)
        elif pick == 2:
            execute('ActivateWindow(SystemSettings)')
            return 'NAVIGATED'
        elif pick == 3:
            execute('ActivateWindow(InterfaceSettings)')
            return 'NAVIGATED'
        elif pick == 4:
            execute('ActivateWindow(ScreenCalibration)')
            return 'NAVIGATED'
    return 'CANCELLED'
