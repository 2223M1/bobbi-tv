"""Verify a built local preview APK, without installing or connecting to a device."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    apk = ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk'
    lock = json.loads((ROOT / 'android/toolchain-lock.json').read_text())
    prepared = json.loads((ROOT / '.private/toolchain/prepared.json').read_text())
    build_tools = Path(prepared['sdk']) / 'build-tools/35.0.0'
    env = dict(os.environ, JAVA_HOME=prepared['java'])
    env['PATH'] = str(Path(prepared['java']) / 'bin') + os.pathsep + env.get('PATH', '')

    def command(name, *args):
        result = subprocess.run([str(build_tools / name), *map(str, args)],
                                capture_output=True, env=env, check=True, timeout=120)
        return result.stdout.decode('utf-8', errors='strict')

    engines = {}
    with zipfile.ZipFile(apk) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError('APK contains duplicate ZIP entries')
        native = {name for name in names if name.startswith('lib/')}
        expected_native = {'lib/' + abi + '/libbobbi_torrserver.so' for abi in lock['engine']['binaries']}
        if native != expected_native:
            raise ValueError('Unexpected or missing native code')
        for abi, item in lock['engine']['binaries'].items():
            name = 'lib/' + abi + '/libbobbi_torrserver.so'
            data = package.read(name)
            value = hashlib.sha256(data).hexdigest()
            if value != item['sha256'] or len(data) != item['bytes']:
                raise ValueError('Packaged engine differs from locked upstream: ' + abi)
            engines[abi] = {'bytes': len(data), 'sha256': value}
        provenance = json.loads(package.read('assets/engine-provenance.json'))
        if provenance['commit'] != lock['engine']['commit'] or provenance['version'] != lock['engine']['version']:
            raise ValueError('Packaged provenance mismatch')
        if not provenance['binaries']['arm64-v8a']['supports_16k_alignment']:
            raise ValueError('ARM64 input lacks 16KB ELF alignment')

    badging = command('aapt.exe', 'dump', 'badging', apk)
    manifest = command('aapt.exe', 'dump', 'xmltree', apk, 'AndroidManifest.xml')
    for required in ("package: name='org.bobbi.helper'", "sdkVersion:'26'", "targetSdkVersion:'35'",
                     "leanback-launchable-activity: name='org.bobbi.helper.MainActivity'",
                     "native-code: 'arm64-v8a' 'armeabi-v7a'", 'application-debuggable'):
        if required not in badging:
            raise ValueError('Built APK contract missing: ' + required)
    permissions = set(re.findall(r"uses-permission: name='([^']+)'", badging))
    expected_permissions = {'android.permission.' + value for value in (
        'INTERNET', 'FOREGROUND_SERVICE', 'FOREGROUND_SERVICE_SPECIAL_USE', 'POST_NOTIFICATIONS')}
    if permissions != expected_permissions:
        raise ValueError('Unexpected APK permissions')
    if not re.search(r'android:extractNativeLibs[^\n]*0xffffffff', manifest):
        raise ValueError('APK does not request installed native executable extraction')
    service = manifest.split('E: service ', 1)[1]
    if ('org.bobbi.helper.EngineService' not in service
            or not re.search(r'android:exported[^\n]*0x0\s', service)
            or not re.search(r'android:foregroundServiceType[^\n]*0x40000000', service)):
        raise ValueError('APK foreground service ownership/type mismatch')
    if 'E: receiver ' in manifest or 'E: provider ' in manifest:
        raise ValueError('Unexpected receiver or provider')
    signature = command('apksigner.bat', 'verify', '--verbose', '--print-certs', apk)
    if 'Verified using v2 scheme (APK Signature Scheme v2): true' not in signature:
        raise ValueError('APK signature verification lacks v2 success')
    command('zipalign.exe', '-c', '-P', '16', '-v', '4', apk)
    report = {
        'apk': str(apk.relative_to(ROOT)).replace('\\', '/'),
        'bytes': apk.stat().st_size, 'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
        'application_id': 'org.bobbi.helper', 'version': '0.1.0-preview',
        'min_sdk': 26, 'target_sdk': 35, 'extract_native_libs': True,
        'engine': lock['engine']['version'], 'engine_binaries': engines,
        'signature_v2_verified': True, 'zipalign_checked': True,
        'debug_preview_only': True, 'device_installed': False, 'device_playback_verified': False,
        'signer_certificate_sha256': re.search(r'Signer #1 certificate SHA-256 digest: (\w+)', signature).group(1),
    }
    destination = ROOT / '.private/android-apk-verification.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
