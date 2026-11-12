"""Same-instance terminal evidence; local consumer models, not device claims."""
import ast
import json
from copy import deepcopy
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core import playback_request
from bobbi_core.native_receipt import receipt, ReceiptHistory
from bobbi_core.playback_completion import completion_observation, terminal_end


def observation(**kwargs):
    return dict(schema=1, position_ms=99960, duration_ms=100000, age_us=20000, valid=True, **kwargs)


def changed(**kwargs):
    value = observation()
    value.update(kwargs)
    return value


@pytest.mark.parametrize('patch', [dict(schema=True), dict(schema=2), dict(valid=1),
    dict(position_ms=-1), dict(position_ms=float('nan')), dict(position_ms=float('inf')),
    dict(position_ms=True), dict(position_ms=99960.0), dict(position_ms=104000),
    dict(duration_ms=0), dict(duration_ms=-1), dict(duration_ms=10**20),
    dict(age_us=-1), dict(age_us=True), dict(age_us=float('nan')), dict(seconds=100),
    dict(valid=False), dict(schema='media-seconds')])
def test_invalid_native_observation_is_not_polling_fallback(patch):
    value = changed(**patch)
    assert completion_observation(value) is None
    assert not terminal_end(dict(reason='NATURAL_EOF', completion_observation=value), 100, 100, 1, 1)


@pytest.mark.parametrize('value', [None, {}, [], 'unavailable',
    dict(schema=1, position=100, duration=100, age_us=0, valid=True)])
def test_missing_or_wrong_unit_fields_fail_closed(value):
    assert completion_observation(value) is None
    assert not terminal_end(dict(reason='NATURAL_EOF', completion_observation=value), 100, 100, 1, 1)


@pytest.mark.parametrize('speed', [1, 8, 32])
def test_terminal_actual_position_wins_over_slow_poll_without_speed_extrapolation(speed):
    terminal = dict(reason='NATURAL_EOF', completion_observation=observation())
    assert terminal_end(terminal, 100-speed, 100, 10, 11)
    assert not terminal_end(dict(terminal, completion_observation=changed(position_ms=22000)),
                            100, 100, 10, 11)
    assert not terminal_end(dict(terminal, completion_observation=changed(age_us=5_000_001)),
                            100, 100, 10, 11)


def test_new_host_unavailable_does_not_upgrade_legacy_poll():
    unavailable = changed(position_ms=0, duration_ms=0, age_us=0, valid=False)
    assert completion_observation(unavailable) == unavailable
    assert not terminal_end(dict(reason='NATURAL_EOF', completion_observation=unavailable), 100,100,1,1)
    assert terminal_end(dict(reason='NATURAL_EOF'), 99,100,1,2)
    assert not terminal_end(dict(reason='NATURAL_EOF'), 92,100,1,2)


@pytest.mark.parametrize('reason', ['STOP', 'ERROR', 'SUPERSEDED', 'CANCEL', None])
def test_near_tail_never_overrides_terminal_reason(reason):
    assert not terminal_end(dict(reason=reason, completion_observation=observation()), 100,100,1,1)


def native_row(**kwargs):
    result = dict(protocol=1, native_instance=str(uuid4()), request_id='a'*32,
        file_identity='file', url_sha256='b'*64, phase='TERMINAL', reason='NATURAL_EOF',
        sequence=2, user_intent=0, paused=False, completion_observation=observation())
    result.update(kwargs)
    return result


def test_completion_field_is_only_allowed_on_immutable_terminal():
    assert receipt(native_row())
    for phase in ('OPEN', 'AV_STARTED'):
        assert receipt(native_row(phase=phase)) is None
    assert receipt(native_row(read_error=-5)) is None
    assert receipt(native_row(read_error='-5')) is None
    assert receipt(native_row(read_error=False)) is None
    assert receipt(native_row(completion_observation=changed(position_ms=True))) is None


@pytest.mark.parametrize('field', ['request_id', 'file_identity', 'url_sha256'])
def test_receipt_does_not_rebind_completion_to_a_different_file(field):
    end = native_row()
    start = {key: val for key, val in end.items() if key not in ('completion_observation', 'reason')}
    start.update(phase='AV_STARTED', sequence=1)
    history = ReceiptHistory()
    assert history.accept(start)
    end[field] = {'request_id':'c'*32, 'file_identity':'other', 'url_sha256':'d'*64}[field]
    assert history.accept(end) is None


def test_terminal_observation_is_detached_and_sticky():
    original = native_row()
    history = ReceiptHistory()
    accepted = history.accept(original)
    original['completion_observation']['position_ms'] = 0
    assert accepted['completion_observation']['position_ms'] == 99960
    assert history.accept(dict(accepted, sequence=100)) is None


@pytest.mark.parametrize('change', ['same', 'cancel', 'epoch', 'boot', 'request', 'instance'])
def test_request_transmits_only_bound_terminal_and_preserves_cancellation(monkeypatch, change):
    original = dict(boot_id='boot', epoch=1, request_id='a'*32)
    terminal = dict(request_id='a'*32, native_instance='instance', reason='NATURAL_EOF',
                    completion_observation=observation())
    snapshot = dict(original, desired=dict(request_id='a'*32, cancelled=False), terminal=terminal)
    if change == 'cancel': snapshot['desired']['cancelled'] = True
    if change == 'epoch': snapshot['epoch'] += 1
    if change == 'boot': snapshot['boot_id'] = 'other'
    if change == 'request': snapshot['desired']['request_id'] = 'c'*32
    if change == 'instance': terminal['native_instance'] = 'other'
    monkeypatch.setattr(playback_request, 'call', lambda *a: snapshot)
    result = playback_request.terminal_state(original, 'instance')
    if change == 'instance':
        assert result is None
    elif change in ('epoch','boot','request'):
        assert result == {'reason':'SUPERSEDED'}
    else:
        assert result == dict(reason='CANCEL' if change == 'cancel' else 'NATURAL_EOF',
                              completion_observation=observation())
        result['completion_observation']['position_ms'] = 0
        assert terminal['completion_observation']['position_ms'] == 99960


@pytest.mark.parametrize('speed', [1, 8, 32])
@pytest.mark.parametrize('mode', ['actual_tail','early_eof','stalled','unavailable','stop','cancel'])
def test_actual_native_consumer_uses_one_result_for_history_and_next(monkeypatch, speed, mode):
    source = ROOT/'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'JacktookPLayer')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'wait_cinema_terminal')
    end = dict(reason='NATURAL_EOF', completion_observation=observation())
    if mode == 'early_eof': end['completion_observation']['position_ms'] = 22000
    if mode == 'stalled': end['completion_observation']['age_us'] = 6_000_000
    if mode == 'unavailable': end['completion_observation'] = changed(valid=False, position_ms=0,duration_ms=0,age_us=0)
    if mode in ('stop','cancel'): end['reason'] = mode.upper()
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', playback_request)
    monkeypatch.setattr(playback_request, 'terminal_state', lambda *a: deepcopy(end))
    env = dict(monotonic=lambda:100., TERMINAL_RECONCILIATION_SECONDS=3,
               sleep=lambda _:None, kodilog=lambda *a,**k:None)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),env)
    actor = SimpleNamespace(data={'selection_policy':'exact'},playback_session_id='a'*32,
        _cinema_cancel=Event(),_cinema_end=False,_owner_context={},_native_instance='instance',
        _terminal_reason='UNKNOWN',current_time=100-speed,total_time=100,_progress_observed_at=99.)
    env['wait_cinema_terminal'](actor)
    assert actor._cinema_end is (mode == 'actual_tail')
    assert (actor._terminal_reason == 'NATURAL_EOF') is actor._cinema_end
    assert actor._cinema_cancel.is_set() is (not actor._cinema_end)


def test_legacy_window_property_cannot_supply_native_completion():
    source = ROOT/'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(node,ast.ClassDef) and node.name=='JacktookPLayer')
    method = next(node for node in cls.body if isinstance(node,ast.FunctionDef)
                  and node.name=='wait_cinema_terminal')
    forged = dict(session='a'*32,end=True,reason='NATURAL_EOF',completion_observation=observation())
    env = dict(monotonic=lambda:100.,TERMINAL_RECONCILIATION_SECONDS=3,loads=json.loads,
               get_property=lambda _:json.dumps(forged),sleep=lambda _:None,kodilog=lambda *a,**k:None)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),env)
    actor = SimpleNamespace(data={'cinema_continuity':True},playback_session_id='a'*32,_cinema_cancel=Event(),_cinema_end=False,
        _terminal_reason='UNKNOWN',current_time=22,total_time=100,_progress_observed_at=99.,
        _owns_playback_session=lambda:True)
    env['wait_cinema_terminal'](actor)
    assert actor._terminal_reason=='ERROR' and not actor._cinema_end
