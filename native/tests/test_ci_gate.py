"""Gate orchestration tests; subprocess doubles are not native validation."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SPEC = importlib.util.spec_from_file_location('native_ci_gate', Path(__file__).with_name('run_ci_gate.py'))
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def result(root):
    return json.loads(next(root.glob('native-ci-*/gate-result.json')).read_text())


def test_unavailable_toolchain_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr(GATE.shutil, 'which', lambda name: None if name == 'g++' else name)
    monkeypatch.setattr(GATE.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not build')))
    assert GATE.run(tmp_path) == 2
    receipt = result(tmp_path)
    assert receipt['state'] == 'NOT_TESTED' and 'g++' in receipt['reason']
    assert not receipt['android_linked'] and not receipt['real_device_verified']


def test_clean_series_and_real_generic_runner_plus_negative_control_are_required(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(GATE.shutil, 'which', lambda name: name)
    def execute(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(GATE.subprocess, 'run', execute)
    assert GATE.run(tmp_path, tmp_path / 'immutable-source') == 0
    assert commands[0][:4] == ['git', 'clone', '--quiet', '--shared']
    assert [Path(command[1]).name for command in commands[1:]] == [
        'apply-series.py', 'run_generic.py', 'check_completion_gate.py']
    assert result(tmp_path)['state'] == 'HOST_SEMANTICS_PASSED'


def test_failed_native_step_never_reports_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(GATE.shutil, 'which', lambda name: name)
    monkeypatch.setattr(GATE.subprocess, 'run', lambda command, **kwargs: SimpleNamespace(
        returncode=1 if len(command) > 1 and Path(command[1]).name == 'run_generic.py' else 0))
    assert GATE.run(tmp_path, tmp_path / 'source') == 1
    assert result(tmp_path)['state'] == 'FAILED_NOT_PROVEN'
