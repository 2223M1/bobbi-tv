"""Real player/resolver methods and authority; only native IO/time are doubled."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import Event
from types import MethodType, ModuleType, SimpleNamespace
import sys

import pytest

from bobbi_core import playback_request as protocol
from test_playback_authority import playing, select

ROOT = Path(__file__).resolve().parents[2]


def methods(path, name, selected, scope):
    original = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
                    if isinstance(node, ast.ClassDef) and node.name == name)
    body = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in selected]
    cls = ast.ClassDef(name=name, bases=[], keywords=[], decorator_list=[], body=body)
    tree = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(tree, str(path), 'exec'), scope)
    return scope[name]


@pytest.fixture
def scene(monkeypatch):
    authority, native, args = playing()
    request, token = args['request_id'], 'd' * 32
    visible, clock, calls, logs, properties = {13001}, [100.0], [], [], {}
    authority.dispatch(dict(args, operation='register_window', token=token, role='loading'))
    native.loading_window = lambda dialog, expected: dict(visible=dialog in visible,
        matching=expected == token, modal=False, active_window=10000)
    original_fullscreen = native.fullscreen
    def fullscreen(command):
        result = original_fullscreen(command)
        native.gui['fullscreen_instance'] = command['native_instance']
        return result
    native.fullscreen = fullscreen
    faults, hooks, latencies, timed_calls = {}, {}, {}, []
    def call(message, **kwargs):
        calls.append(deepcopy(message))
        operation = message['operation']
        timed_calls.append((clock[0], operation, kwargs.get('timeout', .3)))
        latency = latencies.get(operation, 0)
        budget = kwargs.get('timeout', .3)
        clock[0] += min(latency, budget)
        if latency > budget:
            raise OSError('bounded local timeout')
        fault = faults.get(operation)
        if fault:
            if fault['remaining'] != -1:
                fault['remaining'] -= 1
                if fault['remaining'] == 0:
                    faults.pop(operation)
            if fault['lost_ack']:
                authority.dispatch(message)
            raise OSError('private unavailable body must not escape')
        if operation in hooks:
            hooks.pop(operation)()
        return authority.dispatch(message)
    monkeypatch.setattr(protocol, 'call', call)
    adapter = ModuleType('lib.cinema.playback_request')
    for key in ('call', 'context', 'owned_state', 'monitor_state'):
        setattr(adapter, key, getattr(protocol, key))
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', adapter)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_ipc', adapter)
    xbmc = SimpleNamespace(LOGWARNING=2, LOGINFO=1, LOGERROR=3,
        getCondVisibility=lambda value: int(value.split('(')[1].split(')')[0]) in visible,
        getInfoLabel=lambda value: token if '(13001)' in value else '',
        sleep=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000))
    scope = dict(xbmc=xbmc, kodilog=lambda value, **kw: logs.append(value),
        set_property=lambda key, value: properties.__setitem__(key, value), json_dumps=json.dumps, hashlib=hashlib,
        monotonic=lambda: clock[0], sleep=xbmc.sleep, HANDOFF_CONFIRMATION_TIMEOUT_SECONDS=1,
        HANDOFF_CONFIRMATION_POLL_MS=50, TERMINAL_RECONCILIATION_SECONDS=3,
        get_setting=lambda *args: False)
    Resolver = methods(ROOT/'addons/plugin.video.bobbi/lib/gui/resolver_window.py', 'ResolverWindow',
        {'_capture_loading_dialog','_handoff_rejected','handle_playback_started','handle_playback_error',
         'handle_presentation_deferred','_owns_selection','close_windows'}, scope)
    resolver = Resolver()
    resolver.item_information = {'request_id':request}
    resolver.cancel_event, resolver.resolved, resolver._modeless = Event(), False, True
    resolver._window_context, resolver._window_token, resolver._dialog_id = args, token, 13001
    resolver._owns_selection = lambda: authority.owner._current(args['boot_id'], args['epoch'], request)
    closes = []
    def close_windows():
        closes.append(token)
        visible.clear()
    resolver.close_windows = close_windows
    resolver.close = close_windows
    Player = methods(ROOT/'addons/plugin.video.bobbi/lib/native_player.py', 'JacktookPLayer',
        {'handle_playback_start','cancel_playback','_confirm_cinema_fullscreen','monitor'}, scope)
    player = Player()
    player.data = dict(selection_policy='exact', mode='tv', cinema_continuity=True)
    player.playback_session_id, player._cinema_cancel = request, resolver.cancel_event
    player._owner_context, player._resolution_answered = args, True
    player._native_instance = native.current['native_instance']
    player._owns_playback_session = resolver._owns_selection
    player._matches_requested_playback = lambda: True
    player.isPlayingVideo = lambda: native.current['phase'] != 'TERMINAL'
    player.getPlayingFile = lambda: 'test-file'
    player._record_cinema_handoff = lambda phase: properties.__setitem__('handoff', phase)
    player._cleanup_playback_session = lambda: None
    player.on_started = resolver.handle_playback_started
    player.on_presentation_deferred = resolver.handle_presentation_deferred
    confirmed = []
    player.on_handoff = lambda: confirmed.append(True)
    return SimpleNamespace(player=player, resolver=resolver, authority=authority, native=native, args=args,
        calls=calls, logs=logs, properties=properties, clock=clock, faults=faults, hooks=hooks,
        visible=visible, closes=closes, confirmed=confirmed, latencies=latencies, timed_calls=timed_calls)


@pytest.mark.parametrize('operation,lost_ack', [('begin_window_close',False),('begin_window_close',True),
    ('close_window',False),('close_window',True),('request_fullscreen',False),('request_fullscreen',True),
    ('confirm_fullscreen',False),('confirm_fullscreen',True)])
def test_transient_presentation_recovers_same_request_without_stop_or_duplicate_open(scene, operation, lost_ack):
    scene.faults[operation] = dict(remaining=1, lost_ack=lost_ack)
    assert scene.player.handle_playback_start() is True
    assert scene.player._media_started and scene.resolver.resolved
    scene.clock[0] += .1
    assert scene.player.handle_playback_start() is True
    assert scene.player._handoff_confirmed and scene.confirmed == [True]
    assert scene.closes == ['d' * 32]
    assert not scene.native.commands and not scene.authority.owner.desired['cancelled']
    assert len(scene.native.gui_commands) == 1
    assert all(row.get('request_id', scene.args['request_id']) == scene.args['request_id'] for row in scene.calls)
    assert 'private unavailable' not in '\n'.join(scene.logs)


@pytest.mark.parametrize('operation', ['begin_window_close','close_window','request_fullscreen','confirm_fullscreen'])
def test_persistent_unavailable_finishes_presentation_budget_but_keeps_media(scene, operation):
    scene.faults[operation] = dict(remaining=-1, lost_ack=False)
    for _ in range(8):
        assert scene.player.handle_playback_start() is True
        scene.clock[0] += .1
    assert scene.player._media_started and scene.player._presentation_finished
    assert not getattr(scene.player, '_handoff_confirmed', False)
    assert scene.resolver.resolved and not scene.authority.owner.desired['cancelled']
    assert not scene.native.commands
    attempts = sum(row['operation'] == operation for row in scene.calls)
    assert attempts <= 4
    scene.resolver.handle_playback_error()
    assert scene.resolver.resolved
    assert scene.properties['handoff'] == 'DEFERRED'
    assert not scene.visible


@pytest.mark.parametrize('change', ['cancel','replacement','back','terminal','external_video','external_audio'])
def test_new_intent_or_native_terminal_during_retry_never_activates_or_stops(scene, change):
    scene.faults['close_window'] = dict(remaining=1, lost_ack=False)
    assert scene.player.handle_playback_start()
    if change == 'cancel':
        scene.resolver.cancel_event.set()
        scene.authority.owner.cancel(scene.args['boot_id'], scene.args['epoch'], scene.args['request_id'])
    elif change == 'replacement':
        select(scene.authority, ident='new-selection')
    elif change == 'back':
        scene.native.gui['gui_user_intent'] += 1
    elif change == 'terminal':
        scene.native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    else:
        scene.native.epoch += 1
        if change == 'external_video':
            scene.native.current.update(native_instance='other-video', request_id='', file_identity='external', sequence=1)
        else:
            scene.native.current = None
            scene.player.isPlayingVideo = lambda: False
    scene.clock[0] += .1
    scene.player.handle_playback_start()
    assert not scene.native.gui_commands and not scene.native.commands
    assert not getattr(scene.player, '_handoff_confirmed', False)


def test_lost_close_ack_requires_exact_receipt_and_does_not_close_another_token(scene):
    scene.faults['close_window'] = dict(remaining=1, lost_ack=True)
    assert scene.player.handle_playback_start()
    message = dict(scene.args, operation='close_window', token='d' * 32)
    assert scene.authority.dispatch(message) == {'closed': True}
    assert scene.authority.dispatch(dict(message, token='e' * 32)) == {'closed': False}
    scene.native.gui['gui_user_intent'] += 1
    assert scene.authority.dispatch(message) == {'closed': False}


def test_back_after_confirmed_handoff_never_replays_fullscreen(scene):
    assert scene.player.handle_playback_start() is True
    scene.native.gui['gui_user_intent'] += 1
    scene.native.gui['fullscreen_instance'] = ''
    for _ in range(5):
        scene.player.handle_playback_start()
    assert len(scene.native.gui_commands) == 1 and not scene.native.commands
    assert scene.confirmed == [True]


def test_account_epoch_change_during_retry_blocks_old_presentation_admission(scene):
    class Accounts:
        current = dict(account_id='115:' + '1' * 64, epoch=1, authenticated=True)
        def is_current(self, expected):
            return expected == self.current
        def run_if_current(self, expected, operation):
            if not self.is_current(expected):
                raise RuntimeError('ACCOUNT_CHANGED')
            return operation()
    accounts = Accounts()
    scene.authority.configure_accounts(accounts)
    scene.authority.selection_account = dict(accounts.current)
    scene.faults['close_window'] = dict(remaining=1, lost_ack=True)
    assert scene.player.handle_playback_start()
    accounts.current = dict(accounts.current, epoch=2)
    scene.clock[0] += .1
    assert scene.player.handle_playback_start() is True
    assert not scene.native.gui_commands and not scene.native.commands
    assert not getattr(scene.player, '_handoff_confirmed', False)


def test_deadline_is_not_restarted_by_unavailable(scene):
    scene.faults['close_window'] = dict(remaining=-1, lost_ack=False)
    assert scene.player.handle_playback_start()
    deadline = scene.player._presentation_deadline
    before = len(scene.calls)
    scene.clock[0] = deadline
    assert scene.player.handle_playback_start() is True
    assert scene.player._presentation_finished and scene.player._presentation_deadline == deadline
    assert len(scene.calls) == before
    assert not scene.native.commands


def test_deferred_presenter_close_does_not_close_foreign_modal_or_grant_fullscreen(scene):
    scene.resolver.media_started = True
    scene.visible.add(10126)
    scene.resolver.close = lambda: scene.visible.discard(13001)
    assert scene.resolver.handle_presentation_deferred() is True
    assert scene.visible == {10126}
    assert not scene.native.gui_commands and not scene.native.commands
    assert scene.authority.owner.windows['d' * 32]['role'] == 'loading'


@pytest.mark.parametrize('failure', ['reused_slot','duplicate_token','cancelled'])
def test_deferred_presenter_does_not_close_an_unproved_window(scene, failure):
    scene.resolver.media_started = True
    gui = scene.resolver._capture_loading_dialog.__func__.__globals__['xbmc']
    if failure == 'reused_slot':
        gui.getInfoLabel = lambda value: 'other-token'
    elif failure == 'duplicate_token':
        scene.visible.add(13002)
        gui.getInfoLabel = lambda value: 'd' * 32
    else:
        scene.resolver.cancel_event.set()
    assert scene.resolver.handle_presentation_deferred() is False
    assert not scene.closes and not scene.native.gui_commands


def test_previous_close_error_still_submits_own_close_and_records_it(scene):
    closes = []
    def previous_close():
        closes.append('previous')
        raise RuntimeError('retired previous presenter')
    scene.resolver.close_windows = MethodType(type(scene.resolver).close_windows, scene.resolver)
    scene.resolver.previous_window = SimpleNamespace(setProperty=lambda *args: None, close=previous_close)
    scene.resolver.close = lambda: (closes.append('own'), scene.visible.discard(13001))
    assert scene.player.handle_playback_start() is True
    assert closes == ['previous', 'own'] and not scene.visible
    assert scene.resolver._loading_close_attempted and scene.resolver._loading_close_issued
    assert not scene.native.commands


def test_true_ownership_reads_and_commands_share_absolute_remaining_budget(scene):
    scene.resolver._owns_selection = MethodType(type(scene.resolver)._owns_selection, scene.resolver)
    scene.resolver.close_windows = lambda: None
    scene.latencies.update(snapshot=.25, begin_window_close=.25)
    began = scene.clock[0]
    assert scene.player.handle_playback_start() is True
    assert scene.clock[0] <= began + 3.001
    assert scene.player._presentation_finished
    assert all(0 < budget <= min(.3, began + 3 - started) + 1e-9
               for started, operation, budget in scene.timed_calls)
    assert scene.resolver._handoff_read_deadline is None
    assert not scene.native.commands and not scene.native.gui_commands


def test_close_attempt_is_not_mistaken_for_successful_own_submission(scene):
    closes = []
    scene.resolver.close_windows = MethodType(type(scene.resolver).close_windows, scene.resolver)
    scene.resolver.previous_window = None
    def close():
        closes.append('own')
        if len(closes) == 1:
            raise RuntimeError('GUI close not submitted')
        scene.visible.discard(13001)
    scene.resolver.close = close
    assert scene.player.handle_playback_start() is True
    assert closes == ['own', 'own'] and not scene.visible
    assert scene.resolver._loading_close_issued
    assert not scene.native.commands


def test_recovered_handoff_keeps_monitor_progress_and_natural_eof_lifecycle(scene):
    player, events = scene.player, []
    scene.faults['close_window'] = dict(remaining=1, lost_ack=True)
    player._wait_for_video_start = lambda: True
    player.skip_intro_enabled = False
    player._cinema_phase = lambda phase: events.append(phase)
    player._record_started_history = lambda: events.append('started_history')
    player.update_playback_progress = lambda: events.append('progress')
    player.check_cinema_stall = player._consume_next_dialog_action = lambda: False
    player.queue_cinema_transport_end = lambda budget: False
    player.wait_cinema_terminal = lambda **kwargs: scene.authority.refresh()
    for name in ('start_cinema_preparation','select_audio_stream','handle_subtitle_selection',
        '_apply_simkl_resume','_apply_trakt_resume','_apply_nuvio_resume','check_cinema_subtitles',
        'handle_trakt_pause_resume','check_cinema_continuity','check_autoscrape_threshold',
        'playback_close_dialogs','check_next_dialog','check_skip_intro','check_stinger_notification',
        'check_cinema_transport_recovery','handle_playback_stop','offer_terminal_actions',
        'kill_dialog','clear_playback_properties','_release_playback_session'):
        setattr(player, name, lambda name=name: events.append(name))
    def tick():
        scene.clock[0] += .1
        if events.count('progress') >= 2:
            scene.native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    player._wait_monitor_tick = tick
    def next_episode():
        result = scene.authority.dispatch(dict(scene.args, operation='authorize_next',
            native_instance=scene.native.current['native_instance'], selection_identity='next-exact'))
        assert result['authorized']
        events.append('authorized_next')
    player.queue_cinema_natural_end = next_episode
    player.monitor()
    assert events.count('started_history') == 1 and events.count('progress') == 2
    assert player._handoff_confirmed and 'authorized_next' in events and 'handle_playback_stop' in events
    assert 'kill_dialog' not in events and not scene.native.commands
