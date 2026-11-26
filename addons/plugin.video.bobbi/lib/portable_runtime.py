"""One portable host; retain the existing native owner when actually present."""
from pathlib import Path
import sys
import time

_HOST_UI_STATE = {'android_locale': None}


def _detect_vs10_support(*, sys_root=Path('/sys'), platform_name=None):
    plat = sys.platform if platform_name is None else platform_name
    if not str(plat).startswith('linux'):
        return False
    root = Path(sys_root)
    try:
        if (root / 'module/amdolby_vision').exists():
            return True
    except OSError:
        pass
    dv_cap = root / 'class/amhdmitx/amhdmitx0/dv_cap'
    try:
        if dv_cap.is_file():
            with dv_cap.open('rb') as handle:
                handle.read(64)
            return True
    except OSError:
        pass
    return False


def _sync_android_locale(*, force=False):
    try:
        from bobbi_platform import android_engine
        from bobbi_platform.i18n import current_locale
        if not android_engine.available():
            _HOST_UI_STATE['android_locale'] = None
            return None
        loc = current_locale()
        if not force and _HOST_UI_STATE.get('android_locale') == loc:
            return None
        reply = android_engine.sync_ui_locale(loc)
        _HOST_UI_STATE['android_locale'] = loc
        return reply
    except Exception:
        return None


def _sync_host_ui_properties(*, force_locale=True, sys_root=Path('/sys'), platform_name=None):
    try:
        import xbmcgui
        supports_vs10 = _detect_vs10_support(sys_root=sys_root, platform_name=platform_name)
        xbmcgui.Window(10000).setProperty('Bobbi.Host.SupportsVS10', 'true' if supports_vs10 else '')
    except Exception:
        pass
    try:
        from bobbi_platform.glass_settings import sync_runtime_property
        sync_runtime_property()
    except Exception:
        pass
    return _sync_android_locale(force=force_locale)


def main(capabilities=None):
    import xbmc
    from sqlite3 import Error as SQLiteError
    from bobbi_platform.host import Host
    from bobbi_platform.paths import ProfileBinding
    from bobbi_platform.kodi import rpc
    from bobbi_core.runtime_paths import configure, native_subtitle_abi
    capabilities = capabilities or {}
    native = capabilities.get('native_contract_available') is True
    abi = native_subtitle_abi(capabilities)
    binding = ProfileBinding()
    plugin_root = binding.root('plugin.video.bobbi')
    subtitle_root = configure(plugin_root, subtitle_root=abi['root'] if abi else None,
              native_sha256=abi['sha256'] if abi else None, current=binding.is_current)
    report = lambda code: xbmc.log('[bobbi] ' + code, xbmc.LOGINFO)
    try:
        from lib.db.file_history import FileHistory
        from lib.db.pickle_db import PickleDatabase
        file_history = FileHistory(PickleDatabase(profile_root=plugin_root), report=report)
    except (ImportError, OSError, ValueError, RuntimeError, SQLiteError):
        file_history = None  # Playback can run without history, never with a global fallback.
    try:
        from bobbi_platform.server_accounts import PlexBinding
        import xbmcaddon
        plex_settings = xbmcaddon.Addon('plugin.video.bobbi')
        def read_plex():
            binding.require_current()
            return dict(location=plex_settings.getSetting('plex_streaming_url'),
                token=plex_settings.getSetting('plex_server_token'), user_token=plex_settings.getSetting('plex_token'))
        plex_binding = PlexBinding(read_plex, binding.is_current)
    except (ImportError, OSError, ValueError, RuntimeError):
        plex_binding = None  # Optional Plex settings cannot stop other sources/playback.
        report('PLEX_BINDING_UNAVAILABLE')
    host = Host(binding.root(), report=report,
                native_rpc=rpc if native else None, profile_current=binding.is_current,
                plugin_root=plugin_root, file_history=file_history, plex_binding=plex_binding,
                subtitle_root=subtitle_root)
    if file_history is None:
        host.report('FILE_HISTORY_UNAVAILABLE')
    presentation = revisions = None
    next_locale_poll = [0.0]
    def tick_presentation():
        now = time.monotonic()
        if now >= next_locale_poll[0]:
            next_locale_poll[0] = now + 2.0
            _sync_android_locale(force=False)
        if presentation is not None:
            try:
                presentation.tick()
            except Exception:
                pass  # Optional Home presentation cannot stop either playback owner.
    try:
        host.start()
        _sync_host_ui_properties(force_locale=True)
        try:
            import xbmcgui
            from lib.cinema.focus_anchor import HomeRailLifecycle
            from lib.services.widget_refresh import WidgetRefreshService
            window = xbmcgui.Window(10000)
            revisions = WidgetRefreshService(host=host, window=window)
            presentation = HomeRailLifecycle(host, window, refresh=revisions.tick)
            revisions.start()
        except Exception:
            host.report('HOME_PRESENTATION_UNAVAILABLE')
        host.can_quiesce = lambda: not xbmc.Player().isPlaying()
        host.configure_preparation(plugin_root)
        def idle():
            host.source_libraries.observe_host(host)
            host.playing = xbmc.Player().isPlaying()
            return not host.playing and xbmc.getGlobalIdleTime() >= 30
        # Remote refresh is attached lazily only after an explicit URL is saved.
        host.idle_probe = idle
        if native:
            # Keep the original actor on the Kodi thread, including ordered
            # events, subtitles and continuation. No stock fake receipt path.
            from lib.services.background_service import JacktookMOnitor
            JacktookMOnitor().run_owner_loop(host=host, presentation_tick=tick_presentation)
        else:
            from lib.services.standard_playback import StandardPlayback
            standard = StandardPlayback(host)
            monitor = xbmc.Monitor()
            while not host.stopping.is_set() and not monitor.waitForAbort(.1):
                host.tick()
                if not host.stopping.is_set():
                    tick_presentation()
                    standard.tick()
    finally:
        try:
            if presentation is not None:
                presentation.close()
        except Exception:
            host.report('HOME_PRESENTATION_CLOSE_UNAVAILABLE')
        finally:
            try:
                if revisions is not None:
                    revisions.close()
            finally:
                host.close()
