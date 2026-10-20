"""Assemble explicitly named Release assets; never glob a private workspace."""
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    raise RuntimeError('Public packaging retired: use the signed private offline bundle.')
    output = ROOT / 'dist/public-alpha'
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'repository/manifest.json').read_text())
    installer = ROOT / 'repository/repository.bobbi/repository.bobbi-0.1.0.zip'
    shutil.copyfile(installer, output / installer.name)
    bundle = output / 'bobbi-kodi-components-0.1.0-alpha.1.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_STORED) as archive:
        for row in manifest['components']:
            path = ROOT / 'repository' / row['file']
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Repository package changed')
            info = zipfile.ZipInfo(path.name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    lock = json.loads((ROOT / 'android/toolchain-lock.json').read_text())['engine']
    source = output / 'TorrServer-source-MatriX.147.zip'
    if not source.exists():
        with urlopen('https://codeload.github.com/YouROK/TorrServer/zip/' + lock['commit'], timeout=30) as response:
            raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError('Engine source archive too large')
        source.write_bytes(raw)
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        root = 'TorrServer-' + lock['commit'] + '/'
        if not all(name.startswith(root) for name in names):
            raise ValueError('Engine source commit mismatch')
        if hashlib.sha256(archive.read(root + 'LICENSE')).hexdigest() != lock['license']['sha256']:
            raise ValueError('Engine source license mismatch')
        if not any(name.endswith('/go.mod') for name in names):
            raise ValueError('Missing upstream build dependencies')
    provenance = dict(commit=lock['commit'], repository=lock['repository'], version=lock['version'],
        archive_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), archive_bytes=source.stat().st_size,
        license='GPL-3.0', modified=False,
        build='Upstream build scripts and go.mod/go.sum retained in the corresponding source archive; binary hashes in android/toolchain-lock.json.')
    (ROOT / 'release/torrserver-source.json').write_text(json.dumps(provenance, indent=2) + '\n')
    shutil.copyfile(ROOT / 'release/torrserver-source.json', output / 'torrserver-source.json')
    shutil.copyfile(ROOT / 'repository/manifest.json', output / 'kodi-manifest.json')
    explicit = ['repository.bobbi-0.1.0.zip', 'bobbi-kodi-components-0.1.0-alpha.1.zip',
        'bobbi-tv-0.1.0-alpha.1-android.apk', 'TorrServer-source-MatriX.147.zip',
        'torrserver-source.json', 'kodi-manifest.json', 'android-verification.json']
    checksums = []
    for name in explicit:
        path = output / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing release asset: ' + name)
        checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + name)
    (output / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n', encoding='ascii')
    print('Release assets:', len(explicit) + 1)


if __name__ == '__main__':
    main()
