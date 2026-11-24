"""Real tool IPC/authority chain with synthetic native; not Kodi/device evidence."""
from frozen_history import source_bytes
import ast
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import urllib.request
from uuid import uuid4

import pytest

from test_playback_presentation import scene
from test_user_transport_presentation import transport, retain, stop_result
from test_playback_authority import select, row


ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / 'tools/ce_trial_remote.py'
FROZEN_REMOTE = '6130cfc845b363e0d206a92960479222413aa6d6'
spec = importlib.util.spec_from_file_location('stop_trial_cli', ROOT / 'tools/ce_playback_trial.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@pytest.fixture(scope='module')
def frozen_stop_code():
    source = source_bytes(FROZEN_REMOTE, 'tools/ce_trial_remote.py')
    assert hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest() == (
        '65c422330511225f33ba1822187395dc13183bc6')
    names = {'call', 'stop_trial_identity', 'read_stop_original', 'persist_stop_original',
             'stop_receipt', 'stop_original'}
    definitions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in definitions} == names
    return compile(ast.Module(body=definitions, type_ignores=[]), FROZEN_REMOTE + ':tools/ce_trial_remote.py', 'exec')


@pytest.fixture
def chain(transport, tmp_path):
    owner, native, args = transport
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    names = {'call', 'stop_trial_identity', 'read_stop_original', 'persist_stop_original',
             'stop_receipt', 'stop_original'}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "OP == 'stop'")
    config = tmp_path / 'runtime.json'
    config.write_text(json.dumps(dict(port=12345, token='test-only')))
    record = dict(test={'id': 'synthetic-test'}, request_id=args['request_id'],
        native_instance=native.current['native_instance'],
        file_identity_sha256=hashlib.sha256(b'file-a').hexdigest())
    record_path = tmp_path / 'trial-work.json'
    record_path.write_text(json.dumps(record))
    hooks, requests, outputs, clock = {}, [], [], [0.0]

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'http://127.0.0.1:12345/control'
            assert timeout == .3 and request.headers['Authorization'] == 'Bearer test-only'
            envelope = json.loads(request.data)
            assert envelope['action'] == 'playback'
            message = envelope['body']
            requests.append(deepcopy(message))
            if message['operation'] == 'playback_command':
                original = json.loads(record_path.with_suffix('.stop.json').read_text())
                assert original['command'] == message['command']  # Already readable before control.
            if hooks.get('before'):
                hooks['before'](message)
            reply = owner.dispatch(message)
            if hooks.get('after'):
                reply = hooks['after'](message, reply)
            return io.BytesIO(json.dumps(dict(ok=True, result=reply)).encode())

    namespace = dict(json=json, hashlib=hashlib, NAME='work', RUN_ID='synthetic-stop', attempt=1,
        record_path=record_path, record=record, OP='stop', print=lambda value, **_: outputs.append(json.loads(value)),
        Path=lambda path: config if str(path).endswith('/runtime.json') else Path(path),
        time=SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
        urllib=SimpleNamespace(request=SimpleNamespace(Request=urllib.request.Request,
            ProxyHandler=urllib.request.ProxyHandler, build_opener=lambda *_: Opener())))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(REMOTE), 'exec'), namespace)

    def run():
        exec(compile(ast.Module(body=branch.body, type_ignores=[]), str(REMOTE), 'exec'), namespace)
        return outputs[-1]

    def settle(status='applied', lost_ack=False, bad=None):
        control = native.control
        def stop(wire):
            result = control(wire)
            command = owner.playback_commands[wire['command_id']]['command']
            terminal = stop_result(command, status, **(bad or {}))
            retain(native, [terminal])
            native.current = None
            if lost_ack:
                raise OSError('synthetic lost native ACK')
            return result
        native.control = stop

    return SimpleNamespace(owner=owner, native=native, record=record, path=record_path.with_suffix('.stop.json'),
        namespace=namespace, hooks=hooks, requests=requests, run=run, settle=settle)


@pytest.mark.parametrize('loss', ['none', 'owner_reply', 'native_ack'])
def test_real_stop_branch_retains_original_before_send_and_recovers_only_its_receipt(chain, loss):
    chain.settle(lost_ack=loss == 'native_ack')
    def after(message, reply):
        if message['operation'] == 'playback_command' and loss == 'owner_reply':
            raise TimeoutError('synthetic lost owner response')
        return reply
    chain.hooks['after'] = after
    result = chain.run()
    assert driver.result_exit_code(result) == 0
    assert result['stopped'] and result['stop']['original_receipt_verified']
    assert result['stop']['dispatch_attempted'] is True
    original_bytes = chain.path.read_bytes()
    command = json.loads(original_bytes)['command']
    assert result['stop']['journal_sha256'] == hashlib.sha256(original_bytes).hexdigest()
    assert len(chain.native.commands) == 1 and chain.native.commands[0]['action'] == 'user_stop'
    assert chain.native.gui_commands == []
    chain.requests.clear()
    again = chain.run()
    assert driver.result_exit_code(again) == 0 and again['stop']['dispatch_attempted'] is False
    assert chain.path.read_bytes() == original_bytes and len(chain.native.commands) == 1
    assert chain.requests == [dict(operation='playback_receipt', expected=command['expected'],
                                   command_id=command['command_id'])]


def test_loss_before_owner_receives_command_is_unproved_and_never_resent(chain):
    def before(message):
        if message['operation'] == 'playback_command':
            raise TimeoutError('synthetic loss before dispatch')
    chain.hooks['before'] = before
    first = chain.run()
    original = chain.path.read_bytes()
    assert driver.result_exit_code(first) == 2 and first['state'] == 'unproved'
    assert not chain.owner.playback_commands and not chain.native.commands
    chain.hooks.clear()
    chain.requests.clear()
    second = chain.run()
    assert driver.result_exit_code(second) == 2 and not second['stop']['dispatch_attempted']
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)
    assert chain.path.read_bytes() == original and not chain.native.commands


def test_late_original_receipt_settles_prior_unknown_without_new_expected_or_control(chain):
    first = chain.run()
    assert driver.result_exit_code(first) == 2 and len(chain.native.commands) == 1
    original = chain.path.read_bytes()
    command = json.loads(original)['command']
    retain(chain.native, [stop_result(command)])
    chain.native.current = None
    chain.requests.clear()
    result = chain.run()
    assert driver.result_exit_code(result) == 0 and not result['stop']['dispatch_attempted']
    assert chain.path.read_bytes() == original and len(chain.native.commands) == 1
    assert chain.requests == [dict(operation='playback_receipt', expected=command['expected'],
                                   command_id=command['command_id'])]


def test_already_stopped_without_original_receipt_is_not_a_pass_or_new_command(chain):
    chain.native.current = None
    result = chain.run()
    assert driver.result_exit_code(result) == 2 and result['state'] == 'not_tested'
    assert not chain.path.exists() and chain.native.commands == []
    assert [message['operation'] for message in chain.requests] == ['playback_presentation']


def test_instance_change_between_journal_and_dispatch_rejects_original_cas_without_rebase(chain):
    def before(message):
        if message['operation'] == 'playback_command':
            chain.native.current['native_instance'] = str(uuid4())
    chain.hooks['before'] = before
    first = chain.run()
    assert driver.result_exit_code(first) == 1
    assert chain.native.commands == []
    original = chain.path.read_bytes()
    chain.requests.clear()
    chain.run()
    assert chain.path.read_bytes() == original
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)
    assert chain.native.commands == []


def test_original_receipt_survives_new_selection_without_stopping_replacement(chain):
    terminal = dict(chain.native.current, phase='TERMINAL', reason='STOP', sequence=2, user_intent=1)
    chain.settle()
    replacement = []
    def after(message, reply):
        if message['operation'] == 'playback_command':
            assert chain.owner.event('xbmc', 'Player.OnBobiState', terminal)
            args = select(chain.owner, 'release-b')
            assert chain.owner.dispatch(dict(args, operation='bind_file', selection_identity='release-b',
                file_identity='file-b', url_sha256='b' * 64))['bound']
            assert chain.owner.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
            chain.native.current = row(args['request_id'], 'file-b', url_sha256='b' * 64,
                audio_intent=0, open_epoch=chain.native.epoch, control_protocol=1)
            replacement.append(deepcopy(chain.native.current))
            raise TimeoutError('synthetic lost response after replacement')
        return reply
    chain.hooks['after'] = after
    assert driver.result_exit_code(chain.run()) == 0
    chain.requests.clear()
    assert driver.result_exit_code(chain.run()) == 0
    assert chain.native.current == replacement[0] and len(chain.native.commands) == 1
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)
    assert chain.native.gui_commands == []


@pytest.mark.parametrize('change', ['boot', 'ledger'])
def test_owner_restart_or_lost_ledger_never_borrows_idle_or_rearms_original(chain, change):
    chain.settle()
    assert driver.result_exit_code(chain.run()) == 0
    original = chain.path.read_bytes()
    if change == 'boot':
        chain.owner.owner.boot_id = uuid4().hex
    else:
        chain.owner.playback_commands.clear()
    chain.requests.clear()
    result = chain.run()
    assert driver.result_exit_code(result) == 2 and not result['stop']['original_receipt_verified']
    assert chain.path.read_bytes() == original and len(chain.native.commands) == 1
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)


@pytest.mark.parametrize('bad', [dict(command_id='d' * 32), dict(request_id='d' * 32),
    dict(native_instance='11111111-1111-1111-1111-111111111111'), dict(file_sha256='d' * 64),
    dict(expected_sequence=99), dict(terminal_reason='ERROR'), dict(terminal_user_intent=0)])
def test_real_authority_rejects_malformed_or_other_stop_receipt(chain, bad):
    chain.settle(bad=bad)
    result = chain.run()
    assert driver.result_exit_code(result) == 2 and not result['stopped']
    assert len(chain.native.commands) == 1


def test_explicit_original_terminal_failure_is_failure_not_success(chain):
    chain.settle(status='failed')
    result = chain.run()
    assert driver.result_exit_code(result) == 1 and result['state'] == 'failed'
    assert result['stop']['receipt']['status'] == 'failed' and not result['stopped']


@pytest.mark.parametrize('case', ['partial', 'wrong_trial', 'retargeted'])
def test_corrupt_or_retargeted_journal_fails_closed_without_any_control(chain, case):
    if case == 'partial':
        chain.path.write_text('{')
    else:
        chain.settle()
        chain.run()
        value = json.loads(chain.path.read_text())
        if case == 'wrong_trial':
            value['trial']['run_id'] = 'other'
        else:
            value['command']['expected']['native_instance'] = str(uuid4())
        chain.path.write_text(json.dumps(value))
    chain.requests.clear()
    count = len(chain.native.commands)
    with pytest.raises(AssertionError, match='STOP_JOURNAL_INVALID'):
        chain.run()
    assert chain.requests == [] and len(chain.native.commands) == count


def test_fsync_failure_prevents_send_and_keeps_original_disarmed(chain, monkeypatch):
    def failed(_):
        raise OSError('synthetic fsync failure')
    monkeypatch.setattr(os, 'fsync', failed)
    with pytest.raises(OSError):
        chain.run()
    assert not chain.native.commands and chain.path.exists()
    chain.requests.clear()
    result = chain.run()
    assert driver.result_exit_code(result) == 2 and not result['stop']['dispatch_attempted']
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)


def test_completed_fsync_precedes_only_control_and_repeated_run_has_no_new_write(chain, monkeypatch):
    fsync, calls = os.fsync, []
    def synced(descriptor):
        fsync(descriptor)
        calls.append('fsync_completed')
    monkeypatch.setattr(os, 'fsync', synced)
    def before(message):
        if message['operation'] == 'playback_command':
            assert calls and calls[-1] == 'fsync_completed'
            calls.append('control')
    chain.hooks['before'] = before
    chain.settle()
    assert driver.result_exit_code(chain.run()) == 0
    assert calls[-1] == 'control' and calls.count('control') == 1
    count = len(calls)
    assert driver.result_exit_code(chain.run()) == 0 and len(calls) == count


def test_crash_after_persistence_before_send_does_not_rearm_on_next_invocation(chain):
    persist = chain.namespace['persist_stop_original']
    def crash(path, candidate):
        persist(path, candidate)
        raise InterruptedError('synthetic process death before dispatch')
    chain.namespace['persist_stop_original'] = crash
    with pytest.raises(InterruptedError):
        chain.run()
    original = chain.path.read_bytes()
    assert not chain.native.commands
    chain.requests.clear()
    assert driver.result_exit_code(chain.run()) == 2
    assert chain.path.read_bytes() == original and not chain.native.commands
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)


def test_terminal_stop_without_this_command_receipt_never_passes_even_when_idle(chain):
    control = chain.native.control
    def unrelated_stop(command):
        result = control(command)
        chain.native.current.update(phase='TERMINAL', reason='STOP', sequence=2, user_intent=1)
        return result
    chain.native.control = unrelated_stop
    first = chain.run()
    assert driver.result_exit_code(first) == 2 and not first['stopped']
    chain.native.current = None
    chain.requests.clear()
    assert driver.result_exit_code(chain.run()) == 2 and len(chain.native.commands) == 1
    assert all(message['operation'] == 'playback_receipt' for message in chain.requests)


@pytest.mark.parametrize('case', ['wrong_command', 'no_command', 'applied_string'])
def test_tool_rejects_unbound_or_malformed_owner_receipt(chain, case):
    chain.settle()
    def after(message, reply):
        if message['operation'] == 'playback_receipt':
            if case == 'wrong_command': return dict(reply, command_id='d' * 32)
            if case == 'no_command': return {'status': 'applied'}
            return 'applied'
        return reply
    chain.hooks['after'] = after
    assert driver.result_exit_code(chain.run()) == 2 and len(chain.native.commands) == 1


def test_exclusive_creation_race_loser_can_only_lookup_winners_original(chain):
    persist = chain.namespace['persist_stop_original']
    winner = []
    def race(path, candidate):
        original = deepcopy(candidate)
        original['command']['command_id'] = uuid4().hex
        persist(path, original)
        winner.append(original['command'])
        return persist(path, candidate)  # The real O_EXCL, not an injected exception, must reject this writer.
    chain.namespace['persist_stop_original'] = race
    result = chain.run()
    assert driver.result_exit_code(result) == 2 and not chain.native.commands
    assert result['stop']['original']['command'] == winner[0]
    assert all(message['operation'] != 'playback_command' for message in chain.requests)
    assert all(message['command_id'] == winner[0]['command_id'] for message in chain.requests
               if message['operation'] == 'playback_receipt')


@pytest.mark.parametrize('implementation', ['current', 'frozen'])
@pytest.mark.parametrize('presentation', ['unavailable', 'lost_reply', 'replacement'])
def test_concurrent_winner_during_presentation_recovers_only_persisted_original(
        chain, frozen_stop_code, implementation, presentation):
    if implementation == 'frozen':
        # The actual frozen functions run in the same real IPC/authority fixture.
        # Their historical failure is the negative control, not a made-up stub.
        exec(frozen_stop_code, chain.namespace)
    terminal = dict(chain.native.current, phase='TERMINAL', reason='STOP', sequence=2, user_intent=1)
    chain.settle()
    winners, originals, replacements = [], [], []

    def before(message):
        if message['operation'] != 'playback_presentation':
            return
        chain.hooks.clear()
        # Deterministically interleave a second complete invocation while the
        # first is suspended in its read. Both execute real persistence/control.
        winners.append(chain.run())
        originals.append(chain.path.read_bytes())
        chain.requests.clear()  # From this point only the losing invocation runs.
        if presentation == 'lost_reply':
            raise TimeoutError('synthetic concurrent presentation loss')
        if presentation == 'replacement':
            assert chain.owner.event('xbmc', 'Player.OnBobiState', terminal)
            args = select(chain.owner, 'release-b')
            assert chain.owner.dispatch(dict(args, operation='bind_file', selection_identity='release-b',
                file_identity='file-b', url_sha256='b' * 64))['bound']
            assert chain.owner.dispatch(dict(args, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
            chain.native.current = row(args['request_id'], 'file-b', url_sha256='b' * 64,
                audio_intent=0, open_epoch=chain.native.epoch, control_protocol=1)
            chain.owner.refresh()
            replacements.append(deepcopy(chain.native.current))

    chain.hooks['before'] = before
    if implementation == 'frozen' and presentation != 'unavailable':
        error, reason = ((TimeoutError, 'synthetic concurrent presentation loss') if presentation == 'lost_reply'
                         else (AssertionError, 'STOP_TRIAL_SCOPE_CHANGED'))
        with pytest.raises(error, match=reason):
            chain.run()
    else:
        result = chain.run()
        if implementation == 'frozen':
            assert driver.result_exit_code(result) == 2 and result['state'] == 'not_tested'
            assert 'original' not in result['stop']
        else:
            assert driver.result_exit_code(result) == 0 and result['state'] == 'confirmed'
            assert result['stop']['original_receipt_verified'] and not result['stop']['dispatch_attempted']
            assert result['stop']['original'] == json.loads(originals[0])
    assert len(winners) == 1 and driver.result_exit_code(winners[0]) == 0
    assert winners[0]['stop']['dispatch_attempted'] is True
    assert chain.path.read_bytes() == originals[0]
    original = json.loads(originals[0])['command']
    lookup = dict(operation='playback_receipt', expected=original['expected'], command_id=original['command_id'])
    assert chain.requests == ([lookup] if implementation == 'current' else [])
    assert chain.owner.dispatch(lookup)['status'] == 'applied'
    assert len(chain.native.commands) == 1 and chain.native.gui_commands == []
    if replacements:
        assert chain.native.current == replacements[0]


@pytest.mark.parametrize('failure', ['lost_reply', 'changed_scope'])
def test_preflight_error_without_concurrent_original_keeps_original_failure_and_never_sends(chain, failure):
    if failure == 'lost_reply':
        def before(message):
            raise TimeoutError('synthetic presentation loss without original')
        chain.hooks['before'] = before
        error, reason = TimeoutError, 'synthetic presentation loss without original'
    else:
        chain.record['native_instance'] = str(uuid4())
        error, reason = AssertionError, 'STOP_TRIAL_SCOPE_CHANGED'
    with pytest.raises(error, match=reason):
        chain.run()
    assert not chain.path.exists() and chain.native.commands == []
    assert chain.requests == [dict(operation='playback_presentation')]


@pytest.mark.parametrize('field', ['request_id', 'native_instance', 'file_identity_sha256'])
def test_unbound_or_changed_trial_never_freshly_binds_to_current_player(chain, field):
    chain.record.pop(field)
    with pytest.raises(AssertionError, match='STOP_TRIAL_NOT_BOUND'):
        chain.run()
    assert not chain.requests and not chain.path.exists() and not chain.native.commands


@pytest.mark.parametrize('result,code', [({'stopped': True}, 2), ({'stopped': False}, 1),
    ({'stopped': True, 'before': {'native': 'old'}}, 2), ({}, 2)])
def test_legacy_global_idle_output_never_proves_original_command(result, code):
    assert driver.result_exit_code(result, operation='stop') == code


@pytest.mark.parametrize('change', ['no_original', 'wrong_id', 'ack_only', 'false_proof', 'hash', 'partial_expected'])
def test_local_output_contract_requires_full_original_and_exact_applied_receipt(chain, change):
    chain.settle()
    result = chain.run()
    stop = result['stop']
    if change == 'no_original': stop.pop('original')
    elif change == 'wrong_id': stop['receipt']['command_id'] = 'd' * 32
    elif change == 'ack_only': stop['receipt']['status'] = 'queued'
    elif change == 'false_proof': stop['original_receipt_verified'] = False
    elif change == 'hash': stop['journal_sha256'] = 'd' * 64
    else: stop['original']['command']['expected'].pop('audio_intent')
    assert driver.result_exit_code(result) == 2


def test_cli_help_describes_stop_original_receipt_and_no_retry_contract():
    help_text = ' '.join(driver.build_parser().format_help().split())
    assert 'original receipt applied' in help_text and 'never resend' in help_text
