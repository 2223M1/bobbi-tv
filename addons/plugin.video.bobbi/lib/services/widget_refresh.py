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
        self.catalog_views_revision = ''
        self._emby_seen_revisions = {}
        self._emby_sources_cache = (0.0, ())
        self._active_emby_sources = None
        self._pending_container = None
        self._last_refreshed_container = None

    @staticmethod
    def _parse_library_folder(folder):
        if not isinstance(folder, str) or 'plugin.video.bobbi.library' not in folder:
            return False, '', ''
        from urllib.parse import parse_qs, urlsplit
        parsed = urlsplit(folder)
        qs = parse_qs(parsed.query)
        return True, qs.get('source', [''])[0], qs.get('revision', [''])[0]

    def _profile_identity(self):
        return (getattr(self.host, 'root', None), getattr(self.host, 'plugin_root', None))

    @property
    def _pending_container_source(self):
        return None if self._pending_container is None else self._pending_container['source_id']

    @_pending_container_source.setter
    def _pending_container_source(self, value):
        if value is None:
            self._pending_container = None
            return
        folder = xbmc.getInfoLabel('Container.FolderPath') if hasattr(xbmc, 'getInfoLabel') else ''
        in_lib, sid, gen = self._parse_library_folder(folder)
        matched = folder if (in_lib and (sid == value or (not sid and value in folder))) else None
        self._pending_container = {
            'profile': self._profile_identity(),
            'source_id': value,
            'generation': gen if matched is not None else '',
            'revision': None,
            'container': matched,
        }

    def _schedule_container_refresh(self, source_id, generation, revision, container):
        profile_id = self._profile_identity()
        dedup = (profile_id, source_id, generation, revision, container)
        if revision is not None and self._last_refreshed_container == dedup:
            return
        self._pending_container = {
            'profile': profile_id,
            'source_id': source_id,
            'generation': generation,
            'revision': revision,
            'container': container,
        }

    def start(self):
        if self.worker is None and not self.stop.is_set():
            worker = Thread(target=self.run, name='WidgetRefresh', daemon=True)
            worker.start()
            self.worker = worker

    def close(self):
        self.stop.set()
        worker = self.worker
        if worker is not None and worker.is_alive():
            # The Host lease is released only after local IO actually returns.
            worker.join()

    def _offer(self, values):
        if self.stop.is_set() or not values or not self._profile_current():
            return
        self.observed.update(values)  # worker-owned snapshot, bounded keys
        try:
            self.mailbox.put_nowait(dict(self.observed))
        except Full:
            try:
                self.mailbox.get_nowait()
            except Empty:
                pass
            self.mailbox.put_nowait(dict(self.observed))

    def _flush_pending_container_refresh(self):
        rec = self._pending_container
        if rec is None or self.stop.is_set():
            return
        if rec['profile'] != self._profile_identity():
            self._pending_container = None
            return
        if rec['revision'] is None and 'emby_server' in self.revisions:
            rec['revision'] = self.revisions['emby_server']
        if (
            rec['generation']
            and self._active_emby_sources is not None
            and (rec['source_id'], rec['generation']) not in self._active_emby_sources
        ):
            self._pending_container = None
            return
        folder = xbmc.getInfoLabel('Container.FolderPath') if hasattr(xbmc, 'getInfoLabel') else ''
        in_lib, folder_sid, folder_gen = self._parse_library_folder(folder)
        source_matches = folder_sid == rec['source_id'] if folder_sid else rec['source_id'] in folder
        if not in_lib or not source_matches:
            self._pending_container = None
            return
        if rec['generation'] and folder_gen and folder_gen != rec['generation']:
            self._pending_container = None
            return
        if rec['container'] is not None and folder != rec['container']:
            self._pending_container = None
            return
        if rec['container'] is None:
            rec['container'] = folder
            if not rec['generation'] and folder_gen:
                rec['generation'] = folder_gen
        modal = bool(xbmc.getCondVisibility('System.HasModalDialog')) if hasattr(xbmc, 'getCondVisibility') else False
        if modal:
            return
        dedup = (rec['profile'], rec['source_id'], rec['generation'], rec['revision'], folder)
        if rec['revision'] is not None and self._last_refreshed_container == dedup:
            self._pending_container = None
            return
        try:
            xbmc.executebuiltin('Container.Refresh')
        except Exception:
            return  # Retain pending state for retry if builtin dispatch fails.
        if rec['revision'] is not None:
            self._last_refreshed_container = dedup
        self._pending_container = None

    def tick(self):
        """Owner thread: one bounded mailbox read and Window revision updates."""
        if not self._profile_current():
            self.pending = None
            self._pending_container = None
            self._last_refreshed_container = None
            return
        try:
            self.pending = self.mailbox.get_nowait()
        except Empty:
            pass
        if self.stop.is_set():
            return
        if self.pending is not None:
            from lib.cinema.focus_anchor import bump
            for key, value in self.pending.items():
                if self.revisions.get(key) != value:
                    bump(self.window, key)
                    self.revisions[key] = value
            self.pending = None  # Failed writes stay pending for the next owner tick.
        self._flush_pending_container_refresh()

    def refresh_dependencies(self):
        """Worker only: local reads may be slow; never run on the playback owner."""
        if not self._profile_current():
            return
        from lib.db.pickle_db import PickleDatabase
        from lib.db.file_history import KEY
        from lib.db.catalog_views import KEY as VIEWS_KEY
        from lib.cinema.frontend_contract import history_digest
        import os
        values = {}
        try:
            if self.history_database is None:
                root = getattr(self.host, 'plugin_root', None)
                self.history_database = PickleDatabase(profile_root=root) if root is not None else PickleDatabase()
            database = self.history_database
            stat = os.stat(database._database_path)
            stamp = stat.st_mtime_ns, stat.st_size
            if stamp != self.history_stamp:
                snapshot = database.get_keys_checked(('jt:lfh', KEY, VIEWS_KEY))
                values['continue_watching'] = history_digest({key: value for key, value in snapshot.items() if key != VIEWS_KEY})
                self.catalog_views_revision = history_digest(snapshot.get(VIEWS_KEY))
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
                        values['personal_library'] = (row['generation'], row['revision'], self.catalog_views_revision)
                finally:
                    catalog.index.lock.release()
        finally:
            self._offer(values)

    def _profile_current(self):
        check = getattr(self.host, 'check_profile', None)
        try:
            return check() if check is not None else True
        except (OSError, ValueError, RuntimeError):
            return False

    def refresh_emby_realtime(self):
        """Worker only: bounded Emby WS invalidation check (<=5s) + 25s poll fallback (<=30s)."""
        if not self._profile_current():
            return
        root = getattr(self.host, 'root', None)
        emby_rt = getattr(self.host, '_emby_runtime', None)
        if root is None or not callable(emby_rt):
            return
        reg_path = root / 'libraries.sqlite3'
        if not reg_path.is_file():
            self._active_emby_sources = set()
            return
        now = monotonic()
        cached_at, emby_sources = self._emby_sources_cache
        if now - cached_at >= 5.0:
            try:
                from bobbi_platform.libraries import Registry
                store = Registry(reg_path, read_only=True, timeout=0.05)
                try:
                    found = []
                    for src in store.sources():
                        if src.kind == 'media_server' and src.metadata.get('provider') == 'emby' and src.password:
                            _, rev = store.source_snapshot(src.id)
                            found.append((src.id, rev))
                    emby_sources = tuple(found)
                finally:
                    store.close()
                self._emby_sources_cache = (now, emby_sources)
            except Exception:
                return
        self._active_emby_sources = set(emby_sources)
        if not emby_sources:
            return
        on_home = xbmc.getCondVisibility('Window.IsActive(home)') if hasattr(xbmc, 'getCondVisibility') else False
        folder = xbmc.getInfoLabel('Container.FolderPath') if hasattr(xbmc, 'getInfoLabel') else ''
        in_lib, folder_sid, folder_gen = self._parse_library_folder(folder)
        if not on_home and not in_lib:
            return
        hub, _ = emby_rt()
        revs = []
        for sid, gen in emby_sources:
            if self.stop.is_set():
                return
            hub.ensure_ws_listener(sid, gen)
            snap = hub.poll_server_digest(sid, gen)
            revs.append(f"{sid[:8]}:{snap['revision']}")
            prev_rev = self._emby_seen_revisions.get((sid, gen))
            self._emby_seen_revisions[(sid, gen)] = snap['revision']
            if prev_rev is not None and snap['revision'] != prev_rev:
                source_matches = folder_sid == sid if folder_sid else sid in folder
                if in_lib and source_matches and (not folder_gen or folder_gen == gen):
                    # Synced confirmation happens in emby_dynamic only after directory readback succeeds.
                    self._schedule_container_refresh(sid, gen, snap['revision'], folder)
        if revs:
            joined = ','.join(revs)
            self._offer({
                'emby_server': joined,
                'emby_resume': joined,
                'emby_recent': joined,
            })

    def _wait(self, monitor, seconds=None):
        deadline = monotonic() + (self.interval if seconds is None else seconds)
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
        next_local_due = 0.0
        while not self.stop.is_set() and not monitor.abortRequested():
            try:
                if xbmc.getSkinDir() == 'skin.bobbi.cinema':
                    if (not player.isPlayingVideo()
                            and get_property('bobbi.pause_services') != 'true'):
                        now_m = monotonic()
                        if xbmc.getCondVisibility('Window.IsActive(home)') and now_m >= next_local_due:
                            self.refresh_dependencies()
                            next_local_due = now_m + self.interval
                        self.refresh_emby_realtime()
                else:
                    offset = int(get_setting('widget_refresh_timer', 60))
                    if offset != self.offset:
                        self.set_next_refresh(time())
                    elif not self.condition_check(player) and self.next_refresh < time():
                        self.refresh_widgets()
                        self.set_next_refresh(time())
            except Exception as error:
                kodilog('WidgetRefresh error: ' + type(error).__name__, level=xbmc.LOGERROR)
            if self._wait(monitor, seconds=1.0 if xbmc.getSkinDir() == 'skin.bobbi.cinema' else None):
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
