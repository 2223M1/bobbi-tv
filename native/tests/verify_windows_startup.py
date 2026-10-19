"""Clean-profile smoke start on a private, never-switched Windows desktop."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('test_root', type=Path)
    parser.add_argument('--installed-shared-profile', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    target = args.test_root.resolve()
    if args.report and args.report.exists():
        raise ValueError('A new evidence path is required')
    if args.installed_shared_profile:
        if target != args.image.resolve() or not (target / 'Uninstall.exe').is_file():
            raise ValueError('Exact installed test generation required')
        profile = Path(os.environ['LOCALAPPDATA']) / 'bobbi TV/profile'
        if profile.exists():
            raise ValueError('Existing shared profile must not be reused by this test')
    else:
        if target.exists():
            raise ValueError('Fresh throwaway profile required')
        shutil.copytree(args.image, target)
        profile = target / 'profile'
    userdata = profile / 'userdata'
    userdata.mkdir(parents=True)
    (userdata / 'guisettings.xml').write_text('''<settings version="2"><resolutions />
<setting id="services.webserver">true</setting>
<setting id="services.webserverport">18089</setting>
<setting id="services.webserverauthentication">false</setting>
<setting id="services.zeroconf">false</setting>
<setting id="services.upnpserver">false</setting>
<setting id="videoscreen.screenmode">WINDOW</setting>
</settings>''')

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                    ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR)] + [
                    (name, wintypes.DWORD) for name in ('dwX', 'dwY', 'dwXSize', 'dwYSize',
                        'dwXCountChars', 'dwYCountChars', 'dwFillAttribute', 'dwFlags')] + [
                    ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                    ('lpReserved2', ctypes.POINTER(ctypes.c_byte)), ('hStdInput', wintypes.HANDLE),
                    ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]

    class PROCESSINFO(ctypes.Structure):
        _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID,
        wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESSINFO)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = 'bobbi-native-smoke-' + uuid.uuid4().hex
    desktop = user.CreateDesktopW(name, None, None, 0, 0x10000000, None)
    if not desktop:
        raise OSError(ctypes.get_last_error(), 'Private desktop unavailable')
    startup, process = STARTUPINFO(), PROCESSINFO()
    startup.cb, startup.lpDesktop = ctypes.sizeof(STARTUPINFO), name
    command = ctypes.create_unicode_buffer('"' + str(target / 'bobbi.exe') + '"' +
        ('' if args.installed_shared_profile else ' --portable'))
    result = {'private_desktop': True, 'real_playback_verified': False,
              'installed_mode': args.installed_shared_profile, 'profile': str(profile),
              'fresh_profile': True, 'account_state_copied': False,
              'fixture': 'Only minimal GUI/RPC settings; no existing Kodi/account/profile copied.'}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def rpc(method, params=None):
        request = urllib.request.Request('http://127.0.0.1:18089/jsonrpc',
            data=json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params or {})).encode(),
            headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=2) as response:
            return json.load(response)

    try:
        if not kernel.CreateProcessW(None, command, None, None, False, 0x08000000, None,
                                      str(target), ctypes.byref(startup), ctypes.byref(process)):
            raise OSError(ctypes.get_last_error(), 'Hidden launcher start failed')
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                try:
                    result['ping'] = rpc('JSONRPC.Ping')
                    break
                except Exception:
                    time.sleep(.5)
            if 'ping' in result:
                time.sleep(8)  # Let concurrent home widgets and background services initialize.
                result['labels'] = rpc('XBMC.GetInfoLabels', {'labels': ['System.BuildVersion', 'Skin.CurrentTheme']})
                result['skin'] = rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.skin'})
                result['native_methods'] = {}
                for method in ('Player.BobiControl', 'Player.BobiFullscreen', 'Player.BobiIntent',
                               'Player.BobiState', 'Player.BobiSubtitle', 'Player.BobiSubtitleFile',
                               'Player.BobiSubtitles'):
                    schema = rpc('JSONRPC.Introspect', {'filter': {'id': method, 'type': 'method'}})
                    result['native_methods'][method] = method in schema.get('result', {}).get('methods', {})
                result['addons'] = rpc('Addons.GetAddons', {'enabled': True, 'properties': ['version', 'name']})
                result['quit'] = rpc('Application.Quit')
            if kernel.WaitForSingleObject(process.hProcess, 15000) != 0:
                kernel.TerminateProcess(process.hProcess, 90)  # Only this test's lifecycle owner.
                kernel.WaitForSingleObject(process.hProcess, 5000)
                result['forced_test_cleanup'] = True
            exit_code = wintypes.DWORD()
            kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code))
            result['launcher_exit'] = exit_code.value
        finally:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
    finally:
        user.CloseDesktop(desktop)
    log = profile / 'kodi.log'
    if log.exists():
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
        result['log_errors'] = [line for line in lines if 'error <' in line.lower() or 'Error Type:' in line][-30:]
    output = args.report or target.parent / (target.name + '.verification.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(output), 'ping': result.get('ping'),
                      'exit': result.get('launcher_exit'), 'errors': result.get('log_errors', [])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
