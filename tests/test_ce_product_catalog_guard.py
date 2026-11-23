"""Real signed product rollback/restore cannot strand any retained profile."""
from io import BytesIO
from pathlib import Path
import sqlite3
import zipfile

import pytest

from bobbi_platform import catalog_compatibility as guard
from bobbi_platform.ce_installer import blocked, program_tree
import test_ce_general_installer as fixtures
from test_ce_general_installer import environment, signing


def source(versions):
    return ('raise RuntimeError("never execute candidate code")\nclass MediaIndex:\n'
            '    def __init__(self):\n        version = 0\n        if version not in %r:\n'
            '            raise ValueError("CATALOG_SCHEMA_UNSUPPORTED")\n' % (versions,)).encode()


def package(env, signing, monkeypatch, sequence, versions):
    original = fixtures.archive
    def archive(name, version):
        raw = original(name, version)
        if name != guard.CORE:
            return raw
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as old, zipfile.ZipFile(output, 'w') as new:
            for item in old.infolist():
                new.writestr(item, old.read(item))
            new.writestr(guard.CORE + '/' + guard.PROGRAM, source(versions))
        return output.getvalue()
    with monkeypatch.context() as patch:
        patch.setattr(fixtures, 'archive', archive)
        return fixtures.package(env.root / ('generation%d.zip' % sequence), signing, sequence, '%d.0.0' % sequence)


def schema(root, version):
    path = root / 'addon_data' / guard.CATALOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as database:
        database.execute('PRAGMA user_version=%d' % version)
    return path


def installed(env, signing, monkeypatch):
    for sequence, versions in ((1, (0, 1, 2)), (2, (0, 1, 2, 3))):
        env.installer.apply(package(env, signing, monkeypatch, sequence, versions))
    env.calls.clear()


@pytest.mark.parametrize('operation', ['rollback', 'saved', 'newer_incompatible'])
def test_product_rejects_incompatible_data_before_any_host_or_program_change(environment, signing, monkeypatch, operation):
    env = environment
    installed(env, signing, monkeypatch)
    schema(env.root / 'userdata', 3)
    before = env.installer.state.read_bytes(), program_tree(env.addons)
    if operation == 'newer_incompatible':
        candidate = package(env, signing, monkeypatch, 3, (0, 1, 2))
    with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        if operation == 'rollback':
            env.installer.rollback()
        elif operation == 'saved':
            env.installer.restore_saved(env.installer.saved_generations()['points'][-1]['name'])
        else:
            env.installer.apply(candidate)
    assert env.calls == []
    assert before == (env.installer.state.read_bytes(), program_tree(env.addons))
    assert not blocked(env.work)


def test_all_registered_profiles_are_checked_and_supported_profiles_allow_rollback(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    master = env.root / 'userdata'
    other = master / 'profiles/Other'
    (master / 'profiles.xml').write_text('<profiles><profile><directory/></profile>'
        '<profile><directory>profiles/Other</directory></profile></profiles>')
    schema(master, 2)
    schema(other, 3)
    with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        env.installer.rollback()
    assert not env.calls
    schema(other, 2)
    env.installer.rollback()
    assert not blocked(env.work)
    assert 'version="1.0.0"' in (env.addons / guard.CORE / 'addon.xml').read_text()


def test_secondary_profile_unreadable_database_and_unknown_inventory_fail_closed(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    master = env.root / 'userdata'
    inventory = master / 'profiles.xml'
    inventory.write_text('<profiles><profile><directory>profiles/Other</directory></profile></profiles>')
    path = schema(master / 'profiles/Other', 2)
    path.write_bytes(b'not a database')
    with pytest.raises(guard.CatalogCompatibilityError, match='UNREADABLE'):
        env.installer.rollback()
    inventory.write_text('<profiles/>')
    with pytest.raises(guard.CatalogCompatibilityError, match='OTHER_PROFILES'):
        env.installer.rollback()
    assert not env.calls


def test_wal_is_observed_without_checkpoint_or_old_code_execution(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    path = schema(env.root / 'userdata', 2)
    writer = sqlite3.connect(path)
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('PRAGMA user_version=3')
        writer.commit()
        wal = Path(str(path) + '-wal')
        before = path.read_bytes(), wal.read_bytes()
        with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
            env.installer.rollback()
        assert before == (path.read_bytes(), wal.read_bytes())
        assert not env.calls
    finally:
        writer.close()


@pytest.mark.parametrize('directory', ['../outside', 'smb://server/profile', 'special://unknown/profile'])
def test_unresolved_profile_paths_cannot_be_skipped(tmp_path, directory):
    (tmp_path / 'profiles.xml').write_text('<profiles><profile><directory>' + directory + '</directory></profile></profiles>')
    with pytest.raises(guard.CatalogCompatibilityError, match='OTHER_PROFILES'):
        guard.schemas(tmp_path)


def test_restored_pending_boot_gate_rechecks_data_before_reopening(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    env.installer.rollback()
    state = env.installer._read()
    state['host_pending'] = 'restore'
    env.installer._write(state)
    schema(env.root / 'userdata', 3)
    env.calls.clear()
    with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        env.installer.recover()
    assert env.calls == []
    assert env.installer._read()['host_pending'] == 'restore'


def test_migration_during_rollback_drain_keeps_programs_and_recoverable_closed_gate(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    master = env.root / 'userdata'
    schema(master, 2)
    before = program_tree(env.addons)
    def quiesce():
        env.calls.append('quiesce')
        schema(master, 3)
    env.host.quiesce = quiesce
    with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        env.installer.rollback()
    assert before == program_tree(env.addons)
    assert env.calls == ['quiesce'] and blocked(env.work)
    # Restarting the installer cannot boot the incompatible retained program.
    with pytest.raises(guard.CatalogCompatibilityError):
        env.installer.recover()
    assert before == program_tree(env.addons)
    # An explicitly repaired fixture models an external/offline data restore;
    # the product guard itself never downgrades or edits personal data.
    env.host.quiesce = lambda: env.calls.append('quiesce')
    schema(master, 2)
    env.installer.recover()
    assert not blocked(env.work)
    assert 'version="1.0.0"' in (env.addons / guard.CORE / 'addon.xml').read_text()


def test_candidate_rechecked_after_drain_never_replaces_current_readable_program(environment, signing, monkeypatch):
    env = environment
    installed(env, signing, monkeypatch)
    master = env.root / 'userdata'
    schema(master, 2)
    candidate = package(env, signing, monkeypatch, 3, (0, 1, 2))
    before = program_tree(env.addons)
    def quiesce():
        env.calls.append('quiesce')
        schema(master, 3)
    env.host.quiesce = quiesce
    with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
        env.installer.apply(candidate)
    assert program_tree(env.addons) == before
    assert not blocked(env.work)
    assert env.installer._read()['high_watermark'] == 2
    assert 'verify' not in env.calls


@pytest.mark.parametrize('placement', ['main', 'wal', 'other_profile'])
@pytest.mark.parametrize('operation', ['rollback', 'saved', 'newer_incompatible'])
def test_schema4_product_guard_rejects_schema3_in_every_profile(environment, signing, monkeypatch, placement, operation):
    env = environment
    for sequence, versions in ((1, (0, 1, 2, 3)), (2, (0, 1, 2, 3, 4))):
        env.installer.apply(package(env, signing, monkeypatch, sequence, versions))
    master = env.root / 'userdata'
    target = master
    if placement == 'other_profile':
        (master / 'profiles.xml').write_text('<profiles><profile><directory/></profile>'
            '<profile><directory>profiles/Other</directory></profile></profiles>')
        schema(master, 3)
        target = master / 'profiles/Other'
    path = schema(target, 3)
    writer = sqlite3.connect(path)
    try:
        if placement == 'wal':
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('PRAGMA user_version=4')
        writer.commit()
        paths = [path, env.installer.state]
        if placement == 'wal':
            paths.append(Path(str(path) + '-wal'))
        before = {item: item.read_bytes() for item in paths}, program_tree(env.addons)
        candidate = package(env, signing, monkeypatch, 3, (0, 1, 2, 3)) if operation == 'newer_incompatible' else None
        env.calls.clear()
        with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
            if operation == 'rollback':
                env.installer.rollback()
            elif operation == 'saved':
                env.installer.restore_saved(env.installer.saved_generations()['points'][-1]['name'])
            else:
                env.installer.apply(candidate)
        assert not env.calls and not blocked(env.work)
        assert before == ({item: item.read_bytes() for item in paths}, program_tree(env.addons))
    finally:
        writer.close()
