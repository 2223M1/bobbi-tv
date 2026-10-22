import xbmc

from lib.utils.kodi.logging import kodilog
from lib.utils.kodi.utils import execute_builtin, get_setting


class AutoStartService:
    def run(self):
        if get_setting("auto_start_jacktook", False):
            kodilog("AutoStart: Launching bobbi TV on boot...", level=xbmc.LOGINFO)
            execute_builtin("RunAddon(plugin.video.bobbi)")
        else:
            kodilog("AutoStart: Disabled by user.", level=xbmc.LOGINFO)
