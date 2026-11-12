"""A native Ended receipt is not proof that a truncated movie was watched."""
import ast
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))


@pytest.mark.parametrize('position,duration,age,natural', [
    (22.1, 1444.945, .5, False), (47, 1444.945, .5, False),
    (1443, 1444.945, .5, True), (1444.945, 1444.945, 2.9, True),
    (1444, 1444.945, 6, False), (0, 0, .5, False),
    (None, 1444.945, .5, False), (float('nan'), 1444.945, .5, False),
    (1444, float('inf'), .5, False), (True, 1, .5, False),
])
def test_actual_native_terminal_consumer_rejects_early_or_unproved_eof(monkeypatch, position, duration, age, natural):
    from bobbi_core import playback_request
    source = ROOT/'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'wait_cinema_terminal')
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', playback_request)
    monkeypatch.setattr(playback_request, 'terminal_state', lambda *a: {'reason': 'NATURAL_EOF'})
    env = dict(monotonic=lambda: 100., TERMINAL_RECONCILIATION_SECONDS=3,
               sleep=lambda _: None, kodilog=lambda *a, **k: None)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), env)
    actor = SimpleNamespace(data={'selection_policy':'exact'}, playback_session_id='a'*32,
        _cinema_cancel=Event(), _cinema_end=False, _owner_context={}, _native_instance='native',
        _terminal_reason='UNKNOWN', current_time=position, total_time=duration,
        _progress_observed_at=100-age)
    env['wait_cinema_terminal'](actor)
    assert actor._cinema_end is natural
    assert actor._terminal_reason == ('NATURAL_EOF' if natural else 'ERROR')
    assert actor._cinema_cancel.is_set() is (not natural)


def test_near_end_position_alone_cannot_grant_eof():
    from bobbi_core.playback_completion import observed_end
    assert observed_end(99,100,100,101)
    assert not observed_end(99,100,None,101)
    assert not observed_end(99,100,102,101)
    # This helper never issues a terminal or continuation grant. Both consumers
    # still require their own same-owner Ended event before consulting it.
    standard = (ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py').read_text()
    assert "kind == 'ENDED' and observed_end(" in standard
