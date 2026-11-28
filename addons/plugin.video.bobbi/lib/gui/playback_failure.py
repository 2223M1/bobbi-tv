"""Retire only Kodi's stock, non-interactive playback error on an owned retry."""


def retire_stock_error():
    import xbmc
    try:
        # This is a Kodi-owned window. Read its active skin labels through
        # the GUI info manager, never construct Python controls for it.
        matches = ('Window.IsActive(12002) + String.IsEqual(Control.GetLabel(1),$LOCALIZE[16026])'
                   ' + String.IsEqual(Control.GetLabel(9),$LOCALIZE[16027])')
        if not xbmc.getCondVisibility(matches):
            return False
        # Target this window ID. A message, consent prompt, or other modal is
        # never acknowledged by an untargeted Select/Back/Dialog.Close(all).
        xbmc.executebuiltin('Dialog.Close(12002,true)')
        return True
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False
