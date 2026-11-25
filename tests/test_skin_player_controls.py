"""Remote OSD contracts; real native tempo support remains a device capability."""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def document(name):
    return ET.parse(SKIN / name).getroot()


def speed_button():
    return document('custom_PlaySpeed.xml').find(".//control[@id='9200']")


def enabled(expression, values):
    """Evaluate the simple conjunction/disjunction used by this control."""
    return any(all(not values[token[1:]] if token.startswith('!') else values[token]
                   for token in part.split(' + ')) for part in expression.split(' | '))


def actions(event, **overrides):
    values = {'Player.TempoEnabled': False, 'Player.Paused': False,
              'Player.Forwarding': False, 'Player.Rewinding': False,
              'Player.Forwarding32x': False, 'Player.Rewinding32x': False}
    values.update(overrides)
    return [node.text for node in speed_button().findall(event)
            if enabled(node.get('condition'), values)]


def test_speed_has_one_directional_focus_target_and_no_offscreen_items():
    root = document('custom_PlaySpeed.xml')
    assert root.findtext('defaultcontrol') == '9200'
    assert speed_button().get('type') == 'button'
    assert root.find('onload') is None
    assert speed_button().findtext('onup') == speed_button().findtext('ondown') == 'noop'
    assert root.find(".//control[@type='list']") is None


@pytest.mark.parametrize('event,tempo,fallback', [
    ('onleft', 'TempoDown', 'Rewind'), ('onright', 'TempoUp', 'Forward')])
def test_arrows_use_native_capability_not_a_guessed_platform(event, tempo, fallback):
    assert actions(event) == [f'PlayerControl({fallback})']
    assert actions(event, **{'Player.TempoEnabled': True}) == [f'PlayerControl({tempo})']
    for capability in (True, False):
        assert actions(event, **{'Player.Paused': True, 'Player.TempoEnabled': capability}) in ([], ['noop'])


@pytest.mark.parametrize('event,boundary', [
    ('onleft', 'Player.Rewinding32x'), ('onright', 'Player.Forwarding32x')])
def test_trick_play_stops_at_native_speed_limit(event, boundary):
    assert actions(event, **{boundary: True}) == []


def test_confirm_is_idempotent_and_tempo_reset_has_native_syntax():
    assert actions('onclick') == []  # Do not toggle a normal-speed movie into pause.
    assert actions('onclick', **{'Player.TempoEnabled': True}) == ['PlayerControl(Tempo(1.0))']
    for state in ('Player.Paused', 'Player.Forwarding', 'Player.Rewinding'):
        assert actions('onclick', **{state: True}) == ['RunScript(plugin.video.bobbi,bobbi_osd=resume)']
        assert actions('onclick', **{state: True, 'Player.TempoEnabled': True}) == ['RunScript(plugin.video.bobbi,bobbi_osd=resume)']
    assert 'PlayerControl(Tempo,1.0)' not in ET.tostring(speed_button(), encoding='unicode')


def test_mode_and_limit_are_explained_instead_of_claiming_audible_tempo():
    variables = document('Variables.xml')
    mode = variables.find("variable[@name='TempoModeLabel']")
    assert mode.find('value').get('condition') == 'Player.TempoEnabled'
    assert mode.findall('value')[-1].text == '$LOCALIZE[32282]'
    assert variables.find("variable[@name='TempoStatusHint']").findall('value')[-1].text == '$LOCALIZE[32287]'
    assert variables.find("variable[@name='TempoLabel']/value").get('condition') == 'Player.Paused'
    # Kodi may bind static OSD items before the decoder publishes its capability.
    # Never advertise the fallback from that stale snapshot; the opened button
    # and its hint use the live capability instead.
    for window in ('VideoOSD.xml', 'custom_OptionsDialog.xml'):
        option, = [item for item in document(window).iter('item')
                   if item.findtext('onclick') == 'ActivateWindow(1115)']
        assert option.findtext('label') == '$LOCALIZE[32226]'
    assert '$VAR[TempoModeLabel]' in speed_button().findtext('label')


def test_leaving_player_tools_does_not_reopen_an_unrelated_dialog_on_stop_or_back():
    for name in ('custom_PlaySpeed.xml', 'custom_OptionsDialog.xml', 'custom_1116_VS10.xml'):
        assert not any('ActivateWindow(' in (a.text or '') for a in document(name).findall('onunload'))


def test_track_selection_preserves_pause_and_uses_bobbi_owned_stream_adapter():
    picker = document('Includes_OSD.xml').find("include[@name='StreamPicker']")
    clicks = [node.text for node in picker.iter('onclick')]
    assert 'PlayerControl(Play)' not in clicks
    assert 'RunScript(plugin.video.bobbi,bobbi_osd=apply,token=$INFO[ListItem.Property(bobbi_command)])' in clicks
    assert 'ShowSubtitles' not in clicks
    assert 'Dialog.Close($PARAM[window])' in clicks


def test_no_unknown_tempo_capability_or_malformed_reset_in_executable_xml():
    for path in SKIN.glob('*.xml'):
        root = ET.parse(path).getroot()
        for node in root.iter():
            assert 'Player.SupportsTempo' not in (node.text or ''), path.name
            assert 'Player.SupportsTempo' not in str(node.attrib), path.name
            assert 'PlayerControl(Tempo,1.0)' not in (node.text or ''), path.name
