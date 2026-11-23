"""Historical full 21-to-22 transactions and today's separate owned-only policy.

The frozen 1905/1906 controller managed every component. Explicit legacy engine
fixtures preserve its original 43-move recovery contract without asking today's
SignedBundle.engine to recreate that ownership. Full current-policy coverage,
including rejection of unfinished 22-entry journals, is in test_upstream_updates.
No device operations are performed.
"""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from bobbi_platform.offline_updates import SignedBundle, rollback_engine
from bobbi_platform.signatures import verify
from bobbi_platform.updates import UpdateEngine, UpdateError
from bobbi_platform.upstream_addons import OWNED_COMPONENTS, UPSTREAM_COMPONENTS
from test_updates import archive


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ce_transition_driver', ROOT / 'tools/deploy_ce_candidate.py')
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
OLD = driver.BASELINE_COMPONENTS
NEW = driver.TRANSITION_COMPONENTS
FIRST = driver.BASELINE_SEQUENCE


@contextmanager
def lease():
    yield


def canonical_key_hash(key):
    return hashlib.sha256(json.dumps(key, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.fixture(scope='module')
def signer():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = private.public_key().public_numbers()
    key = dict(algorithm='RSA3072-SHA256', n=format(numbers.n, 'x'), e=numbers.e)
    return private, key


def trust(key, components):
    return dict(schema=1, key=deepcopy(key), components=list(components))


def make_bundle(path, signer, components, sequence, version):
    private, _ = signer
    rows, blobs = [], {}
    for name in components:
        raw = archive(name, version)
        filename = name + '/' + name + '-' + version + '.zip'
        rows.append(dict(id=name, version=version, file=filename, size=len(raw),
                         sha256=hashlib.sha256(raw).hexdigest()))
        blobs[filename] = raw
    manifest = dict(schema=2, channel='private-candidate', profile='coreelec',
                    sequence=sequence, components=rows)
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    signature = base64.b64encode(private.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr('release.json', raw)
        output.writestr('release.sig', signature)
        for name, blob in blobs.items():
            output.writestr(name, blob)
    return manifest


def legacy_engine_for(pinned, root, source=None):
    """Explicit historical full-inventory policy, never a current-policy factory."""
    def no_download(*_):
        raise UpdateError('Historical recovery is local only')
    return UpdateEngine(root / 'addons', root / 'work', pinned['components'],
        'private-candidate', 'coreelec', lambda raw, sig: verify(raw, sig, pinned['key']),
        source.read if source is not None else no_download,
        lambda: True, lease, offline=True, retain_previous=True)


def legacy_apply(path, pinned, root):
    with SignedBundle(path, pinned, 'coreelec') as source:
        engine = legacy_engine_for(pinned, root, source)
        assert engine.managed == engine.expected == frozenset(pinned['components'])
        result = engine.apply(source.raw, source.signature)
    return engine, result


def files(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


@pytest.fixture
def releases(tmp_path, signer):
    old = tmp_path / 'old.zip'
    new = tmp_path / 'new.zip'
    make_bundle(old, signer, OLD, FIRST, '1.0.0')
    manifest = make_bundle(new, signer, NEW, FIRST + 1, '2.0.0')
    root = tmp_path / 'installation'
    profile = root / 'userdata'
    profile.mkdir(parents=True)
    (profile / 'account.fixture').write_bytes(b'account state must not enter program transactions')
    unrelated = root / 'addons/plugin.owner.other'
    unrelated.mkdir(parents=True)
    (unrelated / 'keep.fixture').write_bytes(b'not a managed component')
    return dict(root=root, old=old, new=new, manifest=manifest,
                old_trust=trust(signer[1], OLD), new_trust=trust(signer[1], NEW))


def transition_value(key, manifest, digest='a' * 64):
    return dict(schema=1, baseline_sequence=FIRST, from_components=list(OLD),
                to_components=list(NEW), key=deepcopy(key), candidate_sha256=digest,
                candidate_sequence=manifest['sequence'])


def pinned_contract():
    key = json.loads((ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/release_trust.json')
                     .read_text(encoding='utf-8'))['key']
    manifest = dict(schema=2, channel='private-candidate', profile='coreelec',
                    sequence=FIRST + 1, components=[dict(id=name) for name in NEW])
    return transition_value(key, manifest), manifest, trust(key, NEW)


def test_baseline_is_frozen_21_plus_one_and_same_public_key():
    value, manifest, pinned = pinned_contract()
    assert len(OLD) == 21 and len(NEW) == 22
    assert set(NEW) - set(OLD) == {'plugin.video.bobbi.torrent'}
    assert canonical_key_hash(pinned['key']) == driver.BASELINE_KEY_SHA256
    assert driver.validate_transition(value, 'a' * 64, manifest, pinned) == value


@pytest.mark.parametrize('field,bad', [
    ('schema', True), ('schema', 2), ('baseline_sequence', True),
    ('baseline_sequence', FIRST - 1), ('from_components', list(OLD[:-1])),
    ('from_components', list(reversed(OLD))), ('to_components', list(OLD)),
    ('to_components', list(NEW) + ['plugin.video.unapproved']),
    ('to_components', list(NEW[:-1]) + [NEW[0]]),
    ('candidate_sha256', 'b' * 64), ('candidate_sequence', True),
    ('candidate_sequence', FIRST), ('candidate_sequence', FIRST + 2),
])
def test_transition_rejects_changed_or_ambiguous_fields(field, bad):
    value, manifest, pinned = pinned_contract()
    value[field] = bad
    with pytest.raises(ValueError, match='CE_TRANSITION_'):
        driver.validate_transition(value, 'a' * 64, manifest, pinned)


@pytest.mark.parametrize('target', ['document', 'trust', 'both'])
@pytest.mark.parametrize('field,bad', [('algorithm', 'RSA-SHA256'), ('e', True),
                                     ('e', 3), ('n', 'f' * 768)])
def test_no_document_or_candidate_can_change_pinned_key(target, field, bad):
    value, manifest, pinned = pinned_contract()
    if target in ('document', 'both'):
        value['key'][field] = bad
    if target in ('trust', 'both'):
        pinned['key'][field] = bad
    with pytest.raises(ValueError, match='CE_TRANSITION_'):
        driver.validate_transition(value, 'a' * 64, manifest, pinned)


@pytest.mark.parametrize('change', ['extra', 'missing', 'trust_schema', 'trust_extra',
                                   'trust_inventory', 'manifest_profile', 'manifest_duplicate'])
def test_contract_has_exact_members_and_target_generation(change):
    value, manifest, pinned = pinned_contract()
    if change == 'extra':
        value['allow_extra_components'] = True
    elif change == 'missing':
        del value['key']
    elif change == 'trust_schema':
        pinned['schema'] = True
    elif change == 'trust_extra':
        pinned['extra'] = True
    elif change == 'trust_inventory':
        pinned['components'] = list(OLD)
    elif change == 'manifest_profile':
        manifest['profile'] = 'windows'
    elif change == 'manifest_duplicate':
        manifest['components'][-1] = dict(manifest['components'][0])
    with pytest.raises(ValueError, match='CE_TRANSITION_'):
        driver.validate_transition(value, 'a' * 64, manifest, pinned)


def setup_driver_trust(tmp_path, monkeypatch, pinned):
    path = tmp_path / 'driver/addons/script.module.bobbi.platform/lib/bobbi_platform/release_trust.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(pinned), encoding='utf-8')
    monkeypatch.setattr(driver, 'ROOT', tmp_path / 'driver')
    # Test-only private signer; production fingerprint is tested independently.
    monkeypatch.setattr(driver, 'BASELINE_KEY_SHA256', canonical_key_hash(pinned['key']))


def test_stage_preflight_checks_real_signature_full_inventory_and_frozen_bytes(releases, tmp_path, monkeypatch):
    setup_driver_trust(tmp_path, monkeypatch, releases['new_trust'])
    value = driver.transition_baseline(releases['new'])
    assert value['candidate_sha256'] == hashlib.sha256(releases['new'].read_bytes()).hexdigest()
    assert value['candidate_sequence'] == FIRST + 1
    assert value['from_components'] == list(OLD) and value['to_components'] == list(NEW)
    monkeypatch.setattr(driver, '_file_sha256', lambda _: '0' * 64)
    with pytest.raises(ValueError, match='CE_TRANSITION_BUNDLE_CHANGED'):
        driver.transition_baseline(releases['new'])


@pytest.mark.parametrize('changed', ['release.sig', 'component'])
def test_stage_preflight_cannot_publish_tampered_bundle(releases, tmp_path, monkeypatch, changed):
    setup_driver_trust(tmp_path, monkeypatch, releases['new_trust'])
    bad = tmp_path / 'tampered.zip'
    with zipfile.ZipFile(releases['new']) as source, zipfile.ZipFile(bad, 'w') as output:
        target = 'release.sig' if changed == 'release.sig' else source.namelist()[-1]
        for row in source.infolist():
            raw = source.read(row)
            if row.filename == target:
                raw = bytes([raw[0] ^ 1]) + raw[1:]
            output.writestr(row, raw)
    with pytest.raises(UpdateError):
        driver.transition_baseline(bad)
    assert not (driver.ROOT / 'review-evidence').exists()


def test_driver_rejects_transition_before_connecting_or_freezing_a_run(tmp_path, monkeypatch):
    from test_ce_deploy_controller import driver_harness
    current, calls, _, record, _ = driver_harness(tmp_path, monkeypatch, 'stage',
        (0, dict(state='staged'), 0))
    def rejected(_):
        raise ValueError('CE_TRANSITION_TRUST_CHANGED')
    monkeypatch.setattr(current, 'transition_baseline', rejected)
    with pytest.raises(ValueError, match='CE_TRANSITION_TRUST_CHANGED'):
        current.main()
    assert calls == [] and not record.exists()
    assert not record.with_suffix('.transition-baseline.json').exists()


def test_driver_cannot_upload_bytes_changed_after_transition_validation(tmp_path, monkeypatch):
    from test_ce_deploy_controller import driver_harness
    current, calls, _, record, _ = driver_harness(tmp_path, monkeypatch, 'stage',
        (0, dict(state='staged'), 0))
    def changed(path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_bytes(b'changed candidate bytes')
        return dict(candidate_sha256=digest)
    monkeypatch.setattr(current, 'transition_baseline', changed)
    with pytest.raises(ValueError, match='CE_TRANSITION_BUNDLE_CHANGED'):
        current.main()
    assert calls == [] and not record.exists()


def test_old_exact_21_client_rejects_new_22_without_changing_any_bytes(releases):
    legacy_apply(releases['old'], releases['old_trust'], releases['root'])
    before = files(releases['root'])
    with pytest.raises(UpdateError, match='extra offline package members'):
        legacy_apply(releases['new'], releases['old_trust'], releases['root'])
    assert files(releases['root']) == before


def test_historical_signed_21_to_22_to_21_preserves_profile_and_highwater(releases, tmp_path, signer):
    root = releases['root']
    legacy_apply(releases['old'], releases['old_trust'], root)
    before, profile = files(root / 'addons'), files(root / 'userdata')
    engine, result = legacy_apply(releases['new'], releases['new_trust'], root)
    assert set(result['versions']) == set(NEW)
    assert (root / 'addons' / driver.ADDED_COMPONENT).is_dir()
    restored = engine.rollback()
    assert restored == dict(sequence=FIRST + 1, versions=dict.fromkeys(OLD, '1.0.0'))
    assert files(root / 'addons') == before and files(root / 'userdata') == profile
    assert not (root / 'addons' / driver.ADDED_COMPONENT).exists()
    for path, pinned in ((releases['new'], releases['new_trust']),
                         (releases['old'], releases['old_trust'])):
        with pytest.raises(UpdateError, match='sequence'):
            legacy_apply(path, pinned, root)
        assert files(root / 'addons') == before and files(root / 'userdata') == profile
    # The restored old updater can start once the new controller fully settled
    # its journal, but must not reinterpret the 22-component previous receipt.
    old_engine = legacy_engine_for(releases['old_trust'], root)
    assert old_engine.available() == restored
    with pytest.raises(UpdateError, match='Previous program generation unavailable'):
        old_engine.rollback()
    assert files(root / 'addons') == before
    next_bundle = tmp_path / 'higher-sequence.zip'
    make_bundle(next_bundle, signer, NEW, FIRST + 2, '3.0.0')
    _, next_state = legacy_apply(next_bundle, releases['new_trust'], root)
    assert next_state['sequence'] == FIRST + 2 and set(next_state['versions']) == set(NEW)
    assert files(root / 'userdata') == profile


@pytest.mark.parametrize('cut', range(1, 44))
def test_each_historical_upgrade_move_interruption_recovers_exact_old_21(releases, cut):
    root = releases['root']
    legacy_apply(releases['old'], releases['old_trust'], root)
    before, profile = files(root / 'addons'), files(root / 'userdata')
    with SignedBundle(releases['new'], releases['new_trust'], 'coreelec') as source:
        engine = legacy_engine_for(releases['new_trust'], root, source)
        original, moved = engine._move, []
        def crash(src, dest):
            original(src, dest)
            moved.append(1)
            if len(moved) == cut:
                raise KeyboardInterrupt('simulated process interruption')
        engine._move = crash
        with pytest.raises(KeyboardInterrupt):
            engine.apply(source.raw, source.signature)
    assert (root / 'work/journal.json').is_file()
    # Today's owned-only controller must leave the historical transaction alone.
    stopped = files(root)
    current = rollback_engine(releases['new_trust'], 'coreelec', root / 'addons',
                              root / 'work', lambda: True, lease)
    with pytest.raises(UpdateError, match='frozen controller'):
        current.available()
    assert files(root) == stopped
    # The preserved full-22 controller, not either other updater, owns recovery.
    recovered = legacy_engine_for(releases['new_trust'], root).available()
    assert recovered == dict(sequence=FIRST, versions=dict.fromkeys(OLD, '1.0.0'))
    assert files(root / 'addons') == before and files(root / 'userdata') == profile
    assert not (root / 'addons' / driver.ADDED_COMPONENT).exists()
    assert not (root / 'work/journal.json').exists()


def test_historical_rollback_cleanup_requires_retained_full_22_controller(releases, monkeypatch):
    root = releases['root']
    legacy_apply(releases['old'], releases['old_trust'], root)
    before, profile = files(root / 'addons'), files(root / 'userdata')
    engine, _ = legacy_apply(releases['new'], releases['new_trust'], root)
    def interrupted(*_):
        raise KeyboardInterrupt('rollback committed; cleanup not yet completed')
    monkeypatch.setattr(engine, '_retain', interrupted)
    with pytest.raises(KeyboardInterrupt):
        engine.rollback()
    journal = json.loads(engine.journal_path.read_text())
    assert journal['phase'] == 'committed' and set(journal['entries']) == set(NEW)
    assert files(root / 'addons') == before and files(root / 'userdata') == profile
    interrupted_files = files(root)
    with pytest.raises(UpdateError, match='Invalid transaction journal'):
        legacy_engine_for(releases['old_trust'], root).available()
    assert files(root) == interrupted_files
    current = rollback_engine(releases['new_trust'], 'coreelec', root / 'addons',
                              root / 'work', lambda: True, lease)
    with pytest.raises(UpdateError, match='frozen controller'):
        current.available()
    assert files(root) == interrupted_files
    recovered = legacy_engine_for(releases['new_trust'], root).available()
    assert recovered == dict(sequence=FIRST + 1, versions=dict.fromkeys(OLD, '1.0.0'))
    assert not engine.journal_path.exists()
    assert files(root / 'addons') == before and files(root / 'userdata') == profile
    assert legacy_engine_for(releases['old_trust'], root).available() == recovered
    with pytest.raises(UpdateError, match='sequence'):
        legacy_apply(releases['new'], releases['new_trust'], root)


def test_new_inventory_does_not_reinterpret_unfinished_old_journal(releases):
    root = releases['root']
    before = files(root / 'addons')
    with SignedBundle(releases['old'], releases['old_trust'], 'coreelec') as source:
        engine = legacy_engine_for(releases['old_trust'], root, source)
        original = engine._move
        def crash(src, dest):
            original(src, dest)
            raise KeyboardInterrupt('unfinished 21-component transaction')
        engine._move = crash
        with pytest.raises(KeyboardInterrupt):
            engine.apply(source.raw, source.signature)
    stopped = files(root)
    with pytest.raises(UpdateError, match='Invalid transaction journal'):
        legacy_engine_for(releases['new_trust'], root).available()
    assert files(root) == stopped
    assert legacy_engine_for(releases['old_trust'], root).available() == dict(sequence=0, versions={})
    assert files(root / 'addons') == before


def test_current_signedbundle_policy_preserves_upstream_during_21_to_owned13_transition(releases):
    root = releases['root']
    legacy_apply(releases['old'], releases['old_trust'], root)
    before, profile = files(root / 'addons'), files(root / 'userdata')
    originals = {name: files(root / 'addons' / name) for name in UPSTREAM_COMPONENTS}
    with SignedBundle(releases['new'], releases['new_trust'], 'coreelec') as source:
        engine = source.engine(root / 'addons', root / 'work', lambda: True, lease)
        assert engine.expected == frozenset(NEW)
        assert engine.managed == OWNED_COMPONENTS
        result = engine.apply(source.raw, source.signature)
    assert result == dict(sequence=FIRST + 1, versions=dict.fromkeys(OWNED_COMPONENTS, '2.0.0'))
    assert {name: files(root / 'addons' / name) for name in UPSTREAM_COMPONENTS} == originals
    assert set(json.loads(engine.previous_path.read_text())['entries']) == OWNED_COMPONENTS
    restored = engine.rollback()
    assert restored == dict(sequence=FIRST + 1,
                            versions=dict.fromkeys(set(OLD) & OWNED_COMPONENTS, '1.0.0'))
    assert files(root / 'addons') == before and files(root / 'userdata') == profile
