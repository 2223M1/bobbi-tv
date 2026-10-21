"""Restore the owner's pinned CE typography/sounds, never legacy executables."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from prepare_candidate import rename
from sanitize_skin import font_supports, sanitize_xml
from provenance_document import write_source

ROOT = Path(__file__).resolve().parents[1]
REV = 'ff530e09c34c6285ccb05c1d4179140b097174fb'
SKIN = 'ui-redesign/source/addons/skin.am6b.cinema/'
SOUND = 'ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/'
SOUND_ID = 'resource.uisounds.bobbi-modern'


def restore(repo):
    def read(name):
        return subprocess.check_output(['git', '-C', str(repo), 'show', REV + ':' + name])
    names = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', REV,
                                     '--', SKIN + 'fonts', SOUND]).decode().splitlines()
    records = []
    def put(source, destination, data=None):
        original = read(source)
        value = original if data is None else data
        target = ROOT / destination
        write_source(ROOT, destination, value)
        records.append(dict(source=source, target=destination, bytes=len(value),
                            source_sha256=hashlib.sha256(original).hexdigest(),
                            sha256=hashlib.sha256(value).hexdigest()))
    for name in names:
        if name.startswith(SKIN + 'fonts/'):
            put(name, 'addons/skin.bobbi.cinema/' + name[len(SKIN):])
        elif name.startswith(SOUND):
            relative = name[len(SOUND):]
            if relative not in {'addon.xml', 'LICENSE', 'README.md', 'resources/sounds.xml'} and not (
                relative.startswith('resources/') and Path(relative).suffix.lower() == '.wav'):
                continue
            raw = read(name)
            if relative == 'addon.xml':
                raw = raw.replace(b'resource.uisounds.am6b-modern', SOUND_ID.encode())
            put(name, 'addons/' + SOUND_ID + '/' + relative, raw)
    # Font.xml contains declarations only, not actions or executable helpers.
    name = SKIN + '1080p/Font.xml'
    fonts = rename(read(name).decode('utf-8-sig')).encode('utf-8')
    for filename in ET.fromstring(fonts).iter('filename'):
        if not (ROOT / 'addons/skin.bobbi.cinema/fonts' / filename.text).is_file():
            raise ValueError('Missing restored font: ' + filename.text)
    put(name, 'addons/skin.bobbi.cinema/1080p/Font.xml', fonts)
    # Restore exactly the historical Pro glyph; retain every sanitized action.
    for path in (ROOT / 'addons/skin.bobbi.cinema/1080p').glob('*.xml'):
        raw = path.read_text(encoding='utf-8')
        if '\uf057' in raw:
            path.write_text(raw.replace('\uf057', '\uf05c'), encoding='utf-8')
    icons = (ROOT / 'addons/skin.bobbi.cinema/fonts/BobiAF-Solid.ttf').read_bytes()
    if not font_supports(icons, '\uf058\uf01b\uf13e\uf1ab\uf6ff\uf55a\uf0a8\uf0a9\uf05c'):
        raise ValueError('Original icon font does not cover keyboard glyphs')
    # The only skin functional delta since the public baseline: latest season hub.
    name = SKIN + '1080p/Includes_Views.xml'
    converted, _ = sanitize_xml(read(name), '1080p/Includes_Views.xml')
    put(name, 'addons/skin.bobbi.cinema/1080p/Includes_Views.xml', converted)
    report = dict(schema=1, source_commit=REV, distribution='private-personal', files=records,
                  rights='Original notices retained; no blanket third-party redistribution grant asserted.',
                  excluded='Legacy auth, remote execution, firmware, updater and library-clearing scripts remain excluded.')
    write_source(ROOT, 'release/private-assets.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(dict(restored=len(records), fonts=sum(r['target'].endswith('.ttf') for r in records),
                         sounds=sum(r['target'].endswith('.wav') for r in records))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    restore(parser.parse_args().source)
