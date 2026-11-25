"""Python optimization must never remove publication validation."""
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('optimized', [False, True])
def test_entry_identity_gate_survives_python_optimization(tmp_path, optimized):
    target = tmp_path / 'bad-entry.zip'
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('script.bobbi.start/addon.xml', '<addon id="unexpected.addon"/>')
    probe = '''import sys
sys.path.insert(0, sys.argv[1])
from audit_ce_entry import audit
try:
    audit(sys.argv[2])
except ValueError as error:
    if str(error) != 'Entry addon identity differs':
        raise
else:
    raise RuntimeError('Invalid entry was accepted')
'''
    command = [sys.executable, '-B'] + (['-O'] if optimized else [])
    result = subprocess.run(command + ['-c', probe, str(ROOT / 'tools'), str(target)],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
