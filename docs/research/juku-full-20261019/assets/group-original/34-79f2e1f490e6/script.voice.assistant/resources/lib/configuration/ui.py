"""Show a short-lived LAN configuration URL as a QR on the TV."""
from ..data_paths import data_path
from pathlib import Path
import secrets
import time
import xbmc
import xbmcgui
import xbmcvfs

from ..codex_account_ui import LoginWindow, qr_png
import threading


def show(addon, profile):
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    home.clearProperty('VoiceAssistant.ConfigureURL')
    home.setProperty('VoiceAssistant.ConfigureRequested', secrets.token_hex(8))
    url = ''
    for unused in range(60):
        if monitor.waitForAbort(.05):
            return
        url = home.getProperty('VoiceAssistant.ConfigureURL')
        if url:
            break
    if not url:
        xbmcgui.Dialog().ok('扫码配置', '配置服务尚未启动，请稍后重试。')
        return
    image = data_path(profile, 'configuration-' + secrets.token_hex(8) + '.png')
    stopped = threading.Event()
    window = LoginWindow('Configuration.xml', xbmcvfs.translatePath(addon.getAddonInfo('path')),
                         'Default', '1080i', stopped=stopped)
    try:
        qr_png(url, image)
        window.show()
        while not stopped.is_set() and not monitor.abortRequested():
            if window.ready.is_set():
                window.getControl(301).setImage(str(image))
                window.getControl(302).setText('用手机扫码配置语音助手。\n手机与盒子需在同一局域网。\n电脑打开下方地址后，输入配置码：' + home.getProperty('VoiceAssistant.ConfigurePIN'))
                window.getControl(303).setLabel(url.split('#')[0])
                window.getControl(304).setLabel('配置入口有效 30 分钟 · 返回关闭电视提示')
            monitor.waitForAbort(.1)
    finally:
        window.close()
        image.unlink(missing_ok=True)
