"""Real installer and user maintenance entry; no deletion of recovery state."""
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import random
import re
from types import SimpleNamespace
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from bobbi_platform import ce_installer
from bobbi_platform.updates import UpdateError, _Lock
from bobbi_platform.instance_lock import InstanceLock
from test_ce_general_installer import environment, signing, package
from test_online_updates import entry
from test_onboarding import setup_ui
from test_updates import archive


def large_package(path, signing):
    package(path, signing)
    with zipfile.ZipFile(path) as source:
        manifest = json.loads(source.read('release.json'))
        content = {row['file']: source.read(row['file']) for row in manifest['components']}
    row = next(row for row in manifest['components'] if row['id'] == 'plugin.video.bobbi')
    # Strong compression but within the existing 200x expansion bound.
    block = random.Random(2065).randbytes(8192)
    content[row['file']] = archive(row['id'], extra=[(row['id']+'/asset.bin', block*2048)])
    row.update(size=len(content[row['file']]), sha256=hashlib.sha256(content[row['file']]).hexdigest())
    raw = json.dumps(manifest).encode()
    signature = base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as target:
        target.writestr('release.json', raw)
        target.writestr('release.sig', signature)
        for name, blob in content.items(): target.writestr(name, blob)
    return path


def test_compressed_times_four_cannot_admit_a_larger_expanded_stage(environment, signing, monkeypatch):
    env = environment
    path = large_package(env.root/'compressed.zip', signing)
    assert path.stat().st_size*4 < 8*1024**2
    # More than the reserve alone: the expanded layout must drive refusal.
    monkeypatch.setattr(ce_installer.shutil, 'disk_usage', lambda _: SimpleNamespace(free=28*1024**2, total=100*1024**2))
    with pytest.raises(UpdateError, match='INSTALLATION_SPACE_REQUIRED'):
        env.installer.apply(path)
    assert env.installer._read() is None and env.calls == []
    assert not any(re.fullmatch('[a-f0-9]{32}', path.name) for path in env.work.iterdir())


def test_low_space_fails_before_creating_an_unreferenced_transaction(environment, signing, monkeypatch):
    env = environment
    path = package(env.root/'one.zip', signing)
    monkeypatch.setattr(ce_installer.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0, total=100*1024**2))
    with pytest.raises(UpdateError, match='INSTALLATION_SPACE_REQUIRED'):
        env.installer.apply(path)
    assert not any(re.fullmatch('[a-f0-9]{32}', path.name) for path in env.work.iterdir())
    assert env.installer._read() is None and env.calls == []


def cache_files(env):
    folder = env.work/'downloads'
    root = folder/'components-v1'
    root.mkdir(parents=True)
    entries = [root/('a'*64+'.zip'), root/'transfer.part', folder/'online.partial', folder/'online-resume.json']
    for path in entries: path.write_bytes(b'rebuildable')
    # A completed archive may be between download and apply in an older entry.
    (folder/'online-handed-off.zip').write_bytes(b'in use or unknown')
    (folder/'private-user-file').write_bytes(b'keep')
    return entries


def test_cleanup_only_removes_previewed_download_cache_not_programs_or_handoffs(environment, signing):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    state = env.installer._read()
    unrelated = env.work/('f'*32)
    unrelated.mkdir(); (unrelated/'failed-evidence').write_bytes(b'keep')
    entries = cache_files(env)
    with Maintenance(env.installer) as storage:
        plan = storage.preview()
        assert plan['reclaimable_bytes'] == sum(path.stat().st_size for path in entries)
        assert plan['legacy_transactions'] == 2
        result = storage.clear(plan)
    assert result['removed_files'] == len(entries)
    assert all(not path.exists() for path in entries)
    assert env.installer._read() == state
    assert (unrelated/'failed-evidence').read_bytes() == b'keep'
    assert (env.work/'downloads/online-handed-off.zip').read_bytes() == b'in use or unknown'
    env.installer.rollback()
    assert all('1.0.0' in (env.addons/name/'addon.xml').read_text() for name in ce_installer.MANAGED)
    assert (env.user/'watching').read_text() == 'user-history'


@pytest.mark.parametrize('lock', ['installation.lock', '.bobbi-component-download.lock', '.bobbi-online-download.lock'])
def test_cleanup_rejects_active_install_or_transfer(environment, lock):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    entries = cache_files(env)
    owner = InstanceLock(env.work/lock)
    owner.acquire()
    try:
        with pytest.raises(UpdateError):
            with Maintenance(env.installer) as storage: storage.clear(storage.preview())
    finally: owner.close()
    assert all(path.exists() for path in entries)


def test_cleanup_plan_changed_after_preview_is_not_executed(environment):
    from bobbi_platform.ce_storage import Maintenance
    entries = cache_files(environment)
    with Maintenance(environment.installer) as storage:
        plan = storage.preview()
        entries[0].write_bytes(b'changed after confirmation')
        with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
            storage.clear(plan)
    assert all(path.exists() for path in entries)


def test_cleanup_interruption_only_loses_rebuildable_cache_and_can_retry(environment):
    from bobbi_platform.ce_storage import Maintenance
    entries = cache_files(environment)
    calls = []
    def active():
        calls.append(1)
        if sum(path.exists() for path in entries) < len(entries):
            raise InterruptedError('user cancelled')
    with Maintenance(environment.installer) as storage:
        plan = storage.preview()
        with pytest.raises(InterruptedError): storage.clear(plan, active=active)
    with Maintenance(environment.installer) as storage:
        storage.clear(storage.preview())
    assert not any(path.exists() for path in entries)
    assert (environment.user/'watching').read_text() == 'user-history'


@pytest.mark.parametrize('fault', ['hardlink', 'directory', 'journal'])
def test_untrusted_cache_or_journal_never_becomes_delete_authority(environment, fault):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    entries = cache_files(env)
    outside = env.root/'outside'
    outside.write_bytes(b'keep outside')
    if fault == 'journal': env.installer.state.write_bytes(b'not json')
    else:
        entries[0].unlink()
        if fault == 'directory': entries[0].mkdir()
        else: os.link(outside, entries[0])
    with pytest.raises((UpdateError, OSError)):
        with Maintenance(env.installer) as storage: storage.clear(storage.preview())
    assert outside.read_bytes() == b'keep outside'
    assert all(path.exists() for path in entries)


def test_actual_menu_decline_is_readonly_and_confirmation_uses_existing_dialog(entry):
    from bobbi_platform import ce_install_ui as ui
    entries = cache_files(entry.env)
    entry.env.host.details = lambda _: {'version': '0.1.0'}
    entry.choice = 5
    entry.dialog.yesno = lambda *args: False
    ui.main()
    assert all(path.exists() for path in entries)
    entry.dialog.yesno = lambda *args: True
    ui.main()
    assert not any(path.exists() for path in entries)
    assert entry.env.calls == [] and entry.commands == []


def test_settings_exposes_storage_without_changing_existing_actions(setup_ui):
    setup_ui.choice = 4
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert setup_ui.builtins == ['RunScript(script.bobbi.start,storage)']


def test_space_plan_counts_allocation_and_only_missing_dependency_copies(environment, signing):
    from bobbi_platform.ce_storage import RESERVE, plan_text
    env = environment
    path = package(env.root/'one.zip', signing)
    plan = env.installer.plan_space(path)
    assert plan['expanded_bytes'] > 0
    assert plan['stage_bytes'] >= plan['expanded_bytes']
    assert plan['dependency_copy_bytes'] == 0
    assert plan['required_bytes'] == plan['stage_bytes']+RESERVE
    assert plan['archive_already_present'] and plan['backup_extra_bytes'] == 0
    assert plan['external_dependency_space_unknown']
    assert not env.calls and env.installer._read() is None
    name = sorted(ce_installer.UPSTREAM_COMPONENTS)[0]
    (env.addons/name/'origin').unlink()
    (env.addons/name).rmdir()
    missing = env.installer.plan_space(path)
    assert missing['dependency_copy_bytes'] > 0
    assert missing['required_bytes'] == plan['required_bytes']+missing['dependency_copy_bytes']
    assert '已读下限' in plan_text(dict(plan, existing_sizes_complete=False))


def test_space_consumed_during_staging_refuses_before_journal_and_quiesce(environment, signing, monkeypatch):
    from bobbi_platform.ce_storage import RESERVE
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    original = env.installer._read()
    env.calls.clear()
    remaining = [100*1024**2, RESERVE-1]
    monkeypatch.setattr(ce_installer.shutil, 'disk_usage', lambda _: SimpleNamespace(free=remaining.pop(0)))
    with pytest.raises(UpdateError, match='INSTALLATION_SPACE_REQUIRED') as caught:
        env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    assert caught.value.space['phase'] == 'after-dependencies'
    assert env.installer._read() == original
    assert env.calls == ['dependencies']
    assert all('1.0.0' in (env.addons/name/'addon.xml').read_text() for name in ce_installer.MANAGED)


def test_storage_session_and_original_plan_are_required(environment):
    from bobbi_platform.ce_storage import Maintenance
    entries = cache_files(environment)
    storage = Maintenance(environment.installer)
    with pytest.raises(UpdateError, match='STORAGE_SESSION_REQUIRED'):
        storage.preview()
    with storage:
        plan = storage.preview()
        with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
            storage.clear(dict(plan))
        plan['files'] += 1
        with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
            storage.clear(plan)
    with pytest.raises(UpdateError, match='STORAGE_PLAN_CHANGED'):
        storage.clear(plan)
    assert all(path.exists() for path in entries)


@pytest.mark.parametrize('operation', ['playing', 'abort'])
def test_playback_or_host_abort_after_confirmation_prevents_clear(entry, operation):
    from bobbi_platform import ce_install_ui as ui
    entries = cache_files(entry.env)
    cancelled = [False]
    entry.env.host.monitor = SimpleNamespace(abortRequested=lambda: operation == 'abort' and cancelled[0])
    def idle():
        if operation == 'playing' and cancelled[0]: raise ce_installer.PlaybackActive('PLAYBACK_ACTIVE')
    entry.env.host.check_idle = idle
    def confirm(*args):
        cancelled[0] = True
        return True
    entry.dialog.yesno = confirm
    ui.main(storage=True)
    assert all(path.exists() for path in entries)
    assert entry.env.calls == []


def test_busy_failure_has_actionable_user_message():
    from bobbi_platform.ce_install_ui import failure_message
    from bobbi_platform.updates import Busy
    assert '等待' in failure_message(Busy('Another update is active'))


def test_cleanup_cannot_hold_unbounded_unknown_directory_scan(environment, monkeypatch):
    from bobbi_platform import ce_storage
    entries = cache_files(environment)
    monkeypatch.setattr(ce_storage, 'SCAN_FILES', 1)
    with pytest.raises(UpdateError, match='ONLINE_COMPONENT_CACHE_LIMIT'):
        with ce_storage.Maintenance(environment.installer) as storage: storage.preview()
    assert all(path.exists() for path in entries)


def test_maintenance_holds_real_downloader_locks_through_confirmation(environment):
    from bobbi_platform.ce_storage import Maintenance
    from bobbi_platform.online_components import ComponentCache
    from bobbi_platform.online_partial import PartialDownload
    env = environment
    cache_files(env)
    with Maintenance(env.installer) as storage:
        storage.preview()
        with pytest.raises(UpdateError, match='ONLINE_DOWNLOAD_BUSY'):
            with ComponentCache(env.work/'downloads', lambda: None): pass
        with pytest.raises(UpdateError, match='ONLINE_DOWNLOAD_BUSY'):
            with PartialDownload(env.work/'downloads', dict(tag='ce2065', sequence=2026102065,
                    size=100, sha256='a'*64), [], lambda: None): pass


def test_pending_recovery_preserves_all_cache(environment, signing):
    from bobbi_platform.ce_storage import Maintenance
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    state = env.installer._read()
    state['phase'] = 'activation_pending'
    env.installer._write(state)
    entries = cache_files(env)
    with pytest.raises(UpdateError, match='INSTALLATION_RECOVERY_REQUIRED'):
        with Maintenance(env.installer) as storage: storage.preview()
    assert all(path.exists() for path in entries)


def test_existing_backup_and_live_code_do_not_double_charge_extra_space(environment, signing):
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    plan = env.installer.plan_space(package(env.root/'three.zip', signing, 3, '3.0.0'))
    assert plan['current_program_bytes'] > 0 and plan['retained_backup_bytes'] > 0
    assert plan['backup_extra_bytes'] == 0
    assert plan['required_bytes'] == plan['stage_bytes'] + plan['dependency_copy_bytes'] + plan['reserve_bytes']


def test_storage_details_scroll_and_delete_confirmation_stays_short(entry):
    from bobbi_platform import ce_install_ui as ui
    entries = cache_files(entry.env)
    ui.main(storage=True)
    assert len(entry.textviews) == len(entry.confirmations) == 1
    assert '已交付' in entry.textviews[0][1]
    assert len(entry.confirmations[0][1]) < 150
    assert all(not path.exists() for path in entries)


@pytest.mark.parametrize('playing_during_details', [False, True])
def test_offline_space_details_precede_short_confirmation_and_recheck_idle(entry, monkeypatch, playing_during_details):
    from bobbi_platform import ce_install_ui as ui
    import sys
    path = entry.env.root/'online.zip'
    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda p: str(entry.env.addons) if p.startswith('special:') else p)
    def view(*args):
        entry.textviews.append(args)
        entry.playing = playing_during_details
    entry.dialog.textviewer = view
    def decline(*args):
        entry.confirmations.append(args)
        return False
    entry.dialog.yesno = decline
    ui.main(payload=path)
    assert len(entry.textviews) == 1 and '解压暂存' in entry.textviews[0][1]
    if playing_during_details:
        assert not entry.confirmations
    else:
        assert len(entry.confirmations) == 1 and len(entry.confirmations[0][1]) < 150
    assert entry.env.installer._read() is None and entry.env.calls == []
