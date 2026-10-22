"""Check a locally built preview APK; device playback remains unverified."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile
from prepare_android_design import FONTS

ROOT = Path(__file__).resolve().parents[1]


def check_contents(path, lock):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or 'AndroidManifest.xml' not in names or 'classes.dex' not in names:
            raise ValueError('Invalid APK inventory')
        engines = {name.split('/')[1] for name in names if name.endswith('/libbobbi_torrserver.so')}
        if engines != set(lock['engine']['binaries']):
            raise ValueError('Universal ARM APK is missing an engine ABI')
        for abi, item in lock['engine']['binaries'].items():
            raw = archive.read('lib/' + abi + '/libbobbi_torrserver.so')
            if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('Packaged engine differs from pinned upstream input')
        provenance = json.loads(archive.read('assets/engine-provenance.json'))
        if provenance.get('commit') != lock['engine']['commit']:
            raise ValueError('Packaged source provenance mismatch')
        for filename, expected in FONTS.items():
            if hashlib.sha256(archive.read('assets/fonts/' + filename)).hexdigest() != expected:
                raise ValueError('Packaged cinema font differs from reviewed input')
        repository = ROOT / 'repository/repository.bobbi/repository.bobbi-0.1.0.zip'
        if archive.read('assets/repository.bobbi.zip') != repository.read_bytes():
            raise ValueError('Bundled Kodi installer does not match repository build')
    return sorted(engines)


def verify(path):
    path = Path(path).resolve()
    lock = json.loads((ROOT / 'android/toolchain-lock.json').read_text())
    prepared = json.loads((ROOT / '.private/toolchain/prepared.json').read_text())
    abis = check_contents(path, lock)
    sdk, java = Path(prepared['sdk']), Path(prepared['java'])
    build_tools = sdk / 'build-tools/35.0.0'
    env = dict(os.environ, JAVA_HOME=str(java))
    env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    signature = subprocess.run([str(build_tools / 'apksigner.bat'), 'verify', '--verbose', '--print-certs', str(path)],
        env=env, check=True, capture_output=True, text=True, timeout=60).stdout
    digest = re.search(r'Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]{64})', signature)
    if not digest or 'Verified using v2 scheme (APK Signature Scheme v2): true' not in signature:
        raise ValueError('APK signature validation did not establish a v2 signer')
    badging = subprocess.run([str(build_tools / 'aapt.exe'), 'dump', 'badging', str(path)],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=60).stdout
    for required in ["name='org.bobbi.helper'", "sdkVersion:'26'", "targetSdkVersion:'35'",
                     "launchable-activity: name='org.bobbi.helper.MainActivity'",
                     "native-code: 'arm64-v8a' 'armeabi-v7a'"]:
        if required not in badging:
            raise ValueError('APK manifest contract changed: ' + required)
    # Current artifact is intentionally a local development preview, not a
    # public release key, not installation/playback certification.
    debug = 'application-debuggable' in badging
    return {'status': 'local-debug-preview' if debug else 'public-alpha-device-unverified', 'debuggable': debug, 'file': path.name,
            'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'signer_sha256': digest.group(1).lower(), 'abis': abis,
            'minimum_android_api': 26, 'requires_model_selection': False,
            'device_installed': False, 'device_playback_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk')
    args = parser.parse_args()
    print(json.dumps(verify(args.apk), indent=2))
