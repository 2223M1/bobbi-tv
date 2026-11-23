"""Local release signer. Persistent key never enters the repository or argv."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from verify_android_apk import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    private = ROOT / '.private'
    prepared = json.loads((private / 'toolchain/prepared.json').read_text())
    java = Path(prepared['java'])
    sdk = Path(prepared['sdk'])
    secret_path = private / 'release-signing.json'
    key = private / 'bobbi-release.jks'
    if secret_path.is_file():
        password = json.loads(secret_path.read_text())['password']
    else:
        if key.exists():
            raise ValueError('Existing key requires its original password; never regenerate')
        password = secrets.token_urlsafe(48)
        fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'password': password}, stream)
    env = dict(os.environ, JAVA_HOME=str(java), BOBBI_SIGN_PASSWORD=password)
    env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    if not key.exists():
        subprocess.run([str(java / 'bin/keytool.exe'), '-genkeypair', '-keystore', str(key),
            '-storetype', 'JKS', '-alias', 'bobbi-release', '-storepass:env', 'BOBBI_SIGN_PASSWORD',
            '-keypass:env', 'BOBBI_SIGN_PASSWORD', '-keyalg', 'RSA', '-keysize', '3072',
            '-validity', '10000', '-dname', 'CN=bobbi TV,O=bobbi TV,C=CN'],
            env=env, check=True, capture_output=True, timeout=60)
    destination = ROOT / 'dist/public-alpha'
    destination.mkdir(parents=True, exist_ok=True)
    apk = destination / 'bobbi-tv-0.1.0-alpha.1-android.apk'
    subprocess.run([str(sdk / 'build-tools/35.0.0/apksigner.bat'), 'sign', '--ks', str(key),
        '--ks-key-alias', 'bobbi-release', '--ks-pass', 'env:BOBBI_SIGN_PASSWORD',
        '--key-pass', 'env:BOBBI_SIGN_PASSWORD', '--out', str(apk),
        str(ROOT / 'android/app/build/outputs/apk/release/app-release-unsigned.apk')],
        env=env, check=True, capture_output=True, timeout=120)
    result = verify(apk)
    if result['debuggable']:
        raise ValueError('Public APK must not be debuggable')
    (destination / 'android-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    (ROOT / 'release/android-signing-certificate.sha256').write_text(result['signer_sha256'] + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
