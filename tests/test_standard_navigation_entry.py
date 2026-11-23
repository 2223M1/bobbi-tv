"""Real navigation -> StandardSession -> stock handoff on one loopback Host.

Kodi presentation and provider resolution are doubles. Runtime registration,
profile fences, reservation, request/account checks and Handoff are real.
This is not device or AV-start certification.
"""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import paths, playback_client, prepared_sessions, runtime
from bobbi_platform.playback import Handoff
from bobbi_platform.standard_session import StandardSession

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons/plugin.video.bobbi'
ACCOUNT = dict(account_id='', authenticated=False, epoch=0)
DATA = dict(selection_policy='exact', type='Direct', url='https://media.example/selected.mkv')


@pytest.fixture(params=['play_media', 'play_from_pack'])
def entry(request, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(PLUGIN))
    def module(name, relative):
        spec = importlib.util.spec_from_file_location(name, PLUGIN / relative)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        monkeypatch.setitem(sys.modules, name, value)
        return value
    # Exercise real modules without leaving a first-import cache or a patched
    # dependency in another suite's plugin/Kodi interpreter.
    product = module('lib.player', 'lib/player.py')
    stock = module('lib.stock_player', 'lib/stock_player.py')
    module('lib.services.standard_playback', 'lib/services/standard_playback.py')
    state = SimpleNamespace(profile='A', adapter='standard', calls=[], captures=[], bindings=[],
        opened=[], notifications=[], resolutions=[], native_players=[], handoffs=[], wire=[],
        after_dispatch=None, resolve_hook=None, make_hook=None, send_error=None, on_notice=None,
        account=dict(ACCOUNT), desired=None, entry=request.param)
    def require(value, authenticated=False):
        if value != state.account or (authenticated and not value['authenticated']):
            raise ValueError('ACCOUNT_CHANGED')
    state.session = StandardSession(SimpleNamespace(require_current=require,
        is_current=lambda value: value == state.account))
    def dispatch(action, body):
        state.calls.append((action, deepcopy(body)))
        if action == 'status':
            result = dict(playback_adapter=state.adapter)
        elif action == 'account_status':
            result = dict(state.account)
        elif action == 'standard_playback':
            result = ({'state': 'pending'} if body['operation'] == 'subtitle_start'
                      else state.session.dispatch(body))
        elif action == 'playback' and state.adapter == 'native':
            if body['operation'] == 'select':
                state.desired = dict(request_id=body['request_id'], cancelled=False)
            else:
                assert body['operation'] == 'snapshot'
            result = dict(boot_id='native-fixture', epoch=4, desired=state.desired)
        else:
            pytest.fail('Unexpected capability: ' + action)
        if state.after_dispatch:
            state.after_dispatch(action, body)
        return result
    first = runtime.Runtime(dispatch, tmp_path / 'A/script.module.bobbi.platform/runtime.json')
    first.start()
    state.server = first
    state.original_registration = first.path.read_bytes()
    second_calls = []
    second = runtime.Runtime(lambda action, body: second_calls.append((action, body)) or {},
                             tmp_path / 'replacement/runtime.json')
    second.start()
    state.replacement, state.replacement_calls = second, second_calls
    real_binding, real_bind, real_capture = paths.ProfileBinding, runtime.bind_call, playback_client.capture_transport
    def binding():
        value = real_binding(lambda addon: tmp_path / state.profile / addon)
        state.bindings.append(value)
        return value
    def bind(path):
        value = real_bind(path)
        def call(action, body, timeout=3):
            state.wire.append((action, deepcopy(body), timeout))
            return value(action, body, timeout=timeout)
        return call
    def capture(**options):
        result = real_capture(**options)
        state.captures.append(result)
        return result
    monkeypatch.setattr(paths, 'ProfileBinding', binding)
    monkeypatch.setattr(runtime, 'bind_call', bind)
    monkeypatch.setattr(playback_client, 'capture_transport', capture)
    monkeypatch.setattr(runtime, 'profile', lambda **kw: pytest.fail('Dynamic runtime discovery'))
    monkeypatch.setattr(prepared_sessions, 'capture', lambda *a, **kw: pytest.fail('Ordinary media needs no prepared capture'))
    monkeypatch.setitem(sys.modules, 'lib.native_support', SimpleNamespace(
        available=lambda: pytest.fail('Adapter must not be rediscovered')))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(ADDON_HANDLE=17))
    monkeypatch.setitem(sys.modules, 'lib.search', SimpleNamespace(
        run_search_entry=lambda *a, **kw: pytest.fail('Standard failure must not reopen another entry')))
    class NativePlayer:
        def __init__(self, *, playback_client):
            self.playback_client = playback_client
            state.native_players.append(self)
        def run(self, data):
            state.opened.append(('native', deepcopy(data)))
    monkeypatch.setitem(sys.modules, 'lib.native_player', SimpleNamespace(JacktookPLayer=NativePlayer))
    def handoff(identity, handle, **options):
        def make_item(url, data):
            if state.make_hook:
                state.make_hook()
            return deepcopy(data)
        def send(*args):
            state.opened.append(('standard', args))
            if state.send_error:
                raise state.send_error
        value = Handoff(identity, handle, send, send, make_item, **options)
        state.handoffs.append(value)
        return value
    monkeypatch.setattr(stock, 'standard_handoff', handoff)
    def resolve(data, *, playback_client):
        json.dumps(data)  # Callables must stay outside the wire payload.
        state.resolutions.append((deepcopy(data), playback_client))
        if state.resolve_hook:
            return state.resolve_hook(data)
        return data
    def notice(message):
        state.notifications.append(message)
        if state.on_notice:
            state.on_notice()
    namespace = dict(json=json, notification=notice, JacktookPLayer=product.JacktookPLayer,
        resolve_stremio_playback_url=resolve)
    source = PLUGIN / 'lib/navigation.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in (request.param, '_reselect_cached_torrent')]
    assert len(nodes) == 2
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    state.invoke = lambda data=None: namespace[request.param]({'data': json.dumps(DATA if data is None else data)})
    state.stock = stock
    try:
        yield state
    finally:
        first.close()
        second.close()
        state.session.close()


def operations(entry):
    return [body['operation'] for action, body in entry.calls if action == 'standard_playback']


@pytest.mark.parametrize('media', ['direct', 'resolved-bt'])
def test_exact_standard_uses_real_select_once_and_needs_no_prepared_session(entry, media):
    data = dict(DATA)
    if media == 'resolved-bt':
        data.update(resolved_backend='local_torrserver', info_hash='a' * 40, file_id=1)
    entry.invoke(data)
    assert len(entry.captures) == len(entry.bindings) == 1
    assert operations(entry) == ['select', 'current', 'subtitle_start', 'register', 'current']
    assert not entry.notifications and len(entry.opened) == 1
    assert not any(action == 'playback' for action, _ in entry.calls)
    selected = entry.session.current
    assert selected['state'] == 'submitted'  # Not a fabricated AV-start receipt.
    assert selected['data']['_account'] == ACCOUNT and selected['data']['request_id'] == selected['request_id']
    assert not {'boot_id', 'epoch', '_selection_context'} & selected['data'].keys()
    assert entry.handoffs[0].state == 'submitted'
    with pytest.raises(OSError):
        entry.resolutions[0][1].read_snapshot()  # No native capability for stock resolution.


def test_native_entry_keeps_real_client_and_existing_reserve_algorithm(entry):
    entry.adapter = 'native'
    entry.invoke()
    assert len(entry.captures) == 1 and not entry.notifications
    assert [(action, body.get('operation')) for action, body in entry.calls] == [
        ('status', None), ('playback', 'snapshot'), ('playback', 'select')]
    assert entry.resolutions[0][1] is entry.native_players[0].playback_client is entry.captures[0][1]
    assert entry.opened[0][1]['_selection_context']['boot_id'] == 'native-fixture'
    assert all(0 < timeout <= .3 for action, body, timeout in entry.wire if action == 'playback')


def test_native_non_exact_control_keeps_no_reservation_behavior(entry):
    entry.adapter = 'native'
    entry.invoke({key: value for key, value in DATA.items() if key != 'selection_policy'})
    assert [action for action, body in entry.calls] == ['status']
    assert len(entry.opened) == 1 and not entry.notifications


@pytest.mark.parametrize('adapter', ['starting', 'unknown', None])
def test_only_positive_bound_host_adapter_can_choose_player(entry, adapter):
    entry.adapter = adapter
    entry.invoke()
    assert [action for action, body in entry.calls] == ['status']
    assert not entry.opened and not entry.resolutions and len(entry.notifications) == 1


def test_standard_plain_entry_can_play_with_logged_out_account(entry):
    entry.invoke({key: value for key, value in DATA.items() if key != 'selection_policy'})
    assert len(entry.opened) == 1 and operations(entry).count('select') == 1
    assert entry.session.current['account']['authenticated'] is False


def test_stale_account_cannot_be_adopted_from_new_host_scope(entry):
    entry.invoke(dict(DATA, _account=dict(ACCOUNT, epoch=5)))
    assert not operations(entry) and not entry.opened and len(entry.notifications) == 1


@pytest.mark.parametrize('stage', ['select', 'register'])
def test_lost_reply_cancels_only_original_request_without_reselection(entry, stage):
    def lost(action, body):
        if action == 'standard_playback' and body['operation'] == stage:
            raise OSError('accepted, reply lost')
    entry.after_dispatch = lost
    entry.invoke()
    assert operations(entry).count('select') == 1 and operations(entry).count('cancel') == 1
    assert not entry.opened and len(entry.captures) == 1 and len(entry.notifications) == 1
    assert entry.session.current['cancel'].is_set()
    requests = {body['request_id'] for action, body in entry.calls if action == 'standard_playback'}
    assert requests == {entry.session.current['request_id']}


def test_lost_select_and_cleanup_replies_do_not_retry_mutations(entry):
    def lost(action, body):
        if action == 'standard_playback' and body['operation'] in ('select', 'cancel'):
            raise OSError('reply lost')
    entry.after_dispatch = lost
    entry.invoke()
    assert operations(entry) == ['select', 'cancel']
    assert not entry.opened and len(entry.captures) == len(entry.notifications) == 1


@pytest.mark.parametrize('change', ['profile', 'runtime'])
@pytest.mark.parametrize('stage', ['select', 'register'])
def test_inflight_scope_change_and_aba_cannot_revive_reply_or_cleanup(entry, change, stage):
    def changed(action, body):
        if action == 'standard_playback' and body['operation'] == stage:
            if change == 'profile':
                entry.profile = 'B'
            else:
                entry.server.path.write_bytes(entry.replacement.path.read_bytes())
    entry.after_dispatch = changed
    def restored():
        entry.profile = 'A'
        entry.server.path.write_bytes(entry.original_registration)
    entry.on_notice = restored
    entry.invoke()
    assert len(entry.captures) == 1 and not entry.opened and not entry.replacement_calls
    assert operations(entry).count('select') == 1 and 'cancel' not in operations(entry)
    with pytest.raises((OSError, ValueError), match='PROFILE_CHANGED|RUNTIME_INSTANCE_CHANGED'):
        entry.captures[0][2]('status', {})


def test_missing_registration_cannot_recapture_after_late_recovery(entry):
    entry.server.path.unlink()
    entry.on_notice = lambda: entry.server.path.write_bytes(entry.original_registration)
    entry.invoke()
    assert len(entry.captures) == 1 and entry.calls == [] and not entry.opened
    with pytest.raises(OSError):
        entry.captures[0][2]('status', {})


def test_superseded_request_cleanup_does_not_cancel_new_selection(entry):
    def newer(data):
        entry.session.select('b' * 32, ACCOUNT)
        return data
    entry.resolve_hook = newer
    entry.invoke()
    assert not entry.opened and entry.session.current_request('b' * 32)
    assert operations(entry) == ['select', 'current', 'cancel']


def test_profile_change_during_listitem_creation_blocks_last_handoff(entry):
    entry.make_hook = lambda: setattr(entry, 'profile', 'B')
    entry.invoke()
    assert not entry.opened and len(entry.notifications) == 1 and len(entry.captures) == 1


@pytest.mark.parametrize('mutation', ['empty', 'request', 'account'])
def test_resolver_failure_or_retarget_never_reopens_search_or_reselects(entry, mutation):
    def resolve(data):
        if mutation == 'empty':
            return None
        if mutation == 'request':
            return dict(data, request_id='c' * 32)
        return dict(data, _account=dict(ACCOUNT, epoch=7))
    entry.resolve_hook = resolve
    entry.invoke()
    assert operations(entry) == ['select', 'cancel']
    assert not entry.opened and len(entry.notifications) == 1


def test_unknown_kodi_submission_is_single_shot_without_native_commands(entry):
    entry.send_error = OSError('Kodi submission reply lost')
    entry.invoke()
    assert len(entry.opened) == 1 and entry.handoffs[0].state == 'submission_unknown'
    assert operations(entry).count('select') == operations(entry).count('cancel') == 1
    assert not any(action == 'playback' for action, body in entry.calls)
    assert len(entry.notifications) == 1


def test_stock_explicit_failed_host_binding_never_captures(entry, monkeypatch):
    monkeypatch.setattr(playback_client, 'capture_transport', lambda **kw: pytest.fail('Explicit failure recaptured'))
    player = entry.stock.JacktookPLayer(host_call=None)
    with pytest.raises(OSError, match='PLAYBACK_BINDING_UNAVAILABLE'):
        player.run(DATA)
    assert not entry.opened and not entry.calls


def test_stock_falsey_injected_callback_is_not_recaptured(entry, monkeypatch):
    _, _, bound = playback_client.capture_transport()
    class Call:
        def __bool__(self):
            return False
        def __call__(self, action, body, **options):
            return bound(action, body, **options)
    injected = Call()
    monkeypatch.setattr(playback_client, 'capture_transport', lambda **kw: pytest.fail('Explicit callback recaptured'))
    player = entry.stock.JacktookPLayer(host_call=injected, prepared_session=None)
    player.run(DATA)
    assert player.host_call is injected and player._resolution_answered


def test_stock_compatibility_boundary_captures_once_before_run(entry):
    player = entry.stock.JacktookPLayer(prepared_session=None)
    assert len(entry.captures) == 1 and not entry.calls
    player.run(DATA)
    assert player._resolution_answered and len(entry.captures) == 1


def test_stock_optional_preparation_failure_keeps_same_host_and_plain_media(entry, monkeypatch):
    def failed(*args, **kwargs):
        raise ValueError('Optional preparation unavailable')
    monkeypatch.setattr(prepared_sessions, 'PreparedSession', failed)
    player = entry.stock.JacktookPLayer()
    assert player.prepared_session is None and len(entry.captures) == 1
    player.run(DATA)
    assert player._resolution_answered and len(entry.captures) == 1


def test_prepared_navigation_uses_same_profile_host_without_optional_recapture(entry, monkeypatch):
    sessions = []
    def prepared(root, call, account, current):
        sessions.append((root, call, account, current))
        return SimpleNamespace(direct_resolve=lambda data, cancelled:
            dict(path='https://media.example/prepared.mkv', key='prepared', bytes=10))
    monkeypatch.setattr(prepared_sessions, 'PreparedSession', prepared)
    entry.invoke(dict(DATA, direct_cloud_required=True))
    assert len(sessions) == len(entry.captures) == len(entry.opened) == 1
    assert sessions[0][0] == entry.bindings[0].root('plugin.video.bobbi')
    assert sessions[0][1] is entry.captures[0][2] and sessions[0][2] == ACCOUNT


def test_standard_transport_keeps_existing_generic_call_budget(entry):
    entry.invoke()
    assert 0 < entry.wire[0][2] <= .25
    assert all(.3 < timeout <= 3 for action, body, timeout in entry.wire if action != 'status')
