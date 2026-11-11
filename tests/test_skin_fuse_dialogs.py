"""CE21-safe dialog navigation adopted from Fuse3's native-control patterns.

These are skin contracts, not a replacement for live Kodi focus/scroll testing.
Native reference: GUITextBox::CanFocus is false; GUIDialogSelect owns lists 3/6
and buttons 5/7/8. GUIControlFactory only accepts a boolean <scroll> override.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def document(name):
    return ET.parse(SKIN / name).getroot()


def control(root, ident):
    result = root.find(f".//control[@id='{ident}']")
    assert result is not None, ident
    return result


def included(name):
    return document('Includes_Dialogs.xml').find(f"include[@name='{name}']")


def test_text_viewer_focuses_real_page_control_even_for_one_page():
    root = document('DialogTextViewer.xml')
    page = control(root, root.findtext('defaultcontrol'))
    assert page.get('type') == 'scrollbar'
    assert control(root, '5').findtext('pagecontrol') == page.get('id')
    assert page.findtext('showonepage') == 'true'
    close = control(root, page.findtext('onright'))
    assert close.findtext('onclick') == 'Close'
    assert close.findtext('onleft') == page.get('id')
    assert root.find('onunload') is None


@pytest.mark.parametrize('list_id,page_id', [('3', '61'), ('6', '62')])
def test_select_simple_and_detailed_views_have_independent_page_owners(list_id, page_id):
    root = included('BobiSelectSheet')
    listing = control(root, list_id)
    page = control(root, page_id)
    assert listing.findtext('pagecontrol') == page_id
    assert listing.findtext('onright') == page_id
    assert page.findtext('onleft') == list_id
    assert page.findtext('onright') == '9000'
    assert page.findtext('visible') == f'Control.IsVisible({list_id})'
    assert page.findtext('showonepage') == 'false'


def test_select_footer_returns_to_visible_native_view_and_keeps_native_buttons():
    footer = control(included('BobiSelectSheet'), '9000')
    routes = {n.get('condition'): n.text for n in footer.findall('onup')}
    assert routes == {'Control.IsVisible(6)': '6', '!Control.IsVisible(6)': '3'}
    assert {n.findtext("param[@name='id']") for n in footer.findall('include')} == {'5', '7', '8'}
    assert not list(footer.iter('onclick'))  # Native Kodi owns confirm/cancel semantics.


def test_detailed_select_thumbnail_label_and_checkmark_never_overlap():
    root = included('SelectRowDetailed')
    group = root.find(".//control[@type='grouplist']")
    label_right = int(group.findtext('left')) + 88 + max(
        int(node.findtext('width')) for node in group.findall('control'))
    check = next(node for node in root.findall('definition/control')
                 if node.findtext('visible') == 'ListItem.IsSelected')
    check_left = 744 - int(check.findtext('right')) - int(check.findtext('width'))
    assert label_right < check_left


@pytest.mark.parametrize('filename', ['DialogSettings.xml', 'DialogAddonSettings.xml', 'SettingsCategory.xml'])
def test_setting_rows_have_reachable_paging_and_readable_long_help(filename):
    root = document(filename)
    listing, page = control(root, '5'), control(root, '60')
    assert listing.findtext('onright') == page.get('id')
    assert listing.findtext('pagecontrol') == page.get('id')
    assert page.findtext('onleft') == listing.get('id')
    assert page.findtext('onright') == ('5' if filename == 'SettingsCategory.xml' else '9000')
    help_text = control(root, '6')
    assert help_text.findtext('autoscroll') == 'ControlGroup(5).HasFocus'
    assert int(help_text.find('autoscroll').get('delay')) >= 5000


@pytest.mark.parametrize('list_id,page_id', [('450', '60'), ('451', '61')])
def test_file_browser_both_native_views_have_separate_page_controls(list_id, page_id):
    root = document('FileBrowser.xml')
    assert control(root, list_id).findtext('pagecontrol') == page_id
    page = control(root, page_id)
    assert page.findtext('onleft') == list_id
    assert page.findtext('onright') == '9000'
    assert page.findtext('visible') == f'Control.IsVisible({list_id})'
    footer = control(root, '9000')
    assert {n.text for n in footer.findall('onleft')} == {'450', '451'}


@pytest.mark.parametrize('list_id,page_id,outer,inner,other', [
    ('20', '60', 'onleft', 'onright', '21'),
    ('21', '61', 'onright', 'onleft', '20'),
])
def test_file_manager_preserves_direct_panel_switch_and_adds_outer_edge_paging(
        list_id, page_id, outer, inner, other):
    root = document('FileManager.xml')
    listing, page = control(root, list_id), control(root, page_id)
    assert listing.findtext(inner) == other
    assert listing.findtext(outer) == page_id
    assert listing.findtext('pagecontrol') == page_id
    assert page.findtext('onleft') == page.findtext('onright') == list_id
    for layout in ('itemlayout', 'focusedlayout'):
        row = listing.find(f'{layout}/include')
        assert row.get('content') == 'BobiFileManagerRow'
        assert row.findtext("param[@name='list']") == list_id


def test_file_manager_shared_rows_expose_real_icon_and_selected_state():
    row = included('BobiFileManagerRow')
    assert any(n.text == '$INFO[ListItem.Icon]' for n in row.iter('texture'))
    assert any(n.text == 'ListItem.IsSelected' for n in row.iter('visible'))
    # Omitting scroll delegates focus-only scrolling to CE21's list-label implementation.
    assert not list(row.iter('scroll'))
    root = document('FileManager.xml')
    assert control(root, '101').findtext('haspath') == 'true'
    assert control(root, '102').findtext('haspath') == 'true'
    assert root.find('onload') is None  # Opening a manager must not mutate files/settings.


def test_settings_hub_has_no_dead_action_tiles():
    root = document('Settings.xml')
    for item in root.findall('.//content/item'):
        assert item.findtext('onclick'), item.findtext('label')


def test_numeric_actions_keep_native_ids_but_have_readable_labels():
    root = document('DialogNumeric.xml')
    assert {str(n) for n in range(10, 24)} <= {n.get('id') for n in root.iter('control')}
    assert control(root, '21').findtext('label') == '完成'
    assert control(root, '23').findtext('label') == '退格'
    for ident in ('21', '23'):
        assert control(root, ident).find('onclick') is None


def test_smart_playlist_cancel_button_can_navigate_to_confirm_on_both_sides():
    root = document('SmartPlaylistRule.xml')
    cancel = control(root, '19')
    assert cancel.findtext('onleft') == cancel.findtext('onright') == '18'


def test_chinese_keyboard_keeps_native_and_bobbi_candidate_fallback_contracts():
    root = document('DialogKeyboard.xml')
    assert root.findtext('onload') == 'RunScript(special://skin/scripts/cinema_keyboard.py)'
    assert {str(n) for n in (311, 312, 313, 314, 308, 310)} <= {
        node.get('id') for node in root.iter('control')}
    assert control(root, '314').find('animation').get('condition') == '$EXP[BobiIMECurrent]'
    for ident in ('510', '511'):
        assert control(root, ident).find('onclick').get('condition') == '$EXP[BobiIMECurrent]'


@pytest.mark.parametrize('filename', [
    'Includes_Dialogs.xml', 'DialogTextViewer.xml', 'DialogSettings.xml',
    'DialogAddonSettings.xml', 'SettingsCategory.xml', 'Settings.xml',
    'FileBrowser.xml', 'FileManager.xml', 'DialogNumeric.xml', 'SmartPlaylistRule.xml',
])
def test_changed_dialog_xml_remains_parseable_and_uses_ce21_scroll_values(filename):
    root = document(filename)
    for node in root.iter('scroll'):
        assert node.text in ('true', 'false'), (filename, node.text)
