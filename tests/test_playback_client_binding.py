"""Real request algorithms and fixed platform bindings, with no device IO."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bobbi_core import playback_ipc, playback_request
from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_platform import paths, runtime


ROOT = Path(__file__).resolve().parents[1]
RID = 'a' * 32
HASH = 'b' * 40
URL = 'http://127.0.0.1:18090/stream?index=1'
FILE = dict(id=1, path='Series.S01E01.mkv', length=1000)


class Native:
    def __init__(self):
        self.epoch, self.current = 0, None
        self.commands = []

    def state(self):
        return dict(protocol=1, selection_epoch=self.epoch, playback=deepcopy(self.current),
                    gui_generation=0, gui_user_intent=0, fullscreen_instance='', windows=[])

    def intent(self, command):
        assert command['expected_epoch'] == self.epoch
        self.epoch += 1
        return dict(reserved=True, selection_epoch=self.epoch)

    def control(self, command):
        self.commands.append(deepcopy(command))
        return {'queued': True, 'command_id': command['command_id']}


class Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert 0 <= seconds <= .05
        self.now += seconds


@pytest.fixture
def actor():
    native = Native()
    authority = PlaybackAuthority(native)
    calls = []
    def call(body, timeout=.3):
        assert 0 < timeout <= .3
        calls.append((deepcopy(body), timeout))
        return authority.dispatch(body)
    client = playback_request.Client(call)
    accepted = client.select(client.read_snapshot(), RID, 'bt:' + HASH)
    return SimpleNamespace(native=native, authority=authority, calls=calls, call=call,
        client=client, context=client.context(accepted, RID),
        identity=client.torrent_file_identity(HASH, FILE['id'], FILE['path'], FILE['length']))


def no_default_transport(*args, **kwargs):
    pytest.fail('A bound operation escaped to the module default transport')


def test_core_import_and_actual_bound_operations_never_discover_platform_or_kodi():
    script = '''
import importlib.abc, sys
class DenyEnvironment(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'bobbi_platform', 'lib', 'xbmc', 'xbmcgui', 'xbmcaddon', 'xbmcvfs'}, fullname
sys.meta_path.insert(0, DenyEnvironment())
sys.path.insert(0, sys.argv[1])
from bobbi_core import playback_request as request, playback_ipc as ipc
calls = []
snapshot = {'boot_id':'b'*32, 'epoch':1, 'desired':{'request_id':'a'*32, 'cancelled':False, 'selection_identity':'bt:'+'c'*40}}
def call(body, timeout=.3):
    calls.append(body['operation'])
    if body['operation'] == 'snapshot': return snapshot
    if body['operation'] == 'bind_file': return {'bound':True}
    if body['operation'] == 'claim_start':
        receipt = {key:body[key] for key in ('boot_id','epoch','request_id','claim_id','route')}
        receipt.update(file_identity=identity, url_sha256=request.digest(url))
        return {'status':'CLAIMED','receipt':receipt}
    raise AssertionError(body)
client = request.Client(call)
identity = client.torrent_file_identity('c'*40,1,'movie.mkv',100)
url = 'http://127.0.0.1:18090/movie'
assert client.owned_state('a'*32) == snapshot
assert client.bind_and_claim('a'*32,identity,url,lambda:False,'resolved_url')['file_identity'] == identity
assert calls == ['snapshot','snapshot','bind_file','claim_start']
for operation in (lambda: ipc.call({'operation':'snapshot'}), request.read_snapshot):
    try: operation()
    except OSError: pass
    else: raise AssertionError('Missing explicit transport discovered an environment')
assert client.digest is request.digest
assert client.context is request.context
assert client.torrent_file_identity is request.torrent_file_identity
'''
    result = subprocess.run([sys.executable, '-I', '-c', script,
        str(ROOT / 'addons/script.module.bobbi.core/lib')], text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('use_module', [False, True], ids=['bound-client', 'explicit-module-callback'])
def test_real_claim_algorithm_keeps_exact_receipt_and_all_nested_reads_bound(actor, monkeypatch, use_module):
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    actor.calls.clear()
    kwargs = {'owner_call': actor.call} if use_module else {}
    protocol = playback_request if use_module else actor.client
    resolution = protocol.resolve_torrent(RID, 'magnet:?xt=urn:btih:' + HASH, HASH, HASH, **kwargs)
    identity = protocol.resolved_torrent_file_identity(RID, resolution, HASH,
        FILE['id'], FILE['path'], FILE['length'], **kwargs)
    assert protocol.validate_torrent_resolution(RID, resolution, HASH, **kwargs) == 'bt:' + HASH
    result = protocol.bind_and_claim(RID, identity, URL, lambda: False, 'resolved_url', **kwargs)
    assert result == dict(actor.context, file_identity=identity)
    claims = [body for body, _ in actor.calls if body['operation'] == 'claim_start']
    assert len(claims) == 1
    assert actor.authority.start_receipt == dict(result, claim_id=claims[0]['claim_id'],
                                                route='resolved_url', url_sha256=protocol.digest(URL))
    assert actor.native.commands == []


def test_reserve_ui_entry_uses_same_client_for_snapshot_and_select(actor, monkeypatch):
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    actor.calls.clear()
    result = actor.client.reserve_ui_entry(dict(selection_policy='exact', info_hash=HASH,
        url='magnet:?xt=urn:btih:' + HASH, _parent_request_id='old', _continuation_token='old'))
    assert [body['operation'] for body, _ in actor.calls] == ['snapshot', 'select']
    assert result['request_id'] != RID
    assert result['_selection_context']['request_id'] == result['request_id']
    assert '_parent_request_id' not in result and '_continuation_token' not in result


def test_read_retries_only_the_same_injected_callback(actor, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(playback_request, 'time', clock)
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    attempts = []
    def call(body, timeout=.3):
        attempts.append(deepcopy(body))
        if len(attempts) < 3:
            raise OSError('temporary observation loss')
        return actor.call(body, timeout)
    client = playback_request.Client(call)
    assert client.owned_state(RID)['desired']['request_id'] == RID
    assert attempts == [{'operation': 'snapshot'}] * 3
    assert actor.native.commands == []


def test_falsey_callable_is_still_an_explicit_binding(actor, monkeypatch):
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    class FalseyCall:
        def __bool__(self):
            return False
        def __call__(self, body, timeout=.3):
            return actor.call(body, timeout)
    client = playback_request.Client(FalseyCall())
    assert client.owned_state(RID)['desired']['request_id'] == RID
    assert client.bind_and_claim(RID, actor.identity, URL, lambda: False, 'resolved_url') == dict(
        actor.context, file_identity=actor.identity)


@pytest.mark.parametrize('result', ['confirmed', 'not_received', 'wrong_file', 'consumed', 'cancelled', 'manual'])
def test_only_internal_eof_can_reconcile_original_claim_after_its_admission_deadline(actor, monkeypatch, result):
    clock, journal = Clock(), []
    monkeypatch.setattr(playback_request, 'time', clock)
    def call(body, timeout=.3):
        journal.append(deepcopy(body))
        if body['operation'] == 'claim_start':
            actor.call(body, timeout)
            clock.now += .4
            raise TimeoutError('original admission lost its response')
        if body['operation'] == 'claim_status':
            if result in ('not_received', 'consumed'):
                return {'status': result.upper()}
            v = actor.call(body, timeout)
            if result == 'wrong_file':
                v['receipt']['file_identity'] = 'different'
            return v
        return actor.call(body, timeout)
    run = lambda: playback_request.Client(call).bind_and_claim(RID, actor.identity, URL,
        lambda: result == 'cancelled' and clock.now > 100., 'player_play', budget=.4,
        reconcile_eof_claim=result != 'manual')
    if result == 'confirmed':
        assert run()['file_identity'] == actor.identity
    else:
        with pytest.raises(TimeoutError):
            run()
    claims = [v for v in journal if v['operation'] == 'claim_start']
    reads = [v for v in journal if v['operation'] == 'claim_status']
    assert len(claims) == 1 and len(reads) == (0 if result in ('cancelled','manual') else 1)
    assert all(v['claim_id'] == claims[0]['claim_id'] for v in reads)
    assert actor.native.commands == []


@pytest.mark.parametrize('result', ['confirmed', 'unknown', 'explicit_unknown', 'wrong_receipt'])
def test_lost_claim_reply_uses_claim_status_without_reissuing_unknown_claim(actor, monkeypatch, result):
    monkeypatch.setattr(playback_request, 'time', Clock())
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    calls = []
    def call(body, timeout=.3):
        calls.append(deepcopy(body))
        if body['operation'] == 'claim_start':
            actor.call(body, timeout)
            raise OSError('accepted command, lost response')
        if body['operation'] == 'claim_status' and result == 'unknown':
            raise OSError('receipt still unavailable')
        if body['operation'] == 'claim_status' and result == 'explicit_unknown':
            return {'status': 'UNKNOWN'}
        reply = actor.call(body, timeout)
        if body['operation'] == 'claim_status' and result == 'wrong_receipt':
            reply['receipt']['claim_id'] = 'f' * 32
        return reply
    client = playback_request.Client(call)
    if result == 'confirmed':
        assert client.bind_and_claim(RID, actor.identity, URL, lambda: False, 'resolved_url',
            budget=.4) == dict(actor.context, file_identity=actor.identity)
    else:
        with pytest.raises((OSError, RuntimeError)):
            client.bind_and_claim(RID, actor.identity, URL, lambda: False, 'resolved_url', budget=.4)
    mutations = [body for body in calls if body['operation'] == 'claim_start']
    receipts = [body for body in calls if body['operation'] == 'claim_status']
    assert len(mutations) == 1 and receipts
    assert all(body['claim_id'] == mutations[0]['claim_id'] for body in receipts)
    assert actor.native.commands == []


def test_only_not_received_receipt_allows_resubmission_of_same_claim_identity(actor, monkeypatch):
    monkeypatch.setattr(playback_request, 'time', Clock())
    calls = []
    def call(body, timeout=.3):
        calls.append(deepcopy(body))
        if body['operation'] == 'claim_start' and sum(value['operation'] == 'claim_start' for value in calls) == 1:
            raise OSError('never reached owner')
        return actor.call(body, timeout)
    result = playback_request.Client(call).bind_and_claim(
        RID, actor.identity, URL, lambda: False, 'resolved_url')
    assert result == dict(actor.context, file_identity=actor.identity)
    assert [value['operation'] for value in calls] == [
        'snapshot', 'bind_file', 'claim_start', 'claim_status', 'claim_start']
    assert calls[2] == calls[4]
    assert calls[3]['claim_id'] == calls[2]['claim_id']


@pytest.mark.parametrize('field', ['boot_id', 'epoch', 'request_id', 'claim_id', 'route', 'file_identity', 'url_sha256'])
def test_claimed_receipt_cannot_retarget_any_scope_field(actor, field):
    def call(body, timeout=.3):
        result = actor.call(body, timeout)
        if body['operation'] == 'claim_start':
            result['receipt'][field] = 99 if field == 'epoch' else 'different'
        return result
    actor.calls.clear()
    with pytest.raises(RuntimeError):
        playback_request.Client(call).bind_and_claim(RID, actor.identity, URL, lambda: False, 'resolved_url')
    assert [body['operation'] for body, _ in actor.calls] == ['snapshot', 'bind_file', 'claim_start']
    assert actor.native.commands == []


@pytest.mark.parametrize('late_stage', ['snapshot', 'bind_file', 'claim_start', 'claim_status'])
def test_late_success_never_escapes_or_resets_the_original_claim_deadline(actor, monkeypatch, late_stage):
    clock = Clock()
    monkeypatch.setattr(playback_request, 'time', clock)
    deadline = clock.now + .5
    calls = []
    def call(body, timeout=.3):
        assert 0 < timeout <= min(.3, deadline - clock.now)
        calls.append(body['operation'])
        result = actor.call(body, timeout)
        if body['operation'] == 'claim_start' and late_stage == 'claim_status':
            raise OSError('accepted command, lost reply')
        if body['operation'] == late_stage:
            clock.now += .51
        return result
    with pytest.raises(TimeoutError):
        playback_request.Client(call).bind_and_claim(
            RID, actor.identity, URL, lambda: False, 'resolved_url', budget=.5)
    assert calls[-1] == late_stage
    assert calls.count('claim_start') <= 1
    assert 'cancel' not in calls
    assert actor.native.commands == []


def test_cancel_callback_is_live_and_cannot_mint_start_after_binding(actor):
    cancelled = [False]
    def call(body, timeout=.3):
        result = actor.call(body, timeout)
        if body['operation'] == 'bind_file':
            cancelled[0] = True
        return result
    actor.calls.clear()
    with pytest.raises(RuntimeError):
        playback_request.Client(call).bind_and_claim(RID, actor.identity, URL,
            lambda: cancelled[0], 'resolved_url')
    operations = [body['operation'] for body, _ in actor.calls]
    assert operations == ['snapshot', 'bind_file', 'cancel']
    assert actor.authority.owner.desired['cancelled']
    assert actor.native.commands == []


def test_monitor_failure_and_terminal_queries_use_the_bound_client(actor, monkeypatch):
    monkeypatch.setattr(playback_request, 'call', no_default_transport)
    context = actor.client.bind_and_claim(RID, actor.identity, URL, lambda: False, 'resolved_url')
    instance = str(uuid4())
    actor.native.current = dict(protocol=1, native_instance=instance, request_id=RID,
        file_identity=actor.identity, url_sha256=actor.client.digest(URL), phase='AV_STARTED',
        sequence=1, user_intent=0, paused=False, subtitle_intent=0, subtitle_auto_intent=0)
    assert actor.client.monitor_state(context, instance, timeout=.1) == 'ACTIVE'
    assert actor.client.startup_failure(context) is None
    actor.native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    assert actor.client.monitor_state(context, instance) == 'TERMINAL'
    assert actor.client.terminal_state(context, instance) == {'reason': 'NATURAL_EOF'}


def test_explicit_ipc_host_callback_keeps_wire_action_and_timeout():
    calls = []
    def host(action, body, timeout):
        calls.append((action, body, timeout))
        return {'observed': True}
    body = {'operation': 'snapshot'}
    assert playback_ipc.call(body, timeout=.125, host_call=host) == {'observed': True}
    assert calls == [('playback', body, .125)]


def capture(binding):
    from bobbi_platform.playback_client import capture as platform_capture
    return platform_capture(binding=binding)


def test_platform_capture_and_plain_torrent_claim_need_no_prepared_session_or_account(actor, tmp_path, monkeypatch):
    from bobbi_platform import prepared_sessions
    monkeypatch.setattr(prepared_sessions, 'capture', lambda *args, **kwargs: None)
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    bindings, actions = [], []
    def bind(path):
        bindings.append(path)
        def host(action, body, timeout):
            actions.append(action)
            assert action == 'playback'
            return actor.call(body, timeout)
        return host
    monkeypatch.setattr(runtime, 'bind_call', bind)
    client = capture(binding)
    assert bindings == [binding.root() / 'runtime.json'] and actions == []
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi.torrent/lib'))
    from bobbi_torrent.owner import Owner
    window = SimpleNamespace(getProperty=lambda key: RID if key == 'bobbi_active_player_session' else '')
    owner = Owner(RID, protocol=client, window=window, monitor=SimpleNamespace(abortRequested=lambda: False))
    assert owner.prepared_session is None
    resolution = client.resolve_torrent(RID, 'magnet:?xt=urn:btih:' + HASH, HASH, HASH)
    properties = {}
    context = owner.bind(SimpleNamespace(setProperty=lambda key, value: properties.__setitem__(key, value)),
        HASH, FILE, URL, resolution)
    assert context['file_identity'] == actor.identity
    assert properties['bobitv.request_id'] == RID
    assert len(bindings) == 1 and set(actions) == {'playback'}


def test_platform_bound_callback_keeps_timeout_and_checks_profile_before_and_after(tmp_path, monkeypatch):
    events = []
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    original = binding.require_current
    def current():
        events.append('profile')
        original()
    monkeypatch.setattr(binding, 'require_current', current)
    def bind(path):
        def host(action, body, timeout):
            assert 0 < timeout <= .125
            events.append('wire')
            return {'ok': True}
        return host
    monkeypatch.setattr(runtime, 'bind_call', bind)
    client = capture(binding)
    events.clear()
    assert client.call({'operation': 'snapshot'}, timeout=.125) == {'ok': True}
    assert events == ['profile', 'wire', 'profile']


@pytest.mark.parametrize('timeout', [0, -1, .301, True, None, float('nan'), float('inf')])
def test_platform_bound_callback_rejects_invalid_timeout_before_io(tmp_path, monkeypatch, timeout):
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    calls = []
    monkeypatch.setattr(runtime, 'bind_call', lambda _: lambda *args, **kwargs: calls.append(args))
    client = capture(binding)
    with pytest.raises(ValueError):
        client.call({'operation': 'snapshot'}, timeout=timeout)
    assert calls == []


def test_failed_capture_cannot_adopt_a_host_that_appears_later(tmp_path, monkeypatch):
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    attempts = []
    def offline(path):
        attempts.append(path)
        raise OSError('not ready')
    monkeypatch.setattr(runtime, 'bind_call', offline)
    client = capture(binding)
    monkeypatch.setattr(runtime, 'bind_call', lambda path: pytest.fail('Old client captured a replacement'))
    for _ in range(2):
        with pytest.raises(OSError):
            client.call({'operation': 'snapshot'})
    assert attempts == [binding.root() / 'runtime.json']
    assert client.digest('pure helper') == playback_request.digest('pure helper')


def test_capture_timeout_budget_is_spent_before_wire_and_not_restarted(tmp_path, monkeypatch):
    from bobbi_platform import playback_client
    clock = Clock()
    monkeypatch.setattr(playback_client, 'time', clock)
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    calls = []
    monkeypatch.setattr(runtime, 'bind_call', lambda _: lambda *args, **kwargs: calls.append(args))
    client = capture(binding)
    original = binding.require_current
    def slow_check():
        original()
        clock.now += .4
    monkeypatch.setattr(binding, 'require_current', slow_check)
    with pytest.raises(TimeoutError):
        client.call({'operation': 'snapshot'}, timeout=.3)
    assert calls == []


def test_transient_read_error_retries_original_binding_without_recapture(tmp_path, monkeypatch):
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    binds, calls = [], []
    def bind(path):
        binds.append(path)
        def host(action, body, timeout):
            calls.append((action, deepcopy(body)))
            if len(calls) == 1:
                raise OSError('temporary observation timeout')
            return {'same_host': True}
        return host
    monkeypatch.setattr(runtime, 'bind_call', bind)
    client = capture(binding)
    assert client.read_snapshot() == {'same_host': True}
    assert len(binds) == 1
    assert calls == [('playback', {'operation': 'snapshot'})] * 2


def test_real_runtime_profile_a_b_a_never_retargets_or_revives_old_client(tmp_path, monkeypatch):
    current, first_calls, second_calls = ['A'], [], []
    binding = paths.ProfileBinding(lambda addon: tmp_path / current[0] / addon)
    first = runtime.Runtime(lambda action, body: first_calls.append(action) or {'host': 'A'},
                            tmp_path / 'A/script.module.bobbi.platform/runtime.json')
    second = runtime.Runtime(lambda action, body: second_calls.append(action) or {'host': 'B'},
                             tmp_path / 'B/script.module.bobbi.platform/runtime.json')
    first.start()
    second.start()
    try:
        client = capture(binding)
        monkeypatch.setattr(runtime, 'profile', lambda **kwargs: second.path)
        assert client.call({'operation': 'snapshot'}) == {'host': 'A'}
        current[0] = 'B'
        with pytest.raises((OSError, ValueError, RuntimeError)):
            client.call({'operation': 'snapshot'})
        current[0] = 'A'
        with pytest.raises((OSError, ValueError, RuntimeError)):
            client.call({'operation': 'snapshot'})
        assert first_calls == ['playback'] and second_calls == []
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('change', ['token', 'remove', 'invalid'])
def test_real_runtime_registration_change_permanently_revokes_client(tmp_path, change):
    binding = paths.ProfileBinding(lambda addon: tmp_path / addon)
    calls = []
    server = runtime.Runtime(lambda action, body: calls.append(action) or {}, binding.root() / 'runtime.json')
    server.start()
    try:
        client = capture(binding)
        original = server.path.read_bytes()
        if change == 'remove':
            server.path.unlink()
        else:
            server.path.write_text(json.dumps({'port': server.server.server_port, 'token': 'f' * 64})
                                   if change == 'token' else '{}', encoding='utf-8')
        with pytest.raises(OSError):
            client.call({'operation': 'snapshot'})
        server.path.write_bytes(original)
        with pytest.raises(OSError):
            client.call({'operation': 'snapshot'})
        assert calls == []
    finally:
        server.close()


@pytest.mark.parametrize('change', ['profile', 'token'])
def test_inflight_binding_change_discards_reply_and_cannot_revive(tmp_path, change):
    current, calls = ['A'], []
    binding = paths.ProfileBinding(lambda addon: tmp_path / current[0] / addon)
    def dispatch(action, body):
        calls.append(action)
        if change == 'profile':
            current[0] = 'B'
        else:
            server.path.write_text(json.dumps({'port': server.server.server_port, 'token': 'e' * 64}),
                                   encoding='utf-8')
        return {'must_not_escape': True}
    server = runtime.Runtime(dispatch, binding.root() / 'runtime.json')
    server.start()
    try:
        original = server.path.read_bytes()
        client = capture(binding)
        with pytest.raises((OSError, ValueError, RuntimeError)):
            client.call({'operation': 'snapshot'})
        current[0] = 'A'
        server.path.write_bytes(original)
        with pytest.raises((OSError, ValueError, RuntimeError)):
            client.call({'operation': 'snapshot'})
        assert calls == ['playback']
    finally:
        server.close()
