"""Package frozen add-ons with already-built native ABI engines, in a new tree."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys


REVIEWED_COMPONENT_ADDITION = 'plugin.video.bobbi.torrent'


def validate_component_inventory(previous, frozen, allowed_addition=None):
    """Keep existing native inventory closed except for the reviewed 21->22 delta."""
    def ids(manifest):
        rows = manifest.get('components')
        if not isinstance(rows, list) or not rows:
            raise ValueError('A nonempty component inventory is required')
        values = [row.get('id') if isinstance(row, dict) else None for row in rows]
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError('Component inventory IDs must be nonempty strings')
        if len({value.casefold() for value in values}) != len(values):
            raise ValueError('Component inventory IDs must be unique')
        return set(values)

    old_ids, new_ids = ids(previous), ids(frozen)
    if allowed_addition not in (None, REVIEWED_COMPONENT_ADDITION):
        raise ValueError('The requested component addition has not been reviewed')
    added, removed = new_ids - old_ids, old_ids - new_ids
    if added or removed:
        if (allowed_addition != REVIEWED_COMPONENT_ADDITION
                or added != {REVIEWED_COMPONENT_ADDITION} or removed
                or len(old_ids) != 21 or len(new_ids) != 22):
            raise ValueError('Changing native component inventory needs an explicit review')
    elif allowed_addition is not None:
        raise ValueError('The explicitly approved component addition is not present')
    return {'previous_count': len(old_ids), 'current_count': len(new_ids),
            'added_components': sorted(added), 'removed_components': sorted(removed)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--abi', choices=['arm64', 'armv7'], required=True)
    parser.add_argument('--allow-component-addition', choices=[REVIEWED_COMPONENT_ADDITION],
                        help='Explicitly approve only the reviewed 21-to-22 component migration')
    args = parser.parse_args()
    task = args.root.resolve()
    if os.name != 'posix' or str(task) != '/opt/bobbi-native-20261019':
        raise ValueError('Use the isolated existing Linux build workspace')
    manifest = args.manifest.resolve()
    frozen = json.loads(manifest.read_text(encoding='utf-8'))
    component_ids = {row['id'] for row in frozen['components']}
    source = task / ('build-' + args.abi) / 'tools/android/packaging'
    destination = task / ('package-' + args.abi + '-' + str(args.sequence))
    if destination.exists():
        raise ValueError('A new packaging tree is required')
    previous = json.loads((source / 'xbmc/assets/system/bobbi-components.json').read_text())
    inventory_transition = validate_component_inventory(previous, frozen, args.allow_component_addition)
    destination.mkdir()
    for filename in ('build.gradle', 'gradle.properties', 'settings.gradle'):
        shutil.copy2(source / filename, destination / filename)
    app = destination / 'xbmc'
    app.mkdir()
    for filename in ('build.gradle', 'AndroidManifest.xml'):
        shutil.copy2(source / 'xbmc' / filename, app / filename)
    old_addons = source / 'xbmc/assets/addons'

    def ignore(path, names):
        return [name for name in names if name in component_ids] if Path(path) == old_addons else []

    for dirname in ('assets', 'java', 'lib', 'res'):
        shutil.copytree(source / 'xbmc' / dirname, app / dirname, ignore=ignore)
    spec = importlib.util.spec_from_file_location('stage_components', Path(__file__).with_name('stage-components.py'))
    stager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stager)
    receipt = stager.stage(manifest, app / 'assets')
    # This one-off throwaway signer is not the release identity. The Windows
    # signing step verifies all frozen bytes, ABI and the existing final signer.
    java = task / 'toolchain/jdk-17.0.18+8'
    sdk = task / 'toolchain/sdk'
    if not sdk.is_dir():
        raise ValueError('Pinned Android SDK not found')
    env = dict(os.environ, JAVA_HOME=str(java), ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               BOBBI_ANDROID_VERSION_CODE=str(args.sequence),
               KODI_ANDROID_KEY_ALIAS='build-only',
               KODI_ANDROID_STORE_FILE=str(destination / 'build-only.keystore'))
    env['KODI_ANDROID_STORE_PASSWORD'] = secrets.token_urlsafe(32)
    env['KODI_ANDROID_KEY_PASSWORD'] = env['KODI_ANDROID_STORE_PASSWORD']
    subprocess.run([str(java / 'bin/keytool'), '-genkeypair', '-alias', 'build-only',
        '-keyalg', 'RSA', '-keysize', '2048', '-validity', '2',
        '-dname', 'CN=bobbi temporary native packaging',
        '-keystore', env['KODI_ANDROID_STORE_FILE'],
        '-storepass:env', 'KODI_ANDROID_STORE_PASSWORD', '-keypass:env', 'KODI_ANDROID_KEY_PASSWORD'],
        check=True, env=env, capture_output=True, timeout=30)
    subprocess.run([sys.executable, str(Path(__file__).with_name('gradle-isolated.py')),
        str(task), '--no-daemon', '--offline', '-p', str(destination), ':xbmc:assembleRelease'],
        check=True, env=env, timeout=600)
    output = app / 'build/outputs/apk/release/xbmc-release.apk'
    if not output.is_file():
        raise ValueError('Gradle did not produce a host APK')
    print(json.dumps({'apk': str(output), 'sequence': args.sequence,
        'components_manifest_sha256': receipt['components_manifest_sha256'],
        'inventory_transition': inventory_transition,
        'native_engine_recompiled': False, 'final_release_signed': False}))


if __name__ == '__main__':
    main()
