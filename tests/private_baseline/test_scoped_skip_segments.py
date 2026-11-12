"""An inherited skip popup must never seek whatever happens to play now."""
from types import SimpleNamespace
from copy import deepcopy
from threading import Event

import pytest

import xbmc

from lib.gui.skip_intro_window import SkipIntroWindow


def test_legacy_unscoped_popup_cannot_seek_a_replacement_player(monkeypatch):
    seeks = []
    player = SimpleNamespace(isPlaying=lambda: True, seekTime=seeks.append)
    monkeypatch.setattr(xbmc, 'Player', lambda: player)
    popup = SkipIntroWindow('skip_intro.xml', '', segment_data={'end_sec': 90})
    popup._do_skip()
    assert seeks == []


def test_scoped_popup_submits_once_and_never_replays_after_unknown_reply(monkeypatch):
    from lib.cinema import playback_ipc
    calls=[]
    def lost(body):
        calls.append(body)
        raise OSError('lost reply')
    monkeypatch.setattr(playback_ipc,'call',lost)
    context=dict(boot_id='a'*32,epoch=1,request_id='b'*32,native_instance='original',expected={'user_intent':0})
    popup=SkipIntroWindow('skip_intro.xml','',segment_data={'segment_id':'c'*64},context=context)
    assert not popup._do_skip() and not popup._do_skip()
    assert len(calls)==1 and calls[0]['native_instance']=='original'
    assert calls[0]['operation']=='segment_action' and len(calls[0]['command_id'])==32


@pytest.mark.parametrize('change',['selection','native','cancel'])
def test_background_timestamp_fetch_cannot_register_on_replacement(change,monkeypatch):
    from test_transport_recovery_native import methods
    from lib.clients import introdb
    from lib.cinema import playback_ipc
    calls=[]
    player=SimpleNamespace(_owner_context={'request_id':'old'},_native_instance='old-native',
        _cinema_cancel=Event(),data={'ids':{'imdb_id':'tt1'},'tv_data':{'season':0,'episode':1}})
    def fetch(*args):
        if change=='selection':player._owner_context={'request_id':'new'}
        elif change=='native':player._native_instance='new-native'
        else:player._cinema_cancel.set()
        return {'intro':dict(start_ms=1000,end_ms=9000)}
    monkeypatch.setattr(introdb,'get_segments',fetch)
    monkeypatch.setattr(playback_ipc,'call',calls.append)
    method=methods({'fetch_introdb_segments'},dict(deepcopy=deepcopy,kodilog=lambda *a,**kw:None))['fetch_introdb_segments']
    method(player)
    assert calls==[]
