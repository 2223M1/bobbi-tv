"""One real Kodi addon ZIP containing the complete signed offline generation.

Bootstrap code is assembled from the reviewed inventory, not a second fork.
No user profile, maintainer transport or private signing key is read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust
from build_release import sources, files

BOOTSTRAP = ('__init__.py', 'ce_installer.py', 'ce_install_ui.py', 'offline_updates.py',
             'updates.py', 'upstream_addons.py', 'signatures.py', 'release_trust.json',
             'paths.py', 'kodi.py', 'playback.py', 'capabilities.py',
             'runtime.py', 'instance_lock.py', 'online_updates.py', 'online_transport.py')


def build(bundle, output, online=False):
    inventory = json.loads((ROOT / 'release/source-inventory.json').read_text(encoding='utf-8'))['components']
    roots = sources()
    for name in ('script.bobbi.start', 'script.module.bobbi.platform'):
        if files(roots[name]) != inventory[name]:
            raise ValueError('Bootstrap source inventory changed')
    with SignedBundle(bundle, load_trust(), 'coreelec') as signed:
        manifest = signed.check_all()
        entry = next(row for row in manifest['components'] if row['id'] == 'script.bobbi.start')
        platform = next(row for row in manifest['components'] if row['id'] == 'script.module.bobbi.platform')
        from io import BytesIO
        # Bootstrap comes from this very signed generation, not the potentially
        # newer checkout that happens to be used by the packaging command.
        with zipfile.ZipFile(BytesIO(signed.read(entry['file'], entry['size']))) as source:
            payload = {name: source.read(name) for name in source.namelist()}
        with zipfile.ZipFile(BytesIO(signed.read(platform['file'], platform['size']))) as source:
            for name in BOOTSTRAP:
                path = 'script.module.bobbi.platform/lib/bobbi_platform/' + name
                payload['script.bobbi.start/bootstrap/bobbi_platform/' + name] = source.read(path)
        # Retain the checked archive bytes while its signed instance is open.
        signed.archive.fp.seek(0)
        from bobbi_platform.offline_updates import MAX_BUNDLE
        raw = signed.archive.fp.read(MAX_BUNDLE + 1)
        if len(raw) > MAX_BUNDLE:
            raise ValueError('Complete bundle changed size')
        if not online:
            payload['script.bobbi.start/resources/complete.bobbi-update.zip'] = raw
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED) as target:
        for name, raw in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, raw)
    result = dict(schema=1, sequence=manifest['sequence'], entry_id=entry['id'],
        version=entry['version'], file=output.name, bytes=output.stat().st_size,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(), native_hash_required=False,
        complete_offline_payload=not online, upstream_dependencies='signed originals if absent; existing Kodi/author channels preserved; crypto by Kodi',
        actual_other_hardware_tested=False)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--online', action='store_true', help='Small repository entry; fetch the complete release on demand')
    args = parser.parse_args()
    print(json.dumps(build(args.bundle, args.output, online=args.online), indent=2))
