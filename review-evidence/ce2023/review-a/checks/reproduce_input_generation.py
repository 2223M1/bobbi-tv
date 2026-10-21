#!/usr/bin/env python3
"""Exercise the real CE2021 packager with temporary RSA-signed fixture inputs.

No production key, release asset, repository file, device, or network is used.
The only injected boundary is load_trust(), pointed at a temporary test key.
The packager, manifest verifier, ZIP handling, and signature checks are real.
Exit 1 means a product assertion failed; exit 2 means the harness errored.
"""
import argparse
import base64
import contextlib
import hashlib
import importlib.util
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def zipped(members):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, value in members.items():
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), value)
    return stream.getvalue()


def make_input(module, key, sequence, profile='coreelec'):
    component = 'plugin.video.bobbi'
    version = '0.1.15'
    blob = zipped({
        component + '/addon.xml': ('<addon id="' + component + '" version="' + version + '"/>').encode(),
        component + '/fixture.py': b'FIXTURE_ONLY = True\n',
        component + '/NOTICE.txt': b'Fixture document only.\n',
    })
    filename = component + '/' + component + '-' + version + '.zip'
    manifest = dict(schema=2, channel='private-candidate', profile=profile,
                    sequence=sequence, components=[dict(
                        id=component, version=version, file=filename, size=len(blob),
                        sha256=hashlib.sha256(blob).hexdigest())])
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    signature = base64.b64encode(key.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    bundle = zipped({'release.json': raw, 'release.sig': signature, filename: blob})
    entry = zipped({
        'script.bobbi.start/addon.xml': b'<addon id="script.bobbi.start" version="0.2.13"/>',
        'script.bobbi.start/default.py': b'# fixture bootstrap\n',
        module.EMBEDDED: bundle,
    })
    outer = zipped({module.BUNDLE: bundle, module.ENTRY: entry,
                    module.REPORT: b'Fixture input report; replaced by repository report.\n',
                    'README.md': b'Fixture input.\n'})
    return outer, bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        actual_commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
            check=True, capture_output=True, text=True).stdout.strip()
        # A parent directory's repository does not identify this source snapshot.
        top = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'],
            check=True, capture_output=True, text=True).stdout.strip()
        if Path(top).resolve() != repo:
            actual_commit = None
    except (OSError, subprocess.CalledProcessError):
        actual_commit = None
    module_path = repo / 'tools/package_ce2021_github.py'
    spec = importlib.util.spec_from_file_location('review_ce2021_packager', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = key.public_key().public_numbers()
    trust = dict(schema=1, key=dict(algorithm='RSA3072-SHA256', e=65537,
                                   n=format(numbers.n, 'x')),
                 components=['plugin.video.bobbi'])
    saved_trust, saved_argv = module.load_trust, sys.argv[:]
    module.load_trust = lambda: trust
    cases = []
    try:
        with tempfile.TemporaryDirectory(prefix='ce2021-packager-fixtures-') as work:
            root = Path(work)
            pem = root / 'temporary-fixture-key.pem'
            pem.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            pem.chmod(0o600)
            for case_id, sequence, profile, wrong_key, should_accept in [
                ('exact_ce2021_input', 2026102021, 'coreelec', False, True),
                ('earlier_signed_generation_must_be_rejected', 2026102014, 'coreelec', False, False),
                ('non_increasing_sequence_rejected', 2026102022, 'coreelec', False, False),
                ('wrong_profile_rejected', 2026102021, 'windows', False, False),
                ('untrusted_input_signature_rejected', 2026102021, 'coreelec', True, False),
            ]:
                row = dict(case=case_id, input_sequence=sequence, expected_accepted=should_accept)
                try:
                    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=3072) if wrong_key else key
                    outer, bundle = make_input(module, signing_key, sequence, profile)
                    case_root = root / case_id
                    case_root.mkdir()
                    input_path = case_root / 'ce2021-local-delivery-20261021.zip'
                    input_path.write_bytes(outer)
                    original_path = case_root / 'fixture-original-bundle.zip'
                    original_path.write_bytes(bundle)
                    if not wrong_key:
                        with module.SignedBundle(original_path, trust, profile) as signed:
                            row['input_actual_signed_bundle_check'] = signed.check_all()['sequence']
                    out = case_root / 'out'
                    sys.argv = [str(module_path), '--key', str(pem), '--input', str(input_path), '--output', str(out)]
                    try:
                        with contextlib.redirect_stdout(StringIO()):
                            module.main()
                        row['accepted'] = True
                    except ValueError as exc:
                        row.update(accepted=False, rejection=str(exc))
                    if row['accepted']:
                        with module.SignedBundle(out / 'bobbi-private-2026102022-coreelec.bobbi-update.zip', trust, 'coreelec') as signed:
                            row['output_actual_signed_bundle_check'] = signed.check_all()['sequence']
                        with zipfile.ZipFile(out / 'ce2021-clean-delivery-20261021.zip') as cleaned:
                            metadata = json.loads(cleaned.read('MANIFEST.json'))
                        result = json.loads((out / 'packaging-result.json').read_text())
                        row.update(reported_original_sequence=metadata['original_sequence'],
                                   original_sequence_truthful=metadata['original_sequence'] == sequence,
                                   signature_verified_flag=result['signature_verified'],
                                   non_document_unchanged_flag=result['non_document_files_unchanged'])
                    row['status'] = 'pass' if row['accepted'] == should_accept else 'fail'
                except Exception as exc:
                    row.update(status='error', error_type=type(exc).__name__, error=str(exc))
                cases.append(row)
    finally:
        module.load_trust, sys.argv = saved_trust, saved_argv
    result = dict(
        schema=1,
        scope='CE2021-only repackager input generation contract; synthetic signed fixture, not release bytes',
        review_reference_commit='b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2',
        actual_checkout_commit=actual_commit,
        module_sha256=hashlib.sha256(module_path.read_bytes()).hexdigest(),
        fixture_boundaries=['load_trust replaced with temporary test trust; no production key accessed',
                            'single-component valid signed input; real SignedBundle and real signing used'],
        cases=cases,
        totals={name: sum(row['status'] == name for row in cases) for name in ['pass', 'fail', 'error']})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['totals']['error'] else (1 if result['totals']['fail'] else 0)


if __name__ == '__main__':
    sys.exit(main())
