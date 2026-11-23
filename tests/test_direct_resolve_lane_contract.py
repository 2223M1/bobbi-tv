"""Real direct queue/IO/resolver/lane; catalogue and provider IO are doubled.

The fixture supplies previously qualified evidence through DirectQueue.complete.
It does not claim to exercise cloud qualification, CDN bytes or Host/profile
fences. Cancellation here is the DirectIO lifetime guard, not player authority.
"""
from concurrent.futures import wait
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from bobbi_core import direct_cloud, direct_cloud_io
from bobbi_core.direct_cloud import DirectQueue, DirectResolver, MOUNT
from bobbi_core.direct_cloud_io import DirectIO
from bobbi_core.resolve_lane import ResolveLane


URL = 'http://127.0.0.1:19798/static/file/same-file'


@pytest.fixture
def direct_case(tmp_path, monkeypatch):
    state = SimpleNamespace(now=0.0, account='fixture-account', cancelled=False,
                            provider_reads=[], closed=[], addresses=[], on_address=None)
    body = dict(request_id='a' * 32,
        source=dict(provider='mdsub', guid='mdsub:' + 'b' * 64,
                    locator='https://pan.mdsub.top/api/raw?fixture=same-file',
                    title='same-file.mkv', size=32768),
        media=dict(tmdb_id=1, kind='movie', season=0, episode=0))
    destination = '/115open/fixture'
    item = dict(file_id='cloud-file', path=destination + '/same-file.mkv',
                name='same-file.mkv', bytes=32768, hashes={'sha1': 'c' * 40})
    state.rows = [dict(item, directory=False, forbidden=False)]

    class Provider:
        def __init__(self):
            self.session = SimpleNamespace(close=lambda: state.closed.append(self))

        def account_scope(self):
            return state.account

        def identified_files(self, path):
            state.provider_reads.append(path)
            return deepcopy(state.rows)

    def address(provider, selected):
        state.addresses.append(deepcopy(selected))
        if state.on_address:
            return state.on_address()
        return URL

    # This is the reviewed catalogue boundary; real source shape validation
    # remains active. No catalogue download or cloud preparation is performed.
    monkeypatch.setattr(direct_cloud_io, 'validate_catalog',
                        lambda value: direct_cloud.checked(value)[0])
    io = DirectIO(Provider(), Provider, None, lambda: state.cancelled, address=address)
    queue = DirectQueue(tmp_path / 'direct.sqlite', tmp_path / 'direct.json',
                        state.account, destination, io, clock=lambda: state.now)
    accepted = queue.accept(body)
    action = queue.next_action()
    assert action['kind'] == 'inspect'
    evidence = dict(file=item, proof='d' * 64,
                    video=dict(duration=900, codec='h264', width=1920, height=1080))
    assert queue.complete(action, dict(ok=True, result=dict(state='ready', evidence=evidence)))
    resolver = DirectResolver(queue, io)
    lane = ResolveLane(resolver, clock=lambda: state.now)
    state.queue, state.io, state.resolver, state.lane = queue, io, resolver, lane
    state.body = dict(key=accepted['key'], request_id=body['request_id'], verification_id='e' * 32)
    state.item, state.evidence = item, evidence
    try:
        yield state
    finally:
        lane.close()
        queue.close()


def start_io(case):
    assert case.lane.request(case.body)['state'] == 'pending'
    case.lane.tick()
    assert case.lane.future is not None
    # Wait for the actual executor without retrieving/transforming its proof.
    done, pending = wait([case.lane.future], timeout=2)
    assert done and not pending, 'Local fake provider must finish promptly'


def complete(case, *, allow_submit=True):
    start_io(case)
    case.lane.tick(allow_submit=allow_submit)
    return case.lane.request(case.body)


def test_http_proof_survives_first_completion_and_repeated_owner_revalidation(direct_case):
    case = direct_case
    start_io(case)
    case.lane.tick()
    # Assert both internal completion and the public poll. A fix to only one
    # of the two old bool conversions cannot pass this regression.
    first = case.lane.records[case.body['verification_id']]['result']
    assert first['state'] == 'ready' and first['playback_url'] == URL
    for _ in range(3):
        result = case.lane.request(case.body)
        assert result['state'] == 'ready' and result['playback_url'] == URL
        assert all(result[key] == value for key, value in case.body.items())
        assert result['proof'] == case.evidence['proof']
    assert case.provider_reads == ['/115open/fixture'] and len(case.addresses) == 1
    assert len(case.closed) == 1
    assert URL not in case.queue.snapshot.read_text(encoding='utf-8')
    assert URL not in case.queue.db.execute('SELECT evidence FROM direct_jobs').fetchone()[0]


def test_mount_true_proof_retains_ordinary_path_without_http_address(direct_case):
    case = direct_case
    case.io.address = None
    result = complete(case)
    for _ in range(3):
        assert result['state'] == 'ready' and result['path'] == MOUNT + case.item['path']
        assert 'playback_url' not in result
        result = case.lane.request(case.body)
    assert len(case.closed) == 1 and not case.addresses


def test_real_io_false_for_missing_file_cannot_become_ready(direct_case):
    case = direct_case
    case.rows = []
    assert complete(case) == {'state': 'unavailable'}
    assert len(case.closed) == 1 and not case.addresses


@pytest.mark.parametrize('proof', [
    False, None, 1, 'verified', [True], {}, {'ok': True},
    {'playback_url': URL, 'extra': True}, {'playback_url': 123},
])
def test_real_resolver_rejects_non_contract_truthy_proof(direct_case, proof):
    # Deliberately inject at the real resolver's evidence boundary. DirectIO
    # itself cannot naturally produce these malformed envelopes; no resolver
    # or lane implementation is replaced to manufacture a green integration.
    case = direct_case
    plan = case.resolver.plan(case.body)
    if proof == {'playback_url': 123}:
        with pytest.raises(ValueError, match='PREPARED_PLAYBACK_ADDRESS'):
            case.resolver.finish(plan, proof)
    else:
        assert case.resolver.finish(plan, proof) == {'state': 'unavailable'}


@pytest.mark.parametrize('address', [False, 1, {}, 'https://example.invalid/file',
                                    'http://127.0.0.1:19798/file|Authorization=bad'])
def test_real_io_malformed_portable_url_never_survives_lane(direct_case, address):
    case = direct_case
    case.on_address = lambda: address
    result = complete(case)
    assert result['state'] == 'unavailable' and 'playback_url' not in result
    assert len(case.closed) == 1 and len(case.addresses) == 1


def test_cloud_file_drift_during_real_verification_never_requests_address(direct_case):
    case = direct_case
    case.rows[0]['bytes'] += 1
    assert complete(case) == {'state': 'unavailable'}
    assert len(case.closed) == 1 and not case.addresses


@pytest.mark.parametrize('change', ['file', 'proof', 'state', 'account'])
def test_repeated_poll_revalidates_live_queue_instead_of_returning_cached_url(direct_case, change):
    case = direct_case
    assert complete(case)['state'] == 'ready'
    if change in ('file', 'proof'):
        evidence = deepcopy(case.evidence)
        if change == 'file':
            evidence['file']['file_id'] = 'replacement-file'
        else:
            evidence['proof'] = 'f' * 64
        case.queue.db.execute('UPDATE direct_jobs SET evidence=? WHERE key=?',
                              (json.dumps(evidence), case.body['key']))
    else:
        case.queue.db.execute('UPDATE direct_jobs SET ' + change + '=? WHERE key=?',
                              ('failed' if change == 'state' else 'replacement-account', case.body['key']))
    case.queue.db.commit()
    result = case.lane.request(case.body)
    assert result['state'] == 'unavailable' and 'playback_url' not in result
    assert len(case.provider_reads) == len(case.addresses) == len(case.closed) == 1


@pytest.mark.parametrize('change', ['cancelled', 'account'])
def test_real_io_rechecks_lifetime_after_address_before_returning_proof(direct_case, change):
    case = direct_case
    def revoke():
        if change == 'cancelled':
            case.cancelled = True
        else:
            case.account = 'replacement-account'
        return URL
    case.on_address = revoke
    assert complete(case) == {'state': 'unavailable'}
    assert len(case.closed) == len(case.addresses) == 1


def test_cancelled_io_does_not_read_file_or_request_address(direct_case):
    case = direct_case
    case.cancelled = True
    assert complete(case) == {'state': 'unavailable'}
    assert len(case.closed) == 1 and not case.provider_reads and not case.addresses


@pytest.mark.parametrize('boundary', ['expired', 'dependency_lost'])
def test_valid_http_proof_is_discarded_when_completion_permission_is_lost(direct_case, boundary):
    case = direct_case
    start_io(case)
    if boundary == 'expired':
        case.now = 3.0  # Original queue/IO deadline, not a fresh completion budget.
    case.lane.tick(allow_submit=boundary != 'dependency_lost')
    result = case.lane.request(case.body)
    assert result['state'] == 'unavailable' and 'playback_url' not in result
    assert len(case.closed) == len(case.addresses) == 1


def test_completed_proof_expiry_requires_new_io_without_reusing_old_url(direct_case):
    case = direct_case
    case.on_address = lambda: URL + '-' + str(len(case.addresses))
    first = complete(case)
    assert first['state'] == 'ready' and first['playback_url'] == URL + '-1'
    case.now = 2.1  # Original completed-receipt window remains two seconds.
    second = complete(case)
    assert second['state'] == 'ready' and second['playback_url'] == URL + '-2'
    assert len(case.provider_reads) == len(case.addresses) == len(case.closed) == 2
