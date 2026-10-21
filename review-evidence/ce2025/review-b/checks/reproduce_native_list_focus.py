#!/usr/bin/env python3
"""Replay actual SourceSelect against Kodi 21.3's queued ControlList boundary.

The product renderer and SourceListSession come from --repo. The control double
models Control.cpp::sendLabelBind and GUIBaseContainer::OnMessage: add/remove
enqueue a complete list bind with selected index zero. It deliberately supports
both legal GUI schedules, before and after Python's selection read.
This is a source-backed IO contract, not a new device or Kodi binary test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import traceback


class Item:
    def __init__(self, label='', **kwargs):
        self.label = label
        self.props = {}

    def getLabel(self):
        return self.label

    def setLabel(self, label):
        self.label = label

    def getProperty(self, key):
        return self.props.get(key, '')

    def setProperty(self, key, value):
        self.props[key] = value


class QueuedControl:
    def __init__(self, dispatch_before_read=False):
        self.items = []
        self.gui_items = []
        self.selected = 0
        self.queue = []
        self.dispatch_before_read = dispatch_before_read
        self.binds = 0
        self.resets = 0
        self.selects = 0

    def _bind(self):
        self.queue.append(('bind', list(self.items)))

    def addItems(self, items):
        self.items.extend(items)
        self._bind()

    def addItem(self, item):
        self.items.append(item)
        self._bind()

    def removeItem(self, index):
        self.items.pop(index)
        self._bind()

    def reset(self):
        self.items.clear()
        self.queue.append(('reset', None))
        self.resets += 1

    def selectItem(self, index):
        self.queue.append(('select', index))
        self.selects += 1

    def dispatch(self):
        while self.queue:
            operation, value = self.queue.pop(0)
            if operation == 'bind':
                self.gui_items = value
                self.selected = 0
                self.binds += 1
            elif operation == 'reset':
                self.gui_items = []
                self.selected = 0
            else:
                self.selected = value

    def getSelectedPosition(self):
        if self.dispatch_before_read:
            self.dispatch()
        return self.selected if self.gui_items else -1

    def getSelectedItem(self):
        position = self.getSelectedPosition()
        return self.items[position] if 0 <= position < len(self.items) else None

    def size(self):
        return len(self.items)


def make_window(ui, Session, Stream, *, early=False):
    def source(number, quality='1080p'):
        return Stream(type='Torrent', guid='review:' + str(number),
                      infoHash='%040x' % number, indexer='Review',
                      title='Example S01E01 ' + quality + ' x264 ' + str(number),
                      quality=quality, size=1024 ** 3)

    session = Session({'tmdb_id': 30991, 'season': 1, 'episode': 1},
                      rank=lambda rows: list(reversed(rows)))
    session.publish(session.epoch, 'fixture', [source(1), source(2)], state='RUNNING')
    window = ui.SourceSelect.__new__(ui.SourceSelect)
    window.display_list = QueuedControl(early)
    window.quality_list = QueuedControl(early)
    window.source_session = session
    window.sources, window.list_sources = [], []
    window.filtered_sources, window.filter_applied = None, False
    window.item_information = {}
    window.last_error = ''
    window._source_revision = -1
    window._source_interacted = True
    window._auto_select_pending = False
    window._refresh_frontend_metadata = lambda **kwargs: None
    window.add_item_information_to_window = lambda value: None
    window.setProperty = lambda *args: None
    window.getControl = lambda control_id: window.quality_list if control_id == 1300 else window.display_list
    window._refresh_progressive_sources(capture_focus=False, force=True)
    window.display_list.dispatch()
    window.quality_list.dispatch()
    return window, session, source


def card_case(ui, Session, Stream, *, selected, early=False, add=True):
    window, session, source = make_window(ui, Session, Stream, early=early)
    control = window.display_list
    control.selectItem(selected)
    control.dispatch()
    expected = control.getSelectedItem().getProperty('source_key')
    before = dict(binds=control.binds, resets=control.resets, selects=control.selects)
    session.publish(session.epoch, 'fixture', [source(3)] if add else (),
                    state='RUNNING' if add else 'COMPLETE')
    window._refresh_progressive_sources()
    queued = [operation for operation, _ in control.queue]
    selected_before_dispatch = control.selected
    control.dispatch()
    window.quality_list.dispatch()
    actual = control.getSelectedItem().getProperty('source_key')
    return dict(passed=actual == expected,
                expected_selected_key=expected, actual_selected_key=actual,
                selected_index_before=selected,
                selected_index_before_final_dispatch=selected_before_dispatch,
                selected_index_after=control.selected,
                dispatch_before_read=early, queued_before_final_dispatch=queued,
                additional_native_binds=control.binds-before['binds'],
                additional_python_resets=control.resets-before['resets'],
                additional_python_selects=control.selects-before['selects'],
                native_count=control.size())


def quality_case(ui, Session, Stream):
    window, session, source = make_window(ui, Session, Stream)
    quality = window.quality_list
    selected = next(i for i, item in enumerate(quality.items)
                    if item.getProperty('quality') == '1080p')
    quality.selectItem(selected)
    quality.dispatch()
    session.publish(session.epoch, 'fixture', [source(3, '2160p')], state='RUNNING')
    window._refresh_progressive_sources()
    quality.dispatch()
    window.display_list.dispatch()
    actual = quality.getSelectedItem().getProperty('quality')
    return dict(passed=actual == '1080p', expected_quality='1080p', actual_quality=actual,
                final_quality_keys=[item.getProperty('quality') for item in quality.gui_items],
                selected_index_after=quality.selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    # Reuse only the repository's Kodi import scaffolding. Assertions and the
    # queued native-control semantics above are independent of its UI tests.
    original_argv = sys.argv[:]
    runpy.run_path(str(repo / 'tests/private_baseline/conftest.py'))
    sys.argv = original_argv
    from lib.gui import source_select as ui
    from lib.domain.torrent import TorrentStream
    from bobbi_core.source_list_session import SourceListSession
    ui.xbmcgui.ListItem = Item
    ui.get_random_color = lambda value, **kwargs: value
    ui.cache.get = lambda *args, **kwargs: {}
    ui.kodilog = lambda *args, **kwargs: None
    cases = [
        ('UI-NONFIRST-FOCUS-DEFERRED-BIND', lambda: card_case(ui, SourceListSession, TorrentStream, selected=1)),
        ('UI-QUALITY-FOCUS-NEW-TAB', lambda: quality_case(ui, SourceListSession, TorrentStream)),
        ('CONTROL-FIRST-CARD-FOCUS', lambda: card_case(ui, SourceListSession, TorrentStream, selected=0)),
        ('CONTROL-NONFIRST-EARLY-DISPATCH', lambda: card_case(ui, SourceListSession, TorrentStream, selected=1, early=True)),
        ('CONTROL-COMPLETION-WITHOUT-NEW-CARD', lambda: card_case(ui, SourceListSession, TorrentStream, selected=1, add=False)),
    ]
    rows = []
    for name, run in cases:
        try:
            rows.append(dict(id=name, **run()))
        except Exception as error:
            rows.append(dict(id=name, passed=False, error=type(error).__name__,
                             detail=str(error), traceback=traceback.format_exc()))
    paths = ['addons/plugin.video.bobbi/lib/gui/source_select.py',
             'addons/plugin.video.bobbi/lib/gui/base_window.py',
             'addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py',
             'tests/private_baseline/conftest.py']
    result = dict(schema=1,
                  scope='Actual product renderer; official Kodi 21.3 queued-control IO model; no device operation',
                  count=len(rows), passed=sum(row['passed'] for row in rows),
                  failed=sum(not row['passed'] and 'error' not in row for row in rows),
                  errors=sum('error' in row for row in rows), tests=rows,
                  sources=[dict(path=path, sha256=hashlib.sha256((repo/path).read_bytes()).hexdigest()) for path in paths],
                  kodi_sources=[
                      'https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Control.cpp#L1243-L1296',
                      'https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/guilib/GUIBaseContainer.cpp#L484-L493',
                  ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if hasattr(ui.cache, 'close'):
        ui.cache.close()
    return 2 if result['errors'] else 1 if result['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
