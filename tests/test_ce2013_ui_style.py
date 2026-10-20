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
        assert any(node.get('colordiffuse') == 'FF15171C' for node in root.iter('texture'))
        assert all('BobiReduceMotion' in node.get('condition', '') for node in root.iter('animation'))
        for tag in ('texture', 'texturefocus', 'texturenofocus'):
            for node in root.iter(tag):
                text = node.text or ''
                if text.startswith('special://home/addons/'):
                    target = ROOT/'addons'/text.split('special://home/addons/', 1)[1]
                elif text.startswith('bobi/'):
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
