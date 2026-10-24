"""One portable host; retain the existing native owner when actually present."""


def main(capabilities=None):
    import xbmc
    from bobbi_platform.host import Host
    from bobbi_platform.paths import profile
    from bobbi_platform.kodi import rpc
    from bobbi_core.runtime_paths import configure, native_subtitle_abi
    capabilities = capabilities or {}
    native = capabilities.get('native_contract_available') is True
    abi = native_subtitle_abi(capabilities)
    configure(profile('plugin.video.bobbi'), subtitle_root=abi['root'] if abi else None,
              native_sha256=abi['sha256'] if abi else None)
    host = Host(profile(), report=lambda code: xbmc.log('[bobbi] ' + code, xbmc.LOGINFO),
                native_rpc=rpc if native else None)
    try:
        host.start()
        host.can_quiesce = lambda: not xbmc.Player().isPlaying()
        host.configure_preparation(profile('plugin.video.bobbi'))
        def idle():
            host.playing = xbmc.Player().isPlaying()
            return not host.playing and xbmc.getGlobalIdleTime() >= 30
        # Local preparation still needs playback state; no remote refresh job.
        host.idle_probe = idle
        if native:
            # Keep the original actor on the Kodi thread, including ordered
            # events, subtitles and continuation. No stock fake receipt path.
            from lib.services.background_service import JacktookMOnitor
            JacktookMOnitor().run_owner_loop(host=host)
        else:
            from lib.services.standard_playback import StandardPlayback
            standard = StandardPlayback(host)
            monitor = xbmc.Monitor()
            while not host.stopping.is_set() and not monitor.waitForAbort(.1):
                host.tick()
                if not host.stopping.is_set():
                    standard.tick()
    finally:
        host.close()
