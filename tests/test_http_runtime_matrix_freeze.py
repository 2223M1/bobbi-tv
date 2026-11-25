import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('http_runtime_freeze', ROOT / 'tools/check_http_runtime_matrix.py')
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    def git(*args):
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test',
            '-c', 'user.email=test@invalid.local', *args], check=True, capture_output=True)
    git('init')
    (root / 'consumer.py').write_text('assert True\n')
    policy = root / 'policy.json'
    policy.write_text('{}')
    git('add', '.')
    git('commit', '-m', 'fixture')
    monkeypatch.setattr(matrix, 'ROOT', root)
    monkeypatch.setattr(matrix, 'POLICY', policy)
    monkeypatch.setattr(matrix, 'SUITES', ('consumer.py',))
    return root, git


def test_dirty_source_is_rejected_before_download_or_output(source, tmp_path, monkeypatch):
    root, _ = source
    (root / 'consumer.py').write_text('assert False\n')
    monkeypatch.setattr(matrix, 'prepare_floor', lambda *_: pytest.fail('No download before source freeze'))
    destination = tmp_path / 'matrix'
    with pytest.raises(ValueError, match='Commit candidate changes'):
        matrix.run_matrix(destination)
    assert not destination.exists()


@pytest.mark.parametrize('change', ['uncommitted-test', 'committed-source', 'policy'])
def test_final_identity_rejects_edits_and_new_commits(source, change):
    root, git = source
    before = matrix.source_identity(matrix.SUITES)
    matrix.require_frozen_source(before)
    if change == 'uncommitted-test':
        (root / 'consumer.py').write_text('assert False\n')
    elif change == 'policy':
        (root / 'policy.json').write_text('{"different":true}')
    else:
        (root / 'new-production.py').write_text('changed = True\n')
        git('add', '.')
        git('commit', '-m', 'changed during verification')
    with pytest.raises(ValueError, match='Source changed'):
        matrix.require_frozen_source(before, matrix.source_identity(matrix.SUITES))


def test_unchanged_clean_candidate_passes_freeze(source):
    before = matrix.source_identity(matrix.SUITES)
    matrix.require_frozen_source(before, matrix.source_identity(matrix.SUITES))
