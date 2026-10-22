"""Fetch pinned, unmodified skin dependencies."""
from io import BytesIO
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'script.skinvariables': ('jurialmunkey/script.skinvariables', '45be183640d4a3f1be96ad97c7d0032b2a174dcb'),
    'script.module.jurialmunkey': ('jurialmunkey/script.module.jurialmunkey', '8f42fb5f4698f3e4552f38955964b2f3843dba69'),
    'script.module.infotagger': ('jurialmunkey/script.module.infotagger', '0118f53c9cf68a6625794d07af607cac1e920064'),
}


def main():
    manifest = {}
    for addon, (repo, commit) in SOURCES.items():
        destination = ROOT / 'third_party/addons' / addon
        url = 'https://codeload.github.com/' + repo + '/zip/' + commit
        with urlopen(url, timeout=30) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('Upstream archive too large')
        files = {}
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            for item in archive.infolist():
                parts = PurePosixPath(item.filename).parts[1:]
                if not parts or item.is_dir() or parts[0].startswith('.') or '__pycache__' in parts:
                    continue
                if '..' in parts or any('\\' in part or ':' in part for part in parts) or item.file_size > 8 * 1024 * 1024:
                    raise ValueError('Unsafe upstream path')
                name = '/'.join(parts)
                payload = archive.read(item)
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != payload:
                    raise ValueError('Existing vendored file changed: ' + addon + '/' + name)
                target.write_bytes(payload)
                files[name] = hashlib.sha256(payload).hexdigest()
        if not (destination / 'addon.xml').exists():
            raise ValueError('Upstream source incomplete')
        manifest[addon] = dict(repository='https://github.com/' + repo, commit=commit,
            archive_sha256=hashlib.sha256(raw).hexdigest(), files=files)
        print(addon, len(files), 'pinned files')
    (ROOT / 'release/kodi-vendors.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
