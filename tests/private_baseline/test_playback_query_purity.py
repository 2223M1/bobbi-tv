"""Real authority/query boundaries with simulated native IO, not device evidence.

Status queries may synchronize the complete native lifecycle. They may not run
window reconciliation or publish skin state. Resident ticks retain that duty.
The pre-existing presentation/resource reads remain lifecycle-free.
"""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from test_playback_authority import playing, row, window
from test_playback_presentation import scene


SYNC_QUERIES = (
    'snapshot', 'segment_status', 'next_picker_status', 'startup_failure',
    'font_preflight_guard', 'claim_status', 'transport_status',
)
PURE_READS = ('resource_snapshot', 'playback_presentation', 'playback_receipt')


def request_for(authority, native, args, operation):
    if operation in ('snapshot', 'resource_snapshot', 'playback_presentation'):
        return dict(operation=operation)
    if operation == 'playback_receipt':
        expected = authority.dispatch(dict(operation='playback_presentation'))['expected']
        return dict(operation=operation, expected=expected, command_id=uuid4().hex)
    message = dict(args, operation=operation)
    if operation in ('startup_failure', 'font_preflight_guard'):
        message['file_identity'] = 'file-a'
    elif operation == 'segment_status':
        message['native_instance'] = native.current['native_instance']
    elif operation == 'claim_status':
        message.update(claim_id=uuid4().hex, route='resolved_url')
    elif operation == 'transport_status':
        message['token'] = uuid4().hex
    return message


def window_state(authority):
    return deepcopy((authority.native_windows, authority.owner.windows, authority.owner.pause))


def resident_window_tick(authority, native):
    # Exercise the actual resident event -> refresh path, not a no-op mock or
    # another query. A portable server avoids sockets, Kodi and device IO.
    from lib.services.playback_control import PlaybackControlServer
    server = PlaybackControlServer(native=native, path=None)
    server.authority = authority
    server.events.put(('xbmc', 'Player.OnBobiWindow', '{}'))
    server.tick(budget=0)


def pending_window_change(authority, native, args, closing):
    native.gui['windows'] = [window(native, args, 'audio')]
    if closing:
        resident_window_tick(authority, native)
        assert [item['action'] for item in native.commands] == ['pause']
        native.current.update(paused=True, sequence=native.current['sequence'] + 1)
        resident_window_tick(authority, native)
        assert authority.owner.pause['confirmed']
        native.gui['windows'] = []
        native.commands.clear()


@pytest.mark.parametrize('operation', SYNC_QUERIES + PURE_READS)
@pytest.mark.parametrize('closing', [False, True], ids=['opening', 'closing'])
def test_query_does_not_pause_or_resume_but_real_resident_tick_does_once(scene, operation, closing):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    pending_window_change(authority, native, args, closing)
    before = window_state(authority)
    epoch = native.epoch

    result = authority.dispatch(request)

    assert isinstance(result, dict)
    assert native.commands == [] and native.gui_commands == []
    assert native.epoch == epoch
    assert window_state(authority) == before
    resident_window_tick(authority, native)
    assert [item['action'] for item in native.commands] == ['resume' if closing else 'pause']
    resident_window_tick(authority, native)
    assert len(native.commands) == 1


@pytest.mark.parametrize('operation', SYNC_QUERIES)
@pytest.mark.parametrize('closing', [False, True], ids=['opening', 'closing'])
def test_query_consumed_state_duplicate_does_not_hide_following_window_event(scene, operation, closing):
    from lib.services.playback_control import PlaybackControlServer
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    pending_window_change(authority, native, args, closing)
    native.current['sequence'] += 1
    before = window_state(authority)
    duplicate = ('xbmc', 'Player.OnBobiState', json.dumps(native.current))

    authority.dispatch(request)

    assert authority.last_native == native.current
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []
    server = PlaybackControlServer(native=native, path=None)
    server.authority = authority
    for _ in range(2):
        server.events.put(duplicate)
        server.events.put(('xbmc', 'Player.OnBobiWindow', '{}'))
        server.tick(budget=0)
        assert [item['action'] for item in native.commands] == ['resume' if closing else 'pause']


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_status_synchronizes_fresh_native_lifecycle_without_window_control(scene, operation):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    native.current.update(sequence=native.current['sequence'] + 1, paused=True)
    native.gui.update(gui_generation=7, windows=[window(native, args, 'subtitles')])
    before = window_state(authority)

    authority.dispatch(request)

    assert authority.last_native == native.current
    assert authority.owner.observed['paused'] is True
    assert authority.gui_state['gui_generation'] == 7
    assert authority.native_epoch == native.epoch
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_status_observes_new_epoch_and_revokes_old_owner_without_native_control(scene, operation):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    native.epoch += 1
    native.current['sequence'] += 1
    native.gui['windows'] = [window(native, args, 'audio')]

    authority.dispatch(request)

    assert authority.native_epoch == native.epoch
    assert authority.last_native == native.current
    assert authority.owner.desired['cancelled'] is True
    assert not authority.owner.owns_instance(args['boot_id'], args['epoch'], args['request_id'],
                                            native.current['native_instance'])
    assert window_state(authority) == ({}, {}, None)
    assert native.commands == [] and native.gui_commands == []
    resident_window_tick(authority, native)
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_status_observes_replacement_instance_without_taking_ownership_or_stopping_it(scene, operation):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    previous = native.current['native_instance']
    native.gui['windows'] = [window(native, args, 'audio')]
    native.current = row(identity='external-file')

    authority.dispatch(request)

    assert authority.last_native == native.current
    assert authority.owner.terminal['reason'] == 'SUPERSEDED'
    assert authority.owner.terminal['native_instance'] == previous
    assert authority.owner.observed['native_instance'] == native.current['native_instance']
    assert authority.owner.observed['request_id'] == ''
    assert window_state(authority) == ({}, {}, None)
    assert native.commands == [] and native.gui_commands == []
    resident_window_tick(authority, native)
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_status_accepts_manual_pause_intent_and_prevents_later_automatic_resume(scene, operation):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    pending_window_change(authority, native, args, closing=True)
    before_windows = deepcopy((authority.native_windows, authority.owner.windows))
    old_intent = authority.owner.user_intent
    native.current.update(sequence=native.current['sequence'] + 1,
                          user_intent=native.current['user_intent'] + 1, paused=True)

    authority.dispatch(request)

    assert authority.last_native == native.current
    assert authority.owner.observed['paused'] is True
    assert authority.owner.observed['native_user_intent'] == native.current['user_intent']
    assert authority.owner.user_intent == old_intent + 1
    assert authority.owner.pause is None
    assert (authority.native_windows, authority.owner.windows) == before_windows
    assert native.commands == [] and native.gui_commands == []
    resident_window_tick(authority, native)
    assert window_state(authority) == ({}, {}, None)
    assert native.commands == [] and native.gui_commands == []


def test_observational_refresh_keeps_full_event_processing_and_defers_window_reconciliation(scene):
    authority, native, args = scene
    native.current.update(sequence=native.current['sequence'] + 1, paused=True)
    native.gui['windows'] = [window(native, args, 'audio')]
    before = window_state(authority)

    result = authority.refresh(reconcile_windows=False)

    assert result == native.current == authority.last_native
    assert authority.history.items[result['native_instance']] == result
    assert authority.owner.observed['paused'] is True
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []


def test_segment_status_reads_current_suggestion_without_publishing_skin(scene):
    authority, native, args = scene
    published = []
    native.publish_playback_presentation = lambda *value: published.append(deepcopy(value))
    message = dict(args, native_instance=native.current['native_instance'])
    registered = authority.dispatch(dict(message, operation='segment_register',
        segments=dict(intro=dict(start_ms=0, end_ms=10000))))
    assert registered == dict(accepted=True, count=1)
    published.clear()

    result = authority.dispatch(dict(message, operation='segment_status'))

    assert result['available'] and result['segment']['kind'] == 'intro'
    assert result['auto_allowed'] is False
    assert published == []
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('invalid', ['unknown_operation', 'missing_operation', 'font_extra', 'claim_missing_id'])
@pytest.mark.parametrize('closing', [False, True], ids=['opening', 'closing'])
def test_unknown_or_invalid_query_is_rejected_without_window_control(scene, invalid, closing):
    authority, native, args = scene
    if invalid == 'unknown_operation':
        message = dict(operation='not_a_playback_operation')
    elif invalid == 'missing_operation':
        message = {}
    elif invalid == 'font_extra':
        message = dict(args, operation='font_preflight_guard', file_identity='file-a', extra=True)
    else:
        message = dict(args, operation='claim_status', route='resolved_url')
    pending_window_change(authority, native, args, closing)
    before = window_state(authority)

    with pytest.raises(ValueError):
        authority.dispatch(message)

    assert native.commands == [] and native.gui_commands == []
    assert window_state(authority) == before
    resident_window_tick(authority, native)
    assert [item['action'] for item in native.commands] == ['resume' if closing else 'pause']


def terminal_receipt(native):
    return dict(native.current, phase='TERMINAL', reason='NATURAL_EOF',
        sequence=native.current['sequence'] + 1,
        completion_observation=dict(schema=1, position_ms=99960, duration_ms=100000,
                                    age_us=10000, valid=True))


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_status_observes_complete_eof_and_preserves_one_use_child_after_native_destruction(scene, monkeypatch, operation):
    from bobbi_core import playback_authority as module
    authority, native, args = scene
    clock = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    request = request_for(authority, native, args, operation)
    end = terminal_receipt(native)
    instance = end['native_instance']
    native.current = deepcopy(end)

    authority.dispatch(request)

    terminal = deepcopy(authority.owner.terminal)
    assert terminal['reason'] == 'NATURAL_EOF' and terminal['av_started']
    assert terminal['completion_observation'] == end['completion_observation']
    assert terminal['consumed'] is False
    assert authority.last_native == end
    assert authority.terminal_seen_at == 100.0
    # The query accepted the full event, so the queued duplicate must be harmless.
    assert not authority.event('xbmc', 'Player.OnBobiState', deepcopy(end))
    assert authority.owner.terminal == terminal
    native.current = None
    clock[0] = 102.9
    authority.dispatch(request)
    assert authority.owner.terminal == terminal
    assert authority.last_native == end and authority.terminal_seen_at == 100.0
    assert native.commands == [] and native.gui_commands == []

    grant = authority.dispatch(dict(args, operation='authorize_next', native_instance=instance,
        selection_identity='same-release-next'))
    assert grant['authorized']
    assert authority.owner.terminal['consumed'] is True
    command = dict(args, operation='reserve_child', token=grant['token'],
        child_request_id=uuid4().hex, selection_identity='same-release-next')
    result = authority.dispatch(command)
    assert result['desired']['request_id'] == command['child_request_id']
    with pytest.raises(RuntimeError):
        authority.dispatch(command)


def test_repeated_status_reads_do_not_extend_original_three_second_eof_window(monkeypatch):
    from bobbi_core import playback_authority as module
    clock = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    authority, native, args = playing()
    end = terminal_receipt(native)
    native.current = deepcopy(end)
    assert authority.event('xbmc', 'Player.OnBobiState', deepcopy(end))
    for stamp in (101.0, 102.9):
        clock[0] = stamp
        authority.dispatch(dict(operation='snapshot'))
        assert authority.terminal_seen_at == 100.0
    native.current = None
    clock[0] = 103.01
    result = authority.dispatch(dict(args, operation='authorize_next',
        native_instance=end['native_instance'], selection_identity='same-release-next'))
    assert result == {'authorized': False}
    assert authority.owner.terminal['consumed'] is False


@pytest.mark.parametrize('operation', PURE_READS)
def test_existing_pure_read_does_not_consume_terminal_before_real_event(scene, operation):
    authority, native, args = scene
    request = request_for(authority, native, args, operation)
    before = deepcopy((authority.owner.snapshot(), authority.history.items,
                       authority.last_native, authority.terminal_seen_at))
    end = terminal_receipt(native)
    native.current = deepcopy(end)

    authority.dispatch(request)

    assert (authority.owner.snapshot(), authority.history.items,
            authority.last_native, authority.terminal_seen_at) == before
    assert authority.event('xbmc', 'Player.OnBobiState', deepcopy(end))
    assert authority.owner.terminal['reason'] == 'NATURAL_EOF'
    assert authority.owner.terminal['completion_observation'] == end['completion_observation']
    assert authority.owner.terminal['consumed'] is False
    assert native.commands == [] and native.gui_commands == []


@pytest.fixture
def captured_transport(tmp_path):
    from test_transport_handoff_authority import command, setup
    authority, native, args, _, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    assert grant['authorized']
    native.captured()
    status = command(args, account, grant, 'transport_status')
    assert authority.dispatch(status)['state'] == 'CAPTURED'
    native.commands.clear()
    return authority, native, args, status


@pytest.mark.parametrize('role', ['audio', 'subtitles'])
def test_live_transport_status_rejects_new_window_without_creating_pause_lease(captured_transport, role):
    authority, native, args, status = captured_transport
    native.gui['windows'] = [window(native, args, role)]
    before = window_state(authority)

    result = authority.dispatch(status)

    # No hidden pause lease is needed to notice the current GUI conflict. A
    # seemingly usable capture must not survive the change in user interaction.
    assert result['state'] == 'REJECTED'
    assert native.commands == [] and native.gui_commands == []
    assert window_state(authority) == before
    assert authority.continuation is None
    resident_window_tick(authority, native)
    assert [item['action'] for item in native.commands] == ['pause']
    resident_window_tick(authority, native)
    assert len(native.commands) == 1


@pytest.mark.parametrize('foreign', ['request_id', 'native_instance', 'both', 'eight_unrelated'])
def test_live_transport_status_ignores_other_request_or_instance_windows(captured_transport, foreign):
    authority, native, args, status = captured_transport
    other = window(native, args, 'audio')
    if foreign in ('request_id', 'both', 'eight_unrelated'):
        other['request_id'] = uuid4().hex
    if foreign in ('native_instance', 'both', 'eight_unrelated'):
        other['native_instance'] = str(uuid4())
    native.gui['windows'] = ([dict(other, token=uuid4().hex) for _ in range(8)]
                             if foreign == 'eight_unrelated' else [other])
    before = window_state(authority)
    grant = deepcopy(authority.continuation)

    result = authority.dispatch(status)

    assert result['state'] == 'CAPTURED'
    assert authority.continuation == grant
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []
    resident_window_tick(authority, native)
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('invalid', [
    'not_a_list', 'null', 'tuple', 'not_an_object', 'role', 'token_text',
    'token_type', 'token_missing', 'too_many',
])
def test_live_transport_status_rejects_malformed_windows_without_native_control(captured_transport, invalid):
    authority, native, args, status = captured_transport
    value = window(native, args, 'audio')
    windows = [value]
    if invalid == 'not_a_list':
        windows = {}
    elif invalid == 'null':
        windows = None
    elif invalid == 'tuple':
        windows = (value,)
    elif invalid == 'not_an_object':
        windows = [None]
    elif invalid == 'role':
        value['role'] = 'source'
    elif invalid == 'token_text':
        value['token'] = 'not-a-window-token'
    elif invalid == 'token_type':
        value['token'] = 123
    elif invalid == 'token_missing':
        value.pop('token')
    else:
        windows = [dict(value, token=uuid4().hex) for _ in range(9)]
    native.gui['windows'] = windows
    before = window_state(authority)
    grant = deepcopy(authority.continuation)

    with pytest.raises(ValueError):
        authority.dispatch(status)

    assert authority.continuation == grant
    assert window_state(authority) == before
    assert native.commands == [] and native.gui_commands == []
