"""Focus graph and effective defaults; screenshots remain a separate device gate."""
from pathlib import Path
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def effective_defaults():
    # Kodi's include loader follows file declarations in order and inserts the
    # first definition of each default type. A loose Defaults.xml is not loaded.
    seen, defaults = set(), {}
    def load(name):
        if name in seen:
            return
        seen.add(name)
        root = ET.parse(SKIN / name).getroot()
        for node in root.findall('default'):
            defaults.setdefault(node.get('type'), (name, node))
        for node in root.findall('include[@file]'):
            load(node.get('file'))
    load('Includes.xml')
    return defaults


def test_white_focus_controls_use_actual_loaded_dark_text_defaults():
    defaults = effective_defaults()
    for kind in ('button', 'radiobutton', 'edit'):
        source, node = defaults[kind]
        assert source == 'Defaults.xml'
        assert node.findtext('focusedcolor') == 'on_focus'
    assert defaults['selectbutton'][1].findtext('texturefocus') == 'bobi/row-focus.png'


def test_weather_spinner_keeps_overlay_label_and_white_arrows_on_dark_background():
    label = ET.parse(SKIN / 'MyWeather.xml').find(".//control[@id='301']")
    assert label.findtext('textcolor') == 'text'
    spinner = ET.parse(SKIN / 'MyWeather.xml').find(".//control[@type='spincontrolex'][@id='3']")
    assert spinner.findtext('texturefocus') == 'bobi/row-focus.png'
    assert list(spinner).index(spinner.find('texturefocus')) < list(spinner).index(spinner.find('include'))


def test_legacy_button_focus_background_agrees_with_new_default_text():
    for name in ('Custom_1195_AM6BStreamingHub.xml', 'DialogPVRChannelManager.xml',
                 'Includes_Compatibility.xml', 'SmartPlaylistEditor.xml', 'SmartPlaylistRule.xml',
                 'IncludesGames.xml', 'IncludesHomeAM6BStreaming.xml'):
        for node in ET.parse(SKIN / name).iter('control'):
            if node.get('type') not in ('button', 'edit', 'radiobutton'):
                continue
            focus = node.find('texturefocus')
            if focus is not None and focus.get('colordiffuse') == 'FF454545':
                assert node.findtext('focusedcolor') == 'text', (name, node.get('id'))
    for name, cid in [('Includes_Dialogs.xml','12'), ('DialogPVRGuideSearch.xml','9')]:
        node = ET.parse(SKIN / name).find(".//control[@type='edit'][@id='%s']" % cid)
        assert node.findtext('focusedcolor') == 'text'
    spinner = ET.parse(SKIN / 'DialogPVRChannelManager.xml').find(".//control[@type='spincontrolex'][@id='13']")
    assert spinner.findtext('texturefocus') == 'bobi/row-focus.png'


def test_personal_page_direction_keys_reach_header_card_and_right_column():
    root = ET.parse(SKIN / 'Custom_1197_BobiPersonal.xml')
    node = lambda cid: root.find(".//control[@id='%s']" % cid)
    assert node(9100).findtext('onup') == '9701'
    has = 'String.IsEqual(Container(9130).ListItem.Property(Bobi.Resume.State),ready)'
    for cid, direction, expected in ((9100, 'onright', ('9110','9101')),
                                     (9101, 'onup', ('9110','9701'))):
        assert [(n.get('condition'), n.text) for n in node(cid).findall(direction)] == [
            (has, expected[0]), ('!' + has, expected[1])]
    for direction, target in [('onup','9701'),('ondown','9101'),('onleft','9100')]:
        assert node(9110).findtext(direction) == target
    assert root.find(".//include[@content='TopBar']/param[@name='down']").get('value') == '9100'


def test_native_dialog_buttons_do_not_override_white_focus_with_white_text():
    cases = {'custom_1126_Confirm.xml': {'10','11'}, 'DialogSubtitles.xml': {'160'},
        'DialogVideoManager.xml': {'21','22','23','27','24','28','26','25'},
        'custom_SideMenuHelp.xml': {'100'},
        'Includes_Compatibility.xml': {'10825','10826','18','19','5','7'}}
    for name, ids in cases.items():
        for node in ET.parse(SKIN / name).iter('control'):
            if (node.get('type') == 'button' and node.get('id') in ids
                    and node.find('texturefocus') is None):
                assert node.findtext('focusedcolor') != 'white', (name, node.get('id'))
    for name, cid in [('EventLog.xml','4'), ('DialogPVRGroupManager.xml','34'),
                      ('Includes_Compatibility.xml','4')]:
        nodes = [n for n in ET.parse(SKIN/name).iter('control')
                 if n.get('id') == cid and n.get('type') == 'togglebutton']
        assert nodes
        for node in nodes:
            assert node.findtext('texturefocus') == 'bobi/row-focus.png'
            assert node.findtext('alttexturefocus') == 'bobi/row-focus.png'


def test_compatibility_does_not_keep_shadow_control_defaults():
    assert not ET.parse(SKIN / 'Includes_Compatibility.xml').findall('default')
