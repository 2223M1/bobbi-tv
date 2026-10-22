"""Real RSA/ZIP wrong-input controls; no production signing key or device."""
import base64
import copy
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import package_ce2021_github as pack
from delivery_policy import EXCLUDE, require_clean


def zipped(files):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return stream.getvalue()


@pytest.fixture(scope='module')
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def fixture(key, sequence=2026102021, profile='coreelec', channel='private-candidate',
            corrupt=False, extra=False, mismatched_entry=False):
    component = 'plugin.video.bobbi'
    file = component+'/'+component+'-0.1.15.zip'
    blob = zipped({component+'/addon.xml':b'<addon id="plugin.video.bobbi" version="0.1.15"/>',
                  component+'/license_state.py':b'answer = 42\n',
                  component+'/NOTICE.txt':b'test document',
                  component+'/fonts/notice.ttf':b'fixture-font'})
    row = dict(id=component, version='0.1.15', file=file, size=len(blob), sha256=pack.digest(blob))
    manifest = dict(schema=2, channel=channel, profile=profile, sequence=sequence, components=[row])
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    members = {'release.json':raw, 'release.sig':base64.b64encode(key.sign(raw, padding.PKCS1v15(), hashes.SHA256())),
               file:blob+b'corrupt' if corrupt else blob}
    if extra:
        members['extra'] = b'not signed'
    bundle = zipped(members)
    entry = zipped({pack.EMBEDDED:bundle+b'changed' if mismatched_entry else bundle,
                    'script.bobbi.start/default.py':b'# test entry\n',
                    'script.bobbi.start/bootstrap/LICENSE':b'fixture notice'})
    files = {pack.BUNDLE:bundle, pack.ENTRY:entry, pack.REPORT:b'fixture report'}
    records = [dict(path=k, bytes=len(v), sha256=pack.digest(v)) for k,v in files.items()]
    files['MANIFEST.json'] = json.dumps(dict(schema=1, files=records)).encode()
    outer = zipped(files)
    identity = dict(sequence=2026102021, components=[row], outer_sha256=pack.digest(outer),
                    payload_sha256=pack.digest(bundle), entry_sha256=pack.digest(entry))
    numbers = key.public_key().public_numbers()
    trust = dict(schema=1, components=[component], key=dict(algorithm='RSA3072-SHA256', e=numbers.e, n=format(numbers.n,'x')))
    return outer, identity, trust


@pytest.mark.parametrize('name', ['LICENSE', 'fonts/LICENCE-X.txt', 'licenses/vendor/a.json', 'asset-provenance.md'])
def test_document_policy_positive(name):
    assert EXCLUDE.search(name)
    with pytest.raises(ValueError):
        require_clean([name])


@pytest.mark.parametrize('name', ['license_state.py','LICENSE.py','licenses/font.ttf','notice.wav','notice.ttf',
                                 'lib/attribution.xml','lib/notices.py','script/default.py'])
def test_policy_never_silently_excludes_runtime_assets(name):
    assert not EXCLUDE.search(name)
    require_clean([name])


@pytest.mark.parametrize('kwargs', [dict(sequence=2026102014), dict(sequence=2026102022),
    dict(sequence=2026102023), dict(sequence=True), dict(profile='windows'),
    dict(channel='private-stable'), dict(corrupt=True), dict(extra=True), dict(mismatched_entry=True)])
def test_wrong_signed_input_rejected_even_if_hashes_pinned(key, kwargs):
    outer, identity, trust = fixture(key, **kwargs)
    with pytest.raises(ValueError):
        pack.validate_input(outer, identity, trust)


@pytest.mark.parametrize('field', ['outer_sha256','payload_sha256','entry_sha256','components'])
def test_pins_not_advisory(key, field):
    outer, identity, trust = fixture(key)
    identity[field] = [] if field == 'components' else '0'*64
    with pytest.raises(ValueError):
        pack.validate_input(outer, identity, trust)


def test_wrong_trust_rejected(key):
    outer, identity, trust = fixture(key)
    another = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_numbers()
    trust['key']['n'] = format(another.n, 'x')
    with pytest.raises(ValueError):
        pack.validate_input(outer, identity, trust)


def test_outer_manifest_and_members_checked(key):
    outer, identity, trust = fixture(key)
    with zipfile.ZipFile(BytesIO(outer)) as z:
        members = {n:z.read(n) for n in z.namelist()}
    members['unlisted.txt'] = b'x'
    outer = zipped(members)
    identity['outer_sha256'] = pack.digest(outer)
    with pytest.raises(ValueError, match='membership'):
        pack.validate_input(outer, identity, trust)


def test_exact_input_clean_output_signed_and_truthful(key, tmp_path):
    outer, identity, trust = fixture(key)
    manifest, bundle, entry = pack.validate_input(outer, identity, trust)
    out = tmp_path/'out'
    result = pack.repackage(outer, manifest, bundle, entry, key, trust, 2026102023, out, 'fixture.zip')
    with pack.SignedBundle(out/'bobbi-private-2026102023-coreelec.bobbi-update.zip', trust, 'coreelec') as signed:
        assert signed.check_all()['sequence'] == 2026102023
        row = signed.manifest['components'][0]
        with zipfile.ZipFile(BytesIO(signed.read(row['file'], row['size']))) as component:
            assert component.read('plugin.video.bobbi/license_state.py') == b'answer = 42\n'
            assert component.read('plugin.video.bobbi/fonts/notice.ttf') == b'fixture-font'
    assert result['original_sequence'] == 2026102021
    with zipfile.ZipFile(out/'ce2021-clean-2026102023.zip') as z:
        meta = json.loads(z.read('MANIFEST.json'))
        assert z.read(pack.REPORT) == b'fixture report'
    assert (out / Path(pack.REPORT).name).read_bytes() == b'fixture report'
    assert meta['original_payload_sha256'] == identity['payload_sha256']
    removals = json.loads((out/'REMOVAL-MANIFEST.json').read_text())['entries']
    assert len(removals) == 2 and all(len(r['sha256']) == 64 for r in removals)


def test_output_failure_never_publishes_final_directory(key, tmp_path, monkeypatch):
    outer, identity, trust = fixture(key)
    inp, ident, registry, pem = [tmp_path/name for name in ('in.zip','identity.json','registry.json','fixture.pem')]
    inp.write_bytes(outer); ident.write_text(json.dumps(identity)); registry.write_text(json.dumps(dict(allocated=[2026102022])))
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    monkeypatch.setattr(pack, 'load_trust', lambda:trust)
    def failure(*args, **kwargs):
        raise ValueError('injected final verification failure')
    monkeypatch.setattr(pack, 'check_nested', failure)
    dest = tmp_path/'final'
    monkeypatch.setattr(sys, 'argv', ['pack','--input',str(inp),'--identity',str(ident),'--registry',str(registry),
        '--key',str(pem),'--sequence','2026102023','--output',str(dest)])
    with pytest.raises(ValueError, match='injected'):
        pack.main()
    assert not dest.exists()


@pytest.mark.parametrize('value', [2026102014,2026102021,2026102022,2026102023,True])
def test_sequence_registry_collision_rejected(value):
    with pytest.raises(ValueError):
        pack.checked_sequence(value, dict(allocated=[2026102023]))


def test_patch_removal_records_whole_block_without_removing_code():
    raw = b'diff --git a/LICENSE b/LICENSE\n+test\ndiff --git a/license_state.py b/license_state.py\n+x=1\n'
    removed = []
    result = pack.patch_without_excluded(raw, removed)
    assert result == b'diff --git a/license_state.py b/license_state.py\n+x=1\n'
    assert len(removed) == 1 and removed[0]['category'] == 'document-patch-block'
