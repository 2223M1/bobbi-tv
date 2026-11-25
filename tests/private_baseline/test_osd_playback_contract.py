"""Real OSD client -> production actor -> simulated native. Not device proof."""
from copy import deepcopy
import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from uuid import uuid4
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit
import zipfile

import pytest

from test_playback_presentation import scene, submit, view
from test_ce_general_installer import environment, signing

ROOT = Path(__file__).resolve().parents[2]
SKIN = ROOT / 'addons/skin.bobbi.cinema/1080p'
BOBBI = ROOT / 'addons/plugin.video.bobbi'
SCRIPTS = ROOT / 'third_party/addons/script.skinvariables/resources/lib'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


osd = load('tested_bobbi_osd', BOBBI / 'lib/services/osd_playback.py')


class Window:
    def __init__(self):
        self.props = {}

    def getProperty(self, key):
        return self.props.get(key, '')

    def setProperty(self, key, value):
        self.props[key] = value

    def clearProperty(self, key):
        self.props.pop(key, None)


@pytest.fixture
def client(scene):
    return osd.Client(scene[0].dispatch, Window())


@pytest.fixture
def ui(monkeypatch, client, tmp_path):
    calls, notices = [], []
    dialog = SimpleNamespace(numeric=lambda *a: '', select=lambda *a: -1)
    monkeypatch.setattr(osd, 'client', lambda: client)
    monkeypatch.setattr(osd, '_notice', notices.append)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(executebuiltin=calls.append,
                                                          getCondVisibility=lambda _: False))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: dialog))
    import bobbi_platform.kodi
    monkeypatch.setattr(bobbi_platform.kodi, 'rpc',
                        lambda method, params: calls.append((method, params)))
    # Keep production InstanceLock in this route, isolate only its disk location.
    import bobbi_platform.paths
    monkeypatch.setattr(bobbi_platform.paths, 'profile', lambda **kw: tmp_path / kw['name'])
    return SimpleNamespace(calls=calls, notices=notices, dialog=dialog)


@pytest.fixture
def directory_ui(monkeypatch, ui):
    """Only Kodi's directory boundary is doubled; the owned renderer is real."""
    class Item(Window):
        def __init__(self, label='', label2='', path='', offscreen=False):
            super().__init__()
            self.path, self.label, self.label2 = path, label, label2

        def setProperties(self, values):
            self.props.update(values)

        def getPath(self):
            return self.path

    result = SimpleNamespace(rows=[], completions=[])
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=Item, Dialog=lambda: ui.dialog))
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        addDirectoryItems=lambda handle, items: result.rows.append((handle, items)),
        endOfDirectory=lambda handle, **kwargs: result.completions.append((handle, kwargs))))
    return result


def capture(client, kind='audio'):
    value = client.read()
    row = value['audio' if kind == 'audio' else 'subtitles'][0]
    return client.capture(value, 'audio_stream' if kind == 'audio' else 'manual_subtitle_stream',
                          dict(index=row['index'], stream_key=row['stream_key']))


@pytest.fixture
def phone_api(scene):
    phone = load('osd_cross_entry_phone', ROOT / 'addons/plugin.video.bobbi/lib/services/phone_management.py')
    account = dict(provider='quark', account_id='quark:' + 'a' * 64, epoch=1, authenticated=True)
    scene[0].selection_account = account
    scene[0].configure_accounts(SimpleNamespace(run_if_current=lambda scope, callback: callback()))
    def rpc(action, body, **kwargs):
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', account=account)])
        assert action == 'playback'
        return scene[0].dispatch(body)
    origin = 'http://127.0.0.1:8081'
    manager = phone.PhoneManagement(account, origin, rpc=rpc, scopes=phone.PLAYBACK_SCOPES)
    headers = dict(Host='127.0.0.1:8081', Origin=origin)
    result, cookie = manager.handle('/manage/api/pair', headers,
        phone.encode(dict(code=manager.pairing_url.split('#')[1])))
    headers.update(Cookie=cookie.split(';')[0], **{'X-Bobbi-CSRF': result['csrf']})
    def invoke(action, params=None):
        return manager.handle('/manage/api', headers, phone.encode(
            dict(action=action, params=params or {})))[0]
    return invoke


@pytest.mark.parametrize('action', ['refresh', 'seek', 'chapters'])
def test_open_render_cancel_and_read_are_pure(scene, client, ui, action):
    before = deepcopy(scene[0].owner.snapshot())
    osd.run(action)
    assert scene[1].commands == [] and scene[1].gui_commands == []
    assert scene[0].owner.snapshot() == before
    assert ui.calls == []


@pytest.mark.parametrize('kind', ['audio', 'subtitle'])
def test_osd_stream_carries_exact_same_projection_as_phone(scene, client, ui, phone_api, kind):
    original = capture(client, kind)
    assert original['expected'] == phone_api('playback_presentation')['expected']
    result = osd.run('apply', token=osd.encode(original))
    assert result['status'] == 'queued'
    native = scene[1].commands[0]
    assert native['command_id'] == original['command_id']
    assert native['index'] == 0 and native['stream_key'] == original['params']['stream_key']
    assert native['expected_sequence'] == original['expected']['expected_sequence']
    assert ui.calls == []


@pytest.mark.parametrize('kind', ['audio', 'subtitle'])
def test_phone_manual_action_invalidates_old_osd_capture_without_rebase(scene, client, ui, phone_api, kind):
    captured = capture(client, kind)
    phone = dict(expected=phone_api('playback_presentation')['expected'], command_id=uuid4().hex,
                 action='subtitle_visible', params=dict(visible=False))
    result = phone_api('playback_command', phone)
    assert result['status'] == 'queued'
    native = scene[1]
    # Model the native actor actually applying the phone command, not just queued.
    native.current['user_intent'] += 1
    native.current['subtitle_intent'] += 1
    native.current['sequence'] += 1
    osd.run('apply', token=osd.encode(captured))
    assert len(native.commands) == 1 and native.commands[0]['command_id'] == phone['command_id']
    assert ui.notices == ['rejected'] and ui.calls == []


def test_osd_action_invalidates_previously_rendered_phone_controls(scene, client, ui, phone_api):
    phone_view = phone_api('playback_presentation')
    osd.run('apply', token=osd.encode(capture(client)))
    scene[1].current['sequence'] += 1
    scene[1].current['user_intent'] += 1
    scene[1].current['audio_intent'] += 1
    old_phone = dict(expected=phone_view['expected'], command_id=uuid4().hex,
                     action='seek', params=dict(position_ms=20000))
    assert phone_api('playback_command', old_phone)['status'] == 'rejected'
    assert len(scene[1].commands) == 1 and scene[1].commands[0]['action'] == 'audio_stream'
    assert ui.calls == []


@pytest.mark.parametrize('entry', ['seek', 'chapters'])
def test_interactive_seek_keeps_scope_from_before_dialog(scene, client, ui, entry):
    original = scene[1].subtitles
    scene[1].subtitles = lambda: dict(original(), chapters=[dict(name='第二章', position_ms=20000)])
    def changed(*args):
        scene[1].current['native_instance'] = str(uuid4())
        return '20' if entry == 'seek' else 0
    ui.dialog.numeric = changed
    ui.dialog.select = changed
    osd.run(entry)
    assert scene[1].commands == [] and ui.calls == []
    assert ui.notices == ['rejected']


@pytest.mark.parametrize('entry,position', [('seek_back', 0), ('seek_forward', 32000),
    ('chapter_previous', 0), ('chapter_next', 20000), ('chapters', 20000), ('seek', 20000)])
def test_seek_and_chapters_use_same_instance_bound_seek(scene, client, ui, entry, position):
    original = scene[1].subtitles
    scene[1].subtitles = lambda: dict(original(), chapters=[
        dict(name='开始', position_ms=0), dict(name='第二章', position_ms=20000)])
    ui.dialog.numeric = lambda *a: '20'
    ui.dialog.select = lambda *a: 1
    osd.run(entry)
    assert len(scene[1].commands) == 1
    actual = scene[1].commands[0]
    assert actual['action'] == 'seek' and actual['position_ms'] == position
    assert actual['native_instance'] == scene[1].current['native_instance']
    assert actual['control_protocol'] == 1 and ui.calls == []


def test_lost_submit_persists_original_before_ipc_and_only_receipt_on_reopen(scene, client, ui):
    native, original_control = scene[1], scene[1].control
    def lost(command):
        assert osd.decode(client.window.getProperty(osd.PENDING))['command_id'] == command['command_id']
        original_control(command)
        raise OSError('lost reply')
    native.control = lost
    first = capture(client)
    assert osd.run('apply', token=osd.encode(first))['status'] == 'unknown'
    # A separate script instance and newly rendered row cannot silently resend.
    fresh_client = osd.Client(scene[0].dispatch, client.window)
    newer = capture(fresh_client)
    assert newer['command_id'] != first['command_id']
    assert fresh_client.submit(newer)['status'] == 'unknown'
    assert fresh_client.submit(first)['status'] == 'unknown'
    assert len(native.commands) == 1
    assert osd.decode(client.window.getProperty(osd.PENDING)) == first
    assert scene[0].event('xbmc', 'Player.OnBobiControl', dict(native.commands[0], status='applied'))
    assert fresh_client.submit(first)['status'] == 'applied'
    assert len(native.commands) == 1 and ui.calls == []


def test_transport_reply_loss_does_not_repost_a_command_even_if_owner_never_received(client):
    requests = []
    original = capture(client)
    def lost(message):
        requests.append(message)
        raise OSError('IPC unavailable')
    client.call = lost
    assert client.submit(original)['status'] == 'unknown'
    assert client.submit(original)['status'] == 'unknown'
    assert [row['operation'] for row in requests] == ['playback_command', 'playback_receipt']


def test_retired_instance_unknown_is_preserved_without_blocking_verified_new_movie(client):
    first = capture(client)
    client.window.setProperty(client.pending_key, osd.encode(first))
    fresh = deepcopy(client.read())
    fresh['expected']['native_instance'] = str(uuid4())
    fresh['expected']['boot_id'] = uuid4().hex
    calls = []
    def restarted(request):
        calls.append(request)
        if request['operation'] == 'playback_receipt':
            return dict(command_id=request['command_id'], status='unknown')
        if request['operation'] == 'playback_presentation':
            return fresh
        return dict(command_id=request['command']['command_id'], status='queued')
    client.call = restarted
    current = capture(client)
    assert client.submit(current)['status'] == 'queued'
    assert osd.decode(client.window.getProperty(client.pending_key + '.PreviousUnknown')) == first
    assert osd.decode(client.window.getProperty(client.pending_key)) == current
    assert sum(row['operation'] == 'playback_command' for row in calls) == 1


def test_forged_different_instance_cannot_discard_an_unknown_original(client):
    first = capture(client)
    client.window.setProperty(client.pending_key, osd.encode(first))
    changed = deepcopy(first)
    changed['command_id'] = uuid4().hex
    changed['expected']['native_instance'] = str(uuid4())
    assert client.submit(changed)['status'] == 'unknown'
    assert osd.decode(client.window.getProperty(client.pending_key)) == first


def test_pending_record_uses_same_profile_boundary_as_lock(client):
    a = osd.Client(client.call, client.window, pending_key='OSD.profile-A')
    b = osd.Client(client.call, client.window, pending_key='OSD.profile-B')
    first = capture(a)
    a.window.setProperty(a.pending_key, osd.encode(first))
    assert not b.window.getProperty(b.pending_key)
    assert a.window.getProperty(a.pending_key)


def test_client_binds_runtime_once_and_profiles_have_separate_slots(monkeypatch, tmp_path):
    import bobbi_platform.paths
    import bobbi_platform.runtime
    root = [tmp_path / 'A']
    calls = []
    window = Window()
    def bind(path):
        def bound(action, body, timeout):
            calls.append((path, action, body, timeout))
            return dict(available=False, mode='standard')
        return bound
    monkeypatch.setattr(bobbi_platform.paths, 'profile_root', lambda: root[0])
    monkeypatch.setattr(bobbi_platform.runtime, 'bind_call', bind)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda _: window))
    a = osd.client()
    root[0] = tmp_path / 'B'
    b = osd.client()
    a.read()
    b.read()
    assert calls[0][0] == tmp_path / 'A/runtime.json'
    assert calls[1][0] == tmp_path / 'B/runtime.json'
    assert a.pending_key != b.pending_key
    assert a.lock_path.parent == tmp_path / 'A' and b.lock_path.parent == tmp_path / 'B'


def test_render_rejects_incomplete_managed_projection(client):
    incomplete = {'available': True, 'mode': 'managed', 'expected': client.read()['expected']}
    client.call = lambda _: incomplete
    assert client.read() == dict(available=False, mode='unavailable')


def test_external_publication_clears_old_bobbi_status(client):
    osd.publish(client.read(), client.window)
    assert client.window.getProperty('AM6B.AudioState')
    osd.publish(dict(available=False, mode='external'), client.window)
    assert not client.window.getProperty('AM6B.AudioState')
    assert not client.window.getProperty('AM6B.SubtitleState')


def test_visibility_is_captured_absolute_value_and_cannot_fall_back_after_switch(scene, client, ui):
    value = client.read()
    token = osd.encode(client.capture(value, 'subtitle_visible', dict(visible=not value['subtitle_visible'])))
    assert osd.decode(token)['params'] == {'visible': False}
    # Capture remains scoped even when the current native playback is external.
    scene[1].current['request_id'] = ''
    osd.run('subtitle_toggle', token=token)
    assert scene[1].commands == [] and ui.calls == []
    assert ui.notices == ['rejected']


@pytest.mark.parametrize('value', [None, {}, {'available': False},
    {'available': False, 'mode': 'managed'}, {'available': True, 'mode': 'external'},
    {'available': True, 'mode': 'managed', 'expected': {}}, OSError('down')])
@pytest.mark.parametrize('entry', ['seek_back', 'chapter_next', 'audio_settings', 'subtitle_settings'])
def test_unavailable_or_malformed_cannot_authorize_native_fallback(client, ui, value, entry):
    def reply(_):
        if isinstance(value, Exception):
            raise value
        return value
    client.call = reply
    osd.run(entry)
    assert ui.calls == [] and ui.notices == ['unavailable']


@pytest.mark.parametrize('mode', ['external', 'standard'])
@pytest.mark.parametrize('entry,native', [('seek_back', 'Seek(-10)'),
    ('chapter_next', 'PlayerControl(Next)'), ('audio_settings', 'ActivateWindow(OSDAudioSettings)'),
    ('subtitle_settings', 'ActivateWindow(OSDSubtitleSettings)'), ('chapters', 'ActivateWindow(videobookmarks)')])
def test_explicit_ordinary_modes_retain_native_interaction(client, ui, mode, entry, native):
    requests = []
    client.call = lambda request: requests.append(request) or dict(mode=mode, available=False)
    osd.run(entry)
    assert ui.calls == [native]
    assert all(row['operation'] == 'playback_presentation' for row in requests)
    assert not client.window.getProperty(osd.PENDING)


def test_external_list_capture_cannot_control_new_managed_playback(scene, client, ui):
    osd.run('apply', token=osd.encode(dict(native_stream='audio', index=0)))
    osd.run('subtitle_toggle', token=osd.encode(dict(native_toggle=True)))
    assert ui.calls == [] and scene[1].commands == []
    assert ui.notices == ['rejected', 'rejected']


@pytest.mark.parametrize('kind,method', [('audio', 'Player.SetAudioStream'), ('subtitle', 'Player.SetSubtitle')])
def test_ordinary_stream_selection_is_native_without_fabricated_scope(client, ui, kind, method):
    client.call = lambda _: dict(mode='standard', available=False)
    osd.run('apply', token=osd.encode(dict(native_stream=kind, index=0)))
    assert ui.calls[0][0] == method and not client.window.getProperty(osd.PENDING)


def test_managed_full_settings_are_not_a_global_control_escape(scene, client, ui):
    osd.run('audio_settings')
    osd.run('subtitle_settings')
    assert ui.calls == [] and scene[1].commands == []


@pytest.mark.parametrize('kind', ['audio', 'subtitle'])
def test_real_directory_uses_shared_projection_and_keeps_zero_index(scene, client, ui, directory_ui, kind):
    before = deepcopy(scene[0].owner.snapshot())
    osd.stream_directory(7, kind)
    handle, items = directory_ui.rows[0]
    path, row, is_folder = items[0]
    assert handle == 7 and is_folder is False
    assert directory_ui.completions == [(7, {'cacheToDisc': False})]
    assert row.getProperty('index') == '0' and row.getProperty('iscurrent') == 'true'
    captured = osd.decode(row.getProperty('bobbi_command'))
    assert captured['expected'] == view(scene)['expected']
    assert captured['params']['index'] == 0
    url = urlsplit(path)
    assert url.scheme == 'plugin' and url.netloc == 'plugin.video.bobbi'
    assert parse_qs(url.query) == dict(action=['osd_apply'], token=[row.getProperty('bobbi_command')])
    assert scene[1].commands == [] and ui.calls == [] and scene[0].owner.snapshot() == before
    assert osd.apply(client, row.getProperty('bobbi_command'))['status'] == 'queued'


def test_reopening_same_stream_menu_never_publishes_old_capture(scene, client, ui, directory_ui):
    def opening():
        client.window.setProperty(osd.STREAM_PANEL, 'opening-audio')
        osd.begin_stream_panel(client.window, 'audio', lambda: True)
        return client.window.getProperty(osd.STREAM_PANEL)
    first, second = opening(), opening()
    assert first != second and len(first) == len(second) == 32
    osd.stream_directory(7, 'audio', first)
    assert directory_ui.rows[-1] == (7, [])
    osd.stream_directory(8, 'audio', second)
    row = directory_ui.rows[-1][1][0][1]
    assert row.getProperty('bobbi_panel') == second
    assert osd.decode(row.getProperty('bobbi_command'))['expected'] == view(scene)['expected']
    assert scene[1].commands == [] and ui.calls == []


def test_closed_stream_menu_cannot_publish_late_view(scene, client, ui, directory_ui, monkeypatch):
    panel = 'a' * 32
    client.window.setProperty(osd.STREAM_PANEL, panel)
    read = client.read
    def close_during_read():
        client.window.clearProperty(osd.STREAM_PANEL)
        return read()
    monkeypatch.setattr(client, 'read', close_during_read)
    osd.stream_directory(7, 'audio', panel)
    assert directory_ui.rows[-1] == (7, []) and scene[1].commands == [] and ui.calls == []


def test_transient_missing_projection_only_rereads_while_panel_current(scene, client, ui, directory_ui, monkeypatch):
    panel = 'b' * 32
    client.window.setProperty(osd.STREAM_PANEL, panel)
    read = client.read
    views = iter([dict(mode='unavailable', available=False), read()])
    monkeypatch.setattr(client, 'read', lambda: next(views))
    monkeypatch.setattr(osd.time, 'sleep', lambda _: None)
    osd.stream_directory(7, 'audio', panel)
    assert directory_ui.rows[-1][1][0][1].getProperty('bobbi_panel') == panel
    assert scene[1].commands == [] and ui.calls == []


def test_stream_buttons_cannot_submit_another_menus_row():
    control = ET.parse(SKIN / 'Includes_OSD.xml').find(".//include[@name='StreamPicker']//control[@id='2021']")
    assert control.findtext('enable') == '$EXP[BobbiCurrentStreamPanel]'
    assert all(c.attrib.get('condition') == '$EXP[BobbiCurrentStreamPanel]' for c in control.findall('onclick'))
    assert control.findtext('content') == '$VAR[BobbiStreamFetchPanel,plugin://plugin.video.bobbi/?action=osd_streams&stream_type=$PARAM[type]&panel=,]'


def test_subtitle_list_toggle_stays_with_original_list_when_another_view_is_published(scene, client, ui, directory_ui):
    osd.stream_directory(7, 'subtitle')
    row = directory_ui.rows[0][1][0][1]
    token = row.getProperty('bobbi_toggle')
    captured = osd.decode(token)
    scene[1].current['user_intent'] += 1
    scene[1].current['subtitle_intent'] += 1
    scene[1].current['sequence'] += 1
    osd.publish(client.read(), client.window)
    assert row.getProperty('bobbi_toggle') == token
    assert osd.decode(token) == captured
    osd.apply(client, token)
    assert ui.notices == ['rejected'] and scene[1].commands == [] and ui.calls == []


@pytest.mark.parametrize('mode', ['standard', 'external'])
@pytest.mark.parametrize('kind,key,current', [
    ('audio', 'audiostreams', 'currentaudiostream'),
    ('subtitle', 'subtitles', 'currentsubtitle')])
def test_ordinary_directory_uses_unwrapped_platform_rpc_and_native_tokens(
        client, ui, directory_ui, monkeypatch, mode, kind, key, current):
    import bobbi_platform.kodi
    client.call = lambda _: dict(mode=mode, available=False)

    def rpc(method, params):
        ui.calls.append((method, params))
        return {key: [dict(index=0, language='zh', name='原声')], current: dict(index=0)}

    monkeypatch.setattr(bobbi_platform.kodi, 'rpc', rpc)
    osd.stream_directory(7, kind)
    row = directory_ui.rows[0][1][0][1]
    assert row.getProperty('index') == '0' and row.getProperty('iscurrent') == 'true'
    assert osd.decode(row.getProperty('bobbi_command')) == dict(native_stream=kind, index=0)
    assert osd.decode(row.getProperty('bobbi_toggle')) == dict(native_toggle=True)
    assert ui.calls == [('Player.GetProperties', dict(playerid=1, properties=[key, current]))]
    assert directory_ui.completions == [(7, {'cacheToDisc': False})]


@pytest.mark.parametrize('value', [None, {}, {'available': False, 'mode': 'managed'},
    {'available': True, 'mode': 'external'}, OSError('down')])
def test_directory_unknown_scope_is_empty_without_global_rpc(client, ui, directory_ui, value):
    def reply(_):
        if isinstance(value, Exception):
            raise value
        return value

    client.call = reply
    osd.stream_directory(7, 'audio')
    assert directory_ui.rows == [(7, [])]
    assert directory_ui.completions == [(7, {'cacheToDisc': False})]
    assert ui.calls == []


def test_owned_osd_module_load_does_not_import_vendor_player_helpers(monkeypatch):
    original_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name.startswith(('jurialmunkey', 'resources.lib')):
            raise AssertionError('Owned OSD must not import vendor player helpers: ' + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guard)
    module = load('owned_osd_without_vendor', BOBBI / 'lib/services/osd_playback.py')
    assert callable(module.run) and callable(module.stream_directory)


@pytest.fixture
def script_entry(monkeypatch):
    monkeypatch.setitem(sys.modules, 'lib.boot_gate', SimpleNamespace(ready=lambda: True))
    monkeypatch.setitem(sys.modules, 'lib.services.osd_playback', osd)
    return load('tested_owned_osd_script', BOBBI / 'osd.py')


@pytest.mark.parametrize('use_sys_argv', [False, True])
def test_owned_script_passes_original_capture_to_real_client(
        scene, client, ui, script_entry, monkeypatch, use_sys_argv):
    captured = capture(client)
    args = ['bobbi_osd=apply', 'token=' + osd.encode(captured)]
    if use_sys_argv:
        monkeypatch.setattr(sys, 'argv', ['osd.py'] + args)
        result = script_entry.main()
    else:
        result = script_entry.main(args)
    assert result['status'] == 'queued'
    assert scene[1].commands[0]['command_id'] == captured['command_id']
    assert scene[1].commands[0]['expected_sequence'] == captured['expected']['expected_sequence']
    assert ui.calls == []


@pytest.mark.parametrize('args', [[], ['token=unused']])
def test_owned_script_without_action_does_not_control_playback(scene, ui, script_entry, args):
    script_entry.main(args)
    assert scene[1].commands == [] and ui.calls == []


@pytest.mark.parametrize('args', [
    ['seek_forward'], ['bobbi_osd=seek_forward', 'unexpected=x'],
    ['bobbi_osd=seek_back', 'bobbi_osd=seek_forward'],
    ['bobbi_osd=apply', 'token=first', 'token=second']])
def test_owned_script_rejects_ambiguous_or_unknown_parameters(scene, ui, script_entry, args):
    script_entry.main(args)
    assert scene[1].commands == [] and ui.calls == []
    assert ui.notices == ['rejected']


def test_owned_script_boot_gate_failure_does_not_control_playback(
        scene, ui, script_entry, monkeypatch):
    monkeypatch.setitem(sys.modules, 'lib.boot_gate', SimpleNamespace(ready=lambda: False))
    monkeypatch.setitem(sys.modules, 'lib.services.osd_playback', None)
    script_entry.main(['bobbi_osd=seek_forward'])
    assert scene[1].commands == [] and ui.calls == []
    assert ui.notices == []


@pytest.mark.parametrize('kind', ['audio', 'subtitle'])
def test_owned_router_reaches_real_read_only_stream_directory(
        scene, ui, directory_ui, script_entry, monkeypatch, kind):
    monkeypatch.setattr(sys, 'argv', [
        'plugin://plugin.video.bobbi/', '7', '?action=osd_streams&stream_type=' + kind])
    router = load('tested_owned_osd_router', BOBBI / 'lib/router.py')
    before = deepcopy(scene[0].owner.snapshot())
    router.addon_router()
    assert directory_ui.rows[0][0] == 7 and len(directory_ui.rows[0][1]) == 1
    assert directory_ui.completions == [(7, {'cacheToDisc': False})]
    assert scene[1].commands == [] and ui.calls == []
    assert scene[0].owner.snapshot() == before


def test_owned_list_path_dispatches_original_capture_once(
        scene, client, ui, directory_ui, script_entry, monkeypatch):
    osd.stream_directory(7, 'audio')
    path, row, _ = directory_ui.rows[0][1][0]
    captured = osd.decode(row.getProperty('bobbi_command'))
    monkeypatch.setattr(sys, 'argv', [
        'plugin://plugin.video.bobbi/', '7', '?' + urlsplit(path).query])
    router = load('tested_owned_osd_apply_router', BOBBI / 'lib/router.py')
    assert router.addon_router()['status'] == 'queued'
    assert router.addon_router()['status'] == 'queued'
    assert len(scene[1].commands) == 1
    assert scene[1].commands[0]['command_id'] == captured['command_id']
    assert directory_ui.completions == [(7, {'cacheToDisc': False})] * 3
    assert ui.calls == []


@pytest.fixture(scope='module')
def packaged_osd(tmp_path_factory):
    """Use the release archiver on the complete real addon, not a hand-built ZIP."""
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(ROOT / 'tools'))
        builder = load('osd_delivery_release_builder', ROOT / 'tools/build_release.py')
        inventory = builder.files(BOBBI)
        path = tmp_path_factory.mktemp('owned-osd-package') / 'plugin.video.bobbi.zip'
        builder.archive(BOBBI, inventory, path)
    return SimpleNamespace(path=path, inventory=inventory,
        version=ET.parse(BOBBI / 'addon.xml').getroot().get('version'))


def test_real_release_zip_contains_owned_osd_and_matches_reviewed_inventory(packaged_osd):
    reviewed = json.loads((ROOT / 'release/source-inventory.json').read_text(encoding='utf-8'))
    assert packaged_osd.inventory == reviewed['components']['plugin.video.bobbi']
    with zipfile.ZipFile(packaged_osd.path) as archive:
        assert set(archive.namelist()) == {'plugin.video.bobbi/' + name for name in packaged_osd.inventory}
        for name in ('osd.py', 'lib/services/osd_playback.py', 'lib/router.py', 'addon.xml'):
            raw = archive.read('plugin.video.bobbi/' + name)
            assert hashlib.sha256(raw).hexdigest() == packaged_osd.inventory[name]
        addon = ET.fromstring(archive.read('plugin.video.bobbi/addon.xml'))
        assert addon.find("extension[@point='xbmc.python.script']").get('library') == 'osd.py'
        imports = {node.get('addon') for node in addon.findall('requires/import')}
        assert {'script.module.bobbi.core', 'script.module.bobbi.platform'} <= imports
        assert 'script.skinvariables' not in imports and 'script.module.jurialmunkey' not in imports


@pytest.mark.parametrize('upstream_version', ['original', '99.0.0'])
def test_signed_install_preserves_upstream_and_installed_owned_osd_still_runs(
        environment, signing, packaged_osd, scene, ui, directory_ui, monkeypatch, upstream_version):
    """Real ZIP/signature/installer/dependency code; Kodi and native remain simulated."""
    import test_ce_general_installer as installer_tests
    from bobbi_platform.ce_install_ui import KodiHost
    from bobbi_platform.upstream_addons import UPSTREAM_COMPONENTS

    env = environment
    for name in UPSTREAM_COMPONENTS:
        shutil.copy2(ROOT / 'third_party/addons' / name / 'addon.xml', env.addons / name / 'addon.xml')
    vendor = env.addons / 'script.skinvariables'
    shutil.copytree(ROOT / 'third_party/addons/script.skinvariables', vendor, dirs_exist_ok=True)
    if upstream_version != 'original':
        manifest = ET.parse(vendor / 'addon.xml')
        manifest.getroot().set('version', upstream_version)
        manifest.write(vendor / 'addon.xml', encoding='utf-8')
    version_before = ET.parse(vendor / 'addon.xml').getroot().get('version')

    def vendor_hashes():
        return {path.relative_to(vendor).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in vendor.rglob('*') if path.is_file()}

    before = vendor_hashes()
    assert 'resources/lib/bobbi_playback.py' not in before
    assert 'bobbi_osd' not in (vendor / 'resources/lib/script.py').read_text(encoding='utf-8')
    dependency_host = KodiHost.__new__(KodiHost)

    def details(name):
        if name == 'script.module.pycryptodome':
            return dict(version='3.4.3', enabled=True)
        path = env.addons / name / 'addon.xml'
        return dict(version=ET.parse(path).getroot().get('version'), enabled=True) if path.exists() else None

    dependency_host.details = details
    dependency_host.xbmc = SimpleNamespace(executebuiltin=lambda *args: pytest.fail('Existing upstream must be preserved'))

    def dependencies(stage):
        env.calls.append('dependencies')
        dependency_host.dependencies(stage)

    env.host.dependencies = dependencies
    original_archive = installer_tests.archive
    monkeypatch.setattr(installer_tests, 'archive', lambda name, version:
        packaged_osd.path.read_bytes() if name == 'plugin.video.bobbi' else original_archive(name, version))
    owned_versions = {p.parent.name: ET.parse(p).getroot().get('version') for p in (ROOT / 'addons').glob('*/addon.xml')}
    bundle = installer_tests.package(env.root / 'owned-osd-signed.zip', signing, version=packaged_osd.version, versions=owned_versions)
    env.installer.apply(bundle)
    assert env.calls == ['dependencies', 'quiesce', 'refresh', 'verify', 'activate']
    assert vendor_hashes() == before
    assert details('script.skinvariables')['version'] == version_before
    assert (vendor / 'origin').read_text() == 'original-kodi-repository'

    installed = env.addons / 'plugin.video.bobbi'
    for name in ('osd.py', 'lib/services/osd_playback.py', 'lib/router.py', 'addon.xml'):
        assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == packaged_osd.inventory[name]
    original_import = builtins.__import__

    def no_vendor_import(name, *args, **kwargs):
        if name.startswith(('jurialmunkey', 'resources.lib')):
            raise AssertionError('Installed owned OSD imported a vendor helper: ' + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_vendor_import)
    installed_osd = load('installed_owned_osd', installed / 'lib/services/osd_playback.py')
    installed_client = installed_osd.Client(scene[0].dispatch, Window())
    monkeypatch.setattr(installed_osd, 'client', lambda: installed_client)
    monkeypatch.setattr(installed_osd, '_notice', ui.notices.append)
    monkeypatch.setitem(sys.modules, 'lib.services.osd_playback', installed_osd)
    boot_gate = load('installed_owned_osd_boot_gate', installed / 'lib/boot_gate.py')
    monkeypatch.setitem(sys.modules, 'lib.boot_gate', boot_gate)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda path: str(env.work / 'installation.json')))
    assert boot_gate.ready()
    entry = load('installed_owned_osd_entry', installed / 'osd.py')
    router = load('installed_owned_osd_router', installed / 'lib/router.py')

    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '7', '?action=osd_streams&stream_type=audio'])
    router.addon_router()
    path, item, _ = directory_ui.rows[0][1][0]
    token = item.getProperty('bobbi_command')
    captured = installed_osd.decode(token)
    assert captured['expected'] == view(scene)['expected']
    assert scene[1].commands == []
    assert entry.main(['bobbi_osd=apply', 'token=' + token])['status'] == 'queued'
    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '7', '?' + urlsplit(path).query])
    assert router.addon_router()['status'] == 'queued'
    assert len(scene[1].commands) == 1
    assert scene[1].commands[0]['command_id'] == captured['command_id']
    assert ui.calls == [] and vendor_hashes() == before


def test_skin_has_no_global_stream_or_video_seek_escape_and_transports_capture_tokens():
    video = ET.parse(SKIN / 'VideoOSD.xml').getroot()
    clicks = [node.text for node in video.iter('onclick')]
    assert not {'Seek(-10)', 'Seek(30)', 'PlayerControl(Previous)', 'PlayerControl(Next)'} & set(clicks)
    assert video.find(".//control[@type='slider']") is None
    picker = ET.parse(SKIN / 'Includes_OSD.xml').getroot().find("include[@name='StreamPicker']")
    text = ET.tostring(picker, encoding='unicode')
    assert 'ShowSubtitles' not in text and 'ActivateWindow($PARAM[full])' not in text
    assert 'token=$INFO[ListItem.Property(bobbi_command)]' in text
    assert 'token=$INFO[Container(2021).ListItem.Property(bobbi_toggle)]' in text
    assert 'Window(Home).Property(Bobbi.OSD.SubtitleToggle)' not in text
    assert 'plugin://plugin.video.bobbi/?action=osd_streams&amp;stream_type=$PARAM[type]' in text
    options = (SKIN / 'custom_OptionsDialog.xml').read_text(encoding='utf-8')
    assert '<onclick>ActivateWindow(videobookmarks)</onclick>' not in options
    assert 'bobbi_osd=chapters' in options
    for path in SKIN.glob('*.xml'):
        document = path.read_text(encoding='utf-8')
        assert 'RunScript(script.skinvariables,bobbi_osd=' not in document, path.name
        assert 'plugin://script.skinvariables/?info=get_player_streams' not in document, path.name


def test_owned_script_declares_runtime_dependencies_and_vendor_is_not_bobbi_owner():
    addon = ET.parse(BOBBI / 'addon.xml').getroot()
    imports = {node.get('addon') for node in addon.findall('requires/import')}
    assert {'script.module.bobbi.core', 'script.module.bobbi.platform'} <= imports
    assert addon.find("extension[@point='xbmc.python.script']").get('library') == 'osd.py'
    vendor = ET.parse(SCRIPTS.parent.parent / 'addon.xml').getroot()
    vendor_imports = {node.get('addon') for node in vendor.findall('requires/import')}
    assert not {'script.module.bobbi.core', 'script.module.bobbi.platform'} & vendor_imports
    assert "'bobbi_osd':" not in (SCRIPTS / 'script.py').read_text()
    assert not (SCRIPTS / 'bobbi_playback.py').exists()
    assert 'bobbi_playback' not in (SCRIPTS / 'lists/playerstreams.py').read_text()
    assert 'bobbi_playback' not in (SCRIPTS / 'method.py').read_text()


def test_seeded_popup_consumes_new_display_nonce_not_a_cached_command(scene, client, ui, directory_ui):
    next_key = 'Bobbi.OSD.NextStreamPanel'
    osd.publish(client.read(), client.window)
    first = client.window.getProperty(next_key)
    assert len(first) == 32 and client.window.getProperty(osd.STREAM_PANEL) == ''
    osd.publish(client.read(), client.window)
    assert client.window.getProperty(next_key) == first  # no warm-up invalidation
    for i in (1, 2):
        live = client.window.getProperty(next_key)
        client.window.setProperty(osd.STREAM_PANEL, live)
        client.window.clearProperty(next_key)
        osd.stream_directory(i, 'audio', live)
        assert client.window.getProperty('Bobbi.OSD.StreamPanelRead') == live
        assert len(client.window.getProperty(next_key)) == 32 and client.window.getProperty(next_key) != live
        _, rows = directory_ui.rows[-1]
        assert rows[0][1].getProperty('bobbi_panel') == live
    osd.stream_directory(3, 'audio', first)
    assert directory_ui.rows[-1] == (3, [])
    assert client.window.getProperty('Bobbi.OSD.StreamPanelRead') == live
    assert not scene[1].commands and not ui.calls


@pytest.mark.parametrize('name,kind', [('Custom_1145_OSD_audio.xml','audio'), ('Custom_1144_OSD_subtitles.xml','subtitle')])
def test_seeded_dialog_uses_one_snapshot_and_does_not_launch_refresh(name, kind):
    root = ET.parse(SKIN / name).getroot()
    actions = root.findall('onload')
    assert [x.text for x in actions] == [
        'SetProperty(Bobbi.OSD.StreamPanel,$VAR[BobbiNextStreamPanel],Home)',
        'RunScript(plugin.video.bobbi,bobbi_osd=open_' + kind + '_panel)',
        'ClearProperty(Bobbi.OSD.NextStreamPanel,Home)']
    assert actions[1].get('condition') == ('String.IsEmpty(Window(Home).Property(Bobbi.OSD.NextStreamPanel))'
            ' | String.IsEqual(Window(Home).Property(Bobbi.OSD.StreamPanel),opening)')
    variables = ET.parse(SKIN / 'Variables.xml').getroot()
    gate = variables.find("variable[@name='BobbiStreamFetchPanel']/value")
    assert '!String.StartsWith(Window(Home).Property(Bobbi.OSD.StreamPanel),opening)' in gate.get('condition')
    assert gate.text == '$INFO[Window(Home).Property(Bobbi.OSD.StreamPanel)]'
    assert root.findtext('onunload') == 'ClearProperty(Bobbi.OSD.StreamPanel,Home)'


def test_popup_product_entry_does_not_load_or_mutate_catalogue_views(scene, ui, directory_ui, script_entry, monkeypatch):
    import runpy
    router = load('tested_popup_main_router', BOBBI / 'lib/router.py')
    monkeypatch.setitem(sys.modules, 'lib.router', router)
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', None)
    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '9', '?action=osd_streams&stream_type=audio'])
    runpy.run_path(str(BOBBI / 'bobbi.py'))
    assert directory_ui.rows[0][0] == 9 and directory_ui.rows[0][1][0][1].getProperty('index') == '0'
    assert directory_ui.completions == [(9, {'cacheToDisc': False})] and not scene[1].commands
