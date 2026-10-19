"""Static cross-platform design checks, not claims of TV screenshot validation."""
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOKENS = {
    'cinema_bg': ('bg', '0A0B0E'), 'cinema_surface': ('surface', '15171C'),
    'cinema_surface_hi': ('surface_hi', '1E2128'), 'cinema_line': ('surface_line', '2A2E37'),
    'cinema_text': ('text', 'F5F3EF'), 'cinema_text_secondary': ('text2', 'B4B2AD'),
    'cinema_text_muted': ('text3', '7E7D79'), 'cinema_disabled': ('text_disabled', '54545A'),
    'cinema_focus': ('focus', 'FFFFFF'), 'cinema_accent': ('accent', 'FF8A3D'),
    'cinema_accent_text': ('accent_text', 'FFB27F'),
}


def test_android_uses_reviewed_new_cinema_palette():
    colors = ET.parse(ROOT / 'android/app/src/main/res/values/colors.xml')
    values = {node.get('name'): node.text for node in colors.findall('color')}
    assert values == {key: '#' + rgb for key, (_, rgb) in TOKENS.items()}
    source = ROOT / 'staging/baseline/skin.bobbi.cinema/colors/defaults.xml'
    if source.exists():
        original = {node.get('name'): node.text for node in ET.parse(source).findall('color')}
        assert all(original[key] == 'FF' + rgb for key, rgb in TOKENS.values())


def test_remote_focus_and_reduced_motion_contract():
    text = (ROOT / 'android/app/src/main/java/org/bobbi/helper/CinemaStyle.java').read_text()
    assert 'FOCUS_MILLIS = 140' in text and 'FOCUS_SCALE = 1.02f' in text
    assert 'ValueAnimator.areAnimatorsEnabled()' in text
    assert 'item.animate().cancel()' in text
    assert 'state_focused' in text and '-android.R.attr.state_enabled' in text
    assert 'setMinHeight(dp(56))' in text


def test_fonts_are_unchanged_and_licensed_in_project_assets():
    expected = {
        'HarmonyOS_SansSC_Regular.ttf': '984cf609545acee8ef060780fb70fc3099b058c0553416331b6e863fdf7c26fa',
        'HarmonyOS_SansSC_Bold.ttf': 'c215d8ab1cb6709fec2e063f8213e9af86d7587d345b56325e36b67d6b947d98',
        'LICENCE-HarmonyOS-Sans.txt': '327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102',
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / 'assets/fonts' / name).read_bytes()).hexdigest() == digest
