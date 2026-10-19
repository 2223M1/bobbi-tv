"""Simulated actor regression, explicitly not Kodi/device evidence."""
from copy import deepcopy
from threading import Thread
from uuid import uuid4

import pytest

from lib.cinema.native_receipt import ReceiptHistory, receipt
from lib.cinema.playback_authority import PlaybackAuthority


def row(request='', identity='', phase='AV_STARTED', **fields):
    result = dict(protocol=1, native_instance=str(uuid4()), request_id=request,
                file_identity=identity, url_sha256='a' * 64, phase=phase,
                sequence=1, user_intent=0, paused=False, subtitle_intent=0, subtitle_auto_intent=0)
    result.update(fields)
    return result


class Native:
    def __init__(self):
        self.current = None
        self.commands = []
        self.epoch = 0
        self.gui = dict(gui_generation=0, gui_user_intent=0, fullscreen_instance='')
        self.gui_commands = []

    def state(self):
        return dict(protocol=1, selection_epoch=self.epoch, playback=deepcopy(self.current), **self.gui)

    def fullscreen(self, command):
        self.gui_commands.append(deepcopy(command))
        return {'queued': True}

    def intent(self, command):
        if command['expected_epoch'] != self.epoch:
            return {'reserved': False, 'selection_epoch': self.epoch}
        self.epoch += 1
        return {'reserved': True, 'selection_epoch': self.epoch}

    def control(self, command):
        self.commands.append(deepcopy(command))
        return {'queued': True}


def select(authority, ident='release-a'):
    state = authority.dispatch({'operation': 'snapshot'})
    args = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=uuid4().hex)
    result = authority.dispatch(dict(args, operation='select', selection_identity=ident))
    args['epoch'] = result['epoch']
    return args


def bind(authority, args):
    result = authority.dispatch(dict(args, operation='bind_file', selection_identity='release-a',
                                    file_identity='file-a', url_sha256='a' * 64))
    assert result == {'bound': True}


def test_resolver_failure_is_not_a_native_terminal_and_blocks_late_start():
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    message = dict(args, operation='resolver_failed', category='target_unresolved')
    assert authority.dispatch(message) == {'recorded': True}
    state = authority.dispatch({'operation': 'snapshot'})
    assert state['desired']['resolver_failure'] == {'request_id': args['request_id'], 'category': 'target_unresolved'}
    assert state['terminal'] is None and state['observed'] is None
    assert authority.dispatch(dict(args, operation='bind_file', selection_identity='release-a',
                                   file_identity='file-a', url_sha256='a' * 64)) == {'bound': False}
    assert authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] != 'CLAIMED'
    assert authority.dispatch(message) == {'recorded': False}
    assert native.commands == []


@pytest.mark.parametrize('change', ['new_selection', 'cancelled', 'boot', 'epoch', 'playing'])
def test_late_resolver_failure_never_affects_new_or_started_playback(change):
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    if change == 'new_selection': select(authority, 'release-b')
    elif change == 'cancelled': authority.dispatch(dict(args, operation='cancel'))
    elif change == 'boot': args['boot_id'] = 'old'
    elif change == 'epoch': args['epoch'] -= 1
    else:
        bind(authority, args)
        authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))
        native.current = row(args['request_id'], 'file-a')
        authority.refresh()
    before = authority.dispatch({'operation': 'snapshot'})
    assert authority.dispatch(dict(args, operation='resolver_failed', category='target_unresolved')) == {'recorded': False}
    assert authority.dispatch({'operation': 'snapshot'}) == before
    assert native.commands == []


def test_resolver_failure_rejects_unbounded_or_native_terminal_categories():
    authority = PlaybackAuthority(Native())
    args = select(authority)
    for category in ('NATURAL_EOF', 'STOP', 'secret-url', None, {}):
        with pytest.raises(ValueError):
            authority.dispatch(dict(args, operation='resolver_failed', category=category))


def playing():
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    assert authority.dispatch(dict(args, operation='claim_start', route='resolved_url')) == {'status': 'CLAIMED'}
    native.current = row(args['request_id'], 'file-a')
    authority.refresh()
    return authority, native, args


def subtitle_catalog(native, tracks, index=-1, visible=False):
    native.current['subtitle_intent'] = 0
    native.current['subtitle_auto_intent'] = 0
    result = dict(status='READY', receipt=deepcopy(native.current),
                  selection_epoch=native.epoch, streams=tracks, current_index=index, visible=visible)
    native.subtitles = lambda: deepcopy(result)
    native.subtitle = native.control
    return result


def test_scoped_chinese_selection_requires_execution_confirmation():
    authority, native, args = playing()
    tracks = [dict(index=0, language='eng', stream_key='e' * 64),
              dict(index=1, language='zho', stream_key='c' * 64)]
    catalog = subtitle_catalog(native, tracks)
    request = dict(args, operation='auto_chinese_subtitle', native_instance=native.current['native_instance'])
    result = authority.dispatch(request)
    assert result['status'] == 'QUEUED'
    command = native.commands[-1]
    assert command['index'] == 1 and command['stream_key'] == 'c' * 64
    assert command['native_instance'] == native.current['native_instance']
    assert command['subtitle_intent'] == 0
    assert command['selection_epoch'] == native.epoch
    assert authority.dispatch(request)['status'] == 'QUEUED'
    assert len(native.commands) == 1  # A late native receipt does not re-open the subtitle repeatedly.
    catalog['current_index'], catalog['visible'] = 1, True
    assert authority.dispatch(request)['status'] == 'CONFIRMED'
    assert len(native.commands) == 1


@pytest.mark.parametrize('change', ['manual', 'new_instance', 'new_selection', 'forced_only'])
def test_scoped_subtitle_catalog_cannot_apply_stale_or_forced_results(change):
    authority, native, args = playing()
    catalog = subtitle_catalog(native, [dict(index=0, language='zho', stream_key='c' * 64)])
    old_instance = native.current['native_instance']
    if change == 'manual':
        native.current['subtitle_intent'] = catalog['receipt']['subtitle_intent'] = 1
    elif change == 'new_instance':
        native.current['native_instance'] = str(uuid4())
    elif change == 'new_selection':
        select(authority, 'release-b')
    else:
        catalog['streams'][0]['isforced'] = True
    result = authority.dispatch(dict(args, operation='auto_chinese_subtitle', native_instance=old_instance))
    assert result['status'] in ('STALE', 'MANUAL_PRESERVED', 'NO_FULL_CHINESE_TRACK')
    assert native.commands == []


def test_manual_intent_during_catalog_read_wins():
    authority, native, args = playing()
    catalog = subtitle_catalog(native, [dict(index=0, language='zho', stream_key='c' * 64)])
    def read_then_manual():
        native.current['subtitle_intent'] += 1
        return deepcopy(catalog)
    native.subtitles = read_then_manual
    assert authority.dispatch(dict(args, operation='auto_chinese_subtitle',
        native_instance=native.current['native_instance']))['status'] == 'STALE'
    assert not native.commands


@pytest.mark.parametrize('terminal', ['resolver_failed', 'cancel'])
def test_preav_failure_and_cancel_do_not_publish_status_owner(terminal):
    from unittest.mock import Mock
    native = Native()
    native.publish_subtitle_status = Mock()
    authority = PlaybackAuthority(native)
    args = select(authority)
    if terminal == 'resolver_failed':
        authority.dispatch(dict(args, operation=terminal, category='target_unresolved'))
    else:
        authority.dispatch(dict(args, operation=terminal))
    assert authority.dispatch(dict(args, operation='auto_chinese_subtitle',
        native_instance=str(uuid4()), subtitle_final_attempt=True)) == {'status': 'STALE'}
    native.publish_subtitle_status.assert_not_called()


@pytest.mark.parametrize('manual', [False, True])
def test_valid_av_status_publication_uses_current_receipt_even_for_manual(manual):
    from unittest.mock import Mock
    authority, native, args = playing()
    catalog = subtitle_catalog(native, [dict(index=0, language='zho', stream_key='c' * 64)], 0, True)
    if manual:
        native.current['subtitle_intent'] = catalog['receipt']['subtitle_intent'] = 1
    # Exercise a newer native event as well; live subtitle changes alone do not
    # increment native sequence (covered in test_subtitle_presentation_snapshot).
    native.current['sequence'] += 1
    catalog['receipt']['sequence'] = native.current['sequence']
    native.publish_subtitle_status = Mock()
    result = authority.dispatch(dict(args, operation='auto_chinese_subtitle',
        native_instance=native.current['native_instance'], subtitle_final_attempt=True))
    assert result['status'] == ('MANUAL_PRESERVED' if manual else 'CONFIRMED')
    native.publish_subtitle_status.assert_called_once_with(native.current, result['status'], True)
    assert native.commands == []


@pytest.mark.parametrize('change', ['new_selection', 'cancel', 'external_intent', 'new_instance', 'request_mismatch', 'stopped', 'unknown'])
def test_status_publication_revalidates_ownership_and_never_clears_newer(change):
    from unittest.mock import Mock
    authority, native, args = playing()
    subtitle_catalog(native, [], -1, False)
    instance = native.current['native_instance']
    labels = {'AM6B.SubtitleStateOwner': 'new-request', 'AM6B.SubtitleState': 'new-status'}
    native.publish_subtitle_status = Mock(side_effect=lambda *args: labels.clear())
    if change == 'new_selection':
        select(authority, 'release-b')
    elif change == 'cancel':
        authority.dispatch(dict(args, operation='cancel'))
    elif change == 'external_intent':
        native.epoch += 1
    elif change == 'new_instance':
        native.current['native_instance'] = str(uuid4())
    elif change == 'request_mismatch':
        native.current['request_id'] = 'f' * 32
    elif change == 'stopped':
        native.current = None
    else:
        native.state = Mock(side_effect=OSError('native unavailable'))
    owner_args = tuple(args[key] for key in ('boot_id', 'epoch', 'request_id'))
    authority._publish_subtitle_status(owner_args, instance, {'status': 'CONFIRMED'}, True)
    native.publish_subtitle_status.assert_not_called()
    assert labels == {'AM6B.SubtitleStateOwner': 'new-request', 'AM6B.SubtitleState': 'new-status'}


def test_late_a_response_cannot_overwrite_published_b_status():
    from unittest.mock import Mock
    authority, native, args_a = playing()
    instance_a = native.current['native_instance']
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    authority.refresh()
    native.current = None
    args_b = select(authority)
    bind(authority, args_b)
    authority.dispatch(dict(args_b, operation='claim_start', route='resolved_url'))
    native.current = row(args_b['request_id'], 'file-a')
    catalog = subtitle_catalog(native, [dict(index=0, language='zho', stream_key='c' * 64)], 0, True)
    native.publish_subtitle_status = Mock()
    authority.dispatch(dict(args_b, operation='auto_chinese_subtitle', native_instance=native.current['native_instance']))
    assert native.publish_subtitle_status.call_count == 1
    assert native.publish_subtitle_status.call_args.args[0]['request_id'] == args_b['request_id']
    owner_args = tuple(args_a[key] for key in ('boot_id', 'epoch', 'request_id'))
    authority._publish_subtitle_status(owner_args, instance_a, {'status': 'CONFIRMED'}, True)
    assert native.publish_subtitle_status.call_count == 1


@pytest.mark.parametrize('protocol', [True, 1.0])
def test_publication_rejects_noninteger_protocol_before_observation(protocol):
    from unittest.mock import Mock
    authority, native, args = playing()
    instance = native.current['native_instance']
    before = deepcopy(authority.history.items)
    state = native.state
    native.state = lambda: dict(state(), protocol=protocol)
    native.publish_subtitle_status = Mock()
    owner_args = tuple(args[key] for key in ('boot_id', 'epoch', 'request_id'))
    authority._publish_subtitle_status(owner_args, instance, {'status': 'CONFIRMED'}, True)
    native.publish_subtitle_status.assert_not_called()
    assert authority.history.items == before


@pytest.mark.parametrize('stale_sequence', [1, 3])
def test_publication_never_replays_old_or_same_sequence_auto_over_manual(stale_sequence):
    from unittest.mock import Mock
    authority, native, args = playing()
    native.current.update(sequence=3, subtitle_intent=1, subtitle_auto_intent=0)
    instance = native.current['native_instance']
    native.publish_subtitle_status = Mock()
    owner_args = tuple(args[key] for key in ('boot_id', 'epoch', 'request_id'))
    authority._publish_subtitle_status(owner_args, instance, {'status': 'MANUAL_PRESERVED'})
    assert native.publish_subtitle_status.call_count == 1
    accepted = deepcopy(authority.history.items[instance])
    native.current.update(sequence=stale_sequence, subtitle_intent=0)
    authority._publish_subtitle_status(owner_args, instance, {'status': 'CONFIRMED'}, True)
    assert native.publish_subtitle_status.call_count == 1
    assert authority.history.items[instance] == accepted


def test_late_chinese_track_beyond_first_32_is_not_hidden_by_an_ordinal_cap():
    authority, native, args = playing()
    tracks = [dict(index=i, language='eng', stream_key=f'{i:064x}') for i in range(40)]
    catalog = subtitle_catalog(native, tracks)
    command = dict(args, operation='auto_chinese_subtitle', native_instance=native.current['native_instance'])
    assert authority.dispatch(command)['status'] == 'NO_FULL_CHINESE_TRACK'
    catalog['streams'].append(dict(index=40, language='zho', stream_key='c' * 64))
    assert authority.dispatch(command)['status'] == 'QUEUED'
    assert native.commands[0]['index'] == 40


def test_fullscreen_requires_native_confirmation_not_client_visibility():
    authority, native, args = playing()
    command = dict(args, native_instance=native.current['native_instance'])
    assert authority.dispatch(dict(command, operation='request_fullscreen')) == {'queued': True}
    assert authority.dispatch(dict(command, operation='confirm_fullscreen', actually_fullscreen=True)) == {'confirmed': False}
    assert authority.dispatch(dict(command, operation='request_fullscreen')) == {'queued': False}
    native.gui['fullscreen_instance'] = command['native_instance']
    assert authority.dispatch(dict(command, operation='confirm_fullscreen')) == {'confirmed': True}
    native.gui['gui_user_intent'] += 1  # User Back after confirmed handoff.
    assert authority.dispatch(dict(command, operation='request_fullscreen')) == {'queued': False}
    assert len(native.gui_commands) == 1


def test_back_before_native_handoff_never_queues_activation():
    authority, native, args = playing()
    native.gui['gui_user_intent'] += 1
    assert authority.dispatch(dict(args, native_instance=native.current['native_instance'],
                                   operation='request_fullscreen')) == {'queued': False}
    assert not native.gui_commands


def test_loading_window_lease_must_close_before_fullscreen():
    authority, native, args = playing()
    token = uuid4().hex
    assert authority.dispatch(dict(args, token=token, role='loading', operation='register_window'))['registered']
    command = dict(args, native_instance=native.current['native_instance'], operation='request_fullscreen')
    assert authority.dispatch(command) == {'queued': False}
    assert authority.dispatch(dict(args, token=token, operation='close_window'))['closed']
    assert authority.dispatch(command) == {'queued': True}


def window(native, args, role='subtitles'):
    return dict(token=uuid4().hex, role=role, request_id=args['request_id'],
                native_instance=native.current['native_instance'])


def test_native_osd_nested_lease_pauses_once_and_resumes_only_after_last_close():
    authority, native, args = playing()
    parent = window(native, args)
    native.gui['windows'] = [parent]
    authority.refresh()
    assert [c['action'] for c in native.commands] == ['pause']
    assert native.commands[0]['window_token'] == parent['token']
    native.current.update(paused=True, sequence=2)
    authority.refresh()
    child = window(native, args, 'audio')
    native.gui['windows'] = [child]  # Child opens as parent closes.
    authority.refresh()
    assert [c['action'] for c in native.commands] == ['pause']
    native.gui['windows'] = []
    authority.refresh()
    assert [c['action'] for c in native.commands] == ['pause', 'resume']
    assert native.commands[-1]['window_token'] == child['token']
    authority.refresh()
    assert len(native.commands) == 2


@pytest.mark.parametrize('manual', [False, True])
def test_continuation_requires_terminal_exact_release_and_one_use_grant(manual):
    authority, native, args = playing()
    instance = native.current['native_instance']
    if not manual:
        native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    grant = authority.dispatch(dict(args, native_instance=instance,
        operation='manual_next' if manual else 'authorize_next', selection_identity='next-release'))
    assert grant['authorized']
    command = dict(args, operation='reserve_child', token=grant['token'],
                   child_request_id=uuid4().hex, selection_identity='next-release')
    if manual:
        with pytest.raises(RuntimeError):
            authority.dispatch(command)  # Stop queued is not completed.
        native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    with pytest.raises(RuntimeError):
        authority.dispatch(dict(command, selection_identity='other-release'))
    state = authority.dispatch(command)
    assert state['desired']['request_id'] == command['child_request_id']
    with pytest.raises(RuntimeError):
        authority.dispatch(command)


@pytest.mark.parametrize('destroy_before_grant', [False, True])
def test_native_player_destruction_preserves_verified_natural_terminal_for_child(destroy_before_grant):
    authority, native, args = playing()
    instance = native.current['native_instance']
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    assert authority.event('xbmc', 'Player.OnBobiState', deepcopy(native.current))
    if destroy_before_grant:
        native.current = None  # Real CApplicationPlayer has released IPlayer.
    grant = authority.dispatch(dict(args, operation='authorize_next', native_instance=instance,
                                   selection_identity='same-next-release'))
    assert grant['authorized']
    native.current = None
    child = uuid4().hex
    result = authority.dispatch(dict(args, operation='reserve_child', token=grant['token'],
                                     child_request_id=child, selection_identity='same-next-release'))
    assert result['desired']['request_id'] == child


@pytest.mark.parametrize('change', ['epoch', 'gui', 'different-player', 'missing-state', 'late'])
def test_cached_natural_terminal_is_not_permission_after_new_input_or_unknown_state(change, monkeypatch):
    import lib.cinema.playback_authority as module
    clock = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    authority, native, args = playing()
    instance = native.current['native_instance']
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    grant = authority.dispatch(dict(args, operation='authorize_next', native_instance=instance,
                                   selection_identity='next'))
    assert grant['authorized']
    native.current = None
    if change == 'epoch': native.epoch += 1
    if change == 'gui': native.gui['gui_user_intent'] += 1
    if change == 'different-player': native.current = row(request=uuid4().hex, identity='other')
    if change == 'late': clock[0] += 3.01
    if change == 'missing-state':
        old = native.state
        native.state = lambda: {k: v for k, v in old().items() if k != 'playback'}
    with pytest.raises((RuntimeError, ValueError)):
        authority.dispatch(dict(args, operation='reserve_child', token=grant['token'],
                                child_request_id=uuid4().hex, selection_identity='next'))


@pytest.mark.parametrize('read_error', [-1, -5, -110])
def test_explicit_native_read_error_is_not_natural_continuation(read_error):
    authority, native, args = playing()
    native.current.update(phase='TERMINAL', reason='ERROR', sequence=2, read_error=read_error)
    observed = authority.dispatch({'operation': 'resource_snapshot'})
    assert observed['playback']['read_error'] == read_error
    result = authority.dispatch(dict(args, native_instance=native.current['native_instance'],
        operation='authorize_next', selection_identity='next-release'))
    assert not result['authorized']
    assert authority.owner.terminal['reason'] == 'ERROR'
    assert authority.owner.desired['cancelled']


@pytest.mark.parametrize('change', ['new-selection', 'manual-stop', 'error', 'back'])
def test_manual_next_grant_is_revoked_by_new_intent_or_error(change):
    authority, native, args = playing()
    grant = authority.dispatch(dict(args, native_instance=native.current['native_instance'],
                                   operation='manual_next', selection_identity='next'))
    assert grant['authorized']
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    if change == 'manual-stop': native.current['user_intent'] += 1
    if change == 'error': native.current['reason'] = 'ERROR'
    if change == 'back': native.gui['gui_user_intent'] += 1
    if change == 'new-selection': select(authority, 'different-movie')
    with pytest.raises(RuntimeError):
        authority.dispatch(dict(args, operation='reserve_child', token=grant['token'],
            child_request_id=uuid4().hex, selection_identity='next'))


@pytest.mark.parametrize('manual', ['already-paused', 'later-pause', 'new-selection', 'close-before-pause'])
def test_native_osd_never_resumes_without_its_confirmed_pause_right(manual):
    authority, native, args = playing()
    if manual == 'already-paused':
        native.current.update(paused=True, sequence=2)
    native.gui['windows'] = [window(native, args)]
    authority.refresh()
    if manual == 'later-pause':
        native.current.update(paused=True, user_intent=1, sequence=3)
    elif manual == 'new-selection':
        select(authority, 'release-b')
        native.current.update(paused=True, sequence=3)
    native.gui['windows'] = []
    authority.refresh()
    assert not any(command['action'] == 'resume' for command in native.commands)


@pytest.mark.parametrize('reason', ['ERROR', 'NATURAL_EOF'])
def test_terminal_before_first_open_poll_is_recorded_without_fabricating_av(reason):
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))
    native.current = row(args['request_id'], 'file-a', phase='TERMINAL', reason=reason)
    authority.refresh()
    assert authority.owner.terminal['reason'] == 'ERROR'
    assert not authority.owner.terminal['av_started']
    assert authority.owner.desired['cancelled']


def test_old_observed_player_is_not_relabelled_after_selection():
    native = Native()
    native.current = row()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    for _ in range(2):
        assert authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] == 'WAIT_TERMINAL'
    assert len(native.commands) == 1
    assert native.commands[0]['native_instance'] == native.current['native_instance']
    assert authority.owner.observed['request_id'] == ''
    # Queue acknowledgement has not cleared the actually observed old video.
    native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
    assert authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
    assert authority.dispatch(dict(args, operation='claim_start', route='player_play'))['status'] == 'ALREADY_CLAIMED'


def test_new_external_player_c_is_never_stopped_by_waiting_b():
    native = Native()
    native.current = row()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    native.current = row()  # An independent open happened outside this request.
    assert authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] == 'OTHER_PLAYBACK'
    assert native.commands == []


def test_unknown_item_and_generic_onplay_cannot_grant_terminal_authority():
    authority, native, args = playing()
    for method in ('Player.OnPlay', 'Player.OnAVStart', 'Player.OnStop'):
        assert authority.event('xbmc', method, {'item': {'type': 'unknown'}, 'end': True}) is False
    assert authority.owner.terminal is None
    assert authority.owner.observed['request_id'] == args['request_id']


def test_open_then_av_start_upgrades_only_the_matching_native_instance():
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))
    native.current = row(args['request_id'], 'file-a', phase='OPEN')
    authority.refresh()
    assert authority.owner.observed['request_id'] == args['request_id']
    assert not authority.owner.observed['av_started']
    native.current.update(phase='AV_STARTED', sequence=2)
    authority.refresh()
    assert authority.owner.observed['av_started']


def test_eof_without_any_av_start_is_error_not_successful_episode():
    native = Native()
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))
    native.current = row(args['request_id'], 'file-a', phase='OPEN')
    authority.refresh()
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    authority.refresh()
    assert authority.owner.terminal['reason'] == 'ERROR'
    assert not authority.dispatch(dict(args, operation='consume_next', native_instance=native.current['native_instance']))['consumed']


@pytest.mark.parametrize('reason,can_next', [('STOP', False), ('ERROR', False),
                                          ('SUPERSEDED', False), ('NATURAL_EOF', True)])
def test_only_matching_native_natural_end_consumable_once(reason, can_next):
    authority, native, args = playing()
    instance = native.current['native_instance']
    native.current.update(phase='TERMINAL', reason=reason, sequence=2)
    first = authority.dispatch(dict(args, operation='consume_next', native_instance=instance))
    assert first['consumed'] is can_next
    assert authority.dispatch(dict(args, operation='consume_next', native_instance=instance)) == {'consumed': False}


def test_late_terminal_cannot_queue_old_episode_after_new_selection():
    authority, native, old = playing()
    current = select(authority)
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    assert not authority.dispatch(dict(old, operation='consume_next', native_instance=native.current['native_instance']))['consumed']
    assert authority.owner.desired['request_id'] == current['request_id']


def test_binding_cannot_change_release_url_or_exact_file():
    native, authority = Native(), None
    authority = PlaybackAuthority(native)
    args = select(authority)
    bind(authority, args)
    for changes in ({'selection_identity': 'release-b'}, {'file_identity': 'file-b'}, {'url_sha256': 'b' * 64}):
        command = dict(args, operation='bind_file', selection_identity='release-a', file_identity='file-a', url_sha256='a' * 64)
        command.update(changes)
        assert authority.dispatch(command) == {'bound': False}


def test_manual_pause_invalidates_osd_auto_resume():
    authority, native, args = playing()
    instance, token = native.current['native_instance'], uuid4().hex
    authority.dispatch(dict(args, operation='register_window', token=token, role='subtitles'))
    assert authority.dispatch(dict(args, operation='acquire_pause', token=token, native_instance=instance))['queued']
    native.current.update(paused=True, sequence=2)
    authority.refresh()
    native.current.update(user_intent=1, sequence=3)
    authority.refresh()
    assert not authority.dispatch(dict(args, operation='release_pause', token=token, native_instance=instance))['queued']
    assert [command['action'] for command in native.commands] == ['pause']


def test_native_interface_absence_is_not_unscoped_fallback():
    native = Native()
    native.state = lambda: {'error': 'Method not found'}
    with pytest.raises(RuntimeError, match='原生播放实例'):
        PlaybackAuthority(native).dispatch({'operation': 'snapshot'})
    assert native.commands == []


def test_service_rejects_second_writer_thread():
    authority = PlaybackAuthority(Native())
    errors = []
    def second_writer():
        try:
            authority.dispatch({'operation': 'snapshot'})
        except RuntimeError as error:
            errors.append(str(error))
    worker = Thread(target=second_writer)
    worker.start()
    worker.join()
    assert errors == ['Playback authority has exactly one service thread']


@pytest.mark.parametrize('bad', [dict(protocol=True), dict(sequence=True), dict(user_intent=-1),
                               dict(request_id='old'), dict(url_sha256='url'), dict(paused='false'),
                               dict(phase='TERMINAL', reason='unknown')])
def test_malformed_receipts_rejected(bad):
    value = row()
    value.update(bad)
    assert receipt(value) is None


def test_immutable_native_binding_and_terminal_sticky_even_with_higher_late_sequence():
    history = ReceiptHistory()
    value = row()
    assert history.accept(value)
    assert history.accept(dict(value, file_identity='changed', sequence=2)) is None
    assert history.accept(dict(value, phase='TERMINAL', reason='ERROR', sequence=2))
    assert history.accept(dict(value, sequence=100)) is None
