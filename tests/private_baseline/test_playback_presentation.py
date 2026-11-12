"""Production owner boundary; simulated native responses, not device proof."""
from copy import deepcopy
from uuid import uuid4

import pytest

from test_playback_authority import playing
from bobbi_core import playback_presentation as contract


@pytest.fixture
def scene():
    owner, native, args = playing()
    native.current.update(audio_intent=0, open_epoch=native.epoch, control_protocol=1)
    native.subtitles = lambda: dict(status='READY', control_protocol=1, receipt=deepcopy(native.current),
        selection_epoch=native.epoch, position_ms=2000, duration_ms=100000, can_seek=True, visible=True,
        audio_index=0, current_index=0, audio_streams=[dict(index=0, stream_key='b'*64, name='原声', language='fr')],
        streams=[dict(index=0, stream_key='c'*64, name='中文', language='zh')], chapters=[])
    return owner, native, args


def view(scene):
    return scene[0].dispatch(dict(operation='playback_presentation'))


def submit(scene, action='seek', params=None, expected=None, command_id=None):
    command = dict(expected=expected or view(scene)['expected'], command_id=command_id or uuid4().hex,
                   action=action, params=params if params is not None else {'position_ms': 10000})
    return scene[0].dispatch(dict(operation='playback_command', command=command)), command


def test_one_projection_and_queued_is_not_applied(scene):
    value = view(scene)
    assert value['available'] and value['audio'][0]['selected']
    assert 'file_identity' not in repr(value) and 'url_sha256' not in repr(value)
    reply, command = submit(scene)
    assert reply['status'] == 'queued'
    wire = scene[1].commands[-1]
    assert wire['request_id'] == scene[2]['request_id'] and wire['control_protocol'] == 1
    assert not scene[0].event('xbmc', 'Player.OnBobiControl', dict(wire, accepted=True))
    assert scene[0].event('xbmc', 'Player.OnBobiControl', dict(wire, status='applied'))
    result = scene[0].dispatch(dict(operation='playback_receipt', expected=command['expected'], command_id=command['command_id']))
    assert result['status'] == 'applied'
    again, _ = submit(scene, expected=command['expected'], command_id=command['command_id'])
    assert again['status'] == 'applied' and len(scene[1].commands) == 1


@pytest.mark.parametrize('key,value', [('native_instance', str(uuid4())), ('request_id', 'd'*32),
    ('file_sha256', 'd'*64), ('user_intent', 1), ('subtitle_intent', 1), ('audio_intent', 1),
    ('expected_sequence', 100), ('selection_epoch', 100), ('epoch', 100), ('boot_id', 'd'*32)])
def test_old_expected_is_not_replaced_with_fresh_authority(scene, key, value):
    scope = view(scene)['expected']
    scope[key] = value
    reply, _ = submit(scene, expected=scope)
    assert reply['status'] == 'rejected' and not scene[1].commands


@pytest.mark.parametrize('target', [-1, True, float('nan'), float('inf'), '2'])
def test_seek_rejects_non_integer_or_negative(scene, target):
    with pytest.raises(ValueError):
        submit(scene, params=dict(position_ms=target))
    assert not scene[1].commands


@pytest.mark.parametrize('action,params', [('seek', {'position_ms':100000}),
    ('audio_stream', {'index':0,'stream_key':'d'*64}), ('manual_subtitle_stream', {'index':1,'stream_key':'c'*64})])
def test_invalid_target_does_not_reach_native(scene, action, params):
    assert submit(scene, action, params)[0]['status'] == 'rejected'
    assert not scene[1].commands


def test_lost_reply_no_replay_and_ledger_can_resolve_real_final_result(scene):
    owner, native, _ = scene
    original = native.control
    def lost(command):
        original(command)
        raise OSError('reply lost')
    native.control = lost
    reply, command = submit(scene)
    assert reply['status'] == 'unknown'
    assert submit(scene, expected=command['expected'], command_id=command['command_id'])[0]['status'] == 'unknown'
    assert len(native.commands) == 1
    original_read = native.subtitles
    native.subtitles = lambda: dict(original_read(), commands=[dict(native.commands[0],status='applied')])
    assert owner.dispatch(dict(operation='playback_receipt', expected=command['expected'], command_id=command['command_id']))['status'] == 'applied'


def test_old_native_and_unknown_standard_read_have_no_control_capability(scene):
    scene[1].subtitles = lambda: dict(status='READY', receipt=scene[1].current)
    assert view(scene) == dict(available=False, reason='SCOPED_CONTROL_UNAVAILABLE')


@pytest.mark.parametrize('operation', ['playback_presentation', 'playback_command', 'playback_receipt'])
def test_phone_account_scope_fences_every_playback_operation(scene, operation):
    from types import SimpleNamespace
    owner, native, _ = scene
    owner.selection_account = {'provider': 'one'}
    owner.configure_accounts(SimpleNamespace(run_if_current=lambda scope, action: action()))
    result = owner.dispatch(dict(operation=operation, account_scope={'provider': 'other'}))
    assert result['status'] == 'rejected' and result['reason'] == 'PLAYBACK_SCOPE_CHANGED'
    assert native.commands == []


def test_boolean_protocol_does_not_advertise_scoped_control(scene):
    original=scene[1].subtitles
    scene[1].subtitles=lambda: dict(original(),control_protocol=True)
    assert not view(scene)['available']


def test_large_unicode_track_projection_keeps_selected_tracks_within_phone_budget(scene):
    import json
    original=scene[1].subtitles
    def many():
        value=original()
        for key in ('audio_streams','streams'):
            value[key]=[dict(index=i,stream_key=('%064x'%i),name='片'*128,language='语'*32) for i in range(64)]
        value['chapters']=[dict(position_ms=i*1000,name='章'*128) for i in range(32)]
        return value
    scene[1].subtitles=many
    value=view(scene)
    assert value['available'] and len(json.dumps(value,ensure_ascii=False).encode())<=12288
    assert value['audio'][0]['selected'] and value['subtitles'][0]['selected']
    assert value['audio_truncated'] and value['subtitles_truncated'] and value['chapters_truncated']


def test_subtitle_hide_uses_same_bound_command_without_manual_auto_fallback(scene):
    reply, command = submit(scene, 'subtitle_visible', {'visible':False})
    assert reply['status'] == 'queued'
    assert scene[1].commands[-1]['visible'] is False
    assert command['expected']['subtitle_intent'] == 0


def test_public_segments_are_manual_only_and_invalidate_with_original_popup(scene):
    owner, native, args = scene
    context = dict(args, native_instance=native.current['native_instance'])
    assert owner.dispatch(dict(context, operation='segment_register', segments={
        'intro':dict(start_ms=1000,end_ms=9000)})) == {'accepted':True, 'count':1}
    status = owner.dispatch(dict(context, operation='segment_status'))
    assert status['available'] and status['auto_allowed'] is False
    popup = dict(context, expected=status['expected'], segment_id=status['segment']['segment_id'])
    assert owner.dispatch(dict(popup, operation='segment_action', command_id=uuid4().hex))['queued']
    native.current['user_intent'] += 1
    assert not owner.dispatch(dict(popup, operation='segment_status'))['available']
    assert not owner.dispatch(dict(popup, operation='segment_action', command_id=uuid4().hex))['available']
    assert len(native.commands) == 1
