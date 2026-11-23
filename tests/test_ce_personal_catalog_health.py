"""The personal-catalog probe never initializes/migrates storage or lists sources."""
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from bobbi_core.media_library_index import MediaIndex
from bobbi_platform import libraries

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog_health_probe', ROOT / 'tools/ce_personal_catalog_health.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def catalog(root):
    path = root / 'addon_data/script.module.bobbi.platform/media-index.sqlite3'
    index = MediaIndex(path)
    index.close()
    return path


def registry(root, revisions=('a' * 64, None)):
    path = root / 'addon_data/script.module.bobbi.platform/libraries.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        for name, key, value in (('sources', 'id', 'record'), ('metadata', 'key', 'value')):
            db.execute('CREATE TABLE %s (%s TEXT PRIMARY KEY,%s TEXT NOT NULL)' % (name, key, value))
        for number, revision in enumerate(revisions):
            source = 'private-account-%d' % number
            db.execute('INSERT INTO sources VALUES (?,?)', (source,
                json.dumps(dict(location='smb://private-user:private-password/server', token='private-token'))))
            if revision is not None:
                db.execute('INSERT INTO metadata VALUES (?,?)', ('source_revision:' + source, revision))
        db.execute('PRAGMA user_version=1')
    return path


def test_absent_inventory_is_not_created_and_unknown_inventory_is_not_skipped(tmp_path):
    missing = tmp_path / 'absent'
    result = probe.inspect_catalog(missing)
    assert result['state'] == 'observed'
    assert result['profiles'][0]['catalog']['state'] == 'absent'
    assert not missing.exists()
    (tmp_path / 'profiles.xml').write_text('<profiles/>')
    assert probe.inspect_catalog(tmp_path)['reason'] == 'PROFILE_OR_PROGRAM_UNPROVEN'


def test_schema4_and_registry_are_mode_ro_without_constructors_or_secrets(tmp_path, monkeypatch):
    path, source = catalog(tmp_path), registry(tmp_path)
    with sqlite3.connect(path) as db:
        for i, kind in enumerate(probe.KINDS):
            db.execute('INSERT INTO typed_objects VALUES (?,?,?,?)', (str(i), 'private-source', 'private-space',
                json.dumps(dict(reference_kind=kind, location='https://private-url/?token=private-secret'))))
    before = path.read_bytes(), source.read_bytes()
    def forbidden(*args, **kwargs):
        pytest.fail('No constructors allowed in a read-only probe')
    monkeypatch.setattr(MediaIndex, '__init__', forbidden)
    monkeypatch.setattr(libraries.Registry, '__init__', forbidden)
    connect = sqlite3.connect
    calls = []
    def readonly(connection_uri, *args, **kwargs):
        calls.append(connection_uri)
        assert connection_uri.endswith('?mode=ro') and kwargs['uri'] is True
        return connect(connection_uri, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', readonly)
    result = probe.inspect_catalog(tmp_path, ROOT / 'addons/script.module.bobbi.core')
    assert calls and result['state'] == 'observed'
    row = result['profiles'][0]
    assert row['catalog']['schema'] == 4 and row['catalog']['program_compatible'] is True
    assert row['catalog']['typed_lanes_sample'] == dict(mounted_path=1, local_path=1, network_path=1, unknown_or_invalid=0)
    assert row['registry']['source_revisions_sample'] == dict(valid=1, missing_legacy=1, invalid=0)
    assert 'pan_directories' in row['registry']['missing_tables']
    assert before == (path.read_bytes(), source.read_bytes())
    assert 'private-' not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


def test_all_profiles_and_committed_wal_observed_without_checkpoint(tmp_path):
    catalog(tmp_path)
    other = tmp_path / 'profiles/Other'
    path = catalog(other)
    (tmp_path / 'profiles.xml').write_text('<profiles><profile><directory/></profile>'
        '<profile><directory>profiles/Other</directory></profile></profiles>')
    writer = sqlite3.connect(path)
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('PRAGMA user_version=99')
        writer.commit()
        wal = Path(str(path) + '-wal')
        before = path.read_bytes(), wal.read_bytes()
        result = probe.inspect_catalog(tmp_path, ROOT / 'addons/script.module.bobbi.core')
        assert len(result['profiles']) == 2 and result['state'] == 'attention_required'
        observed = next(row['catalog'] for row in result['profiles'] if not row['master'])
        assert observed['schema'] == 99 and observed['wal_present'] and not observed['program_compatible']
        assert before == (path.read_bytes(), wal.read_bytes())
    finally:
        writer.close()


@pytest.mark.parametrize('damage', ['corrupt', 'unknown', 'missing_table', 'invalid_ref', 'invalid_revision'])
def test_invalid_storage_reports_fixed_reason_without_repair(tmp_path, damage):
    path = catalog(tmp_path)
    if damage == 'corrupt':
        path.write_bytes(b'private-secret-not-sqlite')
    elif damage == 'invalid_revision':
        registry(tmp_path, revisions=('private-invalid-revision',))
    else:
        with sqlite3.connect(path) as db:
            if damage == 'unknown':
                db.execute('PRAGMA user_version=77')
            elif damage == 'missing_table':
                db.execute('DROP TABLE file_segments')
            else:
                db.execute('INSERT INTO typed_objects VALUES (?,?,?,?)', ('x', 'y', 'z', 'private-invalid-json'))
    before = path.read_bytes()
    result = probe.inspect_catalog(tmp_path)
    assert result['state'] == 'attention_required'
    assert 'private-' not in json.dumps(result)
    assert path.read_bytes() == before


def test_counts_and_sampling_are_bounded_and_never_claim_complete_inventory(tmp_path, monkeypatch):
    path = catalog(tmp_path)
    with sqlite3.connect(path) as db:
        db.executemany('INSERT INTO objects VALUES (?,?,?,?)', [(str(i), '115', 'private', '{}') for i in range(6)])
    monkeypatch.setattr(probe, 'MAX_ROWS', 2)
    result = probe.inspect_catalog(tmp_path)
    assert result['profiles'][0]['catalog']['counts']['objects'] == dict(count=2, exact=False)


def test_remote_payload_reuses_probe_without_importing_storage_owners():
    source = probe.remote_code()
    compile(source, '<catalog-probe>', 'exec')
    assert 'mode=ro' in source and 'sys.dont_write_bytecode=True' in source
    assert 'MediaIndex(' not in source and 'Registry(' not in source
    assert 'Player.' not in source and 'Input.' not in source and 'wal_checkpoint' not in source


def test_deadline_stops_new_database_reads(tmp_path, monkeypatch):
    times = iter((0, 6, 6))
    monkeypatch.setattr(probe.time, 'monotonic', lambda: next(times))
    result = probe.inspect_catalog(tmp_path)
    assert result['state'] == 'attention_required'
    assert all(result['profiles'][0][key]['reason'] == 'PROBE_BUDGET' for key in ('catalog', 'registry'))
