"""Present Kodi's own IME page as directly focusable characters.

No network, dictionary, input history or player access. Runs only while the
native keyboard is open; the native coding table still owns composition.
"""
import re


def candidates(code, raw):
    if not code or len(raw) > 8192:
        return []
    matches = list(re.finditer(r'(?:^<?| )([0-9])\.(.*?)(?= [0-9]\.|>?$)', raw))
    result = [(int(m[1]), m[2]) for m in matches]
    if not result or [n for n, _ in result] != list(range(len(result))):
        return []
    if any(not word.strip() for _, word in result):
        return []
    return [word for _, word in result]


def main():
    import time
    import xbmc
    import xbmcgui

    monitor = xbmc.Monitor()
    window = xbmcgui.Window(10103)
    # GUI onload owns one worker for this keyboard instance. A fresh onload
    # supersedes a worker that has not yet observed the preceding close.
    owner = str(time.monotonic_ns())
    window.setProperty('BobiIME.Owner', owner)
    previous = None
    try:
        for _ in range(20):
            if xbmc.getCondVisibility('Window.IsActive(10103)'):
                break
            if monitor.waitForAbort(0.05):
                return
        while (not monitor.abortRequested()
               and xbmc.getCondVisibility('Window.IsActive(10103)')
               and window.getProperty('BobiIME.Owner') == owner):
            # Kodi 21 ControlLabel.getLabel() returns the Python wrapper's
            # original strText, NOT the native label changed by the IME.
            code = xbmc.getInfoLabel('Control.GetLabel(313)')
            raw = xbmc.getInfoLabel('Control.GetLabel(314)')
            layout = xbmc.getInfoLabel('Control.GetLabel(309)')
            if layout == 'Chinese BasePY':
                window.getControl(309).setLabel('中文拼音')
            current = (code, raw)
            words = candidates(code, raw)
            if current != previous:
                # Withdraw old buttons before publishing a different page.
                window.clearProperty('BobiIME.Ready')
                focused = window.getFocusId()
                if 500 <= focused <= 511:
                    window.setFocusId(120)
                window.setProperty('BobiIME.Code', code)
                window.setProperty('BobiIME.Page', raw)
                for i in range(10):
                    window.setProperty('BobiIME.Word' + str(i), words[i] if i < len(words) else '')
                # Labels can change between IPC reads while the user types.
                # Publish only a complete page which is still native-current.
                confirmed = (xbmc.getInfoLabel('Control.GetLabel(313)'),
                             xbmc.getInfoLabel('Control.GetLabel(314)'))
                if confirmed == current:
                    window.setProperty('BobiIME.Ready', '1' if words else '')
                    previous = current
                else:
                    previous = None
            if window.getProperty('BobiIME.Clear'):
                window.clearProperty('BobiIME.Clear')
                for _ in range(min(len(code), 256)):
                    xbmc.executebuiltin('SendClick(10103,8)')
                xbmc.executebuiltin('SendClick(10103,308)')
                xbmc.executebuiltin('SetFocus(120)')
            monitor.waitForAbort(0.1)
    except (RuntimeError, TypeError):
        # Closing a native dialog invalidates its controls. Do not log input.
        pass
    finally:
        if window.getProperty('BobiIME.Owner') == owner:
            for name in ['Owner', 'Ready', 'Clear', 'Code', 'Page'] + ['Word' + str(i) for i in range(10)]:
                window.clearProperty('BobiIME.' + name)


if __name__ == '__main__':
    main()
