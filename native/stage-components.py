"""Verify a frozen components manifest and stage it into a non-running host image.

This is a build tool, not an in-place updater. No user profile is read or copied.
"""
import argparse
import hashlib
import io
import json
import os
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
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode('utf-8'))
    if manifest.get('channel') == 'source-check' or manifest.get('installable') is False:
        raise ValueError('Source-check components are not an installable generation')
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
        if type(row['bytes']) is not int or not 0 < row['bytes'] <= 1024 ** 3:
            raise ValueError('Invalid component byte count: ' + addon)
        archive = manifest_path.parent.joinpath(*relative.parts)
        with archive.open('rb') as raw_handle:
            data = raw_handle.read(row['bytes'] + 1)
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Component hash mismatch: ' + addon)
        # Parse metadata and extract payloads from the same verified snapshot.
        # Reopening the pathname then swapping ZipFile.fp leaves its directory
        # metadata tied to a separate read and doubles compressed IO/memory.
        with zipfile.ZipFile(io.BytesIO(data), 'r') as zipped:
            names = set()
            meta = ET.fromstring(zipped.read(addon + '/addon.xml'))
            if meta.get('id') != addon or meta.get('version') != row['version']:
                raise ValueError('Component metadata mismatch')
            infos = zipped.infolist()
            for member in infos:
                name = PurePosixPath(member.filename)
                if (name.is_absolute() or '..' in name.parts or '\\' in member.filename or ':' in member.filename or
                    not name.parts or name.parts[0] != addon or
                    member.filename.casefold() in names or
                    ((member.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('Unsafe component member')
                names.add(member.filename.casefold())
            if sum(item.file_size for item in infos) > 1024 ** 3:
                raise ValueError('Oversized component')
            verified_entries = [
                (
                    PurePosixPath(member.filename).parts,
                    member.is_dir(),
                    None if member.is_dir() else zipped.read(member),
                    (member.external_attr >> 16) & 0o777,
                )
                for member in infos
            ]
        archives.append((addon, verified_entries))
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
    receipt_path = host / 'system/bobbi-components.json'
    receipt_path.unlink(missing_ok=True)
    addons_root = host / 'addons'
    for addon, verified_entries in archives:
        destination = addons_root / addon
        if destination.exists():
            raise ValueError('Use a fresh staging image, not a previous component tree: ' + addon)
        for parts, is_dir, payload, unix_mode in verified_entries:
            target = addons_root.joinpath(*parts)
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                if unix_mode & 0o111:
                    os.chmod(target, 0o755)
        if addon not in present:
            # Optional system components start enabled on a new profile but do
            # not override an existing user's decision to disable one.
            ET.SubElement(system_manifest.getroot(), 'addon', optional='true').text = addon
    ET.indent(system_manifest, space='  ')
    system_manifest.write(host / 'system/addon-manifest.xml', encoding='utf-8', xml_declaration=True)
    receipt = {
        'components_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'version': manifest.get('version'),
        'components': rows,
        'profile_copied': False,
        'disabled_upstream_services_for_new_profiles': disabled_upstream_services,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('host', type=Path)
    args = parser.parse_args()
    receipt = stage(args.manifest, args.host)
    print('Verified and staged', len(receipt['components']), 'offline components')
