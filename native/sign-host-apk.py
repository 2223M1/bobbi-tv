"""Re-sign an actual Kodi host APK with the existing release identity only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--private-root', type=Path, required=True)
    parser.add_argument('--abi', choices=['arm64-v8a', 'armeabi-v7a'], required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.input) as apk:
        expected_machine = 183 if args.abi == 'arm64-v8a' else 40
        native_libraries = {}
        for name in apk.namelist():
            if name.startswith('lib/') and name.endswith('.so'):
                if not name.startswith('lib/' + args.abi + '/'):
                    raise ValueError('Unexpected ABI in split APK')
                data = apk.read(name)
                if data[:4] != b'\x7fELF' or struct.unpack_from('<H', data, 18)[0] != expected_machine:
                    raise ValueError('Native library CPU mismatch: ' + name)
                native_libraries[name] = hashlib.sha256(data).hexdigest()
        native = apk.getinfo('lib/' + args.abi + '/libkodi.so')
        if native.file_size < 20 * 1024 * 1024:
            raise ValueError('Not a real native Kodi host')
        if 'assets/system/bobbi-components.json' not in apk.namelist():
            raise ValueError('Missing frozen offline components receipt')
        components = json.loads(apk.read('assets/system/bobbi-components.json'))
        manifest_bytes = args.manifest.read_bytes()
        manifest = json.loads(manifest_bytes)
        if hashlib.sha256(manifest_bytes).hexdigest() != components['components_manifest_sha256']:
            raise ValueError('APK is not using the requested frozen generation')
        component_files = 0
        for component in manifest['components']:
            component_archive = args.manifest.parent / component['file']
            raw = component_archive.read_bytes()
            if len(raw) != component['bytes'] or hashlib.sha256(raw).hexdigest() != component['sha256']:
                raise ValueError('Frozen component archive changed after build')
            with zipfile.ZipFile(component_archive) as source:
                for row in source.infolist():
                    if not row.is_dir():
                        if apk.read('assets/addons/' + row.filename) != source.read(row):
                            raise ValueError('APK component byte drift: ' + row.filename)
                        component_files += 1
        if ('lib/' + args.abi + '/libCryptodome_Cipher__raw_aes.so' not in native_libraries or
                not any(name.startswith('assets/python3.11/lib/python3.11/site-packages/Cryptodome/')
                        for name in apk.namelist())):
            raise ValueError('Missing ABI-native Cryptodome runtime closure')
    private = args.private_root.resolve()
    # These files are local inputs only. Never generate/rotate a key implicitly.
    key = private / 'bobbi-release.jks'
    secret = json.loads((private / 'release-signing.json').read_text(encoding='utf-8'))['password']
    prepared = json.loads((private / 'toolchain/prepared.json').read_text(encoding='utf-8'))
    java, sdk = Path(prepared['java']), Path(prepared['sdk'])
    if not key.is_file():
        raise ValueError('Original release keystore is required')
    env = dict(os.environ, JAVA_HOME=str(java), BOBBI_SIGN_PASSWORD=secret)
    env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    signer = str(sdk / 'build-tools/35.0.0/apksigner.bat')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([signer, 'sign', '--ks', str(key), '--ks-key-alias', 'bobbi-release',
                    '--ks-pass', 'env:BOBBI_SIGN_PASSWORD', '--key-pass', 'env:BOBBI_SIGN_PASSWORD',
                    '--out', str(args.output), str(args.input)], env=env, check=True,
                   capture_output=True, timeout=180)
    verification = subprocess.run([signer, 'verify', '--verbose', '--print-certs', str(args.output)],
                                  env=env, check=True, capture_output=True, text=True, timeout=60).stdout
    signer_sha = re.search(r'Signer #1 certificate SHA-256 digest: ([0-9a-f]+)', verification).group(1)
    expected = (ROOT / 'release/android-signing-certificate.sha256').read_text().strip()
    if signer_sha != expected:
        raise ValueError('Release certificate identity changed')
    aapt = str(sdk / 'build-tools/35.0.0/aapt.exe')
    info = subprocess.run([aapt, 'dump', 'badging', str(args.output)], env=env, check=True,
                          capture_output=True, text=True, timeout=60).stdout
    if ("package: name='org.bobbi.helper'" not in info or "sdkVersion:'26'" not in info or
            "targetSdkVersion:'34'" not in info or 'application-debuggable' in info or
            "native-code: '" + args.abi + "'" not in info):
        raise ValueError('Wrong package identity, API level or debuggable release')
    version_code = int(re.search(r"versionCode='(\d+)'", info).group(1))
    if version_code < 2026101901:
        raise ValueError('APK cannot update the existing private host generation')
    result = {'abi': args.abi, 'application_id': 'org.bobbi.helper', 'min_sdk': 26,
              'version_code': version_code, 'target_sdk': 34,
              'signer_sha256': signer_sha, 'kodi_native_bytes': native.file_size,
              'components_manifest_sha256': components['components_manifest_sha256'],
              'components_count': len(components['components']), 'component_files_verified': component_files,
              'native_libraries': native_libraries,
              'bytes': args.output.stat().st_size,
              'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'real_device_verified': False}
    args.output.with_suffix('.verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('abi', 'version_code', 'components_count',
        'component_files_verified', 'bytes', 'sha256', 'real_device_verified')}, indent=2))


if __name__ == '__main__':
    main()
