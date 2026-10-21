"""Prepare a document-cleaned CE2021 handoff; never deploy or replace trust."""
import argparse
import base64
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust

EXCLUDE = re.compile(
    r'(^|/)(licenses?(/|$)|[^/]*(copyright|licen[cs]e|notice|copying|'
    r'attribution|asset-provenance|upstream-asset-provenance|third.party.audit|'
    r'third.party)([^/]*\.(md|txt|json)|$))', re.I)
REPORT = 'docs/CE-REVIEW-CLOSURE-2021-20261021.md'
BUNDLE = 'installers/bobbi-private-2026102021-coreelec.bobbi-update.zip'
ENTRY = 'installers/script.bobbi.start-0.2.13-ce2021.zip'
EMBEDDED = 'script.bobbi.start/resources/complete.bobbi-update.zip'
SEQUENCE = 2026102022


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def safe_members(archive):
    seen = set()
    for item in archive.infolist():
        name = item.filename
        path = PurePosixPath(name)
        if (name in seen or path.is_absolute() or '..' in path.parts or
                '\\' in name or ':' in name or item.flag_bits & 1):
            raise ValueError('Unsafe or duplicate archive member')
        seen.add(name)
        yield item


def patch_without_excluded(raw):
    chunks = re.split(rb'(?m)(?=^diff --git )', raw)
    kept = []
    for chunk in chunks:
        first = chunk.split(b'\n', 1)[0].decode('utf-8', 'replace')
        if first.startswith('diff --git '):
            paths = first[len('diff --git '):].split(' b/', 1)
            if any(EXCLUDE.search(p.removeprefix('a/').strip('"')) for p in paths):
                continue
        kept.append(chunk)
    return b''.join(kept)


def clean_archive(raw, label, removed, replacements=None, depth=0):
    if depth > 10:
        raise ValueError('Archive nesting limit')
    replacements = replacements or {}
    output = BytesIO()
    changed = False
    with zipfile.ZipFile(BytesIO(raw)) as source, zipfile.ZipFile(output, 'w') as target:
        names = set(source.namelist())
        if {'release.json', 'release.sig'} <= names:
            raise ValueError('Signed payload must go through explicit resigning')
        for item in safe_members(source):
            name = item.filename
            if EXCLUDE.search(name):
                removed.append(label + '!' + name)
                changed = True
                continue
            blob = source.read(item)
            new_blob = replacements.get(name, blob)
            if name not in replacements and not item.is_dir():
                if name.lower().endswith('.apk'):
                    raise ValueError('APK requires a separate Android signing workflow')
                if name.lower().endswith('.zip'):
                    new_blob = clean_archive(blob, label + '!' + name, removed, depth=depth + 1)
                elif name.endswith('.patch'):
                    new_blob = patch_without_excluded(blob)
            changed |= new_blob != blob
            target.writestr(copy.copy(item), new_blob)
    return output.getvalue() if changed else raw


def check_nested(raw, label, depth=0):
    if depth > 10:
        raise ValueError('Archive nesting limit')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity failed')
        for item in safe_members(archive):
            if EXCLUDE.search(item.filename):
                raise ValueError('Excluded document remains in ' + label)
            if not item.is_dir() and item.filename.lower().endswith('.zip'):
                check_nested(archive.read(item), label + '!' + item.filename, depth + 1)


def inventory(blob):
    """Fingerprint non-document files recursively, independent of ZIP bytes."""
    result = {}
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        for item in safe_members(archive):
            if item.is_dir() or EXCLUDE.search(item.filename):
                continue
            raw = archive.read(item)
            if item.filename.lower().endswith('.zip'):
                for key, value in inventory(raw).items():
                    result[item.filename + '!' + key] = value
            else:
                result[item.filename] = digest(raw)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--input', type=Path, default=ROOT / 'dist/ce2021-local-delivery-20261021.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/ce2021-clean-delivery-20261021')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output already exists; originals are never overwritten')
    trust = load_trust()
    private = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
    numbers = private.public_key().public_numbers()
    if numbers.n != int(trust['key']['n'], 16) or numbers.e != trust['key']['e']:
        raise ValueError('Original pinned maintainer key required')
    original = args.input.read_bytes()
    with zipfile.ZipFile(BytesIO(original)) as delivery:
        original_bundle = delivery.read(BUNDLE)
        original_entry = delivery.read(ENTRY)
        with zipfile.ZipFile(BytesIO(original_entry)) as entry:
            if entry.read(EMBEDDED) != original_bundle:
                raise ValueError('Entry and standalone generation differ')
        with zipfile.ZipFile(BytesIO(original_bundle)) as source:
            raw = source.read('release.json')
            from bobbi_platform.signatures import verify
            if not verify(raw, source.read('release.sig').decode('ascii'), trust['key']):
                raise ValueError('Input signature rejected')
            manifest = json.loads(raw)
            if manifest['sequence'] >= SEQUENCE:
                raise ValueError('New unique sequence required')
            if manifest['profile'] != 'coreelec' or manifest['channel'] != 'private-candidate':
                raise ValueError('Only the existing CE candidate may be repackaged')
            expected = {'release.json', 'release.sig'} | {r['file'] for r in manifest['components']}
            if set(source.namelist()) != expected:
                raise ValueError('Original generation membership differs')
            cleaned_components = []
            removed = []
            for row in manifest['components']:
                blob = source.read(row['file'])
                if digest(blob) != row['sha256'] or len(blob) != row['size']:
                    raise ValueError('Input component failed integrity')
                cleaned = clean_archive(blob, BUNDLE + '!' + row['file'], removed)
                if inventory(blob) != inventory(cleaned):
                    raise ValueError('Non-document component data changed')
                row['sha256'], row['size'] = digest(cleaned), len(cleaned)
                cleaned_components.append((row['file'], cleaned))
        manifest['sequence'] = SEQUENCE
        signed_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        signature = base64.b64encode(private.sign(signed_raw, padding.PKCS1v15(), hashes.SHA256()))
        bundle_stream = BytesIO()
        with zipfile.ZipFile(bundle_stream, 'w', compression=zipfile.ZIP_STORED) as target:
            for name, blob in [('release.json', signed_raw), ('release.sig', signature)] + cleaned_components:
                target.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), blob)
        bundle = bundle_stream.getvalue()
        entry = clean_archive(original_entry, ENTRY, removed, {EMBEDDED: bundle})
        old_bootstrap = inventory(original_entry)
        new_bootstrap = inventory(entry)
        prefix = EMBEDDED + '!'
        if ({k: v for k, v in old_bootstrap.items() if not k.startswith(prefix)} !=
                {k: v for k, v in new_bootstrap.items() if not k.startswith(prefix)}):
            raise ValueError('Installer bootstrap code changed')
        args.output.mkdir(parents=True)
        bundle_path = args.output / 'bobbi-private-2026102022-coreelec.bobbi-update.zip'
        entry_path = args.output / 'script.bobbi.start-0.2.13-ce2021-clean.zip'
        bundle_path.write_bytes(bundle)
        entry_path.write_bytes(entry)
        with SignedBundle(bundle_path, trust, 'coreelec') as checked:
            checked.check_all()
        report = (ROOT / REPORT).read_bytes()
        replacements = {BUNDLE: bundle, ENTRY: entry, REPORT: report}
        outer = BytesIO()
        records = []
        with zipfile.ZipFile(outer, 'w') as output:
            for item in safe_members(delivery):
                name = item.filename
                if EXCLUDE.search(name):
                    removed.append('delivery!' + name)
                    continue
                if name == 'MANIFEST.json':
                    continue
                blob = replacements.get(name)
                if blob is None:
                    blob = delivery.read(item)
                    if name.lower().endswith('.zip'):
                        blob = clean_archive(blob, name, removed)
                    elif name.endswith('.patch'):
                        blob = patch_without_excluded(blob)
                if name == 'README.md':
                    blob = ('# CE2021 GitHub cleaned delivery\n\n'
                            'Document-cleaned derivative; original maintainer trust, sequence 2026102022.\n'
                            'Installers retain their original internal paths and component versions.\n'
                            'Read docs/CE-REVIEW-CLOSURE-2021-20261021.md for historical device-test limits.\n'
                            'Signing/ZIP checks are not a new device or source-build certification.\n').encode()
                output.writestr(copy.copy(item), blob)
                records.append(dict(path=name, bytes=len(blob), sha256=digest(blob)))
            metadata = dict(schema=2, sequence=SEQUENCE, original_delivery_sha256=digest(original),
                            original_sequence=2026102021, components=len(cleaned_components),
                            excluded_document_entries=len(removed), signature='original pinned maintainer key',
                            non_document_component_files='byte-identical', current_source_build='not rerun; previous failure remains',
                            device_test='original pre-cleanup evidence only; no deployment', files=records)
            output.writestr('MANIFEST.json', json.dumps(metadata, ensure_ascii=False, indent=2).encode())
        handoff = outer.getvalue()
        check_nested(handoff, 'delivery')
        (args.output / args.input.name.replace('local-delivery', 'clean-delivery')).write_bytes(handoff)
        (args.output / Path(REPORT).name).write_bytes(report)
        result = dict(sequence=SEQUENCE, removed_entries=len(removed), components=len(cleaned_components),
                      original_key_verified=True, signature_verified=True, nested_zip_verified=True,
                      non_document_files_unchanged=True, device_deployed=False,
                      assets=[dict(name=p.name, bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
                              for p in sorted(args.output.iterdir()) if p.is_file()])
        (args.output / 'packaging-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
