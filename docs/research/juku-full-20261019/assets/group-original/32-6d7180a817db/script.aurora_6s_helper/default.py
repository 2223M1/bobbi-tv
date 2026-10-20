import json
import os
from pathlib import Path
import sys
import subprocess

import xbmc
import xbmcaddon
import xbmcgui

sys.path.insert(0, str(Path(__file__).parent / 'resources/lib'))
from config import ADDON_ID, parse_color
import repair
from diagnostics import exception_details, user_message


def notify_service():
    xbmc.executebuiltin('NotifyAll(%s,aurora.apply)' % ADDON_ID)


def main():
    dialog = xbmcgui.Dialog()
    addon = xbmcaddon.Addon(ADDON_ID)
    choice = sys.argv[1] if len(sys.argv) > 1 else ''
    if not choice:
        selected = dialog.select('极光 4 Pro / 6S 助手', ['修复硬件（自动识别 NG / NO）', '设置灯条（常规 / 播放）', 'eMMC 双系统与备份', '启动第一屏'])
        if selected < 0:
            return
        choice = ('repair', 'lights', 'emmc', 'logo')[selected]
        if choice == 'lights':
            action = dialog.select('灯条设置', ['色盘选色与灯光效果', '精确输入颜色值'])
            if action < 0:
                return
            if action == 1:
                choice = 'custom-color'
    if choice == 'logo':
        import logo_ui
        logo_ui.main()
        return
    if choice == 'emmc':
        import emmc_ui
        emmc_ui.main()
        return
    if choice == 'custom-color':
        scene = dialog.select('精确输入颜色', ['常规状态', '播放状态'])
        if scene < 0:
            return
        key = ('normal', 'playback')[scene] + '.color'
        old = addon.getSetting(key) or 'FF0000FF'
        value = dialog.input('输入六位颜色值 RRGGBB，例如 0080FF', defaultt=old[-6:])
        if not value:
            return
        rgb = parse_color(value.strip())
        addon.setSetting(key, 'FF' + ''.join('%02X' % c for c in rgb))
        notify_service()
        dialog.notification('极光灯条', '颜色已保存，并按当前播放状态应用')
        return
    if choice == 'lights':
        addon.openSettings()
        notify_service()
        return
    if choice == 'apply':
        notify_service()
        dialog.notification('极光灯条', '已请求按当前播放状态应用保存的设置')
        return
    if choice == 'status':
        p = Path('/run/aurora6s-led-status.json')
        if not p.exists():
            dialog.ok('灯条状态', '服务尚未运行，请启用插件或重启 Kodi。')
        else:
            info = json.loads(p.read_text(encoding='utf-8'))
            if 'error' in info:
                xbmc.log('[Aurora6S] lighting status: ' + info['error'], xbmc.LOGERROR)
                dialog.ok('灯条状态', user_message(info['error']))
            else:
                profile = info['profile']
                scene = '播放' if profile['name'] == 'playback' else '常规'
                engine = {'disabled': '已停用', 'hardware': '硬件控制', 'software': '软件呼吸'}[info['backend']]
                dialog.ok('灯条状态', '%s / %s\nRGB %s，亮度 %s%%\n%s' %
                          (scene, profile['mode'], profile['rgb'], profile['brightness'], engine))
        return
    if choice != 'repair':
        return
    profile = repair.check(allow_unidentified=True)
    if not profile['board']:
        if profile.get('identity_error'):
            dialog.ok('无法自动识别实物机型', user_message(profile['identity_error']) + '\n当前 DTB 名称不能证明实物机型，请按盒子标签确认。')
        if profile.get('model_choice_required'):
            selected = dialog.select('A4111 / rev D：请选择实物机型', ['极光 4 Pro', '极光 6S'])
            choices = ('4pro', '6s')
        else:
            selected = dialog.select('按盒子实物确认机型', ['极光 6S（A4112）', '极光 4 Pro（A4111）'])
            choices = ('6s', '4pro')
        if selected < 0:
            return
        profile = repair.check(confirmed_board=choices[selected])
    branch = profile['branch'].upper()
    board_name = '极光 4 Pro（A4111）' if profile['board'] == '4pro' else '极光 6S（A4112）'
    chip_name = 'AP6275P / BCM43752' if profile['chip'] == 'ap6275p' else 'RTL8852'
    result = 'CoreELEC %s / %s\n%s / %s\n' % (profile['version'], branch, board_name, chip_name)
    if profile['soc_revision']:
        result += 'S905X4 rev %s\n' % profile['soc_revision']
    if profile.get('model_choice_required'):
        result += 'Android 属性为 A4111 / rev D，修复包按你选择的实物机型安装。\n'
    elif profile['confirmation_required']:
        result += '当前设备树型号：%s\n设备树标识：%s\n' % (profile['model'] or '未知', profile['dt_id'] or '未知')
        result += '无法自动确认机型。如果只是借用了 X4 等设备树，请按盒子实际型号确认；真正的其他型号请取消。\n'
    result += ('将安装 NG DTB 和灯条驱动服务，使用 CE 自带的博通 Wi-Fi/蓝牙支持；备份并清理旧 Realtek NG 修复文件及启动项。' if profile['chip'] == 'ap6275p' and branch == 'NG'
               else '将安装 NO DTB 及 V12 识别规则，使用 CE 自带的博通 Wi-Fi/蓝牙驱动和固件。' if profile['chip'] == 'ap6275p'
               else '将安装 NG DTB、蓝牙配置及驱动服务。还会配置蓝牙待机唤醒、恢复及 PCIe 待机修复，更新 config.ini 启动参数；唤醒名单自动更新，下一步选择有线选项。' if branch == 'NG'
               else '将安装 NO DTB、蓝牙配置及 V12 识别规则，并配置蓝牙待机唤醒和恢复；唤醒名单自动更新，下一步选择有线选项。')
    if branch == 'NO':
        result += '\n同时消除自定义设备树引起的 30 秒开机等待。'
    if not dialog.yesno('极光硬件修复', result + '\n\n安装前会备份，完成后需要重启。确认机型并安装？',
                        nolabel='取消', yeslabel='备份并安装'):
        return
    wake_settings = None
    import wake_install
    if wake_install.supported(profile):
        wake_settings = wake_install.choose(dialog)
        if wake_settings is None:
            return
    progress = xbmcgui.DialogProgressBG()
    progress.create('极光硬件修复', '正在备份并部署…')
    try:
        script = Path(__file__).parent / 'resources/scripts/install-repair.sh'
        arguments = ['/bin/sh', str(script), '--install', '--confirm-board', profile['board']]
        if wake_settings is not None:
            arguments += ['--wake-settings', json.dumps(wake_settings, ensure_ascii=False)]
        proc = subprocess.run(arguments,
                              capture_output=True, encoding='utf-8', timeout=180,
                              env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or '安装失败')
        backup = json.loads(proc.stdout)['backup']
    finally:
        progress.close()
    if dialog.yesno('修复已安装', '已核对文件。重启后加载新配置。\n备份：' + backup,
                    nolabel='稍后重启', yeslabel='立即重启'):
        xbmc.executebuiltin('Reboot')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        xbmc.log(exception_details('UI'), xbmc.LOGERROR)
        xbmcgui.Dialog().ok('极光6S/4Pro助手', user_message(exc) + '\n详细信息已记录到 Kodi 日志。')
