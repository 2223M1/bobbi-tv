"""One shared, drainable dependency worker; the owner only publishes revisions."""
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic, time

import xbmc


class WidgetRefreshService:
    def __init__(self, monitor=None, host=None, window=None, interval=10):
        self.monitor, self.host, self.window = monitor, host, window
        self.interval = interval
        self.stop = Event()
        self.worker = None
        self.mailbox = Queue(maxsize=1)
        self.revisions, self.observed = {}, {}
        self.pending = None
        self.history_stamp = self.history_database = None

    def start(self):
        if self.worker is None and not self.stop.is_set():
            worker = Thread(target=self.run, name='WidgetRefresh', daemon=True)
            worker.start()
            self.worker = worker

    def close(self):
        self.stop.set()
        if self.worker is not None:
            # The Host lease is released only after local IO actually returns.
            self.worker.join()

    def _offer(self, values):
        if self.stop.is_set() or not values:
            return
        self.observed.update(values)  # worker-owned snapshot, at most two keys
        try:
            self.mailbox.put_nowait(dict(self.observed))
        except Full:
            try:
                self.mailbox.get_nowait()
            except Empty:
                pass
            self.mailbox.put_nowait(dict(self.observed))

    def tick(self):
        """Owner thread: one bounded mailbox read and at most two Window writes."""
        try:
            self.pending = self.mailbox.get_nowait()
        except Empty:
            pass
        if self.pending is None or self.stop.is_set():
            return
        from lib.cinema.focus_anchor import bump
        for key, value in self.pending.items():
            if self.revisions.get(key) != value:
                bump(self.window, key)
                self.revisions[key] = value
        self.pending = None  # Failed writes stay pending for the next owner tick.

    def refresh_dependencies(self):
        """Worker only: local reads may be slow; never run on the playback owner."""
        from lib.db.pickle_db import PickleDatabase
        from lib.db.file_history import KEY
        from lib.cinema.frontend_contract import history_digest
        import os
        values = {}
        try:
            if self.history_database is None:
                self.history_database = PickleDatabase()
            database = self.history_database
            stat = os.stat(database._database_path)
            stamp = stat.st_mtime_ns, stat.st_size
            if stamp != self.history_stamp:
                snapshot = database.get_keys_checked(('jt:lfh', KEY))
                values['continue_watching'] = history_digest(snapshot)
                self.history_stamp = stamp
        except (OSError, ValueError):
            pass
        if self.stop.is_set():
            return
        catalog = getattr(self.host, 'catalog', None)
        # A scanner may own this lock for a long transaction. Skip this sample
        # instead of holding shutdown or the next dependency pass behind it.
        try:
            if catalog is not None and catalog.index.lock.acquire(blocking=False):
                try:
                    row = catalog.index.db.execute('SELECT generation,revision FROM catalog_meta WHERE singleton=1').fetchone()
                    if row is not None:
                        values['personal_library'] = (row['generation'], row['revision'])
                finally:
                    catalog.index.lock.release()
        finally:
            self._offer(values)

    def _wait(self, monitor):
        deadline = monotonic() + self.interval
        while not self.stop.is_set() and not monitor.abortRequested():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            if monitor.waitForAbort(min(.1, remaining)):
                return True
        return True

    def run(self):
        # Compatibility settings imports stay off the serialized owner thread.
        from lib.utils.kodi.utils import get_property, get_setting, kodilog
        monitor = self.monitor or xbmc.Monitor()
        player = xbmc.Player()
        self.set_next_refresh(time())
        while not self.stop.is_set() and not monitor.abortRequested():
            try:
                if xbmc.getSkinDir() == 'skin.bobbi.cinema':
                    if (xbmc.getCondVisibility('Window.IsActive(home)')
                            and not player.isPlayingVideo()
                            and get_property('bobbi.pause_services') != 'true'):
                        self.refresh_dependencies()
                else:
                    offset = int(get_setting('widget_refresh_timer', 60))
                    if offset != self.offset:
                        self.set_next_refresh(time())
                    elif not self.condition_check(player) and self.next_refresh < time():
                        self.refresh_widgets()
                        self.set_next_refresh(time())
            except Exception as error:
                kodilog('WidgetRefresh error: ' + type(error).__name__, level=xbmc.LOGERROR)
            if self._wait(monitor):
                return

    def condition_check(self, player):
        from lib.utils.kodi.utils import get_property
        plugin = xbmc.getInfoLabel('Container.PluginName')
        return ('jacktook' in plugin or plugin == 'plugin.video.bobbi'
                or player.isPlayingVideo() or get_property('bobbi.pause_services') == 'true'
                or self.next_refresh is None)

    def set_next_refresh(self, now):
        from lib.utils.kodi.utils import get_setting
        self.offset = int(get_setting('widget_refresh_timer', 60))
        self.next_refresh = now + self.offset * 60 if self.offset else None

    def refresh_widgets(self):
        if xbmc.getSkinDir() == 'skin.bobbi.cinema':
            self.refresh_dependencies()
            return
        from lib.utils.kodi.utils import execute_builtin, get_setting, notification
        execute_builtin('UpdateLibrary(video,special://skin/foo)')
        if get_setting('widget_refresh_notification', True):
            notification('Widgets Refreshed', time=2500)
