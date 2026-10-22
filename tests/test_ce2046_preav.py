#!/usr/bin/env python3
"""Actual resolver/run/activation control flow with deterministic IPC/Kodi IO.

Exercises an already accepted selection through the real ResolverWindow.doModal,
resolve_source, _owns_selection and real player.run/_activate_playback_session.
PlaybackOwner, playback_request.context/owned_state, and attach_context are real.
Provider resolution, account capture, GUI operations, and the final media dispatch
are explicit IO doubles. Reaching dispatch is not AV_STARTED or device playback.
There is no socket, device, login, source fetch, or playback command in this file.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from threading import Event
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Optional
from uuid import uuid4


def extracted_class(path, original, name, methods, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    source = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == original)
    nodes = [deepcopy(node) for node in source.body if isinstance(node, ast.FunctionDef) and node.name in methods]
    assert {node.name for node in nodes} == set(methods)
    cls = ast.ClassDef(name=name, bases=[], keywords=[], body=nodes, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name]


def module(name):
    value = ModuleType(name)
    value.__path__ = []
    sys.modules[name] = value
    return value


def run_case(root, case):
    from bobbi_core.playback_owner import PlaybackOwner
    from bobbi_core import playback_request

    rid, replacement = 'a' * 32, 'b' * 32
    identity = 'transport:' + '1' * 64
    owner = PlaybackOwner(boot_id='c' * 32)
    owner.select(owner.boot_id, owner.epoch, rid, identity)
    initial = owner.snapshot()
    calls, events, logs, players, props = [], [], [], [], {}
    reads = 0

    def rpc(message, **kwargs):
        nonlocal reads
        operation = message['operation']
        calls.append(operation)
        if operation == 'snapshot':
            reads += 1
            if reads == case.get('inject_at') or (case.get('persistent') and reads > case.get('inject_at', 999)):
                if case['kind'] == 'reset':
                    raise ConnectionResetError('synthetic one-shot IPC read gap')
                if case['kind'] == 'oserror':
                    raise OSError('synthetic one-shot IPC read gap')
                if case['kind'] == 'replacement':
                    owner.select(owner.boot_id, owner.epoch, replacement, 'transport:' + '2' * 64)
                if case['kind'] == 'cancel':
                    owner.cancel(owner.boot_id, owner.epoch, rid)
            if reads == case.get('inject_at', -999) + 1:
                mutation = case.get('recover_kind')
                if mutation == 'cancel':
                    owner.cancel(owner.boot_id, owner.epoch, rid)
                elif mutation == 'replacement':
                    owner.select(owner.boot_id, owner.epoch, replacement, 'transport:' + '2' * 64)
                elif mutation == 'boot':
                    owner.boot_id = 'e' * 32
                elif mutation == 'epoch':
                    owner.epoch += 1
            return owner.snapshot()
        if operation == 'register_window':
            return dict(registered=owner.register_window(message['boot_id'], message['epoch'],
                message['request_id'], message['token'], message['role']))
        raise AssertionError('Unexpected control command: ' + operation)

    playback_request.call = rpc
    module('lib')
    module('lib.cinema')
    ipc = module('lib.cinema.playback_ipc')
    ipc.call = rpc
    sys.modules['lib.cinema.playback_request'] = playback_request
    account = module('lib.cinema.preparation_client')
    account.capture_account = lambda *a, **k: events.append('optional_account_io')
    xbmc = SimpleNamespace(LOGWARNING=2, LOGINFO=1)
    namespace = dict(re=re, uuid4=uuid4, xbmc=xbmc, Any=Any, Dict=Dict, Optional=Optional,
        json=json, json_dumps=json.dumps, monotonic=lambda: 0.0,
        kodilog=lambda message, **kwargs: logs.append(message),
        set_property=lambda key, value: props.__setitem__(key, value),
        clear_property=lambda key: props.pop(key, None),
        close_busy_dialog=lambda: events.append('close_busy_dialog'),
        ACTIVE_PLAYER_SESSION_PROPERTY='bobbi_active_player_session',
        PLAYNEXT_ACTION_PROPERTY='bobbi_playnext_action',
        make_listing=lambda data: SimpleNamespace(),
        notification=lambda *a, **k: events.append('notification'))
    player_path = root / 'addons/plugin.video.bobbi/lib/native_player.py'
    window_path = root / 'addons/plugin.video.bobbi/lib/gui/resolver_window.py'
    player_class = extracted_class(player_path, 'JacktookPLayer', 'ReviewPlayer',
        ['run', '_activate_playback_session', '_cinema_phase'], namespace)

    def factory(**callbacks):
        player = player_class()
        players.append(player)
        player._was_superseded = False
        player._resolution_answered = False
        player._cinema_cancel = callbacks['cancel_event']
        player.on_error = lambda: events.append('player_error_callback')
        player.set_constants = lambda data: (setattr(player, 'data', data), setattr(player, 'url', data['url']))
        player.clear_playback_properties = lambda: events.append('clear_compat_properties')
        player._is_trakt_tracking_excluded = lambda: True
        player.play_video = lambda item: events.append('reached_final_media_dispatch_double')
        player.run_error = lambda error: events.append('run_error:' + type(error).__name__)
        player._drain_nextep_queue = lambda: False
        return player

    namespace['JacktookPLayer'] = factory
    window_class = extracted_class(window_path, 'ResolverWindow', 'ReviewWindow',
        ['doModal', 'resolve_source', '_owns_selection', '_handoff_rejected'], namespace)
    window = window_class()
    window.source = SimpleNamespace(isPack=False, debridType='')
    window.item_information = dict(selection_policy='exact', request_id=rid,
        _selection_context=playback_request.context(initial, rid))
    window._update_window_properties = lambda source: None
    window.is_subtitle_download = False
    window.local_subtitle_path = None
    window._window_token = 'd' * 32
    window.cancel_event = Event()
    window.user_cancelled = False
    window.resolved = False
    window.error_message = ''
    window.resolution_answered = False
    window.startup_failure_category = None
    window.preparation_intent = None
    window.player = None
    window.show = lambda: events.append('show_loading_window')
    window.close = lambda: events.append('close_loading_window')
    data = dict(selection_policy='exact', request_id=rid, mode='movies',
                is_torrent=False, url='https://fixture.invalid/not-fetched.mkv')
    window.resolve_single_source = lambda: setattr(window, 'playback_info', dict(data))
    for name in ('handle_playback_started', 'handle_playback_error', 'update_progress',
                 'handle_handoff_confirmed', 'handle_presentation_deferred'):
        setattr(window, name, lambda n=name: events.append(n))
    escaped = None
    try:
        window.doModal(False)
    except Exception as error:
        escaped = type(error).__name__

    reads_before_probe = reads
    state = owner.snapshot()
    # The injected exception is one-shot. An immediately subsequent real context
    # check proves whether the same selection is still current after the read gap.
    try:
        playback_request.context(rpc({'operation': 'snapshot'}), rid)
        post_read_current = True
    except (OSError, RuntimeError):
        post_read_current = False
    dispatches = events.count('reached_final_media_dispatch_double')
    forbidden = [call for call in calls if call not in ('snapshot', 'register_window')]
    error_notice = bool(window.error_message or 'player_error_callback' in events
                        or 'handle_playback_error' in events or 'notification' in events)
    closed = bool(state['desired']['resolver_failure'] or state['desired']['cancelled'])
    if case['kind'] == 'normal':
        contract_pass = dispatches == 1 and not forbidden
    elif case['kind'] in ('replacement', 'cancel'):
        contract_pass = dispatches == 0 and not forbidden and not post_read_current and not error_notice
    else:
        contract_pass = not forbidden and bool(dispatches == 1 or error_notice or closed)
    return dict(id=case['id'], injected=case, contract_pass=contract_pass,
        initial_owner=initial, owner_after=state, reads_before_diagnostic_probe=reads_before_probe,
        same_request_still_current_on_next_read=post_read_current, escaped_exception=escaped,
        player_was_superseded=getattr(players[-1], '_was_superseded', None) if players else None,
        reached_dispatch_count=dispatches, error_message=window.error_message,
        error_callback_or_notification=error_notice, forbidden_control_calls=forbidden,
        operations=calls, events=events, logs=logs)



import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('inject_at', [1, 2, 3, 4])
@pytest.mark.parametrize('kind,persistent,recover_kind', [
    ('normal', False, None), ('reset', False, None), ('oserror', False, None),
    ('replacement', False, None), ('cancel', False, None),
    ('reset', True, None), ('reset', False, 'cancel'),
    ('reset', False, 'replacement'), ('reset', False, 'boot'), ('reset', False, 'epoch')])
def test_actual_resolver_player_preav(inject_at, kind, persistent, recover_kind):
    from bobbi_core import playback_request
    previous_modules, previous_call = dict(sys.modules), playback_request.call
    try:
        row = run_case(ROOT, dict(id='production_preav', kind=kind,
            inject_at=inject_at, persistent=persistent, recover_kind=recover_kind))
    finally:
        playback_request.call = previous_call
        for name in list(sys.modules):
            if name == 'lib' or name.startswith('lib.'):
                if name in previous_modules: sys.modules[name] = previous_modules[name]
                else: sys.modules.pop(name, None)
    assert not row['escaped_exception'], row
    assert not row['forbidden_control_calls'], row
    if kind in ('cancel', 'replacement') or recover_kind:
        assert row['reached_dispatch_count'] == 0, row
        assert not row['error_callback_or_notification'], row
    elif persistent:
        assert row['reached_dispatch_count'] == 0, row
        assert row['error_callback_or_notification'], row
        assert row['player_was_superseded'] is not True, row
    else:
        assert row['reached_dispatch_count'] == 1, row
        assert not row['error_callback_or_notification'], row


@pytest.mark.parametrize('persistent', [False, True])
def test_source_window_before_show_has_visible_feedback_and_stops_jobs(monkeypatch, persistent):
    from bobbi_core import playback_request
    reads, shown, notices, stopped = [], [], [], []
    owner = __import__('bobbi_core.playback_owner', fromlist=['PlaybackOwner']).PlaybackOwner()
    def call(message, **kwargs):
        assert message['operation'] == 'snapshot'
        reads.append(True)
        if persistent or len(reads) == 1:
            raise ConnectionResetError('fixture')
        return owner.snapshot()
    monkeypatch.setattr(playback_request, 'call', call)
    monkeypatch.setitem(sys.modules, 'lib.native_support', SimpleNamespace(available=lambda: True))
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', playback_request)
    class Parent:
        def doModal(self): shown.append(True)
    path = ROOT/'addons/plugin.video.bobbi/lib/gui/source_select.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SourceSelect')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'doModal')
    block = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='SourceSelect',
        bases=[ast.Name(id='Parent', ctx=ast.Load())], keywords=[], body=[method], decorator_list=[])], type_ignores=[]))
    ns = dict(Parent=Parent, notification=lambda *a, **k: notices.append(a))
    exec(compile(block, str(path), 'exec'), ns)
    window = ns['SourceSelect']()
    window.source_session = SimpleNamespace(cancel=lambda: stopped.append('session')) if persistent else None
    window.source_pump = SimpleNamespace(cancel=lambda: stopped.append('pump')) if persistent else None
    window.setProperty = lambda *args: None
    window.resolved = False
    assert window.doModal() is False
    if persistent:
        assert len(reads) == 3 and not shown and len(notices) == 1
        assert stopped == ['pump', 'session']
    else:
        assert len(reads) == 2 and shown == [True] and not notices
