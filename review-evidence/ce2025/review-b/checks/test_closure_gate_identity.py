"""Independent regression: receipt must identify the checkout actually executed.

Run: BOBBI_REVIEW_ROOT=/absolute/fixed/source python -m pytest -q this_file
Uses temporary local repositories only; no product files or remotes are changed.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(os.environ.get('BOBBI_REVIEW_ROOT', Path(__file__).resolve().parents[1] / 'ce2024-review'))


def local_repository(path, identity):
    path.mkdir()
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    (path / 'identity.txt').write_text(identity + '\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(path), 'add', 'identity.txt'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Independent Review',
                    '-c', 'user.email=review@example.invalid', 'commit', '-qm', identity], check=True)
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


@pytest.mark.parametrize('different_root', [False, True], ids=['same-root-control', 'different-execution-root'])
def test_receipt_commit_identifies_executed_checkout(tmp_path, different_root):
    recorder_root, execution_root = tmp_path / 'recorder', tmp_path / 'execution'
    recorder_commit = local_repository(recorder_root, 'recorder-source')
    execution_commit = local_repository(execution_root, 'executed-source')
    assert recorder_commit != execution_commit
    spec = importlib.util.spec_from_file_location('reviewed_closure_gate', REPO / 'tools/closure_gate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = recorder_root  # Isolate receipt writes; run() remains the product implementation.
    root = execution_root if different_root else recorder_root
    expected = execution_commit if different_root else recorder_commit
    command = [sys.executable, '-c',
               'import subprocess; print(subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip())']
    assert module.run('identity-probe', command, root=root) == 0
    directory = recorder_root / 'review-evidence/ce2023/identity-probe'
    receipt = json.loads((directory / 'result.json').read_text())
    actual_command_head = (directory / 'stdout.log').read_text().strip()
    assert actual_command_head == expected
    output = os.environ.get('BOBBI_REVIEW_OUTPUT')
    if output:
        target = Path(output)
        target.mkdir(parents=True, exist_ok=True)
        result = {'case': 'different-execution-root' if different_root else 'same-root-control',
                  'executed_head': actual_command_head, 'recorded_head': receipt['commit'],
                  'recorded_dirty': receipt['dirty'], 'cwd': receipt['cwd'],
                  'source_path': 'tools/closure_gate.py', 'source_lines': [19, 24, 25],
                  'matches_executed_checkout': receipt['commit'] == expected}
        (target / (result['case'] + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    assert receipt['commit'] == expected, 'Receipt attributed execution to recorder checkout instead of cwd checkout'
