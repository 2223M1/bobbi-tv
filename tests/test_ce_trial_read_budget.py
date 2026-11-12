"""Real collector paths: slow read admission and bounded failure attribution."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

ROOT = Path(os.environ.get('BOBBI_REVIEW_REPO', Path(__file__).resolve().parents[1]))


def metric_collector(activity_seconds=0, fail_at=None, duration=2):
    source = ROOT / 'tools/ce_trial_metrics.py'
    spec = importlib.util.spec_from_file_location('metrics_budget_probe', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = ast.parse(module.REMOTE)
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    ns = dict(hashlib=module.hashlib, json=json, re=re)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
    clock, calls = [0.0], []
    delays = iter(activity_seconds) if isinstance(activity_seconds, (list, tuple)) else None
    def process_sample(pid):
        calls.append(clock[0])
        if len(calls) == fail_at:
            raise OSError('private-process-path')
        return dict(monotonic=clock[0], utc=clock[0], start_ticks=1,
                    cpu_ticks=int(clock[0]*100), host_total_ticks=int(clock[0]*1000),
                    host_idle_ticks=int(clock[0]*500))
    def activity():
        seconds = next(delays) if delays is not None else activity_seconds
        clock[0] += seconds
        return dict(activity_monotonic=clock[0], activity_observation_seconds=seconds)
    tail = SimpleNamespace(poll=lambda *a: None, events=[], gaps=0, missing=0)
    ns.update(time=SimpleNamespace(monotonic=lambda:clock[0], time=lambda:clock[0],
        sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),
        binding=lambda:('1', {'clock_ticks_per_second':100}), TraceTail=lambda _:tail,
        process_sample=process_sample, activity=activity, DURATION=duration, EXPECTED_FILE=None,
        SAMPLE_NAME='fixture', CONDITION='idle', CACHE_STATE='unknown', REPEAT=1,
        SOURCE_TREE='a'*40)
    return ns['collect'](), calls


def test_slow_metrics_read_stops_admission_at_monotonic_deadline(tmp_path):
    result, calls = metric_collector(activity_seconds=3)
    assert calls == [0.0]
    assert len(result['samples']) == 1 and result['errors'] == []
    assert result['elapsed_seconds'] == 3
    assert result['sampling']['stopped_reason'] == 'deadline'
    assert result['sampling']['skipped_points'] == 0
    assert result['sampling']['unstarted_points'] == 2
    assert result['sampling']['overrun_seconds'] == 1
    source = ROOT / 'tools/ce_playback_trial.py'
    spec = importlib.util.spec_from_file_location('trial_slow_exit', source)
    trial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trial)
    assert trial.result_exit_code(result, operation='metrics') == 1
    source = ROOT / 'tools/ce_trial_metrics.py'
    spec = importlib.util.spec_from_file_location('metrics_slow_summary', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = tmp_path / 'short.json'
    receipt.write_text(json.dumps({'result':result}))
    with pytest.raises(ValueError, match='METRICS_RECEIPT_FAILED'):
        module.summarize([receipt], ROOT)


def test_normal_metrics_preserves_real_schedule_and_completed_samples():
    result, calls = metric_collector(activity_seconds=.1)
    assert calls == [0.0, 1.0, 2.0]
    assert len(result['samples']) == 3 and result['errors'] == []
    assert result['sampling']['unstarted_points'] == 0
    assert result['sampling']['skipped_points'] == 0
    assert result['sampling']['stopped_reason'] == 'schedule_complete'
    assert result['sampling']['overrun_seconds'] == pytest.approx(.1)
    assert all(row['schedule_lag_seconds'] == 0 for row in result['samples'])


@pytest.mark.parametrize('first_read_seconds', [3.0, 3.25])
def test_metrics_skips_expired_slots_without_replaying_reads(first_read_seconds):
    result, calls = metric_collector(activity_seconds=[first_read_seconds] + [.1] * 10, duration=10)
    assert calls == [0.0, first_read_seconds] + list(map(float, range(4, 11)))
    assert len(result['samples']) == 9 and result['errors'] == []
    sampling = result['sampling']
    assert sampling['skipped_points'] == 2 and sampling['unstarted_points'] == 0
    assert sampling['planned_points'] == sampling['collected_points'] + sampling['skipped_points']
    assert sampling['stopped_reason'] == 'schedule_complete'
    assert sampling['overrun_seconds'] == pytest.approx(.1)
    assert result['samples'][1]['schedule_lag_seconds'] == first_read_seconds - 3


def test_interrupted_metrics_retains_partial_samples_and_failure():
    result, calls = metric_collector(fail_at=2)
    assert calls == [0.0, 1.0] and len(result['samples']) == 1
    assert result['errors'] == [dict(sample=1,error='OSError',reason='PROCESS_SAMPLE_UNAVAILABLE')]
    assert result['sampling']['stopped_reason'] == 'sample_error'
    source = ROOT / 'tools/ce_playback_trial.py'
    spec = importlib.util.spec_from_file_location('trial_budget_exit', source)
    trial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trial)
    assert trial.result_exit_code(result, operation='metrics') == 1
    assert 'private' not in json.dumps(result)


CHANNELS = ('OWNER_SNAPSHOT', 'NATIVE_STATE', 'ACTIVE_PLAYERS', 'PLAYER_PROPERTIES',
            'CACHING', 'LABELS', 'GUI', 'DECODER')


def startup_capture(failed_channel=None):
    source = ROOT / 'tools/ce_trial_remote.py'
    names = {'state','sample','request_status','seconds','capture_startup_trace',
             'decoder_snapshot','decoder_intervals','decoder_frame_pair'}
    nodes = [node for node in ast.parse(source.read_text()).body
             if isinstance(node,ast.FunctionDef) and node.name in names]
    clock, seen = [0.0], []
    request = 'a'*32
    native = '11111111-1111-1111-1111-111111111111'
    def read(channel, value):
        seen.append(channel)
        clock[0] += .25
        if channel == failed_channel:
            raise TimeoutError('https://signed.invalid/?token=private-secret')
        return value
    def snapshot():
        return read('OWNER_SNAPSHOT', {'desired':{'request_id':request}})
    replies = {
        'Player.BobiState': ('NATIVE_STATE', {'playback':{'request_id':request,
            'native_instance':native,'phase':'AV_STARTED','sequence':2}}),
        'Player.GetActivePlayers': ('ACTIVE_PLAYERS', [{'playerid':1,'type':'video'}]),
        'Player.GetProperties': ('PLAYER_PROPERTIES', {'time':{'hours':0,'minutes':0,'seconds':1,'milliseconds':0},
            'totaltime':{'hours':0,'minutes':20,'seconds':0,'milliseconds':0},'speed':1}),
        'XBMC.GetInfoBooleans': ('CACHING', {'Player.Caching':False}),
        'XBMC.GetInfoLabels': ('LABELS', {}),
        'GUI.GetProperties': ('GUI', {'currentwindow':{'id':12005}}),
    }
    ns = dict(re=re, snapshot=snapshot, rpc=lambda method,*_:read(*replies[method]),
        save=lambda _:None, Path=lambda _:SimpleNamespace(read_text=lambda:read('DECODER',
            'vdec channel 0 statistics:\n device name : h264\nframe count : 24\n')),
        time=SimpleNamespace(monotonic=lambda:clock[0],
            sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds)))
    exec(compile(ast.Module(body=nodes,type_ignores=[]), str(source), 'exec'), ns)
    trace, error = ns['capture_startup_trace']({'request_id':request,'native_instance':native},budget=.5)
    return trace, error, seen


@pytest.mark.parametrize('channel', CHANNELS)
def test_startup_failure_attributes_only_actual_failed_read_channel(channel):
    trace, error, seen = startup_capture(channel)
    assert trace == []
    assert error['type'] == 'TimeoutError' and error['reason'] == 'STARTUP_OBSERVATION_INTERRUPTED'
    diagnostic = error['read_diagnostic']
    assert diagnostic['channel'] == channel
    assert [entry['channel'] for entry in diagnostic['stages']] == list(CHANNELS[:CHANNELS.index(channel)+1])
    assert diagnostic['stages'][-1]['status'] == 'error'
    assert diagnostic['stages'][-1]['elapsed_seconds'] == .25
    assert seen[-1] == channel
    assert 'private' not in json.dumps((trace,error)) and 'signed.invalid' not in json.dumps(error)


def test_successful_startup_trace_retains_bounded_per_read_observations():
    trace, error, seen = startup_capture()
    assert error is None and len(trace) == 1
    assert seen == list(CHANNELS)
    observations = trace[0]['read_observations']
    assert len(observations) == 8 and all(entry['status'] == 'ok' for entry in observations)
    assert all(entry['elapsed_seconds'] == .25 for entry in observations)
    assert 'url' not in json.dumps(observations) and 'private' not in json.dumps(observations)


@pytest.mark.parametrize('damage', ['channel_type', 'unknown_channel', 'stage_channel_type',
                                  'extra_field', 'nonfinite', 'too_many'])
def test_uncontrolled_exception_attributes_cannot_escape_or_break_failure_receipt(damage):
    source = ROOT / 'tools/ce_trial_remote.py'
    node = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node,ast.FunctionDef) and node.name == 'capture_startup_trace')
    stage = dict(channel='GUI',status='error',started=0.0,completed=.25,elapsed_seconds=.25)
    diagnostic = dict(channel='GUI',stages=[stage])
    if damage == 'channel_type': diagnostic['channel'] = ['private']
    elif damage == 'unknown_channel': diagnostic['channel'] = 'private://locator'
    elif damage == 'stage_channel_type': stage['channel'] = ['private']
    elif damage == 'extra_field': stage['url'] = 'private://locator'
    elif damage == 'nonfinite': stage['elapsed_seconds'] = float('nan')
    elif damage == 'too_many': diagnostic['stages'] = [stage]*9
    def sample(_):
        error = TimeoutError('private://locator')
        error.trial_read_diagnostic = diagnostic
        raise error
    namespace = dict(sample=sample,time=SimpleNamespace(monotonic=lambda:0))
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
    trace, error = namespace['capture_startup_trace']({})
    assert trace == []
    assert error == dict(type='TimeoutError',reason='STARTUP_OBSERVATION_INTERRUPTED',samples_retained=0)
