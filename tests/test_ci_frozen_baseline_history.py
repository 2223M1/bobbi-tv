"""The primary CI checkout must retain real frozen negative-control sources."""
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_primary_pytest_checkout_requests_complete_history():
    workflow = (ROOT / '.github/workflows/verify.yml').read_text(encoding='utf-8')
    primary = workflow.split('\n  verify:\n', 1)[1].split('\n  native-contracts:', 1)[0]
    checkout = re.search(r'(?m)^      - uses: actions/checkout@v4\n'
                         r'((?:^        .*\n)*)', primary)
    assert checkout is not None
    assert re.search(r'(?m)^        with:\s*$', checkout[1])
    assert re.search(r'(?m)^          fetch-depth: 0\s*$', checkout[1])
    assert 'python -m pytest -q -rs tests ' in primary


def test_both_frozen_transport_sources_are_real_available_git_objects():
    for revision in ('c58cd3ede800ef401d203838bdc0c5e59c0a1686',
                     '7220670f1ac3dda3bfd8e8e182c778311b14be48'):
        source = subprocess.check_output(['git', 'show', revision + ':' +
            'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py'], cwd=ROOT)
        assert b'class ByteQueue:' in source and b'class Handler(' in source
        compile(source, '<frozen-' + revision[:7] + '>', 'exec')
