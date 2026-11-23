"""One route to confirmed updates, with non-interrupting discovery on managed CE installs."""
import xbmc
from lib.utils.kodi.utils import ADDON_VERSION

CHANGELOG_PATH = 'special://home/addons/plugin.video.bobbi/CHANGELOG.md'


def updates_check_addon(automatic=False, monitor=None):
    if not automatic:
        return xbmc.executebuiltin('RunScript(script.bobbi.setup,updates)')
    import xbmcgui
    from bobbi_platform.ce_update_notice import NoticeProfile, check
    binding = NoticeProfile()
    work = binding.root('script.bobbi.start')
    player = xbmc.Player()
    monitor = monitor or xbmc.Monitor()
    def cancelled():
        return (monitor.abortRequested() or player.isPlaying() or xbmc.getGlobalIdleTime() < 30
                or xbmc.getCondVisibility('System.HasModalDialog') or not binding.is_current())
    def notify(tag):
        xbmcgui.Dialog().notification('波比 TV 有新版本', tag + ' · 影院设置 → 更新与恢复', sound=False)
    return check(work, cancelled, notify)


def get_versions():
    return ADDON_VERSION, None


def get_changes(online_version=None):
    from lib.utils.kodi.utils import dialog_text
    dialog_text('bobbi TV · 更新记录', file=CHANGELOG_PATH)
