"""Real host queue and existing resolver receipt boundary, without cloud IO."""
from copy import deepcopy
from pathlib import Path
import sys
from threading import Thread, get_ident
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.transport_handoff import VerifiedTransportTarget
from bobbi_core.video_context import video_identity
from bobbi_platform.host import Host
from test_accounts import logged_in


def data(account):
    selected = dict(source_info_hash='a' * 40, torrent_file_id=1,
                    torrent_path='Show.S01E01.mkv', torrent_file_bytes=1000)
    context = video_identity('tmdb:tv:1:s1:e1', 'b' * 64, selected)
    verification = dict(request_id='c' * 32, verification_id='d' * 32, resource_id='resource',
        generation=3, account='legacy-account', media_id=context['media_id'], source_info_hash='a' * 40)
    result = {key: verification[key] for key in ('request_id', 'verification_id', 'resource_id', 'generation', 'account')}
    result.update(state='ready', file_id='file', path='/115open/prepared/Show.S01E01.mkv',
                  bytes=1000, version_key='b' * 64, video_context=context)
    message = dict(operation='transport_capture', request_id='c' * 32,
                   account_scope=account, prepared_verification=verification)
    return message, result


def host(tmp_path, result_state='ready'):
    manager, account = logged_in(tmp_path)
    h = Host(tmp_path, native_rpc=lambda *args: None)
    h.accounts = manager
    message, result = data(account)
    result['state'] = result_state
    calls = []
    h.preparation = SimpleNamespace(request=lambda *args: (calls.append(deepcopy(args)), deepcopy(result))[1])
    h.bind_owner(lambda value: value)
    return h, message, result, calls


def test_capture_revalidates_nonce_then_delivers_private_proof_on_owner_thread(tmp_path):
    h, message, _, calls = host(tmp_path)
    replies, threads = [], []
    def owner(value):
        threads.append(get_ident())
        assert isinstance(value['_verified_transport'], VerifiedTransportTarget)
        assert 'prepared_verification' not in value
        return dict(authorized=True)
    h.bind_owner(owner)
    worker = Thread(target=lambda: replies.append(h.dispatch('playback', message)))
    worker.start()
    until = time.monotonic() + 1
    while h.calls.empty() and time.monotonic() < until:
        time.sleep(.001)
    h.tick()
    worker.join(1)
    assert replies == [dict(authorized=True)] and threads == [get_ident()]
    assert calls == [('resolve', message['prepared_verification'], message['account_scope'])]
    assert '_verified_transport' not in message


@pytest.mark.parametrize('state', ['pending', 'unavailable', 'failed'])
def test_pending_or_failed_cloud_never_queues_native_capture(tmp_path, state):
    h, message, _, calls = host(tmp_path, state)
    assert h.dispatch('playback', message) == dict(authorized=False, state='NOT_READY')
    assert h.calls.empty() and len(calls) == 1


def test_json_ready_flag_cannot_manufacture_host_proof(tmp_path):
    h, message, _, calls = host(tmp_path)
    message['_verified_transport'] = dict(state='ready')
    with pytest.raises(ValueError, match='PRIVATE_TRANSPORT_PROOF_REQUIRED'):
        h.dispatch('playback', message)
    assert not calls and h.calls.empty()


@pytest.mark.parametrize('field,value', [('request_id', 'e' * 32), ('verification_id', 'e' * 32),
    ('resource_id', 'other'), ('account', 'other'), ('generation', 4), ('bytes', 1001), ('version_key', 'f' * 64)])
def test_stale_or_mismatched_actual_resolver_reply_is_rejected(tmp_path, field, value):
    h, message, result, _ = host(tmp_path)
    result[field] = value
    with pytest.raises(ValueError):
        h.dispatch('playback', message)
    assert h.calls.empty()


def test_foreign_request_is_rejected_before_resolver(tmp_path):
    h, message, _, calls = host(tmp_path)
    message['prepared_verification']['request_id'] = 'f' * 32
    with pytest.raises(ValueError, match='TRANSPORT_VERIFICATION_REQUEST'):
        h.dispatch('playback', message)
    assert calls == []


def test_account_change_signal_coalesces_and_precedes_owner_calls(tmp_path):
    h, _, _, _ = host(tmp_path)
    order = []
    h.bind_owner(lambda value: order.append('call'), lambda: order.append('revoke'))
    for _ in range(100):
        h._account_changed({}, {})
    from bobbi_platform.host import _Call
    h.calls.put(_Call({'operation': 'snapshot'}))
    h.tick()
    assert order == ['revoke', 'call'] and not h.account_changes.is_set()


def test_failed_native_revocation_is_retried_not_lost(tmp_path):
    h, _, _, _ = host(tmp_path)
    calls = []
    def revoke():
        calls.append('revoke')
        if len(calls) == 1:
            raise OSError('temporary native read')
    h.bind_owner(lambda value: None, revoke)
    h._account_changed({}, {})
    h.tick()
    assert h.account_changes.is_set()
    h.tick()
    assert calls == ['revoke', 'revoke'] and not h.account_changes.is_set()
