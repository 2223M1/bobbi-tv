"""Recording window with separate finish and cancel actions."""
import threading

import xbmcgui

from .strings import text

BACK = (9, 10, 92, 216, 247, 257)


class RecordingWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.ready = threading.Event()
        self.finish_requested = threading.Event()
        self.cancelled = threading.Event()
        self.recording = True
        super().__init__(*args, **kwargs)

    def onInit(self):
        self.setFocusId(400)
        self.ready.set()

    def onClick(self, identifier):
        if identifier == 400 and self.recording:
            self.finish_requested.set()
        elif identifier == 401:
            self.cancelled.set()

    def onAction(self, action):
        if action.getId() in BACK:
            self.cancelled.set()


class RecordingProgress:
    """DialogProgress-shaped adapter; UI updates remain on the Kodi main thread."""
    def __init__(self, root):
        self.window = RecordingWindow('InputRecording.xml', root, 'Default', '1080i')
        self.finish_requested = self.window.finish_requested
        self.title = ''

    def create(self, title, message):
        self.title = title
        self.window.show()
        self.update(0, message)

    def set_recording(self, enabled):
        self.window.recording = bool(enabled) and not self.finish_requested.is_set()

    def update(self, percent, message):
        if not self.window.ready.is_set():
            return
        self.window.getControl(301).setLabel(self.title)
        self.window.getControl(302).setText(message)
        if self.finish_requested.is_set() and self.window.recording:
            label = text(31043)
        else:
            label = text(31041) if self.window.recording else text(31044)
        # Keep focus on the finish button. Repeated OK must not accidentally
        # activate Cancel after the first click has completed recording.
        self.window.getControl(400).setLabel(label)

    def iscanceled(self):
        return self.window.cancelled.is_set()

    def close(self):
        self.window.close()
