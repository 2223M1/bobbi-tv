"""Offline capacity admission through real layouts/engines/controller/driver."""
from contextlib import redirect_stdout
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from bobbi_platform import ce_storage as storage, offline_updates, upstream_addons
from bobbi_platform.updates import UpdateError
from test_updates import Harness, archive
from test_offline_updates import signer, bundle, lease
from test_ce_general_installer import signing, package, environment
from test_ce_deploy_controller import controller, upgrade_harness, driver_harness, ROOT

SignedBundle = offline_updates.SignedBundle
controller_space = controller.controller_space
BASELINE = '36767e6c30dd835a73c6eada397ed8e6cf8dcbb4'


@pytest.fixture
def volume(monkeypatch):
    state = dict(free_bytes=8*1024**3, free_inodes=1000000, unit=4096)
    def observe(path):
        return dict(state, device=storage._existing_directory(path).stat().st_dev)
    monkeypatch.setattr(storage, 'filesystem', observe)
    return state


def transactions(work):
    return {p.name for p in work.iterdir() if re.fullmatch('[a-f0-9]{32}', p.name)}


def installed(tmp_path, signer):
    for sequence in (1, 2):
        path = bundle(tmp_path/(str(sequence)+'.zip'), signer, sequence, str(sequence)+'.0.0')
        with SignedBundle(path, signer[1], 'windows') as source:
            engine = source.engine(tmp_path/'addons', tmp_path/'work', lambda: True, lease)
            engine.apply(source.raw, source.signature)
    return engine


@pytest.mark.parametrize('fault', ['bytes', 'inodes'])
def test_engine_refuses_before_transaction_and_download(tmp_path, volume, fault):
    h = Harness(tmp_path)
    manifest = h.manifest()
    volume['free_bytes' if fault == 'bytes' else 'free_inodes'] = 0
    with pytest.raises(storage.SpaceRequired):
        h.apply(manifest)
    assert h.downloads == [] and not transactions(h.engine.work)
    assert not h.engine.journal_path.exists() and not h.engine.state_path.exists()


def test_baseline_negative_control_really_lacked_engine_admission(tmp_path, monkeypatch, volume):
    raw = subprocess.run(['git','show',BASELINE+':addons/script.module.bobbi.platform/lib/bobbi_platform/updates.py'],
                         cwd=ROOT, check=True, capture_output=True).stdout
    module = SimpleNamespace(__name__='bobbi_platform.old_capacity_engine', __package__='bobbi_platform')
    exec(compile(raw, '<frozen-baseline-updates>', 'exec'), module.__dict__)
    h = Harness(tmp_path)
    h.engine = module.UpdateEngine(tmp_path/'addons', tmp_path/'work', h.engine.expected,
        'preview', 'android', h.verify, h.download, h.idle, h.lease)
    volume['free_bytes'] = 0
    assert h.apply(h.manifest())['sequence'] == 1
    assert h.downloads  # Same zero-space observer is never consulted by old code.


def test_exact_signed_stage_and_old_copy_are_both_reserved(tmp_path, signer, volume):
    engine = installed(tmp_path, signer)
    old = tmp_path/'addons/plugin.video.bobbi/large-old-asset'
    old.write_bytes(b'x'*1048577)
    path = bundle(tmp_path/'3.zip', signer, 3, '3.0.0')
    with SignedBundle(path, signer[1], 'windows') as source:
        engine = source.engine(engine.addons, engine.work, lambda: True, lease)
        report = engine.space_budget(source.manifest).report()
        parts = report['parts']
        recovery = sum(p['bytes'] for p in parts if p['kind'] == 'rollback-copy')
        stage = sum(p['bytes'] for p in parts if p['kind'] == 'stage')
        assert recovery > 1048577 and stage > 0
        assert report['required_bytes'] == stage+recovery+storage.CONTROL_BYTES+storage.RESERVE
        volume['free_bytes'] = report['required_bytes']-1
        before = transactions(engine.work)
        with pytest.raises(storage.SpaceRequired):
            engine.apply(source.raw, source.signature)
        assert transactions(engine.work) == before and old.stat().st_size == 1048577


def test_online_component_downloads_once_and_checks_exact_expansion_before_write(tmp_path, volume, monkeypatch):
    h = Harness(tmp_path)
    manifest = h.manifest()
    original = h.download
    extracted = []
    def download(url, limit):
        value = original(url, limit)
        volume['free_bytes'] = storage.CONTROL_BYTES+storage.RESERVE
        return value
    h.engine.download = download
    monkeypatch.setattr(h.engine, '_extract', lambda *a: extracted.append(a))
    with pytest.raises(storage.SpaceRequired):
        h.apply(manifest)
    assert len(h.downloads) == 1 and extracted == []
    assert not transactions(h.engine.work) and not h.engine.journal_path.exists()


def test_many_components_reuse_initial_owned_scan_and_rescan_only_at_commit(tmp_path, volume, monkeypatch):
    h = Harness(tmp_path)
    h.engine.retain_previous = True
    original, scanned = storage.tree_allocation, []
    def scan(path, *args, **kwargs):
        scanned.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(storage, 'tree_allocation', scan)
    h.apply(h.manifest())
    assert len(scanned) == 2*len(h.engine.managed)
    assert len(h.downloads) == len(h.engine.expected)


def test_signed_layout_integrity_failure_precedes_any_staging(tmp_path, signer, volume):
    path = bundle(tmp_path/'good.zip', signer)
    bad = tmp_path/'bad.zip'
    with zipfile.ZipFile(path) as reader, zipfile.ZipFile(bad, 'w') as writer:
        for row in reader.infolist():
            value = reader.read(row)
            if row.filename.endswith('.zip'):
                value = bytes([value[0]^1])+value[1:]
            writer.writestr(row, value)
    with SignedBundle(bad, signer[1], 'windows') as source:
        engine = source.engine(tmp_path/'addons', tmp_path/'work', lambda: True, lease)
        with pytest.raises(UpdateError, match='integrity'):
            engine.apply(source.raw, source.signature)
        assert not transactions(engine.work) and not engine.journal_path.exists()


@pytest.mark.parametrize('fault', ['bytes', 'inodes', 'scan'])
def test_rollback_refuses_before_copytree_or_new_transaction(tmp_path, signer, volume, monkeypatch, fault):
    engine = installed(tmp_path, signer)
    before = transactions(engine.work), engine.state_path.read_bytes(), engine.previous_path.read_bytes()
    if fault == 'scan':
        monkeypatch.setattr(storage, 'SCAN_FILES', 1)
    else:
        volume['free_bytes' if fault == 'bytes' else 'free_inodes'] = 0
    monkeypatch.setattr(storage.shutil, 'copytree',
                        lambda *a, **kw: pytest.fail('No rollback copy before capacity admission'))
    with pytest.raises(UpdateError):
        engine.rollback()
    assert before == (transactions(engine.work), engine.state_path.read_bytes(), engine.previous_path.read_bytes())


def test_forward_reservation_covers_first_rollback_under_fixed_quota(tmp_path, monkeypatch):
    """Free space shrinks with actual tree allocation, without outside writes."""
    h = Harness(tmp_path)
    h.engine.retain_previous = True
    h.apply(h.manifest())
    candidate = h.manifest(2, '2.0.0')
    blob = archive(candidate['components'][0]['id'], '2.0.0',
                   extra=[(candidate['components'][0]['id']+'/large', bytes(range(256))*16384)])
    # Keep the existing archive expansion ratio contract (stored payload).
    data = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as reader, zipfile.ZipFile(data, 'w') as writer:
        for item in reader.infolist():
            writer.writestr(item.filename, reader.read(item))
    h.replace_blob(candidate, data.getvalue())
    layout = [storage.component_layout(h.blobs[row['url']], row) for row in candidate['components']]
    h.engine.layout_reader = lambda: layout
    required = h.engine.space_budget(candidate).report()['required_bytes']
    def used():
        return storage.tree_allocation(tmp_path,4096)['bytes']
    quota = used()+required+128*1024
    device = tmp_path.stat().st_dev
    monkeypatch.setattr(storage, 'filesystem', lambda _: dict(device=device, unit=4096,
        free_bytes=max(0,quota-used()), free_inodes=1000000))
    assert h.apply(candidate)['sequence'] == 2
    current = h.engine._read(h.engine.previous_path)
    report = h.engine.space_budget(previous=current, recovery_copy=False).report()
    assert not any(p['kind'] == 'rollback-copy' for p in report['parts'])
    assert any(p['kind'] == 'rollback-stage' for p in report['parts'])
    assert h.engine.rollback()['versions'] == dict.fromkeys(h.engine.managed,'1.0.0')


def test_tree_budget_counts_tiny_files_directories_and_never_credits_cleanup(tmp_path, volume):
    root = tmp_path/'tree'
    (root/'sub').mkdir(parents=True)
    (root/'a').write_bytes(b'a')
    (root/'sub/b').write_bytes(b'b')
    assert storage.tree_allocation(root, 4096) == dict(bytes=4*4096, inodes=4, logical=2)
    with pytest.raises(UpdateError, match='SCAN_INCOMPLETE'):
        storage.tree_allocation(root, 4096, [2,1024])
    budget = storage.SpaceBudget('test')
    budget.tree(root, tmp_path, 'copy')
    report = budget.report()
    assert report['required_bytes'] == storage.RESERVE+4*4096
    assert all(p['bytes'] >= 0 for p in report['parts'])


@pytest.mark.parametrize('field', ['free_bytes','free_inodes'])
@pytest.mark.parametrize('delta', [-1,0,1])
def test_exact_byte_and_inode_thresholds_are_inclusive(tmp_path, volume, field, delta):
    initial = storage.SpaceBudget('threshold')
    initial.add(tmp_path, 'file', 4097, 2)
    row = initial.report()['filesystems'][0]
    volume[field] = row['required_bytes' if field == 'free_bytes' else 'required_inodes']+delta
    checked = storage.SpaceBudget('threshold')
    checked.add(tmp_path, 'file', 4097, 2)
    assert checked.report()['fits'] is (delta >= 0)


def test_different_filesystems_never_pool_free_space_or_inodes(tmp_path, monkeypatch):
    def directory(path):
        device = 2 if 'run' in str(path) else 1
        return SimpleNamespace(device=device, stat=lambda: SimpleNamespace(st_dev=device))
    monkeypatch.setattr(storage, '_existing_directory', directory)
    def observe(path):
        return dict(device=path.device, unit=4096, free_bytes=10**10 if path.device == 1 else 4096,
                    free_inodes=1000000)
    monkeypatch.setattr(storage, 'filesystem', observe)
    budget = storage.SpaceBudget('split')
    budget.add(tmp_path/'work', 'stage', 1024)
    budget.add(tmp_path/'run', 'upload', 1024)
    report = budget.report()
    assert report['free_bytes'] > report['required_bytes'] and not report['fits']
    assert len(report['filesystems']) == 2
    assert all(row['required_bytes'] == storage.RESERVE+4096 for row in report['filesystems'])
    with pytest.raises(UpdateError, match='share a filesystem'):
        storage.program_budget(tmp_path/'addons', tmp_path/'run', ())


@pytest.mark.parametrize('fault', ['none','statvfs','block-size','inodes'])
def test_posix_statvfs_uses_available_not_total_free_and_never_defaults(tmp_path, monkeypatch, fault):
    observed = SimpleNamespace(f_frsize=8192, f_bavail=110, f_bfree=999, f_favail=7)
    if fault == 'block-size':
        observed.f_frsize = 0
    if fault == 'inodes':
        observed.f_favail = -1
    def statvfs(path):
        if fault == 'statvfs':
            raise OSError('statvfs unavailable')
        return observed
    monkeypatch.setattr(storage, 'os', SimpleNamespace(name='posix', statvfs=statvfs))
    if fault != 'none':
        with pytest.raises(OSError):
            storage.filesystem(tmp_path)
    else:
        result = storage.filesystem(tmp_path)
        assert result['unit'] == 8192 and result['free_bytes'] == 110*8192 and result['free_inodes'] == 7


def test_rename_crash_recovery_does_not_demand_copy_or_upload_budget(tmp_path, volume, monkeypatch):
    h = Harness(tmp_path)
    h.apply(h.manifest())
    original = h.engine._move
    class Crash(BaseException):
        pass
    def crash_after_rename(source, target):
        original(source, target)
        raise Crash()
    monkeypatch.setattr(h.engine, '_move', crash_after_rename)
    with pytest.raises(Crash):
        h.apply(h.manifest(2, '2.0.0'))
    assert h.engine.journal_path.exists()
    monkeypatch.setattr(h.engine, '_move', original)
    monkeypatch.setattr(h.engine, 'space_budget', lambda *a, **kw: pytest.fail('Rename recovery needs no staging budget'))
    volume['free_bytes'] = 0
    assert h.engine.recover()
    assert not h.engine.journal_path.exists()
    assert all('1.0.0' in (h.engine.addons/name/'addon.xml').read_text() for name in h.engine.managed)


def test_old_kodi_installer_negative_control_admitted_only_reserve_after_dependencies(environment, signing, volume, monkeypatch):
    env = environment
    raw = subprocess.run(['git','show',BASELINE+':addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py'],
                         cwd=ROOT, check=True, capture_output=True).stdout
    module = SimpleNamespace(__name__='bobbi_platform.old_capacity_installer', __package__='bobbi_platform')
    exec(compile(raw, '<frozen-baseline-installer>', 'exec'), module.__dict__)
    def dependencies(stage):
        env.calls.append('dependencies')
        volume['free_bytes'] = storage.RESERVE+1
    env.host.dependencies = dependencies
    monkeypatch.setattr(module.shutil, 'disk_usage', lambda _: SimpleNamespace(free=volume['free_bytes']))
    old = module.Installer(env.addons, env.work, env.host, signing[1])
    old.apply(package(env.root/'one.zip', signing))
    assert 'quiesce' in env.calls and old._read()['phase'] == 'complete'


@pytest.mark.parametrize('fault', ['bytes','inodes'])
def test_kodi_capacity_drop_after_quiesce_restores_unchanged_program_without_copy(environment, signing, volume, monkeypatch, fault):
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    original = {name:(env.addons/name/'addon.xml').read_bytes() for name in env.installer._read()['versions']}
    env.calls.clear()
    def quiesce():
        env.calls.append('quiesce')
        if fault == 'bytes':
            volume['free_bytes'] = storage.RESERVE+1
        else:
            volume['free_inodes'] = 0
    env.host.quiesce = quiesce
    monkeypatch.setattr(storage.shutil, 'copytree', lambda *a, **kw: pytest.fail('Rename recovery must not copy'))
    with pytest.raises(storage.SpaceRequired) as caught:
        env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    assert caught.value.space['phase'] == 'before-switch'
    assert env.installer._read()['phase'] == 'restored'
    assert original == {name:(env.addons/name/'addon.xml').read_bytes() for name in original}
    assert any(isinstance(call, tuple) and call[0] == 'restore' for call in env.calls)


@pytest.mark.parametrize('fault', ['missing', 'bad-db', 'wal-without-shm'])
def test_unknown_sqlite_snapshot_is_not_optimistic(tmp_path, fault):
    path = tmp_path/'state.db'
    if fault == 'bad-db':
        path.write_bytes(b'not sqlite')
    if fault == 'wal-without-shm':
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE t(v)')
        Path(str(path)+'-wal').write_bytes(b'unverified WAL')
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises((UpdateError, sqlite3.DatabaseError)):
        storage.sqlite_size(path)
    assert before == {p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_sqlite_size_uses_wal_visible_pages_without_checkpoint_or_sidefile_creation(tmp_path):
    path = tmp_path/'state.db'
    db = sqlite3.connect(path)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('CREATE TABLE t(v BLOB)')
        db.execute('INSERT INTO t VALUES(?)', (b'x'*1024*1024,))
        db.commit()
        expected = db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
        before = {p.name:p.stat().st_size for p in tmp_path.iterdir()}
        assert expected > path.stat().st_size
        assert storage.sqlite_size(path) == expected
        assert before == {p.name:p.stat().st_size for p in tmp_path.iterdir()}
    finally:
        db.close()


@pytest.fixture
def host(tmp_path, monkeypatch, signing):
    root = tmp_path/'kodi'
    (root/'addons').mkdir(parents=True)
    database = root/'userdata/Database/Addons33.db'
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE installed(addonID TEXT,enabled INTEGER)')
    db.close()
    (root/'userdata/guisettings.xml').write_text('<settings/>')
    work, run = tmp_path/'work', tmp_path/'run'
    run.mkdir()
    monkeypatch.setattr(controller, 'KODI', root)
    monkeypatch.setattr(controller, 'WORK', work)
    monkeypatch.setattr(controller, 'PROFILES', root/'userdata/addon_data')
    monkeypatch.setattr(controller, 'PREFLIGHT', SimpleNamespace(ce_storage=storage,
        offline_updates=offline_updates, upstream_addons=upstream_addons, trust=signing[1]))
    package(run/'candidate.zip', signing)
    return SimpleNamespace(root=root, work=work, run=run, database=database)


def test_real_preupload_budget_includes_every_overlap_before_mkdir(host, volume):
    with SignedBundle(host.run/'candidate.zip', controller.PREFLIGHT.trust, 'coreelec') as source:
        layout = storage.bundle_layout(source)
    report = controller.preupload_space(host.run/'new-run', layout, [96334897,8192,4096])
    kinds = {p['kind'] for p in report['parts']}
    assert {'stage','bootstrap','upload','database-backup','database-journal','gui-backup',
            'gui-temporary','controller-metadata','profile-metadata','transaction-metadata'} <= kinds
    assert not host.work.exists() and not (host.run/'new-run').exists()
    volume['free_bytes'] = report['required_bytes']-1
    with pytest.raises(storage.SpaceRequired):
        controller.preupload_space(host.run/'new-run', layout, [96334897,8192,4096])
    assert not host.work.exists() and not (host.run/'new-run').exists()


def test_controller_skin_copy_contains_only_descriptor_but_full_stage_and_recovery_remain(host, volume, monkeypatch):
    monkeypatch.setattr(sys, 'path', list(sys.path))
    with SignedBundle(host.run/'candidate.zip', controller.PREFLIGHT.trust, 'coreelec') as source:
        full = storage.bundle_layout(source)
    skin = next(row for row in full if row['id'] == controller.SKIN)
    assert len(skin['files']) > 1
    reduced = controller.bootstrap_layout(full)
    projected = next(row for row in reduced if row['id'] == controller.SKIN)
    assert projected == dict(id=controller.SKIN, files=[max(skin['files'])], directories=1)
    assert [r for r in reduced if r != projected] == [r for r in full if r != skin]
    controller.bootstrap(host.run)
    root = host.run/'bootstrap/addons'
    assert [p.name for p in (root/controller.SKIN).iterdir()] == ['addon.xml']
    assert (root/'script.module.bobbi.platform/code.py').exists()
    # Skipping the skin's non-descriptor files is never permission to execute
    # an extra file already present in the cached controller input.
    (root/controller.SKIN/'extra.py').write_text('raise AssertionError')
    with pytest.raises(ValueError, match='BOOTSTRAP_TREE_CHANGED'):
        controller.bootstrap(host.run)


@pytest.mark.parametrize('fault', ['space', 'inodes', 'stat', 'database'])
def test_bootstrap_refuses_before_first_directory_or_candidate_import(host, volume, monkeypatch, fault):
    before = list(sys.path)
    if fault == 'space':
        volume['free_bytes'] = 0
    elif fault == 'inodes':
        volume['free_inodes'] = 0
    elif fault == 'database':
        host.database.unlink()
    else:
        monkeypatch.setattr(storage, 'filesystem', lambda _: (_ for _ in ()).throw(OSError('stat failed')))
    with pytest.raises((UpdateError, OSError)):
        controller.bootstrap(host.run)
    assert not (host.run/'bootstrap').exists() and not host.work.exists()
    assert sys.path == before


def test_status_checks_signed_inputs_without_bootstrap_work_or_lease(host, volume, monkeypatch):
    read = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda p,*a,**kw:
                        'NAME=CoreELEC' if p == Path('/etc/os-release') else read(p,*a,**kw))
    transitions, calls = [], []
    monkeypatch.setattr(controller, 'transition_boundary', lambda *a: transitions.append(a))
    monkeypatch.setattr(controller, 'rpc', lambda *a: calls.append(a) or [])
    volume['free_bytes'] = 0
    before = list(sys.path)
    assert controller.main(host.run, 'status')['state'] == 'status'
    assert transitions and len(calls) == 2 and sys.path == before
    assert not (host.run/'bootstrap').exists() and not host.work.exists()


@pytest.mark.parametrize('operation', ['inspect_bundle', 'bootstrap'])
@pytest.mark.parametrize('fault', ['layout','crc'])
def test_readonly_inspection_preserves_signed_inner_layout_and_crc_checks(host, signing, fault, operation):
    path = host.run/'candidate.zip'
    with zipfile.ZipFile(path) as reader:
        manifest = json.loads(reader.read('release.json'))
        blobs = {row['file']:reader.read(row['file']) for row in manifest['components']}
    row = next(r for r in manifest['components'] if r['id'] == controller.SKIN)
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as writer:
        writer.writestr(row['id']+'/addon.xml', '<addon id="skin.bobbi.cinema"/>')
        writer.writestr(row['id']+('/../escape' if fault == 'layout' else '/media/asset.png'), b'CONTENT_MARKER')
    blob = data.getvalue()
    if fault == 'crc':
        blob = blob.replace(b'CONTENT_MARKER', b'changed_marker')
    blobs[row['file']] = blob
    row.update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    raw = json.dumps(manifest).encode()
    signature = base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as writer:
        writer.writestr('release.json', raw)
        writer.writestr('release.sig', signature)
        for name,value in blobs.items():
            writer.writestr(name,value)
    before = list(sys.path)
    with pytest.raises(UpdateError if fault == 'layout' else zipfile.BadZipFile):
        getattr(controller, operation)(host.run)
    assert sys.path == before and not (host.run/'bootstrap').exists() and not host.work.exists()


def test_controller_real_space_rejection_precedes_service_mutations(tmp_path, signer, volume, monkeypatch):
    h = upgrade_harness(tmp_path, monkeypatch)
    database = controller.KODI/'userdata/Database/Addons33.db'
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE t(v)')
    db.close()
    (controller.KODI/'userdata/guisettings.xml').write_text('<settings/>')
    # The lifecycle harness mocks systemd/program commit. Bind its capacity
    # callback to a real signed bundle and real engine, not a success stub.
    path = bundle(tmp_path/'real.zip', signer)
    def real_space(run, source, engine, mode, config=None, **kw):
        with SignedBundle(path, signer[1], 'windows') as signed:
            actual = signed.engine(tmp_path/'addons', tmp_path/'work', lambda: True, lease)
            return controller_space(run, signed, actual, mode, config, **kw)
    monkeypatch.setattr(controller, 'controller_space', real_space)
    monkeypatch.setattr(controller, 'PREFLIGHT', SimpleNamespace(ce_storage=storage))
    volume['free_bytes'] = 0
    with pytest.raises(storage.SpaceRequired):
        controller.main(h.run, 'upgrade')
    assert not any(a[:2] in (('systemctl','mask'),('systemctl','stop')) for a in h.calls)
    assert h.engine.applied == 0 and not h.receipt.exists()


def test_controller_rechecks_after_stop_before_database_copy(tmp_path, signer, volume, monkeypatch):
    import ce_state_migration as migration
    h = upgrade_harness(tmp_path, monkeypatch)
    database = controller.KODI/'userdata/Database/Addons33.db'
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE t(v)')
    db.close()
    (controller.KODI/'userdata/guisettings.xml').write_text('<settings/>')
    path = bundle(tmp_path/'real.zip', signer)
    calls = []
    def real_space(run, source, engine, mode, config=None, **kw):
        calls.append(mode)
        if len(calls) == 2:
            volume['free_bytes'] = 0
        with SignedBundle(path, signer[1], 'windows') as signed:
            actual = signed.engine(tmp_path/'addons', tmp_path/'work', lambda: True, lease)
            return controller_space(run, signed, actual, mode, config, **kw)
    monkeypatch.setattr(controller, 'controller_space', real_space)
    monkeypatch.setattr(controller, 'PREFLIGHT', SimpleNamespace(ce_storage=storage))
    monkeypatch.setattr(migration, 'sqlite_backup', lambda *a: pytest.fail('No database copy after capacity loss'))
    with pytest.raises(storage.SpaceRequired):
        controller.main(h.run, 'upgrade')
    assert calls == ['upgrade','upgrade']
    assert ('systemctl','stop','kodi.service') in h.calls and h.engine.applied == 0
    assert ('systemctl','start','kodi.service') in h.calls
    assert json.loads(h.receipt.read_text())['rolled_back'] is True


def test_driver_capacity_failure_never_opens_sftp_or_creates_remote_run(tmp_path, monkeypatch):
    h = driver_harness(tmp_path, monkeypatch, 'stage', (1, dict(state='failed'), 0))
    driver, calls, client, record, output = h
    def fail(*a):
        raise RuntimeError('CE_UPLOAD_SPACE_UNPROVEN')
    monkeypatch.setattr(driver, 'upload_preflight', fail)
    with pytest.raises(RuntimeError, match='CE_UPLOAD_SPACE_UNPROVEN'):
        driver.main()
    assert calls == [] and client.closed


@pytest.mark.parametrize('outcome', ['success','low-space','transport-loss'])
def test_driver_readonly_probe_executes_frozen_shared_estimator_and_records_result(host, monkeypatch, outcome):
    spec = importlib.util.spec_from_file_location('capacity_driver_real', ROOT/'tools/deploy_ce_candidate.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    runtime = dict(modules=[], trust=controller.PREFLIGHT.trust)
    for name in ('updates','upstream_addons','signatures','offline_updates','ce_storage'):
        raw = (ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform'/(name+'.py')).read_text(encoding='utf-8')
        runtime['modules'].append(dict(name=name, source=raw, sha256=hashlib.sha256(raw.encode()).hexdigest()))
    with SignedBundle(host.run/'candidate.zip', runtime['trust'], 'coreelec') as source:
        layout = storage.bundle_layout(source)
    inputs = {'candidate.zip':host.run/'candidate.zip','controller.py':ROOT/'tools/deploy_ce_remote.py'}
    hashes = {name:driver._file_sha256(path) for name,path in inputs.items()}
    capacity = dict(runtime=runtime, layout=layout, candidate_sha256=hashes['candidate.zip'])
    probe = []
    class Wire:
        def readonly(self, client, script, deadline_seconds):
            if outcome == 'transport-loss':
                raise TimeoutError('sensitive diagnostic must not be persisted')
            # Execute the exact emitted probe in-process with only fixture
            # destinations substituted; never connect to SSH or a real box.
            text = script.decode().replace('controller.PREFLIGHT=package',
                'controller.PREFLIGHT=package\ncontroller.KODI=pathlib.Path('+repr(str(host.root))+')'
                +'\ncontroller.WORK=pathlib.Path('+repr(str(host.work))+')'
                +'\ncontroller.PROFILES=controller.KODI/"userdata/addon_data"')
            if outcome == 'low-space':
                text = text.replace('controller.PREFLIGHT=package',
                    'observed=package.ce_storage.filesystem\n'
                    +'package.ce_storage.filesystem=lambda p: dict(observed(p),free_bytes=0)\n'
                    +'controller.PREFLIGHT=package')
            output = io.StringIO()
            code = 0
            with redirect_stdout(output):
                try:
                    exec(compile(text,'<readonly-capacity-probe>','exec'), {})
                except SystemExit as error:
                    code = error.code
            result = json.loads(output.getvalue())
            probe.append(result)
            return code, result, ''
    before = {p.relative_to(host.run).as_posix() for p in host.run.rglob('*')}
    receipt = host.run.parent/'capacity-result.json'
    if outcome == 'success':
        report = driver.upload_preflight(object(), Wire(), str(host.run/'new-run'), capacity, inputs, hashes, receipt)
        assert report['fits'] and probe[0]['state'] == 'space-ready'
    else:
        with pytest.raises(TimeoutError if outcome == 'transport-loss' else RuntimeError):
            driver.upload_preflight(object(), Wire(), str(host.run/'new-run'), capacity, inputs, hashes, receipt)
    value = json.loads(receipt.read_text())
    assert value['remote_writes'] is False
    if outcome == 'low-space':
        assert value['space']['free_bytes'] == 0 and value['space']['parts'] and value['space']['filesystems']
        assert value['error'] == 'SpaceRequired' and value['state'] == 'failed'
    elif outcome == 'transport-loss':
        assert value['state'] == 'unconfirmed' and 'sensitive' not in receipt.read_text()
    assert before == {p.relative_to(host.run).as_posix() for p in host.run.rglob('*')}
    assert not host.work.exists()


def test_migration_requires_complete_legacy_inventory(host, volume):
    with SignedBundle(host.run/'candidate.zip', controller.PREFLIGHT.trust, 'coreelec') as source:
        layout = storage.bundle_layout(source)
    with pytest.raises(ValueError, match='MIGRATION_SPACE_UNPROVEN'):
        controller.deployment_budget(host.run, layout, (), mode='deploy', config={})
    with pytest.raises(UpdateError, match='STORAGE_TREE_CHANGED'):
        controller.deployment_budget(host.run, layout, (), mode='deploy', config={'state_directory':str(host.run/'missing')})
