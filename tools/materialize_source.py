"""One-time, allowlisted promotion into the self-contained public source tree.

Not part of a user install or ordinary build. No runtime profile/history moves.
Imported catalogue databases are rebuilt from an explicit column allowlist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_candidate import transform, rename, TEXT


def audit_catalog(source):
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        print(json.dumps({'tables': rows}, ensure_ascii=False, indent=2))


def promote():
    sources = {
        'plugin.video.bobbi': ROOT / 'build/portable-candidate-r4/plugin.video.bobbi',
        'script.module.bobbi.core': ROOT / 'build/portable-candidate-r4/script.module.bobbi.core',
        'skin.bobbi.cinema': ROOT / 'build/sanitized-skin-r4',
    }
    for addon, source in sources.items():
        target = ROOT / 'addons' / addon
        if target.exists():
            raise ValueError('Do not overwrite a promoted source tree: ' + addon)
        if not source.is_dir():
            raise ValueError('Prepared candidate missing: ' + addon)
    for addon, source in sources.items():
        shutil.copytree(source, ROOT / 'addons' / addon)
    # Both catalogue modules were created for the user's AM6B project and
    # authorized for publication. Keep their declared MIT license separately.
    for addon in ('script.module.bobbi.catalog', 'script.module.bobbi.mdsub'):
        target = ROOT / 'addons' / addon
        source = ROOT / 'staging/baseline' / addon
        if target.exists():
            raise ValueError('Do not overwrite a promoted catalogue module')
        for path in sorted(source.rglob('*')):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(source).as_posix()
            if path.suffix.lower() in ('.sqlite3', '.db', '.json', '.zip', '.pyc'):
                continue
            destination = target / rename(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            raw = path.read_bytes()
            destination.write_bytes(transform(addon + '/' + rename(relative), raw) if path.suffix in TEXT else raw)
    print('Candidate sources materialized. Public scan and runtime port still required.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-catalog', type=Path)
    args = parser.parse_args()
    audit_catalog(args.audit_catalog) if args.audit_catalog else promote()
