"""Maintenance-only archive guards; not additional device certification."""
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import package_ce2024_handoff as handoff


def test_source_paths_keep_runtime_and_public_ca():
    handoff.validate_source_paths(['addons/skin.bobbi.cinema/1080i/Home.xml', handoff.PUBLIC_CA])


def test_inventory_curated_catalog_is_not_an_account_database():
    handoff.validate_source_paths([handoff.CURATED_CATALOG])


@pytest.mark.parametrize('path', ['../escape', 'C:/private', 'a\\b', '.private/key',
    'userdata/settings.xml', 'keys/private.pem', 'local/account.sqlite',
    'addons/script.module.bobbi.core/resources/tmdb-project.json'])
def test_source_paths_reject_local_state(path):
    with pytest.raises(ValueError):
        handoff.validate_source_paths([path])


def test_case_duplicate_rejected():
    with pytest.raises(ValueError):
        handoff.validate_source_paths(['addons/a', 'addons/A'])


def test_junit_does_not_count_skips_as_passes(tmp_path):
    path = tmp_path/'tests.xml'
    path.write_text('<testsuites><testsuite tests="8" errors="1" failures="2" skipped="1"/></testsuites>')
    assert handoff.junit_counts(path) == dict(tests=8, errors=1, failures=2, skipped=1, passed=4)


def test_archive_requires_complete_git_tree(tmp_path):
    path = tmp_path/'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('addons/a.py', 'pass')
    with pytest.raises(ValueError, match='TREE_MISMATCH'):
        handoff.inspect_source_archive(path, ['addons/a.py', 'addons/missing.py'])


def test_evidence_index_does_not_promote_failures(tmp_path):
    path = tmp_path/'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('review-evidence/failed.json', '{"passed":false}')
    row, = handoff.inspect_source_archive(path, ['review-evidence/failed.json'])
    assert 'does not turn it into a pass' in row['acceptance']
    assert row['bytes'] == len('{"passed":false}')
