"""The primary CI checkout must retain real frozen negative-control sources."""
import json
from pathlib import Path
import re
import zlib

import pytest

from frozen_history import FIXTURES, source_bytes


ROOT = Path(__file__).resolve().parents[1]


def test_primary_and_kodi_jobs_execute_historical_controls():
    workflow = (ROOT / '.github/workflows/verify.yml').read_text(encoding='utf-8')
    primary = workflow.split('\n  verify:\n', 1)[1].split('\n  native-contracts:', 1)[0]
    assert 'python -m pytest -q -rs tests ' in primary
    assert 'python -m pytest -q -rs tests/private_baseline ' in primary


def test_portable_records_bind_every_shipped_object():
    manifest = json.loads((FIXTURES/'manifest.json').read_text(encoding='utf-8'))
    assets = set()
    assert manifest['schema'] == 1 and manifest['commits']
    for commit, snapshot in manifest['commits'].items():
        assert re.fullmatch('[0-9a-f]{40}', commit) and re.fullmatch('[0-9a-f]{40}', snapshot['tree'])
        for path, record in snapshot['files'].items():
            assert path.endswith('.py') and not Path(path).is_absolute() and '..' not in Path(path).parts
            assert source_bytes(commit, path)
            assets.add(record['sha256'] + '.zlib')
    assert assets == {asset.name for asset in FIXTURES.glob('*.zlib')}


def test_changed_historical_blob_fails_before_execution(tmp_path):
    manifest = (FIXTURES/'manifest.json').read_bytes()
    (tmp_path/'manifest.json').write_bytes(manifest)
    commit, snapshot = next(iter(json.loads(manifest)['commits'].items()))
    path, record = next(iter(snapshot['files'].items()))
    (tmp_path/(record['sha256']+'.zlib')).write_bytes(zlib.compress(b'raise RuntimeError("not the old source")'))
    with pytest.raises(ValueError, match='Historical source identity mismatch'):
        source_bytes(commit, path, directory=tmp_path)


def test_both_frozen_transport_sources_are_real_available_git_objects():
    for revision in ('c58cd3ede800ef401d203838bdc0c5e59c0a1686',
                     '7220670f1ac3dda3bfd8e8e182c778311b14be48'):
        source = source_bytes(revision, 'addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py')
        assert b'class ByteQueue:' in source and b'class Handler(' in source
        compile(source, '<frozen-' + revision[:7] + '>', 'exec')
