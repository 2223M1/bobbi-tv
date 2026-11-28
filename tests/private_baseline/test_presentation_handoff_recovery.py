"""Real player/resolver methods and authority; only native IO/time are doubled."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import Event
from types import MethodType, SimpleNamespace

import pytest

from bobbi_core import playback_request as protocol
from test_playback_authority import playing, select
from test_presentation_transient_properties import (
    MemoryWindow, RecordingCache, load_property_api, PRESENTATION_PROPERTIES,
)

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
    visible, clock, calls, logs = {13001}, [100.0], [], []
    window, cache = MemoryWindow(), RecordingCache()
    properties, property_events = window.values, []
    property_api = load_property_api(window, cache)
    original_set = window.setProperty
    def set_window_property(key, value):
        property_events.append((clock[0], key, value))
        original_set(key, value)
    window.setProperty = set_window_property
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
    client = protocol.Client(call)
    xbmc = SimpleNamespace(LOGWARNING=2, LOGINFO=1, LOGERROR=3,
        getCondVisibility=lambda value: int(value.split('(')[1].split(')')[0]) in visible,
        getInfoLabel=lambda value: token if '(13001)' in value else '',
        sleep=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000))
    scope = dict(xbmc=xbmc, kodilog=lambda value, **kw: logs.append(value),
        set_property=property_api.set_property, json_dumps=json.dumps, hashlib=hashlib,
        get_visibility=lambda value: bool(native.gui['fullscreen_instance']),
        video_fullscreen_check='Window.IsActive(fullscreenvideo)',
        monotonic=lambda: clock[0], sleep=xbmc.sleep, HANDOFF_CONFIRMATION_TIMEOUT_SECONDS=1,
        HANDOFF_CONFIRMATION_POLL_MS=50, TERMINAL_RECONCILIATION_SECONDS=3,
        get_setting=lambda *args: False)
    Resolver = methods(ROOT/'addons/plugin.video.bobbi/lib/gui/resolver_window.py', 'ResolverWindow',
        {'_capture_loading_dialog','_handoff_rejected','handle_playback_started','handle_playback_error',
         'handle_presentation_deferred','_owns_selection','close_windows'}, scope)
    resolver = Resolver()
    resolver.playback_client = client
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
        {'handle_playback_start','cancel_playback','_confirm_cinema_fullscreen','monitor',
         '_record_cinema_handoff'}, scope)
    player = Player()
    player.playback_client = client
    player.data = dict(selection_policy='exact', mode='tv', cinema_continuity=True)
    player.playback_session_id, player._cinema_cancel = request, resolver.cancel_event
    player._owner_context, player._resolution_answered = args, True
    player._native_instance = native.current['native_instance']
    player._owns_playback_session = resolver._owns_selection
    player._matches_requested_playback = lambda: True
    player.isPlayingVideo = lambda: native.current['phase'] != 'TERMINAL'
    player.getPlayingFile = lambda: 'test-file'
    player._cleanup_playback_session = lambda: None
    player.on_started = resolver.handle_playback_started
    player.on_presentation_deferred = resolver.handle_presentation_deferred
    confirmed = []
    player.on_handoff = lambda: confirmed.append(True)
    return SimpleNamespace(player=player, resolver=resolver, authority=authority, native=native, args=args,
        calls=calls, logs=logs, properties=properties, clock=clock, faults=faults, hooks=hooks,
        visible=visible, closes=closes, confirmed=confirmed, latencies=latencies, timed_calls=timed_calls,
        gui=xbmc, cache=cache, property_api=property_api, property_events=property_events)


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
    assert json.loads(scene.properties['bobbi_cinema_handoff'])['phase'] == 'DEFERRED'
    assert scene.player._presentation_result['phase'] == 'DEFERRED'
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
    # A local retirement wait can return pending before the absolute deadline;
    # retries share that same budget rather than making each wait spend it all.
    for _ in range(4):
        assert scene.player.handle_playback_start() is True
        if getattr(scene.player, '_presentation_finished', False):
            break
    assert scene.clock[0] <= began + 3.001
    assert scene.player._presentation_finished
    assert scene.player._presentation_deadline == began + 3
    assert all(0 < budget <= min(.3, began + 3 - started) + 1e-9
               for started, operation, budget in scene.timed_calls)
    assert sum(operation == 'snapshot' for _, operation, _ in scene.timed_calls) <= 4
    before = len(scene.calls)
    scene.clock[0] = began + 3
    assert scene.player.handle_playback_start() is True
    assert len(scene.calls) == before
    assert scene.resolver._handoff_read_deadline is None
    assert not scene.native.commands and not scene.native.gui_commands


def timed_retirement(scene, *, hidden_after=1.1, gui_seconds=.008, command_seconds=.02):
    """Real ownership/property paths; deterministic costs, never device timings."""
    scene.player._media_started = True  # monitor() has already observed AV.
    scene.resolver._owns_selection = MethodType(type(scene.resolver)._owns_selection, scene.resolver)
    scene.latencies.update(snapshot=.15, begin_window_close=command_seconds,
                           close_window=command_seconds, request_fullscreen=command_seconds,
                           confirm_fullscreen=command_seconds)
    original_state = scene.native.state
    def state():
        # The prior fixture's timeout clamp excluded synchronous work after the
        # fake transport delay. Keep that work visible in the absolute budget.
        scene.clock[0] += .02
        return original_state()
    scene.native.state = state
    hidden_at, closed_at, gui_reads, sleeps = [None], [None], [], []
    original_visible, original_label = scene.gui.getCondVisibility, scene.gui.getInfoLabel
    def visible(value):
        gui_reads.append((scene.clock[0], value))
        scene.clock[0] += gui_seconds
        if hidden_at[0] is not None and scene.clock[0] >= hidden_at[0]:
            scene.visible.discard(13001)
        return original_visible(value)
    def label(value):
        scene.clock[0] += gui_seconds
        return original_label(value)
    def pause(milliseconds):
        sleeps.append(milliseconds)
        scene.clock[0] += milliseconds / 1000
    def close_windows():
        scene.closes.append('d' * 32)
        closed_at[0] = scene.clock[0]
        hidden_at[0] = scene.clock[0] + hidden_after
    scene.gui.getCondVisibility, scene.gui.getInfoLabel, scene.gui.sleep = visible, label, pause
    scene.resolver.close_windows = close_windows
    cache_writes = []
    def slow_cache(key, value, expiry):
        cache_writes.append((scene.clock[0], key, expiry.days))
        scene.clock[0] += 1.5  # Fault injection, not a measured SQLite delay.
    scene.cache.set = slow_cache
    return SimpleNamespace(hidden_at=hidden_at, closed_at=closed_at,
                           reads=gui_reads, sleeps=sleeps, cache_writes=cache_writes)


def restore_per_poll_owner_read(scene):
    """Negative control: restore only the removed owner RPC in real method AST."""
    path = ROOT / 'addons/plugin.video.bobbi/lib/gui/resolver_window.py'
    cls = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'ResolverWindow')
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == 'handle_playback_started')
    loops = [node for node in ast.walk(method)
             if isinstance(node, ast.For) and isinstance(node.iter, ast.Call)
             and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'range'
             and len(node.iter.args) == 1 and isinstance(node.iter.args[0], ast.Constant)
             and node.iter.args[0].value == 20]
    assert len(loops) == 1, 'Update the negative control if retirement structure changes'
    poll = loops[0].body[0]
    assert isinstance(poll, ast.If)
    assert ast.dump(poll.test) == ast.dump(ast.parse('self.cancel_event.is_set()', mode='eval').body)
    poll.test = ast.BoolOp(op=ast.Or(), values=[
        ast.UnaryOp(op=ast.Not(), operand=ast.Call(
            func=ast.Name(id='owned', ctx=ast.Load()), args=[], keywords=[])), poll.test])
    scope = dict(scene.resolver.handle_playback_started.__func__.__globals__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(path), 'exec'), scope)
    scene.resolver.handle_playback_started = MethodType(scope['handle_playback_started'], scene.resolver)
    scene.player.on_started = scene.resolver.handle_playback_started


@pytest.mark.parametrize('restore_old_poll', [False, True], ids=['current', 'old-poll-negative-control'])
@pytest.mark.parametrize('hidden_after', [.6, 1.1], ids=['within-budget', 'severe-over-budget'])
def test_same_cost_retirement_pair_preserves_fixed_budget(scene, hidden_after, restore_old_poll):
    # Both implementations pay exactly these injected costs. The severe 1.1s
    # case is deliberately not advertised as fixed: neither can confirm in 3s.
    timing = timed_retirement(scene, hidden_after=hidden_after, gui_seconds=.011,
                              command_seconds=.15)
    if restore_old_poll:
        restore_per_poll_owner_read(scene)
    began = scene.clock[0]
    for _ in range(4):
        assert scene.player.handle_playback_start() is True
        if getattr(scene.player, '_presentation_finished', False):
            break
        scene.clock[0] = min(scene.clock[0] + .05, scene.player._presentation_deadline)
    expected_confirmation = hidden_after == .6 and not restore_old_poll
    assert bool(getattr(scene.player, '_handoff_confirmed', False)) is expected_confirmation
    assert scene.player._presentation_finished
    assert scene.player._presentation_deadline == began + 3
    # Timeout bounds transport, not the explicitly injected synchronous tail.
    assert scene.clock[0] <= began + 3.02
    assert all(started < began + 3 and 0 < budget <= min(.3, began + 3 - started) + 1e-9
               for started, _, budget in scene.timed_calls)
    assert not timing.cache_writes and not scene.cache.calls and not scene.native.commands
    assert timing.sleeps and max(timing.sleeps) <= 25
    if expected_confirmation:
        assert scene.player._presentation_result['phase'] == 'CONFIRMED'
        assert scene.clock[0] - began == pytest.approx(2.924)
        assert len(scene.native.gui_commands) == 1 and scene.confirmed == [True]
    else:
        assert scene.player._presentation_result['phase'] == 'DEFERRED'
        assert scene.player._presentation_result['reason'] == 'BUDGET_EXHAUSTED'
        assert not scene.confirmed
        if hidden_after == 1.1:
            assert not scene.native.gui_commands
            if restore_old_poll:
                assert scene.player._presentation_result['stage'] == 'OWNER_READ'
    # Once locally terminal, later monitor ticks cannot add IPC or revive labels.
    before_calls, before_events = len(scene.calls), len(scene.property_events)
    scene.clock[0] = max(scene.clock[0], began + 3)
    for _ in range(3):
        assert scene.player.handle_playback_start() is True
    assert len(scene.calls) == before_calls and len(scene.property_events) == before_events


def test_delayed_retirement_and_real_labels_recover_within_original_three_seconds(scene):
    timing = timed_retirement(scene)
    began, attempts = scene.clock[0], []
    for _ in range(4):
        before = len(timing.sleeps)
        assert scene.player.handle_playback_start() is True
        attempts.append(len(timing.sleeps) - before)
        if getattr(scene.player, '_presentation_finished', False):
            break
        scene.clock[0] += .05
    assert scene.player._handoff_confirmed and scene.confirmed == [True]
    assert scene.player._presentation_deadline == began + 3
    assert scene.clock[0] < began + 3
    assert len(attempts) > 1 and attempts[0] == 20 and max(attempts) <= 20
    assert timing.sleeps and max(timing.sleeps) <= 25
    # Every slot is still checked once before closing; no single-slot shortcut.
    scanned = [value for when, value in timing.reads if when < timing.closed_at[0]]
    assert scanned == ['Window.IsVisible(%d)' % identifier for identifier in range(13000, 13100)]
    assert timing.cache_writes == [] and scene.cache.calls == []
    assert scene.closes == ['d' * 32] and len(scene.native.gui_commands) == 1
    assert not scene.native.commands
    phases = [json.loads(value)['phase'] for _, key, value in scene.property_events
              if key == 'bobbi_cinema_handoff']
    assert phases == ['ATTEMPTING', 'ADMITTED', 'CONFIRMED']
    phase_times = {json.loads(value)['phase']: when for when, key, value in scene.property_events
                   if key == 'bobbi_cinema_handoff'}
    request_index = next(index for index, (_, operation, _) in enumerate(scene.timed_calls)
                         if operation == 'request_fullscreen')
    owner_started, owner_operation, _ = scene.timed_calls[request_index - 1]
    request_started = scene.timed_calls[request_index][0]
    confirm_started = next(started for started, operation, _ in scene.timed_calls
                           if operation == 'confirm_fullscreen')
    assert owner_operation == 'snapshot'
    assert owner_started + .17 <= phase_times['ATTEMPTING'] <= request_started
    assert request_started + .02 <= phase_times['ADMITTED'] <= confirm_started
    assert confirm_started + .02 <= phase_times['CONFIRMED']


def test_retirement_wait_polls_gui_not_owner_on_each_iteration(scene):
    timing = timed_retirement(scene, hidden_after=.2, gui_seconds=0)
    assert scene.player.handle_playback_start() is True
    assert scene.player._handoff_confirmed and len(timing.sleeps) > 1
    operations = [row['operation'] for row in scene.calls]
    begin, close = operations.index('begin_window_close'), operations.index('close_window')
    assert operations[begin + 1:close] == []
    assert operations[begin - 1] == 'snapshot'  # The initial fresh fence remains.
    assert operations[close + 1] == 'snapshot'  # Fullscreen still rechecks owner.


def test_real_property_chain_negative_control_can_consume_presentation_budget(scene):
    timing = timed_retirement(scene, hidden_after=0, gui_seconds=0)
    scope = scene.property_api.set_property.__globals__
    scope['TRANSIENT_PLAYBACK_PROPERTIES'] -= frozenset(PRESENTATION_PROPERTIES)
    assert scene.player.handle_playback_start() is True
    assert [key for _, key, _ in timing.cache_writes] == [
        'bobbi_cinema_started', 'bobbi_cinema_handoff']
    assert all(started < scene.player._presentation_deadline and days == 30
               for started, _, days in timing.cache_writes)
    assert scene.player._presentation_result['phase'] == 'DEFERRED'
    assert scene.player._presentation_result['reason'] == 'BUDGET_EXHAUSTED'
    assert not scene.authority.owner.desired['fullscreen_requested']
    assert not scene.native.gui_commands and not scene.native.commands


def test_expired_presentation_records_local_result_without_rpc_or_newer_global_overwrite(scene):
    scene.faults['begin_window_close'] = dict(remaining=1, lost_ack=False)
    assert scene.player.handle_playback_start() is True
    newer = json.dumps(dict(request_id='f' * 32, phase='CONFIRMED', fullscreen=True))
    scene.properties['bobbi_cinema_handoff'] = newer
    scene.clock[0] = scene.player._presentation_deadline
    before = len(scene.calls)
    assert scene.player.handle_playback_start() is True
    assert len(scene.calls) == before
    assert scene.properties['bobbi_cinema_handoff'] == newer
    result = scene.player._presentation_result
    assert result['request_id'] == scene.args['request_id']
    assert result['native_instance'] == scene.player._native_instance
    assert result['phase'] == 'DEFERRED' and result['reason'] == 'BUDGET_EXHAUSTED'
    assert not scene.cache.calls and not scene.native.gui_commands


@pytest.mark.parametrize('boundary', [
    'owner_snapshot', 'request_fullscreen', 'confirmation_snapshot', 'confirm_fullscreen',
])
@pytest.mark.parametrize('change', ['deadline', 'session', 'cancel_object', 'cancelled'])
def test_late_presentation_reply_cannot_publish_over_newer_labels(scene, boundary, change):
    # Inject only after the real authority has processed the operation. This
    # models response/binding-validation tails, not a request rejected in advance.
    original_call = scene.player.playback_client.call
    snapshots, changed_at = [0], []
    newer_handoff = json.dumps(dict(request_id='e' * 32, phase='CONFIRMED'))
    newer_status = 'newer-request-status'
    newer_result = dict(request_id='e' * 32, phase='ATTEMPTING')
    def late_reply(message, **kwargs):
        result = original_call(message, **kwargs)
        operation = message['operation']
        if operation == 'snapshot':
            snapshots[0] += 1
            matched = boundary == ('owner_snapshot' if snapshots[0] == 1 else 'confirmation_snapshot')
        else:
            matched = operation == boundary
        if matched and not changed_at:
            scene.properties['bobbi_cinema_handoff'] = newer_handoff
            scene.properties['bobbi_cinema_presentation_status'] = newer_status
            if change == 'deadline':
                scene.clock[0] = scene.player._presentation_deadline + .01
            elif change == 'session':
                scene.player.playback_session_id = 'e' * 32
                scene.player._presentation_result = dict(newer_result)
            elif change == 'cancel_object':
                scene.player._cinema_cancel = Event()
            else:
                scene.player._cinema_cancel.set()
            changed_at.append((len(scene.calls), len(scene.property_events)))
        return result
    scene.player.playback_client.call = late_reply
    scene.player.handle_playback_start()
    assert len(changed_at) == 1, 'The intended response boundary must be exercised'
    assert (len(scene.calls), len(scene.property_events)) == changed_at[0]
    assert scene.properties['bobbi_cinema_handoff'] == newer_handoff
    assert scene.properties['bobbi_cinema_presentation_status'] == newer_status
    assert not getattr(scene.player, '_handoff_confirmed', False) and not scene.confirmed
    assert not scene.native.commands and not scene.cache.calls
    if change == 'deadline':
        assert scene.player._presentation_result['phase'] == 'DEFERRED'
        assert scene.player._presentation_result['reason'] == 'BUDGET_EXHAUSTED'
    elif change == 'session':
        assert scene.player._presentation_result == newer_result


def test_capture_still_rejects_duplicate_token_outside_known_window_slot(scene):
    scene.visible.add(13099)
    scene.gui.getInfoLabel = lambda value: 'd' * 32
    assert scene.player.handle_playback_start() is True
    assert scene.resolver._capture_reason == 'LOADING_WINDOW_AMBIGUOUS'
    assert not scene.closes and not scene.native.gui_commands
    assert not any(row['operation'] == 'begin_window_close' for row in scene.calls)


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


@pytest.mark.parametrize('delayed_history', [False, True])
def test_recovered_handoff_keeps_monitor_progress_and_natural_eof_lifecycle(scene, delayed_history):
    player, events = scene.player, []
    if delayed_history:
        # AM6B: the loading lease was retired, then the first owner snapshot
        # timed out. A slow history/preparation call must not eat the UI deadline.
        old_call = player.playback_client.call
        def call(message, **kw):
            if message['operation'] == 'snapshot' and getattr(player, '_presentation_loading_retired', False) and 'miss' not in events:
                events.append('miss')
                scene.clock[0] += .3
                raise OSError('transient owner read')
            return old_call(message, **kw)
        player.playback_client.call = call
    else:
        scene.faults['close_window'] = dict(remaining=1, lost_ack=True)
    player._wait_for_video_start = lambda: True
    player.skip_intro_enabled = False
    player._cinema_phase = lambda phase: events.append(phase)
    def record_history():
        events.append('started_history')
        if delayed_history:
            events.append('fullscreen_at_history' if scene.confirmed else 'video_behind_directory')
            scene.clock[0] += 3
    player._record_started_history = record_history
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
    if delayed_history:
        assert 'miss' in events and 'fullscreen_at_history' in events
    assert player._handoff_confirmed and 'authorized_next' in events and 'handle_playback_stop' in events
    assert 'kill_dialog' not in events and not scene.native.commands
