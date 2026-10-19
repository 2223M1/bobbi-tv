"""Mechanical namespacing + explicit stock-route overlay, local review only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'a9189b5d157d886c814cf28c6748c97fc6825a35'
IDS = {
    'plugin.video.jacktook': 'plugin.video.bobbi',
    'script.module.am6b.core': 'script.module.bobbi.core',
    'script.module.am6b.mdsub': 'script.module.bobbi.mdsub',
    'script.module.am6b.qqdocs': 'script.module.bobbi.catalog',
    'script.am6b.opensubtitles': 'script.bobbi.subtitles',
    'skin.am6b.cinema': 'skin.bobbi.cinema',
    'am6b_core': 'bobbi_core', 'am6b_mdsub': 'bobbi_mdsub', 'am6b_qqdocs': 'bobbi_catalog',
}
TEXT = {'.py', '.xml', '.json', '.md', '.txt', '.po', '.html', '.css', '.js'}


def rename(text):
    for old, new in IDS.items():
        text = text.replace(old, new)
    # Independent Kodi global properties as well as independent addon data.
    return (text.replace('jacktook.', 'bobbi.').replace('jacktook_', 'bobbi_')
            .replace('lib.bobbi.', 'lib.jacktook.'))  # Internal package directory is not an addon ID.


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Pinned migration anchor changed')
    return text.replace(before, after)


def transform(name, raw):
    text = rename(raw.decode('utf-8-sig'))
    if name.endswith('/lib/clients/maintainable_ui.py'):
        # This is the actual new-UI TopBar -> mine -> am6b_home route.
        # Keep existing entries/layout rather than reviving legacy skin menus.
        text = once(text, "    if action == 'am6b_home':\n        return [\n",
            "    if action == 'am6b_home':\n        return [\n"
            "            ('我的网盘 / NAS / 个人片库', 'plugin://plugin.video.bobbi.library/',\n"
            "             '浏览自己添加的 SMB、NFS、WebDAV、本机目录和直链片库；手动选片，不转码。'),\n"
            "            ('添加与管理我的来源', 'plugin://plugin.video.bobbi.library/?action=manage',\n"
            "             '新增、修改或移除本机连接配置；不会删除网盘和 NAS 的媒体文件。'),\n")
    if name.endswith('/lib/utils/torrent/torrserver_utils.py'):
        text = once(text, 'from lib.vendor.bencodepy import bencodepy',
                    'from lib.utils.torrent import flatbencode as bencodepy')
    if name.endswith('/lib/gui/source_select.py'):
        start, end = text.index('    def doModal(self) -> bool:\n'), text.index('    def close(self):\n')
        text = text[:start] + (
            '    def doModal(self) -> bool:\n'
            '        from lib.portable import manual_modal\n'
            '        return manual_modal(self, lambda: super(SourceSelect, self).doModal())\n\n'
        ) + text[end:]
        start = text.index('    def _handle_context_menu_action(self):\n')
        end = text.index('    def _handle_quality_select_action(self):\n', start)
        text = text[:start] + (
            '    def _handle_context_menu_action(self):\n'
            '        xbmcgui.Dialog().ok("bobbi", "后台下载、云任务及字幕上传尚未完成通用版适配。")\n\n'
        ) + text[end:]
        start = text.index('        if not pack_select and not is_subtitle_download:\n')
        end = text.index('    def show_resume_dialog(', start)
        text = text[:start] + (
            '        from lib.portable import queue_selected\n'
            '        return queue_selected(self, selected_source, pack_select, is_subtitle_download, local_subtitle_path)\n\n'
        ) + text[end:]
    if name.endswith('/lib/utils/kodi/utils.py'):
        start, end = text.index('def cancel_playback():\n'), text.index('def finish_action():\n')
        text = text[:start] + (
            'def cancel_playback():\n'
            '    # Portable cancellation must never stop global playback or clear playlists.\n'
            '    return None\n\n\n'
        ) + text[end:]
    if name.endswith('/lib/bobbi_core/cd2.py'):
        text, count = re.subn(r'^BASE = .+$', 'BASE = ""  # Explicit user configuration required.', text, flags=re.M)
        if count != 1:
            raise ValueError('CD2 endpoint migration anchor changed')
        text = once(text, '    def __init__(self, token=None, base=BASE):\n',
            '    def __init__(self, token=None, base=BASE):\n'
            '        if not base:\n'
            '            raise CD2Error("not_configured")\n')
    if name.endswith('/lib/utils/tmdb_init.py'):
        text, count = re.subn(r'get_setting\("tmdb_api_key", "[^"]*"\)', 'get_setting("tmdb_api_key", "")', text)
        if count != 1:
            raise ValueError('TMDb setting migration anchor changed')
    if name.endswith('/resources/settings.xml'):
        xml = ET.fromstring(text)
        for setting in xml.iter('setting'):
            key = setting.get('id', '')
            default = setting.find('default')
            if default is None:
                continue
            if key in {'tmdb_api_key', 'trakt_secret', 'trakt_client'}:
                default.text = ''
            if key in {'auto_play', 'super_quick_play', 'torrent_enable', 'auto_update', 'auto_start_jacktook'}:
                default.text = 'false'
        text = ET.tostring(xml, encoding='unicode')
    if name.endswith('/addon.xml'):
        xml = ET.fromstring(text)
        xml.set('version', '0.1.0')
        if xml.get('id') == 'plugin.video.bobbi':
            xml.set('name', 'bobbi Cinema · 移植预览')
            xml.set('provider-name', 'bobbi TV / Sam-Max and contributors')
            ET.SubElement(xml.find('requires'), 'import', addon='script.module.bobbi.platform', version='0.1.0')
            ET.SubElement(xml.find('requires'), 'import', addon='plugin.video.bobbi.library', version='0.1.0')
        for dependency in xml.findall('./requires/import'):
            if 'bobbi' in dependency.get('addon', ''):
                dependency.set('version', '0.1.0')
        for license in xml.findall('./extension/license'):
            license.text = 'GPL-3.0; see LICENSE and THIRD-PARTY notices'
        text = ET.tostring(xml, encoding='unicode')
    return text.encode('utf-8')


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.parent != ROOT / 'build':
        raise ValueError('Use a new direct child of ignored build')
    proof = json.loads((source / 'export-manifest.json').read_text(encoding='utf-8'))
    if (proof.get('schema') != 1 or proof.get('baseline') != BASELINE
            or proof.get('status') != 'QUARANTINE_NOT_INSTALLABLE'):
        raise ValueError('Unknown quarantine export provenance')
    records = {}
    for addon in ('plugin.video.bobbi', 'script.module.bobbi.core'):
        if not (source / addon / 'addon.xml').is_file():
            raise ValueError('Required source component missing: ' + addon)
        actual = {p.relative_to(source).as_posix() for p in (source / addon).rglob('*') if p.is_file()}
        approved = {p for p in proof['files'] if p.startswith(addon + '/')}
        if actual != approved:
            raise ValueError('Quarantine inventory drift: ' + addon)
        for path in sorted((source / addon).rglob('*')):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError('No symlink migration input')
            original = path.relative_to(source).as_posix()
            name = rename(original)
            if path.suffix.lower() in {'.zip', '.sqlite3', '.db'}:
                raise ValueError('Private archive/database escaped quarantine filter')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != proof['files'][original]['sha256']:
                raise ValueError('Quarantine file changed: ' + original)
            if '/lib/vendor/bencodepy/' in name:
                # Incompatible/unresolved legacy notice; the existing MIT
                # flatbencode implementation replaces its only active import.
                continue
            converted = transform(name, raw) if path.suffix in TEXT or path.name == 'LICENSE' else raw
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(converted)
            records[name] = {'original': original, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                             'candidate_sha256': hashlib.sha256(converted).hexdigest()}
    for path in sorted((ROOT / 'overlays').rglob('*')):
        if path.is_file() and path.suffix in TEXT:
            name = path.relative_to(ROOT / 'overlays').as_posix()
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            records[name] = {'overlay': name, 'candidate_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {'schema': 1, 'status': 'local-port-review-not-release', 'files': records,
              'blocked': ['license closure', 'platform paths and subprocess providers',
                          'BT/115 backend', 'native or stock continuation', 'device acceptance']}
    (output / 'migration.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return {'files': len(records), 'status': report['status']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'staging/baseline')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/portable-candidate')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output)))
