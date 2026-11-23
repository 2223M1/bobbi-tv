"""Actual session/renderer with Kodi's full LABEL_BIND and select FIFO."""
import pytest
from test_source_incremental_ui import Item, window, source
from bobbi_core.source_list_session import SourceListSession


class QueuedControl:
    def __init__(self, eager=False):
        self.items, self.gui_items, self.queue = [], [], []
        self.position, self.resets, self.binds, self.selects = 0, 0, 0, 0
        self.eager = eager
    def bind(self): self.queue.append(('bind', self.items[:]))
    def addItems(self, items): self.items.extend(items); self.bind()
    def addItem(self, item): self.addItems([item])
    def removeItem(self, index): self.items.pop(index); self.bind()
    def reset(self): self.items.clear(); self.resets += 1; self.bind()
    def selectItem(self, index): self.queue.append(('select', index)); self.selects += 1
    def dispatch(self):
        for op, value in self.queue:
            if op == 'bind': self.gui_items = value; self.position = 0; self.binds += 1
            else: self.position = value
        self.queue.clear()
    def getSelectedPosition(self):
        if self.eager: self.dispatch()
        return self.position if self.gui_items else -1
    def getSelectedItem(self):
        index = self.getSelectedPosition()
        return self.items[index] if 0 <= index < len(self.items) else None


@pytest.mark.parametrize('eager', [False, True])
@pytest.mark.parametrize('selected', [0, 1, 2])
def test_real_session_arrival_preserves_key_and_later_user_navigation(window, eager, selected):
    control = window.display_list = QueuedControl(eager)
    session = SourceListSession({'kind': 'fixture'}, rank=lambda rows: list(reversed(rows)), limit=100)
    window.source_session = session
    rows = [source(str(i)) for i in range(4)]
    session.publish(session.epoch, 'fixture', rows[:3], state='RUNNING')
    window.sources = [s for _, s in session.snapshot(full=True)['entries']]
    window.populate_sources_list(); control.dispatch()
    control.selectItem(selected); control.dispatch()
    selected_item = control.getSelectedItem()
    session.focus(selected_item.getProperty('source_key'), selected)
    session.publish(session.epoch, 'fixture', rows[3:], state='RUNNING')
    window.sources = [s for _, s in session.snapshot(full=True)['entries']]
    window.populate_sources_list(incremental=True)
    control.dispatch()
    assert control.getSelectedItem() is selected_item and control.resets == 1
    binds, selects = control.binds, control.selects
    window.populate_sources_list(incremental=True); control.dispatch()
    assert (control.binds, control.selects) == (binds, selects)
    window.sources += [source('new')]
    window.populate_sources_list(incremental=True)
    control.selectItem(3)  # New user input queued after this refresh wins.
    control.dispatch()
    assert control.position == 3


@pytest.mark.parametrize('eager', [False, True])
def test_quality_keys_survive_add_remove_and_counts(window, eager):
    window.quality = QueuedControl(eager)
    a, b, c = source('a'), source('b', '2160p'), source('c', '720p')
    window.sources = [a, b]
    window.populate_qualities_header(); window.quality.dispatch()
    index = window._quality_keys.index('1080p')
    window.quality.selectItem(index); window.quality.dispatch()
    item = window.quality.getSelectedItem()
    window.sources.append(c); window.populate_qualities_header(); window.quality.dispatch()
    assert window.quality.getSelectedItem() is item
    window.sources.remove(b); window.populate_qualities_header(); window.quality.dispatch()
    assert window.quality.getSelectedItem() is item
    binds, selects = window.quality.binds, window.quality.selects
    window.sources.append(source('d')); window.populate_qualities_header(); window.quality.dispatch()
    assert (window.quality.binds, window.quality.selects) == (binds, selects)
    window.sources.remove(a)
    window.sources = [c]; window.populate_qualities_header(); window.quality.dispatch()
    assert window.quality.getSelectedItem().getProperty('quality') == '720p'


def test_withdrawal_has_stable_nearest_neighbor_without_auto_play(window):
    window.display_list = QueuedControl()
    window.sources = [source(k) for k in 'abc']
    window.populate_sources_list(); window.display_list.dispatch()
    window.display_list.selectItem(1); window.display_list.dispatch()
    survivor = window._rendered_cards['c']
    window.sources.pop(1); window.populate_sources_list(incremental=True); window.display_list.dispatch()
    assert window.display_list.getSelectedItem() is survivor
