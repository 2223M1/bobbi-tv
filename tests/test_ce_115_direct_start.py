"""No device calls: single-opener, existing authority and exact-stop boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ce_115_direct_remote as shared
import ce_115_direct_kodi as kodi
import ce_115_direct_start as driver


def test_error_locations_do_not_emit_exception_text_or_source():
    try:
        raise OSError('https://private.invalid/?token=private-secret')
    except OSError as error:
        value = kodi.error_location(error)
    assert value['error_type'] == 'OSError'
    assert value['error_frames'][-1]['function'] == 'test_error_locations_do_not_emit_exception_text_or_source'
    assert set(value['error_frames'][-1]) == {'file', 'function', 'line'}
    assert 'private-secret' not in json.dumps(value)
    assert 'https://' not in json.dumps(value)


def test_scoped_select_uses_existing_wire_with_old_ce2035_helper():
    calls = []
    runtime = kodi.Runtime.__new__(kodi.Runtime)
    runtime.monitor = SimpleNamespace(abortRequested=lambda: False)
    runtime.abort_requested = runtime.monitor.abortRequested
    runtime.protocol = SimpleNamespace(
        select=lambda state, request, identity: pytest.fail('Legacy unscoped helper must not be called'),
        call=lambda message: calls.append(message) or {'accepted': True})
    account = dict(account_id='115:' + 'a' * 64, epoch=3, authenticated=True)
    assert runtime.select({'boot_id': 'boot', 'epoch': 2}, 'd' * 32, 'transport:' + 'a' * 64,
                          account) == {'accepted': True}
    assert calls == [dict(operation='select', boot_id='boot', epoch=2, request_id='d' * 32,
                          selection_identity='transport:' + 'a' * 64, account_scope=account)]


@pytest.mark.parametrize('duration', [0, -0.1])
def test_exhausted_sample_delay_never_calls_kodi_infinite_zero_wait(duration):
    runtime = kodi.Runtime.__new__(kodi.Runtime)
    runtime.abort_requested = lambda: False
    runtime.monitor = SimpleNamespace(waitForAbort=lambda value: pytest.fail('Kodi zero wait is infinite'))
    runtime.wait(duration)


def test_positive_sample_delay_still_observes_abort():
    runtime = kodi.Runtime.__new__(kodi.Runtime)
    runtime.abort_requested = lambda: False
    runtime.monitor = SimpleNamespace(waitForAbort=lambda value: value == 0.1)
    with pytest.raises(kodi.HostAbort):
        runtime.wait(0.1)


REQUEST = 'd' * 32
INSTANCE = '12345678-1234-1234-1234-123456789abc'
UA = 'original user agent/+?=&'
ADDRESS = 'https://safe.115cdn.com/example?opaque=signed' + '|User-Agent=' + quote(UA, safe='')


class FakeRuntime:
    def __init__(self):
        self.calls, self.saved = [], []
        self.scope = dict(account_id='115:' + 'b' * 64, epoch=3, authenticated=True)
        self.row = dict(provider='juku', name='sample', fid='123', size=55, media='movie',
                        locator='private', guid='private', share=dict(code='private', password='private'))
        self.proof = dict(account_fingerprint='b' * 64, account_epoch=3,
                          tuple_sha256=shared.digest(shared.encoded(self.row)))
        self.authority = dict(boot_id='boot', epoch=1, desired=None, observed=None, terminal=None)
        self.native = dict(selection_epoch=7, playback=None)
        self.players = []
        self.after_resolve = self.after_select = self.after_bind = None
        self.open_timeout = False
        self.aborted = False

    def abort_requested(self):
        return self.aborted

    def view(self):
        return deepcopy((self.authority, self.native, self.players))
    def inspect(self, target):
        self.calls.append('inspect')
        return dict(self.proof)
    def account(self):
        return dict(self.scope)
    def tuple(self, target):
        return deepcopy(self.row)
    def save(self, record):
        self.saved.append(deepcopy(record))
    def settings(self):
        return {'audiooutput.passthrough': True}
    def native_identity(self):
        return {'sha256': '1' * 64}
    def user_state(self):
        return {'database.pickle': '2' * 64}
    def resolve(self, row, account):
        self.calls.append('resolve')
        if self.after_resolve:
            self.after_resolve()
        return ADDRESS, UA, lambda url: url.startswith('https://safe.115cdn.com/')
    def select(self, snapshot, request, identity, account):
        self.calls.append('select')
        assert snapshot['epoch'] == self.authority['epoch'] and account == self.scope
        self.authority.update(epoch=2, desired=dict(request_id=request, cancelled=False, selection_identity=identity))
        self.native['selection_epoch'] += 1
        result = deepcopy(self.authority)
        if self.after_select:
            self.after_select()
        return result
    def bind(self, request, identity, address):
        self.calls.append('bind')
        assert self.authority['desired']['request_id'] == request
        result = dict(boot_id='boot', epoch=2, request_id=request, file_identity=identity)
        if self.after_bind:
            self.after_bind()
        return result
    def play(self, address, request, identity):
        self.calls.append(('play', address, request, identity))
        assert self.saved[-1]['state'] == 'open_unconfirmed'
        if self.open_timeout:
            raise TimeoutError('secret signed URL must never be serialized')


def start(runtime):
    record = dict(request_id=REQUEST)
    kodi.perform_start(runtime, runtime.proof, dict(selection_identity='transport:' + 'a' * 64), record)
    return record


def new_selection(runtime):
    runtime.authority.update(epoch=3, desired=dict(request_id='e' * 32, cancelled=False))
    runtime.native['selection_epoch'] += 1


def test_real_address_and_original_pipe_ua_pass_unchanged_to_single_open():
    runtime = FakeRuntime()
    record = start(runtime)
    opens = [call for call in runtime.calls if isinstance(call, tuple)]
    assert len(opens) == 1 and opens[0][1] == ADDRESS
    assert record['original_pipe_preserved'] and record['ua_sha256'] == shared.digest(UA)
    assert 'signed' not in json.dumps(runtime.saved) and UA not in json.dumps(runtime.saved)


@pytest.mark.parametrize('address', [ADDRESS.split('|')[0], ADDRESS + '&Cookie=unsafe',
    ADDRESS.replace('User-Agent=', 'user-agent='), ADDRESS.replace('%2F', '/'),
    'https://bad.example/video|User-Agent=' + quote(UA, safe='')])
def test_stripped_modified_or_untrusted_address_is_rejected(address):
    with pytest.raises(shared.DiagnosticError, match='UA_INVALID'):
        kodi.preserved_address(address, UA, lambda url: url.startswith('https://safe.115cdn.com/'))


def test_preexisting_player_rejects_before_resolver_or_selection():
    runtime = FakeRuntime()
    runtime.players = [{'playerid': 1, 'type': 'video'}]
    with pytest.raises(shared.DiagnosticError, match='ACTIVE_PLAYER'):
        start(runtime)
    assert runtime.calls == []


def test_pending_native_open_without_active_player_still_rejected():
    runtime = FakeRuntime()
    runtime.native['playback'] = dict(phase='OPEN', native_instance=INSTANCE)
    with pytest.raises(shared.DiagnosticError, match='NATIVE_NOT_TERMINAL'):
        start(runtime)
    assert not runtime.calls


@pytest.mark.parametrize('stage', ['after_resolve', 'after_select', 'after_bind'])
def test_new_user_selection_wins_before_open(stage):
    runtime = FakeRuntime()
    setattr(runtime, stage, lambda: new_selection(runtime))
    with pytest.raises(shared.DiagnosticError):
        start(runtime)
    assert not any(isinstance(call, tuple) for call in runtime.calls)
    if stage == 'after_resolve':
        assert 'select' not in runtime.calls
    if stage == 'after_select':
        assert 'bind' not in runtime.calls


def test_account_change_during_resolve_never_selects():
    runtime = FakeRuntime()
    runtime.after_resolve = lambda: runtime.scope.update(epoch=4)
    with pytest.raises(shared.DiagnosticError, match='ACCOUNT_CHANGED'):
        start(runtime)
    assert runtime.calls == ['inspect', 'resolve']


def test_changed_tuple_rejected_before_resolve():
    runtime = FakeRuntime()
    runtime.row['fid'] = 'changed'
    with pytest.raises(shared.DiagnosticError, match='INSPECT_CHANGED'):
        start(runtime)
    assert runtime.calls == ['inspect']


def test_open_timeout_has_no_retry_and_preexisting_unconfirmed_receipt():
    runtime = FakeRuntime()
    runtime.open_timeout = True
    with pytest.raises(TimeoutError):
        start(runtime)
    assert len([call for call in runtime.calls if isinstance(call, tuple)]) == 1
    assert runtime.saved[-1]['state'] == 'open_unconfirmed' and not runtime.saved[-1]['retry_allowed']


def test_transport_timeout_keeps_one_local_receipt_and_never_relaunches(tmp_path):
    output, calls = tmp_path / 'new.json', []
    params = dict(run_id='a' * 32, request_id=REQUEST, inspection={}, target={}, duration=45)
    def sender(source, code):
        calls.append(code)
        assert json.loads(output.read_text())['state'] == 'unconfirmed'
        raise TimeoutError('Cookie=private')
    result = driver.run_once(tmp_path, output, params, sender)
    assert result['state'] == 'unconfirmed' and len(calls) == 1
    assert 'private' not in output.read_text()
    with pytest.raises(FileExistsError):
        driver.run_once(tmp_path, output, params, sender)
    assert len(calls) == 1


def test_generated_launch_collect_and_stop_compile_without_executing():
    params = dict(run_id='a' * 32, request_id=REQUEST, inspection={}, target={}, duration=45)
    code = driver.start_code(params)
    compile(code, 'launch', 'exec')
    assert code.count('subprocess.run(') == 1
    assert 'RunScript(' in code and 'Player.Open' not in code
    compile(driver.collect_code(params), 'collect', 'exec')
    compile(driver.stop_code(dict(params, native_instance=INSTANCE)), 'stop', 'exec')


def test_stop_is_exact_instance_sequence_epoch_command_and_no_retry():
    row = dict(phase='AV_STARTED', native_instance=INSTANCE, request_id=REQUEST,
               file_identity='exact', user_intent=2, sequence=9)
    authority = dict(boot_id='boot', epoch=4, desired=dict(request_id=REQUEST, cancelled=False))
    native = dict(selection_epoch=12, playback=row)
    record = dict(owner_context=dict(boot_id='boot', epoch=4, request_id=REQUEST),
                  request_id=REQUEST, native_instance=INSTANCE, file_identity='exact')
    calls, saved = [], []
    def rpc(method, params=None):
        calls.append((method, params))
        raise TimeoutError('lost ACK')
    fake = SimpleNamespace(view=lambda: (authority, native, [{'playerid':1}]), save=lambda r: saved.append(dict(r)), rpc=rpc)
    with pytest.raises(TimeoutError):
        kodi.Runtime.stop(fake, record)
    assert len(calls) == 1 and calls[0][0] == 'Player.BobiControl'
    params = calls[0][1]
    assert {k: params[k] for k in ('native_instance','user_intent','expected_sequence','selection_epoch','action')} == dict(
        native_instance=INSTANCE,user_intent=2,expected_sequence=9,selection_epoch=12,action='stop')
    assert saved[0]['stop_state'] == 'unconfirmed'
    authority['desired']['request_id'] = 'f' * 32
    with pytest.raises(shared.DiagnosticError, match='OTHER_REQUEST'):
        kodi.Runtime.stop(fake, record)
    assert len(calls) == 1


def test_tagged_item_uses_original_native_contract_and_address(monkeypatch):
    properties, plays = {}, []
    class Item:
        def __init__(self, **kwargs):
            assert kwargs['path'] == ADDRESS
        def setProperty(self, key, value):
            properties[key] = value
        def getVideoInfoTag(self):
            return SimpleNamespace(setResumePoint=lambda *args: None)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=Item))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Player=lambda: SimpleNamespace(play=lambda *args, **kwargs: plays.append((args, kwargs)))))
    kodi.Runtime.play(SimpleNamespace(abort_requested=lambda: False), ADDRESS, REQUEST, 'identity')
    assert properties['bobitv.request_id'] == REQUEST and properties['bobitv.file_identity'] == 'identity'
    assert properties['StartOffset'] == properties['StartPercent'] == '0'
    assert len(plays) == 1 and plays[0][0][0] == ADDRESS


def test_large_trace_sidecar_requires_exact_path_bytes_hash_and_identity():
    import hashlib
    receipt = dict(run_id='a' * 32, request_id=REQUEST)
    value = dict(receipt, diagnostic_only=True, product_proof=False, samples=[{'time': i} for i in range(100)])
    raw = json.dumps(value).encode()
    descriptor = dict(artifact='/tmp/bobbi-115-direct-' + receipt['run_id'] + '/result.json',
                      bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    assert driver.decode_result(raw, descriptor, receipt) == value
    for changed in (dict(descriptor, artifact='/storage/private'), dict(descriptor, bytes=1),
                    dict(descriptor, sha256='0' * 64)):
        with pytest.raises(shared.DiagnosticError):
            driver.decode_result(raw, changed, receipt)


def test_pending_cleanup_never_cancels_new_selection():
    calls = []
    def call(message):
        calls.append(message)
        return dict(boot_id='boot', epoch=3, observed=None,
                    desired=dict(request_id='f' * 32, cancelled=False))
    fake = SimpleNamespace(protocol=SimpleNamespace(call=call))
    assert kodi.Runtime.cancel_pending(fake, dict(request_id=REQUEST)) == {'performed': False}
    assert calls == [{'operation': 'snapshot'}]


@pytest.mark.parametrize('stage', ['initial', 'after_resolve', 'after_select', 'after_bind'])
def test_host_abort_prevents_play_before_async_owner_teardown(stage):
    runtime = FakeRuntime()
    if stage == 'initial':
        runtime.aborted = True
    else:
        setattr(runtime, stage, lambda: setattr(runtime, 'aborted', True))
    with pytest.raises(kodi.HostAbort):
        start(runtime)
    assert not any(isinstance(call, tuple) for call in runtime.calls)
    if stage == 'initial':
        assert runtime.calls == []


def test_abort_after_open_pending_fsync_prevents_the_only_opener():
    runtime = FakeRuntime()
    save = runtime.save
    def aborting_save(record):
        save(record)
        if record.get('state') == 'open_unconfirmed':
            runtime.aborted = True
    runtime.save = aborting_save
    record = dict(request_id=REQUEST)
    with pytest.raises(kodi.HostAbort):
        kodi.perform_start(runtime, runtime.proof, dict(selection_identity='transport:' + 'a' * 64), record)
    assert record['open_cancelled_before_call'] is True
    assert not any(isinstance(call, tuple) for call in runtime.calls)


def test_real_bind_receives_live_abort_callback():
    runtime = FakeRuntime()
    observed = []
    def bind(request, identity, address, cancelled, route):
        assert not cancelled()
        runtime.aborted = True
        observed.append((cancelled(), route))
    runtime.protocol = SimpleNamespace(bind_and_claim=bind)
    kodi.Runtime.bind(runtime, REQUEST, 'identity', ADDRESS)
    assert observed == [(True, 'player_play')]


def test_bounded_wait_observes_abort_without_sleep_or_player_action():
    calls = []
    runtime = FakeRuntime()
    def waiting(duration):
        calls.append(duration)
        runtime.aborted = True
        return True
    runtime.monitor = SimpleNamespace(waitForAbort=waiting)
    with pytest.raises(kodi.HostAbort):
        kodi.Runtime.wait(runtime, .5)
    assert calls == [.5] and runtime.calls == []


def test_abort_in_player_construction_never_calls_player_play(monkeypatch):
    runtime = FakeRuntime()
    plays = []
    item = SimpleNamespace(setProperty=lambda *args: None,
        getVideoInfoTag=lambda: SimpleNamespace(setResumePoint=lambda *args: None))
    def player():
        runtime.aborted = True
        return SimpleNamespace(play=lambda *args, **kwargs: plays.append(args))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=lambda **kwargs: item))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Player=player))
    with pytest.raises(kodi.HostAbort):
        kodi.Runtime.play(runtime, ADDRESS, REQUEST, 'identity')
    assert plays == []


def test_abort_is_a_safe_fixed_cancellation_code():
    assert shared.safe_error(kodi.HostAbort('unpublished content')) == {'error': 'cancelled'}
