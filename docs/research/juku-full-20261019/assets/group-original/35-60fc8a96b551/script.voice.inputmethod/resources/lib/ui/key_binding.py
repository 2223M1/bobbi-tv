"""Capture Kodi button codes like controller.switcher, without changing keymaps until input."""
import math
import threading
import time
import xbmc
import xbmcgui
import xbmcvfs
from ..strings import text
from ..voice_binding import bind, button_code


class KeyListener(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.ready = threading.Event()
        self.received = threading.Event()
        self.key = None
        super().__init__(*args, **kwargs)

    def onInit(self):
        self.ready.set()

    def onAction(self, action):
        raw = action.getButtonCode()
        xbmc.log('[voice-input] bind dialog saw action id=%r code=%r (%s)'
                 % (action.getId(), raw, button_code(raw)), xbmc.LOGINFO)
        if not self.ready.is_set() or self.received.is_set():
            return
        code = button_code(raw)
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
                window.getControl(302).setLabel(text(31051, remaining))
            monitor.waitForAbort(.05)
        return None if monitor.abortRequested() else window.key
    finally:
        window.close()


def show(addon):
    code = record_key(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    if code is None:
        xbmcgui.Dialog().notification(text(31037), text(31052))
        return
    target = bind(xbmcvfs.translatePath('special://userdata/keymaps/'), code)
    # Match controller.switcher's reload delay after the capture dialog closes.
    if not xbmc.Monitor().waitForAbort(.4):
        xbmc.executebuiltin('Action(ReloadKeymaps)')
        xbmcgui.Dialog().notification(text(31053), text(31068, target.name, code), time=5000)
