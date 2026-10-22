from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace

import pytest

from bobbi_core import preparation_client
from bobbi_core.playback_request import torrent_file_identity
from lib.clients import bobi_library
from lib.utils.player.transport_recovery import Recovery, exact_context, verify_ready, child_data
from test_bt_next_continuity import proved


CAPSULE = '12345678-1234-1234-1234-123456789abc'


@pytest.fixture
def recovery_case(proved, monkeypatch):
    data = deepcopy(proved.current)
    data['url'] = 'http://127.0.0.1:8090/current'
    selected = proved.proof['anchor']['selected']
    identity = torrent_file_identity(selected['source_info_hash'], selected['torrent_file_id'],
                                     selected['torrent_path'], selected['torrent_file_bytes'])
    target = dict(request_id=data['request_id'], purpose='current', selected=deepcopy(selected),
        media=dict(tmdb_id=1, kind='tv', season=1, episode=1, anime=False, title='Series', release_title=data['source_title']))
    snapshot = dict(boot_id='boot', epoch=1, desired=dict(request_id=data['request_id'], cancelled=False,
        selection_identity='bt:' + selected['source_info_hash'], file_identity=identity,
        file_evidence='AUTO_VERIFIED_FILE', file_bound=True, start_claimed=True),
        observed=dict(request_id=data['request_id'], native_instance='native-A', av_started=True,
                      file_identity=identity, paused=False))
    context = exact_context(data, target, snapshot, 'native-A')
    assert context is not None
    entry = dict(proved.entry, title=selected['torrent_path'], season=1, episode=1,
        path='/115open/inbox/' + selected['torrent_path'], video_context=deepcopy(proved.proof['anchor']))
    index = dict(proved.index, titles=[dict(kind='tv', tmdb_id=1, sources=[entry])])
    status = dict(proved.status, result={'tasks': [dict(task_id='task', media_id=context['media_id'], version_key='b' * 64)]})
    monkeypatch.setattr(bobi_library, 'load_prepared_index', lambda: deepcopy(index))
    verification = dict(request_id=data['request_id'], verification_id='f' * 32, resource_id=entry['key'],
        generation=index['generation'], account=index['account'], source_info_hash=selected['source_info_hash'],
        media_id=context['media_id'], qualification=entry['prepared_qualification'])
    result = dict(entry=entry, verification=verification, url=index['mount_root'] + entry['path'])
    commands, phases, control = [], ['CAPTURED'], {}
    def command(body):
        commands.append(deepcopy(body))
        operation = body['operation']
        assert body['account_scope'] == data['_account']
        if operation == 'transport_capture':
            control['child'] = body['child_request_id']
            assert body['prepared_verification'] == verification
            return dict(authorized=True, token='9' * 32, state='PENDING')
        if operation == 'transport_status':
            return dict(state=phases[0], capsule=CAPSULE, position_ms=123450,
                        child_request_id=control['child'], file_identity=identity)
        if operation == 'transport_stop':
            phases[0] = 'STOP_REQUESTED'
            return {'queued': True}
        assert operation == 'reserve_child'
        assert body['child_request_id'] == control['child']
        assert body['selection_identity'] == context['selection_identity']
        return dict(boot_id='boot', epoch=2, desired={'request_id': control['child'], 'cancelled': False})
    return SimpleNamespace(data=data, target=target, snapshot=snapshot, context=context, entry=entry,
        index=index, status=status, verification=verification, result=result, commands=commands,
        phases=phases, command=command)


def prime(case, recovery=None):
    recovery = recovery or Recovery(verify=lambda context, cancelled: case.result)
    recovery.tick(0, 123.45, True, False, case.context, case.command)
    recovery.tick(5.9, 123.45, True, False, case.context, case.command)
    assert recovery.worker is None
    recovery.tick(6, 123.45, True, False, case.context, case.command)
    recovery.worker.join(1)
    recovery.tick(6.1, 123.45, True, False, case.context, case.command)
    assert recovery.state == 'CAPTURING'
    return recovery


def test_same_file_capture_stop_real_terminal_and_one_child(recovery_case):
    case = recovery_case
    recovery = prime(case)
    assert [row['operation'] for row in case.commands] == ['transport_capture']
    recovery.tick(6.4, 123.45, True, False, case.context, case.command)
    assert recovery.state == 'STOPPING'
    assert recovery.reserve(case.command) is None
    case.phases[0] = 'STOPPED'
    recovery.poll(7, case.command, allow_stop=False)
    child = recovery.reserve(case.command)
    assert child['_transport_handoff']['position_ms'] == 123450
    assert child['_transport_handoff']['capsule'] == CAPSULE
    assert child['tv_data'] == case.data['tv_data'] and child['ids'] == case.data['ids']
    assert child['info_hash'] == case.data['info_hash']
    assert child['prepared_resource_id'] == case.entry['key'] and not child['is_torrent']
    assert recovery.reserve(case.command) is None
    recovery.tick(10, 123.45, True, False, case.context, case.command)
    assert len([row for row in case.commands if row['operation'] == 'transport_stop']) == 1
    assert len([row for row in case.commands if row['operation'] == 'reserve_child']) == 1


def test_lost_stop_ack_and_delayed_actual_stop_keep_same_grant_for_thirty_seconds(recovery_case):
    case = recovery_case
    recovery = prime(case)
    def command(body):
        value = case.command(body)
        if body['operation'] == 'transport_stop': raise OSError('lost ack after queue')
        return value
    recovery.tick(6.4, 123.45, True, False, case.context, command)
    for now in (10, 20, 30):
        recovery.tick(now, 123.45, True, False, case.context, command)
        assert recovery.state == 'STOPPING'
    case.phases[0] = 'STOPPED'
    recovery.poll(31, command, allow_stop=False)
    assert recovery.reserve(command) is not None
    assert len([row for row in case.commands if row['operation'] == 'transport_stop']) == 1


@pytest.mark.parametrize('change', ['pause', 'seek', 'buffer_ends', 'owner_unknown', 'account', 'instance'])
def test_interruption_during_fresh_verification_cannot_capture_or_stop(recovery_case, change):
    case = recovery_case
    release, started = Event(), Event()
    def verify(context, cancelled):
        started.set()
        release.wait(1)
        return case.result
    recovery = Recovery(verify=verify)
    recovery.tick(0, 123.45, True, False, case.context, case.command)
    recovery.tick(6, 123.45, True, False, case.context, case.command)
    assert started.wait(1)
    context = deepcopy(case.context)
    if change == 'account': context['account_scope']['epoch'] += 1
    if change == 'instance': context['native_instance'] = 'native-other'
    recovery.tick(6.1, 150 if change == 'seek' else 123.45, change != 'buffer_ends', change == 'pause',
                  None if change == 'owner_unknown' else context, case.command)
    release.set()
    recovery.worker.join(1)
    recovery.tick(6.2, 123.45, True, False, context, case.command)
    assert case.commands == []
    recovery.close()


def test_pending_absent_or_failed_cloud_never_stops_bt_and_rechecks_with_backoff(recovery_case):
    case = recovery_case
    attempts = []
    recovery = Recovery(verify=lambda *args: attempts.append(1))
    recovery.tick(0, 10, True, False, case.context, case.command)
    recovery.tick(6, 10, True, False, case.context, case.command)
    recovery.worker.join(1)
    recovery.tick(6.1, 10, True, False, case.context, case.command)
    recovery.tick(10.9, 10, True, False, case.context, case.command)
    assert attempts == [1]
    recovery.tick(11.1, 10, True, False, case.context, case.command)
    recovery.worker.join(1)
    assert attempts == [1, 1] and case.commands == []
    recovery.close()


@pytest.mark.parametrize('position', [None, True, float('nan'), float('inf'), -1, 864001])
def test_unknown_or_invalid_progress_is_not_stall_evidence(recovery_case, position):
    case = recovery_case
    recovery = Recovery(verify=lambda *args: pytest.fail('invalid progress'))
    for now in (0, 6, 12):
        recovery.tick(now, position, True, False, case.context, case.command)
    assert case.commands == [] and recovery.worker is None


@pytest.mark.parametrize('phase', ['REJECTED', 'expired'])
def test_eof_winning_or_capsule_expiry_never_reserves_same_file(recovery_case, phase):
    case = recovery_case
    recovery = prime(case)
    recovery.tick(6.4, 123.45, True, False, case.context, case.command)
    case.phases[0] = 'REJECTED' if phase == 'REJECTED' else 'STOP_REQUESTED'
    recovery.poll(7 if phase == 'REJECTED' else 36.1, case.command, allow_stop=False)
    assert recovery.reserve(case.command) is None
    assert recovery.state == 'REJECTED'


def test_lost_capture_reply_never_replays_control_or_stops(recovery_case):
    case = recovery_case
    def command(body):
        case.command(body)
        raise OSError('lost capture ack')
    recovery = Recovery(verify=lambda *args: case.result)
    for now in (0, 6): recovery.tick(now, 123.45, True, False, case.context, command)
    recovery.worker.join(1)
    for now in (6.1, 7, 50): recovery.tick(now, 123.45, True, False, case.context, command)
    assert [row['operation'] for row in case.commands] == ['transport_capture']


def test_lost_reservation_reply_never_replays_or_creates_a_second_child(recovery_case):
    case = recovery_case
    recovery = prime(case)
    recovery.tick(6.4, 123.45, True, False, case.context, case.command)
    case.phases[0] = 'STOPPED'
    recovery.poll(7, case.command)
    def command(body):
        case.command(body)
        raise OSError('lost reservation')
    assert recovery.reserve(command) is None
    assert recovery.reserve(command) is None
    assert len([row for row in case.commands if row['operation'] == 'reserve_child']) == 1


@pytest.mark.parametrize('field', ['source_info_hash', 'torrent_file_id', 'torrent_path', 'torrent_file_bytes'])
def test_wrong_active_file_tuple_never_seeds_recovery(recovery_case, field):
    case = recovery_case
    value = deepcopy(case.target)
    value['selected'][field] = 99 if field in ('torrent_file_id', 'torrent_file_bytes') else ('9' * 40 if field == 'source_info_hash' else 'Other.mkv')
    assert exact_context(case.data, value, case.snapshot, 'native-A') is None


def test_child_clone_drops_every_old_resume_and_preserves_only_original_scope(recovery_case):
    case = recovery_case
    context = deepcopy(case.context)
    context['data'].update(trakt_resume_progress=20, simkl_resume_progress=30, nuvio_resume_percent=40,
        _bobi_resume_percent=50, _parent_request_id='old', _continuation_token='old-secret',
        _transport_old_token='old-secret', _account=deepcopy(case.data['_account']))
    child = child_data(context, case.result, '8' * 32, CAPSULE, 123450)
    assert child['_account'] == case.data['_account']
    assert not any('resume' in key or key in ('progress', 'current_time', 'total_time', 'subtitles_path', 'stream_subtitles') for key in child)
    assert 'old-secret' not in json.dumps(child)


def test_verify_requires_fresh_exact_same_file_and_returns_original_completed_nonce(recovery_case, monkeypatch):
    case = recovery_case
    calls = []
    def call(method, body, **kwargs):
        calls.append((method, deepcopy(body)))
        assert kwargs['expected_account'] == case.data['_account']
        if method == 'status': return case.status
        assert method == 'resolve'
        return dict(state='ready', **body, file_id=case.entry['prepared_file_id'], path=case.entry['path'],
            bytes=case.entry['bytes'], version_key=case.entry['prepared_version_key'], video_context=case.entry['video_context'])
    monkeypatch.setattr(preparation_client, 'call', call)
    result = verify_ready(case.context, lambda: False)
    assert result['entry'] == case.entry
    assert result['verification'] == calls[-1][1]
    assert result['verification']['request_id'] == case.data['request_id']
    assert result['verification']['verification_id']


@pytest.mark.parametrize('change', ['sibling', 'version', 'pending', 'removed', 'account'])
def test_unready_or_nonidentical_cloud_file_never_returns_capture_proof(recovery_case, monkeypatch, change):
    case = recovery_case
    if change == 'sibling':
        case.entry['video_context']['selected']['torrent_path'] = 'Sibling.mkv'
    elif change == 'version': case.status['result']['tasks'][0]['version_key'] = '9' * 64
    elif change == 'pending': case.entry['state'] = 'pending'
    def call(method, body, **kwargs):
        if change == 'account': raise RuntimeError('ACCOUNT_CHANGED')
        return case.status if method == 'status' else {'state': 'unavailable'}
    monkeypatch.setattr(preparation_client, 'call', call)
    if change == 'account':
        with pytest.raises(RuntimeError): verify_ready(case.context, lambda: False)
    else:
        assert verify_ready(case.context, lambda: False) is None
