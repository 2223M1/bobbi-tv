"""Delivery, source-archive, and signed-bundle hygiene contracts.

Only exact manifest-listed notices cross the document-clean boundary.
Retaining conflicting upstream evidence is not distribution clearance; the
vendor-license gate independently keeps unresolved components blocked.
"""
import base64
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'addons/script.module.bobbi.platform/lib') not in sys.path:
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))

POLICY = 'pinned-notices-v2'
PUBLIC_CA = 'third_party/addons/script.module.certifi/lib/certifi/cacert.pem'
CURATED_CATALOG = 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'
DEFAULT_EMBEDDED_BUNDLE = 'script.bobbi.start/resources/complete.bobbi-update.zip'

# Match document filenames only. A license directory is not permission to
# discard a .py/.ttf/.wav, and e.g. license_status.py is executable input.
EXCLUDE = re.compile(
    r'(^|/)(?:[^/]*(?:copyright|licen[cs]e|notice|copying|attribution|'
    r'asset-' + r'provenance|third.party)[^/]*\.(?:md|txt|json|rst|html)|'
    r'(?:licen[cs]e|copying|notice|copyright)(?:-[a-z0-9_-]+)?|'
    r'(?:licenses?/)(?:[^/]+/)*[^/]+\.(?:md|txt|json|rst|html))$', re.I)

RETIRED_SKIN_FONTS = frozenset({
    'NetflixSans-Regular.ttf',
    'NetflixSans-Bold.ttf',
    'fzltdhk.ttf',
    'BobbiDisplay.ttf',
})


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def require_clean(paths, component=None):
    paths = tuple(paths)
    if any(path.rsplit('/', 1)[-1].casefold() in {n.casefold() for n in RETIRED_SKIN_FONTS} for path in paths):
        raise ValueError('Retired skin font in package')
    from vendor_licenses import load_manifest
    allowed = {(row['component'], row['path']) for row in load_manifest().get('deliveries', [])}

    def permitted(path):
        if component is not None:
            return (component, path) in allowed
        prefix, separator, relative = path.partition('/')
        return bool(separator) and (prefix, relative) in allowed

    if any(EXCLUDE.search(path) and not permitted(path) for path in paths):
        raise ValueError('Document policy conflict; review input before refreshing inventory')


def validate_source_paths(names):
    """A Git snapshot, not an unexamined workspace/account backup."""
    folded = set()
    for name in names:
        parts = PurePosixPath(name).parts
        lower = name.lower()
        if (not parts or name.startswith('/') or '\\' in name or ':' in name
                or any(part in ('.', '..') for part in parts)
                or lower in folded):
            raise ValueError('INVALID_SOURCE_PATH')
        folded.add(lower)
        if any(part.lower() in ('.git', '.private', '.venv', '.venv-closure', '__pycache__') for part in parts):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if parts[0].lower() in ('profile', 'profiles', 'userdata', 'dist', 'staging'):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if (lower.endswith(('.keystore', '.jks', '/tmdb-project.json'))
                or lower.endswith(('.sqlite', '.sqlite3', '.db')) and name != CURATED_CATALOG
                or lower.endswith('.pem') and name != PUBLIC_CA):
            raise ValueError('LOCAL_SECRET_OR_DATABASE_IN_SOURCE')


def junit_counts(path):
    root = ET.parse(path).getroot()
    rows = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    if not rows:
        raise ValueError('MISSING_JUNIT_SUITE')
    result = {key: sum(int(row.get(key, '0')) for row in rows)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    result['passed'] = result['tests'] - result['failures'] - result['errors'] - result['skipped']
    return result


def inspect_source_archive(path, expected):
    with zipfile.ZipFile(path) as source:
        infos = [row for row in source.infolist() if not row.is_dir()]
        names = [row.filename for row in infos]
        validate_source_paths(names)
        if set(names) != set(expected) or len(names) != len(expected):
            raise ValueError('SOURCE_ARCHIVE_TREE_MISMATCH')
        evidence = []
        for row in infos:
            data = source.read(row.filename)
            if row.filename.startswith('review-evidence/'):
                evidence.append(dict(
                    path=row.filename,
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    acceptance='See the individual receipt and report; this index does not turn it into a pass',
                ))
    return evidence


def require_clean_frozen_checkout(product_commit, git_runner=None, output=None):
    """Reject dirty working trees or post-freeze product diffs before creating output."""
    if output is not None and Path(output).exists():
        raise ValueError('OUTPUT_EXISTS')
    runner = git_runner or git
    if runner('status', '--porcelain').strip():
        raise ValueError('HANDOFF_CHECKOUT_DIRTY')
    if runner('diff', product_commit, 'HEAD', '--', 'addons', 'third_party', 'release').strip():
        raise ValueError('PRODUCT_CHANGED_AFTER_FREEZE')


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
                    removed.append(dict(
                        archive=label,
                        path=first,
                        sha256=digest(chunk),
                        bytes=len(chunk),
                        rule=POLICY,
                        category='document-patch-block',
                    ))
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
                removed.append(dict(
                    archive=label,
                    path=name,
                    sha256=digest(blob),
                    bytes=len(blob),
                    rule=POLICY,
                    category='standalone-document',
                ))
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


def checked_sequence(value, registry, minimum_floor=2026102022):
    used = registry.get('allocated') if isinstance(registry, dict) else None
    if (type(value) is not int or not isinstance(used, list) or not used or
            any(type(n) is not int or n < 1 for n in used) or
            value <= max([minimum_floor] + used)):
        raise ValueError('New sequence above verified release registry required')
    return value


def validate_signed_delivery_input(original, identity, trust, *,
                                   input_sequence, bundle_member, entry_member,
                                   embedded_member=DEFAULT_EMBEDDED_BUNDLE,
                                   channel='private-candidate', profile='coreelec'):
    """Verify caller-pinned bytes AND signed bundle contract before any repackage."""
    from bobbi_platform.offline_updates import SignedBundle
    from bobbi_platform.updates import UpdateError

    if (not isinstance(identity, dict) or identity.get('sequence') != input_sequence or
            type(identity.get('sequence')) is not int or
            not isinstance(identity.get('components'), list) or
            any(not isinstance(identity.get(k), str) or not re.fullmatch('[a-f0-9]{64}', identity[k])
                for k in ('outer_sha256', 'payload_sha256', 'entry_sha256'))):
        raise ValueError('Explicit exact input identity required')
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
        bundle, entry = delivery.read(bundle_member), delivery.read(entry_member)
    if digest(bundle) != identity['payload_sha256'] or digest(entry) != identity['entry_sha256']:
        raise ValueError('Frozen payload or entry input differs')
    with zipfile.ZipFile(BytesIO(entry)) as archive:
        list(safe_members(archive))
        if archive.read(embedded_member) != bundle:
            raise ValueError('Entry and standalone generation differ')
    with tempfile.TemporaryDirectory(prefix='checked-signed-input-') as temp:
        path = Path(temp) / 'bundle.zip'
        path.write_bytes(bundle)
        try:
            with SignedBundle(path, trust, profile) as signed:
                manifest = copy.deepcopy(signed.check_all())
        except UpdateError as exc:
            raise ValueError('Input signed contract rejected: ' + str(exc)) from None
    if manifest['sequence'] != input_sequence or manifest['channel'] != channel:
        raise ValueError('Signed candidate sequence or channel mismatch')
    if sorted(manifest['components'], key=lambda r: r['id']) != sorted(identity['components'], key=lambda r: r['id']):
        raise ValueError('Frozen component identities differ')
    return manifest, bundle, entry


def repackage_signed_delivery(original, manifest, original_bundle, original_entry,
                              private, trust, sequence, destination, *,
                              bundle_member, entry_member, report_member,
                              embedded_member=DEFAULT_EMBEDDED_BUNDLE,
                              clean_prefix='clean', verifier=None):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from bobbi_platform.offline_updates import SignedBundle

    verify_nested = verifier or check_nested
    original_sequence = manifest['sequence']
    with zipfile.ZipFile(BytesIO(original)) as delivery:
        with zipfile.ZipFile(BytesIO(original_bundle)) as source:
            cleaned_components = []
            removed = []
            for row in manifest['components']:
                blob = source.read(row['file'])
                if digest(blob) != row['sha256'] or len(blob) != row['size']:
                    raise ValueError('Input component failed integrity')
                cleaned = clean_archive(blob, bundle_member + '!' + row['file'], removed)
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
        entry = clean_archive(original_entry, entry_member, removed, {embedded_member: bundle})
        old_bootstrap = inventory(original_entry)
        new_bootstrap = inventory(entry)
        prefix = embedded_member + '!'
        if ({k: v for k, v in old_bootstrap.items() if not k.startswith(prefix)} !=
                {k: v for k, v in new_bootstrap.items() if not k.startswith(prefix)}):
            raise ValueError('Installer bootstrap code changed')
        destination.mkdir(parents=True)
        bundle_path = destination / ('bobbi-private-%s-coreelec.bobbi-update.zip' % sequence)
        entry_path = destination / ('script.bobbi.start-%s-%s.zip' % (clean_prefix, sequence))
        bundle_path.write_bytes(bundle)
        entry_path.write_bytes(entry)
        with SignedBundle(bundle_path, trust, 'coreelec') as checked:
            checked.check_all()
        report = delivery.read(report_member)
        replacements = {bundle_member: bundle, entry_member: entry, report_member: report}
        outer = BytesIO()
        records = []
        with zipfile.ZipFile(outer, 'w') as output:
            for item in safe_members(delivery):
                name = item.filename
                if EXCLUDE.search(name):
                    blob = delivery.read(item)
                    removed.append(dict(
                        archive='delivery',
                        path=name,
                        sha256=digest(blob),
                        bytes=len(blob),
                        rule=POLICY,
                        category='standalone-document',
                    ))
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
                output.writestr(copy.copy(item), blob)
                records.append(dict(path=name, bytes=len(blob), sha256=digest(blob)))
            metadata = dict(
                schema=2,
                sequence=sequence,
                original_delivery_sha256=digest(original),
                original_payload_sha256=digest(original_bundle),
                original_entry_sha256=digest(original_entry),
                original_sequence=original_sequence,
                components=len(cleaned_components),
                excluded_document_entries=len(removed),
                signature='original pinned maintainer key',
                non_document_component_files='byte-identical',
                files=records,
            )
            output.writestr('MANIFEST.json', json.dumps(metadata, ensure_ascii=False, indent=2).encode())
        handoff = outer.getvalue()
        verify_nested(handoff, 'delivery')
        (destination / ('%s-%s.zip' % (clean_prefix, sequence))).write_bytes(handoff)
        (destination / Path(report_member).name).write_bytes(report)
        (destination / 'REMOVAL-MANIFEST.json').write_text(
            json.dumps(dict(policy=POLICY, entries=removed), indent=2) + '\n',
            encoding='utf-8',
        )
        result = dict(
            sequence=sequence,
            original_sequence=original_sequence,
            removed_entries=len(removed),
            components=len(cleaned_components),
            original_key_verified=True,
            signature_verified=True,
            nested_zip_verified=True,
            non_document_files_unchanged=True,
            device_deployed=False,
            assets=[dict(name=p.name, bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
                    for p in sorted(destination.iterdir()) if p.is_file()],
        )
        (destination / 'packaging-result.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        return result


def stage_verified_repackage(*, input_path, identity_path, registry_path, key_path,
                             sequence, output_path, trust, input_sequence,
                             bundle_member, entry_member, report_member,
                             clean_prefix='clean', verifier=None):
    """Stage repackaging privately so a failed verification never publishes output_path."""
    from cryptography.hazmat.primitives import serialization

    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError('Output already exists; originals are never overwritten')
    seq = checked_sequence(
        sequence,
        json.loads(Path(registry_path).read_text(encoding='utf-8')),
        minimum_floor=max(input_sequence, 2026102022),
    )
    private = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    numbers = private.public_key().public_numbers()
    if numbers.n != int(trust['key']['n'], 16) or numbers.e != trust['key']['e']:
        raise ValueError('Original pinned maintainer key required')
    original = Path(input_path).read_bytes()
    manifest, original_bundle, original_entry = validate_signed_delivery_input(
        original,
        json.loads(Path(identity_path).read_text(encoding='utf-8')),
        trust,
        input_sequence=input_sequence,
        bundle_member=bundle_member,
        entry_member=entry_member,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verified-repackage-', dir=output_path.parent) as temporary:
        staged = Path(temporary) / 'verified'
        result = repackage_signed_delivery(
            original,
            manifest,
            original_bundle,
            original_entry,
            private,
            trust,
            seq,
            staged,
            bundle_member=bundle_member,
            entry_member=entry_member,
            report_member=report_member,
            clean_prefix=clean_prefix,
            verifier=verifier,
        )
        staged.rename(output_path)
    return result
