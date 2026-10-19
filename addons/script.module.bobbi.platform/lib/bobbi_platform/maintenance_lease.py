"""Exit-only host maintenance lease. Never treats a momentary idle as exclusion."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time

from .updates import Busy, UpdateError, _json, _Lock


def expected_request(operation, bundle, addons_root, work_root, profile):
    def absolute(value):
        return os.path.normcase(os.path.abspath(str(value)))
    return dict(operation=operation, bundle=absolute(bundle) if bundle else '',
                addons_root=absolute(addons_root), work_root=absolute(work_root), profile=profile)


def validate_receipt(receipt, expected, parent_pid):
    if (not isinstance(receipt, dict) or set(receipt) != set(expected) | {'parent_pid', 'kodi_pid', 'nonce'} or
            type(receipt['parent_pid']) is not int or receipt['parent_pid'] != parent_pid or parent_pid <= 0 or
            type(receipt['kodi_pid']) is not int or receipt['kodi_pid'] <= 0 or
            not isinstance(receipt['nonce'], str) or not re.fullmatch('[a-f0-9]{32,128}', receipt['nonce'])):
        raise UpdateError('Invalid host maintenance lease')
    normalized = expected_request(receipt['operation'], receipt['bundle'], receipt['addons_root'],
                                  receipt['work_root'], receipt['profile'])
    if normalized != expected:
        raise UpdateError('Host lease does not authorize this exact operation')
    return receipt


def _windows_parent_pid(kernel):
    """Read the real creator PID; some embedded Python builds misreport getppid.

    A process snapshot is independent of Python's implementation and inherited
    environment. The launcher must still be alive and hold the inherited pipe;
    this lookup alone is not a lifecycle lease.
    """
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_uint32), ('cntUsage', ctypes.c_uint32),
                    ('th32ProcessID', ctypes.c_uint32), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', ctypes.c_uint32), ('cntThreads', ctypes.c_uint32),
                    ('th32ParentProcessID', ctypes.c_uint32), ('pcPriClassBase', ctypes.c_int32),
                    ('dwFlags', ctypes.c_uint32), ('szExeFile', ctypes.c_wchar * 260)]

    kernel.GetCurrentProcessId.argtypes = []
    kernel.GetCurrentProcessId.restype = wintypes.DWORD
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32)]
        function.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    current = kernel.GetCurrentProcessId()
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        raise UpdateError('Cannot establish maintenance parent process')
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == current:
                parent = entry.th32ParentProcessID
                if parent <= 0 or parent == current:
                    break
                return parent
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        raise UpdateError('Cannot establish maintenance parent process')
    finally:
        kernel.CloseHandle(snapshot)


class WindowsLease:
    """Inherited read pipe; lifecycle mutex remains held in the live launcher.

    Parent sends one newline-terminated <=8KiB receipt after Kodi exits and keeps
    its write endpoint open until this process exits. No standalone CLI bypass.
    """
    def __init__(self, handle, expected):
        if os.name != 'nt' or type(handle) is not int or handle <= 0:
            raise UpdateError('Inherited Windows lifecycle lease required')
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.types = ctypes, wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPDWORD]
        self.kernel.PeekNamedPipe.restype = wintypes.BOOL
        self.kernel.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                        wintypes.LPDWORD, wintypes.LPVOID]
        self.kernel.ReadFile.restype = wintypes.BOOL
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.pipe, self.parent = wintypes.HANDLE(handle), None
        raw, end = bytearray(), time.monotonic() + 5
        while b'\n' not in raw:
            available = self._peek()
            if len(raw) + available > 8192 or time.monotonic() >= end:
                raise UpdateError('Host lease receipt budget exceeded')
            if not available:
                time.sleep(.01)
                continue
            buffer, count = ctypes.create_string_buffer(available), wintypes.DWORD()
            if not self.kernel.ReadFile(self.pipe, buffer, available, ctypes.byref(count), None):
                raise UpdateError('Host lease pipe closed')
            raw.extend(buffer.raw[:count.value])
        if raw.count(b'\n') != 1 or not raw.endswith(b'\n'):
            raise UpdateError('Multiple host lease receipts rejected')
        receipt = validate_receipt(_json(bytes(raw)), expected, _windows_parent_pid(self.kernel))
        self.parent = self.kernel.OpenProcess(0x100000, False, receipt['parent_pid'])
        if not self.parent:
            raise UpdateError('Maintenance owner is unavailable')
        kodi = self.kernel.OpenProcess(0x100000, False, receipt['kodi_pid'])
        if kodi:
            try:
                if self.kernel.WaitForSingleObject(kodi, 0) != 0:
                    raise Busy('Kodi has not exited')
            finally:
                self.kernel.CloseHandle(kodi)
        elif ctypes.get_last_error() != 87:  # Invalid PID means already exited.
            raise Busy('Cannot establish Kodi process exit')
        if not self.idle():
            raise Busy('Maintenance lifecycle lease lost')

    def _peek(self):
        available = self.types.DWORD()
        if not self.kernel.PeekNamedPipe(self.pipe, None, 0, None, self.ctypes.byref(available), None):
            raise Busy('Maintenance lifecycle pipe closed')
        return available.value

    def idle(self):
        return (bool(self.parent) and self.kernel.WaitForSingleObject(self.parent, 0) == 258
                and self._peek() == 0)

    @contextmanager
    def commit(self):
        if not self.idle():
            raise Busy('Maintenance lifecycle lease lost')
        yield
        if not self.idle():
            raise Busy('Maintenance owner exited during transaction')

    def close(self):
        if self.parent:
            self.kernel.CloseHandle(self.parent)
            self.parent = None


class CoreELECLease:
    """Explicit controller-stopped Kodi service; runtime mask prevents respawn.

    This does not stop/mask/restart anything itself. The deployment controller
    owns reversible systemd changes and must restore them in its finally block.
    """
    def __init__(self, work_root):
        if os.name != 'posix' or not Path('/etc/os-release').is_file() or 'CoreELEC' not in Path('/etc/os-release').read_text():
            raise UpdateError('CoreELEC stopped-service lease required')
        self.lock = _Lock(Path(work_root) / 'lifecycle.lock')
        self.active = False

    def idle(self):
        mask = Path('/run/systemd/system/kodi.service')
        if not mask.is_symlink() or os.readlink(str(mask)) != '/dev/null':
            return False
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                executable = os.readlink(str(process / 'exe'))
            except FileNotFoundError:
                continue
            except PermissionError:
                return False
            if Path(executable).name in ('kodi.bin', 'kodi'):
                return False
        return True

    @contextmanager
    def commit(self):
        with self.lock:
            if not self.idle():
                raise Busy('Kodi must be stopped and runtime-masked by controller')
            yield
            if not self.idle():
                raise Busy('CoreELEC lifecycle lease changed')

    def close(self):
        pass
