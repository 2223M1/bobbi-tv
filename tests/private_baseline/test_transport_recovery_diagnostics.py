"""Closed diagnostics and one known-pre-native NOT_READY refresh, no device IO."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from threading import Event, Thread
from types import MethodType, SimpleNamespace

import pytest

from bobbi_core import preparation_client
from bobbi_core.resolve_lane import ResolveLane
from lib.cinema import playback_request
from lib.utils.player import transport_recovery as module
from lib.utils.player.transport_recovery import Diagnostics, Recovery, verify_ready
from test_transport_recovery import recovery_case, proved, prime
from test_transport_recovery_native import methods


def events(rows):
    return [row['event'] for row in rows]


def test_diagnostic_schema_is_closed_deduplicated_bounded_and_thread_safe():
    rows = []
    diagnostic = Diagnostics(rows.append, request_id='a' * 32)
    def emit():
        for _ in range(100):
            diagnostic('WORKER_ERROR', state='http://private/credential', error=RuntimeError('private_cookie'))
            diagnostic('http://private/event', state='READY')
    workers = [Thread(target=emit) for _ in range(8)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(1)
    assert len(rows) == 1 and rows[0]['error'] == 'RUNTIME_ERROR' and rows[0]['state'] == 'UNKNOWN'
    for event in sorted(module.DIAGNOSTIC_EVENTS):
        for state in sorted(module.DIAGNOSTIC_STATES): diagnostic(event, state=state)
    assert len(rows) == module.DIAGNOSTIC_LIMIT == 64
    assert [row['sequence'] for row in rows] == list(range(1, 65))
    assert rows[-1]['event'] == 'DIAGNOSTIC_LIMIT' and len(diagnostic.seen) == 64
    assert all(set(row) == {'schema', 'request', 'sequence', 'event', 'state', 'error'} for row in rows)
    raw = json.dumps(rows)
    assert 'private' not in raw and 'credential' not in raw and 'cookie' not in raw


@pytest.mark.parametrize('error,label', [(TimeoutError('secret'), 'TIMEOUT'), (OSError('secret'), 'OS_ERROR'),
    (ValueError('secret'), 'VALUE_ERROR'), (TypeError('secret'), 'TYPE_ERROR'), (KeyError('secret'), 'KEY_ERROR'),
    (RuntimeError('secret'), 'RUNTIME_ERROR'), (Exception('secret'), 'OTHER')])
def test_optional_callback_receives_only_fixed_error_and_state_codes(error, label):
    calls = []
    module.diagnostic_note(lambda event, **fields: calls.append((event, fields)),
        'WORKER_ERROR', state='secret', error=error, elapsed_ms=10**20)
    assert calls == [('WORKER_ERROR', {'state': 'UNKNOWN', 'error': label, 'elapsed_ms': None})]


@pytest.mark.parametrize('delay', [-1, True, float('inf'), 'secret', 600001])
def test_diagnostic_time_is_optional_bounded_integer(delay):
    rows = []
    Diagnostics(rows.append, 'secret')('CAPTURE_REQUEST', elapsed_ms=delay)
    assert 'elapsed_ms' not in rows[0] and rows[0]['request'] == ''


def test_throwing_diagnostic_callback_does_not_change_recovery_controls(recovery_case):
    case = recovery_case
    def broken(*args, **kwargs): raise RuntimeError('sink unavailable')
    recovery = prime(case, Recovery(verify=lambda *args: case.result, diagnostic=broken))
    recovery.tick(6.4, 123.45, True, False, case.context, case.command)
    case.phases[0] = 'STOPPED'
    recovery.poll(7, case.command)
    assert recovery.reserve(case.command) is not None
    assert [body['operation'] for body in case.commands] == [
        'transport_capture', 'transport_status', 'transport_stop', 'transport_status', 'reserve_child']


def test_successful_transition_diagnostics_never_include_files_capsules_or_account(recovery_case, monkeypatch):
    case, rows, clock = recovery_case, [], [10.]
    monkeypatch.setattr(module, 'monotonic', lambda: clock[0])
    recovery = Recovery(verify=lambda *args: case.result,
                        diagnostic=Diagnostics(rows.append, case.data['request_id']))
    recovery.tick(0, 123.45, True, False, case.context, case.command)
    recovery.tick(6, 123.45, True, False, case.context, case.command)
    recovery.worker.join(1)
    clock[0] = 12.01
    recovery.tick(8.01, 123.45, True, False, case.context, case.command)
    recovery.tick(8.4, 123.45, True, False, case.context, case.command)
    case.phases[0] = 'STOPPED'
    recovery.poll(9, case.command)
    assert recovery.reserve(case.command)
    assert {'WATCH_STARTED', 'WATCH_THRESHOLD', 'WORKER_START', 'WORKER_READY', 'CAPTURE_REQUEST',
            'CAPTURE_REPLY', 'POLL_REPLY', 'STOP_REQUEST', 'STOP_REPLY', 'POLL_STOPPED',
            'RESERVE_REQUEST', 'RESERVE_READY'} <= set(events(rows))
    capture = next(row for row in rows if row['event'] == 'CAPTURE_REQUEST')
    assert 2000 <= capture['elapsed_ms'] <= 2020
    raw = json.dumps(rows)
    for value in (case.result['url'], case.context['file_identity'], case.entry['path'],
                  case.context['account_scope']['account_id'], case.result['verification']['verification_id']):
        assert value not in raw


@pytest.mark.parametrize('result,error,event', [(None, None, 'WORKER_UNAVAILABLE'),
    (None, RuntimeError('private-url'), 'WORKER_ERROR')])
def test_worker_outcomes_are_visible_and_do_not_trigger_capture(recovery_case, result, error, event):
    rows, case = [], recovery_case
    def verify(*args):
        if error: raise error
        return result
    recovery = Recovery(verify=verify, diagnostic=Diagnostics(rows.append))
    recovery.tick(0, 1, True, False, case.context, case.command)
    recovery.tick(6, 1, True, False, case.context, case.command)
    recovery.worker.join(1)
    recovery.tick(6.1, 1, True, False, case.context, case.command)
    assert event in events(rows) and not case.commands and 'private-url' not in json.dumps(rows)


@pytest.mark.parametrize('change,event', [('absent', 'VERIFY_NO_CANDIDATE'), ('ambiguous', 'VERIFY_AMBIGUOUS'),
    ('status', 'VERIFY_STATUS_REJECTED'), ('version', 'VERIFY_VERSION_MISMATCH'),
    ('unavailable', 'VERIFY_UNAVAILABLE'), ('ready', 'VERIFY_READY')])
def test_verifier_reports_exact_branch_without_extra_cloud_calls(recovery_case, monkeypatch, change, event):
    case, rows, calls = recovery_case, [], []
    if change == 'absent': case.entry['state'] = 'pending'
    elif change == 'ambiguous': case.index['titles'][0]['sources'].append(deepcopy(case.entry))
    elif change == 'status': case.status['state'] = 'validating'
    elif change == 'version': case.status['result']['tasks'][0]['version_key'] = '9' * 64
    def call(method, body, **kwargs):
        calls.append(method)
        if method == 'status': return case.status
        if change == 'unavailable': return {'state': 'unavailable'}
        return dict(state='ready', **body, file_id=case.entry['prepared_file_id'], path=case.entry['path'],
            bytes=case.entry['bytes'], version_key=case.entry['prepared_version_key'], video_context=case.entry['video_context'])
    monkeypatch.setattr(preparation_client, 'call', call)
    result = verify_ready(case.context, lambda: False, Diagnostics(rows.append))
    assert bool(result) == (change == 'ready') and event in events(rows)
    assert calls == ([] if change in ('absent', 'ambiguous') else ['status'] if change in ('status', 'version') else ['status', 'resolve'])


@pytest.mark.parametrize('guard,event', [('policy', 'ENTRY_POLICY'), ('direct', 'ENTRY_NOT_BT'),
    ('prepared', 'ENTRY_PREPARED'), ('instance', 'ENTRY_NO_INSTANCE'), ('cancel', 'ENTRY_CANCELLED'),
    ('buffer', 'ENTRY_NOT_BUFFERING')])
def test_real_native_entry_guard_reasons_are_deduplicated(recovery_case, monkeypatch, guard, event):
    case, rows = recovery_case, []
    env = dict(json_dumps=json.dumps, kodilog=lambda value, **kwargs: rows.append(json.loads(value.split('] ', 1)[1])),
        xbmc=SimpleNamespace(LOGINFO=1), get_visibility=lambda name: guard != 'buffer', monotonic=lambda: 0)
    actor = SimpleNamespace(data=deepcopy(case.data), playback_session_id=case.data['request_id'],
        _native_instance='native-A', _cinema_cancel=Event())
    if guard == 'policy': actor.data['selection_policy'] = 'manual'
    elif guard == 'direct': actor.data['is_torrent'] = False
    elif guard == 'prepared': actor.data['prepared_resource_id'] = 'resource'
    elif guard == 'instance': actor._native_instance = None
    elif guard == 'cancel': actor._cinema_cancel.set()
    for name, method in methods({'_transport_note', 'check_cinema_transport_recovery'}, env).items():
        setattr(actor, name, MethodType(method, actor))
    monkeypatch.setattr(playback_request, 'call', lambda *args: pytest.fail('guard must not start IO'))
    for _ in range(100): actor.check_cinema_transport_recovery()
    assert events(rows).count(event) == 1
    assert getattr(actor, '_transport_recovery', None) is None


@pytest.mark.parametrize('change,event', [('valid', 'CONTEXT_READY'), ('missing', 'CONTEXT_REJECTED'),
    ('cached', 'CONTEXT_CACHED'), ('owner', 'CONTEXT_OWNER_CHANGED'), ('error', 'CONTEXT_ERROR')])
def test_real_native_context_and_watch_path_are_visible(recovery_case, monkeypatch, change, event):
    case, rows = recovery_case, []
    env = dict(json_dumps=json.dumps, kodilog=lambda value, **kwargs: rows.append(json.loads(value.split('] ', 1)[1])),
        xbmc=SimpleNamespace(LOGINFO=1), get_visibility=lambda name: name == 'Player.Caching', monotonic=lambda: 0)
    actor = SimpleNamespace(data=deepcopy(case.data), playback_session_id=case.data['request_id'],
        _native_instance='native-A', _cinema_cancel=Event(), current_time=123.45,
        _owner_context=case.context['owner'], _cinema_prepare_intent=case.target)
    if change == 'missing': actor._cinema_prepare_intent = None
    elif change == 'cached': actor._transport_source_context = case.context
    elif change == 'owner': case.snapshot['epoch'] += 1
    def call(*args):
        if change == 'error': raise OSError('http://private/credential')
        return case.snapshot
    monkeypatch.setattr(playback_request, 'call', call)
    for name, method in methods({'_transport_note', 'check_cinema_transport_recovery'}, env).items():
        setattr(actor, name, MethodType(method, actor))
    actor.check_cinema_transport_recovery()
    assert event in events(rows) and 'private' not in json.dumps(rows)
    if change == 'missing': assert 'WATCH_CONTEXT_MISSING' in events(rows)
    elif change in ('valid', 'cached'): assert 'WATCH_STARTED' in events(rows)


def actual_host_capture(host, body):
    path = Path(__file__).resolve().parents[2]/'addons/script.module.bobbi.platform/lib/bobbi_platform/host.py'
    branch = next(node for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == 'action'
        and isinstance(node.test.ops[0], ast.In) and isinstance(node.test.comparators[0], ast.Tuple)
        and [value.value for value in node.test.comparators[0].elts] == ['playback', 'standard_playback'])
    fn = ast.FunctionDef(name='dispatch', args=ast.arguments(posonlyargs=[],
        args=[ast.arg(arg='self'), ast.arg(arg='body'), ast.arg(arg='action')],
        kwonlyargs=[], kw_defaults=[], defaults=[]), body=[branch], decorator_list=[])
    env = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), 'actual-host-capture', 'exec'), env)
    return env['dispatch'](host, body, 'playback')


def test_real_expired_resolve_lane_receipt_gets_one_new_nonce_before_any_native_control(recovery_case, monkeypatch):
    case, now, requests, owner_calls, verifications, rows = recovery_case, [6.], [], [], [], []
    monkeypatch.setattr(module, 'monotonic', lambda: now[0])
    class Resolver:
        def plan(self, body): return {'body': deepcopy(body)}
        def perform(self, plan): return True
        def finish(self, plan, verified):
            if not verified: return {'state': 'unavailable'}
            return dict(state='ready', **plan['body'], file_id=case.entry['prepared_file_id'],
                path=case.entry['path'], bytes=case.entry['bytes'], version_key=case.entry['prepared_version_key'],
                video_context=case.entry['video_context'])
    lane = ResolveLane(Resolver(), lambda: now[0])
    def verify(context, cancelled):
        verification = dict(case.verification, verification_id=('e' if not verifications else 'f') * 32)
        verifications.append(verification)
        assert lane.request(verification)['state'] == 'pending'
        for _ in range(4):
            lane.tick()
            if lane.future is not None: lane.future.result(timeout=1)
            lane.tick()
            if lane.request(verification)['state'] == 'ready':
                return dict(case.result, verification=verification)
        pytest.fail('bounded real verification did not finish')
    def owned(body):
        owner_calls.append(body)
        return dict(authorized=True, state='PENDING', token='9' * 32)
    host = SimpleNamespace(native_rpc=object(), accounts=SimpleNamespace(require_current=lambda scope: scope),
        preparation=SimpleNamespace(request=lambda method, body, scope: lane.request(body)), _owner_request=owned)
    def command(body):
        result = actual_host_capture(host, body)
        requests.append((body, result))
        return result
    recovery = Recovery(verify=verify, diagnostic=Diagnostics(rows.append))
    try:
        recovery.tick(0, 55.462, True, False, case.context, command)
        recovery.tick(6, 55.462, True, False, case.context, command)
        recovery.worker.join(1)
        now[0] = 8.01  # Existing ready TTL is two seconds; no timeout is changed.
        recovery.tick(now[0], 55.462, True, False, case.context, command)
        assert requests[0][1] == {'authorized': False, 'state': 'NOT_READY'}
        assert not owner_calls and not recovery.attempted and not recovery.stop_sent
        assert recovery.state == 'WATCHING'
        now[0] = 13.01  # Existing five-second retry backoff.
        recovery.tick(now[0], 55.462, True, False, case.context, command)
        recovery.worker.join(1)
        now[0] = 13.02
        recovery.tick(now[0], 55.462, True, False, case.context, command)
        assert len(verifications) == 2 and len({row['verification_id'] for row in verifications}) == 2
        assert len(requests) == 2 and len(owner_calls) == 1 and recovery.state == 'CAPTURING'
        assert not recovery.stop_sent and 'CAPTURE_REVERIFY_SCHEDULED' in events(rows)
        assert any(row['event'] == 'CAPTURE_REPLY' and row['state'] == 'NOT_READY' for row in rows)
        assert 2000 <= next(row for row in rows if row['event'] == 'CAPTURE_REQUEST')['elapsed_ms'] <= 2020
    finally:
        recovery.close()
        lane.close()


@pytest.mark.parametrize('reply', [None, {}, {'authorized': False, 'state': 'REJECTED'},
    {'authorized': False, 'state': 'UNSUPPORTED'}, {'authorized': False, 'state': 'ALREADY_ATTEMPTED'},
    {'authorized': 0, 'state': 'NOT_READY'}, {'authorized': False, 'state': 'NOT_READY', 'token': '9' * 32}])
def test_only_exact_known_pre_native_not_ready_may_reverify(recovery_case, reply):
    calls, attempts, case = [], [], recovery_case
    recovery = Recovery(verify=lambda *args: attempts.append(1) or case.result)
    def command(body): calls.append(body); return reply
    for tick in (0, 6): recovery.tick(tick, 10, True, False, case.context, command)
    recovery.worker.join(1)
    for tick in (6.1, 12, 20, 50): recovery.tick(tick, 10, True, False, case.context, command)
    assert len(calls) == len(attempts) == 1 and recovery.state == 'REJECTED' and not recovery.stop_sent


@pytest.mark.parametrize('fresh', ['none', 'error', 'ready_but_not_ready_again'])
def test_not_ready_refresh_is_one_bounded_verification_not_a_new_retry_loop(recovery_case, fresh):
    case, attempts, calls = recovery_case, [], []
    def verify(*args):
        attempts.append(1)
        if len(attempts) == 2:
            if fresh == 'none': return None
            if fresh == 'error': raise RuntimeError('private data')
        return case.result
    def command(body): calls.append(body); return dict(authorized=False, state='NOT_READY')
    recovery = Recovery(verify=verify)
    for tick in (0, 6): recovery.tick(tick, 10, True, False, case.context, command)
    recovery.worker.join(1)
    recovery.tick(6.1, 10, True, False, case.context, command)
    recovery.tick(11.1, 10, True, False, case.context, command)
    recovery.worker.join(1)
    for tick in (11.2, 20, 50, 100): recovery.tick(tick, 10, True, False, case.context, command)
    assert len(attempts) == 2 and len(calls) == (2 if fresh == 'ready_but_not_ready_again' else 1)
    assert recovery.state == 'REJECTED' and not recovery.stop_sent


def test_pause_during_the_single_fresh_recheck_cannot_capture_or_stop(recovery_case):
    case, release, started, attempts, calls = recovery_case, Event(), Event(), [], []
    def verify(*args):
        attempts.append(1)
        if len(attempts) == 2:
            started.set()
            assert release.wait(1)
        return case.result
    def command(body): calls.append(body); return dict(authorized=False, state='NOT_READY')
    recovery = Recovery(verify=verify)
    try:
        for tick in (0, 6): recovery.tick(tick, 10, True, False, case.context, command)
        recovery.worker.join(1)
        recovery.tick(6.1, 10, True, False, case.context, command)
        recovery.tick(11.1, 10, True, False, case.context, command)
        assert started.wait(1)
        recovery.tick(11.2, 10, True, True, case.context, command)
        release.set()
        recovery.worker.join(1)
        recovery.tick(20, 10, True, False, case.context, command)
        assert len(attempts) == 2 and len(calls) == 1 and not recovery.stop_sent
    finally:
        release.set()
        recovery.close()


def test_single_recheck_worker_start_failure_is_terminal_not_replayed(recovery_case, monkeypatch):
    case, calls = recovery_case, []
    recovery = Recovery(verify=lambda *args: case.result)
    def command(body): calls.append(body); return dict(authorized=False, state='NOT_READY')
    for tick in (0, 6): recovery.tick(tick, 10, True, False, case.context, command)
    recovery.worker.join(1)
    recovery.tick(6.1, 10, True, False, case.context, command)
    class FailedThread:
        def __init__(self, **kwargs): pass
        def start(self): raise RuntimeError('synthetic unavailable worker')
    monkeypatch.setattr(module, 'Thread', FailedThread)
    for tick in (11.1, 20, 100): recovery.tick(tick, 10, True, False, case.context, command)
    assert recovery.state == 'REJECTED' and len(calls) == 1 and not recovery.stop_sent
