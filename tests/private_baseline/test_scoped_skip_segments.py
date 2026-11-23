"""An inherited skip popup must never seek whatever happens to play now."""
import json
from types import SimpleNamespace
from copy import deepcopy
from threading import Event

import pytest

import xbmc

from bobbi_core.playback_request import Client
from lib.gui.skip_intro_window import SkipIntroWindow


def test_legacy_unscoped_popup_cannot_seek_a_replacement_player(monkeypatch):
    seeks = []
    player = SimpleNamespace(isPlaying=lambda: True, seekTime=seeks.append)
    monkeypatch.setattr(xbmc, 'Player', lambda: player)
    popup = SkipIntroWindow('skip_intro.xml', '', segment_data={'end_sec': 90})
    popup._do_skip()
    assert seeks == []


def test_scoped_popup_submits_once_and_never_replays_after_unknown_reply(monkeypatch):
    calls=[]
    def lost(body):
        calls.append(body)
        raise OSError('lost reply')
    context=dict(boot_id='a'*32,epoch=1,request_id='b'*32,native_instance='original',expected={'user_intent':0})
    popup=SkipIntroWindow('skip_intro.xml','',segment_data={'segment_id':'c'*64},context=context,
        playback_client=Client(lost))
    assert not popup._do_skip() and not popup._do_skip()
    assert len(calls)==1 and calls[0]['native_instance']=='original'
    assert calls[0]['operation']=='segment_action' and len(calls[0]['command_id'])==32


@pytest.mark.parametrize('change',['selection','native','cancel'])
def test_background_timestamp_fetch_cannot_register_on_replacement(change,monkeypatch):
    from test_transport_recovery_native import methods
    from lib.clients import introdb
    calls=[]
    fetches=[]
    player=SimpleNamespace(_owner_context={'request_id':'old'},_native_instance='old-native',
        _cinema_cancel=Event(),data={'ids':{'imdb_id':'tt1'},'tv_data':{'season':0,'episode':1}},
        playback_client=Client(calls.append))
    def fetch(*args):
        fetches.append(args)
        if change=='selection':player._owner_context={'request_id':'new'}
        elif change=='native':player._native_instance='new-native'
        else:player._cinema_cancel.set()
        return {'intro':dict(start_ms=1000,end_ms=9000)}
    monkeypatch.setattr(introdb,'get_segments',fetch)
    method=methods({'fetch_introdb_segments'},dict(deepcopy=deepcopy,kodilog=lambda *a,**kw:None))['fetch_introdb_segments']
    method(player)
    assert fetches == [('tt1', 0, 1)]
    assert calls==[]


def test_background_timestamp_fetch_registers_only_with_injected_client(monkeypatch):
    from test_transport_recovery_native import methods
    from lib.clients import introdb
    calls = []
    segments = {'intro': dict(start_ms=1000, end_ms=9000)}
    monkeypatch.setattr(introdb, 'get_segments', lambda *args: segments)
    def call(body):
        calls.append(body)
        return {'accepted': True, 'count': 1}
    player = SimpleNamespace(_owner_context={'request_id': 'original'}, _native_instance='original-native',
        _cinema_cancel=Event(), data={'ids': {'imdb_id': 'tt1'}, 'tv_data': {'season': 0, 'episode': 1}},
        playback_client=Client(call))
    method = methods({'fetch_introdb_segments'}, dict(deepcopy=deepcopy,
        kodilog=lambda *a, **kw: None))['fetch_introdb_segments']
    method(player)
    assert calls == [dict(operation='segment_register', request_id='original',
        native_instance='original-native', segments=segments)]
    assert player.skip_intro_segments == dict(request_id='original', native_instance='original-native')
    assert player._skip_segment_count == 1


def test_popup_without_inherited_client_never_discovers_or_revives_binding(monkeypatch):
    from bobbi_platform import playback_client
    monkeypatch.setattr(playback_client, 'capture',
        lambda: pytest.fail('A popup is not a playback binding composition entry'))
    context = dict(boot_id='a' * 32, epoch=1, request_id='b' * 32, native_instance='original')
    popup = SkipIntroWindow('skip_intro.xml', '', segment_data={'segment_id': 'c' * 64}, context=context)
    with pytest.raises(OSError, match='PLAYBACK_BINDING_UNAVAILABLE'):
        popup._owner_call('segment_status')
    assert not popup._do_skip()
    popup._background_monitor()
    assert popup.closed


@pytest.mark.parametrize('available', [True, False])
def test_dialog_entry_captures_once_and_popup_reuses_even_unavailable_client(monkeypatch, available):
    from bobbi_core.playback_request import unavailable
    from bobbi_platform import playback_client
    from lib.gui import custom_dialogs
    calls, captures, windows, errors = [], [], [], []
    monkeypatch.setattr(custom_dialogs, 'kodilog', errors.append)
    def call(body):
        calls.append(body)
        return {'available': True} if body['operation'] == 'segment_status' else {'queued': True}
    client = Client(call) if available else unavailable()
    def capture():
        captures.append(True)
        return client
    monkeypatch.setattr(playback_client, 'capture', capture)
    def modal(window):
        windows.append(window)
        assert window.playback_client is client
        if available:
            assert window._owner_call('segment_status')['available']
        else:
            with pytest.raises(OSError, match='PLAYBACK_BINDING_UNAVAILABLE'):
                window._owner_call('segment_status')
        assert window._do_skip() is available
        assert not window._do_skip()
    monkeypatch.setattr(SkipIntroWindow, 'doModal', modal)
    custom_dialogs.run_skip_intro_dialog(dict(
        segment_data=json.dumps({'segment_id': 'c' * 64}),
        segment_context=json.dumps(dict(boot_id='a' * 32, epoch=1,
            request_id='b' * 32, native_instance='original'))))
    assert captures == [True] and len(windows) == 1
    assert errors == []
    assert [body['operation'] for body in calls] == (['segment_status', 'segment_action'] if available else [])
