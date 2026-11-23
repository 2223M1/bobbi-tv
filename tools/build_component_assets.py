"""Prepare optional immutable release assets locally; never promotes a feed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust, archive_info
from bobbi_platform.online_components import component_name, metadata_name
from bobbi_platform.online_updates import release_url


def build(bundle, output, tag, trust=None):
    """No new signing: preserve the original authenticated manifest and signature."""
    output = Path(output)
    if output.exists():
        raise ValueError('Component asset output must be new')
    name = metadata_name(tag)
    with SignedBundle(bundle, trust or load_trust(), 'coreelec') as source:
        manifest = source.check_all()
        # Check before creating any assets. Input must be the canonical full
        # archive whose exact outer digest the old schema-1 offer advertises.
        original = source.archive
        expected = ['release.json', 'release.sig'] + [row['file'] for row in manifest['components']]
        if original.namelist() != expected or original.comment:
            raise ValueError('Noncanonical complete bundle')
        for item in original.infolist():
            if (item.date_time != (1980, 1, 1, 0, 0, 0) or item.compress_type != zipfile.ZIP_STORED
                    or item.extra or item.comment or item.flag_bits or item.create_system != 3
                    or item.external_attr != 0o600 << 16):
                raise ValueError('Noncanonical complete bundle')
        output.mkdir(parents=True)
        with zipfile.ZipFile(output/name, 'x', compression=zipfile.ZIP_STORED) as target:
            for member in ('release.json', 'release.sig'):
                target.writestr(archive_info(member), original.read(member))
        assets = []
        for row in manifest['components']:
            raw = source.read(row['file'], row['size'])
            path = output/component_name(row)
            if not path.exists():
                path.write_bytes(raw)
                assets.append(dict(file=path.name, bytes=len(raw), sha256=row['sha256']))
        metadata_raw = (output/name).read_bytes()
        assets.insert(0, dict(file=name, bytes=len(metadata_raw), sha256=hashlib.sha256(metadata_raw).hexdigest()))
    return dict(schema=1, protocol='components-v1', tag=tag, sequence=manifest['sequence'],
                assets=assets, published=False,
                release_roots=[release_url(tag, source).rsplit('/', 1)[0]+'/' for source in ('gitee', 'github')])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    result = build(args.bundle, args.output, args.tag)
    args.report.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
