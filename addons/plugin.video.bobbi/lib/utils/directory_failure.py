"""Finish failed navigation handles, without closing unrelated widget dialogs."""
import sys


def fail_directory(message="资料请求失败，可重试"):
    import xbmcgui
    import xbmcplugin

    try:
        handle = int(sys.argv[1])
    except (IndexError, TypeError, ValueError):
        handle = -1
    # Notify only after notifying Kodi that its pending directory is finished.
    # A failed directory retains the parent, so the same card can be retried.
    if handle >= 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
    xbmcgui.Dialog().notification("波比TV", message, time=4000, sound=False)
    return False
