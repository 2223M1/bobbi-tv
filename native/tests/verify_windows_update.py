"""Exercise real native launcher + bundled Python against signed local updates."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def digest_tree(path):
    return {file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in path.rglob('*') if file.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('test_root', type=Path)
    args = parser.parse_args()
    if args.test_root.exists():
        raise ValueError('Use a fresh throwaway test tree')
    image, bundle, target = args.image.resolve(), args.bundle.resolve(), args.test_root.resolve()
    shutil.copytree(image, target)
    addons = target / 'host/addons'
    sentinel = addons / 'plugin.video.bobbi/native-roundtrip-test-fixture.txt'
    sentinel.write_text('Test-only previous program generation marker.\n')
    before = digest_tree(addons)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0

    def launch(*extra):
        return subprocess.run([str(target / 'bobbi.exe'), '--portable', '--no-launch'] + list(extra),
                              startupinfo=startup, timeout=180).returncode

    assert launch('--apply', str(bundle)) == 0, 'Signed generation failed'
    assert not sentinel.exists(), 'New generation did not replace old component tree'
    applied = digest_tree(addons)
    assert launch('--apply', str(bundle)) != 0, 'Same-sequence replay was accepted'
    assert digest_tree(addons) == applied, 'Rejected replay changed files'
    assert launch('--rollback') == 0, 'Previous generation rollback failed'
    assert digest_tree(addons) == before, 'Rollback did not restore exact previous bytes'
    assert launch('--apply', str(bundle)) != 0, 'Rollback allowed old signed sequence replay'
    assert digest_tree(addons) == before

    corrupt = target.parent / (target.name + '-tampered.bobbi-update.zip')
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(corrupt, 'w') as output:
        for row in source.infolist():
            data = source.read(row)
            if row.filename == 'release.sig':
                data = bytes([data[0] ^ 1]) + data[1:]
            output.writestr(row, data)
    assert launch('--apply', str(corrupt)) != 0, 'Corrupt signature accepted'
    assert digest_tree(addons) == before

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    lock = kernel.CreateFileW(str(target / 'profile/host-lifecycle.lock'), 0xC0000000, 0, None, 4, 128, None)
    assert lock not in (None, ctypes.c_void_p(-1).value)
    try:
        assert launch() != 0, 'Concurrent profile owner was ignored'
    finally:
        kernel.CloseHandle(lock)
    assert digest_tree(addons) == before
    assert launch() == 0, 'Recovery after lifecycle lock release failed'
    result = dict(signed_apply=True, exact_byte_rollback=True, same_sequence_replay_rejected=True,
        replay_after_rollback_rejected=True, tampered_signature_rejected=True,
        concurrent_profile_lock_rejected=True, recovery_after_unlock=True,
        real_native_launcher=True, real_embedded_python=True,
        compared_files=len(before), signed_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        profile='throwaway test fixture only', real_playback_verified=False)
    (target.parent / (target.name + '.verification.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
