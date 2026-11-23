"""Scoped user transport through the production authority; synthetic native only."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_playback_presentation import scene, submit, view
from test_playback_authority import select, row
from bobbi_core import playback_presentation as contract


@pytest.fixture
def transport(scene):
    owner, native, args = scene
    read = native.subtitles
    native.subtitles = lambda: dict(read(), transport_protocol=1, can_pause=True,
        can_resume=True, can_stop=True, transport_state='playing', can_seek=False)
    return scene


def stop_result(command, status='applied', **changes):
    result = dict(contract.native_command(command), status=status)
    if status in ('applied', 'failed'):
        scope = command['expected']
        result.update(terminal_reason='STOP' if status == 'applied' else 'ERROR',
            terminal_sequence=scope['expected_sequence'] + 1,
            terminal_open_epoch=scope['selection_epoch'], terminal_user_intent=scope['user_intent'] + 1)
    result.update(changes)
    return result


def retain(native, rows, **changes):
    read = native.state
    native.state = lambda: dict(read(), control_protocol=1, terminal_commands=deepcopy(rows), **changes)


def lookup(owner, command, **fields):
    return owner.dispatch(dict(operation='playback_receipt', expected=command['expected'],
        command_id=command['command_id'], **fields))


@pytest.mark.parametrize('action', ['user_pause', 'user_resume', 'user_stop'])
def test_explicit_user_transport_does_not_depend_on_seek(transport, action):
    projected = view(transport)
    assert projected['transport_protocol'] == 1 and not projected['can_seek']
    reply, command = submit(transport, action, {})
    assert reply['status'] == 'queued'
    wire = transport[1].commands[-1]
    assert wire == dict(contract.native_command(command))
    assert command['params'] == {} and wire['action'] == action


@pytest.mark.parametrize('protocol', [None, True, '1', 0, 2])
@pytest.mark.parametrize('action', ['user_pause', 'user_resume', 'user_stop'])
def test_old_or_invalid_transport_capability_leaves_old_controls_available(transport, protocol, action):
    native = transport[1]
    read = native.subtitles
    native.subtitles = lambda: dict(read(), transport_protocol=protocol, can_seek=True)
    projected = view(transport)
    assert projected['available'] and projected['can_seek']
    assert projected['can_pause'] is projected['can_resume'] is projected['can_stop'] is False
    assert submit(transport, action, {})[0]['status'] == 'rejected'
    assert native.commands == []
    assert submit(transport, 'subtitle_visible', {'visible': False})[0]['status'] == 'queued'


@pytest.mark.parametrize('field,value', [('can_pause', 1), ('can_resume', 'true'),
    ('can_stop', None), ('transport_state', 'fast'), ('transport_state', None)])
def test_incomplete_transport_projection_does_not_grant_any_user_action(transport, field, value):
    native = transport[1]
    read = native.subtitles
    native.subtitles = lambda: dict(read(), **{field: value})
    projected = view(transport)
    assert projected['available']
    assert not any(projected[key] for key in ('can_pause', 'can_resume', 'can_stop'))
    assert submit(transport, 'user_stop', {})[0]['status'] == 'rejected'
    assert native.commands == []


@pytest.mark.parametrize('action,capability', [('user_pause', 'can_pause'),
    ('user_resume', 'can_resume'), ('user_stop', 'can_stop')])
def test_each_action_needs_its_own_capability_and_empty_parameters(transport, action, capability):
    native = transport[1]
    read = native.subtitles
    native.subtitles = lambda: dict(read(), **{capability: False})
    assert submit(transport, action, {})[0]['status'] == 'rejected'
    with pytest.raises(ValueError):
        submit(transport, action, {'toggle': True})
    assert native.commands == []


def test_stop_lost_reply_recovers_retained_original_result_after_select_without_lifecycle_writes(transport):
    owner, native, _ = transport
    control = native.control
    def lost(command):
        control(command)
        raise OSError('lost ACK')
    native.control = lost
    reply, command = submit(transport, 'user_stop', {})
    assert reply['status'] == 'unknown'
    select(owner, 'release-b')
    native.current = None
    retain(native, [stop_result(command)])
    native.commands.clear()
    native.gui_commands.clear()
    before = deepcopy(owner.owner.snapshot())
    assert lookup(owner, command) == dict(command_id=command['command_id'], status='applied')
    assert owner.owner.snapshot() == before
    assert native.commands == native.gui_commands == []
    assert owner.dispatch(dict(operation='playback_command', command=command))['status'] == 'applied'
    assert native.commands == []


@pytest.mark.parametrize('case', ['missing', 'expired', 'wrong_top_protocol', 'oversized', 'current_stop_only'])
def test_missing_retained_stop_never_infers_applied_or_replays(transport, case):
    owner, native, _ = transport
    control = native.control
    native.control = lambda command: (control(command), (_ for _ in ()).throw(OSError('lost')))[1]
    _, command = submit(transport, 'user_stop', {})
    rows = [] if case in ('missing', 'expired', 'current_stop_only') else [stop_result(command)]
    if case == 'oversized': rows *= 65
    retain(native, rows)
    if case == 'wrong_top_protocol':
        read = native.state
        native.state = lambda: dict(read(), control_protocol=True)
    if case == 'current_stop_only':
        native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    else:
        native.current = None
    assert lookup(owner, command)['status'] == 'unknown'
    assert owner.dispatch(dict(operation='playback_command', command=command))['status'] == 'unknown'
    assert len(native.commands) == 1


@pytest.mark.parametrize('field,value', [('request_id', 'd'*32), ('native_instance', str(uuid4())),
    ('file_sha256', 'd'*64), ('expected_sequence', 3), ('selection_epoch', 99), ('user_intent', 1),
    ('subtitle_intent', 1), ('audio_intent', 1), ('audio_intent', False), ('control_protocol', True),
    ('terminal_reason', 'ERROR'), ('terminal_sequence', 1), ('terminal_sequence', True),
    ('terminal_open_epoch', 99), ('terminal_user_intent', 0)])
def test_stop_applied_requires_all_original_fields_and_causal_terminal_proof(transport, field, value):
    _, command = submit(transport, 'user_stop', {})
    assert contract.result(stop_result(command, **{field: value}), command) is None


@pytest.mark.parametrize('status', ['applied', 'failed', 'unknown'])
def test_stop_terminal_contract_keeps_real_failure_or_unknown(transport, status):
    owner, native, _ = transport
    _, command = submit(transport, 'user_stop', {})
    retain(native, [stop_result(command, status)])
    native.current = None
    assert lookup(owner, command)['status'] == status


@pytest.mark.parametrize('action', ['user_pause', 'user_resume'])
def test_pause_resume_results_are_exact_and_do_not_borrow_stop_retention(transport, action):
    owner, native, _ = transport
    _, command = submit(transport, action, {})
    wire = contract.native_command(command)
    assert contract.result(dict(wire, status='applied', expected_sequence=True), command) is None
    assert owner.event('xbmc', 'Player.OnBobiControl', dict(wire, status='applied'))
    assert lookup(owner, command)['status'] == 'applied'


def test_duplicate_and_full_ledger_do_not_reconcile_windows_or_repeat_native_controls(transport):
    owner, native, args = transport
    _, command = submit(transport, 'user_pause', {})
    read = native.state
    native.state = lambda: dict(read(), windows=[dict(token='a'*32, role='audio',
        request_id=args['request_id'], native_instance=native.current['native_instance'])])
    before = deepcopy(owner.owner.snapshot())
    assert owner.dispatch(dict(operation='playback_command', command=command))['status'] == 'queued'
    assert len(native.commands) == 1 and owner.owner.snapshot() == before
    for _ in range(255):
        copied = deepcopy(command)
        copied['command_id'] = uuid4().hex
        owner.playback_commands[copied['command_id']] = dict(command=copied, status='unknown', account_scope=None)
    full = deepcopy(command)
    full['command_id'] = uuid4().hex
    assert owner.dispatch(dict(operation='playback_command', command=full))['status'] == 'rejected'
    assert len(native.commands) == 1 and len(owner.playback_commands) == 256
    assert owner.owner.snapshot() == before


def test_retained_commands_do_not_cross_account_or_boot_boundaries(transport):
    owner, native, _ = transport
    original_scope, other_scope = {'provider': 'one'}, {'provider': 'two'}
    active = [original_scope]
    def current(scope, action):
        if scope != active[0]: raise RuntimeError('ACCOUNT_CHANGED')
        return action()
    owner.selection_account = original_scope
    owner.configure_accounts(SimpleNamespace(run_if_current=current))
    _, command = submit(transport, 'user_stop', {})
    retain(native, [stop_result(command)])
    active[0] = other_scope
    owner.selection_account = other_scope
    denied = lookup(owner, command, account_scope=other_scope)
    assert denied['status'] == 'rejected'
    with pytest.raises(RuntimeError, match='ACCOUNT_CHANGED'):
        lookup(owner, command, account_scope=original_scope)
    assert owner.playback_commands[command['command_id']]['status'] == 'queued'
    active[0] = original_scope
    owner.owner.boot_id = uuid4().hex
    assert lookup(owner, command, account_scope=original_scope)['status'] == 'unknown'
    assert len(native.commands) == 1


@pytest.mark.parametrize('channel', ['terminal', 'active', 'both'])
def test_reading_original_account_a_receipt_never_settles_account_b_ledger(transport, channel):
    owner, native, _ = transport
    account_a, account_b = {'provider': 'one'}, {'provider': 'two'}
    def current(scope, action):
        assert scope in (account_a, account_b)  # Both independent providers remain authenticated.
        return action()
    owner.selection_account = account_a
    owner.configure_accounts(SimpleNamespace(run_if_current=current))
    _, command_a = submit(transport, 'user_stop', {})
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2, user_intent=1)
    assert owner.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    assert owner.playback_commands[command_a['command_id']]['status'] == 'queued'
    native.current = None
    args_b = select(owner, 'release-b')
    owner.selection_account = account_b
    assert owner.dispatch(dict(args_b, operation='bind_file', selection_identity='release-b',
        file_identity='file-b', url_sha256='b' * 64))['bound']
    assert owner.dispatch(dict(args_b, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
    native.current = row(args_b['request_id'], 'file-b', url_sha256='b' * 64,
        audio_intent=0, open_epoch=native.epoch, control_protocol=1)
    owner.refresh()
    _, command_b = submit(transport, 'user_stop', {})
    result_a, result_b = stop_result(command_a), stop_result(command_b)
    retain(native, [result_a] + ([result_b] if channel in ('terminal', 'both') else []))
    read = native.subtitles
    catalog_reads = []
    def subtitles():
        catalog_reads.append(native.current['native_instance'])
        return dict(read(), commands=[result_b] if channel in ('active', 'both') else [])
    native.subtitles = subtitles
    before = deepcopy(owner.owner.snapshot())
    native.commands.clear()
    native.gui_commands.clear()
    assert owner.dispatch(dict(operation='playback_presentation', account_scope=account_b))['available']
    assert all(entry['status'] == 'queued' for entry in owner.playback_commands.values())
    catalog_reads.clear()
    assert lookup(owner, command_a, account_scope=account_a)['status'] == 'applied'
    assert catalog_reads == []
    assert owner.playback_commands[command_b['command_id']]['status'] == 'queued'
    assert owner.owner.snapshot() == before and native.commands == native.gui_commands == []
    assert lookup(owner, command_b, account_scope=account_b)['status'] == 'applied'
    assert owner.owner.snapshot() == before and native.commands == native.gui_commands == []


@pytest.mark.parametrize('reason', [[], {}, None])
@pytest.mark.parametrize('status', ['applied', 'failed'])
def test_malformed_terminal_reason_is_rejected_without_event_exception_or_ledger_change(transport, reason, status):
    owner, native, _ = transport
    _, command = submit(transport, 'user_stop', {})
    bad = stop_result(command, status, terminal_reason=reason)
    if reason is None:
        bad.pop('terminal_reason')
    assert contract.result(bad, command) is None
    assert owner.event('xbmc', 'Player.OnBobiControl', bad) is False
    retain(native, [bad])
    native.current = None
    assert lookup(owner, command)['status'] == 'queued'
    assert len(native.commands) == 1


@pytest.mark.parametrize('action', sorted(contract.TRANSPORT_ACTIONS))
@pytest.mark.parametrize('field', sorted(contract.NATIVE_EXPECTED))
def test_user_transport_result_requires_every_original_native_expected_field(transport, action, field):
    owner, _, _ = transport
    _, command = submit(transport, action, {})
    value = stop_result(command) if action == 'user_stop' else dict(contract.native_command(command), status='applied')
    value.pop(field)
    assert contract.result(value, command) is None
    assert not owner.event('xbmc', 'Player.OnBobiControl', value)
    assert owner.playback_commands[command['command_id']]['status'] == 'queued'


@pytest.mark.parametrize('action', sorted(contract.TRANSPORT_ACTIONS))
@pytest.mark.parametrize('field', ['selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent'])
def test_user_transport_result_rejects_boolean_alias_for_every_native_counter(transport, action, field):
    _, command = submit(transport, action, {})
    value = stop_result(command) if action == 'user_stop' else dict(contract.native_command(command), status='applied')
    value[field] = bool(command['expected'][field])
    assert contract.result(value, command) is None


@pytest.mark.parametrize('field', sorted(contract.EXPECTED))
def test_new_transport_command_requires_every_original_expected_field(transport, field):
    scope = view(transport)['expected']
    scope.pop(field)
    with pytest.raises(ValueError, match='PLAYBACK_EXPECTED_INVALID'):
        submit(transport, 'user_stop', {}, expected=scope)
    assert transport[1].commands == []


@pytest.mark.parametrize('field', ['epoch', 'selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent'])
def test_new_transport_command_rejects_boolean_alias_for_every_expected_counter(transport, field):
    scope = view(transport)['expected']
    scope[field] = bool(scope[field])
    with pytest.raises(ValueError, match='PLAYBACK_EXPECTED_INVALID'):
        submit(transport, 'user_stop', {}, expected=scope)
    assert transport[1].commands == []


@pytest.mark.parametrize('action', ['user_pause', 'user_resume'])
def test_pause_resume_lost_ack_across_selection_never_replays_or_borrows_terminal_stop(transport, action):
    owner, native, _ = transport
    control = native.control
    def lost(command):
        control(command)
        raise OSError('lost original transport ACK')
    native.control = lost
    response, command = submit(transport, action, {})
    assert response['status'] == 'unknown'
    original_wire = deepcopy(native.commands[0])
    select(owner, 'release-b')
    native.current = None
    stop_command = dict(command, action='user_stop')
    retain(native, [dict(original_wire, status='applied'), stop_result(stop_command)])
    native.commands.clear()
    native.gui_commands.clear()
    before = deepcopy(owner.owner.snapshot())
    assert lookup(owner, command)['status'] == 'unknown'
    assert owner.dispatch(dict(operation='playback_command', command=deepcopy(command)))['status'] == 'unknown'
    assert owner.dispatch(dict(operation='playback_command', command=stop_command))['status'] == 'rejected'
    assert owner.owner.snapshot() == before and native.commands == native.gui_commands == []
    # Only the exact original late receipt, not a fabricated STOP correlation, can settle it.
    assert owner.event('xbmc', 'Player.OnBobiControl', dict(original_wire, status='applied'))
    assert lookup(owner, command)['status'] == 'applied'
    assert owner.owner.snapshot() == before and native.commands == native.gui_commands == []


def settle_transport(transport, command, status='applied', advance=False, via_receipt=False):
    """Drive real authority result handling; never manufacture a final ledger entry."""
    owner, native, _ = transport
    result = dict(contract.native_command(command), status=status)
    if advance:
        native.current.update(sequence=native.current['sequence'] + 1,
            user_intent=native.current['user_intent'] + 1, paused=command['action'] == 'user_pause')
    if via_receipt:
        read = native.subtitles
        native.subtitles = lambda: dict(read(), commands=[result])
        try:
            assert lookup(owner, command)['status'] == status
        finally:
            native.subtitles = read
    else:
        assert owner.event('xbmc', 'Player.OnBobiControl', result)
        assert lookup(owner, command)['status'] == status


def fill_final_transport_ledger(transport, count=256, status='rejected', advance=False):
    commands = []
    for index in range(count):
        reply, command = submit(transport, 'user_pause' if index % 2 == 0 else 'user_resume', {})
        assert reply['status'] == 'queued'
        settle_transport(transport, command, status, advance, via_receipt=bool(index % 2))
        commands.append(command)
    return commands


def watch_refresh(owner):
    calls, refresh = [], owner.refresh
    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        return refresh(*args, **kwargs)
    owner.refresh = tracked
    return calls


def test_capacity_accepts_258_applied_controls_and_retires_only_oldest_unusable_final(transport):
    owner, native, _ = transport
    commands = fill_final_transport_ledger(transport, status='applied', advance=True)
    assert list(owner.playback_commands) == [command['command_id'] for command in commands]
    for index in range(2):
        reply, command = submit(transport, 'user_pause' if index % 2 == 0 else 'user_resume', {})
        assert reply['status'] == 'queued'
        settle_transport(transport, command, advance=True, via_receipt=bool(index))
        commands.append(command)
    assert len(native.commands) == 258 and len(owner.playback_commands) == 256
    assert list(owner.playback_commands) == [command['command_id'] for command in commands[2:]]
    original = commands[0]
    before, sent = deepcopy(owner.owner.snapshot()), len(native.commands)
    ledger = deepcopy(owner.playback_commands)
    refreshes = watch_refresh(owner)
    assert lookup(owner, original)['status'] == 'unknown'
    assert owner.dispatch(dict(operation='playback_command', command=original))['status'] == 'rejected'
    old_scope_new_id = dict(original, command_id=uuid4().hex)
    assert owner.dispatch(dict(operation='playback_command', command=old_scope_new_id))['status'] == 'rejected'
    assert refreshes == [] and owner.owner.snapshot() == before
    assert owner.playback_commands == ledger
    assert len(native.commands) == sent and native.gui_commands == []
    # A retired ID is not authority. A completely fresh expected scope is a new authorization.
    reply, replacement = submit(transport, 'user_pause', {}, command_id=original['command_id'])
    assert reply['status'] == 'queued' and replacement['expected'] != original['expected']
    assert lookup(owner, original)['status'] == 'unknown'
    assert not owner.event('xbmc', 'Player.OnBobiControl',
        dict(contract.native_command(original), status='applied'))
    assert lookup(owner, replacement)['status'] == 'queued'
    settle_transport(transport, replacement, advance=True)
    assert lookup(owner, original)['status'] == 'unknown'
    assert lookup(owner, replacement)['status'] == 'applied'
    assert len(native.commands) == sent + 1 and len(owner.playback_commands) == 256


@pytest.mark.parametrize('status', ['queued', 'unknown'])
def test_capacity_never_retires_any_of_256_pending_or_unknown_controls(transport, status):
    owner, native, _ = transport
    if status == 'unknown':
        control = native.control
        def lost(command):
            control(command)
            raise OSError('lost ACK at capacity')
        native.control = lost
    commands = []
    for _ in range(256):
        reply, command = submit(transport, 'user_pause', {})
        assert reply['status'] == status
        commands.append(command)
    before = deepcopy(owner.playback_commands)
    snapshot = deepcopy(owner.owner.snapshot())
    refreshes = watch_refresh(owner)
    assert submit(transport, 'user_resume', {})[0]['status'] == 'rejected'
    assert owner.playback_commands == before and len(native.commands) == 256
    assert lookup(owner, commands[0])['status'] == status
    assert refreshes == [] and owner.owner.snapshot() == snapshot and native.gui_commands == []


@pytest.mark.parametrize('status', ['applied', 'rejected', 'failed'])
def test_capacity_does_not_retire_final_results_whose_original_scope_still_matches(transport, status):
    owner, native, _ = transport
    commands = fill_final_transport_ledger(transport, status=status)
    scope = view(transport)['expected']
    assert all(command['expected'] == scope for command in commands)
    before = deepcopy(owner.playback_commands)
    snapshot = deepcopy(owner.owner.snapshot())
    refreshes = watch_refresh(owner)
    assert submit(transport, 'user_pause', {})[0]['status'] == 'rejected'
    assert owner.playback_commands == before and len(native.commands) == 256
    assert refreshes == [] and owner.owner.snapshot() == snapshot and native.gui_commands == []


def test_capacity_skips_oldest_queued_and_unknown_and_retires_first_eligible_final(transport):
    owner, native, _ = transport
    queued_reply, queued = submit(transport, 'user_pause', {})
    assert queued_reply['status'] == 'queued'
    control = native.control
    def lost(command):
        control(command)
        raise OSError('lost ACK before finals')
    native.control = lost
    unknown_reply, unknown = submit(transport, 'user_resume', {})
    assert unknown_reply['status'] == 'unknown'
    native.control = control
    finals = fill_final_transport_ledger(transport, count=254, status='applied', advance=True)
    assert submit(transport, 'user_pause', {})[0]['status'] == 'queued'
    assert len(owner.playback_commands) == 256 and len(native.commands) == 257
    assert owner.playback_commands[queued['command_id']]['status'] == 'queued'
    assert owner.playback_commands[unknown['command_id']]['status'] == 'unknown'
    assert finals[0]['command_id'] not in owner.playback_commands
    assert all(command['command_id'] in owner.playback_commands for command in finals[1:])


def test_capacity_retires_old_selection_final_but_never_replays_its_original_scope(transport):
    owner, native, _ = transport
    commands = fill_final_transport_ledger(transport)
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2, user_intent=1)
    assert owner.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    native.current = None
    args_b = select(owner, 'release-b')
    assert owner.dispatch(dict(args_b, operation='bind_file', selection_identity='release-b',
        file_identity='file-b', url_sha256='b' * 64))['bound']
    assert owner.dispatch(dict(args_b, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
    native.current = row(args_b['request_id'], 'file-b', url_sha256='b' * 64,
        audio_intent=0, open_epoch=native.epoch, control_protocol=1)
    owner.refresh()
    assert submit(transport, 'user_pause', {})[0]['status'] == 'queued'
    assert len(owner.playback_commands) == 256
    assert commands[0]['command_id'] not in owner.playback_commands
    assert all(command['command_id'] in owner.playback_commands for command in commands[1:])
    before, sent = deepcopy(owner.owner.snapshot()), len(native.commands)
    ledger = deepcopy(owner.playback_commands)
    refreshes = watch_refresh(owner)
    assert lookup(owner, commands[0])['status'] == 'unknown'
    assert owner.dispatch(dict(operation='playback_command', command=commands[0]))['status'] == 'rejected'
    assert refreshes == [] and owner.owner.snapshot() == before
    assert owner.playback_commands == ledger
    assert len(native.commands) == sent and native.gui_commands == []


@pytest.mark.parametrize('advanced', ['sequence', 'user_intent', 'subtitle_intent', 'audio_intent'])
@pytest.mark.parametrize('regressed', [False, True])
def test_capacity_same_instance_requires_all_counters_monotone_and_one_advanced(transport, advanced, regressed):
    owner, native, _ = transport
    counters = ['sequence', 'user_intent', 'subtitle_intent', 'audio_intent']
    native.current.update({key: 10 for key in counters})
    owner.refresh()
    commands = fill_final_transport_ledger(transport)
    native.current[advanced] += 1
    if regressed:
        native.current[counters[(counters.index(advanced) + 1) % len(counters)]] -= 1
    before = deepcopy(owner.playback_commands)
    refreshes = watch_refresh(owner)
    reply, new = submit(transport, 'user_pause', {})
    assert reply['status'] == ('rejected' if regressed else 'queued')
    assert len(owner.playback_commands) == 256
    if regressed:
        assert owner.playback_commands == before and len(native.commands) == 256
        assert refreshes == []
    else:
        assert commands[0]['command_id'] not in owner.playback_commands
        assert new['command_id'] in owner.playback_commands and len(native.commands) == 257


@pytest.mark.parametrize('action,params', [
    ('user_pause', {}), ('user_resume', {}), ('user_stop', {}),
    ('seek', {'position_ms': 10000}), ('subtitle_visible', {'visible': False}),
    ('audio_stream', {'index': 0, 'stream_key': 'b' * 64}),
    ('manual_subtitle_stream', {'index': 0, 'stream_key': 'c' * 64})])
def test_new_id_with_old_scope_is_rejected_before_refresh_or_window_pause(transport, action, params):
    owner, native, args = transport
    original = view(transport)['expected']
    native.current.update(sequence=2, user_intent=1)
    read = native.state
    native.state = lambda: dict(read(), windows=[dict(token='a' * 32, role='audio',
        request_id=args['request_id'], native_instance=native.current['native_instance'])])
    before = deepcopy(owner.owner.snapshot())
    refreshes = watch_refresh(owner)
    assert submit(transport, action, params, expected=original)[0]['status'] == 'rejected'
    assert refreshes == []
    assert owner.owner.snapshot() == before and owner.playback_commands == {}
    assert native.commands == native.gui_commands == []


LEGACY_CONTROLS = [
    ('seek', {'position_ms': 10000}), ('subtitle_visible', {'visible': False}),
    ('audio_stream', {'index': 0, 'stream_key': 'b' * 64}),
    ('manual_subtitle_stream', {'index': 0, 'stream_key': 'c' * 64})]


def legacy_capabilities(transport, strict):
    native = transport[1]
    read = native.subtitles
    def subtitles():
        result = dict(read(), can_seek=True)
        if not strict:
            result.pop('transport_protocol', None)
        return result
    native.subtitles = subtitles


def minimal_legacy_result(command, status='applied'):
    scope = command['expected']
    return dict(control_protocol=1, status=status, command_id=command['command_id'],
        action=command['action'], request_id=scope['request_id'],
        native_instance=scope['native_instance'], file_sha256=scope['file_sha256'])


@pytest.mark.parametrize('action,params', LEGACY_CONTROLS)
@pytest.mark.parametrize('field', sorted(contract.NATIVE_EXPECTED))
def test_new_native_legacy_results_require_every_original_expected_field(transport, action, params, field):
    owner, native, _ = transport
    legacy_capabilities(transport, strict=True)
    reply, command = submit(transport, action, params)
    assert reply['status'] == 'queued'
    incomplete = dict(contract.native_command(command), status='applied')
    incomplete.pop(field)
    assert not owner.event('xbmc', 'Player.OnBobiControl', incomplete)
    assert lookup(owner, command)['status'] == 'queued'
    assert len(native.commands) == 1


@pytest.mark.parametrize('action,params', LEGACY_CONTROLS)
@pytest.mark.parametrize('field', ['selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent'])
def test_new_native_legacy_results_reject_boolean_counter_aliases(transport, action, params, field):
    owner, native, _ = transport
    legacy_capabilities(transport, strict=True)
    reply, command = submit(transport, action, params)
    assert reply['status'] == 'queued'
    malformed = dict(contract.native_command(command), status='applied')
    malformed[field] = bool(command['expected'][field])
    assert not owner.event('xbmc', 'Player.OnBobiControl', malformed)
    assert lookup(owner, command)['status'] == 'queued'
    assert len(native.commands) == 1


@pytest.mark.parametrize('action,params', LEGACY_CONTROLS)
def test_new_native_legacy_retired_id_reuse_never_accepts_the_old_scoped_result(transport, action, params):
    owner, native, _ = transport
    legacy_capabilities(transport, strict=True)
    original = None
    for index in range(257):
        reply, command = submit(transport, action, params)
        assert reply['status'] == 'queued'
        if original is None:
            original = command
        settle_transport(transport, command, advance=True, via_receipt=bool(index % 2))
    assert original['command_id'] not in owner.playback_commands
    reply, replacement = submit(transport, action, params, command_id=original['command_id'])
    assert reply['status'] == 'queued'
    assert original['expected'] != replacement['expected']
    assert not owner.event('xbmc', 'Player.OnBobiControl',
        dict(contract.native_command(original), status='applied'))
    read = native.subtitles
    native.subtitles = lambda: dict(read(), commands=[dict(contract.native_command(original), status='applied')])
    assert lookup(owner, original)['status'] == 'unknown'
    assert lookup(owner, replacement)['status'] == 'queued'
    native.subtitles = read
    settle_transport(transport, replacement, advance=True)
    assert lookup(owner, replacement)['status'] == 'applied'
    assert lookup(owner, original)['status'] == 'unknown'
    assert len(native.commands) == 258 and len(owner.playback_commands) == 256


@pytest.mark.parametrize('action,params', LEGACY_CONTROLS)
def test_old_native_minimal_results_allow_only_cross_selection_retirement(transport, action, params):
    owner, native, _ = transport
    legacy_capabilities(transport, strict=False)
    original = None
    for _ in range(256):
        reply, command = submit(transport, action, params)
        assert reply['status'] == 'queued'
        if original is None:
            original = command
        assert owner.event('xbmc', 'Player.OnBobiControl', minimal_legacy_result(command))
        assert lookup(owner, command)['status'] == 'applied'
        native.current.update(sequence=native.current['sequence'] + 1,
            user_intent=native.current['user_intent'] + 1)
    ledger, snapshot = deepcopy(owner.playback_commands), deepcopy(owner.owner.snapshot())
    refreshes = watch_refresh(owner)
    assert submit(transport, action, params)[0]['status'] == 'rejected'
    assert owner.playback_commands == ledger and len(native.commands) == 256
    assert refreshes == [] and owner.owner.snapshot() == snapshot and native.gui_commands == []
    # An old binary cannot distinguish late same-instance results after retirement.
    # A new selection changes the request/native identity even in minimal receipts.
    native.current.update(phase='TERMINAL', reason='STOP', sequence=native.current['sequence'] + 1)
    assert owner.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    native.current = None
    args_b = select(owner, 'release-b')
    assert owner.dispatch(dict(args_b, operation='bind_file', selection_identity='release-b',
        file_identity='file-b', url_sha256='b' * 64))['bound']
    assert owner.dispatch(dict(args_b, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
    native.current = row(args_b['request_id'], 'file-b', url_sha256='b' * 64,
        audio_intent=0, open_epoch=native.epoch, control_protocol=1)
    owner.refresh()
    assert submit(transport, action, params)[0]['status'] == 'queued'
    assert original['command_id'] not in owner.playback_commands
    reply, replacement = submit(transport, action, params, command_id=original['command_id'])
    assert reply['status'] == 'queued'
    assert not owner.event('xbmc', 'Player.OnBobiControl', minimal_legacy_result(original))
    assert lookup(owner, original)['status'] == 'unknown'
    assert lookup(owner, replacement)['status'] == 'queued'
    assert owner.event('xbmc', 'Player.OnBobiControl', minimal_legacy_result(replacement))
    assert lookup(owner, replacement)['status'] == 'applied'
    assert len(owner.playback_commands) == 256 and len(native.commands) == 258


def test_weak_legacy_retirement_needs_new_native_identity_not_owner_epoch_alone(transport):
    owner, _, _ = transport
    original = view(transport)['expected']
    next_epoch_same_native = dict(original, epoch=original['epoch'] + 1)
    assert not owner._playback_scope_retired(original, next_epoch_same_native, strict_result=False)
    assert owner._playback_scope_retired(original, next_epoch_same_native, strict_result=True)
    next_epoch_new_native = dict(next_epoch_same_native, native_instance=str(uuid4()))
    assert owner._playback_scope_retired(original, next_epoch_new_native, strict_result=False)
