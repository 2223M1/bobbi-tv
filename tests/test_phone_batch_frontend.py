"""Run the shipped browser script's event-level lifecycle regression suite."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest


def test_browser_batch_lifecycle():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the browser event regression suite')
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, BOBBI_TEST_PYTHON=sys.executable)
    result = subprocess.run([node, '--test', str(root / 'tests/frontend/test_catalog_batch_lifecycle.cjs'),
                             str(root / 'tests/frontend/test_catalog_phone_contract.cjs')],
                            cwd=root, env=env, text=True, encoding='utf-8', capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
