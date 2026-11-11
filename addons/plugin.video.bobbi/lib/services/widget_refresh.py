import contextlib
from time import time

import xbmc

from lib.utils.kodi.utils import (
    execute_builtin,
    get_property,
    get_setting,
    kodilog,
    notification,
)


class WidgetRefreshService:
    def __init__(self, monitor=None, host=None):
        self.monitor, self.host = monitor, host
        self.revisions = {}
        self.history_stamp = None
        self.history_database = None

    def _publish(self, key, value):
        previous = self.revisions.get(key)
        self.revisions[key] = value
        if previous == value:
            return
        import xbmcgui
        from lib.cinema.focus_anchor import bump
        bump(xbmcgui.Window(10000), key)

    def refresh_dependencies(self):
        """Existing tick, local reads only; don't start a catalogue or scan."""
        from lib.db.pickle_db import PickleDatabase
        from lib.db.file_history import KEY
        from lib.cinema.frontend_contract import history_digest
        import os
        try:
            if self.history_database is None:
                self.history_database = PickleDatabase()
            database = self.history_database
            stat = os.stat(database._database_path)
            stamp = stat.st_mtime_ns, stat.st_size
            if stamp != self.history_stamp:
                values = database.get_keys_checked(('jt:lfh', KEY))
                self._publish('continue_watching', history_digest(values))
                self.history_stamp = stamp
        except (OSError, ValueError):
            pass  # One broken history store cannot suppress library revisions.
        catalog = getattr(self.host, 'catalog', None)
        if catalog is not None:
            # Read the existing index's one-row projection stamp under its lock.
            with catalog.index.lock:
                row = catalog.index.db.execute('SELECT generation,revision FROM catalog_meta WHERE singleton=1').fetchone()
            if row is not None:
                self._publish('personal_library', (row['generation'], row['revision']))

    def run(self):
        kodilog("WidgetRefresh Service Starting...", level=xbmc.LOGINFO)
        monitor = self.monitor or xbmc.Monitor()
        player = xbmc.Player()
        wait_for_abort = monitor.waitForAbort

        if wait_for_abort(10):
            return
        self.set_next_refresh(time())

        while not monitor.abortRequested():
            try:
                if wait_for_abort(10):
                    break
                if (xbmc.getSkinDir() == 'skin.bobbi.cinema'
                        and xbmc.getCondVisibility('Window.IsActive(home)')
                        and not player.isPlayingVideo()
                        and get_property('bobbi.pause_services') != 'true'):
                    self.refresh_dependencies()
                offset = int(get_setting("widget_refresh_timer", 60))
                if offset != getattr(self, "offset", None):
                    self.set_next_refresh(time())
                    continue
                if self.condition_check(player):
                    continue
                if self.next_refresh < time():
                    kodilog(
                        "WidgetRefresh Service - Refreshing widgets...",
                        level=xbmc.LOGINFO,
                    )
                    self.refresh_widgets()
                    self.set_next_refresh(time())
            except Exception as e:
                kodilog(f"WidgetRefresh error: {e}", level=xbmc.LOGERROR)

        with contextlib.suppress(BaseException):
            del monitor
        with contextlib.suppress(BaseException):
            del player
        kodilog("WidgetRefresh Service Finished", level=xbmc.LOGINFO)

    def condition_check(self, player):
        container_plugin = xbmc.getInfoLabel("Container.PluginName")

        if "jacktook" in container_plugin or container_plugin == "plugin.video.bobbi":
            return True

        # No refrescar si está reproduciendo vídeo
        if player.isPlayingVideo():
            return True

        # No refrescar si los servicios están pausados (screensaver/sleep)
        if get_property("bobbi.pause_services") == "true":
            return True

        # No refrescar si el timer es 0 (desactivado)
        return self.next_refresh is None

    def set_next_refresh(self, _time):
        self.offset = int(get_setting("widget_refresh_timer", 60))
        if self.offset:
            self.next_refresh = _time + (self.offset * 60)
        else:
            self.next_refresh = None

    def refresh_widgets(self):
        if xbmc.getSkinDir() == 'skin.bobbi.cinema':
            self.refresh_dependencies()
            return
        execute_builtin("UpdateLibrary(video,special://skin/foo)")
        if xbmc.getSkinDir() != 'skin.bobbi.cinema' and get_setting("widget_refresh_notification", True):
            notification("Widgets Refreshed", time=2500)
