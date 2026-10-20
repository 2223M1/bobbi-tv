"""Signed 22-component validation with 13-owned transactions and 9 preserved addons."""
import base64
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from bobbi_platform.offline_updates import SignedBundle, rollback_engine
from bobbi_platform.updates import UpdateEngine, UpdateError
from bobbi_platform.upstream_addons import (FULL_COMPONENTS, OWNED_COMPONENTS,
    UPSTREAM_COMPONENTS, check_dependencies)
from test_upstream_addons import addon_xml, install, snapshot


@contextmanager
def lease():
    yield


@pytest.fixture(scope='module')
def full_signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = key.public_key().public_numbers()
    return key, dict(schema=1, key=dict(algorithm='RSA3072-SHA256', e=65537,
                        n=format(numbers.n, 'x')), components=sorted(FULL_COMPONENTS))


def component(name, version, minimum='1.0.0', fault=None):
    stream = BytesIO()
    requires = (dict(addon='script.module.requests', version=minimum),
                dict(addon='xbmc.python', version='99.0.0')) if name == 'plugin.video.bobbi' else ()
    with zipfile.ZipFile(stream, 'w') as output:
        output.writestr(name + '/addon.xml', addon_xml(name,
            '99.0.0' if fault == 'wrong_version' else version, requires,
            'other.addon' if fault == 'wrong_id' else None))
        output.writestr(name + '/code.py', 'VERSION = ' + repr(version))
        if fault == 'traversal':
            output.writestr(name + '/../escape.py', 'never write')
    return b'not a zip' if fault == 'invalid_zip' else stream.getvalue()


def bundle(path, signer, sequence=1, version='1.0.0', vendor_version='1.0.0',
           minimum='1.0.0', fault=None):
    key, _ = signer
    items, blobs = [], {}
    for name in sorted(FULL_COMPONENTS):
        value = vendor_version if name in UPSTREAM_COMPONENTS else version
        raw = component(name, value, minimum,
                        fault if name == 'script.module.requests' else None)
        filename = name + '/' + name + '-' + value + '.zip'
        items.append(dict(id=name, version=value, file=filename, size=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest()))
        blobs[filename] = (raw[:-1] + bytes([raw[-1] ^ 1])
                          if fault == 'hash' and name == 'script.module.requests' else raw)
    value = dict(schema=2, channel='private-candidate', profile='coreelec',
                 sequence=sequence, components=items)
    raw = json.dumps(value, sort_keys=True).encode()
    signature = base64.b64encode(key.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as target:
        target.writestr('release.json', raw)
        target.writestr('release.sig', signature)
        for name, content in blobs.items():
            target.writestr(name, content)
    return path


def seed_upstream(root, version='3.0.0+matrix.2'):
    for name in UPSTREAM_COMPONENTS:
        target = install(root / 'addons', name, version)
        (target / 'upstream-owned-extra').write_bytes(b'Kodi managed original addon')


def external_snapshot(root):
    return {name: snapshot(root / 'addons' / name) for name in sorted(UPSTREAM_COMPONENTS)}


def apply(path, signer, root, *, legacy=False, configure=None, commit_lease=lease):
    with SignedBundle(path, signer[1], 'coreelec') as source:
        if legacy:
            # Reproduce the frozen historical controller's full ownership;
            # the new engine must not reinterpret unfinished old transactions.
            engine = UpdateEngine(root / 'addons', root / 'work', FULL_COMPONENTS,
                'private-candidate', 'coreelec', lambda *_: True, source.read,
                lambda: True, commit_lease, offline=True, retain_previous=True)
        else:
            engine = source.engine(root / 'addons', root / 'work', lambda: True, commit_lease)
        if configure:
            configure(engine)
        result = engine.apply(source.raw, source.signature)
    return engine, result


def projected(sequence, version):
    return dict(sequence=sequence, versions=dict.fromkeys(OWNED_COMPONENTS, version))


def restore_engine(signer, root):
    return rollback_engine(signer[1], 'coreelec', root / 'addons', root / 'work', lambda: True, lease)


def test_signed_complete_bundle_preserves_newer_upstream_across_update_and_rollback(tmp_path, full_signer):
    seed_upstream(tmp_path)
    original = external_snapshot(tmp_path)
    seen = []
    def record(engine):
        download = engine.download
        engine.download = lambda name, maximum: (seen.append(name), download(name, maximum))[1]
    first = bundle(tmp_path / 'one.zip', full_signer)
    engine, state = apply(first, full_signer, tmp_path, configure=record)
    assert engine.expected == FULL_COMPONENTS
    assert engine.managed == OWNED_COMPONENTS
    assert len(seen) == 22
    assert state == projected(1, '1.0.0')
    assert external_snapshot(tmp_path) == original
    previous = json.loads(engine.previous_path.read_text())
    assert set(previous['entries']) == OWNED_COMPONENTS
    assert previous['digests'] == {}
    engine, state = apply(bundle(tmp_path / 'two.zip', full_signer, 2, '2.0.0'), full_signer, tmp_path)
    assert state == projected(2, '2.0.0')
    assert engine.rollback() == projected(2, '1.0.0')
    assert external_snapshot(tmp_path) == original
    assert engine.rollback() == projected(2, '2.0.0')
    assert external_snapshot(tmp_path) == original
    assert all('2.0.0' in (engine.addons / name / 'addon.xml').read_text() for name in OWNED_COMPONENTS)
    assert set(json.loads(engine.previous_path.read_text())['entries']) == OWNED_COMPONENTS


def test_equal_upstream_version_is_still_not_overwritten(tmp_path, full_signer):
    seed_upstream(tmp_path, '1.0.0')
    original = external_snapshot(tmp_path)
    engine, _ = apply(bundle(tmp_path / 'one.zip', full_signer), full_signer, tmp_path)
    assert engine.rollback() == dict(sequence=1, versions={})
    assert external_snapshot(tmp_path) == original
    assert all(not (engine.addons / name).exists() for name in OWNED_COMPONENTS)


@pytest.mark.parametrize('fault', ['hash', 'wrong_id', 'wrong_version', 'traversal', 'invalid_zip'])
def test_unused_upstream_archives_still_undergo_complete_validation(tmp_path, full_signer, fault):
    seed_upstream(tmp_path)
    original = snapshot(tmp_path / 'addons')
    with pytest.raises(UpdateError):
        apply(bundle(tmp_path / 'bad.zip', full_signer, fault=fault), full_signer, tmp_path)
    assert snapshot(tmp_path / 'addons') == original
    assert not (tmp_path / 'work/state.json').exists()
    assert not (tmp_path / 'work/journal.json').exists()
    assert not (tmp_path / 'work/previous.json').exists()
    assert [path.name for path in (tmp_path / 'work').iterdir()] == ['update.lock']


@pytest.mark.parametrize('fault', ['missing', 'outdated'])
def test_bundled_vendor_never_seeds_missing_or_outdated_kodi_dependency(tmp_path, full_signer, fault):
    seed_upstream(tmp_path)
    target = tmp_path / 'addons/script.module.requests/addon.xml'
    if fault == 'missing':
        target.unlink()
    else:
        install(tmp_path / 'addons', 'script.module.requests', '0.9.0')
    original = snapshot(tmp_path / 'addons')
    with pytest.raises(UpdateError, match='script.module.requests.*install/update.*Kodi'):
        apply(bundle(tmp_path / 'one.zip', full_signer), full_signer, tmp_path)
    assert snapshot(tmp_path / 'addons') == original
    assert not (tmp_path / 'work/state.json').exists()
    assert not (tmp_path / 'work/journal.json').exists()


def test_dependency_is_rechecked_under_exclusive_lease_before_owned_moves(tmp_path, full_signer):
    seed_upstream(tmp_path)
    @contextmanager
    def changed_dependency():
        install(tmp_path / 'addons', 'script.module.requests', '0.9.0')
        yield
    with pytest.raises(UpdateError, match='too old'):
        apply(bundle(tmp_path / 'one.zip', full_signer), full_signer, tmp_path,
              commit_lease=changed_dependency)
    assert all(not (tmp_path / 'addons' / name).exists() for name in OWNED_COMPONENTS)
    assert not (tmp_path / 'work/state.json').exists()
    assert not (tmp_path / 'work/journal.json').exists()


def test_rollback_checks_previous_generation_dependencies_without_restoring_vendors(tmp_path, full_signer):
    seed_upstream(tmp_path)
    apply(bundle(tmp_path / 'one.zip', full_signer, minimum='3.0.0'), full_signer, tmp_path)
    engine, _ = apply(bundle(tmp_path / 'two.zip', full_signer, 2, '2.0.0'), full_signer, tmp_path)
    install(tmp_path / 'addons', 'script.module.requests', '2.0.0')
    before = snapshot(tmp_path / 'addons'), engine.state_path.read_bytes(), engine.previous_path.read_bytes()
    with pytest.raises(UpdateError, match='too old'):
        engine.rollback()
    assert (snapshot(tmp_path / 'addons'), engine.state_path.read_bytes(), engine.previous_path.read_bytes()) == before
    assert not engine.journal_path.exists()


def legacy_previous(root, signer):
    seed_upstream(root, '1.0.0')
    apply(bundle(root / 'old-one.zip', signer), signer, root, legacy=True)
    engine, _ = apply(bundle(root / 'old-two.zip', signer, 2, '2.0.0', '2.0.0'), signer, root, legacy=True)
    previous = json.loads(engine.previous_path.read_text())
    assert set(previous['entries']) == FULL_COMPONENTS
    assert set(previous['digests']) == FULL_COMPONENTS
    seed_upstream(root, '3.0.0+matrix.2')
    return restore_engine(signer, root), previous


def test_legacy_previous22_verifies_all_backups_but_restores_only_owned13(tmp_path, full_signer):
    engine, previous = legacy_previous(tmp_path, full_signer)
    original = external_snapshot(tmp_path)
    assert set(engine.available()['versions']) == FULL_COMPONENTS
    verified = []
    tree = engine._tree
    def record(path):
        verified.append(path)
        return tree(path)
    engine._tree = record
    assert engine.rollback() == projected(2, '1.0.0')
    historical = engine.work / previous['transaction'] / 'backup'
    assert {path.name for path in verified if path.parent == historical} == FULL_COMPONENTS
    assert external_snapshot(tmp_path) == original
    current = json.loads(engine.previous_path.read_text())
    assert set(current['entries']) == OWNED_COMPONENTS
    assert set(current['digests']) == OWNED_COMPONENTS
    assert set(current['state']['versions']) == OWNED_COMPONENTS
    assert engine.rollback() == projected(2, '2.0.0')
    assert external_snapshot(tmp_path) == original


@pytest.mark.parametrize('tamper', ['owned', 'upstream'])
def test_legacy_backup_integrity_includes_preserved_upstream(tmp_path, full_signer, tamper):
    engine, previous = legacy_previous(tmp_path, full_signer)
    name = 'script.module.requests' if tamper == 'upstream' else 'plugin.video.bobbi'
    (engine.work / previous['transaction'] / 'backup' / name / 'code.py').write_text('tampered')
    before = snapshot(engine.addons), engine.state_path.read_bytes(), engine.previous_path.read_bytes()
    with pytest.raises(UpdateError, match='integrity'):
        engine.rollback()
    assert (snapshot(engine.addons), engine.state_path.read_bytes(), engine.previous_path.read_bytes()) == before
    assert not engine.journal_path.exists()


@pytest.mark.parametrize('phase', ['committing', 'committed'])
def test_legacy_unfinished22_journal_requires_frozen_controller_and_is_not_reinterpreted(
        tmp_path, full_signer, monkeypatch, phase):
    from bobbi_platform import updates
    seed_upstream(tmp_path, '1.0.0')
    original_atomic = updates._atomic
    def crash(path, value):
        original_atomic(path, value)
        if path.name == 'journal.json' and value['phase'] == phase:
            raise KeyboardInterrupt('old controller crash')
    monkeypatch.setattr(updates, '_atomic', crash)
    with pytest.raises(KeyboardInterrupt):
        apply(bundle(tmp_path / 'old.zip', full_signer), full_signer, tmp_path, legacy=True)
    monkeypatch.setattr(updates, '_atomic', original_atomic)
    engine = restore_engine(full_signer, tmp_path)
    before = snapshot(tmp_path / 'addons'), snapshot(tmp_path / 'work')
    for action in (engine.available, engine.recover, engine.rollback):
        with pytest.raises(UpdateError, match='frozen controller'):
            action()
        assert (snapshot(tmp_path / 'addons'), snapshot(tmp_path / 'work')) == before


CRASH_CUTS = [(kind, cut) for kind, count in [('first', 13), ('update', 26), ('rollback', 26)]
              for cut in range(1, count + 1)]


@pytest.mark.parametrize('kind,cut', CRASH_CUTS)
def test_every_owned_move_crash_recovers_without_touching_upstream(tmp_path, full_signer, kind, cut):
    seed_upstream(tmp_path)
    original = external_snapshot(tmp_path)
    first = bundle(tmp_path / 'one.zip', full_signer)
    second = bundle(tmp_path / 'two.zip', full_signer, 2, '2.0.0')
    if kind != 'first':
        apply(first, full_signer, tmp_path)
    if kind == 'rollback':
        engine, _ = apply(second, full_signer, tmp_path)
    engines = []
    def configure(engine):
        engines.append(engine)
        move, calls = engine._move, []
        def crash(source, target):
            assert source.name in OWNED_COMPONENTS and target.name in OWNED_COMPONENTS
            move(source, target)
            calls.append(1)
            if len(calls) == cut:
                raise KeyboardInterrupt('owned transaction crash')
        engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        if kind == 'rollback':
            configure(engine)
            engine.rollback()
        else:
            apply(first if kind == 'first' else second, full_signer, tmp_path, configure=configure)
    interrupted = engines[0]
    journal = json.loads(interrupted.journal_path.read_text())
    assert set(journal['entries']) == OWNED_COMPONENTS
    assert not set(journal['old_state']['versions']) & UPSTREAM_COMPONENTS
    engine = restore_engine(full_signer, tmp_path)
    expected = (dict(sequence=0, versions={}) if kind == 'first'
                else projected(2 if kind == 'rollback' else 1,
                               '2.0.0' if kind == 'rollback' else '1.0.0'))
    assert engine.available() == expected
    assert external_snapshot(tmp_path) == original
    assert not engine.journal_path.exists()
    for name in OWNED_COMPONENTS:
        xml = engine.addons / name / 'addon.xml'
        assert xml.exists() == (kind != 'first')
        if kind != 'first':
            assert expected['versions'][name] in xml.read_text()


def test_first_owned_apply_after_legacy_state_projects_recovery_not_external_state(tmp_path, full_signer):
    engine, _ = legacy_previous(tmp_path, full_signer)
    original = external_snapshot(tmp_path)
    def configure(engine):
        move = engine._move
        def crash(source, target):
            move(source, target)
            raise KeyboardInterrupt('first owned move')
        engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        apply(bundle(tmp_path / 'three.zip', full_signer, 3, '3.0.0'), full_signer, tmp_path,
              configure=configure)
    assert restore_engine(full_signer, tmp_path).available() == projected(2, '2.0.0')
    assert external_snapshot(tmp_path) == original
    assert restore_engine(full_signer, tmp_path).rollback() == projected(2, '1.0.0')
    assert external_snapshot(tmp_path) == original


@pytest.mark.parametrize('override', ['unexpected_inventory', 'wrong_managed', 'online', 'no_check'])
def test_partial_ownership_cannot_be_enabled_for_an_unreviewed_boundary(tmp_path, override):
    expected, managed, offline, check = FULL_COMPONENTS, OWNED_COMPONENTS, True, check_dependencies
    if override == 'unexpected_inventory':
        expected = FULL_COMPONENTS | {'another.addon'}
    elif override == 'wrong_managed':
        managed = OWNED_COMPONENTS - {'repository.bobbi'}
    elif override == 'online':
        offline = False
    elif override == 'no_check':
        check = None
    with pytest.raises(UpdateError, match='partial component ownership'):
        UpdateEngine(tmp_path / 'addons', tmp_path / 'work', expected,
            'private-candidate', 'coreelec', None, None, None, None, offline=offline,
            managed_components=managed, dependency_check=check)
