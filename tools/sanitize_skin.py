"""Create a review candidate from quarantined skin files, without editing input.

This preserves Kodi layout/control structure, not device certification. It does
not grant a new license to inherited code or artwork. No network is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
IDS = {
    'skin.am6b.cinema': 'skin.bobbi.cinema',
    'plugin.video.jacktook': 'plugin.video.bobbi',
    'script.am6b.opensubtitles': 'script.bobbi.subtitles',
    'script.module.am6b.core': 'script.module.bobbi.core',
    'script.module.am6b.mdsub': 'script.module.bobbi.mdsub',
    'script.module.am6b.qqdocs': 'script.module.bobbi.catalog',
}
REGULAR = 'HarmonyOS_SansSC_Regular.ttf'
MEDIUM = 'HarmonyOS_SansSC_Medium.ttf'
BOLD = 'HarmonyOS_SansSC_Bold.ttf'
ICON_FONT = 'fa-solid-900.ttf'
TEXT_FONTS = {REGULAR, MEDIUM, BOLD}
FONTS = TEXT_FONTS | {ICON_FONT}
ICON_SHA256 = 'af19d135d3a935b3ebfbd80320716ffe1202052c5f68dc2c5f1abc57005ac605'
FONT_MAP = {
    'BobiDisplay.ttf': BOLD, 'BobiAF-Solid.ttf': ICON_FONT,
    'MiSans-Regular.ttf': REGULAR, 'MiSans-Medium.ttf': MEDIUM,
    'MiSans-Semibold.ttf': BOLD, 'Roboto-Regular.ttf': REGULAR,
    'Roboto-Bold.ttf': BOLD, 'RobotoCJKSC-Regular.ttf': REGULAR,
    'NetflixSans-Regular.ttf': REGULAR, 'NetflixSans-Bold.ttf': BOLD,
    'fzltdhk.ttf': BOLD,
}
# Keep the nine keyboard controls as near-identical real icons. The legacy
# outline times-circle uses Free's solid circle-xmark at its current codepoint.
ICONS = {char: char for char in '\uf058\uf01b\uf13e\uf1ab\uf6ff\uf55a\uf0a8\uf0a9'}
ICONS['\uf05c'] = '\uf057'
SAFE_SCRIPTS = {'cinema_keyboard.py'}
SCRIPT_SHA256 = {'cinema_keyboard.py': 'dffa7451cf431bef47970eccb43b0b9eb8c168fd64fe330d887ac88fb52f5a2f'}
FONT_SUFFIXES = {'.ttf', '.otf', '.woff', '.woff2'}
ARCHIVES = {'.zip', '.rar', '.db', '.sqlite', '.sqlite3', '.pyc'}
UNSAFE = re.compile(
    r'System\.Exec(?:Wait)?\s*\(|\b(?:Reboot|RestartApp|Powerdown|'
    r'Shutdown|Suspend|Hibernate)\s*\(|\b(?:InstallFromZip|InstallAddon|'
    r'UpdateAddonRepos|UpdateLocalAddons)\b|'
    r'RunAddon\(\s*service\.(?:coreelec|libreelec)\.settings\s*\)|'
    r'(?:recordupdate|record|skinupdate|checkskinupdate|autostart|'
    r'cetranscpm|zidoov12|networksetup|rebootoff)\.py', re.I)
MOUNT = re.compile(r'/(?:storage|mnt|media|home)(?:/|\b)', re.I)
ACTION_TAGS = {'onclick', 'altclick', 'onload', 'onunload', 'onfocus',
               'onup', 'ondown', 'onleft', 'onright', 'onback', 'oninfo'}


def remap(text):
    """Only addon identifiers change; native Player.Bobi* names stay exact."""
    text = re.sub(r'\bskin\.confluence\.[A-Za-z0-9_-]+\b', 'skin.bobbi.cinema', text)
    for old, new in IDS.items():
        text = text.replace(old, new)
    return text


def font_supports(raw, characters):
    """Read Unicode cmap formats 4/12 using stdlib; require real glyph IDs."""
    tables = {}
    for i in range(struct.unpack_from('>H', raw, 4)[0]):
        tag, _, offset, _ = struct.unpack_from('>4sIII', raw, 12 + i * 16)
        tables[tag] = offset
    base = tables[b'cmap']
    supported = set()
    for i in range(struct.unpack_from('>H', raw, base + 2)[0]):
        platform, encoding, offset = struct.unpack_from('>HHI', raw, base + 4 + i * 8)
        if platform not in (0, 3) or platform == 3 and encoding not in (1, 10):
            continue
        start = base + offset
        fmt = struct.unpack_from('>H', raw, start)[0]
        for char in characters:
            code = ord(char)
            if fmt == 4 and code <= 0xffff:
                count = struct.unpack_from('>H', raw, start + 6)[0] // 2
                ends = start + 14
                starts = ends + 2 * count + 2
                deltas = starts + 2 * count
                ranges = deltas + 2 * count
                for j in range(count):
                    lo = struct.unpack_from('>H', raw, starts + j * 2)[0]
                    hi = struct.unpack_from('>H', raw, ends + j * 2)[0]
                    if lo <= code <= hi:
                        delta = struct.unpack_from('>h', raw, deltas + j * 2)[0]
                        distance = struct.unpack_from('>H', raw, ranges + j * 2)[0]
                        glyph = ((code + delta) & 0xffff) if not distance else struct.unpack_from(
                            '>H', raw, ranges + j * 2 + distance + (code - lo) * 2)[0]
                        if distance and glyph:
                            glyph = (glyph + delta) & 0xffff
                        if glyph:
                            supported.add(char)
                        break
            elif fmt == 12:
                groups = struct.unpack_from('>I', raw, start + 12)[0]
                for j in range(groups):
                    lo, hi, glyph = struct.unpack_from('>III', raw, start + 16 + j * 12)
                    if lo <= code <= hi and glyph + code - lo:
                        supported.add(char)
                        break
    return supported >= set(characters)


def sanitize_xml(raw, filename):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(remap(raw.decode('utf-8-sig')), parser=parser)
    removed = 0
    for parent in root.iter():
        for child in list(parent):
            if not isinstance(child.tag, str):
                continue
            text = child.text or ''
            for glyph, label in ICONS.items():
                text = text.replace(glyph, label)
            if any(0xe000 <= ord(c) <= 0xf8ff and c not in ICONS.values() for c in text):
                raise ValueError('Unreviewed private-use glyph in ' + filename)
            child.text = text
            action = child.tag in ACTION_TAGS or child.tag == 'param' and 'onclick' in child.get('name', '').lower()
            if action:
                local_scripts = re.findall(r'([\w-]+\.py)\b', text, flags=re.I)
                unsafe_script = any(s not in SAFE_SCRIPTS for s in local_scripts)
                if UNSAFE.search(text) or unsafe_script:
                    parent.remove(child)
                    removed += 1
                    if parent.tag == 'control' and parent.find('enable') is None:
                        ET.SubElement(parent, 'enable').text = 'false'
                    continue
                if MOUNT.search(text):
                    # Keep the user-facing file browser, but never preselect a
                    # private CoreELEC mount. Other mount actions are removed.
                    match = re.match(r'ActivateWindow\((Videos|music),', text, re.I)
                    if match:
                        child.text = 'ActivateWindow(' + match.group(1) + ')'
                    else:
                        parent.remove(child)
                        removed += 1
                        continue
            if child.tag == 'screenshot':
                parent.remove(child)
                removed += 1
    if filename == '1080p/Font.xml':
        for font in root.iter('font'):
            entry = font.find('filename')
            if entry is not None:
                entry.text = FONT_MAP.get(entry.text, entry.text)
                if entry.text not in FONTS:
                    raise ValueError('Unreviewed Font.xml reference')
    if filename == 'addon.xml':
        root.set('id', 'skin.bobbi.cinema')
        root.set('name', 'bobbi TV')
        root.set('version', '0.1.0')
        for dependency in root.findall('./requires/import'):
            if 'bobbi' in dependency.get('addon', ''):
                dependency.set('version', '0.1.0')
        # Preserve inherited authorship. The public fork is not the old repo.
        metadata = root.find("extension[@point='xbmc.addon.metadata']")
        if metadata is not None:
            source = metadata.find('source')
            if source is not None:
                metadata.remove(source)
            notice = ET.SubElement(metadata, 'description', {'lang': 'en_GB'})
            notice.text = 'bobbi TV cinema skin.'
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), removed


def validate(payloads):
    """Fail closed before creating an output directory."""
    fonts = ET.fromstring(payloads['1080p/Font.xml'])
    for entry in fonts.iter('filename'):
        if entry.text not in FONTS or 'fonts/' + entry.text not in payloads:
            raise ValueError('Missing or unreviewed font')
    for name, raw in payloads.items():
        if name.startswith('scripts/') and Path(name).name not in SAFE_SCRIPTS:
            raise ValueError('Unreviewed local script')
        if Path(name).suffix.lower() in {'.xml', '.py', '.json', '.txt', '.md'}:
            text = raw.decode('utf-8-sig')
            for url in re.findall(r'https?://[^\s<>"\']+', text):
                parsed = urlsplit(url)
                if parsed.username or parsed.password or re.search(
                        r'(?:^|&)(?:access_token|api_?key|token|secret|password|cookie|auth)=',
                        parsed.query, re.I):
                    raise ValueError('Credential-bearing URL rejected in ' + name)
        if name.endswith('.xml'):
            root = ET.fromstring(raw)
            for node in root.iter():
                text = node.text or ''
                if UNSAFE.search(text) or MOUNT.search(text):
                    raise ValueError('Unsafe action or mount remains in ' + name)
                if any(0xe000 <= ord(c) <= 0xf8ff and c not in ICONS.values() for c in text):
                    raise ValueError('Private-use glyph remains')


def sanitize(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir() or output.exists() or source == output or source in output.parents or output in source.parents:
        raise ValueError('Use an existing source and a new, separate output directory')
    payloads, excluded, modifications, originals = {}, [], {}, {}
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink inputs are not accepted')
        if not path.is_file():
            continue
        name = path.relative_to(source).as_posix()
        skip = (path.suffix.lower() in ARCHIVES
                or path.suffix.lower() in FONT_SUFFIXES and path.name not in FONTS
                or name.startswith('scripts/') and path.name not in SAFE_SCRIPTS
                or 'screenshot' in name.lower()
                or 'licen' in path.name.lower() or 'licence' in path.name.lower()
                or path.name.lower() in {'notice', 'notice.md', 'notice.txt', 'copying', 'copyright'}
                or name == 'ASSET-PROVENANCE.md')
        if skip:
            excluded.append(name)
            continue
        raw = path.read_bytes()
        if name.startswith('scripts/') and hashlib.sha256(raw).hexdigest() != SCRIPT_SHA256[path.name]:
            raise ValueError('Reviewed local helper hash mismatch')
        originals[name] = hashlib.sha256(raw).hexdigest()
        if path.suffix.lower() == '.xml':
            raw, removed = sanitize_xml(raw, name)
            if removed:
                modifications[name] = {'removed_actions_or_screenshots': removed}
        elif name.startswith('scripts/'):
            raw = remap(raw.decode('utf-8-sig')).encode('utf-8')
        payloads[name] = raw
    for filename in TEXT_FONTS:
        raw = payloads.get('fonts/' + filename)
        if raw is None or not font_supports(raw, '波比影院中文ABC0123'):
            raise ValueError('Font missing or replacement symbols unsupported')
    icon = (ROOT / 'assets/fonts' / ICON_FONT).read_bytes()
    if (hashlib.sha256(icon).hexdigest() != ICON_SHA256
            or not font_supports(icon, ''.join(ICONS.values()))):
        raise ValueError('Pinned icon font or required glyphs failed verification')
    payloads['fonts/' + ICON_FONT] = icon
    validate(payloads)
    report = {'schema': 1, 'status': 'SANITIZED_SKIN_REVIEW_CANDIDATE',
              'excluded': excluded, 'modifications': modifications,
              'input_sha256': originals,
              'output_sha256': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(payloads.items())},
              'native_protocol_names': 'Player.Bobi* preserved unchanged',
              'pending': ['real Kodi/Android layout and playback verification']}
    payloads['sanitization-manifest.json'] = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    output.mkdir(parents=True)
    for name, raw in sorted(payloads.items()):
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    return {'status': report['status'], 'files': len(payloads), 'excluded': len(excluded)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'staging/baseline/skin.bobbi.cinema')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/sanitized-skin')
    args = parser.parse_args()
    print(json.dumps(sanitize(args.source, args.output)))
