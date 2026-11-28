"""native native player contracts without importing newer skin services.

These are structural regression checks, not a substitute for device focus,
decoder, PVR-backend or remote-client acceptance tests.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def document(name):
    return ET.parse(SKIN / name).getroot()


def control(root, cid):
    return root.find(f".//control[@id='{cid}']")


@pytest.mark.parametrize('name', ['MusicOSD.xml'])
def test_seek_sliders_bind_native_progress_and_capability(name):
    slider = control(document(name), 87)
    assert slider.findtext('info') == 'Player.Progress'
    assert slider.findtext('action') == 'seek'
    assert slider.findtext('enable') == 'Player.SeekEnabled'
    # Kodi owns stepping and pending-seek state, as it does in LiquidTiles.
    assert slider.find('onleft') is None
    assert slider.find('onright') is None


def test_video_seek_captures_scope_before_numeric_dialog_instead_of_global_slider():
    target = control(document('VideoOSD.xml'), 87)
    assert target.get('type') == 'button'
    assert target.findtext('onclick') == 'RunScript(plugin.video.bobbi,bobbi_osd=seek)'
    assert target.findtext('enable') == 'Player.SeekEnabled'
    assert target.find('action') is None


@pytest.mark.parametrize('cid', [600, 700, 710])
def test_video_seek_navigation_has_a_nonseekable_fallback(cid):
    upwards = control(document('VideoOSD.xml'), cid).findall('onup')
    assert [(n.get('condition'), n.text) for n in upwards] == [
        ('Player.SeekEnabled', '87'), ('!Player.SeekEnabled', 'noop')]


@pytest.mark.parametrize('action,condition,variable', [
    ('RunScript(plugin.video.bobbi,bobbi_osd=seek_back)', 'Player.SeekEnabled', 'BobbiSeekUnavailable'),
    ('RunScript(plugin.video.bobbi,bobbi_osd=seek_forward)', 'Player.SeekEnabled', 'BobbiSeekUnavailable'),
    ('RunScript(plugin.video.bobbi,bobbi_osd=toggle_pause)', 'Player.PauseEnabled | Player.Forwarding | Player.Rewinding',
     'BobbiPauseUnavailable'),
])
def test_fixed_transport_slots_honor_capability_without_moving_default_focus(action, condition, variable):
    transport = control(document('VideoOSD.xml'), 600)
    items = transport.findall('content/item')
    assert len(items) == 6
    assert any(node.text.endswith('bobbi_osd=toggle_pause)') for node in items[2].findall('onclick'))
    item = next(i for i in items if any(n.text == action for n in i.findall('onclick')))
    clicks = item.findall('onclick')
    assert len(clicks) == 2
    assert all(node.get('condition').startswith('[' + condition + '] + ') for node in clicks)
    assert {node.get('condition').split('] + ', 1)[1] for node in clicks} == {
        prefix + 'String.IsEmpty(Window(Home).Property(Bobbi.OSD.TapScope))' for prefix in ('!', '')}
    assert any(n.text.startswith('NotifyAll(bobbi.osd,BobbiTap.') for n in clicks)
    assert item.findtext("property[@name='unavailable']") == f'$VAR[{variable}]'


@pytest.mark.parametrize('name,condition', [
    ('BobbiSeekUnavailable', 'Player.SeekEnabled'),
    ('BobbiPauseUnavailable', 'Player.PauseEnabled | Player.Forwarding | Player.Rewinding'),
])
def test_transport_capability_variables_default_to_unavailable(name, condition):
    variable = document('Variables.xml').find(f"variable[@name='{name}']")
    assert [(v.get('condition'), v.text) for v in variable] == [
        (condition, 'false'), (None, 'true')]


@pytest.mark.parametrize('name', ['RoundItem', 'ChipItem'])
def test_unavailable_items_dim_all_visuals_without_changing_slots(name):
    definition = document('Includes.xml').find(f"include[@name='{name}']/definition")
    assert len(definition) == 1
    group = definition.find("control[@type='group']")
    animation = group.find('animation')
    assert animation.get('condition') == 'String.IsEqual(ListItem.Property(unavailable),true)'
    assert animation.get('effect') == 'fade'
    assert animation.get('end') == '35'
    assert animation.get('time') == '0'
    assert group.find('visible') is None


def test_unavailable_speed_and_bookmark_tools_are_not_offered():
    root = document('custom_OptionsDialog.xml')
    speed = next(i for i in root.iter('item') if i.findtext('onclick') == 'ActivateWindow(1115)')
    bookmarks = next(i for i in root.iter('item') if i.findtext('onclick') == 'RunScript(plugin.video.bobbi,bobbi_osd=chapters)')
    assert speed.findtext('visible') == 'Player.TempoEnabled | Player.SeekEnabled'
    assert bookmarks.findtext('visible') == 'Player.SeekEnabled'
    assert control(document('custom_PlaySpeed.xml'), 9200).findtext('enable') == speed.findtext('visible')


@pytest.mark.parametrize('name', ['Custom_1144_OSD_subtitles.xml', 'Custom_1145_OSD_audio.xml'])
def test_stream_picker_has_a_real_loading_and_empty_focus_target(name):
    assert document(name).findtext('defaultcontrol') == '2024'
    picker = document('Includes_OSD.xml').find("include[@name='StreamPicker']")
    group = control(picker, 2024)
    assert group.get('type') == 'group'
    assert group.findtext('defaultcontrol') == '2021'
    assert group.find('defaultcontrol').get('always') == 'true'
    placeholder = control(picker, 2020)
    assert placeholder.get('type') == 'button'
    assert placeholder.findtext('label') == '$VAR[BobbiStreamPlaceholder]'
    current = '$EXP[BobbiCurrentStreamPanel]'
    identity = document('Includes_OSD.xml').find("expression[@name='BobbiCurrentStreamPanel']")
    assert identity.text.split(' + ') == [
        'Integer.IsGreater(Container(2021).NumItems,0)',
        '!String.IsEmpty(Window(Home).Property(Bobbi.OSD.StreamPanel))',
        'String.IsEqual(Container(2021).ListItem.Property(bobbi_panel),Window(Home).Property(Bobbi.OSD.StreamPanel))',
    ]
    assert placeholder.findtext('visible') == '!' + current
    assert placeholder.findtext('ondown') == '2022'
    # Empty and stale-but-nonempty lists must both remain unfocusable. Keep
    # the content provider mounted so the new panel can supersede old rows.
    tracks = control(picker, 2021)
    assert tracks.findtext('enable') == current
    assert tracks.find('visible') is None
    assert tracks.find('content').get('condition') is None
    assert [n.get('condition') for n in tracks.findall('onclick')] == [current, current]
    assert [(n.get('condition'), n.text) for n in control(picker, 2022).findall('onup')] == [
        (current, '2021'), ('!' + current, '2020')]


def test_stream_picker_footer_cannot_overlap_long_lists_or_jump_while_loading():
    picker = document('Includes_OSD.xml').find("include[@name='StreamPicker']")
    tracks, footer = control(picker, 2021), control(picker, 2022)
    assert int(tracks.findtext('top')) + int(tracks.findtext('height')) <= int(footer.findtext('top'))
    assert footer.find('animation') is None
    settings = next(i for i in footer.findall('include')
                    if i.findtext("param[@name='id']") == '20222')
    assert settings.findtext("param[@name='onclick']") == 'Dialog.Close($PARAM[window])'
    assert settings.findtext("param[@name='onclick2']") == 'RunScript(plugin.video.bobbi,bobbi_osd=$PARAM[type]_settings)'
    assert not any('PlayerControl(Play)' in (n.text or '') for n in picker.iter('onclick'))


def test_music_seek_and_transport_have_bidirectional_existing_targets():
    root = document('MusicOSD.xml')
    slider, row = control(root, 87), control(root, 100)
    assert slider.findtext('ondown') == slider.findtext('onup') == '100'
    assert row.find('onup').get('condition') == 'Player.SeekEnabled'
    assert row.findtext('onup') == '87'
    assert [(n.get('condition'), n.text) for n in root.findall('onload')] == [
        ('Player.PauseEnabled', 'SetFocus(602)'), ('!Player.PauseEnabled', 'SetFocus(603)')]
    assert 'Dialog.Close(all)' not in ET.tostring(root, encoding='unicode')


def test_compact_player_controls_have_no_dead_numeric_navigation_or_conflicting_enables():
    root = document('PlayerControls.xml')
    ids = {n.get('id') for n in root.iter('control') if n.get('id')}
    for node in root.iter('control'):
        assert len(node.findall('enable')) <= 1, node.get('id')
        for event in ('onleft', 'onright', 'onup', 'ondown'):
            for target in node.findall(event):
                if target.text and target.text.isdigit():
                    assert target.text in ids, (node.get('id'), event, target.text)
    assert control(root, 601).findtext('enable') == 'Player.SeekEnabled'
    assert control(root, 604).findtext('enable') == 'Player.SeekEnabled'
    assert control(root, 703).findtext('enable') == 'Player.PauseEnabled'


def test_chapter_markers_use_a_real_native_count_and_bookmarks_have_one_up_action():
    progress = document('Includes_OSD.xml').find("include[@name='OSDProgress']")
    assert progress.find(".//control[@type='ranges']").findtext('visible') == 'Integer.IsGreater(Player.ChapterCount,0)'
    bookmark_list = control(document('VideoOSDBookmarks.xml'), 11)
    assert [n.text for n in bookmark_list.findall('onup')] == ['Close']
    assert bookmark_list.findtext('ondown') == '2'


@pytest.mark.parametrize('name', ['DialogSeekBar.xml', 'VideoFullScreen.xml'])
def test_player_animations_respect_reduced_motion(name):
    for node in document(name).iter('animation'):
        assert 'Skin.HasSetting(BobbiReduceMotion)' in node.get('condition', '')
