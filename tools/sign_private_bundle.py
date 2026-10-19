"""Maintainer-only RSA signing. Never ships private keys or account data."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, MAX_BUNDLE
from bobbi_platform.updates import MAX_ARCHIVE, MAX_MANIFEST, _safe_path


def checked_components(directory, built, trust):
    """Validate every member before reading, then retain exactly checked bytes."""
    directory = _safe_path(directory)
    rows = built.get('components') if isinstance(built, dict) else None
    expected = set(trust['components'])
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('Component inventory differs from pinned complete generation')
    seen, validated = set(), []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'version', 'file', 'bytes', 'sha256'}
                or not isinstance(row['id'], str) or row['id'] not in expected or row['id'] in seen
                or not isinstance(row['version'], str)
                or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[+~-][A-Za-z0-9._-]{1,64})?', row['version'])
                or row['file'] != row['id'] + '/' + row['id'] + '-' + row['version'] + '.zip'
                or type(row['bytes']) is not int or not 0 < row['bytes'] <= MAX_ARCHIVE
                or not isinstance(row['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', row['sha256'])):
            raise ValueError('Invalid built component metadata')
        target = _safe_path(directory / row['file'])
        if directory not in target.parents or not target.is_file() or target.stat().st_size != row['bytes']:
            raise ValueError('Built component path or length rejected')
        seen.add(row['id'])
        validated.append((dict(row), target))
    if seen != expected or sum(row['bytes'] for row, _ in validated) > MAX_BUNDLE - 2*MAX_MANIFEST:
        raise ValueError('Complete built generation exceeds budget')
    checked = []
    for row, target in validated:
        # Bounded read + retained bytes closes mutation between signing and ZIP
        # creation. Never reread a member after its hash has been signed.
        with target.open('rb') as stream:
            blob = stream.read(row['bytes'] + 1)
        if len(blob) != row['bytes'] or hashlib.sha256(blob).hexdigest() != row['sha256']:
            raise ValueError('Built component changed before signing')
        checked.append((row, blob))
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--create-key', action='store_true')
    parser.add_argument('--components', type=Path)
    parser.add_argument('--profile', choices=('coreelec', 'windows', 'android'))
    parser.add_argument('--sequence', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    trust_path = ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/release_trust.json'
    if args.create_key:
        if args.key.exists() or trust_path.exists():
            raise ValueError('Existing trust key must never be silently replaced')
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        args.key.parent.mkdir(parents=True, exist_ok=True)
        # Caller applies the per-user Windows ACL immediately after generation.
        with args.key.open('xb') as stream:
            stream.write(private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        args.key.chmod(0o600)
        numbers = private.public_key().public_numbers()
        from build_release import sources
        trust = dict(schema=1, key=dict(algorithm='RSA3072-SHA256', n=format(numbers.n, 'x'), e=numbers.e),
                     components=sorted(sources()))
        trust_path.write_text(json.dumps(trust, indent=2) + '\n', encoding='utf-8')
        print('Created private maintainer key and public verification inventory; no secret output.')
        return
    if not all((args.components, args.profile, args.sequence, args.output)) or args.sequence < 1:
        parser.error('Signing requires components/profile/positive sequence/output')
    private = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
    trust = json.loads(trust_path.read_text(encoding='utf-8'))
    numbers = private.public_key().public_numbers()
    if numbers.n != int(trust['key']['n'], 16) or numbers.e != trust['key']['e']:
        raise ValueError('Signing key differs from pinned trust')
    built = json.loads((args.components / 'manifest.json').read_text(encoding='utf-8'))
    checked = checked_components(args.components, built, trust)
    manifest = dict(schema=2, channel='private-candidate', profile=args.profile,
                    sequence=args.sequence, components=[])
    for row, blob in checked:
        manifest['components'].append(dict(id=row['id'], version=row['version'], file=row['file'],
                                          size=row['bytes'], sha256=row['sha256']))
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    signature = base64.b64encode(private.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'x', compression=zipfile.ZIP_STORED) as target:
        for name, content in [('release.json', raw), ('release.sig', signature)]:
            target.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), content)
        for row, blob in checked:
            target.writestr(zipfile.ZipInfo(row['file'], (1980, 1, 1, 0, 0, 0)),
                           blob)
    with SignedBundle(args.output, trust, args.profile) as bundle:
        bundle.check_all()
    print('Signed and independently verified offline complete generation:', len(manifest['components']))


if __name__ == '__main__':
    main()
