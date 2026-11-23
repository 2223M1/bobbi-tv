"""Long-lived isolated native host for parent-controlled account/media trials.

No account import and no movie selection happens here. Authentication material
is written only to this test directory and is never printed or reported.
"""
import argparse
import base64
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import secrets
import time
import urllib.request
import uuid


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('installed', type=Path)
    parser.add_argument('--port', type=int, default=18090)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--launch-prepared', action='store_true')
    parser.add_argument('--visible', action='store_true', help='Use the interactive desktop for actual rendering validation')
    args = parser.parse_args()
    root = args.installed.resolve()
    profile = root / 'profile'
    if not (root / 'Uninstall.exe').is_file() or (profile.exists() and not args.launch_prepared):
        raise ValueError('A genuine installed test generation and absent portable profile are required')
    userdata = profile / 'userdata'
    marker = profile / 'validation-profile.json'
    expected_marker = {'schema': 1, 'installed': str(root), 'test_profile': True}
    if args.launch_prepared:
        if args.prepare_only or json.loads(marker.read_text(encoding='utf-8')) != expected_marker:
            raise ValueError('Only this pre-created test profile may be launched')
        auth = json.loads((profile / 'validation-rpc.json').read_text(encoding='utf-8'))
        password, args.port = auth['password'], auth['port']
    else:
        userdata.mkdir(parents=True)
        password = secrets.token_urlsafe(32)
        auth = dict(host='127.0.0.1', port=args.port, username='bobbi-validation', password=password)
        (profile / 'validation-rpc.json').write_text(json.dumps(auth), encoding='utf-8')
        marker.write_text(json.dumps(expected_marker), encoding='utf-8')
        (userdata / 'guisettings.xml').write_text('''<settings version="2"><resolutions />
<setting id="services.webserver">true</setting>
<setting id="services.webserverport">%d</setting>
<setting id="services.webserverauthentication">true</setting>
<setting id="services.webserverusername">bobbi-validation</setting>
<setting id="services.webserverpassword">%s</setting>
<setting id="services.zeroconf">false</setting>
<setting id="services.upnpserver">false</setting>
<setting id="videoscreen.screenmode">WINDOW</setting>
</settings>''' % (args.port, password), encoding='utf-8')
    if args.prepare_only:
        print(json.dumps({'profile': str(profile), 'player_started': False,
            'tmdb_settings': str(userdata / 'addon_data/plugin.video.bobbi/settings.xml'),
            'future_runtime_json': str(userdata / 'addon_data/script.module.bobbi.platform/runtime.json')},
            ensure_ascii=False), flush=True)
        return
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
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = 'bobbi-account-trial-' + uuid.uuid4().hex
    desktop = None if args.visible else user.CreateDesktopW(name, None, None, 0, 0x10000000, None)
    if not args.visible and not desktop:
        raise OSError(ctypes.get_last_error(), 'Private desktop unavailable')
    startup, process = STARTUPINFO(), PROCESSINFO()
    startup.cb, startup.lpDesktop = ctypes.sizeof(STARTUPINFO), None if args.visible else name
    if args.visible:
        startup.dwFlags, startup.wShowWindow = 1, 1
    command = ctypes.create_unicode_buffer('"' + str(root / 'bobbi.exe') + '" --portable')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    authorization = 'Basic ' + base64.b64encode(('bobbi-validation:' + password).encode()).decode()

    def rpc(method):
        request = urllib.request.Request('http://127.0.0.1:%d/jsonrpc' % args.port,
            data=json.dumps(dict(jsonrpc='2.0', id=1, method=method)).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': authorization})
        with opener.open(request, timeout=2) as response:
            return json.load(response)

    created = False
    try:
        if not kernel.CreateProcessW(None, command, None, None, False, 0x08000000,
                None, str(root), ctypes.byref(startup), ctypes.byref(process)):
            raise OSError(ctypes.get_last_error(), 'Private native host start failed')
        created = True
        runtime = userdata / 'addon_data/script.module.bobbi.platform/runtime.json'
        deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < deadline:
            if kernel.WaitForSingleObject(process.hProcess, 0) == 0:
                break
            try:
                ready = rpc('JSONRPC.Ping').get('result') == 'pong' and runtime.is_file()
                if ready:
                    break
            except Exception:
                pass
            time.sleep(.5)
        print(json.dumps({'ready': ready, 'profile': str(profile), 'runtime_json': str(runtime),
            'rpc_config': str(profile / 'validation-rpc.json'), 'private_desktop': not args.visible,
            'account_imported': False, 'real_playback_verified': False}), flush=True)
        if not ready:
            try:
                rpc('Application.Quit')
            except Exception:
                pass
            raise RuntimeError('Native test host did not reach readiness')
        # Parent sends Application.Quit through authenticated local RPC after
        # account/media acceptance; this watcher cannot act on any other Kodi.
        while kernel.WaitForSingleObject(process.hProcess, 1000) != 0:
            pass
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code))
        print(json.dumps({'launcher_exit': code.value, 'profile_retained': True}), flush=True)
    finally:
        if created:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        if desktop:
            user.CloseDesktop(desktop)


if __name__ == '__main__':
    main()
