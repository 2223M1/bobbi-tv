"""Fetch pinned public Android build inputs into project-private directories.

No device operations, system environment changes, arbitrary URLs or blanket SDK
license acceptance. ``prepare`` installs only the named SDK packages and
answers their standard required license prompt; ``build`` then runs Gradle.
AGP requires platform-tools as well as platform/build-tools; installing this
package does not execute adb or connect to a device.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / 'android'
PRIVATE = ROOT / '.private' / 'toolchain'
LOCK = ANDROID / 'toolchain-lock.json'
HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
         'services.gradle.org', 'downloads.gradle.org', 'dl.google.com', 'raw.githubusercontent.com'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def fetch(item):
    target = PRIVATE / 'downloads' / item['sha256']
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and digest(target) == item['sha256']:
        return target
    if urlsplit(item['url']).scheme != 'https' or urlsplit(item['url']).hostname not in HOSTS:
        raise ValueError('Unapproved build input origin')
    partial = target.with_name(target.name + '.part-' + uuid.uuid4().hex[:8])
    print('Downloading pinned ' + item['url'].rsplit('/', 1)[-1], flush=True)
    with urlopen(Request(item['url'], headers={'User-Agent': 'bobbi-android-build/1'}), timeout=45) as response:
        if urlsplit(response.url).scheme != 'https' or urlsplit(response.url).hostname not in HOSTS:
            raise ValueError('Unapproved build redirect')
        total = 0
        with partial.open('xb') as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > item.get('bytes', 1024 ** 3):
                    raise ValueError('Build input size exceeded')
                output.write(chunk)
    if (item.get('bytes', total) != total or digest(partial) != item['sha256']):
        raise ValueError('Build input checksum/length mismatch')
    partial.replace(target)
    return target


def unpack(archive, name, expected):
    target = PRIVATE / name
    marker = target / '.verified-input'
    if marker.is_file() and marker.read_text() == expected:
        return target
    if target.exists():
        raise ValueError('Existing unverified tool directory: ' + name)
    temporary = target.with_name(target.name + '.unpack-' + uuid.uuid4().hex[:8])
    temporary.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if sum(entry.file_size for entry in entries) > 3 * 1024 ** 3:
            raise ValueError('Tool archive expands beyond limit')
        for entry in entries:
            path = PurePosixPath(entry.filename.replace('\\', '/'))
            mode = entry.external_attr >> 16
            if (path.is_absolute() or '..' in path.parts or ':' in entry.filename
                    or stat.S_ISLNK(mode)):
                raise ValueError('Unsafe archive path')
            package.extract(entry, temporary)
    (temporary / '.verified-input').write_text(expected)
    temporary.rename(target)
    return target


def elf_info(path, expected_machine):
    with path.open('rb') as stream:
        head = stream.read(64)
        if len(head) != 64 or head[:4] != b'\x7fELF' or head[5] != 1 or head[4] not in (1, 2):
            raise ValueError('Expected little-endian Android ELF')
        elf_type, machine = struct.unpack_from('<HH', head, 16)
        if elf_type != 3 or machine != expected_machine:
            raise ValueError('Wrong ELF ABI or non-PIE executable')
        if head[4] == 2:
            phoff = struct.unpack_from('<Q', head, 32)[0]
            phsize, phnum = struct.unpack_from('<HH', head, 54)
        else:
            phoff = struct.unpack_from('<I', head, 28)[0]
            phsize, phnum = struct.unpack_from('<HH', head, 42)
        if not 0 < phnum <= 128 or phsize != (56 if head[4] == 2 else 32):
            raise ValueError('Invalid ELF program headers')
        alignments = []
        page_congruent = True
        interpreter = None
        for index in range(phnum):
            stream.seek(phoff + index * phsize)
            entry = stream.read(phsize)
            if len(entry) != phsize:
                raise ValueError('Truncated ELF program header')
            kind = struct.unpack_from('<I', entry)[0]
            if kind == 1:
                alignments.append(struct.unpack_from('<Q' if head[4] == 2 else '<I', entry,
                                                      48 if head[4] == 2 else 28)[0])
                offset, address = struct.unpack_from('<QQ' if head[4] == 2 else '<II', entry,
                                                     8 if head[4] == 2 else 4)
                page_congruent = page_congruent and (offset - address) % 16384 == 0
            if kind == 3:
                offset = struct.unpack_from('<Q' if head[4] == 2 else '<I', entry,
                                            8 if head[4] == 2 else 4)[0]
                position = stream.tell()
                stream.seek(offset)
                interpreter = stream.read(128).split(b'\0', 1)[0].decode('ascii')
                stream.seek(position)
        expected_interpreter = '/system/bin/linker64' if head[4] == 2 else '/system/bin/linker'
        if not alignments or interpreter != expected_interpreter:
            raise ValueError('Not a verified Android executable')
        return dict(machine=machine, elf_type='PIE', interpreter=interpreter,
                    load_alignments=alignments,
                    supports_16k_alignment=min(alignments) >= 16384 and page_congruent)


def sdk_versions(sdk, lock):
    """Check installed package revisions rather than accepting a stray android.jar."""
    versions = {}
    for package, expected in lock['sdk_revisions'].items():
        source = sdk.joinpath(*package.split(';'), 'source.properties')
        if not source.is_file():
            raise ValueError('Missing SDK package metadata: ' + package)
        values = dict(line.strip().split('=', 1) for line in source.read_text().splitlines()
                      if '=' in line and not line.lstrip().startswith('#'))
        revision = values.get('Pkg.Revision', '').strip()
        if revision != expected:
            raise ValueError('SDK package revision differs from lock: ' + package)
        versions[package] = revision
    return versions


def engine_inputs(lock, downloaded):
    provenance = dict(version=lock['engine']['version'], commit=lock['engine']['commit'],
                      source=lock['engine']['repository'], license='GPL-3.0', binaries={})
    for abi, item in lock['engine']['binaries'].items():
        source = downloaded['engine-' + abi]
        info = elf_info(source, item['elf_machine'])
        if abi == 'arm64-v8a' and not info['supports_16k_alignment']:
            raise ValueError('Upstream ARM64 ELF lacks required 16KB alignment; source rebuild needed')
        target = ANDROID / 'app/src/main/jniLibs' / abi / 'libbobbi_torrserver.so'
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.copy')
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        provenance['binaries'][abi] = dict(sha256=item['sha256'], bytes=item['bytes'], **info)
    assets = ANDROID / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(downloaded['license'], assets / 'TorrServer-GPL-3.0.txt')
    (assets / 'engine-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance


def prepare(lock):
    from prepare_android_design import prepare as prepare_design
    prepare_design()
    if os.name != 'nt':
        raise ValueError('This pinned toolchain bootstrap currently targets Windows x64')
    jobs = {name: lock[name] for name in ('jdk', 'gradle', 'commandline')}
    jobs.update({'engine-' + abi: item for abi, item in lock['engine']['binaries'].items()})
    jobs['license'] = lock['engine']['license']
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {name: pool.submit(fetch, item) for name, item in jobs.items()}
        downloaded = {name: task.result() for name, task in pending.items()}
    paths = {name: unpack(downloaded[name], name + '-' + lock[name]['version'].replace('+', '_'),
                          lock[name]['sha256']) for name in ('jdk', 'gradle', 'commandline')}
    java = next(paths['jdk'].glob('*/bin/java.exe')).parent.parent
    gradle = next(paths['gradle'].glob('*/bin/gradle.bat'))
    manager = paths['commandline'] / 'cmdline-tools/bin/sdkmanager.bat'
    sdk = PRIVATE / 'sdk'
    sdk.mkdir(exist_ok=True)
    env = dict(os.environ, JAVA_HOME=str(java), ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               GRADLE_USER_HOME=str(PRIVATE / 'gradle-home'))
    env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    # Only the three named build dependencies are passed. No blanket --licenses,
    # emulator/NDK installation or adb/device command.
    if not ((sdk / 'platforms/android-35/android.jar').is_file()
            and (sdk / 'build-tools/35.0.0/apksigner.bat').is_file()
            and (sdk / 'platform-tools/adb.exe').is_file()):
        result = subprocess.run([str(manager), '--sdk_root=' + str(sdk), *lock['sdk_packages']],
            input='y\n' * 4, text=True, capture_output=True, env=env, timeout=900)
        (PRIVATE / 'sdk-install.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        result.check_returncode()
    installed_versions = sdk_versions(sdk, lock)
    key = ROOT / '.private/android-preview.keystore'
    if not key.is_file():
        subprocess.run([str(java / 'bin/keytool.exe'), '-genkeypair', '-keystore', str(key),
            '-alias', 'androiddebugkey', '-storepass', 'android', '-keypass', 'android',
            '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
            '-dname', 'CN=bobbi local preview,O=bobbi,C=ZZ'],
            check=True, env=env, timeout=60, capture_output=True)
    engine = engine_inputs(lock, downloaded)
    report = dict(java=str(java), gradle=str(gradle), sdk=str(sdk), engine=engine,
                  sdk_packages=installed_versions, device_installed=False)
    (PRIVATE / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Pinned SDK and real engine inputs prepared; no device installation.', flush=True)
    return gradle, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'build'])
    parser.add_argument('--accept-required-sdk-license', action='store_true',
                        help='Accept only the SDK license prompted for the named build dependencies')
    parser.add_argument('--release', action='store_true', help='Build an unsigned public APK for the separate local signer')
    args = parser.parse_args()
    if not args.accept_required_sdk_license:
        parser.error('Explicit --accept-required-sdk-license is required for SDK package setup')
    lock = json.loads(LOCK.read_text())
    gradle, env = prepare(lock)
    if args.action == 'build':
        repository = ROOT / 'repository/repository.bobbi/repository.bobbi-0.1.0.zip'
        if not repository.is_file():
            raise ValueError('Build the Kodi repository first')
        shutil.copyfile(repository, ANDROID / 'app/src/main/assets/repository.bobbi.zip')
        subprocess.run([str(gradle), '--no-daemon', '--console=plain', 'testDebugUnitTest',
                        'lintRelease' if args.release else 'lintDebug',
                        'assembleRelease' if args.release else 'assembleDebug'], cwd=ANDROID, env=env, check=True, timeout=1800)


if __name__ == '__main__':
    main()
