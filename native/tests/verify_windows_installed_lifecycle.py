"""Exercise the installed launcher and uninstall, preserving a new shared profile."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import winreg


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'native/build/windows-installer-1902'
PROFILE = Path(os.environ['LOCALAPPDATA']) / 'bobbi TV/profile'
ORIGINAL_KODI = Path(os.environ['APPDATA']) / 'Kodi'
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\bobbiTV-0.2.0-private.1-2026101902'
SHORTCUT = (Path(os.environ['APPDATA']) /
    'Microsoft/Windows/Start Menu/Programs/bobbi TV/bobbi TV 0.2.0-private.1-2026101902.lnk')
STARTUP_REPORT = ROOT / 'review-evidence/native-windows-installed-startup-1902-20261019.json'
REPORT = ROOT / 'review-evidence/native-windows-uninstall-1902-20261019.json'


def hashes(root):
    result = {}
    for file in sorted(root.rglob('*')):
        if file.is_symlink():
            raise ValueError('Symlink not allowed in test tree')
        if file.is_file():
            result[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def registry_exists():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY):
            return True
    except FileNotFoundError:
        return False


def main():
    if PROFILE.exists() or STARTUP_REPORT.exists() or REPORT.exists():
        raise ValueError('The shared profile and receipts must not already exist')
    original_before = ORIGINAL_KODI.exists()
    if original_before:
        raise ValueError('Unexpected original Kodi installation; stop this isolated test')
    expected = (ROOT / 'native/build/windows-installer-1902').resolve()
    if TARGET.resolve() != expected or any(p.is_symlink() for p in (TARGET, *TARGET.parents)):
        raise ValueError('Unexpected install location')
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        installed = Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve()
    if installed != expected:
        raise ValueError('Uninstall registration does not belong to this test')
    receipt = json.loads((TARGET / 'bobbi-build.json').read_text(encoding='utf-8'))
    if receipt['sequence'] != 2026101902:
        raise ValueError('Wrong generation')
    subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ROOT / 'native/tests/verify_windows_startup.py'),
        str(TARGET), str(TARGET), '--installed-shared-profile', '--report', str(STARTUP_REPORT)],
        check=True, timeout=100)
    startup = json.loads(STARTUP_REPORT.read_text(encoding='utf-8'))
    assert startup['ping']['result'] == 'pong'
    assert startup['skin']['result']['value'] == 'skin.bobbi.cinema'
    assert startup['launcher_exit'] == 0 and not startup.get('forced_test_cleanup')
    assert all(startup['native_methods'].values())
    assert not list(PROFILE.rglob('115-os_linux.json')), 'Unexpected credentials appeared'
    before = hashes(PROFILE)
    assert before, 'Real startup did not create a profile'
    # Exact registered test directory checked above; no other install is targeted.
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    uninstaller = subprocess.run([str(TARGET / 'Uninstall.exe'), '/S'],
        cwd=str(ROOT), startupinfo=startupinfo, timeout=60)
    deadline = time.monotonic() + 45
    while TARGET.exists() and time.monotonic() < deadline:
        time.sleep(.25)
    assert uninstaller.returncode == 0, 'Uninstaller failed'
    assert not TARGET.exists(), 'Installed generation remains after uninstall'
    assert not registry_exists(), 'Test uninstall registration remains'
    assert not SHORTCUT.exists(), 'Test Start Menu shortcut remains'
    after = hashes(PROFILE)
    assert after == before, 'Uninstall changed the shared test profile bytes'
    assert ORIGINAL_KODI.exists() == original_before
    result = {
        'schema': 1, 'release_sequence': 2026101902,
        'installed_startup_verified': True, 'startup_evidence': str(STARTUP_REPORT.relative_to(ROOT)),
        'uninstall_executed': True, 'uninstaller_exit': uninstaller.returncode,
        'exact_install_target': str(expected), 'install_target_removed': True,
        'registration_removed': True, 'start_menu_shortcut_removed': True,
        'shared_profile': str(PROFILE), 'shared_profile_existed_before_test': False,
        'shared_profile_retained': True, 'shared_profile_files_compared_sha256': len(before),
        'shared_profile_unchanged': True,
        'shared_profile_tree_digest_sha256': hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'account_state_copied': False, 'credentials_present': False,
        'original_kodi_profile_untouched': True, 'real_playback_verified': False,
        'disposition': 'The new empty-account shared profile is retained for subsequent local QR authorization. No original Kodi profile was used.'
    }
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
