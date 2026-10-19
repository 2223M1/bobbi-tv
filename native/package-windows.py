"""Build an offline Kodi-containing Windows image from a frozen component set."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--version', default='0.2.0-private.1')
    parser.add_argument('--sequence', type=int, default=2026101901)
    args = parser.parse_args()
    dest = args.destination.resolve()
    if dest.exists():
        raise ValueError('A fresh non-live output directory is required')
    source = ROOT / 'native/.work/kodi/kodi-build.x64/Release'
    if (source / 'kodi.exe').stat().st_size < 20 * 1024 * 1024:
        raise ValueError('Actual Kodi binary required')
    shutil.copytree(source, dest / 'host', ignore=shutil.ignore_patterns(
        'objs', '*.pdb', '*.lib', '*.exp', 'zlibd.dll', '__pycache__', '*.pyc'))
    for name in ('bobbi.exe', 'bobbi-maintenance.exe'):
        shutil.copy2(ROOT / 'native/build/windows-launcher' / name, dest / name)
    redist = Path('D:/AM6B-Project/toolchains/VS2022/VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT')
    for library in redist.glob('*.dll'):
        shutil.copy2(library, dest / 'host' / library.name)
    spec = spec_from_file_location('stage_components', ROOT / 'native/stage-components.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    components = module.stage(args.manifest, dest / 'host')
    (dest / 'host/tools').mkdir()
    shutil.copy2(ROOT / 'tools/private_maintenance.py', dest / 'host/tools/private_maintenance.py')
    shutil.copytree(ROOT / 'native/.work/kodi/LICENSES', dest / 'host/LICENSES')
    shutil.copy2(ROOT / 'native/.work/kodi/LICENSE.md', dest / 'host/LICENSE.md')
    shutil.copy2(ROOT / 'native/README.md', dest / 'README.md')
    result = subprocess.run([str(dest / 'bobbi-maintenance.exe'), '--crypto-self-test'],
                            check=True, capture_output=True, text=True, timeout=30)
    juku_result = subprocess.run([str(dest / 'bobbi-maintenance.exe'), '--juku-self-test'],
                                check=True, capture_output=True, text=True, timeout=30)
    files = {path.relative_to(dest).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(dest.rglob('*')) if path.is_file()}
    receipt = {'version': args.version, 'sequence': args.sequence, 'kodi_commit': 'a3a448d26b8d560a65655dab2cd122994dc4e146',
               'platform': 'windows-x64', 'components': components,
               'crypto_self_test': result.stdout.strip(), 'juku_crypto_self_test': juku_result.stdout.strip(), 'files': files,
               'real_playback_verified': False, 'authenticode_signed': False}
    (dest / 'bobbi-build.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    archive = dest.parent / (dest.name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(dest.rglob('*')):
            if path.is_file():
                output.write(path, dest.name + '/' + path.relative_to(dest).as_posix())
        output.writestr(dest.name + '/portable.flag', 'Portable profile stays beside bobbi.exe.\n')
    print(json.dumps({'path': str(archive), 'bytes': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
