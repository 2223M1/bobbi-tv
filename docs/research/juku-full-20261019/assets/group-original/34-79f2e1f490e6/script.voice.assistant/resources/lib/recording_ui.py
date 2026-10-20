"""Recording window with separate finish and cancel actions."""
import threading

import xbmcgui
from .voice_binding import current_codes, is_voice_key

BACK = (9, 10, 92, 216, 247, 257)


class RecordingWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.ready = threading.Event()
        self.voice_keys = set()
        self.finish_requested = threading.Event()
        self.cancelled = threading.Event()
        self.recording = True
        super().__init__(*args, **kwargs)

    def onInit(self):
        try:
            self.voice_keys = current_codes()
            self.setFocusId(400)
        except Exception:
            self.cancelled.set()
            raise
        finally:
            self.ready.set()

    def onClick(self, identifier):
        if identifier == 400 and self.recording:
            self.finish_requested.set()
        elif identifier == 401:
            self.cancelled.set()

    def onAction(self, action):
        if is_voice_key(action, self.voice_keys):
            return
        if action.getId() in BACK:
            self.cancelled.set()


class RecordingProgress:
    """DialogProgress-shaped adapter; UI updates remain on the Kodi main thread."""
    def __init__(self, root):
        self.window = RecordingWindow('VoiceRecording.xml', root, 'Default', '1080i')
        self.finish_requested = self.window.finish_requested
        self.title = ''
        self.shown = False

    def create(self, title, message):
        self.title = title
        if not self.shown:
            self.window.show()
            self.shown = True
        self.update(0, message)

    def set_recording(self, enabled):
        self.window.recording = bool(enabled) and not self.finish_requested.is_set()

    def update(self, percent, message):
        if not self.window.ready.is_set():
            return
        self.window.getControl(301).setLabel(self.title)
        self.window.getControl(302).setText(message)
        if self.finish_requested.is_set() and self.window.recording:
            label = '正在结束收音…'
        else:
            label = '说完了，开始识别（OK）' if self.window.recording else '正在处理，请稍候…'
        # Keep focus on the finish button. Repeated OK must not accidentally
        # activate Cancel after the first click has completed recording.
        self.window.getControl(400).setLabel(label)

    def iscanceled(self):
        return self.window.cancelled.is_set()

    def close(self):
        if self.shown:
            self.window.close()
            self.shown = False
