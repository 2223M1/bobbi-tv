"""Reviewed three-way integration; never reads dirty source files or profiles.

Only the committed delta between the previous baseline and ff530e0 is merged.
Conflicts are reported, not installed. Other workers own the explicit skip set.
This one-off tool is not an installer or automatic updater.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from prepare_candidate import rename

ROOT = Path(__file__).resolve().parents[1]
BASE = 'a9189b5d157d886c814cf28c6748c97fc6825a35'
REV = 'ff530e09c34c6285ccb05c1d4179140b097174fb'
PREFIX = 'ui-redesign/backend/source/addons/'
OWNED = {
    'juku_api.py', 'juku_catalog.py', 'search_completion.py', 'progressive_search.py',
    'provider_cache.py', 'catalog_release.py', 'share_stream.py', 'juku_provider.py',
    'catalog_providers.py', 'service.py',
    'player.py',
}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def read(repo, rev, name):
    return git(repo, 'show', rev + ':' + name)


def integrate(repo):
    changes = git(repo, 'diff', '--name-only', BASE, REV, '--', PREFIX).decode().splitlines()
    records = []
    for source in changes:
        rel = source[len(PREFIX):]
        if '/tests/' in rel or Path(rel).name in OWNED:
            continue
        if Path(rel).suffix not in {'.py', '.xml'}:
            continue
        target = ROOT / 'addons' / rename(rel)
        incoming_text = rename(read(repo, REV, source).decode('utf-8-sig'))
        if rel.endswith('/lib/search.py'):
            incoming_text = incoming_text.replace("'腾讯目录'", "'115 目录'")
        incoming = incoming_text.encode('utf-8')
        previous = subprocess.run(['git', '-C', str(repo), 'show', BASE + ':' + source], capture_output=True)
        before = target.read_bytes() if target.exists() else None
        if before is None:
            merged, status = incoming, 'added'
        elif previous.returncode:
            if before == incoming:
                continue
            records.append(dict(path=target.relative_to(ROOT).as_posix(), status='conflict_new_file'))
            continue
        else:
            base_text = rename(previous.stdout.decode('utf-8-sig'))
            if rel.endswith('/lib/search.py'):
                base_text = base_text.replace("'腾讯目录'", "'115 目录'")
            base = base_text.encode('utf-8')
            with tempfile.TemporaryDirectory(prefix='bobbi-merge-') as temp:
                paths = [Path(temp) / name for name in ('current', 'base', 'incoming')]
                for path, raw in zip(paths, (before, base, incoming)):
                    path.write_bytes(raw.replace(b'\r\n', b'\n'))
                merge = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
            if merge.returncode:
                records.append(dict(path=target.relative_to(ROOT).as_posix(), status='conflict'))
                continue
            merged, status = merge.stdout, 'merged'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(merged)
        records.append(dict(path=target.relative_to(ROOT).as_posix(), status=status,
                            source=source, source_sha256=hashlib.sha256(incoming).hexdigest(),
                            integrated_sha256=hashlib.sha256(merged).hexdigest()))
    report = dict(base=BASE, source_commit=REV, records=records)
    (ROOT / 'release/private-delta-integration.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({state: sum(r['status'] == state for r in records) for state in {r['status'] for r in records}}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    integrate(parser.parse_args().source)
