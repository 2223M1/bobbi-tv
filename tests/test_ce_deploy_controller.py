"""Local controller regression checks; no SSH, systemctl or device operations."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import types
import xml.etree.ElementTree as ET
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
spec = importlib.util.spec_from_file_location('ce_deploy_controller', ROOT / 'tools/deploy_ce_remote.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def make_installed(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE installed(id INTEGER PRIMARY KEY, addonID TEXT UNIQUE, enabled INTEGER, '
                   'installDate TEXT, lastUpdated TEXT, lastUsed TEXT, origin TEXT, disabledReason INTEGER)')
        for name, enabled, reason in [('plugin.video.jacktook', 1, 0), ('skin.am6b.cinema', 1, 0),
                                      ('user.unrelated', 0, 7), ('bobbi.existing', 0, 4)]:
            db.execute('INSERT INTO installed(addonID,enabled,disabledReason) VALUES(?,?,?)', (name, enabled, reason))


def test_addon_flag_roundtrip_preserves_unrelated_and_previous_disable_reason(tmp_path):
    database = tmp_path / 'Addons33.db'
    make_installed(database)
    ids = ['plugin.video.jacktook', 'skin.am6b.cinema', 'plugin.video.bobbi', 'bobbi.existing']
    previous = controller.flags(database, ids)
    assert previous['plugin.video.bobbi'] is None
    controller.flags(database, ids, {name: (0, 1) if name in controller.OLD_IDS else (1, 0) for name in ids})
    controller.flags(database, previous, previous)
    assert controller.flags(database, ids) == previous
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT enabled,disabledReason FROM installed WHERE addonID='user.unrelated'").fetchone() == (0, 7)


def test_unexpected_addon_schema_is_not_mutated(tmp_path):
    database = tmp_path / 'Addons33.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE installed(addonID TEXT, enabled INTEGER)')
        db.execute("INSERT INTO installed VALUES('user.unrelated',1)")
    with pytest.raises(ValueError, match='SCHEMA_CHANGED'):
        controller.flags(database, ['user.unrelated'], {'user.unrelated': (0, 1)})
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT * FROM installed').fetchall() == [('user.unrelated', 1)]


def test_old_receipt_cannot_reenable_remove_or_reassign_upstream_addons(tmp_path):
    database = tmp_path / 'Addons33.db'
    make_installed(database)
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO installed(addonID,enabled,origin,disabledReason) VALUES(?,?,?,?)",
                   ('script.module.requests', 0, 'repository.xbmc.org', 9))
    previous = {'script.module.requests': (1, 0), 'script.module.certifi': None,
                'plugin.video.bobbi': (1, 0)}
    controller.flags(database, previous, previous)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT enabled,origin,disabledReason FROM installed WHERE addonID=?',
                          ('script.module.requests',)).fetchone() == (0, 'repository.xbmc.org', 9)
        assert db.execute('SELECT * FROM installed WHERE addonID=?', ('script.module.certifi',)).fetchone() is None
        assert db.execute('SELECT enabled FROM installed WHERE addonID=?', ('plugin.video.bobbi',)).fetchone() == (1,)
    assert set(controller.flags(database, previous)) == {'plugin.video.bobbi'}


def test_program_receipt_projects_only_known_upstream_versions():
    engine = types.SimpleNamespace(managed={'plugin.video.bobbi'},
                                   expected={'plugin.video.bobbi', 'script.module.requests'})
    before = dict(sequence=1, versions={'plugin.video.bobbi': '1.0', 'script.module.requests': '2.0'})
    expected = dict(sequence=2, versions={'plugin.video.bobbi': '2.0', 'script.module.requests': '3.0'})
    observed = dict(sequence=2, versions={'plugin.video.bobbi': '2.0', 'script.module.requests': '99.0'})
    engine.available = lambda: observed
    receipt = dict(program_before=before, program_expected=expected, program_attempted=True)
    phase, actual, restored = controller.program_phase(engine, receipt)
    assert phase == 'applied'
    assert actual == generation(2) and restored == generation(2, '1.0')
    foreign = dict(sequence=2, versions=dict(observed['versions'], **{'foreign.addon': '1.0'}))
    with pytest.raises(RuntimeError, match='PROGRAM_RECEIPT_INVALID'):
        controller.owned_generation(engine, foreign)


def test_disabled_upstream_dependency_rejected_without_database_writes(tmp_path, monkeypatch):
    from bobbi_platform import upstream_addons
    monkeypatch.setattr(controller, 'KODI', tmp_path / 'kodi')
    database = controller.KODI / 'userdata/Database/Addons33.db'
    database.parent.mkdir(parents=True)
    make_installed(database)
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO installed(addonID,enabled,origin,disabledReason) VALUES(?,?,?,?)',
                   ('script.module.requests', 0, 'repository.xbmc.org', 9))
    monkeypatch.setattr(upstream_addons, 'check_dependencies', lambda *_: {'script.module.requests': '2.0.0'})
    engine = types.SimpleNamespace(managed={'plugin.video.bobbi'},
                                   expected={'plugin.video.bobbi', 'script.module.requests'})
    before = database.read_bytes()
    with pytest.raises(ValueError, match='CE_UPSTREAM_DISABLED_USE_KODI:script.module.requests'):
        controller.upstream_preflight(tmp_path / 'run', engine)
    assert database.read_bytes() == before


def test_skin_roundtrip_does_not_change_hdr_audio_or_subtitle_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, 'KODI', tmp_path)
    user = tmp_path / 'userdata'
    user.mkdir()
    path = user / 'guisettings.xml'
    path.write_text('''<settings><setting id="lookandfeel.skin">skin.am6b.cinema</setting>
      <setting id="lookandfeel.soundskin">resource.uisounds.am6b-modern</setting>
      <setting id="subtitles.color">gray</setting><setting id="audiooutput.passthrough">true</setting>
      <setting id="videoscreen.hdrguinits">30</setting></settings>''')
    before = controller.gui()
    controller.gui({'lookandfeel.skin': 'skin.bobbi.cinema', 'lookandfeel.soundskin': 'resource.uisounds.bobbi-modern'})
    controller.gui(before)
    assert controller.gui() == before
    values = {node.get('id'): node.text for node in ET.parse(path).findall('setting')}
    assert {key: values[key] for key in ('subtitles.color', 'audiooutput.passthrough', 'videoscreen.hdrguinits')} == {
        'subtitles.color': 'gray', 'audiooutput.passthrough': 'true', 'videoscreen.hdrguinits': '30'}


def test_program_rollback_failure_does_not_skip_flag_and_gui_restore(tmp_path, monkeypatch):
    import bobbi_platform.offline_updates as updates
    called = []
    class Engine:
        def available(self):
            return generation(2)
        def rollback(self):
            called.append('rollback')
            raise RuntimeError('injected rollback failure')
    monkeypatch.setattr(updates, 'load_trust', lambda: {})
    monkeypatch.setattr(updates, 'rollback_engine', lambda *a: Engine())
    monkeypatch.setattr(controller, 'flags', lambda *a: called.append('flags'))
    monkeypatch.setattr(controller, 'gui', lambda *a: called.append('gui'))
    monkeypatch.setattr(controller, 'write_json', lambda *a: None)
    lease = types.SimpleNamespace(idle=lambda: True, commit=lambda: None)
    receipt = program_receipt()
    try:
        controller.restore(tmp_path, receipt, lease)
    except RuntimeError:
        pass
    assert called == ['rollback', 'flags', 'gui']
    assert receipt.get('rolled_back') is not True


def generation(sequence, version=None):
    return dict(sequence=sequence, versions={'plugin.video.bobbi': version or str(sequence) + '.0'})


def program_receipt():
    return dict(schema=1, installed=True, program_before=generation(1),
                program_expected=generation(2), program_attempted=True,
                flags={'plugin.video.bobbi': None}, gui={'lookandfeel.skin': 'skin.am6b.cinema'})


@pytest.mark.parametrize('pids', ['', '12 13', '12 12', '../12', '0', '-1', '1/exe', '１２'])
def test_native_pin_requires_one_ascii_numeric_pid(monkeypatch, pids):
    from bobbi_core import runtime_paths
    monkeypatch.setattr(controller, 'command', lambda *a: pids)
    monkeypatch.setattr(runtime_paths, 'native_executable_sha256', lambda *a: pytest.fail('Do not open an invalid PID'))
    with pytest.raises(RuntimeError, match='NATIVE_PROCESS_NOT_UNIQUE'):
        controller.running_native_sha256()


def test_native_pin_keeps_actual_proc_object_despite_namespace_path_disagreement(monkeypatch):
    from bobbi_core import runtime_paths
    monkeypatch.setattr(controller, 'command', lambda *a: '24281\n')
    opened = []
    def probe(path):
        opened.append(path)
        return runtime_paths.CE_F9_SHA256 if path == Path('/proc/24281/exe') else 'other-namespace-binary'
    monkeypatch.setattr(runtime_paths, 'native_executable_sha256', probe)
    monkeypatch.setattr(Path, 'resolve', lambda *a, **kw: pytest.fail('Do not resolve the proc executable'))
    assert controller.running_native_sha256() == runtime_paths.CE_F9_SHA256
    assert opened == [Path('/proc/24281/exe')]


def rollback_harness(tmp_path, monkeypatch, rollback_error=False, command_failure=None,
                     current=None, available_failure_after=None):
    import bobbi_platform.offline_updates as updates
    import bobbi_platform.maintenance_lease as leases
    calls, lease_instances = [], []
    run = tmp_path / 'run'
    run.mkdir()
    config = tmp_path / 'old-config.json'
    config.write_text(json.dumps(dict(python_library_directory=str(tmp_path / 'python'))))
    monkeypatch.setattr(controller, 'CONFIG', config)
    monkeypatch.setattr(controller, 'WORK', tmp_path / 'work')
    monkeypatch.setattr(controller, 'KODI', tmp_path / 'kodi')
    monkeypatch.setattr(controller, 'bootstrap', lambda _: dict(sequence=1, components=[]))
    monkeypatch.setattr(controller, 'stopped', lambda: None)
    real_read_text = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw:
        'NAME="CoreELEC"\n' if path == Path('/etc/os-release') else real_read_text(path, *a, **kw))
    class Lease:
        def __init__(self, work):
            self.closed = False
            lease_instances.append(self)
        def close(self):
            self.closed = True
        def idle(self):
            return True
        def commit(self):
            raise AssertionError('Mock engine must not invoke a real commit')
    class Engine:
        state = current if current is not None else generation(2)
        inspections = 0
        def available(self):
            assert not lease_instances[0].closed
            self.inspections += 1
            if available_failure_after is not None and self.inspections > available_failure_after:
                raise RuntimeError('injected recovery failure')
            return self.state
        def rollback(self):
            calls.append(('rollback_program',))
            if rollback_error:
                raise RuntimeError('injected rollback failure')
            self.state = generation(2, '1.0')
    engine = Engine()
    def command(*args):
        calls.append(args)
        if command_failure and command_failure(args):
            raise RuntimeError('injected systemctl failure')
        return ''
    monkeypatch.setattr(controller, 'command', command)
    monkeypatch.setattr(controller, 'flags', lambda *a: calls.append(('restore_flags',)))
    monkeypatch.setattr(controller, 'gui', lambda *a: calls.append(('restore_gui',)))
    monkeypatch.setattr(leases, 'CoreELECLease', Lease)
    monkeypatch.setattr(updates, 'load_trust', lambda: {})
    monkeypatch.setattr(updates, 'rollback_engine', lambda *a: engine)
    sys.path.insert(0, str(ROOT / 'tools'))
    receipt = program_receipt()
    receipt['services'] = {unit: dict(UnitFileState='enabled', ActiveState='active') for unit in controller.UNITS}
    (run / 'deployment.json').write_text(json.dumps(receipt))
    return run, calls, lease_instances


def test_failed_program_rollback_keeps_owners_stopped_and_closes_lease(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch, rollback_error=True)
    with pytest.raises(RuntimeError, match='ROLLBACK_INCOMPLETE'):
        controller.main(run, 'rollback')
    assert ('restore_flags',) in calls and ('restore_gui',) in calls
    assert not any(len(args) > 1 and args[1] in ('start', 'unmask') for args in calls)
    assert leases[0].closed
    receipt = json.loads((run / 'deployment.json').read_text())
    assert receipt['recovery_required_owners_held_stopped'] is True
    assert receipt['rolled_back'] is False


def test_native_overlay_must_return_before_older_program_rollback(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    path = run / 'deployment.json'
    receipt = json.loads(path.read_text())
    receipt['native_before'] = 'a' * 64
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(controller, 'running_native_sha256', lambda: 'b' * 64)
    with pytest.raises(ValueError, match='RESTORE_PREVIOUS_NATIVE'):
        controller.main(run, 'rollback')
    assert ('rollback_program',) not in calls
    assert not any(row[0] == 'systemctl' and 'stop' in row for row in calls)


def test_successful_rollback_restores_only_recorded_owners(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    assert controller.main(run, 'rollback')['state'] == 'rolled_back'
    for unit in controller.UNITS:
        assert ('systemctl', 'unmask', '--runtime', unit) in calls
        assert ('systemctl', 'start', unit) in calls
    assert leases[0].closed
    assert json.loads((run / 'deployment.json').read_text())['installed'] is False


def test_unmask_failure_does_not_skip_other_recovery_or_lease_close(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch,
        command_failure=lambda args: args == ('systemctl', 'unmask', '--runtime', 'bobitv-preparation.service'))
    with pytest.raises(RuntimeError, match='SERVICE_RESTORE_FAILED'):
        controller.main(run, 'rollback')
    assert ('systemctl', 'unmask', '--runtime', 'kodi.service') in calls
    assert ('systemctl', 'start', 'kodi.service') in calls
    assert leases[0].closed
    receipt = json.loads((run / 'deployment.json').read_text())
    assert len(receipt['service_recovery_errors']) == 1


def test_gui_restore_failure_never_starts_a_mixed_owner_set(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    def fail(*args):
        calls.append(('restore_gui',))
        raise OSError('injected GUI write failure')
    monkeypatch.setattr(controller, 'gui', fail)
    with pytest.raises(RuntimeError, match='ROLLBACK_INCOMPLETE'):
        controller.main(run, 'rollback')
    assert not any(len(args) > 1 and args[1] in ('start', 'unmask') for args in calls)
    assert leases[0].closed


@pytest.mark.parametrize('current', [generation(3), generation(2, 'foreign.0')])
def test_old_run_cannot_stop_services_or_restore_ui_over_another_generation(tmp_path, monkeypatch, current):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch, current=current)
    original = (run / 'deployment.json').read_bytes()
    with pytest.raises(controller.GenerationConflict, match='STALE_GENERATION'):
        controller.main(run, 'rollback')
    assert calls == []
    assert (run / 'deployment.json').read_bytes() == original
    assert leases[0].closed


def test_recovery_failure_after_preflight_restores_ui_but_keeps_owners_stopped(tmp_path, monkeypatch):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch, available_failure_after=1)
    with pytest.raises(RuntimeError, match='ROLLBACK_INCOMPLETE'):
        controller.main(run, 'rollback')
    assert ('restore_flags',) in calls and ('restore_gui',) in calls
    assert ('rollback_program',) not in calls
    assert not any(len(args) > 1 and args[1] in ('start', 'unmask') for args in calls)
    assert json.loads((run / 'deployment.json').read_text())['recovery_required_owners_held_stopped']
    assert leases[0].closed


@pytest.mark.parametrize('installed', [True, False])
def test_boolean_only_receipt_cannot_authorize_explicit_rollback(tmp_path, monkeypatch, installed):
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    (run / 'deployment.json').write_text(json.dumps(dict(installed=installed)))
    with pytest.raises(RuntimeError, match='PROGRAM_RECEIPT_INVALID'):
        controller.main(run, 'rollback')
    assert calls == [] and leases[0].closed


def test_program_rollback_uses_durable_state_when_apply_raised_before_return():
    receipt = program_receipt()
    receipt['installed'] = False  # apply committed; caller never got its result.
    class Engine:
        state, rollbacks = generation(2), 0
        def available(self):
            return self.state
        def rollback(self):
            self.rollbacks += 1
            self.state = generation(2, '1.0')
    engine = Engine()
    controller.restore_program(engine, receipt)
    assert engine.rollbacks == 1
    assert receipt['applied_generation'] == generation(2)
    assert receipt['rolled_back_generation'] == generation(2, '1.0')
    # Explicit retry must not toggle the retained generation back to new code.
    controller.restore_program(engine, receipt)
    assert engine.rollbacks == 1 and receipt['installed'] is False


def test_apply_never_committed_does_not_roll_back_an_unrelated_previous_release():
    receipt = program_receipt()
    class Engine:
        def available(self):
            return generation(1)
        def rollback(self):
            pytest.fail('Not-applied generation must not invoke rollback')
    controller.restore_program(Engine(), receipt)
    assert receipt['program_observed'] == generation(1)
    assert receipt['installed'] is False
    assert 'rolled_back_generation' not in receipt


def test_rollback_committed_then_raised_is_confirmed_without_second_rollback():
    receipt = program_receipt()
    class Engine:
        state, rollbacks = generation(2), 0
        def available(self):
            return self.state
        def rollback(self):
            self.rollbacks += 1
            self.state = generation(2, '1.0')
            raise OSError('post-commit retention operation raised')
    engine = Engine()
    controller.restore_program(engine, receipt)
    controller.restore_program(engine, receipt)
    assert engine.rollbacks == 1
    assert receipt['rolled_back_generation'] == generation(2, '1.0')


@pytest.mark.parametrize('raises', [False, True])
def test_generation_change_during_rollback_does_not_restore_old_ui(tmp_path, monkeypatch, raises):
    import bobbi_platform.offline_updates as updates
    calls = []
    class Engine:
        state = generation(2)
        def available(self):
            return self.state
        def rollback(self):
            self.state = generation(3)
            if raises:
                raise OSError('newer generation appeared')
    engine = Engine()
    monkeypatch.setattr(updates, 'load_trust', lambda: {})
    monkeypatch.setattr(updates, 'rollback_engine', lambda *a: engine)
    monkeypatch.setattr(controller, 'flags', lambda *a: calls.append('flags'))
    monkeypatch.setattr(controller, 'gui', lambda *a: calls.append('gui'))
    receipt = program_receipt()
    with pytest.raises(RuntimeError, match='ROLLBACK_INCOMPLETE'):
        controller.restore(tmp_path, receipt, types.SimpleNamespace(idle=None, commit=None))
    assert calls == [] and receipt['rolled_back'] is False
    assert receipt['recovery_errors'] == ['program:CE_ROLLBACK_GENERATION_CHANGED']


def test_ambiguous_same_versions_cannot_authorize_generation_toggle():
    receipt = program_receipt()
    receipt['program_before']['versions'] = receipt['program_expected']['versions']
    with pytest.raises(RuntimeError, match='PROGRAM_RECEIPT_INVALID'):
        controller.program_phase(types.SimpleNamespace(available=lambda: generation(2)), receipt)


def test_upgrade_profile_snapshot_keeps_account_epoch_and_detects_changes(tmp_path, monkeypatch):
    from bobbi_core.runtime_paths import CE_F9_SHA256
    monkeypatch.setattr(controller, 'PROFILES', tmp_path)
    checks = []
    monkeypatch.setattr(controller, 'stopped', lambda: checks.append(True))
    for name in ('plugin.video.bobbi', 'script.module.bobbi.platform', 'skin.bobbi.cinema'):
        (tmp_path / name).mkdir()
    account = tmp_path / 'script.module.bobbi.platform/115-os_linux.json'
    scope = dict(account_id='', epoch=7, authenticated=False)
    account.write_text(json.dumps(dict(_account=scope)))
    marker = tmp_path / 'plugin.video.bobbi/runtime-paths.json'
    marker.write_text(json.dumps(dict(schema=1, subtitle_abi='ce-f9', native_sha256=CE_F9_SHA256)))
    before = controller.upgrade_profile_snapshot()
    assert before['script.module.bobbi.platform/115-os_linux.json']
    assert before['plugin.video.bobbi/database.pickle'] is None
    assert json.loads(account.read_text())['_account']['epoch'] == 7
    (tmp_path / 'plugin.video.bobbi/database.pickle').write_bytes(b'new-history')
    assert controller.upgrade_profile_snapshot() != before
    assert len(checks) == 2
    marker.write_text(json.dumps(dict(schema=1, subtitle_abi='profile')))
    with pytest.raises(ValueError, match='NATIVE_ABI'):
        controller.upgrade_profile_snapshot()


def test_upgrade_rejects_missing_profile_before_reading_account(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, 'PROFILES', tmp_path)
    monkeypatch.setattr(controller, 'stopped', lambda: None)
    with pytest.raises(ValueError, match='PROFILE_MISSING'):
        controller.upgrade_profile_snapshot()


def test_clean_preflight_never_treats_an_existing_profile_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, 'KODI', tmp_path / 'kodi')
    monkeypatch.setattr(controller, 'PROFILES', tmp_path / 'profiles')
    monkeypatch.setattr(controller, 'WORK', tmp_path / 'work')
    controller.clean_install_preflight()
    profile = controller.PROFILES / 'plugin.video.bobbi'
    profile.mkdir(parents=True)
    marker = profile / 'watch.json'
    marker.write_text('keep')
    with pytest.raises(ValueError, match='REQUIRES_EMPTY'):
        controller.clean_install_preflight()
    assert marker.read_text() == 'keep'


@pytest.mark.parametrize('apply_result', ['success', 'commit_then_raise', 'raise_before_commit', 'foreign_generation'])
@pytest.mark.parametrize('operation', ['deploy', 'upgrade'])
def test_deploy_main_records_intent_before_apply_and_recovers_durable_generation(tmp_path, monkeypatch, apply_result, operation):
    import bobbi_platform.offline_updates as updates
    from bobbi_core import runtime_paths
    from bobbi_core.runtime_paths import CE_F9_SHA256
    import ce_state_migration as migration
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    receipt_path = run / 'deployment.json'
    receipt_path.unlink()  # This harness now models a fresh deploy run.
    manifest = dict(sequence=2, components=[dict(id='plugin.video.bobbi', version='2.0')])
    monkeypatch.setattr(controller, 'bootstrap', lambda _: manifest)
    monkeypatch.setattr(controller, 'identity', lambda _: ({}, {}))
    def migrate(*args):
        assert operation == 'deploy', 'An upgrade must never repeat initial account migration'
        return dict(migrated=True)
    monkeypatch.setattr(controller, 'migrate_profiles', migrate)
    monkeypatch.setattr(controller, 'upgrade_profile_snapshot', lambda **kw: {'account': 'unchanged'})
    monkeypatch.setattr(controller, 'copy_file', lambda *a: None)
    monkeypatch.setattr(migration, 'sqlite_backup', lambda *a: None)
    monkeypatch.setattr(runtime_paths, 'native_executable_sha256', lambda *a: CE_F9_SHA256)
    def command(*args):
        calls.append(args)
        if args == ('pidof', 'kodi.bin'):
            return '12345'
        if '--property=ActiveState' in args:
            return 'active'
        if '--property=UnitFileState' in args:
            return 'enabled'
        return ''
    monkeypatch.setattr(controller, 'command', command)
    def flags(database, ids, values=None):
        calls.append(('flags', 'read' if values is None else 'write'))
        return {'plugin.video.bobbi': None}
    def gui(value=None):
        calls.append(('gui', 'read' if value is None else 'write'))
        return {'lookandfeel.skin': 'skin.am6b.cinema'}
    monkeypatch.setattr(controller, 'flags', flags)
    monkeypatch.setattr(controller, 'gui', gui)
    class Engine:
        state, rollbacks = generation(1), 0
        def available(self):
            assert not leases[0].closed
            return self.state
        def apply(self, raw, signature):
            recorded = json.loads(receipt_path.read_text())
            assert recorded['program_before'] == generation(1)
            assert recorded['program_expected'] == generation(2)
            assert recorded['program_attempted'] is True and recorded['installed'] is False
            calls.append(('apply',))
            if apply_result == 'raise_before_commit':
                raise OSError('apply failed before committing')
            self.state = generation(3) if apply_result == 'foreign_generation' else generation(2)
            if apply_result == 'commit_then_raise':
                raise OSError('apply committed before caller received the result')
        def rollback(self):
            self.rollbacks += 1
            self.state = generation(2, '1.0')
    engine = Engine()
    class Bundle:
        raw, signature = b'fixture-manifest', b'fixture-signature'
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def engine(self, *args):
            return engine
    monkeypatch.setattr(updates, 'SignedBundle', Bundle)
    monkeypatch.setattr(updates, 'rollback_engine', lambda *a: engine)
    if apply_result == 'success':
        assert controller.main(run, operation)['state'] == ('upgraded' if operation == 'upgrade' else 'deployed')
    else:
        with pytest.raises((OSError, controller.GenerationConflict)):
            controller.main(run, operation)
    receipt = json.loads(receipt_path.read_text())
    assert leases[0].closed and ('apply',) in calls
    if apply_result == 'success':
        assert receipt['applied_generation'] == generation(2) and receipt['installed'] is True
        assert engine.rollbacks == 0
        assert ('systemctl', 'start', 'kodi.service') in calls
        assert ('systemctl', 'start', 'bobitv-preparation.service') not in calls
        if operation == 'upgrade':
            assert receipt['migration']['performed'] is False
            assert receipt['profile_sentinels_unchanged'] == ['account']
    elif apply_result == 'foreign_generation':
        assert engine.rollbacks == 0
        assert receipt['recovery_required_owners_held_stopped'] is True
        assert ('flags', 'write') not in calls and ('gui', 'write') not in calls
        assert not any(len(args) > 1 and args[1] in ('start', 'unmask') for args in calls)
    else:
        assert receipt['rolled_back'] is True and receipt['installed'] is False
        assert ('flags', 'write') in calls and ('gui', 'write') in calls
        assert ('systemctl', 'start', 'kodi.service') in calls
        assert engine.rollbacks == (1 if apply_result == 'commit_then_raise' else 0)
        if apply_result == 'commit_then_raise':
            assert receipt['applied_generation'] == generation(2)
            assert receipt['rolled_back_generation'] == generation(2, '1.0')


def upgrade_harness(tmp_path, monkeypatch, sequence=2, version='2.0', fault=None):
    """Real current-account sentinels, mocked programs/systemd, no old runtime."""
    import bobbi_platform.offline_updates as updates
    import ce_state_migration as migration
    from bobbi_core.runtime_paths import CE_F9_SHA256
    run, calls, leases = rollback_harness(tmp_path, monkeypatch)
    receipt_path = run / 'deployment.json'
    receipt_path.unlink()
    monkeypatch.setattr(controller, 'CONFIG', tmp_path / 'retired-runtime-missing.json')
    monkeypatch.setattr(controller, 'LOGIN', tmp_path / 'retired-login-missing.json')
    monkeypatch.setattr(controller, 'PROFILES', tmp_path / 'profiles')
    for name in ('plugin.video.bobbi', 'script.module.bobbi.platform', 'skin.bobbi.cinema'):
        (controller.PROFILES / name).mkdir(parents=True)
    account = controller.PROFILES / 'script.module.bobbi.platform/115-os_linux.json'
    account.write_text(json.dumps(dict(_account=dict(account_id='', epoch=7, authenticated=False))))
    marker = controller.PROFILES / 'plugin.video.bobbi/runtime-paths.json'
    marker.write_text(json.dumps(dict(schema=1, subtitle_abi='ce-f9', native_sha256=CE_F9_SHA256)))
    manifest = dict(sequence=sequence, components=[dict(id='plugin.video.bobbi', version=version)])
    monkeypatch.setattr(controller, 'bootstrap', lambda _: manifest)
    monkeypatch.setattr(controller, 'running_native_sha256', lambda: CE_F9_SHA256)
    monkeypatch.setattr(controller, 'identity', lambda *a: pytest.fail('Upgrade must not access retired CD2/login'))
    monkeypatch.setattr(controller, 'migrate_profiles', lambda *a: pytest.fail('Upgrade must not remigrate account'))
    monkeypatch.setattr(controller, 'copy_file', lambda *a: None)
    monkeypatch.setattr(migration, 'sqlite_backup', lambda *a: None)
    service_states = {unit: dict(ActiveState='active', UnitFileState='enabled') for unit in controller.UNITS}
    events = []
    class Engine:
        state, rollbacks, applied = generation(1), 0, 0
        def available(self):
            if fault is not None:
                fault('available', self, None)
            return self.state
        def apply(self, *args):
            self.applied += 1
            events.append('apply')
            self.state = generation(sequence, version)
        def rollback(self):
            self.rollbacks += 1
            self.state = generation(sequence, '1.0')
    engine = Engine()
    class Bundle:
        raw, signature = b'manifest', b'signature'
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def engine(self, *args):
            return engine
    monkeypatch.setattr(updates, 'SignedBundle', Bundle)
    monkeypatch.setattr(updates, 'rollback_engine', lambda *a: engine)
    def command(*args):
        calls.append(args)
        if args[:2] == ('systemctl', 'show'):
            return service_states[args[2]][args[3].split('=', 1)[1]]
        if args[:2] in (('systemctl', 'mask'), ('systemctl', 'stop')):
            # Even the first mask has original states + a legal, durable intent.
            recorded = json.loads(receipt_path.read_text())
            assert recorded['services'] == service_states
            assert recorded['program_before'] == generation(1)
            assert recorded['program_expected'] == generation(sequence, version)
            assert args[-1] in recorded['services_attempted']
            events.append(args[1] + ':' + args[-1])
        if fault is not None:
            fault('command', engine, args)
        return ''
    monkeypatch.setattr(controller, 'command', command)
    def flags(database, ids, values=None):
        events.append('flags-write' if values is not None else 'flags-read')
        return {'plugin.video.bobbi': (1, 0)}
    def gui(value=None):
        events.append('gui-write' if value else 'gui-read')
        return {'lookandfeel.skin': 'skin.bobbi.cinema'}
    monkeypatch.setattr(controller, 'flags', flags)
    monkeypatch.setattr(controller, 'gui', gui)
    return types.SimpleNamespace(run=run, calls=calls, leases=leases, receipt=receipt_path,
        account=account, engine=engine, events=events, service_states=service_states)


def test_clean_install_needs_no_old_account_cd2_or_preparation_unit(tmp_path, monkeypatch):
    h = upgrade_harness(tmp_path, monkeypatch)
    controller.PROFILES.rename(tmp_path / 'unrelated-test-fixture')
    h.engine.state = dict(sequence=0, versions={})
    monkeypatch.setattr(controller, 'migrate_torrent_backend',
                        lambda *a: pytest.fail('Clean installation must not copy old BT settings'))
    monkeypatch.setattr(controller, 'upgrade_profile_snapshot',
                        lambda *a, **kw: pytest.fail('No prior account/profile required'))
    monkeypatch.setattr(controller, 'stopped', lambda units: h.calls.append(('quiescent', units)))
    def command(*args):
        h.calls.append(args)
        assert 'bobitv-preparation.service' not in args
        if '--property=ActiveState' in args:
            return 'active'
        if '--property=UnitFileState' in args:
            return 'enabled'
        return ''
    monkeypatch.setattr(controller, 'command', command)
    assert controller.main(h.run, 'clean-install')['state'] == 'installed'
    value = json.loads(h.receipt.read_text())
    assert value['operation'] == 'clean-install'
    assert value['program_before'] == dict(sequence=0, versions={})
    assert value['migration'] == dict(performed=False, policy='clean-own-account-first-run')
    assert value['torrent_connection'] == dict(state='unconfigured', optional=True)
    assert set(value['services']) == {'kodi.service'}
    assert ('systemctl', 'start', 'kodi.service') in h.calls


@pytest.mark.parametrize('sequence,version', [(0, '2.0'), (1, '2.0'), (2, '1.0')])
def test_invalid_upgrade_generation_rejected_before_any_service_change(tmp_path, monkeypatch, sequence, version):
    item = upgrade_harness(tmp_path, monkeypatch, sequence, version)
    with pytest.raises(controller.GenerationConflict, match='GENERATION_NOT_NEW'):
        controller.main(item.run, 'upgrade')
    assert not item.receipt.exists() and item.calls == []
    assert item.engine.applied == item.engine.rollbacks == 0 and item.leases[0].closed


@pytest.mark.parametrize('account_state', ['logout', 'changed_account'])
def test_upgrade_without_old_runtime_preserves_current_account_and_epoch(tmp_path, monkeypatch, account_state):
    from bobbi_platform.account_manager import account_id
    item = upgrade_harness(tmp_path, monkeypatch)
    if account_state == 'changed_account':
        value = dict(app='os_linux', cookies=dict(UID='456_new', CID='fixture', SEID='fixture'))
        value['_account'] = dict(account_id=account_id(value), epoch=19, authenticated=True)
        item.account.write_text(json.dumps(value))
    before = item.account.read_bytes()
    assert controller.main(item.run, 'upgrade')['state'] == 'upgraded'
    assert item.account.read_bytes() == before
    assert not controller.CONFIG.exists() and not controller.LOGIN.exists()
    receipt = json.loads(item.receipt.read_text())
    assert receipt['migration']['performed'] is False
    assert 'script.module.bobbi.platform/115-os_linux.json' in receipt['profile_sentinels_unchanged']
    assert item.events.index('apply') > item.events.index('stop:bobitv-preparation.service')
    assert item.engine.applied == 1 and item.engine.rollbacks == 0


@pytest.mark.parametrize('failure', [
    ('systemctl', 'mask', '--runtime', 'kodi.service'),
    ('systemctl', 'stop', 'kodi.service'),
    ('systemctl', 'stop', 'bobitv-preparation.service')])
def test_service_stop_window_failure_recovers_only_this_attempt_without_apply(tmp_path, monkeypatch, failure):
    def fault(stage, engine, args):
        if stage == 'command' and args == failure:
            raise OSError('injected service mutation failed after possible effect')
    item = upgrade_harness(tmp_path, monkeypatch, fault=fault)
    with pytest.raises(OSError):
        controller.main(item.run, 'upgrade')
    receipt = json.loads(item.receipt.read_text())
    assert receipt['rolled_back'] is True and receipt['program_attempted'] is False
    assert item.engine.applied == item.engine.rollbacks == 0
    for unit in receipt['services_attempted']:
        assert ('systemctl', 'unmask', '--runtime', unit) in item.calls
        assert ('systemctl', 'start', unit) in item.calls
    if failure[-1] == 'kodi.service':
        assert not any(args[-1] == 'bobitv-preparation.service' and args[1] != 'show' for args in item.calls)
    assert 'flags-write' not in item.events and 'gui-write' not in item.events
    assert item.leases[0].closed


def test_interrupted_stop_window_receipt_allows_explicit_safe_recovery(tmp_path, monkeypatch):
    armed = [True]
    def fault(stage, engine, args):
        if armed[0] and stage == 'command' and args == ('systemctl', 'stop', 'kodi.service'):
            armed[0] = False
            raise KeyboardInterrupt('simulate controller interruption before apply')
    item = upgrade_harness(tmp_path, monkeypatch, fault=fault)
    with pytest.raises(KeyboardInterrupt):
        controller.main(item.run, 'upgrade')
    receipt = json.loads(item.receipt.read_text())
    assert receipt['program_attempted'] is False and receipt['recovery_required_owners_held_stopped']
    assert controller.main(item.run, 'rollback')['state'] == 'rolled_back'
    assert item.engine.applied == item.engine.rollbacks == 0
    recovered = json.loads(item.receipt.read_text())
    assert recovered['rolled_back'] is True
    assert 'recovery_required_owners_held_stopped' not in recovered
    assert all(lease.closed for lease in item.leases)


@pytest.mark.parametrize('change', ['foreign', 'unknown'])
def test_generation_rechecked_after_stop_and_unknown_or_replaced_programs_hold(tmp_path, monkeypatch, change):
    stopped = [False]
    def fault(stage, engine, args):
        if stage == 'command' and args == ('systemctl', 'stop', 'bobitv-preparation.service'):
            stopped[0] = True
            if change == 'foreign':
                engine.state = generation(3)
        if stage == 'available' and stopped[0] and change == 'unknown':
            raise OSError('cannot establish program state')
    item = upgrade_harness(tmp_path, monkeypatch, fault=fault)
    with pytest.raises((controller.GenerationConflict, OSError)):
        controller.main(item.run, 'upgrade')
    receipt = json.loads(item.receipt.read_text())
    assert receipt['program_attempted'] is False and receipt['recovery_required_owners_held_stopped']
    assert not any(args[1] in ('unmask', 'start') for args in item.calls)
    assert item.engine.applied == item.engine.rollbacks == 0
    if change == 'foreign':
        assert 'flags-write' not in item.events and 'gui-write' not in item.events


@pytest.mark.parametrize('mutation', ['modified', 'extra'])
def test_bootstrap_cache_is_checked_again_before_import(tmp_path, monkeypatch, mutation):
    import bobbi_platform.offline_updates as updates
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, 'w') as package:
        package.writestr('addon.fixture/addon.xml', '<addon id="addon.fixture"/>')
    raw = blob.getvalue()
    manifest = dict(components=[dict(id='addon.fixture', file='fixture.zip', sha256=hashlib.sha256(raw).hexdigest())])
    with zipfile.ZipFile(tmp_path / 'candidate.zip', 'w') as package:
        package.writestr('release.json', json.dumps(manifest))
        package.writestr('fixture.zip', raw)
    class Bundle:
        def __init__(self, *args):
            self.manifest = manifest
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def check_all(self):
            return manifest
    monkeypatch.setattr(updates, 'SignedBundle', Bundle)
    monkeypatch.setattr(updates, 'load_trust', lambda: {})
    assert controller.bootstrap(tmp_path) == manifest
    root = tmp_path / 'bootstrap/addons/addon.fixture'
    if mutation == 'modified':
        (root / 'addon.xml').write_text('different code')
    else:
        (root / 'unlisted.py').write_text('different code')
    with pytest.raises(ValueError, match='BOOTSTRAP_(FILE|TREE)_CHANGED'):
        controller.bootstrap(tmp_path)


def driver_harness(tmp_path, monkeypatch, mode, outcome):
    spec = importlib.util.spec_from_file_location('ce_deploy_driver_test', ROOT / 'tools/deploy_ce_candidate.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    monkeypatch.setattr(driver, 'ROOT', tmp_path)
    run_id = '20261019-120000'
    bundle = tmp_path / 'candidate.zip'
    bundle.write_bytes(b'fixture-bundle')
    monkeypatch.setattr(sys, 'argv', ['deploy_ce_candidate.py', '--transport-source', str(tmp_path),
                                    '--mode', mode, '--run-id', run_id, '--bundle', str(bundle)])
    calls = []
    class SFTP:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def mkdir(self, path, mode):
            calls.append(('mkdir', path))
        def put(self, source, target):
            calls.append(('put', target))
        def chmod(self, *args):
            pass
    class Client:
        def __init__(self):
            self.closed = False
        def open_sftp(self):
            return SFTP()
        def close(self):
            self.closed = True
    client = Client()
    class Wire:
        def readonly(self, client, payload, deadline_seconds):
            calls.append(('payload', payload.decode()))
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
    class Loader:
        def create_module(self, spec):
            return None
        def exec_module(self, module):
            module.connect = lambda: (client, Wire())
    from importlib.machinery import ModuleSpec
    monkeypatch.setattr(driver.importlib.util, 'spec_from_file_location',
                        lambda name, path: ModuleSpec(name, Loader()))
    record = tmp_path / 'review-evidence/ce-deploy-runs' / (run_id + '.json')
    if mode != 'stage':
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps(dict(run='/storage/.local/share/bobbi-private-deploy/' + run_id,
                                         hashes={'candidate.zip': 'frozen-bundle-hash',
                                                 'controller.py': 'frozen-controller-hash'})))
    else:
        (tmp_path / 'tools').mkdir()
        for name in ('deploy_ce_remote.py', 'ce_state_migration.py'):
            (tmp_path / 'tools' / name).write_text('fixture staged source')
        # Signature/transition validation has its own real signed-bundle tests;
        # this harness isolates immutable upload and transport-loss behavior.
        monkeypatch.setattr(driver, 'transition_baseline', lambda path: dict(
            candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return driver, calls, client, record, tmp_path / 'review-evidence' / ('ce-' + run_id + '-' + mode + '.json')


def test_driver_rollback_uses_stage_hashes_not_current_workspace(tmp_path, monkeypatch):
    driver, calls, client, record, output = driver_harness(tmp_path, monkeypatch, 'rollback',
        (0, dict(state='rolled_back'), 0))
    # No current controller/migration source exists: the frozen run remains usable.
    driver.main()
    payload = next(value for kind, value in calls if kind == 'payload')
    assert 'frozen-controller-hash' in payload and 'frozen-bundle-hash' in payload
    assert 'except Exception as error:' in payload and 'receipt=str(' in payload
    assert json.loads(output.read_text())['result']['state'] == 'rolled_back'
    assert client.closed


def test_driver_remote_failure_still_records_result_before_raising(tmp_path, monkeypatch):
    driver, calls, client, record, output = driver_harness(tmp_path, monkeypatch, 'deploy',
        (1, dict(state='failed', error='RuntimeError', receipt='fixed-run/deployment.json'), 0))
    with pytest.raises(RuntimeError, match='operation failed'):
        driver.main()
    assert json.loads(output.read_text())['result']['state'] == 'failed'
    assert client.closed


def test_driver_transport_loss_never_claims_rollback_or_deployment_failure(tmp_path, monkeypatch):
    driver, calls, client, record, output = driver_harness(tmp_path, monkeypatch, 'deploy', TimeoutError())
    with pytest.raises(TimeoutError):
        driver.main()
    result = json.loads(output.read_text())
    assert result['state'] == 'unconfirmed'
    assert 'before any retry' in result['instruction']
    assert client.closed


def test_stage_run_is_immutable_and_cannot_overwrite_inputs(tmp_path, monkeypatch):
    driver, calls, client, record, output = driver_harness(tmp_path, monkeypatch, 'stage',
        (0, dict(state='staged'), 0))
    driver.main()
    frozen = record.read_bytes()
    assert sum(kind == 'put' for kind, value in calls) == 4
    before = list(calls)
    with pytest.raises(FileExistsError):
        driver.main()
    assert calls == before and record.read_bytes() == frozen
