"""Public updates belong to Kodi's bobbi repository, never upstream overwrite."""
import xbmc
from lib.utils.kodi.utils import ADDON_VERSION

CHANGELOG_PATH = 'special://home/addons/plugin.video.bobbi/CHANGELOG.md'


def updates_check_addon(automatic=False):
    if not automatic:
        xbmc.executebuiltin('RunScript(script.bobbi.setup,updates)')


def get_versions():
    return ADDON_VERSION, None


def get_changes(online_version=None):
    from lib.utils.kodi.utils import dialog_text
    dialog_text('bobbi TV · 更新记录', file=CHANGELOG_PATH)
