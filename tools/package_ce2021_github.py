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
import tempfile
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust
from bobbi_platform.updates import UpdateError
from delivery_policy import EXCLUDE, POLICY

REPORT = 'docs/CE-REVIEW-CLOSURE-2021-20261021.md'
BUNDLE = 'installers/bobbi-private-2026102021-coreelec.bobbi-update.zip'
ENTRY = 'installers/script.bobbi.start-0.2.13-ce2021.zip'
EMBEDDED = 'script.bobbi.start/resources/complete.bobbi-update.zip'
INPUT_SEQUENCE = 2026102021


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


def patch_without_excluded(raw, removed=None, label='patch'):
    chunks = re.split(rb'(?m)(?=^diff --git )', raw)
    kept = []
    for chunk in chunks:
        first = chunk.split(b'\n', 1)[0].decode('utf-8', 'replace')
        if first.startswith('diff --git '):
            paths = first[len('diff --git '):].split(' b/', 1)
            if any(EXCLUDE.search(p.removeprefix('a/').strip('"')) for p in paths):
                if removed is not None:
                    removed.append(dict(archive=label, path=first, sha256=digest(chunk),
                        bytes=len(chunk), rule=POLICY, category='document-patch-block'))
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
                blob = source.read(item)
                removed.append(dict(archive=label, path=name, sha256=digest(blob),
                    bytes=len(blob), rule=POLICY, category='standalone-document'))
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
                    new_blob = patch_without_excluded(blob, removed, label + '!' + name)
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


def validate_input(original, identity, trust):
    """Explicit caller-pinned bytes AND the production signed contract, before edits."""
    if (not isinstance(identity, dict) or identity.get('sequence') != INPUT_SEQUENCE or
            type(identity.get('sequence')) is not int or
            not isinstance(identity.get('components'), list) or
            any(not isinstance(identity.get(k), str) or not re.fullmatch('[a-f0-9]{64}', identity[k])
                for k in ('outer_sha256', 'payload_sha256', 'entry_sha256'))):
        raise ValueError('Explicit exact CE2021 input identity required')
    if digest(original) != identity['outer_sha256']:
        raise ValueError('Frozen outer input differs')
    with zipfile.ZipFile(BytesIO(original)) as delivery:
        list(safe_members(delivery))
        table = json.loads(delivery.read('MANIFEST.json'))
        rows = table.get('files') if isinstance(table, dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Original outer manifest required')
        expected = {r['path']: r for r in rows}
        if len(expected) != len(rows) or set(delivery.namelist()) != set(expected) | {'MANIFEST.json'}:
            raise ValueError('Original outer membership differs')
        for name, row in expected.items():
            blob = delivery.read(name)
            if type(row['bytes']) is not int or len(blob) != row['bytes'] or digest(blob) != row['sha256']:
                raise ValueError('Original outer member integrity failed')
        bundle, entry = delivery.read(BUNDLE), delivery.read(ENTRY)
    if digest(bundle) != identity['payload_sha256'] or digest(entry) != identity['entry_sha256']:
        raise ValueError('Frozen payload or entry input differs')
    with zipfile.ZipFile(BytesIO(entry)) as archive:
        list(safe_members(archive))
        if archive.read(EMBEDDED) != bundle:
            raise ValueError('Entry and standalone generation differ')
    with tempfile.TemporaryDirectory(prefix='ce2021-checked-input-') as temp:
        path = Path(temp)/'bundle.zip'
        path.write_bytes(bundle)
        try:
            with SignedBundle(path, trust, 'coreelec') as signed:
                manifest = copy.deepcopy(signed.check_all())
        except UpdateError as exc:
            raise ValueError('Input signed contract rejected: ' + str(exc)) from None
    if manifest['sequence'] != INPUT_SEQUENCE or manifest['channel'] != 'private-candidate':
        raise ValueError('Only the exact signed CE2021 candidate may be repackaged')
    if sorted(manifest['components'], key=lambda r:r['id']) != sorted(identity['components'], key=lambda r:r['id']):
        raise ValueError('Frozen component identities differ')
    return manifest, bundle, entry


def checked_sequence(value, registry):
    used = registry.get('allocated') if isinstance(registry, dict) else None
    if (type(value) is not int or not isinstance(used, list) or not used or
            any(type(n) is not int or n < 1 for n in used) or
            value <= max([INPUT_SEQUENCE, 2026102022] + used)):
        raise ValueError('New sequence above verified release registry required')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--input', type=Path, default=ROOT / 'dist/ce2021-local-delivery-20261021.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/ce2021-clean-delivery-20261021')
    parser.add_argument('--identity', type=Path, default=ROOT / 'release/ce2021-input-lock.json')
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output already exists; originals are never overwritten')
    sequence = checked_sequence(args.sequence, json.loads(args.registry.read_text(encoding='utf-8')))
    trust = load_trust()
    private = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
    numbers = private.public_key().public_numbers()
    if numbers.n != int(trust['key']['n'], 16) or numbers.e != trust['key']['e']:
        raise ValueError('Original pinned maintainer key required')
    original = args.input.read_bytes()
    manifest, original_bundle, original_entry = validate_input(original,
        json.loads(args.identity.read_text(encoding='utf-8')), trust)
    original_sequence = manifest['sequence']
    # Stage all outputs privately. No final directory exists on any failure.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ce2021-resign-', dir=args.output.parent) as temporary:
        staged = Path(temporary) / 'verified'
        result = repackage(original, manifest, original_bundle, original_entry,
                           private, trust, sequence, staged, args.input.name)
        staged.rename(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def repackage(original, manifest, original_bundle, original_entry, private, trust, sequence, destination, input_name):
    original_sequence = manifest['sequence']
    with zipfile.ZipFile(BytesIO(original)) as delivery:
        with zipfile.ZipFile(BytesIO(original_bundle)) as source:
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
        manifest['sequence'] = sequence
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
        destination.mkdir(parents=True)
        bundle_path = destination / ('bobbi-private-%s-coreelec.bobbi-update.zip' % sequence)
        entry_path = destination / ('script.bobbi.start-ce2021-clean-%s.zip' % sequence)
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
                    blob = delivery.read(item)
                    removed.append(dict(archive='delivery', path=name, sha256=digest(blob),
                        bytes=len(blob), rule=POLICY, category='standalone-document'))
                    continue
                if name == 'MANIFEST.json':
                    continue
                blob = replacements.get(name)
                if blob is None:
                    blob = delivery.read(item)
                    if name.lower().endswith('.zip'):
                        blob = clean_archive(blob, name, removed)
                    elif name.endswith('.patch'):
                        blob = patch_without_excluded(blob, removed, name)
                if name == 'README.md':
                    blob = ('# CE2021 GitHub cleaned delivery\n\n'
                            'Document-cleaned derivative; original maintainer trust.\n'
                            'Installers retain their original internal paths and component versions.\n'
                            'Read docs/CE-REVIEW-CLOSURE-2021-20261021.md for historical device-test limits.\n'
                            'Signing/ZIP checks are not a new device or source-build certification.\n').encode()
                output.writestr(copy.copy(item), blob)
                records.append(dict(path=name, bytes=len(blob), sha256=digest(blob)))
            metadata = dict(schema=2, sequence=sequence, original_delivery_sha256=digest(original),
                            original_payload_sha256=digest(original_bundle), original_entry_sha256=digest(original_entry),
                            original_sequence=original_sequence, components=len(cleaned_components),
                            excluded_document_entries=len(removed), signature='original pinned maintainer key',
                            non_document_component_files='byte-identical', current_source_build='not rerun; previous failure remains',
                            device_test='original pre-cleanup evidence only; no deployment', files=records)
            output.writestr('MANIFEST.json', json.dumps(metadata, ensure_ascii=False, indent=2).encode())
        handoff = outer.getvalue()
        check_nested(handoff, 'delivery')
        (destination / ('ce2021-clean-%s.zip' % sequence)).write_bytes(handoff)
        (destination / Path(REPORT).name).write_bytes(report)
        (destination / 'REMOVAL-MANIFEST.json').write_text(json.dumps(dict(policy=POLICY, entries=removed), indent=2)+'\n', encoding='utf-8')
        result = dict(sequence=sequence, original_sequence=original_sequence, removed_entries=len(removed), components=len(cleaned_components),
                      original_key_verified=True, signature_verified=True, nested_zip_verified=True,
                      non_document_files_unchanged=True, device_deployed=False,
                      assets=[dict(name=p.name, bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
                              for p in sorted(destination.iterdir()) if p.is_file()])
        (destination / 'packaging-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return result


if __name__ == '__main__':
    main()
