"""Portable proof crosses the real lane/session, never a truthiness shortcut."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_cinema_prepared_index_resolve import prepared, Provider, scoped_body
from bobbi_core import preparation_client
from bobbi_core.capabilities import descriptor
from bobbi_core.prepared_index import document
from bobbi_core.prepared_resolver import PreparedResolver
from bobbi_core.prepared_transport import playback_path
from bobbi_core.resolve_lane import ResolveLane
from bobbi_platform.paths import ProfileBinding
from bobbi_platform.prepared_sessions import PreparedSession


URL = 'http://127.0.0.1:19798/static/file/exact-prepared-file'
ACCOUNT = dict(account_id='115:' + 'a' * 64, epoch=3, authenticated=True)


@pytest.fixture
def flow(prepared):
    queue, resource, root = prepared
    provider = Provider()
    provider.accounts = ['account'] * 10
    addresses = []
    resolver = PreparedResolver(queue, 'account', provider,
        address=lambda p, item: addresses.append(item['file_id']) or URL)
    now = [0.0]
    lane = ResolveLane(resolver, clock=lambda: now[0])
    case = SimpleNamespace(queue=queue, resource=resource, root=root, provider=provider,
        resolver=resolver, lane=lane, now=now, addresses=addresses,
        request=scoped_body(queue, resource))
    try:
        yield case
    finally:
        lane.close()


def finish_io(case, request=None, *, allow_submit=True):
    request = case.request if request is None else request
    assert case.lane.request(request)['state'] == 'pending'
    case.lane.tick()
    proof = case.lane.future.result(timeout=1)
    case.lane.tick(allow_submit=allow_submit)
    return proof, case.lane.records[request['verification_id']]['result']


def test_http_proof_survives_initial_finish_and_every_ready_poll_without_new_io(flow):
    proof, result = finish_io(flow)
    assert proof == {'playback_url': URL}
    assert result['state'] == 'ready' and result['playback_url'] == URL
    for _ in range(3):
        assert flow.lane.request(flow.request) == result
    assert flow.addresses == ['cloud-file']
    assert not flow.queue.ledger.get(flow.resource)['active_lease']
    assert URL not in str(document(flow.queue, 'account'))


@pytest.mark.parametrize('outcome', [True, False])
def test_real_mounted_bool_contract_still_works(flow, outcome):
    flow.resolver.address = None
    if not outcome:
        flow.provider.rows[0]['bytes'] += 1
    proof, result = finish_io(flow)
    assert proof is outcome
    assert result['state'] == ('ready' if outcome else 'unavailable')
    assert 'playback_url' not in result
    assert flow.lane.request(flow.request) == result
    assert flow.addresses == []


@pytest.mark.parametrize('value', [1, 'yes', {'ready': True}, {},
    {'playback_url': URL, 'extra': True}, {'playback_url': None},
    {'playback_url': 'https://example.com/file'},
    {'playback_url': 'http://127.0.0.1:1/file|Authorization=bad'}])
def test_malformed_worker_results_are_rejected_by_real_owner_finish(flow, value):
    # Substitute only the IO reply, retaining the actual lane and resolver plan/finish.
    flow.resolver.perform = lambda plan: value
    _, result = finish_io(flow)
    assert result['state'] == 'unavailable'
    assert flow.lane.request(flow.request)['state'] == 'unavailable'
    assert not flow.queue.ledger.get(flow.resource)['active_lease']


def test_http_dict_is_not_authority_when_transport_has_no_address_adapter(flow):
    flow.resolver.address = None
    flow.resolver.perform = lambda plan: {'playback_url': URL}
    _, result = finish_io(flow)
    assert result['state'] == 'unavailable'


@pytest.mark.parametrize('stage', ['before_io', 'after_address'])
def test_account_drift_rejects_real_http_worker_result(flow, stage):
    flow.provider.accounts = ['other'] if stage == 'before_io' else ['account', 'account', 'other']
    proof, result = finish_io(flow)
    assert proof is False and result['state'] == 'unavailable'
    assert len(flow.addresses) == (0 if stage == 'before_io' else 1)


@pytest.mark.parametrize('at_poll', [False, True])
def test_exact_resource_drift_rejects_late_or_cached_http_proof(flow, at_poll):
    assert flow.lane.request(flow.request)['state'] == 'pending'
    flow.lane.tick()
    assert flow.lane.future.result(timeout=1) == {'playback_url': URL}
    if at_poll:
        flow.lane.tick()
        assert flow.lane.records[flow.request['verification_id']]['result']['playback_url'] == URL
    item = flow.queue.ledger._get(flow.resource)
    item['suppressed'] = True
    flow.queue.ledger._save(item)
    if not at_poll:
        flow.lane.tick()
    assert flow.lane.request(flow.request)['state'] == 'unavailable'
    assert flow.addresses == ['cloud-file']


@pytest.mark.parametrize('reason', ['deadline', 'dependency'])
def test_completed_http_io_cannot_cross_deadline_or_dependency_loss(flow, reason):
    flow.lane.request(flow.request)
    flow.lane.tick()
    assert flow.lane.future.result(timeout=1) == {'playback_url': URL}
    if reason == 'deadline':
        flow.now[0] = 3.0
    flow.lane.tick(allow_submit=reason != 'dependency')
    assert flow.lane.request(flow.request)['state'] == 'unavailable'
    assert not flow.queue.ledger.get(flow.resource)['active_lease']


def session_flow(flow, change=None):
    current, live, cancelled = ['a'], [dict(ACCOUNT)], [False]
    binding = ProfileBinding(lambda addon: flow.root / current[0] / addon)
    root = binding.root('plugin.video.bobbi')
    snapshot = document(flow.queue, 'account')
    entry = snapshot['titles'][0]['sources'][0]
    data = dict(request_id='f' * 32, mode='tv', ids={'tmdb_id': 1},
        tv_data={'season': 1, 'episode': 1}, _account=dict(ACCOUNT))
    calls = []

    def transport(action, envelope, timeout):
        if action == 'account_status':
            return dict(live[0])
        assert action == 'preparation' and envelope['account'] == ACCOUNT
        assert envelope['method'] == 'resolve'
        request = envelope['body']
        calls.append(deepcopy(request))
        result = flow.lane.request(request)
        if result['state'] == 'pending':
            flow.lane.tick()
            flow.lane.future.result(timeout=1)
            flow.lane.tick()
            # Actual service polls re-run owner finish before delivering ready.
            result = flow.lane.request(request)
        assert result['state'] == 'ready' and result['playback_url'] == URL
        if change == 'profile':
            current[0] = 'b'
        elif change == 'account':
            live[0] = dict(ACCOUNT, epoch=4)
        elif change == 'cancel':
            cancelled[0] = True
        return dict(component=descriptor(), **result)

    session = PreparedSession(root, transport, ACCOUNT, binding.is_current)
    return session, data, snapshot, entry, cancelled, calls


def test_real_session_client_lane_resolver_delivers_only_ephemeral_http_url(flow):
    session, data, snapshot, entry, cancelled, calls = session_flow(flow)
    original = deepcopy(snapshot)
    resolved = session.resolve_entry(data, snapshot, entry, lambda: cancelled[0])
    assert resolved is not None
    assert playback_path(snapshot['mount_root'], resolved) == URL
    assert snapshot == original and '_playback_url' not in entry
    assert len(calls) == 1 and flow.addresses == ['cloud-file']


@pytest.mark.parametrize('change', ['profile', 'account', 'cancel'])
def test_ready_http_result_cannot_escape_changed_session_or_cancelled_consumer(flow, change):
    session, data, snapshot, entry, cancelled, calls = session_flow(flow, change)
    if change == 'profile':
        with pytest.raises(RuntimeError, match='REVOKED'):
            session.resolve_entry(data, snapshot, entry, lambda: cancelled[0])
    else:
        assert session.resolve_entry(data, snapshot, entry, lambda: cancelled[0]) is None
    assert len(calls) == 1 and flow.addresses == ['cloud-file']


def test_cancelled_before_admission_does_not_start_http_io(flow):
    session, data, snapshot, entry, cancelled, calls = session_flow(flow)
    cancelled[0] = True
    assert session.resolve_entry(data, snapshot, entry, lambda: cancelled[0]) is None
    assert not calls and not flow.addresses and not flow.lane.records


def test_pending_client_timeout_does_not_consume_or_replay_late_http_proof(flow, monkeypatch):
    snapshot = document(flow.queue, 'account')
    entry = snapshot['titles'][0]['sources'][0]
    data = dict(request_id='f' * 32, mode='tv', ids={'tmdb_id': 1},
        tv_data={'season': 1, 'episode': 1}, _account=dict(ACCOUNT))
    clock, calls = [0.0], []
    monkeypatch.setattr(preparation_client, 'time', SimpleNamespace(
        monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)))

    def transport(action, envelope, timeout):
        assert action == 'preparation'
        calls.append(envelope['body'])
        return dict(component=descriptor(), **flow.lane.request(envelope['body']))

    assert preparation_client.resolve_entry(data, snapshot, entry, budget=.2,
        host_call=transport) is None
    assert len({call['verification_id'] for call in calls}) == 1
    assert flow.lane.future is None and not flow.addresses
    flow.now[0] = 3.0
    flow.lane.tick()
    assert not flow.lane.records and flow.lane.future is None
