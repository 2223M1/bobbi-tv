"""Complete signed generations reuse the real installer and rollback state machine."""
import json
from types import SimpleNamespace

import pytest

from bobbi_platform import ce_installer
from bobbi_platform.ce_recovery import RecoveryStore, show
from bobbi_platform.updates import UpdateError, _Lock
from test_ce_general_installer import environment, signing, package


def install(env, signing, sequence):
    env.installer.apply(package(env.root / ('generation%d.zip' % sequence), signing, sequence, '%d.0.0' % sequence))


def assert_version(env, sequence):
    for name in ce_installer.MANAGED:
        assert 'version="%d.0.0"' % sequence in (env.addons / name / 'addon.xml').read_text()
    assert (env.user / 'watching').read_text() == 'user-history'
    assert (env.addons / 'plugin.user.other/keep').read_text() == 'other-addon'


def test_saved_generations_restore_then_rollback_without_lowering_watermark(environment, signing):
    env = environment
    for sequence in range(1, 4): install(env, signing, sequence)
    points = env.installer.saved_generations()['points']
    assert [row['sequence'] for row in points] == [3, 2, 1]
    env.installer.restore_saved(points[-1]['name'])
    assert_version(env, 1)
    assert env.installer._read()['high_watermark'] == 3
    assert env.installer._read()['phase'] == 'complete'
    with pytest.raises(UpdateError, match='GENERATION_NOT_NEWER'):
        env.installer.apply(env.root / 'generation2.zip')
    env.installer.rollback()
    assert_version(env, 3)
    assert env.installer._read()['high_watermark'] == 3
    install(env, signing, 4)
    assert_version(env, 4)


def test_retention_keeps_three_valid_packages_but_never_legacy_transactions(environment, signing):
    env = environment
    legacy = env.work / ('a' * 32)
    legacy.mkdir()
    (legacy / 'unknown').write_text('old backup without ownership receipt')
    for sequence in range(1, 6): install(env, signing, sequence)
    assert [r['sequence'] for r in env.installer.saved_generations()['points']] == [5, 4, 3]
    assert (legacy / 'unknown').read_text() == 'old backup without ownership receipt'
    # Standard last-install backup is not one of the pruned package files.
    env.installer.rollback()
    assert_version(env, 4)


def test_optional_recovery_write_failure_does_not_undo_install(environment, signing, monkeypatch):
    env = environment
    monkeypatch.setattr(RecoveryStore, 'remember', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk failure')))
    install(env, signing, 1)
    assert_version(env, 1)
    assert env.installer._read()['phase'] == 'complete'
    assert env.installer._read()['recovery_archive'] == dict(saved=False, reason='unavailable')


def test_optional_recovery_low_space_keeps_existing_points(environment, signing, monkeypatch):
    env = environment
    install(env, signing, 1)
    from bobbi_platform import ce_recovery
    from bobbi_platform.offline_updates import SignedBundle
    with SignedBundle(env.root / 'generation1.zip', signing[1], 'coreelec') as signed:
        monkeypatch.setattr(ce_recovery.shutil, 'disk_usage', lambda root: SimpleNamespace(free=0))
        assert RecoveryStore(env.work, signing[1]).remember(signed) == dict(saved=False, reason='space')
    assert len(env.installer.saved_generations()['points']) == 1


@pytest.mark.parametrize('damage', ['corrupt', 'missing', 'renamed'])
def test_changed_selected_package_cannot_replace_live_program(environment, signing, damage):
    env = environment
    install(env, signing, 1)
    install(env, signing, 2)
    row = env.installer.saved_generations()['points'][-1]
    store = RecoveryStore(env.work, signing[1])
    path = store.path(row['name'])
    if damage == 'corrupt': path.write_bytes(b'broken')
    elif damage == 'missing': path.unlink()
    else:
        wrong = '1-' + 'b' * 64 + '.zip'
        path.rename(path.with_name(wrong))
        row['name'] = wrong
    old = env.installer._read()
    with pytest.raises((OSError, ValueError, UpdateError, __import__('zipfile').BadZipFile)):
        env.installer.restore_saved(row['name'])
    assert env.installer._read() == old
    assert_version(env, 2)


def test_failed_restore_recovers_current_generation_and_account_data(environment, signing):
    env = environment
    install(env, signing, 1)
    install(env, signing, 2)
    point = env.installer.saved_generations()['points'][-1]
    env.host.verify = lambda versions: (_ for _ in ()).throw(RuntimeError('registration failed'))
    with pytest.raises(RuntimeError, match='registration failed'):
        env.installer.restore_saved(point['name'])
    assert_version(env, 2)
    assert env.installer._read()['phase'] == 'restored'
    assert env.installer._read()['high_watermark'] == 2


def test_persistent_activation_failure_still_has_original_recovery_path(environment, signing):
    env = environment
    install(env, signing, 1)
    install(env, signing, 2)
    point = env.installer.saved_generations()['points'][-1]
    env.host.activate = lambda versions: (_ for _ in ()).throw(RuntimeError('activate unavailable'))
    with pytest.raises(RuntimeError): env.installer.restore_saved(point['name'])
    assert env.installer._read()['phase'] == 'activation_pending'
    with pytest.raises(RuntimeError): env.installer.recover()
    env.installer.rollback()
    assert_version(env, 2)


def test_playback_and_concurrent_install_protect_recovery_points(environment, signing):
    env = environment
    install(env, signing, 1)
    point = env.installer.saved_generations()['points'][0]
    with _Lock(env.work / 'installation.lock'):
        with pytest.raises(UpdateError): env.installer.restore_saved(point['name'])
    env.host.check_idle = lambda: (_ for _ in ()).throw(ce_installer.PlaybackActive('PLAYBACK_ACTIVE'))
    before = env.installer._read()
    with pytest.raises(ce_installer.PlaybackActive): env.installer.restore_saved(point['name'])
    assert env.installer._read() == before


@pytest.mark.parametrize('name', ['../point.zip', '/point.zip', '1.zip', '1-' + 'b' * 64 + '.zip/extra'])
def test_recovery_never_accepts_an_arbitrary_path(environment, name):
    with pytest.raises(UpdateError, match='RECOVERY_POINT_INVALID'):
        environment.installer.restore_saved(name)


def test_unavailable_points_are_reported_and_not_silently_deleted(environment, signing):
    env = environment
    install(env, signing, 1)
    root = RecoveryStore(env.work, signing[1]).root
    broken = root / ('2-' + 'b' * 64 + '.zip')
    broken.write_bytes(b'broken')
    unknown = root / 'keep.txt'
    unknown.write_text('not a managed recovery package')
    install(env, signing, 2)
    assert env.installer.saved_generations()['unavailable'] == 1
    assert broken.read_bytes() == b'broken'
    assert unknown.exists()


@pytest.mark.parametrize('cancel', ['selection', 'confirmation', 'none'])
def test_native_recovery_dialog_preserves_user_cancel_and_uses_existing_visuals(cancel):
    calls = []
    point = dict(name='point', sequence=2026102067, size=1024)
    installer = SimpleNamespace(saved_generations=lambda: dict(points=[point], unavailable=1),
        restore_saved=lambda name: calls.append(('restore', name)))
    host = SimpleNamespace(check_idle=lambda: calls.append('idle'))
    dialog = SimpleNamespace(select=lambda *a: -1 if cancel == 'selection' else 0,
        textviewer=lambda *a: calls.append('textviewer'), yesno=lambda *a: cancel != 'confirmation')
    assert show(installer, host, dialog) == (cancel == 'none')
    assert (('restore', 'point') in calls) == (cancel == 'none')
    assert ('textviewer' in calls) == (cancel != 'selection')


def test_cleanup_only_retires_receipted_unreferenced_transactions(environment, signing):
    from bobbi_platform.ce_storage import Maintenance
    env, transactions = environment, []
    for sequence in range(1, 5):
        install(env, signing, sequence)
        transactions.append(env.installer._read()['tx'])
    legacy = env.work / ('e' * 32)
    legacy.mkdir()
    (legacy / 'backup.txt').write_text('unknown historic backup')
    with Maintenance(env.installer) as storage:
        plan = storage.preview()
        assert plan['retired_transactions'] == 2
        assert plan['retired_transaction_bytes'] > 0
        result = storage.clear(plan)
        assert result['removed_transactions'] == 2
    assert all(not (env.work / tx).exists() for tx in transactions[:2])
    assert all((env.work / tx).exists() for tx in transactions[2:])
    assert (legacy / 'backup.txt').is_file()
    assert len(env.installer.saved_generations()['points']) == 3
    env.installer.rollback()
    assert_version(env, 3)


@pytest.mark.parametrize('change', ['file', 'receipt', 'extra', 'pending'])
def test_changed_or_pending_transaction_is_never_retired(environment, signing, change):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    install(env, signing, 1)
    old = env.work / env.installer._read()['tx']
    install(env, signing, 2)
    install(env, signing, 3)
    if change == 'file':
        (old / 'stage/new.txt').write_text('changed')
    elif change == 'receipt':
        (old / 'complete.json').write_text('{}')
    elif change == 'extra':
        (old / 'unexpected').write_text('unknown')
    else:
        state = env.installer._read()
        state['phase'] = 'activation_pending'
        env.installer._write(state)
    if change == 'pending':
        with pytest.raises(UpdateError):
            with Maintenance(env.installer): pass
    else:
        with Maintenance(env.installer) as storage:
            plan = storage.preview()
            assert plan['retired_transactions'] == 0
            storage.clear(plan)
    assert old.exists()


def test_cleanup_rechecks_tree_after_confirmation(environment, signing):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    install(env, signing, 1)
    old = env.work / env.installer._read()['tx']
    install(env, signing, 2)
    install(env, signing, 3)
    with Maintenance(env.installer) as storage:
        plan = storage.preview()
        assert plan['retired_transactions'] == 1
        (old / 'unexpected').write_text('created during preview')
        with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
            storage.clear(plan)
    assert old.exists()


def test_interrupted_cache_copy_does_not_accumulate_or_delete_unknown_files(environment, signing):
    env = environment
    install(env, signing, 1)
    root = RecoveryStore(env.work, signing[1]).root
    (root / '.pending-package').write_bytes(b'power loss during copy')
    (root / 'unknown.zip').write_bytes(b'not ours')
    install(env, signing, 2)
    assert not (root / '.pending-package').exists()
    assert (root / 'unknown.zip').read_bytes() == b'not ours'
    assert [r['sequence'] for r in env.installer.saved_generations()['points']] == [2, 1]
