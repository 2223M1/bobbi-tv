"""Same-event live intent only revokes rights; it is never a new native event.

These tests use real authority and resident tick code with simulated native IO.
They do not claim hardware execution or relax immutable ReceiptHistory ordering.
"""
from copy import deepcopy
from uuid import uuid4

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from test_playback_authority import Native, playing, row, select, window
from test_playback_query_purity import SYNC_QUERIES, request_for, resident_window_tick


@pytest.fixture
def paused_scene():
    authority, native, args = playing()
    native.current.update(sequence=2, user_intent=4, open_epoch=native.epoch, audio_intent=2,
                          subtitle_intent=2)
    native.gui['windows'] = [window(native, args, 'audio')]
    authority.refresh()
    assert [value['action'] for value in native.commands] == ['pause']
    native.current.update(sequence=3, paused=True)
    authority.refresh()
    assert authority.owner.pause['confirmed']
    native.commands.clear()
    return authority, native, args


def immutable_evidence(authority):
    return deepcopy((authority.history.items, authority.last_native,
                     authority.terminal_seen_at, authority.owner.terminal))


def complete_state(authority):
    return deepcopy((authority.owner.snapshot(), authority.owner.user_intent,
                     authority.owner.pause, authority.owner.windows, authority.native_windows,
                     authority.continuation, immutable_evidence(authority)))


@pytest.mark.parametrize('operation', SYNC_QUERIES)
def test_same_sequence_query_revokes_pause_without_rewriting_immutable_evidence(paused_scene, operation):
    authority, native, args = paused_scene
    request = request_for(authority, native, args, operation)
    original = immutable_evidence(authority)
    windows = deepcopy((authority.native_windows, authority.owner.windows))
    prior_intent = authority.owner.user_intent
    native.current['user_intent'] += 1

    authority.dispatch(request)

    assert authority.owner.pause is None
    assert authority.owner.user_intent == prior_intent + 1
    assert authority.owner.observed['native_user_intent'] == native.current['user_intent']
    assert authority.owner.observed['paused'] is True
    assert authority.owner.desired['cancelled'] is False
    assert immutable_evidence(authority) == original
    assert (authority.native_windows, authority.owner.windows) == windows
    assert native.commands == [] and native.gui_commands == []
    native.gui['windows'] = []
    resident_window_tick(authority, native)
    resident_window_tick(authority, native)
    assert native.commands == [] and native.gui_commands == []
    assert authority.owner.user_intent == prior_intent + 1


def test_resident_tick_alone_revokes_same_sequence_intent_before_window_release(paused_scene):
    authority, native, _ = paused_scene
    original = immutable_evidence(authority)
    prior_intent = authority.owner.user_intent
    native.current['user_intent'] += 1
    native.gui['windows'] = []

    resident_window_tick(authority, native)

    assert authority.owner.pause is None
    assert authority.owner.user_intent == prior_intent + 1
    assert authority.owner.observed['native_user_intent'] == native.current['user_intent']
    assert immutable_evidence(authority) == original
    assert native.commands == [] and native.gui_commands == []


def test_repeated_live_reads_are_idempotent_and_each_new_intent_only_revokes_once(paused_scene):
    authority, native, _ = paused_scene
    original = immutable_evidence(authority)
    prior_intent = authority.owner.user_intent
    for increase in (1, 2):
        native.current['user_intent'] += 1
        for _ in range(3):
            authority.dispatch(dict(operation='snapshot'))
            resident_window_tick(authority, native)
        assert authority.owner.user_intent == prior_intent + increase
        assert authority.owner.observed['native_user_intent'] == native.current['user_intent']
        assert authority.owner.pause is None
        assert immutable_evidence(authority) == original
        assert native.commands == [] and native.gui_commands == []


def test_raw_same_sequence_event_stays_rejected_until_fresh_state_is_observed(paused_scene):
    authority, native, _ = paused_scene
    before = complete_state(authority)
    native.current['user_intent'] += 1

    assert not authority.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    assert complete_state(authority) == before
    authority.dispatch(dict(operation='snapshot'))
    assert authority.owner.pause is None
    assert immutable_evidence(authority) == before[-1]


@pytest.mark.parametrize('kind', ['manual', 'transport'])
@pytest.mark.parametrize('observe', ['snapshot', 'resident_tick'])
def test_live_intent_revokes_matching_real_continuation_without_replaying_control(tmp_path, kind, observe):
    if kind == 'transport':
        from test_transport_handoff_authority import command, setup
        authority, native, args, _, account, message = setup(tmp_path)
        grant = authority.dispatch(message)
        native.captured()
        assert authority.dispatch(command(args, account, grant, 'transport_status'))['state'] == 'CAPTURED'
    else:
        authority, native, args = playing()
        grant = authority.dispatch(dict(args, operation='manual_next',
            native_instance=native.current['native_instance'], selection_identity='next-release'))
    assert grant['authorized'] and authority.continuation
    original = immutable_evidence(authority)
    attempt = deepcopy(authority.transport_attempt)
    native.commands.clear()
    native.current['user_intent'] += 1

    if observe == 'snapshot':
        authority.dispatch(dict(operation='snapshot'))
    else:
        resident_window_tick(authority, native)

    assert authority.continuation is None
    assert authority.transport_attempt == attempt
    assert immutable_evidence(authority) == original
    assert native.commands == [] and native.gui_commands == []
    # Even a later real STOP receipt cannot resurrect the revoked token.
    native.current.update(phase='TERMINAL', reason='STOP', sequence=native.current['sequence'] + 1)
    assert authority.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    with pytest.raises(RuntimeError):
        authority.dispatch(dict(args, operation='reserve_child', token=grant['token'],
            account_scope=account if kind == 'transport' else None,
            child_request_id=uuid4().hex,
            selection_identity=message['selection_identity'] if kind == 'transport' else 'next-release'))
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('change', [
    'old_sequence', 'new_sequence', 'lower_intent', 'unchanged_intent', 'native_instance',
    'request_id', 'file_identity', 'url_sha256', 'open_epoch', 'open_phase', 'terminal_phase',
    'paused', 'subtitle_regression', 'audio_regression', 'subtitle_auto_intent',
    'audio_missing', 'subtitle_missing', 'unexpected_field', 'boolean_intent',
])
def test_invalid_live_candidate_cannot_revoke_retarget_or_change_event_history(paused_scene, change):
    authority, native, _ = paused_scene
    candidate = deepcopy(native.current)
    candidate['user_intent'] += 1
    if change == 'old_sequence': candidate['sequence'] -= 1
    elif change == 'new_sequence': candidate['sequence'] += 1
    elif change == 'lower_intent': candidate['user_intent'] -= 2
    elif change == 'unchanged_intent': candidate['user_intent'] -= 1
    elif change == 'native_instance': candidate['native_instance'] = str(uuid4())
    elif change == 'request_id': candidate['request_id'] = uuid4().hex
    elif change == 'file_identity': candidate['file_identity'] = 'another-file'
    elif change == 'url_sha256': candidate['url_sha256'] = 'b' * 64
    elif change == 'open_epoch': candidate['open_epoch'] += 1
    elif change == 'open_phase': candidate['phase'] = 'OPEN'
    elif change == 'terminal_phase': candidate.update(phase='TERMINAL', reason='NATURAL_EOF')
    elif change == 'paused': candidate['paused'] = False
    elif change == 'subtitle_regression': candidate['subtitle_intent'] -= 1
    elif change == 'audio_regression': candidate['audio_intent'] -= 1
    elif change == 'subtitle_auto_intent': candidate['subtitle_auto_intent'] += 1
    elif change == 'audio_missing': candidate.pop('audio_intent')
    elif change == 'subtitle_missing': candidate.pop('subtitle_intent')
    elif change == 'unexpected_field': candidate['new_ownership_evidence'] = True
    elif change == 'boolean_intent': candidate['user_intent'] = True
    before = complete_state(authority)

    authority._revoke_live_intent(candidate)

    assert complete_state(authority) == before
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('state', ['idle', 'selected', 'external', 'cancelled', 'epoch_changed'])
def test_live_intent_requires_existing_current_managed_owner_and_cannot_create_one(state):
    if state in ('cancelled', 'epoch_changed'):
        authority, native, args = playing()
        if state == 'cancelled':
            authority.owner.cancel(args['boot_id'], args['epoch'], args['request_id'])
        else:
            authority.native_epoch += 1
        candidate = dict(native.current, user_intent=native.current['user_intent'] + 1)
    else:
        native = Native()
        authority = PlaybackAuthority(native)
        if state == 'selected':
            args = select(authority)
            candidate = row(args['request_id'], 'file-a', user_intent=1)
        else:
            candidate = row(identity='external-file', user_intent=1)
            if state == 'external':
                native.current = deepcopy(candidate)
                authority.refresh()
                candidate['user_intent'] += 1
    before = complete_state(authority)

    authority._revoke_live_intent(candidate)

    assert complete_state(authority) == before
    assert native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('change', ['foreign_request', 'foreign_instance', 'newer_intent'])
def test_live_revocation_does_not_clear_foreign_or_newer_continuation(paused_scene, change):
    authority, native, args = paused_scene
    assert authority.dispatch(dict(args, operation='manual_next',
        native_instance=native.current['native_instance'], selection_identity='next-release'))['authorized']
    if change == 'foreign_request': authority.continuation['request_id'] = uuid4().hex
    elif change == 'foreign_instance': authority.continuation['native_instance'] = str(uuid4())
    else: authority.continuation['native_user_intent'] = native.current['user_intent'] + 1
    grant = deepcopy(authority.continuation)
    native.commands.clear()
    native.current['user_intent'] += 1

    authority.dispatch(dict(operation='snapshot'))

    assert authority.owner.pause is None
    assert authority.continuation == grant
    assert native.commands == [] and native.gui_commands == []


def test_live_observation_does_not_consume_or_replace_retained_immutable_eof(paused_scene):
    authority, native, args = paused_scene
    end = dict(native.current, phase='TERMINAL', reason='NATURAL_EOF',
        sequence=native.current['sequence'] + 1,
        completion_observation=dict(schema=1, position_ms=99960, duration_ms=100000,
                                    age_us=10000, valid=True))
    assert authority.event('xbmc', 'Player.OnBobiState', deepcopy(end))
    before = complete_state(authority)

    authority._revoke_live_intent(dict(end, user_intent=end['user_intent'] + 1))
    authority._revoke_live_intent(dict(native.current, user_intent=end['user_intent'] + 1))

    assert complete_state(authority) == before
    assert authority.owner.terminal['consumed'] is False
    assert not authority.event('xbmc', 'Player.OnBobiState', deepcopy(end))
    native.current = None
    grant = authority.dispatch(dict(args, operation='authorize_next',
        native_instance=end['native_instance'], selection_identity='next-release'))
    assert grant['authorized']
    assert authority.owner.terminal['consumed'] is True
