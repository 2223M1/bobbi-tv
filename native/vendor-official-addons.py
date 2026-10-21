"""Import fixed official Kodi Omega runtime dependencies; never account state."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from provenance_document import read_source, write_source
PACKAGES = {
    'script.module.requests': ('2.31.0', 67576),
    'script.module.routing': ('0.2.3+matrix.1', 25369),
    'script.module.certifi': ('2023.5.7', 162689),
    'script.module.chardet': ('5.1.0', 204491),
    'script.module.idna': ('3.10.0', 73349),
    'script.module.urllib3': ('2.2.3', 130842),
}


def fetch(entry):
    addon, (version, size) = entry
    url = f'https://mirrors.kodi.tv/addons/omega/{addon}/{addon}-{version}.zip'
    archive = ROOT / 'native/downloads' / f'{addon}-{version}.zip'
    if not archive.exists():
        subprocess.run(['curl.exe', '--location', '--fail', '--connect-timeout', '20',
                        '--max-time', '120', '--output', str(archive), url],
                       check=True, capture_output=True)
    if archive.stat().st_size != size:
        raise ValueError('Official index length mismatch: ' + addon)
    return addon, version, archive, url


def main():
    lock_path = ROOT / 'release/kodi-vendors.json'
    lock = json.loads(read_source(ROOT, 'release/kodi-vendors.json'))
    for addon, version, archive, url in ThreadPoolExecutor(max_workers=4).map(fetch, PACKAGES.items()):
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if addon in lock and lock[addon]['archive_sha256'] != digest:
            raise ValueError('Previously locked archive changed: ' + addon)
        records = {}
        with zipfile.ZipFile(archive) as package:
            meta = ET.fromstring(package.read(addon + '/addon.xml'))
            if meta.get('id') != addon or meta.get('version') != version:
                raise ValueError('Wrong official package metadata')
            for member in package.infolist():
                path = PurePosixPath(member.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in member.filename or
                        not path.parts or path.parts[0] != addon or
                        (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('Unsafe archive member')
                if member.is_dir():
                    continue
                content = package.read(member)
                target = ROOT / 'third_party/addons' / path
                if target.exists() and target.read_bytes() != content:
                    raise ValueError('Refusing to overwrite an existing vendor edit')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                records[PurePosixPath(*path.parts[1:]).as_posix()] = hashlib.sha256(content).hexdigest()
        lock[addon] = {
            'repository': 'https://mirrors.kodi.tv/addons/omega/', 'version': version,
            'archive_url': url, 'archive_sha256': digest, 'archive_bytes': archive.stat().st_size,
            'license': meta.findtext('./extension[@point="xbmc.addon.metadata"]/license'),
            'upstream': meta.findtext('./extension[@point="xbmc.addon.metadata"]/source'),
            'files': records,
        }
        print(addon, version, digest)
    write_source(ROOT, 'release/kodi-vendors.json', (json.dumps(lock, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


if __name__ == '__main__':
    main()
