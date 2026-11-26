"""Offline installed version notes and About viewer (R3-SET-02)."""
from pathlib import Path
import xml.etree.ElementTree as ET
from .i18n import is_english, tr

MAX_NOTES_BYTES = 256 * 1024


def _default_addon_root():
    try:
        import xbmcvfs
        translated = xbmcvfs.translatePath('special://home/addons/plugin.video.bobbi')
        if translated and not str(translated).startswith('special://'):
            cand = Path(translated)
            if cand.exists():
                return cand
    except Exception:
        pass
    repo_cand = Path(__file__).resolve().parents[4] / 'addons' / 'plugin.video.bobbi'
    if repo_cand.exists():
        return repo_cand
    return None


def installed_plugin_version(addon_xml_path=None):
    if addon_xml_path is None:
        try:
            import xbmcaddon
            ver = str(xbmcaddon.Addon('plugin.video.bobbi').getAddonInfo('version') or '').strip()
            if ver:
                return ver
        except Exception:
            pass
        root = _default_addon_root()
        addon_xml_path = (root / 'addon.xml') if root is not None else None
    if addon_xml_path is not None:
        path = Path(addon_xml_path)
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536:
                return str(ET.parse(path).getroot().attrib.get('version') or '').strip()
        except (OSError, ET.ParseError):
            pass
    return ''


def default_changelog_path():
    root = _default_addon_root()
    return (root / 'CHANGELOG.md') if root is not None else None


def read_installed_notes(changelog_path=None, installed_version=None):
    en = is_english()
    version = str(installed_version if installed_version is not None else installed_plugin_version()).strip()
    path = Path(changelog_path) if changelog_path is not None else default_changelog_path()
    base_heading = tr(32095, '关于波比 TV 与版本说明', 'About bobbi TV & Release Notes')
    heading = base_heading + ((' · ' + version) if version else '')
    if en:
        header_line = (
            'Installed Version · ' + (version or 'Unknown version')
            + '\nSource · Bundled offline package (check "Cinema Setup · Updates & Recovery" for online updates)\n\n'
        )
        missing_line = 'Local release notes for the installed version are missing or unreadable.'
    else:
        header_line = (
            '当前已安装版本 · ' + (version or '未知版本')
            + '\n说明来源 · 本机已安装离线包（在线新版本请到“影院设置 · 更新与恢复”检查）\n\n'
        )
        missing_line = '当前已安装版本的本地说明文件缺失或暂不可读。'
    if path is None:
        return {
            'available': False,
            'version': version,
            'matched_version': False,
            'title': heading,
            'body': header_line + missing_line,
        }
    try:
        if (path.is_symlink() or any(p.is_symlink() for p in path.parents)
                or not path.is_file()):
            raise OSError('missing changelog')
        size = path.stat().st_size
        if not 0 < size <= MAX_NOTES_BYTES:
            raise OSError('invalid changelog size')
        text = path.read_text(encoding='utf-8').strip()
        if not text:
            raise OSError('empty changelog')
    except (OSError, UnicodeDecodeError):
        return {
            'available': False,
            'version': version,
            'matched_version': False,
            'title': heading,
            'body': header_line + missing_line,
        }
    matched = (not version) or (version in text)
    if not matched:
        mismatch_note = (
            'Note · No dedicated entry for installed version ' + version + ' was found in local notes; showing bundled offline changelog.\n\n'
            if en else
            '提示 · 本地说明文件未找到当前已安装版本 ' + version + ' 的专门条目，以下为随包离线记录。\n\n'
        )
    else:
        mismatch_note = ''
    return {
        'available': True,
        'version': version,
        'matched_version': matched,
        'title': heading,
        'body': header_line + mismatch_note + text,
    }


def show_about(dialog=None, *, changelog_path=None, installed_version=None):
    import xbmcgui
    from bobbi_core.project_metadata import ATTRIBUTION
    dialog = dialog or xbmcgui.Dialog()
    notes = read_installed_notes(changelog_path=changelog_path, installed_version=installed_version)
    full_text = notes['body'] + '\n\n---\n' + ATTRIBUTION
    dialog.textviewer(notes['title'], full_text)
    return notes
