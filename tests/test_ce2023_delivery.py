"""Real RSA/ZIP wrong-input controls over delivery_policy, SignedBundle, and ce_release_gate."""
import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle
from bobbi_platform.updates import UpdateError
import ce_release_gate
import delivery_policy as policy
from delivery_policy import DEFAULT_EMBEDDED_BUNDLE, EXCLUDE, require_clean, safe_members

INPUT_SEQUENCE = 2026102021


def zipped(files):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return stream.getvalue()


@pytest.fixture(scope='module')
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def make_signed_bundle(key, *, sequence=INPUT_SEQUENCE, profile='coreelec', channel='private-candidate',
                       corrupt=False, extra=False, mismatched_entry=False):
    component = 'plugin.video.bobbi'
    file = component + '/' + component + '-0.1.15.zip'
    blob = zipped({
        component + '/addon.xml': b'<addon id="plugin.video.bobbi" version="0.1.15"/>',
        component + '/license_state.py': b'answer = 42\n',
        component + '/fonts/notice.ttf': b'fixture-font',
    })
    row = dict(id=component, version='0.1.15', file=file, size=len(blob), sha256=policy.digest(blob))
    manifest = dict(schema=2, channel=channel, profile=profile, sequence=sequence, components=[row])
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    members = {
        'release.json': raw,
        'release.sig': base64.b64encode(key.sign(raw, padding.PKCS1v15(), hashes.SHA256())),
        file: blob + b'corrupt' if corrupt else blob,
    }
    if extra:
        members['extra'] = b'not signed'
    bundle = zipped(members)
    entry = zipped({
        DEFAULT_EMBEDDED_BUNDLE: bundle + b'changed' if mismatched_entry else bundle,
        'script.bobbi.start/default.py': b'# test entry\n',
    })
    numbers = key.public_key().public_numbers()
    trust = dict(schema=1, components=[component], key=dict(algorithm='RSA3072-SHA256', e=numbers.e, n=format(numbers.n, 'x')))
    return bundle, entry, trust


@pytest.mark.parametrize('name', ['LICENSE', 'fonts/LICENCE-X.txt', 'licenses/vendor/a.json', 'asset-' + 'provenance.md'])
def test_document_policy_positive(name):
    assert EXCLUDE.search(name)
    with pytest.raises(ValueError):
        require_clean([name])


@pytest.mark.parametrize('name', ['license_state.py', 'LICENSE.py', 'licenses/font.ttf', 'notice.wav', 'notice.ttf',
                                  'lib/attribution.xml', 'lib/notices.py', 'script/default.py'])
def test_policy_never_silently_excludes_runtime_assets(name):
    assert not EXCLUDE.search(name)
    require_clean([name])


@pytest.mark.parametrize('kwargs', [
    dict(sequence=True),
    dict(profile='windows'),
    dict(corrupt=True),
    dict(extra=True),
])
def test_signed_bundle_rejects_wrong_profile_sequence_type_corruption_or_unlisted_member(key, kwargs, tmp_path):
    bundle, _entry, trust = make_signed_bundle(key, **kwargs)
    bundle_path = tmp_path / 'bundle.zip'
    bundle_path.write_bytes(bundle)
    with pytest.raises((UpdateError, ValueError)):
        with SignedBundle(bundle_path, trust, 'coreelec') as signed:
            signed.check_all()


def test_wrong_trust_rejected_by_signed_bundle(key, tmp_path):
    bundle, _entry, trust = make_signed_bundle(key)
    another = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_numbers()
    trust['key']['n'] = format(another.n, 'x')
    bundle_path = tmp_path / 'bundle.zip'
    bundle_path.write_bytes(bundle)
    with pytest.raises(UpdateError):
        with SignedBundle(bundle_path, trust, 'coreelec') as signed:
            signed.check_all()


def test_entry_embedded_bundle_mismatch_and_unsafe_archive_members_rejected(key, tmp_path):
    bundle, bad_entry, trust = make_signed_bundle(key, mismatched_entry=True)
    bundle_path = tmp_path / 'bundle.zip'
    entry_path = tmp_path / 'entry.zip'
    bundle_path.write_bytes(bundle)
    entry_path.write_bytes(bad_entry)
    with SignedBundle(bundle_path, trust, 'coreelec') as signed:
        assert signed.check_all()['sequence'] == INPUT_SEQUENCE
    with zipfile.ZipFile(entry_path) as archive:
        list(safe_members(archive))
        assert policy.digest(archive.read(DEFAULT_EMBEDDED_BUNDLE)) != policy.digest(bundle)

    traversal = BytesIO()
    with zipfile.ZipFile(traversal, 'w') as z:
        z.writestr('../escape.txt', b'x')
    with zipfile.ZipFile(BytesIO(traversal.getvalue())) as bad_zip:
        with pytest.raises(ValueError, match='Unsafe'):
            list(safe_members(bad_zip))


def test_release_gate_prepare_failure_never_publishes_output_receipt(tmp_path):
    receipt_out = tmp_path / 'receipt.json'
    gh_meta = tmp_path / 'release.json'
    gh_meta.write_text(json.dumps({'prerelease': False, 'draft': True, 'target_commitish': '0' * 40}), encoding='utf-8')
    with pytest.raises(ValueError):
        ce_release_gate.prepare(
            bundle=tmp_path / 'missing-bundle.zip',
            entry=tmp_path / 'missing-entry.zip',
            component_assets=None,
            feeds={'github': tmp_path, 'gitcode': tmp_path},
            output=receipt_out,
            track='stable',
            github_release=gh_meta,
            source_checks=(tmp_path / 's1', tmp_path / 's2'),
        )
    assert not receipt_out.exists()


@pytest.mark.parametrize('value', [2026102014, 2026102021, 2026102022, 2026102023, True])
def test_sequence_registry_collision_rejected(value):
    with pytest.raises(ValueError):
        policy.checked_sequence(value, dict(allocated=[2026102023]))


def test_retired_ce2021_repackage_orchestration_absent_from_delivery_policy():
    for retired in (
        'validate_signed_delivery_input',
        'patch_without_excluded',
        'clean_archive',
        'check_nested',
        'inventory',
        'repackage_signed_delivery',
        'stage_verified_repackage',
    ):
        assert not hasattr(policy, retired), retired
