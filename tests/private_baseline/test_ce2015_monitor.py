"""Real monitor + real PlaybackOwner, only Kodi/IPC/time and optional IO doubled."""
import importlib.util
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

import pytest
from lib.cinema import playback_request as request
from bobbi_core.playback_owner import PlaybackOwner


@pytest.mark.parametrize('fault', ['none', 'gap', 'timeout', 'eof', 'stop', 'replacement',
                                  'cancel', 'boot', 'epoch', 'instance', 'malformed'])
def test_monitor_distinguishes_current_terminal_retired_and_unknown(monkeypatch, fault):
    # xbmc.Player must be a type, not the legacy harness's MagicMock metaclass.
    monkeypatch.setattr(sys.modules['xbmc'], 'Player', type('Player', (), {}))
    path = Path(__file__).resolve().parents[2]/'addons/plugin.video.bobbi/lib/native_player.py'
    spec = importlib.util.spec_from_file_location('ce2015_native_product', path)
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    owner = PlaybackOwner(boot_id='c'*32)
    rid, selection = 'a'*32, 'transport:'+'1'*64
    identity = selection+'|'+'2'*64
    owner.select(owner.boot_id, owner.epoch, rid, selection)
    owner.bind_file(owner.boot_id, owner.epoch, rid, selection, identity)
    owner.claim_start(owner.boot_id, owner.epoch, rid, 'player_play')
    owner.observe_started(owner.boot_id, owner.epoch, rid, 'native-A', identity)
    clock, calls, events = [100.], [], []
    playing = [True]
    player = native.JacktookPLayer.__new__(native.JacktookPLayer)
    player.data = dict(selection_policy='exact', mode='tv', cinema_continuity=True)
    player.playback_session_id, player._native_instance = rid, 'native-A'
    player._owner_context = dict(boot_id=owner.boot_id, epoch=owner.epoch, request_id=rid)
    player._cinema_cancel, player._cinema_end = Event(), False
    player._was_superseded, player._terminal_reason, player.skip_intro_enabled = False, 'UNKNOWN', False
    def transport(body, **kwargs):
        calls.append(body)
        if fault in ('timeout', 'malformed') or (fault == 'gap' and len(calls) <= 3):
            clock[0] += min(.2, kwargs.get('timeout', .3))
            if fault == 'malformed': return {'observed': 'bad'}
            raise OSError('temporary IPC')
        if fault in ('eof', 'stop') and not owner.terminal:
            playing[0] = False
            owner.observe_terminal('native-A', 'NATURAL_EOF' if fault == 'eof' else 'STOP')
        if len(calls) == 1:
            if fault == 'cancel': owner.cancel(owner.boot_id, owner.epoch, rid)
            if fault == 'replacement': owner.select(owner.boot_id, owner.epoch, 'b'*32, selection)
        snapshot = owner.snapshot()
        if fault in ('boot', 'epoch'): snapshot[fault if fault == 'epoch' else 'boot_id'] = 'changed'
        if fault == 'instance' and snapshot['observed']: snapshot['observed']['native_instance'] = 'native-B'
        return snapshot
    monkeypatch.setattr(request, 'call', transport)
    monkeypatch.setattr(request, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0]+s)))
    monkeypatch.setattr(native, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(native, 'sleep', lambda ms: clock.__setitem__(0, clock[0]+ms/1000))
    monkeypatch.setattr(native, 'get_setting', lambda *a: False)
    monkeypatch.setattr(native, 'kodilog', lambda *a, **kw: None)
    player.isPlayingVideo = lambda: playing[0]
    player._wait_for_video_start = player.handle_playback_start = lambda: True
    player._cinema_phase = lambda phase: events.append(phase)
    player._record_started_history = lambda: None
    player.update_playback_progress = lambda: events.append('progress')
    player.check_cinema_stall = player._consume_next_dialog_action = lambda: False
    for name in ('start_cinema_preparation', 'select_audio_stream', 'handle_subtitle_selection',
                 '_apply_simkl_resume', '_apply_trakt_resume', '_apply_nuvio_resume',
                 'check_cinema_subtitles', 'handle_trakt_pause_resume', 'check_cinema_continuity',
                 'check_autoscrape_threshold', 'playback_close_dialogs', 'check_next_dialog',
                 'check_skip_intro', 'check_stinger_notification'):
        setattr(player, name, lambda: None)
    def tick():
        playing[0] = False
        owner.observe_terminal('native-A', 'NATURAL_EOF')
    player._wait_monitor_tick = tick
    for name in ('queue_cinema_natural_end', 'handle_playback_stop', 'offer_terminal_actions',
                 'kill_dialog', 'clear_playback_properties', '_release_playback_session'):
        setattr(player, name, lambda name=name: events.append(name))
    player.monitor()
    assert 'kill_dialog' not in events
    if fault in ('none', 'gap', 'eof', 'stop'):
        assert not player._was_superseded
        assert player._terminal_reason == ('STOP' if fault == 'stop' else 'NATURAL_EOF')
        assert 'handle_playback_stop' in events
        assert ('progress' in events) is (fault in ('none', 'gap'))
    else:
        assert 'progress' not in events and 'handle_playback_stop' not in events
        assert 'clear_playback_properties' not in events
        if fault in ('timeout', 'malformed'):
            assert not player._was_superseded and 2.9 <= clock[0]-100 <= 3.001
            assert 'OWNER_OBSERVATION_TIMEOUT' in events
        else:
            assert player._was_superseded
