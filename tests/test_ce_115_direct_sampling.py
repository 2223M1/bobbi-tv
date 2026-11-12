"""Bounded observation gaps never replay playback, ownership or control."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import ce_115_direct_kodi as kodi


class Clock:
    now = 100.0
    def monotonic(self):
        return self.now


class Observer:
    def __init__(self, clock, action=None):
        self.clock, self.action, self.calls, self.saved = clock, action, [], []
    def abort_requested(self):
        return False
    def wait(self, seconds):
        self.clock.now += max(0, seconds)
    def sample(self, record):
        self.calls.append(self.clock.now)
        self.clock.now += .01
        if self.action:
            self.action(len(self.calls))
        return dict(phase='OPEN', native=dict(request_id=record['request_id']))
    def save(self, record):
        self.saved.append(deepcopy(record))


def record():
    return dict(play_issued_at=100., request_id='a' * 32, samples=[])


def unavailable():
    raise kodi.SampleReadUnavailable('owner', TimeoutError('https://private.invalid/?token=secret'))


def test_transient_owner_timeout_retains_later_samples_in_original_window(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(kodi.time, 'monotonic', clock.monotonic)
    observer = Observer(clock, lambda count: unavailable() if count == 2 else None)
    result = record()
    kodi.observe_samples(observer, result, 45)
    assert len(observer.calls) == 90 and observer.calls[-1] == 144.5 and clock.now == 145.
    assert len(result['samples']) == 89 and len(result['sample_errors']) == 1
    assert result['sample_errors'][0]['channel'] == 'owner'
    assert result['sample_errors'][0]['error_type'] == 'TimeoutError'
    assert result['sampling']['has_gaps'] is True and result['sampling']['unstarted_points'] == 0
    assert result['sampling']['admission_deadline_monotonic'] == 145.
    assert result['sampling']['error_points'] == 1 and result['sampling']['collected_points'] == 89
    assert 'private.invalid' not in json.dumps(result) and 'token=secret' not in json.dumps(result)


def test_slow_read_skips_expired_slots_without_catchup_or_extended_window(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(kodi.time, 'monotonic', clock.monotonic)
    def slow(count):
        if count == 1:
            clock.now += 2.1
            unavailable()
    observer, result = Observer(clock, slow), record()
    kodi.observe_samples(observer, result, 10)
    assert len(observer.calls) == 17 and result['sampling']['skipped_points'] == 3
    assert result['sampling']['collected_points'] == 16 and result['sampling']['error_points'] == 1
    assert observer.calls[1] == pytest.approx(102.11) and observer.calls[2] == 102.5
    assert max(observer.calls) < 110. and clock.now == 110.


def test_inflight_overrun_is_recorded_and_no_further_sample_is_admitted(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(kodi.time, 'monotonic', clock.monotonic)
    def slow(count):
        clock.now += 12
        unavailable()
    observer, result = Observer(clock, slow), record()
    kodi.observe_samples(observer, result, 10)
    assert len(observer.calls) == 1 and result['samples'] == []
    assert result['sampling']['unstarted_points'] == 19 and result['sampling']['error_points'] == 1
    assert result['sampling']['overrun_seconds'] == pytest.approx(2.01)
    assert result['sampling']['stopped_reason'] == 'deadline'


@pytest.mark.parametrize('error', [kodi.DiagnosticError('OTHER_REQUEST'), kodi.DiagnosticError('OTHER_INSTANCE'),
    kodi.DiagnosticError('RPC_REJECTED'), kodi.HostAbort('HOST_ABORT_REQUESTED'), ValueError('invalid schema')])
def test_identity_abort_and_schema_failures_remain_fatal(monkeypatch, error):
    clock = Clock()
    monkeypatch.setattr(kodi.time, 'monotonic', clock.monotonic)
    def fatal(count):
        kodi.sample_read('owner', lambda: (_ for _ in ()).throw(error))
    observer, result = Observer(clock, fatal), record()
    with pytest.raises(type(error)):
        kodi.observe_samples(observer, result, 10)
    assert len(observer.calls) == 1 and result['sample_errors'] == []
    assert result['sampling']['stopped_reason'] == 'fatal_error' and result['sampling']['has_gaps']


@pytest.mark.parametrize('channel', ['owner', 'native', 'active_players'])
def test_snapshot_timeout_identifies_read_channel_without_control_calls(channel):
    runtime = kodi.Runtime.__new__(kodi.Runtime)
    calls = []
    def read(name):
        calls.append(name)
        if name == channel:
            raise TimeoutError('private response')
        return {}
    runtime.protocol = SimpleNamespace(call=lambda value: read('owner') if value == {'operation': 'snapshot'}
                                       else pytest.fail('No mutating owner operation'))
    runtime.rpc = lambda method: read({'Player.BobiState': 'native', 'Player.GetActivePlayers': 'active_players'}[method])
    with pytest.raises(kodi.SampleReadUnavailable) as caught:
        runtime.view(kodi.sample_read)
    assert caught.value.evidence['channel'] == channel
    assert calls.count(channel) == 1


def test_entry_with_gaps_opens_and_stops_once_and_is_not_clean_completion(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(kodi.time, 'monotonic', clock.monotonic)
    observer = Observer(clock, lambda count: unavailable() if count == 2 else None)
    opens, stops = [], []
    observer.settings = observer.user_state = observer.native_identity = lambda: {}
    def start(runtime, expected, target, value):
        opens.append(1)
        value['play_issued_at'] = clock.now
    def stop(value):
        stops.append(1)
        return dict(confirmed=True, target_terminal=True, stop_issued=True)
    observer.stop = stop
    monkeypatch.setattr(kodi, 'Runtime', lambda directory: observer)
    monkeypatch.setattr(kodi, 'perform_start', start)
    monkeypatch.setattr(kodi, 'target_evidence', lambda target: {})
    kodi.kodi_entry(dict(run_id='b' * 32, request_id='a' * 32, target={}, inspection={}, duration=10), '/unused')
    assert opens == [1] and stops == [1]
    assert observer.saved[-1]['state'] == 'completed_with_gaps'
    assert observer.saved[-1]['sampling']['error_points'] == 1
    assert observer.saved[-1]['product_proof'] is False and observer.saved[-1]['retry_allowed'] is False


def test_log_scope_can_read_v11_completed_with_gaps_without_claiming_acceptance(tmp_path):
    from test_ce2039_diagnostic_log_probe import receipt, scope_for
    value = receipt()
    value.update(tool_revision=11, state='completed_with_gaps')
    assert scope_for(tmp_path, value)['tool_revision'] == 11
