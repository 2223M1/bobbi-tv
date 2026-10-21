"""Verify the independent review package manifest (stdlib only, read-only)."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1:
        raise ValueError('Unsupported manifest schema')
    expected = set()
    for row in manifest['files']:
        relative = PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or row['path'] in expected:
            raise ValueError('Invalid or duplicate manifest path')
        expected.add(row['path'])
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError('Missing or unsafe file: ' + row['path'])
        raw = path.read_bytes()
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('File integrity mismatch: ' + row['path'])
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != expected | {'MANIFEST.json', 'SHA256SUMS.txt'}:
        raise ValueError('Unexpected or missing package members')
    checksum_rows = (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()
    checksummed = set()
    for line in checksum_rows:
        digest, name = line.split('  ', 1)
        if name not in expected | {'MANIFEST.json'} or name in checksummed:
            raise ValueError('Invalid checksum entry')
        checksummed.add(name)
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Checksum mismatch: ' + name)
    if checksummed != expected | {'MANIFEST.json'}:
        raise ValueError('Incomplete checksum list')
    print(json.dumps({'verified': True, 'payload_files': len(expected),
                      'package_files': len(actual), 'head': manifest['reviewed_head']}))


if __name__ == '__main__':
    main()
