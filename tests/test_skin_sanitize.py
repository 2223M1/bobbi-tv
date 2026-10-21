import importlib.util
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sanitize_skin', ROOT / 'tools/sanitize_skin.py')
skin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skin)


def test_xml_preserves_layout_native_contract_and_maps_ids():
    raw = b'''<window><controls><control id="42" type="button"><left>120</left>
    <width>320</width><onclick>RunPlugin(plugin://plugin.video.jacktook/play)</onclick>
    <visible>Player.BobiNextReady</visible></control></controls></window>'''
    out, _ = skin.sanitize_xml(raw, '1080p/Test.xml')
    root = ET.fromstring(out)
    control = root.find('.//control')
    assert control.attrib == {'id': '42', 'type': 'button'}
    assert control.findtext('left') == '120'
    assert control.findtext('width') == '320'
    assert control.findtext('visible') == 'Player.BobiNextReady'
    assert 'plugin.video.bobbi' in control.findtext('onclick')


@pytest.mark.parametrize('command', [
    'RunScript(special://skin/scripts/record.py)',
    'RunScript(special://skin/scripts/skinupdate.py)',
    'System.ExecWait("/usr/sbin/rebootfromnand")',
    'Reboot()', 'InstallFromZip', 'UpdateAddonRepos',
    'RunAddon(service.coreelec.settings)',
    'RunAddon(service.libreelec.settings)',
    'RunScript(special://skin/scripts/unknown.py)',
])
def test_unsafe_actions_removed_without_secrets(command):
    raw = ('<window><controls><control type="button" id="5"><onclick>'
           + command + '</onclick></control></controls></window>').encode()
    out, count = skin.sanitize_xml(raw, '1080p/Test.xml')
    assert count == 1
    control = ET.fromstring(out).find('.//control')
    assert control.find('onclick') is None
    assert control.findtext('enable') == 'false'


def test_private_mount_becomes_unconfigured_browser():
    out, _ = skin.sanitize_xml(
        b'<window><onclick>ActivateWindow(Videos,/storage/videos/CloudNAS/CloudDrive,return)</onclick></window>',
        '1080p/Test.xml')
    assert ET.fromstring(out).findtext('onclick') == 'ActivateWindow(Videos)'


def test_icons_keep_nearby_free_glyphs_and_unknown_pua_fails():
    for glyph, label in skin.ICONS.items():
        raw = ('<window><font>BobiAFIcon</font><label>' + glyph + '</label></window>').encode()
        out, _ = skin.sanitize_xml(raw, '1080p/Test.xml')
        assert ET.fromstring(out).findtext('label') == label
        assert len(label) == 1 and ord(label) >= 0xe000
    assert skin.font_supports((ROOT / 'assets/fonts' / skin.ICON_FONT).read_bytes(), ''.join(skin.ICONS.values()))
    with pytest.raises(ValueError, match='private-use'):
        skin.sanitize_xml('<window><label>\ue000</label></window>'.encode(), '1080p/Test.xml')


def test_font_roles_are_all_remapped_and_missing_fonts_fail():
    raw = b'<fonts><fontset><font><name>Display72</name><filename>BobiDisplay.ttf</filename><size>72</size></font></fontset></fonts>'
    out, _ = skin.sanitize_xml(raw, '1080p/Font.xml')
    root = ET.fromstring(out)
    assert root.findtext('.//filename') == skin.BOLD
    assert root.findtext('.//size') == '72'
    with pytest.raises(ValueError, match='Missing'):
        skin.validate({'1080p/Font.xml': out})


def test_validator_rejects_credential_urls_without_echoing_values():
    font_xml = ('<fonts><font><filename>' + skin.REGULAR + '</filename></font></fonts>').encode()
    payload = {'1080p/Font.xml': font_xml, 'fonts/' + skin.REGULAR: b'dummy',
               'unsafe.md': b'https://example.invalid/api?access_token=synthetic-test-value'}
    with pytest.raises(ValueError, match='Credential-bearing URL') as error:
        skin.validate(payload)
    assert 'synthetic-test-value' not in str(error.value)


def test_actual_private_skin_restores_exact_fonts_but_not_legacy_scripts():
    source = ROOT / 'addons/skin.bobbi.cinema'
    # Store hashes, not private helper contents, so assertion diagnostics can
    # never spill encoded credentials from an excluded input script.
    before = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file()}
    output = source
    import json
    proof = json.loads((ROOT / 'release/private-assets.json').read_text(encoding='utf-8'))
    assert proof['source_commit'] == 'ff530e09c34c6285ccb05c1d4179140b097174fb'
    font_rows = [row for row in proof['files'] if row['target'].endswith('.ttf')]
    sound_rows = [row for row in proof['files'] if row['target'].endswith('.wav')]
    assert len(font_rows) == 14 and len(sound_rows) == 8
    for row in font_rows + sound_rows:
        assert hashlib.sha256((ROOT / row['target']).read_bytes()).hexdigest() == row['source_sha256'] == row['sha256']
    after = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source.rglob('*') if p.is_file()}
    assert before == after
    assert {Path(row['target']).name for row in font_rows} <= {p.name for p in (output / 'fonts').glob('*.ttf')}
    assert {p.name for p in (output / 'scripts').glob('*.py')} == skin.SAFE_SCRIPTS
    fonts = ET.parse(output / '1080p/Font.xml')
    assert all((output / 'fonts' / e.text).is_file() for e in fonts.iter('filename'))
    for font in skin.TEXT_FONTS:
        assert hashlib.sha256((output / 'fonts' / font).read_bytes()).hexdigest() == before['fonts/' + font]
    assert hashlib.sha256((output / 'fonts' / skin.ICON_FONT).read_bytes()).hexdigest() == skin.ICON_SHA256
    assert not (output / 'fonts' / skin.ICON_LICENSE).exists()
    assert skin.font_supports((output / 'fonts/BobiAF-Solid.ttf').read_bytes(), '\uf058\uf01b\uf13e\uf1ab\uf6ff\uf55a\uf0a8\uf0a9\uf05c')
    addon = ET.parse(output / 'addon.xml').getroot()
    assert addon.get('id') == 'skin.bobbi.cinema'
    assert addon.get('version') == ET.parse(source / 'addon.xml').getroot().get('version')
    assert all(d.get('version') == '0.1.0' for d in addon.findall('./requires/import') if 'bobbi' in d.get('addon', ''))
    assert addon.find('.//screenshot') is None
    for file in (output / '1080p').glob('*.xml'):
        for node in ET.parse(file).iter():
            assert not skin.UNSAFE.search(node.text or ''), file.name
            assert not skin.MOUNT.search(node.text or ''), file.name
    for file in output.rglob('*'):
        if file.is_file() and file.suffix in ('.xml', '.py'):
            text = file.read_text(encoding='utf-8')
            assert 'b64decode' not in text and 'token_part' not in text
            assert 'plugin.video.jacktook' not in text
            assert 'skin.am6b.cinema' not in text
