"""New product UI uses the installed cinema assets, not invented font names."""
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT/'addons/skin.bobbi.cinema'


def test_account_cinema_fonts_exist_in_installed_skin():
    fonts = {node.text for node in ET.parse(SKIN/'1080p/Font.xml').findall('.//font/name')}
    source = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform/account_dialog.py'
    for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
        if isinstance(node, ast.keyword) and node.arg == 'font':
            assert isinstance(node.value, ast.IfExp)
            assert node.value.body.value in fonts


def test_new_panels_have_shared_palette_focus_motion_and_real_textures():
    paths = [
        ROOT/'addons/plugin.video.bobbi/resources/skins/Default/1080i/terminal-actions.xml',
        ROOT/'addons/script.module.bobbi.platform/resources/skins/Default/1080i/account-login.xml',
        ROOT/'addons/script.bobbi.setup/resources/skins/Default/1080i/tmdb-attribution.xml',
    ]
    for path in paths:
        root = ET.parse(path).getroot()
        assert root.find('defaultcontrol').get('always') == 'true'
        panels = [node for node in root.iter('texture') if (node.text or '').endswith('glass/modal-glass.png')]
        assert panels and all(node.get('border') == '46' for node in panels)
        if path.name == 'terminal-actions.xml':
            # The plugin XML cannot assume a named color in every external skin.
            # Compare its fallback by mode against the owning skin's actual palette.
            palette = ET.parse(SKIN/'colors/defaults.xml')
            variable = ET.parse(SKIN/'1080p/Variables.xml').find(".//variable[@name='BobbiMattePanelColor']")
            live = next(v.text for v in variable.findall('value') if 'condition' not in v.attrib)
            classic = variable.find("value[@condition='!Skin.HasSetting(BobbiLiquidGlassEnabled)']").text
            expected = {'Skin.HasSetting(BobbiLiquidGlassEnabled)': live,
                        '!Skin.HasSetting(BobbiLiquidGlassEnabled)': palette.findtext(f"color[@name='{classic}']")}
            assert {ctrl.findtext('visible'): ctrl.find('texture').get('colordiffuse')
                    for ctrl in root.iter('control') if ctrl.find('texture') in panels} == expected
        else:
            assert {node.get('colordiffuse') for node in panels} == {'FF15171C'}
        focus = list(root.iter('texturefocus'))
        assert focus and all(node.get('colordiffuse') == 'FFFFFFFF' for node in focus)
        for animation in root.iter('animation'):
            if animation.get('time') == '0' and animation.text == 'Conditional':
                # Instant material selection still applies with reduced motion.
                assert 'BobbiLiquidGlassEnabled' in animation.get('condition', '')
            else:
                assert '!Skin.HasSetting(BobbiReduceMotion)' in animation.get('condition', '')
        for tag in ('texture', 'texturefocus', 'texturenofocus'):
            for node in root.iter(tag):
                text = node.text or ''
                if text.startswith('special://home/addons/'):
                    target = ROOT/'addons'/text.split('special://home/addons/', 1)[1]
                elif text.startswith('bobbi/'):
                    target = SKIN/'media'/text
                else:
                    continue
                assert target.is_file(), text


def test_account_qr_cancel_button_has_no_login_or_playback_action():
    path = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform/account_dialog.py'
    value = path.read_text(encoding='utf-8')
    assert 'account_install' not in value and 'executebuiltin' not in value
    tree = ast.parse(value)
    click = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'onClick')
    assert 'self.cancelled = True' in ast.unparse(click)
