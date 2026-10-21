"""Recover the exact, retained CE2021 delta and receipts into an isolated clone.

This is an import of immutable local evidence, not a source reconstruction from
the review prose. It never touches the original worktree, keys or a device.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_INPUTS = {
    'b91725bcf656750020823d1e3e318ff1e0fa65a66fc0df7c942a87fc9e6a0eb1': 'original-local-handoff',
    '4188691ab12040ac0f1e33bcba6761c6a02fc5bc6c00932f23991192988da708': 'retained-clean-handoff',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def recover(path):
    raw = path.read_bytes()
    if sha(raw) not in EXPECTED_INPUTS:
        raise ValueError('Not the frozen local CE2021 handoff')
    report = dict(schema=1, input=str(path), sha256=sha(raw), bytes=len(raw),
                  input_kind=EXPECTED_INPUTS[sha(raw)],
                  original_outer_available=False,
                  original_review_base='c8de17ae9dabbe0f37753e1751b1d88107311316',
                  rewritten_base='f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167',
                  imported=[], preserved=[])
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate member')
        manifest = json.loads(archive.read('MANIFEST.json'))
        expected = {row['path']: row for row in manifest['files']}
        if set(names) != set(expected) | {'MANIFEST.json'}:
            raise ValueError('Handoff membership differs')
        for name, row in expected.items():
            parts = PurePosixPath(name).parts
            if not parts or PurePosixPath(name).is_absolute() or '..' in parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe input path')
            data = archive.read(name)
            if len(data) != row['bytes'] or sha(data) != row['sha256']:
                raise ValueError('Handoff member integrity failed')
        # Validation precedes all writes. Existing b20e972 report stays intact;
        # its original pre-cleanup form is retained separately below.
        for name in sorted(expected):
            data = archive.read(name)
            destination = None
            if name.startswith('source-delta/'):
                relative = name[len('source-delta/'):]
                if relative.split('/')[0] not in {'addons', 'tools', 'tests', 'release'}:
                    raise ValueError('Unexpected source-delta scope')
                destination = ROOT / relative
            elif name.startswith('review-evidence/'):
                destination = ROOT / name
            elif name == 'docs/CE-REVIEW-CLOSURE-2021-20261021.md':
                destination = ROOT / 'review-evidence/ce2023/historical-retained-report.md'
            if destination is None:
                continue
            if destination.exists() and destination.read_bytes() == data:
                report['preserved'].append(name)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            report['imported'].append(dict(input=name, output=destination.relative_to(ROOT).as_posix(),
                                           sha256=sha(data), bytes=len(data)))
    output = ROOT / 'review-evidence/ce2023/recovered-ce2021.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(imported=len(report['imported']), preserved=len(report['preserved']),
                          report=str(output)), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('handoff', type=Path)
    recover(parser.parse_args().handoff)
