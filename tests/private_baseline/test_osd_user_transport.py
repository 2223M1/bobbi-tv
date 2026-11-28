"""OSD -> actual authority contract; native is simulated, not device proof."""
from copy import deepcopy
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

from test_osd_playback_contract import SKIN, osd, client, ui, scene
from test_user_transport_presentation import retain, stop_result


@pytest.fixture
def transport_scene(scene, ui, monkeypatch):
    native = scene[1]
    old = native.subtitles
    state = dict(transport_protocol=1, transport_state='playing',
                 can_pause=True, can_resume=True, can_stop=True)
    native.subtitles = lambda: dict(old(), **state)
    ui.dialog.yesno = lambda *a: True
    monkeypatch.setattr(sys.modules['xbmc'], 'getCondVisibility', lambda _: False, raising=False)
    return state


@pytest.mark.parametrize('entry,state,action', [
    ('toggle_pause', 'playing', 'user_pause'), ('toggle_pause', 'paused', 'user_resume'),
    ('toggle_pause', 'other', 'user_resume'), ('resume', 'playing', 'user_resume'),
    ('resume', 'other', 'user_resume'), ('stop', 'playing', 'user_stop'),
    ('confirm_stop', 'playing', 'user_stop')])
def test_explicit_transport_does_not_depend_on_seek(scene, client, ui, transport_scene, entry, state, action):
    transport_scene.update(transport_state=state, can_seek=False)
    captured = client.read()['expected']
    assert osd.run(entry)['status'] == 'queued'
    issued = scene[1].commands
    assert len(issued) == 1 and issued[0]['action'] == action
    assert all(issued[0][key] == value for key, value in captured.items() if key not in ('boot_id', 'epoch'))
    assert ui.calls == (['Dialog.Close(1126)'] if entry == 'confirm_stop' else [])


@pytest.mark.parametrize('entry', ['toggle_pause', 'resume', 'stop', 'confirm_stop'])
def test_old_native_cannot_fall_back_to_global_player(scene, ui, entry):
    osd.run(entry)
    assert scene[1].commands == [] and ui.notices == ['unavailable']
    assert all('PlayerControl' not in str(value) for value in ui.calls)


@pytest.mark.parametrize('field,value', [
    ('transport_protocol', True), ('transport_protocol', 2), ('transport_state', 'unknown'),
    ('can_stop', 'true'), ('can_stop', False)])
def test_transport_capability_is_strict(scene, ui, transport_scene, field, value):
    transport_scene[field] = value
    osd.run('stop')
    assert not scene[1].commands and ui.notices == ['unavailable']


@pytest.mark.parametrize('change', ['instance', 'sequence', 'intent'])
def test_confirm_keeps_original_before_wait_and_never_stops_new_scope(
        scene, client, ui, transport_scene, monkeypatch, change):
    captured = []
    original = osd.Client.capture
    def capture(*args):
        result = original(*args)
        captured.append(deepcopy(result))
        return result
    monkeypatch.setattr(osd.Client, 'capture', staticmethod(capture))
    before = client.read()['expected']
    def confirm(*args):
        assert len(captured) == 1 and captured[0]['expected'] == before
        if change == 'instance':
            scene[1].current['native_instance'] = str(uuid4())
        else:
            scene[1].current['sequence' if change == 'sequence' else 'user_intent'] += 1
        return True
    ui.dialog.yesno = confirm
    assert osd.run('confirm_stop')['status'] == 'rejected'
    assert len(captured) == 1 and captured[0]['expected'] == before
    assert scene[1].commands == [] and ui.calls == ['Dialog.Close(1126)']


def test_cancel_confirmation_is_read_only(scene, client, ui, transport_scene):
    before = deepcopy(scene[0].owner.snapshot())
    ui.dialog.yesno = lambda *a: False
    assert osd.run('confirm_stop') is None
    assert scene[1].commands == [] and not client.window.getProperty(client.pending_key)
    assert scene[0].owner.snapshot() == before


def test_backstop_preference_uses_scoped_command_without_dialog(scene, ui, transport_scene, monkeypatch):
    monkeypatch.setattr(sys.modules['xbmc'], 'getCondVisibility', lambda text: text == 'Skin.HasSetting(backstopplay)')
    ui.dialog.yesno = lambda *a: pytest.fail('Preference requests direct scoped stop')
    assert osd.run('confirm_stop')['status'] == 'queued'
    assert scene[1].commands[-1]['action'] == 'user_stop'


def test_lost_ack_retains_original_command_and_only_polls(scene, client, ui, transport_scene):
    real = client.call
    sent = []
    def call(message):
        if message['operation'] == 'playback_command':
            sent.append(deepcopy(message['command']))
            real(message)
            raise TimeoutError('simulated lost ACK')
        return real(message)
    client.call = call
    assert osd.run('stop')['status'] == 'unknown'
    first = osd.decode(client.window.getProperty(client.pending_key))
    # Reopening is a read, not evidence that the original stop failed.
    osd.run('refresh')
    assert osd.run('stop')['status'] in ('queued', 'unknown')
    assert sent == [first] and len(scene[1].commands) == 1
    assert osd.decode(client.window.getProperty(client.pending_key)) == first
    assert ui.calls == []


@pytest.mark.parametrize('status', ['applied', 'failed', 'unknown'])
def test_refresh_recovers_original_stop_after_player_destroyed_without_control(
        scene, client, ui, transport_scene, status):
    original_call = client.call
    requests = []
    def lost(message):
        requests.append(deepcopy(message))
        result = original_call(message)
        if message['operation'] == 'playback_command':
            raise TimeoutError('lost stop ACK')
        return result
    client.call = lost
    assert osd.run('stop')['status'] == 'unknown'
    pending = client.window.getProperty(client.pending_key)
    original = osd.decode(pending)
    retain(scene[1], [stop_result(original, status)])
    scene[1].current = None
    before = deepcopy(scene[0].owner.snapshot())
    requests.clear()
    projected = osd.run('refresh')
    assert projected['available'] is False
    assert requests == [dict(operation='playback_presentation', include_owner=True),
                        dict(operation='playback_receipt', expected=original['expected'],
                             command_id=original['command_id'])]
    assert client.window.getProperty(client.pending_key) == (pending if status == 'unknown' else '')
    assert ui.notices[-1] == status
    assert len(scene[1].commands) == 1 and ui.calls == []
    assert scene[0].owner.snapshot() == before
    if status in osd.FINAL:
        requests.clear()
        osd.run('refresh')
        assert requests == [dict(operation='playback_presentation', include_owner=True)]


@pytest.mark.parametrize('bad', ['corrupt', 'wrong_reply', 'timeout'])
def test_refresh_cannot_discard_uncertain_pending_or_rebase_to_current_scope(
        scene, client, ui, transport_scene, bad):
    assert osd.run('stop')['status'] == 'queued'
    pending = client.window.getProperty(client.pending_key)
    if bad == 'corrupt':
        pending = 'not a command'
        client.window.setProperty(client.pending_key, pending)
    original_call, requests = client.call, []
    def call(message):
        requests.append(deepcopy(message))
        if message['operation'] == 'playback_receipt':
            if bad == 'timeout':
                raise TimeoutError('receipt unavailable')
            return dict(command_id=uuid4().hex, status='applied')
        return original_call(message)
    client.call = call
    scene[1].current = None
    osd.run('refresh')
    assert client.window.getProperty(client.pending_key) == pending
    assert all(request['operation'] in ('playback_presentation', 'playback_receipt') for request in requests)
    assert len(scene[1].commands) == 1 and ui.calls == []
    assert ui.notices[-1] == 'unknown'


def test_refresh_cannot_query_or_clear_pending_while_submit_lock_is_owned(
        scene, client, ui, transport_scene):
    from bobbi_platform.instance_lock import InstanceLock
    from bobbi_platform.paths import profile
    assert osd.run('stop')['status'] == 'queued'
    pending = client.window.getProperty(client.pending_key)
    original_call, requests = client.call, []
    client.call = lambda message: requests.append(message) or original_call(message)
    lock = InstanceLock(str(client.lock_path or profile(name='osd.lock')))
    lock.acquire()
    try:
        osd.run('refresh')
        assert client.window.getProperty(client.pending_key) == pending
        assert requests == [dict(operation='playback_presentation', include_owner=True)]
        assert ui.notices[-1] == 'unknown'
    finally:
        lock.close()


@pytest.mark.parametrize('same_id', [False, True])
def test_refresh_old_receipt_cannot_clear_replaced_capture(client, ui, transport_scene, same_id):
    original = client.capture(client.read(), 'user_stop', {})
    replacement = deepcopy(original)
    replacement['expected']['expected_sequence'] += 1
    if not same_id:
        replacement['command_id'] = uuid4().hex
    client.window.setProperty(client.pending_key, osd.encode(original))
    read = client.call
    def call(message):
        if message['operation'] == 'playback_receipt':
            assert message == dict(operation='playback_receipt', expected=original['expected'],
                                   command_id=original['command_id'])
            client.window.setProperty(client.pending_key, osd.encode(replacement))
            return dict(command_id=original['command_id'], status='applied')
        return read(message)
    client.call = call
    osd.run('refresh')
    assert osd.decode(client.window.getProperty(client.pending_key)) == replacement
    assert not client.window.getProperty(client.pending_key + '.PreviousUnknown')
    assert ui.calls == []


@pytest.mark.parametrize('mode', ['external', 'standard'])
def test_affirmative_native_adapter_keeps_native_controls(client, ui, mode, monkeypatch):
    monkeypatch.setattr(client, 'read', lambda: dict(available=False, mode=mode))
    osd.run('toggle_pause')
    osd.run('stop')
    assert ui.calls == ['PlayerControl(Play)', 'PlayerControl(Stop)']


def test_confirmation_compatibility_entry_has_no_live_skin_reset_branch():
    root = ET.parse(SKIN / 'custom_1126_Confirm.xml').getroot()
    assert root.findtext('onload') == 'RunScript(plugin.video.bobbi,bobbi_osd=confirm_stop)'
    text = ET.tostring(root, encoding='unicode')
    assert 'Skin.ResetSettings' not in text and 'PlayerControl' not in text


@pytest.mark.parametrize('switched', [False, True])
def test_music_confirmation_keeps_audio_only_native_target(scene, client, ui, monkeypatch, switched):
    active = [True]
    monkeypatch.setattr(sys.modules['xbmc'], 'getCondVisibility',
                        lambda text: active[0] if text == 'Player.HasAudio + !Player.HasVideo' else False)
    monkeypatch.setattr(client, 'read', lambda: dict(available=False, mode='unavailable'))
    def confirm(*args):
        active[0] = not switched
        return True
    ui.dialog.yesno = confirm
    osd.run('confirm_stop')
    assert ui.calls == ['Dialog.Close(1126)'] + ([] if switched else [('Player.Stop', {'playerid': 0})])
    assert scene[1].commands == []


def test_video_and_sidebar_transport_use_owned_entry_music_livetv_are_preserved():
    root = ET.parse(SKIN / 'VideoOSD.xml').getroot()
    clicks = [node.text for node in root.iter('onclick')]
    assert 'RunScript(plugin.video.bobbi,bobbi_osd=stop)' in clicks
    assert 'RunScript(plugin.video.bobbi,bobbi_osd=toggle_pause)' in clicks
    assert 'Stop' not in clicks and 'PlayerControl(Play)' not in clicks
    for name in ('PlayerControls.xml', 'Includes_Compatibility.xml'):
        nodes = list(ET.parse(SKIN / name).iter('onclick'))
        for action in ('stop', 'toggle_pause'):
            assert any(n.text == 'RunScript(plugin.video.bobbi,bobbi_osd=' + action + ')'
                       and n.get('condition') == 'Player.HasVideo' for n in nodes)
        for native in ('PlayerControl(Play)', 'PlayerControl(Stop)'):
            assert any(n.text == native and n.get('condition') == '!Player.HasVideo' for n in nodes)
            assert any(n.text == native and n.get('condition') is None for n in nodes)  # Live TV.


def test_resident_commands_require_visible_osd_and_original_tap_scope(scene, client, ui, transport_scene, monkeypatch):
    xbmc = sys.modules['xbmc']
    active = [True]
    monkeypatch.setattr(xbmc, 'getCondVisibility', lambda _: active[0], raising=False)
    osd.resident_tap(client, 'Other.BobbiRefresh')
    token = client.window.getProperty(osd.TAP_SCOPE)
    assert len(token) == 32
    active[0] = False
    osd.resident_tap(client, 'Other.BobbiTap.toggle_pause.' + token)
    active[0] = True
    stale = ('0' if token[0] != '0' else '1') + token[1:]
    osd.resident_tap(client, 'Other.BobbiTap.toggle_pause.' + stale)
    assert not scene[1].commands
    osd.resident_tap(client, 'Other.BobbiTap.toggle_pause.' + token)
    assert [event['action'] for event in scene[1].commands] == ['user_pause']
