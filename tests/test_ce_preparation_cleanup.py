"""Preparation ownership is distinct from committed installation/rollback."""
import os

import pytest

from bobbi_platform import ce_installer, ce_recovery
from bobbi_platform.ce_storage import Maintenance
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import environment, signing, package


def preparation(env, tx='a' * 32):
    root = env.work / tx
    root.mkdir()
    ce_recovery.record_preparation(env.work, tx, 2)
    (root / 'stage').mkdir()
    (root / 'stage/payload').write_bytes(b'rebuildable')
    (root / 'backup').mkdir()
    return root


def test_two_dependency_failures_never_accumulate_staging(environment, signing):
    env = environment
    path = package(env.root / 'one.zip', signing)
    def fail(_):
        raise UpdateError('DEPENDENCY_UNAVAILABLE:fixture')
    env.host.dependencies = fail
    for _ in range(2):
        with pytest.raises(UpdateError, match='DEPENDENCY_UNAVAILABLE'):
            env.installer.apply(path)
        assert not list(env.work.glob('*/stage'))
        assert env.installer._read() is None
    assert (env.user / 'watching').read_text() == 'user-history'


@pytest.mark.parametrize('fault', ['extract', 'idle', 'metadata', 'before-journal', 'after-journal'])
def test_preparation_faults_preserve_previous_live_and_handoff(environment, signing, monkeypatch, fault):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    previous = env.installer._read()
    path = package(env.root / 'two.zip', signing, 2, '2.0.0')
    def fail(*_):
        raise RuntimeError('injected interruption')
    if fault == 'extract':
        monkeypatch.setattr(ce_installer.UpdateEngine, '_extract', fail)
    elif fault == 'metadata':
        monkeypatch.setattr(ce_installer, 'program_tree', fail)
    elif fault == 'idle':
        calls = []
        def idle():
            calls.append(1)
            if len(calls) == 2:
                fail()
        env.host.check_idle = idle
    else:
        write = env.installer._write
        def interrupt(state):
            if fault == 'after-journal':
                write(state)
            fail()
        monkeypatch.setattr(env.installer, '_write', interrupt)
    with pytest.raises(RuntimeError, match='interruption'):
        env.installer.apply(path)
    state = env.installer._read()
    if fault == 'after-journal':
        assert state['phase'] == 'staged' and state['tx'] != previous['tx']
        assert (env.work / state['tx'] / 'stage').exists()
        assert ce_recovery.preparation_transaction(env.work, state['tx'], state) is None
    else:
        assert state == previous
        assert len(list(env.work.glob('*/stage'))) == 1  # Previous complete tree only.
    assert all('1.0.0' in (env.addons / name / 'addon.xml').read_text() for name in ce_installer.MANAGED)


@pytest.mark.parametrize('fault', ['unknown', 'backup', 'receipt', 'current', 'previous', 'pending'])
def test_unproven_or_referenced_preparations_are_protected(environment, signing, fault):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    root = preparation(env)
    state = env.installer._read()
    if fault == 'unknown': (root / 'foreign').write_text('keep')
    elif fault == 'backup': (root / 'backup/old').write_text('keep')
    elif fault == 'receipt': (root / ce_recovery.PREPARATION).write_text('{}')
    elif fault == 'current': state['tx'] = root.name
    elif fault == 'previous': state['previous_tx'] = root.name
    else: state['phase'] = 'switching'
    assert ce_recovery.preparation_transaction(env.work, root.name, state) is None
    assert (root / 'stage/payload').exists()


@pytest.mark.parametrize('fault', ['content', 'member', 'replace', 'hardlink'])
def test_maintenance_rechecks_entire_preparation_identity(environment, fault):
    env = environment
    root = preparation(env)
    with Maintenance(env.installer) as maintenance:
        plan = maintenance.preview()
        assert plan['preparation_transactions'] == 1 and plan['preparation_bytes'] > 0
        if fault == 'content': (root / 'stage/payload').write_bytes(b'changed')
        elif fault == 'member': (root / 'unknown').write_text('keep')
        elif fault == 'replace':
            root.rename(env.work / ('b' * 32))
            root.mkdir()
        else:
            os.link(root / 'stage/payload', env.root / 'outside-link')
        with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
            maintenance.clear(plan)
    assert root.exists()


def test_startup_reclaims_receipted_stage_but_keeps_mkdir_crash_and_backup(environment):
    env = environment
    root = preparation(env)
    unknown = env.work / ('c' * 32)
    unknown.mkdir()
    protected = preparation(env, 'd' * 32)
    (protected / 'backup/old').write_text('keep')
    with Maintenance(env.installer) as maintenance:
        plan = maintenance.preview()
        assert plan['preparation_transactions'] == 1
        assert plan['protected_unknown_transactions'] == 2
    env.installer.recover()
    env.installer.recover()
    assert not root.exists() and unknown.exists()
    assert (protected / 'backup/old').read_text() == 'keep'


def test_clear_preparation_is_repeatable_after_partial_payload_deletion(environment):
    env = environment
    root = preparation(env)
    (root / 'stage/payload').unlink()  # Process lost during a previous cleanup.
    with Maintenance(env.installer) as maintenance:
        result = maintenance.clear(maintenance.preview())
    assert result['removed_preparations'] == 1 and not root.exists()


def test_preparation_scan_has_shared_file_and_byte_budgets(environment):
    env = environment
    root = preparation(env)
    assert ce_recovery.preparation_transaction(env.work, root.name, None, [1, 100000]) is None
    assert ce_recovery.preparation_transaction(env.work, root.name, None, [100, 1]) is None
    assert root.exists()


def test_receipt_creation_cannot_adopt_existing_content_or_escape_root(environment):
    root = environment.work / ('a' * 32)
    root.mkdir()
    (root / 'unknown').write_text('keep')
    with pytest.raises(UpdateError, match='PREPARATION_RECEIPT_INVALID'):
        ce_recovery.record_preparation(environment.work, root.name, 1)
    with pytest.raises(UpdateError, match='PREPARATION_RECEIPT_INVALID'):
        ce_recovery.record_preparation(environment.work, '../escape', 1)
    assert (root / 'unknown').read_text() == 'keep'


def test_symlink_payload_never_becomes_preparation_cleanup_authority(environment):
    env = environment
    root = preparation(env)
    outside = env.root / 'outside'
    outside.write_bytes(b'keep')
    try:
        (root / 'stage/link').symlink_to(outside)
    except OSError:
        pytest.skip('Host does not permit symlink creation; run this safety case on Linux')
    assert ce_recovery.preparation_transaction(env.work, root.name, None) is None
    env.installer.recover()
    assert outside.read_bytes() == b'keep' and root.exists()


def test_receipt_persistence_crash_before_payload_leaves_only_protected_small_directory(environment, signing, monkeypatch):
    env = environment
    def fail(*args): raise OSError('receipt fsync failed')
    monkeypatch.setattr(ce_recovery, 'record_preparation', fail)
    with pytest.raises(OSError, match='receipt fsync failed'):
        env.installer.apply(package(env.root / 'one.zip', signing))
    roots = [path for path in env.work.iterdir() if path.is_dir()]
    assert len(roots) == 1 and not list(roots[0].iterdir())
    env.installer.recover()
    assert roots[0].exists() and env.installer._read() is None
