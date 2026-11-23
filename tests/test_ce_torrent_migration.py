"""Connection-only CE migration and generation-boundary tests; no device I/O."""
import json
from pathlib import Path
import sys

import pytest

import test_ce_deploy_controller as harness

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/plugin.video.bobbi.torrent/lib'))
sys.path.insert(0, str(ROOT / 'tools'))
controller = harness.controller
MANIFEST = dict(components=[dict(id=controller.TORRENT_ID)])


@pytest.fixture
def migration(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, 'PROFILES', tmp_path / 'profiles')
    monkeypatch.setattr(controller, 'stopped', lambda: None)
    source = controller.PROFILES / 'plugin.video.jacktorr/settings.xml'
    target = controller.PROFILES / controller.TORRENT_ID / 'backend.json'
    source.parent.mkdir(parents=True)
    return source, target


def legacy(source, extra=''):
    source.write_text('<settings><setting id="service_host">127.0.0.1</setting>'
                      '<setting id="service_port" value="8090"/>'
                      '<setting id="ssl_connection">false</setting>' + extra + '</settings>')


def test_missing_legacy_is_optional_and_does_not_create_profile(migration):
    source, target = migration
    assert controller.migrate_torrent_backend(MANIFEST) == {
        'state': 'unconfigured', 'reason': 'legacy-settings-absent'}
    assert not target.parent.exists()


def test_only_connection_fields_migrate_and_service_is_not_touched(migration, monkeypatch):
    source, target = migration
    legacy(source, '<setting id="service_enabled">false</setting>'
           '<setting id="apply_settings_to_torrserver">true</setting>'
           '<setting id="s:CacheSize">999</setting>'
           '<setting id="service_login">fixture-user</setting>'
           '<setting id="service_password">fixture-pass</setting>')
    original = source.read_bytes()
    monkeypatch.setattr(controller, 'command', lambda *a: pytest.fail('No engine/service changes'))
    result = controller.migrate_torrent_backend(MANIFEST)
    value = json.loads(target.read_text())
    assert value == dict(schema=1, endpoint='http://127.0.0.1:8090',
        auth=dict(username='fixture-user', password='fixture-pass'), metadata_seconds=30, buffering_seconds=90)
    assert source.read_bytes() == original
    assert result['old_service_unchanged'] and result['preserved_on_rollback']
    assert set(result['fields']) == {'service_host', 'service_port', 'ssl_connection',
                                     'service_login', 'service_password'}
    assert 'fixture-' not in json.dumps(result) and '127.0.0.1' not in json.dumps(result)


def test_existing_configuration_is_validated_but_not_rewritten(migration):
    source, target = migration
    legacy(source)
    controller.migrate_torrent_backend(MANIFEST)
    value = json.loads(target.read_text())
    value['buffering_seconds'] = 51
    target.write_text(json.dumps(value, separators=(',', ':')))
    original = target.read_bytes()
    source.write_text('broken legacy now irrelevant')
    assert controller.migrate_torrent_backend(MANIFEST)['state'] == 'existing-preserved'
    assert target.read_bytes() == original


@pytest.mark.parametrize('bad', ['{}', '{"schema":1}', 'not-json'])
def test_invalid_existing_config_is_not_overwritten(migration, bad):
    from bobbi_torrent.backend import BackendError
    source, target = migration
    legacy(source)
    target.parent.mkdir()
    target.write_text(bad)
    with pytest.raises(BackendError):
        controller.migrate_torrent_backend(MANIFEST)
    assert target.read_text() == bad


@pytest.mark.parametrize('bad', [
    '<settings><setting id="service_port">8090</setting></settings>',
    '<!DOCTYPE settings><settings/>',
    '<settings><setting id="service_host">127.0.0.1</setting><setting id="service_host">localhost</setting></settings>',
    '<other/>', 'x' * (256 * 1024 + 1)], ids=['missing-host', 'doctype', 'duplicate', 'root', 'oversize'])
def test_malformed_or_oversized_legacy_fails_without_writing(migration, bad):
    source, target = migration
    source.write_text(bad)
    with pytest.raises((ValueError, RuntimeError)):
        controller.migrate_torrent_backend(MANIFEST)
    assert not target.exists()


@pytest.mark.parametrize('which', ['source', 'target', 'parent'])
def test_symlink_migration_is_rejected(migration, which, tmp_path):
    source, target = migration
    real = tmp_path / 'real'
    real.mkdir()
    legacy(real / 'settings.xml')
    try:
        if which == 'source':
            source.symlink_to(real / 'settings.xml')
        elif which == 'target':
            target.parent.mkdir()
            target.symlink_to(real / 'settings.xml')
        else:
            target.parent.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create symlink fixtures')
    with pytest.raises(ValueError, match='SYMLINK'):
        controller.migrate_torrent_backend(MANIFEST)


def test_engine_owner_must_be_stopped_before_migration(migration, monkeypatch):
    source, target = migration
    legacy(source)
    def running():
        raise RuntimeError('CE_OWNER_RUNNING')
    monkeypatch.setattr(controller, 'stopped', running)
    with pytest.raises(RuntimeError, match='OWNER_RUNNING'):
        controller.migrate_torrent_backend(MANIFEST)
    assert not target.exists()


def test_backend_is_preserved_as_program_update_sentinel(tmp_path, monkeypatch):
    item = harness.upgrade_harness(tmp_path, monkeypatch)
    target = controller.PROFILES / controller.TORRENT_ID / 'backend.json'
    target.parent.mkdir()
    value = dict(schema=1, endpoint='http://localhost:8090', auth=None,
                 metadata_seconds=30, buffering_seconds=90)
    target.write_text(json.dumps(value))
    before = target.read_bytes()
    assert controller.main(item.run, 'upgrade')['state'] == 'upgraded'
    receipt = json.loads(item.receipt.read_text())
    assert controller.TORRENT_ID + '/backend.json' in receipt['profile_sentinels_unchanged']
    assert controller.main(item.run, 'rollback')['state'] == 'rolled_back'
    assert target.read_bytes() == before


def test_old_pending_transaction_rejected_before_owner_mutations(tmp_path, monkeypatch):
    item = harness.upgrade_harness(tmp_path, monkeypatch)
    controller.WORK.mkdir()
    journal = controller.WORK / 'journal.json'
    journal.write_text('{"old":"unfinished"}')
    with pytest.raises(ValueError, match='PENDING_TRANSACTION'):
        controller.main(item.run, 'upgrade')
    assert item.calls == [] and not item.receipt.exists()
    assert journal.read_text() == '{"old":"unfinished"}'
    assert item.engine.applied == item.engine.rollbacks == 0 and item.leases[0].closed


def transition(run):
    from bobbi_platform.offline_updates import load_trust
    from ce_state_migration import digest
    trust = load_trust()
    (run / 'candidate.zip').write_bytes(b'fixed-candidate')
    value = dict(schema=1, baseline_sequence=2026101905,
        from_components=[i for i in trust['components'] if i != controller.TORRENT_ID],
        to_components=trust['components'], key=trust['key'],
        candidate_sha256=digest(run / 'candidate.zip'), candidate_sequence=2026101906)
    manifest = dict(sequence=2026101906, components=[dict(id=i) for i in trust['components']])
    return value, manifest


def test_transition_manifest_is_bound_to_same_key_and_exact_component_set(tmp_path):
    value, manifest = transition(tmp_path)
    (tmp_path / 'transition-baseline.json').write_text(json.dumps(value))
    assert controller.transition_boundary(tmp_path, manifest) is None


@pytest.mark.parametrize('change', ['extra', 'missing', 'key', 'hash', 'replay', 'duplicate', 'bool'])
def test_transition_rejects_modified_boundaries(tmp_path, change):
    value, manifest = transition(tmp_path)
    if change == 'extra':
        value['unexpected'] = True
    elif change == 'missing':
        value['from_components'].pop()
    elif change == 'key':
        value['key']['e'] = 3
    elif change == 'hash':
        value['candidate_sha256'] = '0' * 64
    elif change == 'replay':
        value['candidate_sequence'] = 2026101905
    elif change == 'duplicate':
        value['from_components'][0] = value['from_components'][1]
    else:
        value['schema'] = True
    (tmp_path / 'transition-baseline.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='TRANSITION_INVALID'):
        controller.transition_boundary(tmp_path, manifest)
