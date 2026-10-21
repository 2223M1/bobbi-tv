"""Legacy-window colors use current tokens without changing playback or layout."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema'
SCREENS = ('Includes_Compatibility.xml', 'Custom_1142_OSD_Cast.xml',
    'Custom_1140_OSD_Playlist.xml', 'custom_1126_Confirm.xml', 'IncludesHomeRecentlyAdded.xml',
    'script-cu-lrclyrics-main.xml', 'script-globalsearch.xml', 'SettingsProfile.xml',
    'SettingsSystemInfo.xml', 'ViewsVideoLibrary.xml', 'ViewsFileMode.xml', 'VideoOSDBookmarks.xml',
    'Custom_1196_BobiSearch.xml', 'IncludesCinema.xml', 'FileManager.xml')
OLD = ('FF03B585', 'FFE50914', 'FF87CEFA', 'FF12A0C7', 'FF64E535', 'FF0091EA',
       'FFFF8C00', 'FFAA0000', 'FF795548', 'FF004974', 'FFE50924', 'FFFFEA00',
       'FF00FFFF', 'FF00DD44', 'FFFF6B4A', 'FFE4D7F0', '8016A34A')


def test_skin_variable_and_expression_references_are_defined():
    definitions = {'VAR': set(), 'EXP': set()}
    references = []
    for path in (SKIN / '1080p').glob('*.xml'):
        raw = path.read_text(encoding='utf-8')
        root = ET.fromstring(raw)
        for kind, tag in [('VAR', 'variable'), ('EXP', 'expression')]:
            definitions[kind].update(node.get('name') for node in root.iter(tag))
        references.extend((kind, name, path.name) for kind, name in
                          re.findall(r'\$(VAR|EXP)\[([^,\]]+)', raw))
    assert not [(kind, name, path) for kind, name, path in references if name not in definitions[kind]]


def test_legacy_windows_retire_conflicting_brand_palette_not_neutral_alpha_masks():
    for name in SCREENS:
        raw = (SKIN / '1080p' / name).read_text(encoding='utf-8')
        assert not [color for color in OLD if re.search(color, raw, re.I)], name
        assert not re.search(r'(?:colordiffuse="blue"|<selectedcolor>blue</selectedcolor>)', raw), name
    raw = (SKIN / '1080p/Includes_Compatibility.xml').read_text(encoding='utf-8')
    assert '00000000' in raw
    # Duplicate unused defaults were removed; their alpha-mask styles now
    # live in the one effective Defaults.xml, not a second shadow copy.
    assert '40FFFFFF' in (SKIN / '1080p/Defaults.xml').read_text(encoding='utf-8')


def test_progress_completion_error_and_disabled_colors_remain_different():
    palette = {node.get('name'): node.text for node in ET.parse(SKIN/'colors/defaults.xml').getroot()}
    assert len({palette[name] for name in ('accent', 'ok', 'error', 'focus', 'text_disabled')}) == 5
    root = ET.parse(SKIN / '1080p/Includes_Compatibility.xml').getroot()
    progress = [node for node in root.iter('texture') if 'Defs_PercentPlayed' in (node.text or '')]
    watched = [node for node in root.iter('texture') if 'Defs_checkmark' in (node.text or '')]
    assert progress and all(node.get('colordiffuse') == 'accent' for node in progress)
    assert watched and all(node.get('colordiffuse') == 'ok' for node in watched)
    broken = [node for node in root.iter('control') if node.findtext('label') == '24098']
    assert broken and all(node.findtext('textcolor') == 'error' for node in broken)
    disabled = root.find(".//control[@id='90400']")
    assert disabled.findtext('enable') == 'false'
    assert '[COLOR text_disabled]' in disabled.findtext('label')


def test_added_person_expression_does_not_guess_media_identity_from_title():
    root = ET.parse(SKIN / '1080p/Variables.xml').getroot()
    expression = root.find("expression[@name='Exp_IsPersonInfo']")
    assert expression is not None
    assert set(expression.text.split(' | ')) == {
        'String.IsEqual(ListItem.DBType,actor)', 'String.IsEqual(ListItem.DBType,person)',
        'String.IsEqual(ListItem.Property(item.type),person)',
        'String.IsEqual(ListItem.Property(tmdb_type),person)'}


def test_new_semantic_tokens_resolve_and_weather_uses_existing_resource():
    palette = {node.get('name') for node in ET.parse(SKIN/'colors/defaults.xml').getroot()}
    tokens = {'accent', 'accent_text', 'ok', 'error', 'focus', 'surface_line', 'info', 'text2', 'text3', 'text_disabled'}
    assert tokens <= palette
    root = ET.parse(SKIN / '1080p/Includes_Compatibility.xml').getroot()
    values = root.find("variable[@name='GlobalBackgroundVar']").findall('value')
    weather = [node for node in values if 'Current.FanartCode' in (node.text or '')]
    assert len(weather) == 1
    assert weather[0].text == 'resource://resource.images.weatherfanart.multi/$INFO[Window(Weather).Property(Current.FanartCode)]'
    assert 'System.AddonIsEnabled(resource.images.weatherfanart.multi)' in weather[0].get('condition', '')


def test_brand_aliases_do_not_reintroduce_old_red_and_preserve_error_semantics():
    palette = {node.get('name'): node.text for node in ET.parse(SKIN/'colors/defaults.xml').getroot()}
    for alias, token in {'blue': 'accent', 'orange': 'accent', 'lightblue': 'accent_text',
                         'red': 'error', 'warning': 'warn'}.items():
        assert palette[alias] == palette[token]
    assert palette['red'] != palette['orange']
    for path in (SKIN/'1080p').glob('*.xml'):
        assert not re.search(r'FFE509(?:14|24)', path.read_text(encoding='utf-8'), re.I), path.name


def test_migrated_window_color_tokens_exist():
    palette = {node.get('name') for node in ET.parse(SKIN/'colors/defaults.xml').getroot()}
    tags = {'textcolor', 'selectedcolor', 'focusedcolor', 'disabledcolor', 'invalidcolor',
            'shadowcolor', 'colordiffuse', 'controllerdiffuse'}
    for name in SCREENS:
        root = ET.parse(SKIN/'1080p'/name).getroot()
        colors = [node.text.strip() for node in root.iter() if node.tag in tags and node.text]
        colors += [node.get('colordiffuse') for node in root.iter() if node.get('colordiffuse')]
        for value in colors:
            if '$' in value or re.fullmatch(r'[0-9A-Fa-f]{8}', value):
                continue
            assert value in palette, (name, value)
