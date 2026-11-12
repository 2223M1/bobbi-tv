"""Offline schema compatibility gates before any retained-program rollback."""
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from test_ce_deploy_controller import controller, generation, rollback_harness

CORE = 'script.module.bobbi.core'
RELATIVE = 'lib/bobbi_core/media_library_index.py'


def program(root, versions):
    path = root / RELATIVE
    path.parent.mkdir(parents=True)
    path.write_text('raise RuntimeError("never execute retained code")\nclass MediaIndex:\n'
        '    def __init__(self):\n        version = 0\n        if version not in %r:\n'
        '            raise ValueError("CATALOG_SCHEMA_UNSUPPORTED")\n' % (versions,))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema(path, version):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=%d' % version)


def harness(tmp_path, monkeypatch, version=3):
    before = dict(sequence=1, versions=dict(generation(1)['versions'], **{CORE: '1.0'}))
    current = dict(sequence=2, versions=dict(generation(2)['versions'], **{CORE: '2.0'}))
    run, calls, leases = rollback_harness(tmp_path, monkeypatch, current=current)
    monkeypatch.setattr(controller, 'PROFILES', tmp_path/'profiles')
    path = run/'deployment.json'
    receipt = json.loads(path.read_text())
    receipt.update(program_before=before, program_expected=current)
    path.write_text(json.dumps(receipt))
    digest = program(controller.WORK / ('a'*32) / 'backup' / CORE, (0, 1, 2))
    (controller.WORK/'previous.json').write_text(json.dumps(dict(transaction='a'*32, current_sequence=2,
        state=before, entries={CORE: True}, digests={CORE: {RELATIVE: digest}})))
    program(controller.KODI/'addons'/CORE, (0, 1, 2, 3))
    database = controller.PROFILES/'script.module.bobbi.platform/media-index.sqlite3'
    schema(database, version)
    return SimpleNamespace(run=run, receipt=receipt, calls=calls, leases=leases, database=database,
        engine=SimpleNamespace(), current=current)


def test_schema3_refuses_old_program_before_service_or_receipt_mutation(tmp_path, monkeypatch):
    item = harness(tmp_path, monkeypatch)
    before = (item.run/'deployment.json').read_bytes()
    with pytest.raises(controller.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        controller.main(item.run, 'rollback')
    assert item.calls == [] and (item.run/'deployment.json').read_bytes() == before
    assert item.leases[0].closed and controller.catalog_schema() == 3


def test_schema2_and_already_restored_schema3_code_have_proven_read_contract(tmp_path, monkeypatch):
    item = harness(tmp_path, monkeypatch, 2)
    controller.catalog_rollback_preflight(item.engine, item.receipt, 'applied')
    schema(item.database, 3)
    controller.catalog_rollback_preflight(item.engine, item.receipt, 'restored')


@pytest.mark.parametrize('change', ['program', 'generation', 'unknown_contract'])
def test_unproven_retained_code_fails_closed_without_execution(tmp_path, monkeypatch, change):
    item = harness(tmp_path, monkeypatch, 2)
    path = controller.WORK/'previous.json'
    value = json.loads(path.read_text())
    source = controller.WORK/('a'*32)/'backup'/CORE/RELATIVE
    if change == 'program':
        source.write_text(source.read_text() + '# modified\n')
    elif change == 'generation':
        value['state']['versions'][CORE] = 'other'
        path.write_text(json.dumps(value))
    else:
        source.write_text('class MediaIndex: pass\n')
        value['digests'][CORE][RELATIVE] = hashlib.sha256(source.read_bytes()).hexdigest()
        path.write_text(json.dumps(value))
    with pytest.raises(controller.CatalogCompatibilityError):
        controller.catalog_rollback_preflight(item.engine, item.receipt, 'applied')
    assert not item.calls


def test_migration_during_stop_rejects_rollback_and_restarts_only_unchanged_new_generation(tmp_path, monkeypatch):
    item = harness(tmp_path, monkeypatch, 2)
    original = controller.command
    def command(*args):
        result = original(*args)
        if args[:2] == ('systemctl', 'show'):
            if args[2] == 'bobitv-preparation.service':
                return 'inactive' if '--property=ActiveState' in args else 'disabled'
            return 'active' if '--property=ActiveState' in args else 'enabled'
        if args == ('systemctl', 'stop', 'kodi.service'):
            schema(item.database, 3)
        return result
    monkeypatch.setattr(controller, 'command', command)
    with pytest.raises(controller.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        controller.main(item.run, 'rollback')
    assert not any(row[0] in ('rollback_program', 'restore_flags', 'restore_gui') for row in item.calls)
    assert ('systemctl', 'start', 'kodi.service') in item.calls
    assert ('systemctl', 'start', 'bobitv-preparation.service') not in item.calls
    receipt = json.loads((item.run/'deployment.json').read_text())
    assert receipt['rollback_rejected_program_unchanged'] and not receipt.get('rolled_back')
    assert not receipt.get('recovery_required_owners_held_stopped')


def test_wal_schema3_is_observed_without_checkpoint_or_program_mutation(tmp_path, monkeypatch):
    item = harness(tmp_path, monkeypatch, 2)
    writer = sqlite3.connect(item.database)
    try:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('PRAGMA user_version=3')
        writer.commit()
        main_before = item.database.read_bytes()
        wal = Path(str(item.database) + '-wal')
        wal_before = wal.read_bytes()
        with pytest.raises(controller.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
            controller.main(item.run, 'rollback')
        assert not item.calls and item.database.read_bytes() == main_before and wal.read_bytes() == wal_before
    finally:
        writer.close()


@pytest.mark.parametrize('profiles', [
    '<profiles><profile><directory/></profile><profile><directory>profiles/Other</directory></profile></profiles>',
    '<profiles><profile><directory>profiles/Other</directory></profile></profiles>',
    '<profiles/>', '<unknown/>', '<profiles>'])
def test_other_or_unknown_profiles_block_shared_addon_rollback_before_stop(tmp_path, monkeypatch, profiles):
    item = harness(tmp_path, monkeypatch, 2)
    path = controller.KODI/'userdata/profiles.xml'
    path.parent.mkdir(parents=True)
    path.write_text(profiles)
    with pytest.raises(controller.CatalogCompatibilityError, match='OTHER_PROFILES'):
        controller.main(item.run, 'rollback')
    assert not item.calls


def test_uninitialized_sqlite_is_not_assumed_to_be_supported_schema_zero(tmp_path, monkeypatch):
    item = harness(tmp_path, monkeypatch, 0)
    with pytest.raises(controller.CatalogCompatibilityError, match='UNINITIALIZED_OR_UNKNOWN'):
        controller.main(item.run, 'rollback')
    assert not item.calls
