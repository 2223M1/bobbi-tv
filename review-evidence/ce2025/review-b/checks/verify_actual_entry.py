#!/usr/bin/env python3
"""Read-only independent CE2024 artifact-to-fixed-tree verification.

No maintainer/application secret is printed or persisted by this verifier.
The one allowed private application input is recorded only by size and hash.
This verifies bytes and packaging contracts; it does not certify a device.
"""
import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


HEAD = 'c4e0baca6acefa58f031979bff71e7cd1028efdf'
TREE = 'bb4256d63465fefb9c5820f3ce1ec9cca33ff546'
ENTRY_PATH = 'review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip'
ENTRY_SHA256 = 'cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c'
PAYLOAD_SHA256 = 'd53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096'
EMBEDDED = 'script.bobbi.start/resources/complete.bobbi-update.zip'
LOCAL_INPUT = ('script.module.bobbi.core', 'resources/tmdb-project.json')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_files(archive):
    rows = archive.infolist()
    names = [row.filename for row in rows]
    require(len(names) == len(set(names)) == len({n.casefold() for n in names}), 'Duplicate ZIP member')
    for row in rows:
        require(not row.is_dir() and not row.filename.startswith('/') and '\\' not in row.filename
                and ':' not in row.filename and not any(p in ('', '.', '..') for p in row.filename.split('/'))
                and row.orig_filename == row.filename and not row.flag_bits & 1
                and stat.S_IFMT(row.external_attr >> 16) in (0, stat.S_IFREG), 'Unsafe ZIP member')
    require(archive.testzip() is None, 'ZIP CRC failure')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--fixed-source', type=Path, required=True)
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    fixed = json.loads(args.fixed_source.read_text())
    require(fixed['branch']['commit']['sha'] == HEAD, 'Wrong fixed head')
    require(fixed['tree']['sha'] == TREE and not fixed['tree']['truncated'], 'Wrong/incomplete tree')
    tree = {r['path']: r for r in fixed['tree']['tree'] if r['type'] == 'blob'}
    source_receipts = []

    def verified_source(path):
        raw = (repo / path).read_bytes()
        require(blob(raw) == tree[path]['sha'], 'Unverified source: ' + path)
        source_receipts.append(dict(path=path, bytes=len(raw), git_blob=blob(raw), sha256=sha256(raw)))
        return raw

    inventory = json.loads(verified_source('release/source-inventory.json'))['components']
    platform = 'addons/script.module.bobbi.platform/lib/bobbi_platform/'
    trust_raw = verified_source(platform + 'release_trust.json')
    trust = json.loads(trust_raw)
    for path in ('tools/audit_ce_entry.py', 'tools/build_ce_entry.py', 'tools/build_release.py',
                 'tools/delivery_policy.py', platform + 'offline_updates.py', platform + 'signatures.py',
                 platform + 'updates.py'):
        verified_source(path)
    entry_raw = args.entry.read_bytes()
    entry_blob = blob(entry_raw)
    require(entry_blob == tree[ENTRY_PATH]['sha'], 'Actual entry differs from fixed Git blob')
    require(len(entry_raw) == 95916922 and sha256(entry_raw) == ENTRY_SHA256, 'Actual entry differs from delivery pin')
    sys.path.insert(0, str(repo / 'tools'))
    import audit_ce_entry
    from build_ce_entry import BOOTSTRAP
    from delivery_policy import EXCLUDE
    from bobbi_platform.offline_updates import SignedBundle

    actual_audit = audit_ce_entry.audit(args.entry)
    files_receipts = []
    component_receipts = []
    local_inputs = []
    entry_component = None
    platform_component = None
    with zipfile.ZipFile(BytesIO(entry_raw)) as entry:
        entry_names = safe_files(entry)
        require(not any(EXCLUDE.search(n) for n in entry_names), 'Excluded document remains in entry')
        payload_raw = entry.read(EMBEDDED)
        require(len(payload_raw) == 95817630 and sha256(payload_raw) == PAYLOAD_SHA256,
                'Actual payload differs from delivery pin')
        with zipfile.ZipFile(BytesIO(payload_raw)) as payload:
            safe_files(payload)
            # Independent standard-library-provider verification, separate from product verify().
            public = rsa.RSAPublicNumbers(trust['key']['e'], int(trust['key']['n'], 16)).public_key()
            public.verify(base64.b64decode(payload.read('release.sig'), validate=True),
                          payload.read('release.json'), padding.PKCS1v15(), hashes.SHA256())
        with tempfile.TemporaryDirectory(prefix='ce2024-real-payload-') as name:
            checked_payload = Path(name) / 'payload.zip'
            checked_payload.write_bytes(payload_raw)
            with SignedBundle(checked_payload, trust, 'coreelec') as signed:
                manifest = signed.check_all()
                require(manifest['sequence'] == 2026102024 and manifest['channel'] == 'private-candidate',
                        'Wrong signed generation')
                require({r['id'] for r in manifest['components']} == set(inventory), 'Component inventory differs')
                for row in manifest['components']:
                    component = row['id']
                    packed = signed.read(row['file'], row['size'])
                    with zipfile.ZipFile(BytesIO(packed)) as archive:
                        names = safe_files(archive)
                        require(not any(EXCLUDE.search(n) for n in names), 'Excluded component document')
                        prefix = component + '/'
                        expected = {prefix + name for name in inventory[component]}
                        if component == LOCAL_INPUT[0]:
                            expected.add(prefix + LOCAL_INPUT[1])
                        require(set(names) == expected, 'Component member inventory mismatch: ' + component)
                        for member in names:
                            relative = member[len(prefix):]
                            raw = archive.read(member)
                            if (component, relative) == LOCAL_INPUT:
                                local_inputs.append(dict(component=component, path=relative, bytes=len(raw),
                                                         sha256=sha256(raw), content_disclosed=False))
                                continue
                            require(sha256(raw) == inventory[component][relative], 'Inventory byte mismatch: ' + member)
                            path = 'addons/' + member
                            if path not in tree:
                                path = 'third_party/addons/' + member
                            require(path in tree and blob(raw) == tree[path]['sha'], 'Fixed Git byte mismatch: ' + member)
                            files_receipts.append(dict(component=component, path=path, bytes=len(raw),
                                                       sha256=sha256(raw), git_blob=blob(raw)))
                        if component == 'script.bobbi.start':
                            entry_component = {n: archive.read(n) for n in names}
                        if component == 'script.module.bobbi.platform':
                            platform_component = {n: archive.read(n) for n in names}
                    component_receipts.append(dict(id=component, version=row['version'], bytes=len(packed),
                                                   sha256=sha256(packed), files=len(names), inventory_matches=True,
                                                   fixed_tree_matches=True))
        require(entry_component is not None and platform_component is not None, 'Entry/platform component absent')
        expected_entry = dict(entry_component)
        for filename in BOOTSTRAP:
            expected_entry['script.bobbi.start/bootstrap/bobbi_platform/' + filename] = platform_component[
                'script.module.bobbi.platform/lib/bobbi_platform/' + filename]
        expected_entry[EMBEDDED] = payload_raw
        require(set(entry_names) == set(expected_entry), 'Unexpected or absent outer entry member')
        for name, raw in expected_entry.items():
            require(entry.read(name) == raw, 'Outer entry differs from signed components: ' + name)

    result = dict(schema=1, head=HEAD, tree=TREE,
                  scope='Actual downloaded entry; full cryptographic verification and byte mapping, no device certification',
                  entry=dict(path=ENTRY_PATH, bytes=len(entry_raw), sha256=sha256(entry_raw),
                             git_blob=entry_blob, fixed_tree_matches=True, member_count=len(entry_names),
                             exact_signed_assembly=True),
                  payload=dict(bytes=len(payload_raw), sha256=sha256(payload_raw), sequence=manifest['sequence'],
                               channel=manifest['channel'], profile=manifest['profile'],
                               product_signed_bundle_check='passed', independent_cryptography_signature='passed'),
                  product_audit=actual_audit,
                  source_inventory=dict(components=len(inventory), files=sum(len(v) for v in inventory.values()),
                                        matched_git_files=len(files_receipts), excluded_documents=0,
                                        all_expected_members_present=True, unexpected_members=0),
                  application_inputs=local_inputs, components=component_receipts,
                  verifier_sources=source_receipts, files=files_receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('head', 'entry', 'payload', 'source_inventory', 'application_inputs')}, indent=2))


if __name__ == '__main__':
    main()
