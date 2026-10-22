"""Local-only route checks; these do not certify in-process sampling liveness."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace

import pytest

from test_ce_115_direct_start import FakeRuntime, REQUEST, INSTANCE, kodi, driver, shared

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.catalog/lib'))
from bobbi_platform import runtime as host
from bobbi_catalog.api import ShareError

ADDRESS = 'http://127.0.0.1:33777/stream/' + 'a' * 32 + '/video.mkv'


@pytest.fixture
def share(monkeypatch):
    runtime = FakeRuntime()
    runtime.resolve = lambda *args: pytest.fail('Sharestream must not ask for a direct CDN grant')
    runtime.resolve_sharestream = MethodType(kodi.Runtime.resolve_sharestream, runtime)
    state = SimpleNamespace(runtime=runtime, calls=[], actions=[], address=ADDRESS, after=None, change={})
    def call(action, body, **kwargs):
        assert action in ('share_open','share_open_diagnostic') and 0 < kwargs['timeout'] <= .3
        state.actions.append(action)
        state.calls.append(deepcopy(body))
        if state.after: state.after()
        return dict(dict(state='ready', request_id=body['request_id'], guid=body['guid'], media=body['media'],
                         bytes=body['size'], url=state.address), **state.change)
    monkeypatch.setattr(host, 'call', call)
    return state


def perform(state, route='sharestream'):
    record = dict(request_id=REQUEST, route=route)
    kodi.perform_start(state.runtime, state.runtime.proof, {'selection_identity': 'transport:' + 'a' * 64}, record)
    return record


def test_real_stream_resolver_receives_only_the_retained_tuple_and_frozen_account(share):
    record = perform(share)
    assert len(share.calls) == 1
    assert share.actions == ['share_open'] and 'diagnostic' not in share.calls[0]
    body, row = share.calls[0], share.runtime.row
    assert {key: body[key] for key in ('locator', 'guid', 'title', 'size', 'media', 'account')} == dict(
        locator=row['locator'], guid=row['guid'], title=row['name'], size=row['size'], media=row['media'], account=share.runtime.scope)
    opens = [call for call in share.runtime.calls if isinstance(call, tuple)]
    assert len(opens) == 1 and opens[0][1] == ADDRESS
    assert record['tool_revision'] == 8 and record['route'] == 'sharestream'
    assert record['grant_timing'] == 'first_stream_get' and record['original_pipe_preserved'] is None
    assert 'ua_sha256' not in record and ADDRESS not in json.dumps(share.runtime.saved)


@pytest.mark.parametrize('route,mode',[('sharestream-open-range','open_range'),
    ('sharestream-open-range-microbatch','open_range_microbatch'),
    ('sharestream-open-range-bound-guard','open_range_bound_guard'),
    ('sharestream-block-startup-1m','block_startup_1m')])
def test_diagnostic_route_is_explicit_short_lived_and_uses_the_same_resident_resolver(share,route,mode):
    record=perform(share,route)
    assert share.actions==['share_open_diagnostic']
    assert share.calls[0]['diagnostic']=={'mode':mode,'seconds':60}
    assert record['tool_revision']==8 and record['transport_diagnostic']==share.calls[0]['diagnostic']
    assert record['route']==route
    assert len([call for call in share.runtime.calls if isinstance(call,tuple)])==1


@pytest.mark.parametrize('address', [
    'https://127.0.0.1:33777/stream/' + 'a' * 32 + '/video.mkv',
    ADDRESS.replace('127.0.0.1', 'localhost'), ADDRESS.replace('127.0.0.1', '192.0.2.1'),
    ADDRESS.replace('127.0.0.1', 'user:secret@127.0.0.1'), ADDRESS + '?token=secret', ADDRESS + '#secret',
    ADDRESS.replace('/stream/', '/other/'), ADDRESS.replace('/' + 'a' * 32 + '/', '/bad/'),
    ADDRESS + '|User-Agent=secret', 'https://cdn.example/video.mkv'])
def test_existing_stream_validation_rejects_wrong_loopback_before_admission(share, address):
    share.address = address
    with pytest.raises(ShareError): perform(share)
    assert 'select' not in share.runtime.calls and not any(isinstance(call, tuple) for call in share.runtime.calls)


@pytest.mark.parametrize('field,value', [('guid', 'other'), ('media', 'other'), ('bytes', 56), ('request_id', 'f' * 32)])
def test_registration_for_another_tuple_or_request_is_not_a_playable_result(share, field, value):
    share.change[field] = value
    with pytest.raises(ShareError): perform(share)
    assert 'select' not in share.runtime.calls


@pytest.mark.parametrize('signal', ['account', 'abort'])
def test_account_or_cancel_during_registration_wins_before_select(share, signal):
    share.after = (lambda: share.runtime.scope.update(epoch=4)) if signal == 'account' else (
        lambda: setattr(share.runtime, 'aborted', True))
    with pytest.raises(shared.DiagnosticError): perform(share)
    assert 'select' not in share.runtime.calls


def test_changed_retained_file_never_calls_sharestream(share):
    share.runtime.row['fid'] = 'other'
    with pytest.raises(shared.DiagnosticError, match='INSPECT_CHANGED'): perform(share)
    assert share.calls == []


def test_sharestream_open_timeout_is_not_replayed(share):
    share.runtime.open_timeout = True
    with pytest.raises(TimeoutError): perform(share)
    assert len([call for call in share.runtime.calls if isinstance(call, tuple)]) == 1
    assert share.runtime.saved[-1]['state'] == 'open_unconfirmed'


def test_resolve_to_observed_av_includes_pre_play_time_for_both_routes(monkeypatch):
    monkeypatch.setattr(kodi.time, 'monotonic', lambda: 120.0)
    monkeypatch.setattr(kodi, 'Path', lambda path: SimpleNamespace(read_text=lambda: ''))
    row = dict(request_id=REQUEST, native_instance=INSTANCE, file_identity='identity', phase='AV_STARTED')
    view = ({'boot_id': 'boot', 'epoch': 2, 'desired': {'request_id': REQUEST, 'cancelled': False}},
            {'playback': row}, [{'playerid': 1}])
    def rpc(method, params):
        if method == 'Player.GetProperties':
            stamp = {'hours': 0, 'minutes': 0, 'seconds': 1, 'milliseconds': 0}
            return dict(time=stamp, totaltime=stamp, speed=1)
        if method == 'XBMC.GetInfoBooleans': return {'Player.Caching': False}
        return {}
    runtime = SimpleNamespace(view=lambda: deepcopy(view), rpc=rpc)
    for route in ('direct', 'sharestream'):
        record = dict(request_id=REQUEST, file_identity='identity', route=route,
            owner_context={'boot_id': 'boot', 'epoch': 2}, resolve_began=100., play_issued_at=110.)
        kodi.Runtime.sample(runtime, record)
        assert record['resolve_to_av_observed_seconds'] == 20
        assert record['play_to_av_observed_seconds'] == 10
        assert 'click_to_av_seconds' not in record


@pytest.mark.parametrize('route', ['sharestream','sharestream-open-range','sharestream-open-range-microbatch',
                                  'sharestream-open-range-bound-guard','sharestream-block-startup-1m'])
def test_route_is_pinned_in_new_receipts_and_cannot_change_at_collection(tmp_path,route):
    params = dict(run_id='a' * 32, request_id=REQUEST, inspection={}, target={}, duration=45, route=route)
    sent = []
    def sender(source, code): sent.append(code); raise TimeoutError('private')
    receipt = driver.run_once(tmp_path, tmp_path/'receipt.json', params, sender)
    assert receipt['route'] == route and receipt['tool_revision'] == 8 and len(sent) == 1
    compile(sent[0], 'route-launch', 'exec')
    result = dict(run_id=params['run_id'], request_id=REQUEST, route='direct', diagnostic_only=True, product_proof=False)
    raw = json.dumps(result).encode()
    descriptor = dict(artifact='/tmp/bobbi-115-direct-' + params['run_id'] + '/result.json',
                      bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(shared.DiagnosticError): driver.decode_result(raw, descriptor, receipt)
