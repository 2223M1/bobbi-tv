"""Tool-only signal characterization; no imports of the remote device entrypoint."""
import ast
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/ce_trial_remote.py'


def functions(*names):
    names = set(names) | {'decoder_snapshot', 'decoder_intervals', 'decoder_frame_pair'}
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


def row(wall, seconds, frames, caching=False, phase='AV_STARTED', instance='one'):
    return dict(wall=wall, seconds=seconds, speed=1, caching=caching, phase=phase,
                native=dict(native_instance=instance, request_id='request'),
                decoder_counters={'frame count': frames})


def test_clock_only_stationarity_is_separate_from_real_caching_without_rewriting_failure():
    ns = functions('startup_health', 'startup_coverage', 'startup_signal_diagnostics')
    samples = [row(i / 2, 1.114, 70 + i * 12) for i in range(6)]
    samples += [row(3, 4.177, 133, True)]
    samples += [row(i / 2, 4.177, 143, True) for i in range(7, 20)]
    samples += [row(10, 4.487, 149)]
    original = deepcopy(samples)
    legacy = ns['startup_health'](samples)
    assert legacy['max_observed_stall_seconds'] == 9.5
    assert legacy['no_observed_stall'] is False
    diagnostic = ns['startup_signal_diagnostics'](samples)
    assert diagnostic['stationary_clock_with_decoder_progress_runs'][0]['wall_seconds'] == 2.5
    assert diagnostic['caching_sample_runs'][0]['wall_seconds'] == 6.5
    assert diagnostic['stationary_decoder_with_caching_runs'][0]['wall_seconds'] == 6
    assert diagnostic['changes_legacy_result'] is False
    assert diagnostic['render_continuity_proven'] is False
    assert ns['startup_coverage'](samples, legacy)['passed'] is False
    assert samples == original


def test_clock_catchups_keep_signal_steps_but_do_not_claim_a_seek():
    ns = functions('startup_signal_diagnostics')
    samples = [row(0, .238, 45), row(.4, .238, 57), row(.91, 1.114, 70),
               row(1.4, 1.114, 84), row(1.9, 4.177, 100)]
    result = ns['startup_signal_diagnostics'](samples)
    assert len(result['clock_step_events']) == 2
    assert all(event['decoder_advanced'] for event in result['clock_step_events'])
    assert all(event['meaning'] == 'CLOCK_STEP_NOT_SEEK_PROOF' for event in result['clock_step_events'])
    assert result['decoder_counter_reset_events'] == []


def test_negative_initial_pts_does_not_hide_a_caching_observation():
    ns = functions('startup_signal_diagnostics')
    result = ns['startup_signal_diagnostics']([
        row(0, -.039, 72, True), row(.5, .001, 72, True), row(1, .001, 72, True)])
    assert result['caching_sample_runs'][0]['wall_seconds'] == 1
    assert result['stationary_decoder_with_caching_runs'][0]['wall_seconds'] == 1
    assert result['changes_legacy_result'] is False


def test_open_phase_sampling_gap_is_recorded_without_claiming_a_playback_freeze():
    ns = functions('startup_signal_diagnostics')
    result = ns['startup_signal_diagnostics']([row(0, -1, 0, phase='OPEN'),
                                               row(2.668, -1, 0, phase='OPEN')])
    assert result['observation_gap_events'] == [dict(first_index=0, last_index=1,
        wall_seconds=2.668, first_phase='OPEN', last_phase='OPEN')]
    assert result['stationary_decoder_with_caching_runs'] == []
    assert result['clock_step_events'] == []


@pytest.mark.parametrize('middle', ['gap', 'new_instance', 'invalid'])
def test_diagnostic_runs_do_not_bridge_unobserved_or_unowned_intervals(middle):
    ns = functions('startup_signal_diagnostics')
    samples = [row(0, 2, 20, True), row(.5, 2, 20, True), row(1, 2, 20, True)]
    if middle == 'gap':
        samples[-1]['wall'] = 5
    elif middle == 'new_instance':
        samples[-1]['native']['native_instance'] = 'another'
    else:
        samples[-1]['seconds'] = float('nan')
    result = ns['startup_signal_diagnostics'](samples)
    assert result['stationary_decoder_with_caching_runs'][0]['last_index'] == 1
    assert result['stationary_decoder_with_caching_runs'][0]['wall_seconds'] == .5


def test_decoder_reset_and_negative_time_step_are_not_hidden():
    ns = functions('startup_signal_diagnostics')
    result = ns['startup_signal_diagnostics']([row(0, 10, 100), row(.5, 2, 4)])
    assert result['clock_step_events'][0]['direction'] == 'backward'
    assert result['decoder_counter_reset_events'] == [dict(first_index=0, last_index=1)]


def test_sample_brackets_separate_rpc_observation_times_without_more_device_reads():
    ns = functions('sample', 'seconds', 'request_status')
    clock, calls = [100.0], []
    def monotonic():
        clock[0] += .01
        return clock[0]
    def state(record):
        clock[0] += .2
        return {'desired': {'request_id': 'request'}}, {}, {'phase': 'AV_STARTED'}
    def rpc(method, params=None):
        calls.append(method)
        clock[0] += .3
        if method == 'Player.GetActivePlayers':
            return [{'playerid': 1}]
        if method == 'Player.GetProperties':
            return dict(time=dict(hours=0, minutes=0, seconds=1, milliseconds=0),
                        totaltime=dict(hours=1, minutes=0, seconds=0, milliseconds=0), speed=1)
        if method == 'XBMC.GetInfoBooleans':
            return {'Player.Caching': False}
        return {}
    ns.update(state=state, rpc=rpc, re=re, time=SimpleNamespace(monotonic=monotonic),
              Path=lambda _: SimpleNamespace(read_text=lambda: 'vdec channel 0 statistics:\n device name : h264\nframe count : 24\n'))
    value = ns['sample']({'request_id': 'request'})
    times = value['observation_times']
    assert times['sample_started'] < value['wall'] < times['player_time_started']
    ordered = ('player_time_started', 'player_time_completed', 'caching_started', 'caching_completed',
               'decoder_started', 'decoder_completed', 'sample_completed')
    assert all(times[first] < times[last] for first, last in zip(ordered, ordered[1:]))
    assert calls == ['Player.GetActivePlayers', 'Player.GetProperties', 'XBMC.GetInfoBooleans',
                     'XBMC.GetInfoLabels', 'GUI.GetProperties']
    assert value['seconds'] == 1 and value['decoder_counters']['frame count'] == 24
