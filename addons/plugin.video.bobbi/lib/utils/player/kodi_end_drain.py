"""Keep Kodi's application-level stop separate from the native EOF grant."""
import json
from time import monotonic

import xbmc


class VideoEndMonitor(xbmc.Monitor):
    """This announcement paces an already reserved child; it can never authorize one."""

    def __init__(self):
        super().__init__()
        self._ended_at = None

    def onNotification(self, sender, method, data):
        if sender != 'xbmc' or method != 'Player.OnStop' or not isinstance(data, str) or len(data) > 16384:
            return
        try:
            event = json.loads(data)
        except (ValueError, RecursionError):
            return
        if not isinstance(event, dict) or event.get('end') is not True:
            return
        player, item = event.get('player') or {}, event.get('item') or {}
        if (not isinstance(player, dict) or not isinstance(item, dict)
                or player.get('playerid', 1) != 1 or item.get('type') in ('song', 'album', 'picture')):
            return
        self._ended_at = monotonic()

    def wait_for_reserved_next(self, reserved_at, cancelled):
        # AM6B can declare native EOF several seconds before Kodi releases the old
        # video window. The receipt was already consumed, within its 3-second limit.
        # Accept an end notification delivered during that same terminal window.
        deadline = reserved_at + 12.0
        while not self.abortRequested() and not cancelled():
            now = monotonic()
            if self._ended_at is not None and self._ended_at >= reserved_at - 3.0:
                # Both physical controls successfully opened after this short
                # post-notification interval. If teardown is already done, don't wait again.
                if now - self._ended_at >= 1.1:
                    return 'ready'
            if now >= deadline:
                return 'timeout'
            if self.waitForAbort(min(.15, deadline - now)):
                break
        return 'cancelled'
