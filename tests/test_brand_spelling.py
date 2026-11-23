"""Installed UI contract, independent of native RPC and historical proof fixtures."""
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / 'addons'
SKIN = ROOT / 'skin.bobbi.cinema'


def test_active_skin_and_plugin_paths_do_not_reintroduce_old_brand():
    for base in (SKIN, ROOT / 'plugin.video.bobbi'):
        for path in base.rglob('*'):
            if '__pycache__' not in path.parts:
                assert 'bobi' not in path.name.casefold(), path
    for base in (SKIN / '1080p', ROOT / 'plugin.video.bobbi/resources/skins/Default/1080i'):
        for xml in base.glob('*.xml'):
            tree = ET.parse(xml)
            for element in tree.iter():
                # The three one-way settings migrations are not presentation names.
                if xml.name == 'Home.xml' and element.tag == 'onload':
                    continue
                for value in [element.text or '', *element.attrib.values()]:
                    assert 'bobi' not in value.casefold(), (xml.name, value)


def test_named_font_family_is_inside_the_ttf_not_just_its_filename():
    used = {node.text for node in ET.parse(SKIN / '1080p/Font.xml').iter('filename')}
    for style in ('Regular', 'Medium', 'Semibold', 'Bold', 'CCMedium'):
        name = f'BobbiTV-{style}.ttf'
        assert name in used
        data = (SKIN / 'fonts' / name).read_bytes()
        tables = struct.unpack_from('>H', data, 4)[0]
        offset, = [struct.unpack_from('>I', data, pos + 8)[0]
                   for pos in range(12, 12 + 16*tables, 16) if data[pos:pos+4] == b'name']
        _, count, strings = struct.unpack_from('>HHH', data, offset)
        records = {}
        for i in range(count):
            platform, encoding, lang, key, size, start = struct.unpack_from('>6H', data, offset + 6 + 12*i)
            if (platform, encoding, lang) == (3, 1, 0x409):
                pos = offset + strings + start
                records[key] = data[pos:pos+size].decode('utf-16-be')
        assert (records[16], records[17], records[6]) == ('BobbiTV', style, 'BobbiTV-' + style)
