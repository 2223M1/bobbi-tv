"""Portable startup: never start the legacy Linux/native owner service."""
import xbmc
from bobbi_platform.capabilities import probe
from bobbi_platform.kodi import rpc

capabilities = probe(rpc, 'android' if xbmc.getCondVisibility('System.Platform.Android') else 'kodi')
xbmc.log('[bobbi] portable preview; standard_playback=' + str(capabilities['standard_playback']), xbmc.LOGINFO)
# No self-updater, webserver, system service, remote code or private account
# migration at startup. Coordinated updates stay gated pending lease validation.
