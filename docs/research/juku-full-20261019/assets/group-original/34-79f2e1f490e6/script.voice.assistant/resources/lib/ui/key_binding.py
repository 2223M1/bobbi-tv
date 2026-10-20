"""Capture Kodi button codes like controller.switcher, without changing keymaps until input."""
import math
import threading
import time
import xbmc
import xbmcgui
import xbmcvfs
from ..voice_binding import bind, button_code, begin_binding, update_binding


class KeyListener(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.ready = threading.Event()
        self.received = threading.Event()
        self.key = None
        super().__init__(*args, **kwargs)

    def onInit(self):
        self.ready.set()

    def onAction(self, action):
        if not self.ready.is_set() or self.received.is_set():
            return
        code = button_code(action.getButtonCode())
        if code is not None:
            self.key = code
            self.received.set()


def record_key(root, timeout=10):
    window = KeyListener('BindVoiceKey.xml', root, 'Default', '1080i')
    monitor = xbmc.Monitor()
    try:
        window.show()
        deadline = time.monotonic() + timeout
        while not window.received.is_set() and not monitor.abortRequested():
            remaining = math.ceil(deadline - time.monotonic())
            if remaining <= 0:
                return None
            if window.ready.is_set():
                window.getControl(302).setLabel('请按一下要用的语音按键 · {} 秒内不按则取消'.format(remaining))
            monitor.waitForAbort(.05)
        return None if monitor.abortRequested() else window.key
    finally:
        window.close()


def show(addon, request=None):
    profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    identifier = request or begin_binding(profile)
    update_binding(profile, identifier, 'listening')
    try:
        _show(addon, profile, identifier)
    except Exception:
        update_binding(profile, identifier, 'error', error='按键绑定失败，请检查按键 XML 后重试。')
        raise


def _show(addon, profile, identifier):
    code = record_key(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    if code is None:
        update_binding(profile, identifier, 'cancelled')
        xbmcgui.Dialog().notification('绑定语音按键', '未收到按键，未修改绑定。')
        return
    target = bind(xbmcvfs.translatePath('special://userdata/keymaps/'), code)
    update_binding(profile, identifier, 'done', key=code, target=target.name)
    # Match controller.switcher's reload delay after the capture dialog closes.
    if not xbmc.Monitor().waitForAbort(.4):
        xbmc.executebuiltin('Action(ReloadKeymaps)')
        xbmcgui.Dialog().notification('语音按键已绑定', '{} · global · 按键 {}'.format(target.name, code), time=5000)
