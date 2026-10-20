"""Verify a frozen components manifest and stage it into a non-running host image.

This is a build tool, not an in-place updater. No user profile is read or copied.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile


def stage(manifest_path, host):
    manifest_path, host = Path(manifest_path).resolve(), Path(host).resolve()
    if not (host / 'system/addon-manifest.xml').is_file():
        raise ValueError('Not a Kodi host build/staging tree')
    # Refuse installation/userdata trees; this tool never updates a live profile.
    if (host / 'portable_data').exists() or (host / 'userdata/guisettings.xml').exists():
        raise ValueError('Existing user profile is not a build staging destination')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = manifest['components']
    seen, archives = set(), []
    for row in rows:
        addon = row['id']
        if not re.fullmatch(r'[a-z0-9_.-]+', addon) or addon in seen:
            raise ValueError('Duplicate/invalid component id')
        seen.add(addon)
        relative = PurePosixPath(row['file'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in row['file'] or ':' in row['file']:
            raise ValueError('Unsafe package path')
        archive = manifest_path.parent.joinpath(*relative.parts)
        data = archive.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Component hash mismatch: ' + addon)
        with zipfile.ZipFile(archive) as zipped:
            names = set()
            meta = ET.fromstring(zipped.read(addon + '/addon.xml'))
            if meta.get('id') != addon or meta.get('version') != row['version']:
                raise ValueError('Component metadata mismatch')
            for member in zipped.infolist():
                name = PurePosixPath(member.filename)
                if (name.is_absolute() or '..' in name.parts or '\\' in member.filename or ':' in member.filename or
                    not name.parts or name.parts[0] != addon or
                    member.filename.casefold() in names or
                    ((member.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('Unsafe component member')
                names.add(member.filename.casefold())
            if sum(item.file_size for item in zipped.infolist()) > 1024 ** 3:
                raise ValueError('Oversized component')
        archives.append((addon, archive))
    if any((host / 'addons' / addon).exists() for addon, _ in archives):
        raise ValueError('Use a fresh staging image, not a previous component tree')
    if not {'skin.bobbi.cinema', 'resource.uisounds.bobbi-modern', 'plugin.video.bobbi'} <= seen:
        raise ValueError('Incomplete user-facing host image')
    system_manifest = ET.parse(host / 'system/addon-manifest.xml')
    disabled_upstream_services = []
    for node in list(system_manifest.getroot().findall('addon')):
        if node.text == 'service.xbmc.versioncheck' and node.get('optional') == 'true':
            system_manifest.getroot().remove(node)
            disabled_upstream_services.append(node.text)
    present = {node.text for node in system_manifest.getroot().findall('addon')}
    for addon, archive in archives:
        destination = host / 'addons' / addon
        if destination.exists():
            raise ValueError('Use a fresh staging image, not a previous component tree: ' + addon)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(host / 'addons')
        if addon not in present:
            # Optional system components start enabled on a new profile but do
            # not override an existing user's decision to disable one.
            ET.SubElement(system_manifest.getroot(), 'addon', optional='true').text = addon
    ET.indent(system_manifest, space='  ')
    system_manifest.write(host / 'system/addon-manifest.xml', encoding='utf-8', xml_declaration=True)
    receipt = {'components_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
               'version': manifest.get('version'), 'components': rows, 'profile_copied': False,
               'disabled_upstream_services_for_new_profiles': disabled_upstream_services}
    (host / 'system/bobbi-components.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('host', type=Path)
    args = parser.parse_args()
    receipt = stage(args.manifest, args.host)
    print('Verified and staged', len(receipt['components']), 'offline components')
