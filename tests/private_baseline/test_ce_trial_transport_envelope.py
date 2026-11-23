"""Full local CLI with the real STOP authority chain; no SSH/device access."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace

import pytest

from test_ce_trial_stop_original import chain, scene, transport


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / 'tools/ce_playback_trial.py'
BASELINE = '6130cfc845b363e0d206a92960479222413aa6d6'
spec = importlib.util.spec_from_file_location('transport_envelope_cli', CLI_PATH)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@pytest.fixture
def cli_chain(chain, monkeypatch, tmp_path, capsys):
    work = next(iter(driver.trial_cases()['works']))
    chain.namespace.update(NAME=work, RUN_ID='offline-stop-envelope')
    chain.record['test'] = driver.trial_cases()['works'][work]
    calls, scripts, outputs = [], [], []

    def run(*, cli=driver, fail=None, close_error=False, operation='stop', result=None, brief=False):
        output_dir = tmp_path / ('output-' + str(len(outputs)))
        outputs.append(output_dir)
        observed = []

        def close():
            calls.append('close')
            if close_error:
                raise OSError('synthetic sensitive cleanup detail must not be retained')

        def readonly(client, script, **options):
            calls.append('execute')
            scripts.append(script)
            assert options == dict(deadline_seconds=60)
            value = chain.run() if operation == 'stop' and result is None else deepcopy(result)
            observed.append(deepcopy(value))
            if fail == 'execute':
                raise TimeoutError('synthetic response lost after execution')
            return 0, value, False

        def connect():
            calls.append('connect')
            if fail == 'connect':
                raise OSError('synthetic sensitive connection detail must not be retained')
            return SimpleNamespace(close=close), SimpleNamespace(readonly=readonly)

        wire = SimpleNamespace(connect=connect)
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None))
        with monkeypatch.context() as patch:
            patch.setattr(cli.importlib.util, 'spec_from_file_location', lambda *args: spec)
            patch.setattr(cli.importlib.util, 'module_from_spec', lambda _: wire)
            # Only SSH transport is replaced. main still builds the actual guarded
            # script; the remote STOP branch/owner runs through the chain fixture.
            patch.setattr(cli.sys, 'argv', ['trial', work, operation, '--transport-source', str(tmp_path),
                '--output-dir', str(output_dir), '--run-id', 'offline-stop-envelope'] + (['--brief'] if brief else []))
            code, escaped = 0, None
            try:
                cli.main()
            except SystemExit as error:
                code = error.code
            except Exception as error:
                escaped = error
        stdout = capsys.readouterr().out
        files = list(output_dir.glob('*.json')) if output_dir.exists() else []
        return SimpleNamespace(code=code, escaped=escaped, observed=observed, stdout=stdout, files=files,
            value=json.loads(files[0].read_text(encoding='utf-8')) if files else None,
            display=json.loads(stdout) if stdout else None)

    return SimpleNamespace(chain=chain, run=run, calls=calls, scripts=scripts, outputs=outputs)


@pytest.mark.parametrize('prior_original', [False, True])
def test_connect_failure_retains_unproved_stage_without_dispatch(cli_chain, prior_original):
    state = cli_chain
    if prior_original:
        state.chain.settle()
        assert state.chain.run()['stopped'] is True
    before = len(state.chain.native.commands)
    result = state.run(fail='connect')
    assert result.escaped is None and result.code == 2 and len(result.files) == 1
    assert result.value['exit_code'] == result.value['trial_exit_code'] == 2
    assert result.value['transport_exit_code'] == 1
    assert result.value['transport_errors'] == [dict(phase='connect', error='OSError')]
    assert result.value['transport_cleanup_attention'] is False
    assert result.value['result']['state'] == 'unproved' and result.value['result']['stopped'] is None
    assert state.calls == ['connect'] and len(state.chain.native.commands) == before
    assert 'sensitive' not in result.files[0].read_text(encoding='utf-8')


@pytest.mark.parametrize('close_error', [False, True])
def test_lost_ssh_reply_is_unproved_then_only_original_receipt_is_recovered(cli_chain, close_error):
    state = cli_chain
    state.chain.settle()
    first = state.run(fail='execute', close_error=close_error)
    assert first.escaped is None and first.code == 2
    assert first.observed[0]['stopped'] is True  # Reply existed remotely but was lost.
    assert first.value['result']['state'] == 'unproved'
    errors = [dict(phase='execute', error='TimeoutError')]
    if close_error:
        errors.append(dict(phase='close', error='OSError'))
    assert first.value['transport_errors'] == errors
    original = state.chain.path.read_bytes()
    state.chain.requests.clear()
    recovered = state.run()
    assert recovered.escaped is None and recovered.code == 0
    assert not recovered.value['result']['stop']['dispatch_attempted']
    assert all(message['operation'] == 'playback_receipt' for message in state.chain.requests)
    assert state.chain.path.read_bytes() == original and len(state.chain.native.commands) == 1


@pytest.mark.parametrize('status,code', [('applied', 0), ('failed', 1), ('unknown', 2)])
@pytest.mark.parametrize('brief', [False, True])
def test_close_failure_preserves_exact_obtained_original_and_reports_cleanup_attention(cli_chain, status, code, brief):
    state = cli_chain
    if status != 'unknown':
        state.chain.settle(status=status)
    result = state.run(close_error=True, brief=brief)
    assert result.escaped is None and result.code == code
    assert result.value['result'] == result.observed[0]
    assert result.value['exit_code'] == result.value['trial_exit_code'] == code
    assert result.value['transport_exit_code'] == 0
    assert result.value['transport_errors'] == [dict(phase='close', error='OSError')]
    assert result.value['transport_cleanup_attention'] is True
    assert result.display['transport_cleanup_attention'] is True
    assert result.display['result']['stop'] == result.value['result']['stop']
    assert len(state.chain.native.commands) == 1 and state.calls == ['connect', 'execute', 'close']
    assert 'sensitive' not in result.files[0].read_text(encoding='utf-8')


def test_success_envelope_binds_local_driver_template_and_exact_requested_script(cli_chain):
    state = cli_chain
    state.chain.settle()
    result = state.run()
    assert result.escaped is None and result.code == 0
    assert result.value['transport_errors'] == [] and not result.value['transport_cleanup_attention']
    assert result.value['tool_source'] == dict(
        driver_sha256=hashlib.sha256(CLI_PATH.read_bytes()).hexdigest(),
        remote_template_sha256=hashlib.sha256((ROOT / 'tools/ce_trial_remote.py').read_bytes()).hexdigest(),
        request_script_sha256=hashlib.sha256(state.scripts[0]).hexdigest())


@pytest.mark.parametrize('phase', ['connect', 'execute', 'close'])
def test_non_stop_transport_failure_keeps_exit_one_and_retains_observation(cli_chain, phase):
    observed = dict(operation='cards', cards=[], selected=False)
    result = cli_chain.run(operation='cards', result=observed,
        fail=None if phase == 'close' else phase, close_error=phase == 'close')
    assert result.escaped is None and result.code == 1
    assert result.value['exit_code'] == result.value['trial_exit_code'] == 1
    assert result.value['transport_errors'][0]['phase'] == phase
    if phase == 'close':
        assert result.value['result'] == observed
    assert not cli_chain.chain.native.commands and not cli_chain.chain.path.exists()


@pytest.mark.parametrize('phase', ['connect', 'close'])
def test_actual_frozen_cli_loses_envelope_for_the_same_failure_injection(cli_chain, phase):
    raw = subprocess.check_output(['git', 'show', BASELINE + ':tools/ce_playback_trial.py'], cwd=ROOT, timeout=20)
    frozen = ModuleType('frozen_stop_cli')
    frozen.__file__ = str(CLI_PATH)
    exec(compile(raw, BASELINE + ':tools/ce_playback_trial.py', 'exec'), frozen.__dict__)
    if phase == 'close':
        cli_chain.chain.settle()
    result = cli_chain.run(cli=frozen, fail='connect' if phase == 'connect' else None,
                           close_error=phase == 'close')
    assert isinstance(result.escaped, OSError) and result.files == [] and result.stdout == ''
    if phase == 'close':
        assert result.observed[0]['stopped'] is True and len(cli_chain.chain.native.commands) == 1


@pytest.mark.parametrize('phase', ['connect', 'execute', 'trace'])
def test_exit_classifier_distinguishes_unproved_transport_from_explicit_original_failure(cli_chain, phase):
    errors = [dict(phase=phase, error='OSError')]
    unknown = dict(operation='stop', error='OSError', stopped=None, state='unproved')
    assert driver.result_exit_code(unknown, remote_code=1, transport_errors=errors) == 2
    cli_chain.chain.settle(status='failed')
    failed = cli_chain.chain.run()
    assert driver.result_exit_code(failed, remote_code=1, transport_errors=errors) == 1


def test_cli_help_distinguishes_connection_loss_and_cleanup_attention():
    help_text = ' '.join(driver.build_parser().format_help().split())
    assert 'unproved including connection/response loss' in help_text
    assert 'Cleanup attention is separate' in help_text
