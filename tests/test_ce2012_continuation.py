"""Audio/video takeover, optional subtitle IO and immutable native EOF."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

import pytest
from test_standard_product import product, selected, handoff
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core import playback_request as request


def test_external_audio_finishes_before_eof_budget_never_resumes_old_video(product):
    data = selected(product)
    product.actor.session.next_loader = None
    handoff(product, data)
    product.state.position = 99
    product.actor.tick()
    product.state.playing = False
    product.actor.player.onPlayBackEnded()
    product.actor.tick()
    product.actor.session.current['next_data'] = dict(data, request_id='b'*32, url='https://media.example/B.mkv')
    product.state.playing = True
    product.actor.player.isPlayingVideo = lambda: False
    product.actor.player.getVideoInfoTag = lambda: pytest.fail('audio has no video tag')
    product.actor.player.getPlayingItem = lambda: pytest.fail('audio request property is not needed')
    product.state.url = 'https://audio.example/song.flac'
    product.actor.tick()
    assert product.actor.session.current['state'] == 'retired'
    product.clock[0] += 5
    product.state.playing = False
    product.actor.player.onPlayBackEnded()
    product.actor.tick()
    assert len(product.state.opened) == 1
    assert product.actor.session.current['next_data'] is None


def test_late_media_does_not_spend_last_second_on_subtitles(product, monkeypatch):
    data = selected(product)
    product.actor.session.next_loader = None
    handoff(product, data)
    product.state.position = 99
    product.actor.tick()
    product.state.playing = False
    product.actor.player.onPlayBackEnded()
    product.actor.tick()
    product.clock[0] += 19.3
    monkeypatch.setattr(product.module, 'next_data', lambda *a: dict(data, url='https://media.example/B.mkv'))
    monkeypatch.setattr(product.module, 'discover', lambda *a: pytest.fail('no subtitle time remains'))
    assert product.actor.next_with_subtitle(data, lambda: False)['url'].endswith('/B.mkv')


@pytest.mark.parametrize('change,expected', [('none','NATURAL_EOF'), ('cancel','CANCEL'),
    ('stop','STOP'), ('error','ERROR'), ('epoch','SUPERSEDED'), ('instance',None)])
def test_terminal_observation_never_revives_other_request(monkeypatch, change, expected):
    original = dict(boot_id='boot', epoch=1, request_id='a'*32)
    snapshot = dict(boot_id='boot', epoch=1, desired=dict(request_id='a'*32, cancelled=False),
        terminal=dict(request_id='a'*32, native_instance='native', reason='NATURAL_EOF'))
    if change == 'cancel': snapshot['desired']['cancelled'] = True
    if change in ('stop','error'):
        snapshot['desired']['cancelled'] = True
        snapshot['terminal']['reason'] = change.upper()
    if change == 'epoch': snapshot['epoch'] = 2
    if change == 'instance': snapshot['terminal']['native_instance'] = 'other'
    monkeypatch.setattr(request, 'call', lambda body: deepcopy(snapshot))
    actual = request.terminal_state(original, 'native')
    assert actual == ({'reason': expected} if expected else None)


def test_actual_terminal_wait_survives_busy_read_without_guessing_eof(monkeypatch):
    path = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'wait_cinema_terminal')
    original = dict(boot_id='boot', epoch=1, request_id='a'*32)
    calls, clock = [], [100.]
    def read(body):
        calls.append(body)
        if len(calls) == 1: raise OSError('busy')
        return dict(original, desired=dict(request_id='a'*32, cancelled=False),
            terminal=dict(request_id='a'*32, native_instance='native', reason='NATURAL_EOF'))
    monkeypatch.setattr(request, 'call', read)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', request)
    env = dict(monotonic=lambda: clock[0], TERMINAL_RECONCILIATION_SECONDS=3,
        sleep=lambda ms: clock.__setitem__(0, clock[0]+ms/1000), kodilog=lambda *a,**kw: None)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), env)
    player = SimpleNamespace(data=dict(selection_policy='exact'), playback_session_id='a'*32,
        _cinema_cancel=Event(), _cinema_end=False, _owner_context=original, _native_instance='native',
        _terminal_reason='UNKNOWN', _owns_playback_session=lambda: pytest.fail('do not collapse an unavailable read to false'))
    env['wait_cinema_terminal'](player, 3)
    assert player._terminal_reason == 'NATURAL_EOF' and player._cinema_end
    assert len(calls) == 2 and not player._cinema_cancel.is_set()
