"""TinyPPI background service: react to playback and settings changes."""

import json
import os
import sys

import xbmc
import xbmcaddon
import xbmcgui

_LIB_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _LIB_PATH not in sys.path:
    sys.path.insert(0, _LIB_PATH)

from ui.theme import apply_theme

_ADDON_ID = "script.signde.tinyppi"
_HOME_WINDOW_ID = 10000
_FORCE_DEBUG_LOG = False


def _log(msg: str, level: int = xbmc.LOGDEBUG) -> None:
    if level == xbmc.LOGDEBUG and _FORCE_DEBUG_LOG:
        level = xbmc.LOGINFO
    xbmc.log(f"{_ADDON_ID} --> {msg}", level=level)


def _notification_media_type(data: str) -> str:
    """Extract the media type field from a Kodi JSON notification payload."""
    payload = json.loads(data)
    if not isinstance(payload, dict):
        return ""
    item = payload.get("item") or {}
    if isinstance(item, dict):
        return item.get("type", "") or payload.get("type", "")
    return payload.get("type", "")


class KodiMonitor(xbmc.Monitor):
    """Listen for Kodi notifications and launch configured codec badges."""

    def onNotification(self, sender: str, method: str, data: str) -> None:
        if method == "Player.OnAVStart":
            self._maybe_show_splash()
        try:
            mediatype = _notification_media_type(data)
            _log(f"sender={sender}  method={method}  type={mediatype!r}")
        except Exception as exc:
            _log(f"Exception in KodiMonitor.onNotification: {exc}", xbmc.LOGERROR)

    def onSettingsChanged(self) -> None:
        """Apply newly enabled badge triggers without restarting playback."""
        self._maybe_show_splash()

    def _maybe_show_splash(self) -> None:
        """Fire the format-logo splash when enabled for this video."""
        try:
            addon = xbmcaddon.Addon()
            if not (
                addon.getSettingBool("splash_enabled")
                or addon.getSettingBool("splash_show_on_osd")
                or addon.getSettingBool("splash_show_on_tinyppi")
            ):
                return
            if not xbmc.getCondVisibility("Player.HasVideo"):
                return
            xbmc.executebuiltin(f"RunScript({_ADDON_ID},splash)")
        except Exception as exc:
            _log(f"Exception starting splash: {exc}", xbmc.LOGERROR)


if __name__ == "__main__":
    addon = xbmcaddon.Addon()
    window = xbmcgui.Window(_HOME_WINDOW_ID)
    monitor = KodiMonitor()

    try:
        apply_theme(window, addon)
    except Exception as exc:  # pragma: no cover - never block the service
        xbmc.log(f"TinyPPI: apply_theme at startup failed: {exc}", xbmc.LOGWARNING)

    xbmc.log("TinyPPI: KodiMonitor started", xbmc.LOGINFO)
    monitor.waitForAbort()
    del monitor
