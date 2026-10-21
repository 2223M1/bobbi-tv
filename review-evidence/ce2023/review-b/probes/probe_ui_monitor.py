#!/usr/bin/env python3
"""Read-only, frozen-source diagnosis for three CE2014/CE2021 handoff gaps.

Usage: python probe_ui_monitor.py --repo /path/to/bobbi-tv

Designed for b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2. This is NOT general
regression CI for newer implementations. It reads three repository files,
AST-extracts selected actual functions/methods and executes them with explicit
GUI/IPC substitutes; it does not import the full addon, contact a device,
write repository files or execute an installer. Run only against trusted code.

The F02 observation is lost quality-tab focus/highlight. It does not establish
that the active filtering condition changes. Kodi 21.3-Omega's queued
LABEL_BIND/ITEM_SELECT behavior grounds the GUI substitute.

Exit 1: at least one targeted defect observed, and all probes compatible.
Exit 0: no targeted defect observed by the compatible probes; not acceptance.
Exit 2: missing source / incompatible interface / harness error in any probe.
JSON is written to stdout. No production source is bundled with this script.
"""
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from threading import Event
from types import ModuleType, SimpleNamespace

FROZEN_HEAD = 'b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2'
FILES = {
    'ui': 'addons/plugin.video.bobbi/lib/gui/source_select.py',
    'native': 'addons/plugin.video.bobbi/lib/native_player.py',
    'request': 'addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py',
}


class Incompatible(RuntimeError):
    pass


def extract(source, filename, methods=(), functions=()):
    tree = ast.parse(source, filename=filename)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in functions]
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef):
            nodes.extend(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods)
    expected = list(methods) + list(functions)
    if sorted(n.name for n in nodes) != sorted(expected):
        raise Incompatible('Expected frozen methods/functions are missing or ambiguous')
    return compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec')


class Item:
    def __init__(self, label):
        self.label, self.props = label, {}

    def getLabel(self): return self.label
    def setLabel(self, label): self.label = label
    def getProperty(self, key): return self.props.get(key, '')
    def setProperty(self, key, value): self.props[key] = value


class DelayedControl:
    def __init__(self):
        self.items, self.selected, self.queue = [], 0, []

    def addItem(self, item):
        self.items.append(item)
        self.queue.append(('LABEL_BIND', 0))

    def removeItem(self, position):
        self.items.pop(position)
        self.queue.append(('LABEL_BIND', 0))

    def selectItem(self, position): self.queue.append(('ITEM_SELECT', position))
    def getSelectedPosition(self): return self.selected

    def flush(self):
        messages = self.queue[:]
        for _, position in self.queue:
            self.selected = position
        self.queue.clear()
        return messages


def probe_quality(sources):
    env = dict(re=re, xbmcgui=SimpleNamespace(ListItem=Item))
    exec(extract(sources['ui'], FILES['ui'], methods=['populate_qualities_header'],
        functions=['_plain_source_label', '_quality_key', '_source_quality', '_quality_tabs']), env)
    control = DelayedControl()
    window = SimpleNamespace(sources=[SimpleNamespace(quality='1080p')],
        getControl=lambda _id: control, setProperty=lambda *a: None)
    env['populate_qualities_header'](window)
    control.flush()
    control.selectItem(1)
    control.flush()
    before = control.items[control.selected].getProperty('quality')
    if before != '1080p':
        raise Incompatible('Could not establish the expected 1080p tab fixture')
    window.sources.append(SimpleNamespace(quality='2160p'))
    env['populate_qualities_header'](window)
    immediate_index = control.selected
    messages = control.flush()
    after = control.items[control.selected].getProperty('quality')
    defect = after != before
    return dict(case='F02_quality_tab_focus', defect_observed=defect,
        before=before, immediate_index=immediate_index, messages=messages, after=after,
        filtering_condition_changed='not_measured',
        status='defect_reproduced' if defect else 'not_reproduced')


def probe_monitor(sources, mode):
    session, native = 'request-a', 'native-a'
    active = dict(boot_id='boot', epoch=1, desired=dict(request_id=session, cancelled=False),
        observed=dict(request_id=session, native_instance=native, av_started=True), terminal=None)
    terminal = dict(active, observed=None,
        terminal=dict(request_id=session, native_instance=native, reason='NATURAL_EOF'))
    calls, events, video_checks, logged_errors = [], [], [], []

    def call(body):
        calls.append(body)
        if mode == 'unavailable' and len(calls) <= 3:
            raise OSError('short IPC interruption')
        if mode == 'terminal_race' and len(calls) >= 2:
            return terminal
        return active

    request = ModuleType('lib.cinema.playback_request')
    request.__dict__.update(call=call, time=SimpleNamespace(monotonic=lambda: 100., sleep=lambda _: None))
    exec(extract(sources['request'], FILES['request'],
        functions=['owned_state', 'context', 'terminal_state']), request.__dict__)
    previous = sys.modules.get(request.__name__)
    sys.modules[request.__name__] = request

    def log(message, **kwargs):
        if kwargs.get('level') == 3:
            logged_errors.append(message)

    env = dict(kodilog=log, xbmc=SimpleNamespace(LOGWARNING=2, LOGERROR=3),
        get_setting=lambda *a: False, TERMINAL_RECONCILIATION_SECONDS=3.)

    def video():
        video_checks.append(True)
        return len(video_checks) == 1

    player = SimpleNamespace(data=dict(selection_policy='exact', mode='movies'),
        playback_session_id=session, _native_instance=native, _cinema_cancel=Event(),
        _was_superseded=False, skip_intro_enabled=False,
        isPlayingVideo=video, _wait_for_video_start=lambda: True,
        handle_playback_start=lambda: True,
        _cinema_phase=lambda name: events.append(name),
        wait_cinema_terminal=lambda **k: events.append('WAIT_TERMINAL'),
        queue_cinema_natural_end=lambda: events.append('QUEUE_NEXT'),
        handle_playback_stop=lambda: events.append('STOP_BOOKKEEPING'),
        clear_playback_properties=lambda: events.append('CLEANUP'),
        _release_playback_session=lambda: events.append('RELEASE'),
        kill_dialog=lambda: events.append('HARNESS_OR_MONITOR_ERROR'))
    for name in ['_record_started_history', 'start_cinema_preparation', 'select_audio_stream',
                 'handle_subtitle_selection', 'offer_terminal_actions']:
        setattr(player, name, lambda: None)
    try:
        exec(extract(sources['native'], FILES['native'], methods=['monitor',
            '_owns_playback_session', '_matches_requested_playback']), env)
        player._owns_playback_session = lambda: env['_owns_playback_session'](player)
        player._matches_requested_playback = lambda: env['_matches_requested_playback'](player)
        env['monitor'](player)
    finally:
        if previous is None:
            sys.modules.pop(request.__name__, None)
        else:
            sys.modules[request.__name__] = previous
    if logged_errors or 'HARNESS_OR_MONITOR_ERROR' in events:
        raise Incompatible('Monitor raised/caught an error; not evidence that the defect is fixed: '
                           + '; '.join(logged_errors))
    defect = (player._was_superseded and 'WAIT_TERMINAL' not in events
              and 'QUEUE_NEXT' not in events and player._cinema_cancel.is_set())
    if not defect and 'WAIT_TERMINAL' not in events:
        raise Incompatible('Changed monitor flow is outside this frozen-source probe')
    return dict(case='F03_'+mode, snapshot_calls=len(calls),
        superseded=player._was_superseded, terminal_wait_called='WAIT_TERMINAL' in events,
        next_queued='QUEUE_NEXT' in events, cancelled=player._cinema_cancel.is_set(),
        events=events, defect_observed=bool(defect),
        status='defect_reproduced' if defect else 'not_reproduced')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path, help='Trusted bobbi-tv checkout root')
    args = parser.parse_args()
    result = dict(probe='CE2021_UI_MONITOR', frozen_head=FROZEN_HEAD,
        repo=str(args.repo.resolve()),
        scope='AST-selected frozen-source control flow; not full-addon, Kodi or Release ZIP execution',
        quality_note='Tab focus/highlight only; active filtering condition is not measured',
        newer_versions='Not generic CI: incompatible changed interfaces yield exit 2',
        source_sha256={}, cases=[])
    try:
        sources = {}
        for key, path in FILES.items():
            data = (args.repo / path).read_bytes()
            result['source_sha256'][path] = sha256(data).hexdigest()
            sources[key] = data.decode('utf-8-sig')
    except (OSError, UnicodeError) as error:
        result.update(exit_code=2, error=f'{type(error).__name__}: {error}')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    probes = [('F02_quality_tab_focus', lambda: probe_quality(sources)),
              ('F03_unavailable', lambda: probe_monitor(sources, 'unavailable')),
              ('F03_terminal_race', lambda: probe_monitor(sources, 'terminal_race'))]
    for name, run in probes:
        try:
            result['cases'].append(run())
        except Exception as error:
            result['cases'].append(dict(case=name, status='unsupported',
                error=f'{type(error).__name__}: {error}'))
    if any(case['status'] == 'unsupported' for case in result['cases']):
        code = 2
    elif any(case['defect_observed'] for case in result['cases']):
        code = 1
    else:
        code = 0
    result['exit_code'] = code
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
