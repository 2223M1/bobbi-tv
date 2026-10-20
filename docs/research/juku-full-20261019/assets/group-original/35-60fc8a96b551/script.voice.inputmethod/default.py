"""Kodi entry point for the CoreELEC voice input method."""
import fcntl
from pathlib import Path
import sys
import xbmcaddon
import xbmcvfs

ADDON_ID = 'script.voice.inputmethod'


def guarded_main():
    addon = xbmcaddon.Addon(ADDON_ID)
    if not sys.argv[1:]:
        from resources.lib.application import action
        action(addon, None, set())
        return
    profile = Path(xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    profile.mkdir(parents=True, exist_ok=True)
    # A held voice key repeats RunScript. Only one dictation may run at a time;
    # a repeated press while recording must never open a second interpreter.
    with (profile / 'invocation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        from resources.lib.application import main
        main(addon, profile, invocation_owned=True)


if __name__ == '__main__':
    guarded_main()
else:
    # Development probes import the capture entry explicitly.
    from resources.lib.application import main, capture as run, rpc
