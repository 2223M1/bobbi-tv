"""Kodi 21 home navigation contracts inspired by Fuse's available-widget routing."""
from itertools import product
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest


SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'
RAILS = (9810, 9830, 9840, 9850, 9860)
EXPANDED_RAILS = (9810, 9820, 9830, 9840, 9850, 9860)


def document(name):
    return ET.parse(SKIN / name).getroot()


def matches(expression, populated=(), focus=0, remembered=0, updating=()):
    """Evaluate only the skin's navigation predicates, not Kodi presentation state."""
    if expression is None:
        return True
    expression = re.sub(
        r'\$EXP\[([^]]+)\]',
        lambda m: str(matches(document('Includes_HomeRails.generated.xml').find(
            f"expression[@name='{m[1]}']").text, populated, focus, remembered, updating)),
        expression)
    expression = re.sub(r'Integer.IsGreater\(Container\((\d+)\).NumItems,0\)',
                        lambda m: str(int(m[1]) in populated), expression)
    expression = re.sub(r'Container\((\d+)\).IsUpdating',
                        lambda m: str(int(m[1]) in updating), expression)
    expression = re.sub(r'Control.HasFocus\((\d+)\)',
                        lambda m: str(int(m[1]) == focus), expression)
    expression = re.sub(r'String.IsEqual\(Window\(Home\).Property\(BobiRail\),(\d+)\)',
                        lambda m: str(int(m[1]) == remembered), expression)
    # Every predicate above reduces to a boolean; reject unsupported syntax.
    assert re.fullmatch(r'(?:True|False|[\s+|!\[\]])+', expression), expression
    expression = expression.replace('+', ' and ').replace('|', ' or ')
    expression = expression.replace('!', ' not ').replace('[', '(').replace(']', ')')
    return eval(expression.strip(), {'__builtins__': {}}, {})


def destination(name, **state):
    variable = document('Includes_HomeRails.generated.xml').find(f"variable[@name='{name}']")
    return int(next(value.text for value in variable
                    if matches(value.get('condition'), **state)))


@pytest.mark.parametrize('available', tuple(product((False, True), repeat=len(RAILS))))
def test_rail_navigation_skips_every_combination_of_empty_and_loading_rows(available):
    populated = tuple(rail for rail, ready in zip(RAILS, available) if ready)
    empty = set(RAILS) - set(populated)
    for focus in populated:
        index = RAILS.index(focus)
        previous = [rail for rail in populated if RAILS.index(rail) < index]
        following = [rail for rail in populated if RAILS.index(rail) > index]
        # Updating rows with existing items stay usable; rows with no items don't.
        for updating in ((), empty, RAILS):
            state = dict(populated=populated, focus=focus, updating=updating)
            assert destination('HomeRailUp', **state) == (previous[-1] if previous else 9701)
            assert destination('HomeRailDown', **state) == (following[0] if following else focus)


@pytest.mark.parametrize('available', tuple(product((False, True), repeat=len(RAILS))))
def test_topbar_restores_last_available_row_and_has_loading_empty_fallbacks(available):
    populated = tuple(rail for rail, ready in zip(RAILS, available) if ready)
    for remembered in (0, *RAILS):
        for updating in ((), RAILS):
            expected = (remembered if remembered in populated else populated[0]
                        if populated else 9701 if updating else 9870)
            assert destination('HomeContentFocus', populated=populated,
                               remembered=remembered, updating=updating) == expected


def test_dynamic_navigation_uses_explicit_builtins_and_preserves_item_offsets():
    root = document('Includes_Home.xml')
    for include in ('HomeRail', 'HomeRailWide'):
        control = root.find(f"include[@name='{include}']/.//control[@type='list']")
        assert control.findtext('onup') == 'SetFocus($VAR[HomeRailUp])'
        assert control.findtext('ondown') == 'SetFocus($VAR[HomeRailDown])'
        assert control.findtext('enable') == 'Integer.IsGreater(Container($PARAM[id]).NumItems,0)'
        assert control.findtext('preloaditems') == '$PARAM[preloaditems]'
        assert control.find('content').get('limit') == '$PARAM[limit]'
        template = root.find(f"include[@name='{include}']")
        assert template.findtext("param[@name='preloaditems']") == '2'
        assert template.findtext("param[@name='limit']") == '20'
    nav = document('Home.xml').find(".//include[@content='TopBar']/param[@name='down']")
    assert nav.get('value') == 'SetFocus($VAR[HomeContentFocus])'


def test_home_empty_state_is_not_loading_and_offers_a_real_destination():
    root = document('Home.xml')
    state = next(group for group in root.iter('control')
                 if group.find("control[@id='9870']") is not None)
    visible = state.findtext('visible')
    assert matches(visible)
    assert not matches(visible, updating=(9810,))
    assert not matches(visible, populated=(9840,))
    button = state.find("control[@id='9870']")
    assert button.findtext('onclick') == 'ActivateWindow(1197)'
    assert button.findtext('onup') == '9701'
    assert button.findtext('onback') == 'SetFocus(9701)'


def test_wide_resume_rail_explains_initial_loading_without_hiding_cached_items():
    root = document('Includes_Home.xml').find("include[@name='HomeRailWide']")
    label = next(node for node in root.iter('control')
                 if node.findtext('label') == '正在读取观看记录…')
    assert label.findtext('visible') == (
        'Container($PARAM[id]).IsUpdating + Integer.IsEqual(Container($PARAM[id]).NumItems,0)')


@pytest.mark.parametrize('name', ['HomeRail', 'HomeRailWide'])
def test_account_filtered_rail_keeps_provider_alive_during_first_visibility_tick(name):
    root = document('Includes_Home.xml').find(f"include[@name='{name}']/definition/control")
    # Kodi DirectoryProvider DONE first Fetch can be empty: node.visible is
    # evaluated on its next Update. A hidden parent never processes children,
    # so hiding the owner on NumItems==0 permanently prevents that next tick.
    assert root.findtext('visible', 'true') == 'true'
    title = next(node for node in root.findall('control')
                 if node.findtext('label') == '$PARAM[title]')
    assert title.findtext('visible') == (
        'Integer.IsGreater(Container($PARAM[id]).NumItems,0) | Container($PARAM[id]).IsUpdating')
    control = root.find("control[@type='list']")
    assert control.findtext('enable') == 'Integer.IsGreater(Container($PARAM[id]).NumItems,0)'


def test_home_rails_share_one_viewport_without_empty_group_scroll_slots():
    root = document('Home.xml')
    viewport = root.find(".//control[@id='9000']")
    assert viewport.get('type') == 'group'
    assert viewport.findtext('top') == '580'
    assert viewport.findtext('height') == '420'
    assert viewport.find('visible') is None  # Directory providers must still tick.
    selector = root.find(".//control[@id='9791']")
    assert selector is not None and selector.findtext('label') == '$VAR[HomeContentFocus]'
    for name in ('HomeRail', 'HomeRailWide'):
        rail = document('Includes_Home.xml').find(f"include[@name='{name}']/definition/control")
        hidden = rail.find('animation')
        assert hidden is not None and hidden.text == 'Conditional'
        assert hidden.attrib == dict(effect='slide', start='0,0', end='0,2160', time='0',
            condition='!String.IsEqual(Control.GetLabel(9791),$PARAM[id])')
    loading = root.find(".//control[label='正在加载片单…']")
    assert loading.findtext('visible') == '$EXP[BobiHomeUpdating] + !$EXP[BobiHomeHasItems]'


def test_cold_home_has_a_visible_default_before_async_rails_arrive():
    node = document('Home.xml').find('defaultcontrol')
    assert node.text == '9711'  # Always-present Home tab, not an empty group.
    assert node.get('always') == 'false'  # Returning retains the existing card.


def test_personal_preview_is_data_only_not_an_offscreen_remote_focus_target():
    root = document('Custom_1197_BobiPersonal.xml')
    preview = root.find(".//control[@id='9130']")
    assert preview.findtext('enable') == 'false'
    assert preview.find('hitrect').attrib == {'x': '0', 'y': '0', 'w': '0', 'h': '0'}
    assert preview.find('content').get('limit') == '1'
    assert 'resume_preview=true' in preview.findtext('content')
    for control_id in ('9100', '9101'):
        control = root.find(f".//control[@id='{control_id}']")
        assert control.findtext('ondown') == 'noop'
        assert control.findtext('enable') != 'false'


@pytest.mark.parametrize('name', ('StageArt', 'StageMeta', 'StagePlot',
                                 'StageTitlePrimary', 'StageTitleSecondary',
                                 'StageSeasonLabel', 'StageEpisodeLabel', 'StageEpisodeTitle'))
def test_stage_falls_back_when_the_remembered_row_becomes_empty(name):
    variable = document('Includes_HomeRails.generated.xml').find(f"variable[@name='{name}']")
    for value in variable:
        condition = value.get('condition', '')
        if '.Property(BobiRail)' in condition:
            rail = re.search(r'Property\(BobiRail\),(\d+)\)', condition)[1]
            assert f'Integer.IsGreater(Container({rail}).NumItems,0)' in condition
    fallbacks = [v for v in variable if '.Property(BobiRail)' not in v.get('condition', '')]
    for rail in RAILS:
        assert any(v.get('condition') == f'Integer.IsGreater(Container({rail}).NumItems,0)'
                   for v in fallbacks)


def test_home_does_not_add_refresh_polling_new_addons_or_duplicate_content_requests():
    root = document('Home.xml')
    assert root.findtext(".//control[@id='9000']/include") == 'HomeRails'
    rails = [node for node in document('Includes_HomeRails.generated.xml').iter('include')
             if node.get('content') in {'HomeRail', 'HomeRailWide'}]
    assert len(rails) == 6
    assert [node.find("param[@name='id']").get('value') for node in rails] == [
        '9810', '9820', '9830', '9840', '9850', '9860']
    assert root.find('defaultcontrol').get('always') == 'false'
    assert not any('Refresh' in (node.text or '') or 'AlarmClock' in (node.text or '')
                   for node in root.iter())


@pytest.mark.parametrize('available', tuple(product((False, True), repeat=len(EXPANDED_RAILS))))
def test_six_rail_navigation_also_covers_personal_library_and_real_recovery_cards(available):
    populated = tuple(rail for rail, ready in zip(EXPANDED_RAILS, available) if ready)
    for focus in populated:
        index = populated.index(focus)
        assert destination('HomeRailUp', populated=populated, focus=focus) == (populated[index-1] if index else 9701)
        assert destination('HomeRailDown', populated=populated, focus=focus) == (populated[index+1] if index+1<len(populated) else focus)
    expected = populated[0] if populated else 9870
    assert destination('HomeContentFocus', populated=populated) == expected
