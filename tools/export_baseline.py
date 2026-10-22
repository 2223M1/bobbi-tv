"""Extract the approved commit into ignored quarantine, NEVER a public release.

Only an explicit committed inventory is read. No working-tree files, private Git
history, runtime databases or credentials are copied. Public promotion requires
separate portability/license review and a fresh inventory.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASELINE = 'a9189b5d157d886c814cf28c6748c97fc6825a35'
ROOT = Path(__file__).resolve().parents[1]
IDS = {
    'plugin.video.jacktook': 'plugin.video.bobbi',
    'script.module.am6b.core': 'script.module.bobbi.core',
    'script.module.am6b.mdsub': 'script.module.bobbi.mdsub',
    'script.module.am6b.qqdocs': 'script.module.bobbi.catalog',
    'script.am6b.opensubtitles': 'script.bobbi.subtitles',
    'skin.am6b.cinema': 'skin.bobbi.cinema',
}
EXCLUDE_EXT = {'.sqlite3', '.sqlite', '.db', '.zip', '.rar', '.apk', '.pyc'}
FONT_ALLOW = {'HarmonyOS_SansSC_Regular.ttf', 'HarmonyOS_SansSC_Medium.ttf',
              'HarmonyOS_SansSC_Bold.ttf', 'RobotoCJKSC-Regular.ttf'}
DATA_EXCLUDE = {'resources/catalog.json', 'resources/cinema/ui-catalog-preview.json'}


def committed(repo, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', BASELINE + ':' + path])


def safe_name(name):
    path = PurePosixPath(name)
    return (name == path.as_posix() and not path.is_absolute()
            and not any(p in ('..', '.') for p in path.parts)
            and '\\' not in name and ':' not in name)


def extract(repo, target):
    target = Path(target).resolve()
    quarantine = ROOT / 'staging'
    if target.parent != quarantine or target.exists():
        raise ValueError('Use a new direct child of ignored staging, not a public tree')
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', BASELINE]).decode().strip()
    if actual != BASELINE:
        raise ValueError('Unexpected baseline')
    inventory = json.loads(committed(repo, 'ui-redesign/tools/release-inputs.json'))
    if inventory['schema'] != 1:
        raise ValueError('Unknown inventory schema')
    payloads, evidence, excluded = {}, {}, []
    for root, names in inventory['roots'].items():
        if not safe_name(root) or names != sorted(set(names)):
            raise ValueError('Invalid committed inventory')
        parts = PurePosixPath(root).parts
        original_id = parts[parts.index('addons') + 1]
        if original_id not in IDS:
            excluded.append({'path': root, 'reason': 'not approved for redistribution'})
            continue
        ui_overlay = root.endswith('/resources/skins/Default')
        for name in names:
            if not safe_name(name):
                raise ValueError('Invalid path')
            relative = ('resources/skins/Default/' if ui_overlay else '') + name
            source = 'ui-redesign/' + root + '/' + name
            suffix = PurePosixPath(name).suffix.lower()
            reason = None
            if suffix in EXCLUDE_EXT or name in DATA_EXCLUDE:
                reason = 'runtime/catalog/archive excluded'
            elif suffix in {'.ttf', '.otf', '.woff', '.woff2'} and PurePosixPath(name).name not in FONT_ALLOW:
                reason = 'font not in the reviewed set'
            elif name.startswith('resources/screenshots/') or name.startswith('resources/screenshot-'):
                reason = 'private UI image not a public demonstration'
            if reason:
                excluded.append({'path': source, 'reason': reason})
                continue
            key = IDS[original_id] + '/' + relative
            raw = committed(repo, source)
            payloads[key] = raw
            evidence[key] = {'source': source, 'sha256': hashlib.sha256(raw).hexdigest()}
    target.mkdir(parents=True)
    for name, data in sorted(payloads.items()):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    report = {'schema': 1, 'baseline': BASELINE, 'status': 'QUARANTINE_NOT_INSTALLABLE',
              'note': 'Directory IDs are reserved only; code is not yet ported or public-cleared.',
              'files': evidence, 'excluded': excluded}
    (target / 'export-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'files': len(payloads), 'excluded': len(excluded), 'status': report['status']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'staging' / 'baseline')
    args = parser.parse_args()
    print(json.dumps(extract(args.source, args.output)))
