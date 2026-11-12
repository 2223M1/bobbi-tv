from threading import Thread
from uuid import uuid4

import xbmc
import xbmcgui

from lib.utils.kodi.utils import kodilog

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92


class SkipIntroWindow(xbmcgui.WindowXMLDialog):
    """
    Overlay dialog that shows a 'Skip Intro' or 'Skip Recap' button

    during playback when IntroDB segment data is available.
    """
    def __init__(self, xml_file, xml_location, segment_data=None, label="建议跳过片头", context=None):

        super().__init__(xml_file, xml_location)
        self.segment_data = segment_data or {}
        self.label = label
        self.action = None
        self.closed = False
        self.monitor_thread = None
        self.context = dict(context) if type(context) is dict else None
        self.submitted = False

    def onInit(self):
        self.setProperty("skip_label", self.label)
        self._start_background_monitor()

    def _start_background_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            return

        self.monitor_thread = Thread(target=self._background_monitor)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def _background_monitor(self):
        """Reuse this overlay's existing monitor; it owns no Kodi player."""
        try:
            while not self.closed:
                if not self._owner_call('segment_status').get('available'):
                    break
                xbmc.sleep(500)
        except (OSError, RuntimeError, ValueError, TypeError):
            pass  # Unknown/stale owner state grants no further action.

        if not self.closed:
            self.close()

    def onClick(self, control_id):
        if control_id == 4001:
            # Skip button pressed
            self.action = "skip"
            self._do_skip()
            self.close()
        elif control_id == 4002:
            # Dismiss button pressed
            self.action = "dismiss"
            self.close()

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (ACTION_PREVIOUS_MENU, ACTION_PLAYER_STOP, ACTION_NAV_BACK):
            self.action = "dismiss"
            self.close()

    def _do_skip(self):
        """Submit once to the original owner. Never fall back to global seek."""
        if self.submitted or self.closed:
            return False
        self.submitted = True
        try:
            return self._owner_call('segment_action', command_id=uuid4().hex).get('queued') is True
        except (OSError, RuntimeError, ValueError, TypeError):
            return False

    def _owner_call(self, operation, **values):
        if not self.context or not self.segment_data.get('segment_id'):
            return {}
        from lib.cinema.playback_ipc import call
        return call(dict(self.context, operation=operation,
                         segment_id=self.segment_data['segment_id'], **values))

    def close(self):
        self.closed = True
        super().close()
