# -*- coding: utf-8 -*-
"""
CD2 Preheat - RunScript 入口
- auto_detect: 设置界面"自动检测 CD2 挂载路径"按钮调用
"""
import sys
import subprocess

import xbmc
import xbmcaddon
import xbmcgui


_ADDON = xbmcaddon.Addon()


def log(msg):
    if _ADDON.getSettingBool('debug_log'):
        xbmc.log(f'[CD2 Preheat] {msg}', xbmc.LOGINFO)


def auto_detect_cd2_paths():
    """自动检测 CD2 挂载路径（FUSE 挂载点包含 CloudDrive/CloudNAS 关键字）"""
    paths = []
    try:
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'type fuse' in line or 'fuse.' in line:
                parts = line.split(' on ')
                if len(parts) >= 2:
                    mount_point = parts[1].split(' type ')[0]
                    lower_mp = mount_point.lower()
                    if any(kw in lower_mp for kw in ['clouddrive', 'cloudnas', 'cloudfs']):
                        if not mount_point.endswith('/'):
                            mount_point += '/'
                        paths.append(mount_point)
    except Exception as e:
        log(f'auto_detect error: {e}')
    return paths


def do_auto_detect():
    """执行自动检测，更新 path_prefix 设置"""
    paths = auto_detect_cd2_paths()
    if paths:
        unique_paths = list(dict.fromkeys(paths))
        new_prefix = ','.join(unique_paths)
        _ADDON.setSetting('path_prefix', new_prefix)
        log(f'auto_detect -> path_prefix updated: {new_prefix}')
        xbmcgui.Dialog().notification(
            'CD2 Preheat',
            f'检测到 {len(unique_paths)} 个 CD2 挂载路径\n{unique_paths[0]}' +
            (f'\n等 {len(unique_paths)} 个' if len(unique_paths) > 1 else ''),
            xbmcgui.NOTIFICATION_INFO, 5000
        )
    else:
        log('auto_detect -> no CD2 mount points found')
        xbmcgui.Dialog().notification(
            'CD2 Preheat',
            '未检测到 CD2 挂载路径\n请确认 CloudDrive2 已运行并挂载',
            xbmcgui.NOTIFICATION_WARNING, 5000
        )


def main():
    log(f'default.py called, sys.argv={sys.argv}')
    if len(sys.argv) < 2:
        return

    cmd = sys.argv[1]

    if cmd == 'auto_detect':
        do_auto_detect()


if __name__ == '__main__':
    main()
