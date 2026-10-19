"""Stock Kodi long-lived service: renewable 115 reads, no private native IPC."""
import xbmc
from bobbi_platform.runtime import Runtime
from bobbi_core.share_stream import ShareStream
from bobbi_catalog.catalog import selected, resolve
from bobbi_catalog.api import valid_cdn


def arguments(body):
    return {key: body[key] for key in ('locator', 'guid', 'title', 'size', 'media')}


def main():
    monitor = xbmc.Monitor()
    from lib.api.trakt.base_cache import setup_databases
    setup_databases()  # Local tables only; never migrate or authenticate accounts.
    from bobbi_platform.native_engine import Engine
    engine = Engine()
    streams = ShareStream(validate=lambda body: selected(**arguments(body)),
        resolve=lambda body: resolve(**arguments(body)), validate_url=valid_cdn,
        report=lambda phase: xbmc.log('[bobbi] share: ' + phase, xbmc.LOGINFO),
        observer=lambda row: None)
    def dispatch(action, body):
        if monitor.abortRequested():
            raise ValueError('Runtime stopping')
        if action == 'share_open':
            return streams.register(body)
        if action == 'status':
            return {'ready': True, 'version': '0.1.0'}
        raise ValueError('Unsupported action')
    runtime = Runtime(dispatch)
    try:
        runtime.start()
        while not monitor.waitForAbort(1):
            if not xbmc.getCondVisibility('System.Platform.Android'):
                try:
                    engine.tick()
                except (ValueError, OSError):
                    xbmc.log('[bobbi] local engine unavailable; existing services untouched', xbmc.LOGWARNING)
    finally:
        runtime.close()
        streams.close()
        engine.close()
