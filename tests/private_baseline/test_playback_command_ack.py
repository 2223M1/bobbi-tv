"""Native ACK admission, distinct from execution proof; no device evidence."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from test_playback_presentation import scene, submit, view
from test_user_transport_presentation import lookup, retain, stop_result


ACTIONS = [
    ('seek', {'position_ms': 10000}),
    ('audio_stream', {'index': 0, 'stream_key': 'b' * 64}),
    ('manual_subtitle_stream', {'index': 0, 'stream_key': 'c' * 64}),
    ('subtitle_visible', {'visible': False}),
    ('user_pause', {}), ('user_resume', {}), ('user_stop', {}),
]
UNCERTAIN = [
    'null', 'list', 'scalar', 'empty', 'missing_id', 'missing_queued',
    'foreign_true', 'foreign_false', 'null_id', 'numeric_id',
    'null_queued', 'zero_queued', 'one_queued', 'text_true', 'text_false', 'list_queued',
]


@pytest.fixture
def ack_scene(scene):
    native = scene[1]
    original = native.subtitles
    native.subtitles = lambda: dict(original(), transport_protocol=1,
        transport_state='playing', can_pause=True, can_resume=True, can_stop=True)
    return scene


def ack(command, case):
    if case in ('accepted', 'rejected'):
        return dict(command_id=command['command_id'], queued=case == 'accepted')
    if case in ('null', 'list', 'scalar', 'empty'):
        return {'null': None, 'list': [], 'scalar': True, 'empty': {}}[case]
    reply = dict(command_id=command['command_id'], queued=True)
    if case == 'missing_id':
        reply.pop('command_id')
    elif case == 'missing_queued':
        reply.pop('queued')
    elif case.startswith('foreign_'):
        reply.update(command_id=uuid4().hex, queued=case == 'foreign_true')
    elif case in ('null_id', 'numeric_id'):
        reply['command_id'] = None if case == 'null_id' else 1
    else:
        reply['queued'] = {'null_queued': None, 'zero_queued': 0, 'one_queued': 1,
            'text_true': 'true', 'text_false': 'false', 'list_queued': []}[case]
    return reply


@pytest.mark.parametrize('action,params', ACTIONS)
@pytest.mark.parametrize('case', UNCERTAIN)
def test_uncertain_ack_retains_original_and_only_exact_execution_proof_can_settle(
        ack_scene, action, params, case):
    owner, native, _ = ack_scene
    control = native.control
    def malformed(command):
        control(command)  # It may already have reached the native actor.
        return ack(command, case)
    native.control = malformed
    reply, command = submit(ack_scene, action, params)
    assert reply == dict(command_id=command['command_id'], status='unknown')
    assert owner.playback_commands[command['command_id']]['command'] == command
    assert owner.playback_commands[command['command_id']]['status'] == 'unknown'
    before = deepcopy(owner.owner.snapshot())
    assert owner.dispatch(dict(operation='playback_command', command=command)) == reply
    assert lookup(owner, command) == reply
    assert len(native.commands) == 1 and native.gui_commands == []
    assert owner.owner.snapshot() == before
    result = (stop_result(command) if action == 'user_stop'
              else dict(native.commands[0], status='applied'))
    assert not owner.event('xbmc', 'Player.OnBobiControl', dict(result, command_id=uuid4().hex))
    assert lookup(owner, command) == reply
    if action == 'user_stop':
        retain(native, [result])
        native.current = None
    else:
        assert owner.event('xbmc', 'Player.OnBobiControl', result)
    assert lookup(owner, command) == dict(command_id=command['command_id'], status='applied')
    assert owner.dispatch(dict(operation='playback_command', command=command))['status'] == 'applied'
    assert len(native.commands) == 1 and native.gui_commands == []
    assert owner.owner.snapshot() == before


@pytest.mark.parametrize('action,params', ACTIONS)
@pytest.mark.parametrize('case,status', [('accepted', 'queued'), ('rejected', 'rejected')])
def test_exact_boolean_ack_is_admission_not_execution(ack_scene, action, params, case, status):
    owner, native, _ = ack_scene
    control = native.control
    def reply(command):
        control(command)
        return ack(command, case)
    native.control = reply
    result, command = submit(ack_scene, action, params)
    assert result == dict(command_id=command['command_id'], status=status)
    assert owner.dispatch(dict(operation='playback_command', command=command)) == result
    assert lookup(owner, command) == result
    assert len(native.commands) == 1


@pytest.mark.parametrize('case', ['accepted', 'rejected'] + UNCERTAIN + [
    'missing_result', 'rpc_rejected', 'rpc_unavailable', 'broken_json',
    'null_envelope', 'list_envelope', 'scalar_envelope', 'text_envelope', 'malformed_error'])
def test_real_kodi_jsonrpc_result_reaches_core_ack_validation(ack_scene, monkeypatch, case):
    """Real adapter/JSON decoding/core; only Kodi's native boundary is doubled."""
    import xbmc
    from lib.services.playback_control import KodiNative
    owner, native, _ = ack_scene
    calls = []
    def execute(raw):
        request = json.loads(raw)
        calls.append(request)
        assert request['method'] == 'Player.BobiControl'
        command = request['params']
        native.commands.append(deepcopy(command))
        response = dict(jsonrpc='2.0', id=request['id'])
        if case == 'broken_json':
            return '{"result":'
        if case in ('null_envelope', 'list_envelope', 'scalar_envelope', 'text_envelope'):
            return json.dumps({'null_envelope': None, 'list_envelope': [],
                               'scalar_envelope': 1, 'text_envelope': 'invalid'}[case])
        if case == 'malformed_error':
            return json.dumps(dict(error=[1]))
        if case == 'rpc_rejected':
            response['error'] = dict(code=-32602, message='Invalid params')
        elif case == 'rpc_unavailable':
            response['error'] = dict(code=-32100, message='Unavailable')
        elif case != 'missing_result':
            response['result'] = ack(command, case)
        return json.dumps(response)
    monkeypatch.setattr(xbmc, 'executeJSONRPC', execute)
    native.control = KodiNative.__new__(KodiNative).control
    expected = deepcopy(view(ack_scene)['expected'])
    reply, command = submit(ack_scene, 'user_pause', {}, expected=expected)
    status = {'accepted': 'queued', 'rejected': 'rejected'}.get(case, 'unknown')
    assert reply == dict(command_id=command['command_id'], status=status)
    assert len(calls) == 1 and calls[0]['params']['command_id'] == command['command_id']
    assert all(calls[0]['params'][key] == value for key, value in expected.items()
               if key not in ('boot_id', 'epoch'))
    assert owner.dispatch(dict(operation='playback_command', command=command)) == reply
    assert len(calls) == 1 and len(native.commands) == 1


@pytest.mark.parametrize('action,params', ACTIONS[:4])
@pytest.mark.parametrize('case,status', [('accepted', 'queued'), ('rejected', 'rejected')])
def test_old_native_four_actions_keep_original_boolean_ack_contract(scene, action, params, case, status):
    native, control = scene[1], scene[1].control
    def reply(command):
        control(command)
        return ack(command, case)
    native.control = reply
    assert 'transport_protocol' not in view(scene)
    result, command = submit(scene, action, params)
    assert result == dict(command_id=command['command_id'], status=status)
    assert len(native.commands) == 1


@pytest.mark.parametrize('action,params', ACTIONS)
def test_bad_ack_does_not_freeze_out_a_real_failed_execution_receipt(ack_scene, action, params):
    owner, native, _ = ack_scene
    control = native.control
    def malformed(command):
        control(command)
        return dict(queued=False)  # Not the explicit rejection of this original ID.
    native.control = malformed
    reply, command = submit(ack_scene, action, params)
    assert reply['status'] == 'unknown'
    result = (stop_result(command, 'failed') if action == 'user_stop'
              else dict(native.commands[0], status='failed'))
    assert owner.event('xbmc', 'Player.OnBobiControl', result)
    assert lookup(owner, command) == dict(command_id=command['command_id'], status='failed')
    assert len(native.commands) == 1
