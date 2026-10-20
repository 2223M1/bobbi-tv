"""Reproducible offline Kodi components from a reviewed explicit inventory.

This delegates installation/update lifecycle to Kodi. It does NOT activate the
experimental custom atomic updater or claim real-device certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / 'release/source-inventory.json'
OFFICIAL = {'xbmc.python', 'xbmc.gui', 'script.module.pycryptodome'}  # Official Kodi ABI-native host modules.
LOCAL_RESOURCE = ('script.module.bobbi.core', 'resources/tmdb-project.json')


def sources():
    result = {}
    for base in (ROOT / 'addons', ROOT / 'third_party/addons'):
        for source in sorted(base.glob('*/addon.xml')):
            addon = ET.parse(source).getroot().attrib['id']
            if source.parent.name != addon or addon in result:
                raise ValueError('Duplicate or mismatched addon')
            result[addon] = source.parent
    return result


def files(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('Symlink source')
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if (root.name, name) == LOCAL_RESOURCE:
                continue  # Separate maintainer input; a clean Git clone stays testable.
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def refresh():
    content = {key: files(root) for key, root in sources().items()}
    with INVENTORY.open('w', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps({'schema': 1, 'components': content}, indent=2) + '\n')
    preview = ROOT / 'release/preview-inputs.json'
    value = json.loads(preview.read_text())
    from build_preview import COMPONENTS
    value['components'] = {key: sorted(content[key]) for key in COMPONENTS}
    with preview.open('w', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(value, indent=2) + '\n')


def archive(root, names, output, extra=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(names):
            info = zipfile.ZipInfo(root.name + '/' + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, (root / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        for name, raw in sorted((extra or {}).items()):
            if name in names or (root.name, name) != LOCAL_RESOURCE:
                raise ValueError('Unreviewed local build resource')
            info = zipfile.ZipInfo(root.name + '/' + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def project_resource(roots):
    """One explicit application input, frozen before packaging; never account state."""
    import importlib.util
    root = roots[LOCAL_RESOURCE[0]]
    spec = importlib.util.spec_from_file_location('build_project_metadata', root / 'lib/bobbi_core/project_metadata.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = root / LOCAL_RESOURCE[1]
    key = module.tmdb_key(path)
    if not key:
        raise ValueError('Maintainer TMDb project configuration required; no user account needed')
    # Canonicalize only already-validated application fields. The original file
    # is not re-read after validation, avoiding a check/package substitution.
    raw = json.dumps(dict(schema=1, application='Bobbi TV', api_key=key,
        use='personal-noncommercial', attribution=module.ATTRIBUTION),
        sort_keys=True, separators=(',', ':')).encode('utf-8')
    return raw


def build(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))['components']
    roots = sources()
    if set(roots) != set(inventory):
        raise ValueError('Addon inventory changed; review before refreshing')
    local_resource = project_resource(roots)
    manifest = {'version': '0.2.0-private.1', 'channel': 'private-candidate', 'device_verified': False, 'components': []}
    xml = ET.Element('addons')
    for addon, root in roots.items():
        if files(root) != inventory[addon]:
            raise ValueError('Source inventory changed: ' + addon)
        meta = ET.parse(root / 'addon.xml').getroot()
        for dependency in meta.findall('./requires/import'):
            if dependency.get('addon') not in set(roots) | OFFICIAL and dependency.get('optional') != 'true':
                raise ValueError('Unresolved required dependency: ' + dependency.get('addon'))
        version = meta.attrib['version']
        filename = addon + '-' + version + '.zip'
        output = destination / addon / filename
        archive(root, inventory[addon], output,
                {LOCAL_RESOURCE[1]: local_resource} if addon == LOCAL_RESOURCE[0] else None)
        output.with_suffix(output.suffix + '.sha256').write_text(
            hashlib.sha256(output.read_bytes()).hexdigest(), encoding='ascii')
        # Kodi uses raw artwork alongside repository zip paths.
        for node in meta.findall('./extension/assets/*'):
            if node.text and node.text in inventory[addon]:
                target = destination / addon / node.text
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / node.text, target)
        xml.append(meta)
        manifest['components'].append(dict(id=addon, version=version, file=addon + '/' + filename,
            sha256=hashlib.sha256(output.read_bytes()).hexdigest(), bytes=output.stat().st_size))
    raw = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(xml, encoding='utf-8') + b'\n'
    (destination / 'addons.xml').write_bytes(raw)
    # Kodi's checksum file is a change detector, not a security signature.
    (destination / 'addons.xml.md5').write_text(hashlib.md5(raw).hexdigest(), encoding='ascii')
    (destination / 'addons.xml.sha256').write_text(hashlib.sha256(raw).hexdigest(), encoding='ascii')
    # Unlike source inventories, this file is regenerated on Linux CI too.
    # Explicit LF prevents Windows text translation changing its bytes.
    with (destination / 'manifest.json').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    (destination / 'application-input.json').write_text(json.dumps(dict(
        component=LOCAL_RESOURCE[0], resource=LOCAL_RESOURCE[1],
        sha256=hashlib.sha256(local_resource).hexdigest(), account_state=False), indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh-inventory', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'repository')
    args = parser.parse_args()
    if args.refresh_inventory:
        refresh()
    manifest = build(args.output)
    print('Built', len(manifest['components']), 'components from explicit source inventory')
