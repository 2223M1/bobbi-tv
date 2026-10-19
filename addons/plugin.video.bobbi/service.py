"""Portable base host plus the real native owner when that contract exists."""
import xbmc
from bobbi_platform.capabilities import probe
from bobbi_platform.kodi import rpc

capabilities = probe(rpc, 'android' if xbmc.getCondVisibility('System.Platform.Android') else 'kodi')
xbmc.log('[bobbi] startup; standard_playback=' + str(capabilities['standard_playback']), xbmc.LOGINFO)
from lib.portable_runtime import main
main(capabilities)
