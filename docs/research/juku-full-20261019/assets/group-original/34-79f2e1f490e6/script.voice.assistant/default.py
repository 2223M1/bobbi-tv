"""Separate direct launch guidance from serialized voice-button invocation."""


def guarded_main():
    import fcntl
    import os
    import sys
    import time
    import xbmcaddon
    import xbmcgui
    import xbmcvfs
    addon = xbmcaddon.Addon('script.voice.assistant')
    if not sys.argv[1:]:
        from resources.lib.application import action
        action(addon, None, set())
        return
    profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    os.makedirs(profile, exist_ok=True)
    from resources.lib.profile_upgrade import prepare_profile
    if not prepare_profile(profile):
        return
    from resources.lib.data_paths import data_path
    with data_path(profile, 'invocation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            from resources.lib.settings import get_setting
            home = xbmcgui.Window(10000)
            if sys.argv[1:] == ['--voice'] and get_setting(addon, 'voice_input') == 'usb' and home.getProperty('VoiceAssistant.State') == 'conversation':
                home.setProperty('VoiceAssistant.USBRecordRequested', str(time.monotonic()))
            return
        from resources.lib.application import main
        main(addon, profile, invocation_owned=True)

if __name__ == '__main__':
    guarded_main()
else:
    # Development probes import capture explicitly, outside the F5 entry.
    from resources.lib.application import main, capture as run, rpc
