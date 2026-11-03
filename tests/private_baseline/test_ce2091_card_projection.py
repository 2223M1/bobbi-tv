"""Bobi card projection keeps UI/selection fields and legacy templates intact."""
from pathlib import Path
import re

import pytest
from lib.gui import source_select as ui
from test_source_incremental_ui import window, source

FIELDS = frozenset(('type_plain', 'title', 'chinese_subtitles', 'badges_plain',
    'release_group', 'size', 'seeders', 'languages_plain', 'source_site',
    'recommendation_status', 'quality_plain', 'source_key', 'peers',
    'status_plain', 'recommendation_reason'))


def test_cinema_projection_publishes_only_consumed_fields(window):
    window._card_fields = FIELDS
    window.sources = [source('a')]
    window.populate_sources_list()
    item = window.display_list.items[0]
    assert set(window._rendered_card_values['a']) == FIELDS
    assert set(item.props) <= FIELDS
    assert item.props['source_key'] == 'a'
    before = dict(item.props)
    window.sources[0].seeders = 9
    window.populate_sources_list(incremental=True)
    assert item.batches[-1]['seeders'] == '9'
    assert item.batches[-1] == {key: value for key, value in item.props.items()
                                if before.get(key, '') != value}
    assert window.display_list.items[0] is item


@pytest.mark.parametrize('template', ['source_select.xml', 'source_select_direct.xml'])
def test_bundled_source_templates_and_quality_badge_keep_every_consumed_property(template):
    root = Path(__file__).resolve().parents[2] / 'addons'
    xml = (root/'plugin.video.bobbi/resources/skins/Default/1080i'/template).read_text(encoding='utf-8')
    skin = (root/'skin.bobbi.cinema/1080p/Variables.xml').read_text(encoding='utf-8')
    badge = re.search(r'<variable name="BobiQualityBadge">(.*?)</variable>', skin, re.S)
    assert badge
    # "quality" belongs to the separate 1300 filter control, not source cards.
    used = set(re.findall(r'ListItem\.Property\(([^)]+)\)', xml + badge[1])) - {'quality'}
    assert used <= FIELDS
    assert ui._source_card_fields(template, 'skin.bobbi.cinema') == FIELDS


@pytest.mark.parametrize('template,skin', [
    ('source_select.xml', 'skin.estuary'),
    ('source_select_direct.xml', 'skin.other'),
    ('custom_source.xml', 'skin.bobbi.cinema')])
def test_unowned_templates_use_complete_projection(template, skin):
    assert ui._source_card_fields(template, skin) is None


def test_legacy_renderer_still_exposes_extended_properties(window):
    window._card_fields = None
    window.sources = [source('a')]
    window.populate_sources_list()
    assert {'codec', 'display_title', 'guid', 'quality', 'isPack'} <= set(window._rendered_card_values['a'])
