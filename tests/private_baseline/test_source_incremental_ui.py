"""Real source-card renderer: provider updates retain native items and focus."""
from types import SimpleNamespace

import pytest
from lib.gui import source_select as ui
from lib.domain.torrent import TorrentStream


class Item:
    def __init__(self, label='', **kw):
        self.label, self.props, self.writes = label, {}, 0
    def getLabel(self): return self.label
    def setLabel(self, label): self.label = label; self.writes += 1
    def getProperty(self, key): return self.props.get(key, '')
    def setProperty(self, key, value): self.props[key] = value; self.writes += 1


class Control:
    def __init__(self):
        self.items, self.selected, self.resets, self.selects = [], 0, 0, 0
    def reset(self): self.items.clear(); self.resets += 1; self.selected = 0
    def addItems(self, items): self.items.extend(items)
    def addItem(self, item): self.items.append(item)
    def removeItem(self, position): self.items.pop(position)
    def getSelectedItem(self): return self.items[self.selected] if self.selected < len(self.items) else None
    def getSelectedPosition(self): return self.selected
    def selectItem(self, position): self.selected = position; self.selects += 1


def source(key, quality='1080p'):
    return TorrentStream(type='Torrent', guid=key, title='Example S01E01 '+quality+' x264',
                         size=1024, quality=quality, indexer='Nyaa')


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setattr(ui.xbmcgui, 'ListItem', Item)
    monkeypatch.setattr(ui, 'get_random_color', lambda value, **kw: value)
    monkeypatch.setattr(ui.cache, 'get', lambda *a: {})
    window = ui.SourceSelect.__new__(ui.SourceSelect)
    window.display_list, window.quality = Control(), Control()
    window.source_session = SimpleNamespace(key=lambda source: source.guid, limit=100)
    window.filter_applied, window.filtered_sources = False, None
    window.item_information = {}
    window.setProperty = lambda *a: None
    window.getControl = lambda _: window.quality
    return window


def test_new_ranked_source_appends_without_reset_and_compensates_native_bind(window):
    a, b, c = [source(k) for k in 'abc']
    window.sources = [a, b]
    window.populate_sources_list()
    old = list(window.display_list.items)
    window.display_list.selected = 1
    writes = [item.writes for item in old]
    window.sources = [c, a, b]  # The provider ranks the new result first.
    window.populate_sources_list(incremental=True)
    assert window.display_list.resets == 1
    assert window.display_list.items[:2] == old
    assert [s.guid for s in window.list_sources] == ['a', 'b', 'c']
    assert window.display_list.getSelectedItem() is old[1]
    assert window.display_list.selects == 1
    assert [item.writes for item in old] == writes
    # Completion-only publication is a true no-op on native card fields.
    window.populate_sources_list(incremental=True)
    assert window.display_list.resets == 1 and window.display_list.selects == 1
    assert [item.writes for item in old] == writes


def test_only_superseded_bt_row_removed_cloud_does_not_rebind_survivors(window):
    bt, keep, cloud = [source(k) for k in ('bt', 'keep', 'cloud')]
    window.sources = [bt, keep]
    window.populate_sources_list()
    survivor = window.display_list.items[1]
    window.display_list.selected = 1
    window.sources = [cloud, keep]
    window.populate_sources_list(incremental=True)
    assert window.display_list.resets == 1
    assert window.display_list.items[0] is survivor
    assert window.display_list.getSelectedItem() is survivor
    assert [s.guid for s in window.list_sources] == ['keep', 'cloud']


def test_explicit_filter_can_rebuild_and_next_publication_is_incremental(window):
    window.sources = [source('a'), source('b', '2160p')]
    window.populate_sources_list()
    window.filter_applied, window.filtered_sources = True, window.sources[1:]
    window.populate_sources_list()
    item = window.display_list.items[0]
    window.populate_sources_list(incremental=True)
    assert window.display_list.resets == 2
    assert window.display_list.items == [item]
    assert [s.guid for s in window.list_sources] == ['b']


def test_quality_count_changes_in_place_without_resetting_tab_focus(window):
    window.sources = [source('a')]
    window.populate_qualities_header()
    old = list(window.quality.items)
    window.quality.selected = 1
    window.sources.append(source('b', '2160p'))
    window.populate_qualities_header()
    assert window.quality.items[:2] == old
    assert old[0].getLabel() == '全部 (2)'
    assert window.quality.resets == 0 and window.quality.selects == 2
    assert window.quality.getSelectedItem() is old[1]
