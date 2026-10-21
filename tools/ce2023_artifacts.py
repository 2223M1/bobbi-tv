"""Map retained program generations to the recovered checkout (no account data)."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile

from build_release import ROOT, sources, LOCAL_RESOURCE
from delivery_policy import EXCLUDE, POLICY
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bundle(path):
    files = {}
    with SignedBundle(path, load_trust(), 'coreelec') as signed:
        manifest = signed.check_all()
        for row in manifest['components']:
            blob = signed.read(row['file'], row['size'])
            with zipfile.ZipFile(BytesIO(blob)) as component:
                for name in component.namelist():
                    if not name.endswith('/'):
                        files[name] = dict(sha256=sha(component.read(name)), component=row['id'],
                            archive=row['file'], component_sha256=row['sha256'])
    return manifest, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--clean', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original, a = read_bundle(args.original)
    cleaned, b = read_bundle(args.clean)
    if original['sequence'] != 2026102021 or cleaned['sequence'] != 2026102022:
        raise ValueError('Historical generations differ')
    roots, rows, removed = sources(), [], []
    for name in sorted(set(a)|set(b)):
        component, relative = name.split('/', 1)
        path = roots[component]/relative
        record = dict(path=path.relative_to(ROOT).as_posix(), original=a.get(name), cleaned=b.get(name),
                      checkout_sha256=sha(path.read_bytes()) if path.is_file() else None)
        if name not in b:
            if not EXCLUDE.search(name):
                raise ValueError('Runtime member removed')
            record['status'] = 'approved-document-removal'
            removed.append(dict(archive=a[name]['archive'], path=name, sha256=a[name]['sha256'], rule=POLICY))
        else:
            if name not in a or a[name]['sha256'] != b[name]['sha256']:
                raise ValueError('Historical non-document member changed')
            if (component, relative) == LOCAL_RESOURCE:
                record['status'] = 'generated-local-application-input'
            elif record['checkout_sha256'] == b[name]['sha256']:
                record['status'] = 'identical-runtime'
            else:
                record['status'] = 'current-candidate-change'
        rows.append(record)
    report = dict(schema=1, original_sequence=original['sequence'], clean_sequence=cleaned['sequence'],
        original_payload_sha256=sha(args.original.read_bytes()), clean_payload_sha256=sha(args.clean.read_bytes()),
        original_outer_available=False, original_producer_commit=None,
        historical_evidence='Retained receipts; original dirty build had no final commit. Not this run.', files=rows)
    (args.output/'SOURCE-PACKAGE-MAP.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (args.output/'REMOVAL-MANIFEST.json').write_text(json.dumps(dict(policy=POLICY, entries=removed), indent=2)+'\n', encoding='utf-8')
    # Exact historical input lock remains useful even though its outer ZIP was
    # deleted by another task. No replacement outer is called the original.
    lock = dict(sequence=original['sequence'], components=original['components'],
        outer_sha256='b91725bcf656750020823d1e3e318ff1e0fa65a66fc0df7c942a87fc9e6a0eb1',
        payload_sha256=sha(args.original.read_bytes()),
        entry_sha256='993de4a82a674b2041594f34e48ee45c45b048aebdb8524b59b353340d44b2d4')
    (ROOT/'release/ce2021-input-lock.json').write_text(json.dumps(lock, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(files=len(rows), removed=len(removed),
        statuses={status:sum(row['status']==status for row in rows) for status in sorted({r['status'] for r in rows})})))


if __name__ == '__main__':
    main()
