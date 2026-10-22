import os
from threading import Event, Thread
from time import time

import xbmc
import xbmcaddon
import xbmcvfs

from lib.utils.kodi.settings import update_delay
from lib.utils.kodi.utils import (
    ADDON_VERSION,
    clear_cached_settings,
    clear_property,
    dialog_ok,
    get_kodi_version,
    get_property_no_fallback,
    get_setting,
    kodilog,
    set_property_no_fallback,
    set_setting,
    translatePath,
    translation,
)

first_run_update_prop = "bobbi.first_run_update"
pause_services_prop = "bobbi.pause_services"


def _start_optional_sync(module_name, class_name, flags, credentials=(), monitor=None):
    """Do not import provider clients or create idle threads for disabled sync."""
    if not all(str(get_setting(key)).lower() == "true" for key in flags):
        return None
    if not all(get_setting(key) for key in credentials):
        return None

    def run():
        try:
            from importlib import import_module
            service_type = getattr(import_module(module_name), class_name)
            service = service_type(monitor=monitor) if monitor is not None else service_type()
            # Each service retains its own auth/profile checks and stop loop.
            service.run()
        except Exception as error:
            kodilog(class_name + " failed: " + type(error).__name__, level=xbmc.LOGERROR)

    thread = Thread(target=run, name=class_name, daemon=True)
    thread.start()
    return thread


def updates_check_addon(*args, **kwargs):
    # Keep the existing updater and test seam; import only on its auxiliary job.
    from lib.updater import updates_check_addon as update
    return update(*args, **kwargs)


class CheckKodiVersion:
    def run(self):
        kodilog("Checking Kodi version...")
        if get_kodi_version() < 20:
            dialog_ok(
                heading=xbmcaddon.Addon().getAddonInfo("name"),
                line1=translation(90559),
            )


class DatabaseSetup:
    def run(self):
        from lib.api.nuvio_store import setup_nuvio_database
        from lib.api.trakt.base_cache import setup_databases
        setup_databases()
        setup_nuvio_database()


class UpdateCheck:
    def __init__(self, monitor=None):
        self.monitor = monitor

    def run(self):
        kodilog("Update Check Service Started...", level=xbmc.LOGINFO)
        if get_property_no_fallback(first_run_update_prop) == "true":
            kodilog("Update check already performed, skipping...", level=xbmc.LOGINFO)
            return

        try:
            end_pause = time() + update_delay()
            monitor = self.monitor or xbmc.Monitor()
            player = xbmc.Player()

            while not monitor.abortRequested():
                while time() < end_pause:
                    if monitor.waitForAbort(1):
                        return
                while player.isPlayingVideo():
                    if monitor.waitForAbort(1):
                        return
                if monitor.abortRequested():
                    return
                set_property_no_fallback(first_run_update_prop, "true")
                updates_check_addon(automatic=True)
                break

            kodilog("Update Check Service Finished", level=xbmc.LOGINFO)
        except Exception as e:
            kodilog(e, level=xbmc.LOGERROR)


def TMDBHelperAutoInstall():
    import lib.cinema  # Bootstrap the independently packaged core in Kodi.
    from bobbi_core.deployment import PINNED_RUNTIME

    if PINNED_RUNTIME:
        # The coordinated installer owns the reviewed profile-level adapter.
        # Startup must never rewrite another pinned addon's resources or replace
        # a user's player configuration with the upstream legacy adapter.
        kodilog("Pinned AM6B profile: automatic TMDBHelper player sync disabled.")
        return

    bobbi_select_path = "special://home/addons/plugin.video.bobbi/bobbi.select.json"

    if not xbmcvfs.exists(bobbi_select_path):
        kodilog("bobbi.select.json file not found!", level=xbmc.LOGERROR)
        return

    target_addons = [
        "plugin.video.themoviedb.helper",
        "plugin.video.tmdb.bingie.helper",
    ]

    source_content = _read_text_file(bobbi_select_path)
    if source_content is None:
        kodilog("Unable to read bundled bobbi.select.json", level=xbmc.LOGERROR)
        return

    for addon_id in target_addons:
        # Query Kodi's installed-addon condition before constructing Addon().
        # Kodi logs an Unknown addon exception internally before Python can catch
        # RuntimeError, so exception-only probing pollutes every service start.
        if not xbmc.getCondVisibility(f"System.HasAddon({addon_id})"):
            kodilog(
                f"{addon_id} is optional and not installed; skipping player-file sync.",
                level=xbmc.LOGINFO,
            )
            continue
        _ = xbmcaddon.Addon(addon_id)

        tmdb_helper_path = (
            f"special://home/addons/{addon_id}/resources/players/bobbi.select.json"
        )

        target_content = _read_text_file(tmdb_helper_path)
        if target_content == source_content:
            continue

        target_dir = os.path.dirname(translatePath(tmdb_helper_path))
        if target_dir and not xbmcvfs.exists(target_dir):
            xbmcvfs.mkdirs(target_dir)

        if xbmcvfs.exists(tmdb_helper_path):
            xbmcvfs.delete(tmdb_helper_path)

        ok = xbmcvfs.copy(bobbi_select_path, tmdb_helper_path)
        if ok:
            kodilog(
                f"Installed or updated bobbi.select.json file for {addon_id}!",
                level=xbmc.LOGINFO,
            )
        else:
            kodilog(
                f"Error installing bobbi.select.json file for {addon_id}!",
                level=xbmc.LOGERROR,
            )


def _read_text_file(path):
    translated_path = translatePath(path)
    if not translated_path or not os.path.exists(translated_path):
        return None

    try:
        with open(translated_path, encoding="utf-8") as file_obj:
            return file_obj.read()
    except OSError as error:
        kodilog(f"Failed to read {path}: {error}", level=xbmc.LOGERROR)
        return None


class DownloaderSetup:
    def run(self):
        download_dir = get_setting("download_dir")
        translated_path = translatePath(download_dir)
        if not xbmcvfs.exists(translated_path):
            xbmcvfs.mkdir(translated_path)


class DebridExpirationCheck:
    def run(self):
        kodilog("Debrid Expiration Check Service Started...", level=xbmc.LOGINFO)
        if not get_setting("debrid_expiration_enabled"):
            return

        try:
            threshold = int(get_setting("debrid_expiration_threshold", 3))

            def notify_expiration(name, days):
                from lib.utils.kodi.utils import notification, translation

                if days == 0:
                    msg = translation(90231) % name
                else:
                    msg = translation(90230) % (name, days)
                notification(msg, time=5000)

            if get_setting("real_debrid_enabled") and get_setting("real_debrid_token"):
                from lib.api.debrid.realdebrid import RealDebrid

                rd = RealDebrid(str(get_setting("real_debrid_token", "")))
                days = rd.days_remaining()
                if days is not None and days <= threshold:
                    notify_expiration("Real-Debrid", days)

            alldebrid_token = get_setting("alldebrid_token")
            if get_setting("alldebrid_enabled") and alldebrid_token:
                from lib.api.debrid.alldebrid import AllDebrid

                ad = AllDebrid(str(alldebrid_token))
                days = ad.days_remaining()
                if days is not None and days <= threshold:
                    notify_expiration("AllDebrid", days)

            if get_setting("torbox_enabled") and get_setting("torbox_token"):
                from lib.api.debrid.torbox import Torbox

                tb = Torbox(get_setting("torbox_token"))
                days = tb.days_remaining()
                if days is not None and days <= threshold:
                    notify_expiration("Torbox", days)

            if get_setting("premiumize_enabled") and get_setting("premiumize_token"):
                from lib.api.debrid.premiumize import Premiumize

                pm = Premiumize(str(get_setting("premiumize_token", "")))
                days = pm.days_remaining()
                if days is not None and days <= threshold:
                    notify_expiration("Premiumize", days)

            if get_setting("debrider_enabled") and get_setting("debrider_token"):
                from lib.api.debrid.debrider import Debrider

                db = Debrider(get_setting("debrider_token"))
                days = db.days_remaining()
                if days is not None and days <= threshold:
                    notify_expiration("Debrider", days)

        except Exception as e:
            kodilog(f"Error in DebridExpirationCheck: {e}", level=xbmc.LOGERROR)


class JacktookMOnitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        from queue import Queue
        self._playback_events = Queue(maxsize=128)
        self._playback_event_overflow = False
        self._owner_stopped = Event()
        self._auxiliary_thread = None
        self._auxiliary_status = 'NOT_STARTED'
        self._auxiliary_workers = []
        self._control = None

    def run_owner_loop(self, host=None):
        from lib.services.playback_control import PlaybackControlServer
        control = PlaybackControlServer(events=self._playback_events)
        self._control = control
        if host is not None:
            host.playback = self
            control.authority.configure_accounts(host.accounts)
            host.bind_owner(control.authority.dispatch, control.authority.account_changed)
            control.native.subtitle_fallback.share_provider = host.sidecar_candidate
            control.native.subtitle_fallback.accounts = host.accounts
        xbmc.log('[BOBI-OWNER-BOOT] playback socket bound; entering owner loop', xbmc.LOGINFO)
        try:
            # Bind the authoritative owner before optional startup work. A slow
            # migration/provider/helper must not prevent the IPC loop starting.
            self._auxiliary_thread = Thread(target=self._start_auxiliary_services,
                                            name='JacktookAuxiliaryStartup', daemon=True)
            self._auxiliary_thread.start()
            while not self.abortRequested() and (host is None or not host.stopping.is_set()):
                if self._playback_event_overflow:
                    # Never keep issuing playback actions after losing ordering.
                    raise RuntimeError('Playback receipt queue overflow; owner stopped')
                control.tick()
                if host is not None:
                    host.tick()
                # Kodi dispatches pending Python notifications in waitForAbort,
                # not abortRequested or Python's selector.select. Keep this on
                # the owner interpreter/thread so window/terminal events reach
                # the ordered queue even when no IPC client is connected.
                # Zero means an infinite wait in this fork; use a finite value.
                if self.waitForAbort(.01):
                    break
        finally:
            self._owner_stopped.set()
            if host is not None:
                host.bind_owner(None)
            if host is None:
                self.close()

    def close(self):
        self._owner_stopped.set()
        errors = []
        try:
            if self._control is not None:
                xbmc.log('[BOBBI-SHUTDOWN] native control begin', xbmc.LOGINFO)
                self._control.close()
                self._control = None
                xbmc.log('[BOBBI-SHUTDOWN] native control drained', xbmc.LOGINFO)
        except BaseException as error:
            errors.append(error)
        # Startup can still be registering child jobs. Drain it before taking
        # the final child inventory; Kodi's addon abort wakes their stop loops.
        if self._auxiliary_thread is not None:
            xbmc.log('[BOBBI-SHUTDOWN] auxiliary startup join ' + self._auxiliary_status, xbmc.LOGINFO)
            self._auxiliary_thread.join()
        for worker in self._auxiliary_workers:
            xbmc.log('[BOBBI-SHUTDOWN] auxiliary worker join ' + worker.name, xbmc.LOGINFO)
            worker.join()
        xbmc.log('[BOBBI-SHUTDOWN] auxiliary workers drained', xbmc.LOGINFO)
        if errors:
            raise errors[0]

    def _start_worker(self, target):
        worker = Thread(target=target, daemon=True)
        worker.start()
        return worker

    def _worker_monitor(self):
        from bobbi_platform.stop_monitor import StopMonitor
        return StopMonitor(self._owner_stopped, xbmc.Monitor())

    def _start_auxiliary_services(self):
        self._auxiliary_status = 'RUNNING'
        try:
            self.startServices()
            self._auxiliary_status = 'STOPPED' if self._owner_stopped.is_set() else 'COMPLETE'
        except Exception as error:
            self._auxiliary_status = 'FAILED'
            # Preserve a real diagnostic without copying provider credentials.
            kodilog('Auxiliary startup failed: ' + type(error).__name__, level=xbmc.LOGERROR)

    def startServices(self):
        if self._owner_stopped.is_set() or self.abortRequested():
            return
        # These existing modules import provider clients and database helpers.
        # Load them on the existing auxiliary thread, after owner socket bind.
        from lib.services.migrations import run_migrations
        from lib.services.preloader import StartupPreloader
        operations = (
            lambda: set_setting("addon_version", ADDON_VERSION),
            # Isolated invokers cannot share import-only warmup. Keep the real
            # persistent catalog preloader below as the startup cache warmer.
            lambda: CheckKodiVersion().run(),
            lambda: DatabaseSetup().run(), run_migrations,
            lambda: self._start_worker(UpdateCheck(self._worker_monitor()).run),
            lambda: _start_optional_sync("lib.services.trakt_sync", "TraktSyncService",
                                         ("trakt_enabled", "is_trakt_auth"), monitor=self._worker_monitor()),
            lambda: _start_optional_sync("lib.services.simkl_sync", "SimklSyncService",
                                         ("simkl_enabled", "simkl_authenticated"),
                                         ("simkl_access_token",), monitor=self._worker_monitor()),
            lambda: _start_optional_sync("lib.services.nuvio_sync", "NuvioSyncService",
                                         ("nuvio_enabled", "nuvio_authenticated"),
                                         ("nuvio_access_token", "nuvio_profile_id"), monitor=self._worker_monitor()),
            lambda: (self._start_worker(DebridExpirationCheck().run)
                     if get_setting("debrid_expiration_enabled") else None),
            lambda: StartupPreloader(self._worker_monitor()).run(), lambda: DownloaderSetup().run(), TMDBHelperAutoInstall,
        )
        for operation in operations:
            if self._owner_stopped.is_set() or self.abortRequested():
                return
            worker = operation()
            if isinstance(worker, Thread):
                self._auxiliary_workers.append(worker)
        if self._owner_stopped.is_set() or self.abortRequested():
            return
        try:
            from lib.services.autostart import AutoStartService

            AutoStartService().run()
        except Exception as e:
            kodilog(f"AutoStart failed: {e}", level=xbmc.LOGERROR)
        if self._owner_stopped.is_set() or self.abortRequested():
            return
        try:
            from lib.services.widget_refresh import WidgetRefreshService

            self._auxiliary_workers.append(self._start_worker(WidgetRefreshService(self._worker_monitor()).run))
        except Exception as e:
            kodilog(f"WidgetRefresh failed: {e}", level=xbmc.LOGERROR)

    def onScreensaverActivated(self):
        set_property_no_fallback(pause_services_prop, "true")
        kodilog("PAUSING Jacktook Services Due to Device Sleep", level=xbmc.LOGINFO)

    def onScreensaverDeactivated(self):
        clear_property(pause_services_prop)
        kodilog("UNPAUSING Jacktook Services Due to Device Awake", level=xbmc.LOGINFO)

    def onSettingsChanged(self):
        clear_cached_settings()
        from lib.utils.tmdb_init import ensure_tmdb_init

        ensure_tmdb_init()
        kodilog(
            "Cleared cached settings and refreshed TMDB language after Kodi settings change",
            level=xbmc.LOGINFO,
        )

    def onNotification(self, sender, method, data):
        if sender == 'xbmc' and method in ('Player.OnBobiState', 'Player.OnBobiWindow'):
            from queue import Full
            try:
                if not isinstance(data, str) or len(data) > 16384:
                    return
                self._playback_events.put_nowait((sender, method, data))
            except Full:
                self._playback_event_overflow = True
            return
        # Generic OnPlay/OnStop and unknown item descriptors are never relayed
        # as evidence about a desired request. Legacy playback keeps its own
        # native Player callback path; exact playback uses the owner above.
        if method == "System.OnSleep":
            set_property_no_fallback(pause_services_prop, "true")
            kodilog(
                "PAUSING Jacktook Services Due to Device Sleep",
                level=xbmc.LOGINFO,
            )
        elif method == "System.OnWake":
            clear_property(pause_services_prop)
            kodilog(
                "UNPAUSING Jacktook Services Due to Device Awake",
                level=xbmc.LOGINFO,
            )
