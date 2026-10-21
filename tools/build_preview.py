"""Reproducible diagnostic preview build, not the full bobbi cinema release."""
import hashlib
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from build_release import files, sources, OFFICIAL
from provenance_document import component_records

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ('script.module.bobbi.platform', 'script.bobbi.setup', 'plugin.video.bobbi.library',
              'script.module.bobbi.core', 'script.module.requests', 'script.module.certifi',
              'script.module.chardet', 'script.module.idna', 'script.module.urllib3')


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((ROOT / 'release/preview-inputs.json').read_text(encoding='utf-8'))
    if inventory['schema'] != 1 or set(inventory['components']) != set(COMPONENTS):
        raise ValueError('Unknown diagnostic preview inventory')
    manifest = {'schema': 1, 'status': 'diagnostic-preview-not-cinema', 'components': []}
    for addon in COMPONENTS:
        root = sources()[addon]
        names = inventory['components'][addon]
        actual = set(files(root))
        if names != sorted(set(names)) or set(names) != actual:
            raise ValueError('Review and update explicit source inventory: ' + addon)
        xml = ET.parse(root / 'addon.xml').getroot()
        if xml.attrib['id'] != addon:
            raise ValueError('Addon ID mismatch')
        if any(dep.get('addon') not in set(COMPONENTS) | OFFICIAL
               for dep in xml.findall('./requires/import') if dep.get('optional') != 'true'):
            raise ValueError('Diagnostic dependency closure changed')
        dest = output / (addon + '-' + xml.attrib['version'] + '.zip')
        notices = component_records(ROOT, root)
        with zipfile.ZipFile(dest, 'w') as archive:
            for name in names:
                path = root / name
                if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                    raise ValueError('No symlink build inputs')
                info = zipfile.ZipInfo(addon + '/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                raw = notices[name] if name in notices else path.read_bytes()
                archive.writestr(info, raw, compress_type=zipfile.ZIP_STORED)
        manifest['components'].append({'id': addon, 'version': xml.attrib['version'],
            'file': dest.name, 'bytes': dest.stat().st_size,
            'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/diagnostic-preview')
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
