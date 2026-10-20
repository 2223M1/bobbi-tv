import os
import sys
import tempfile
from unittest.mock import MagicMock

# --- Create stub classes for xbmcgui to avoid type hint issues in Python 3.13 ---
# Python 3.13 evaluates type hints at class definition time.
# If xbmcgui.WindowXMLDialog is a MagicMock, using Optional[SomeClass] where
# SomeClass inherits from it will break.


class _XbmcguiStub:
    """Stub module for xbmcgui with real classes for inheritance."""

    class Window:
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            pass

        def close(self):
            pass

        def setProperty(self, key, value):
            pass

        def getProperty(self, key):
            return ""

        def clearProperty(self, key):
            pass

        def setFocus(self, control):
            pass

        def setFocusId(self, control_id):
            pass

        def getFocus(self):
            return MagicMock()

        def getFocusId(self):
            return 0

        def getControl(self, control_id):
            return MagicMock()

        def doModal(self):
            pass

    class WindowXML(Window):
        def __init__(self, *args, **kwargs):
            pass

    class WindowXMLDialog(Window):
        def __init__(self, *args, **kwargs):
            pass

    class Dialog:
        def ok(self, *args, **kwargs):
            return True

        def yesno(self, *args, **kwargs):
            return True

        def select(self, *args, **kwargs):
            return 0

        def multiselect(self, *args, **kwargs):
            return []

        def notification(self, *args, **kwargs):
            pass

        def textviewer(self, *args, **kwargs):
            pass

        def input(self, *args, **kwargs):
            return ""

        def browse(self, *args, **kwargs):
            return ""

    class DialogProgress:
        def create(self, *args, **kwargs):
            pass

        def update(self, *args, **kwargs):
            pass

        def close(self):
            pass

        def iscanceled(self):
            return False

    class DialogProgressBG:
        def create(self, *args, **kwargs):
            pass

        def update(self, *args, **kwargs):
            pass

        def close(self):
            pass

        def isFinished(self):
            return False

    class ListItem:
        def __init__(self, *args, **kwargs):
            self._label = kwargs.get("label", "")

        def getLabel(self):
            return self._label

        def setLabel(self, label):
            self._label = label

        def setLabel2(self, label):
            pass

        def setInfo(self, *args, **kwargs):
            pass

        def setArt(self, *args, **kwargs):
            pass

        def setProperty(self, key, value):
            pass

        def getProperty(self, key):
            return ""

        def setPath(self, path):
            pass

        def getPath(self):
            return ""

        def setSubtitles(self, subtitleFiles):
            pass

        def addStreamInfo(self, cType, values):
            pass

        def addContextMenuItems(self, items):
            pass

    class ControlList:
        def addItem(self, item):
            pass

        def addItems(self, items):
            pass

        def selectItem(self, item):
            pass

        def getSelectedItem(self):
            return MagicMock()

        def getSelectedPosition(self):
            return 0

        def size(self):
            return 0

        def reset(self):
            pass

    class ControlProgress:
        def setPercent(self, percent):
            pass

        def getPercent(self):
            return 0.0

    # Fallback for any other attributes
    def __getattr__(self, name):
        return MagicMock()


# --- Create mock modules ---
xbmc_mock = MagicMock()
xbmc_mock.getSupportedMedia.return_value = ".mp4|.mkv|.avi|.ts|.m2ts"
xbmc_mock.LOGDEBUG = 0
xbmc_mock.LOGINFO = 1
xbmc_mock.LOGWARNING = 2
xbmc_mock.LOGERROR = 3

sys.modules["xbmc"] = xbmc_mock
sys.modules["xbmcgui"] = _XbmcguiStub()
sys.modules["xbmcaddon"] = MagicMock()
sys.modules["xbmcvfs"] = MagicMock()
# Resolve Kodi virtual paths before importing addon code. A MagicMock path can
# otherwise create a literal, relative cache tree inside distributable sources.
_kodi_paths = tempfile.TemporaryDirectory(prefix="am6b-kodi-tests-")
sys.modules["xbmcaddon"].Addon.return_value.getAddonInfo.side_effect = lambda key: {
    'profile': 'special://profile/addon_data/plugin.video.bobbi',
    'path': str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi'),
    'id': 'plugin.video.bobbi', 'name': 'Jacktook', 'version': '0.0-test',
}.get(key, '')
def _translate_path(value):
    if not isinstance(value, str):
        raise TypeError("Kodi path must be text")
    if value.startswith("special://"):
        relative = value[len("special://"):].replace("\\", "/")
        if ".." in relative.split("/"):
            raise ValueError("Parent traversal in test path")
        return os.path.join(_kodi_paths.name, *relative.split("/"))
    return value
sys.modules["xbmcvfs"].translatePath.side_effect = _translate_path
sys.modules["xbmcplugin"] = MagicMock()
sys.modules["pydevd"] = MagicMock()

# Mock sys.argv to simulate Kodi addon arguments
sys.argv = ["plugin.video.bobbi", "1", "/", ""]


from pathlib import Path
_root = Path(__file__).resolve().parents[2]
for _dir in ('plugin.video.bobbi', 'script.module.bobbi.core/lib', 'script.module.bobbi.platform/lib', 'script.module.bobbi.catalog/lib'):
    sys.path.insert(0, str(_root / 'addons' / _dir))
sys.path.insert(0, str(Path(__file__).parent))

def pytest_sessionfinish(session, exitstatus):
    module = sys.modules.get('lib.db.cached')
    if module is not None:
        module.cache.close()
    # Some baseline tests reload cached.py, leaving earlier *real* SQLite
    # connections reachable outside the final module singleton. Close those
    # fixture connections before Windows TemporaryDirectory teardown.
    import gc
    import sqlite3
    for value in gc.get_objects():
        if isinstance(value, sqlite3.Connection):
            try:
                value.close()
            except sqlite3.Error:
                pass
