"""OS-owned subtitle child lifetime; no Python watchdog thread or credentials.

Linux children own an absolute wall-clock alarm and parent-death signal.
Windows parents own a kill-on-close Job; a child must verify membership before
network IO. Windows wall-clock supervision remains in the live parent.
"""
import ctypes
import math
import os
import sys
import time

_UNCLOSED_JOB = None


class LifetimeError(ValueError):
    def __init__(self):
        super().__init__('SUBTITLE_IO_LIFETIME_FAILED')


def _windows():
    from ctypes import wintypes as w

    class BasicLimits(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                    ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', w.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD),
                    ('SchedulingClass', w.DWORD)]

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                     'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class Limits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', Counters),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    declarations = {
        'CreateJobObjectW': ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        'OpenJobObjectW': ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
        'SetInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
        'IsProcessInJob': ([w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
        'GetCurrentProcess': ([], w.HANDLE),
        'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        'WaitForSingleObject': ([w.HANDLE, w.DWORD], w.DWORD),
        'CloseHandle': ([w.HANDLE], w.BOOL),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel, Limits, w.BOOL


class ParentLifetime:
    """One parent-owned Windows Job, or Linux child-side protection contract."""
    def __init__(self):
        if _UNCLOSED_JOB is not None:
            _UNCLOSED_JOB.close()  # No new Job while an old handle is unresolved.
        self.kernel, self.handle, self.name = None, None, None
        if sys.platform == 'win32':
            from uuid import uuid4
            self.kernel, limits_type, _ = _windows()
            self.name = 'Local\\AM6B-subtitle-' + uuid4().hex
            ctypes.set_last_error(0)
            self.handle = self.kernel.CreateJobObjectW(None, self.name)
            if not self.handle:
                raise LifetimeError()
            try:
                # An existing named object is never accepted as our supervisor.
                if ctypes.get_last_error() == 183:
                    raise LifetimeError()
                limits = limits_type()
                limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
                if not self.kernel.SetInformationJobObject(self.handle, 9,
                        ctypes.byref(limits), ctypes.sizeof(limits)):
                    raise LifetimeError()
            except BaseException:
                self.close()
                raise
        elif not sys.platform.startswith('linux'):
            raise LifetimeError()

    def contract(self, expires):
        return dict(parent_pid=os.getpid(), expires=expires, job=self.name)

    def attach(self, process):
        if self.handle is None:
            return
        # The child's bootstrap cannot perform network IO until this exact
        # Job membership is visible. OpenProcess avoids Popen private handles.
        handle = self.kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise LifetimeError()
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise LifetimeError()
        finally:
            self.kernel.CloseHandle(handle)

    def close(self):
        global _UNCLOSED_JOB
        if self.handle is not None:
            _UNCLOSED_JOB = self
            if not self.kernel.CloseHandle(self.handle):
                raise LifetimeError()
            self.handle = None
            _UNCLOSED_JOB = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def protect(contract):
    """Fail closed before network IO, including death before registration."""
    try:
        _protect(contract)
    except LifetimeError:
        raise
    except ValueError as error:
        if str(error) == 'SUBTITLE_IO_DEADLINE':
            raise
        raise LifetimeError() from error
    except Exception as error:
        raise LifetimeError() from error


def _protect(contract):
    if not isinstance(contract, dict):
        raise LifetimeError()
    parent, expires = contract.get('parent_pid'), contract.get('expires')
    if (type(parent) is not int or parent <= 0 or type(expires) not in (int, float)
            or not math.isfinite(expires)):
        raise LifetimeError()
    if expires <= time.monotonic():
        raise ValueError('SUBTITLE_IO_DEADLINE')
    if sys.platform.startswith('linux'):
        import signal
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        if prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
            raise LifetimeError()
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
        remaining = expires - time.monotonic()
        if remaining <= 0:
            raise ValueError('SUBTITLE_IO_DEADLINE')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        return
    if sys.platform != 'win32':
        raise LifetimeError()
    name = contract.get('job')
    prefix = 'Local\\AM6B-subtitle-'
    if (not isinstance(name, str) or not name.startswith(prefix)
            or len(name) != len(prefix) + 32 or any(c not in '0123456789abcdef' for c in name[len(prefix):])):
        raise LifetimeError()
    kernel, _, boolean = _windows()
    parent_handle = kernel.OpenProcess(0x100000, False, parent)  # SYNCHRONIZE
    if not parent_handle:
        raise LifetimeError()
    job = None
    try:
        job = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
        if not job:
            raise LifetimeError()
        while True:
            if expires <= time.monotonic():
                raise ValueError('SUBTITLE_IO_DEADLINE')
            if kernel.WaitForSingleObject(parent_handle, 0) != 258:
                raise LifetimeError()
            assigned = boolean()
            if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), job, ctypes.byref(assigned)):
                raise LifetimeError()
            if assigned.value:
                return
            # Parent may still be between Popen and AssignProcessToJobObject.
            if kernel.WaitForSingleObject(parent_handle, 10) != 258:
                raise LifetimeError()
    finally:
        # A child-held Job handle would defeat KILL_ON_JOB_CLOSE. It is only
        # borrowed during bootstrap and is closed BEFORE returning to HTTP.
        if job:
            closed = kernel.CloseHandle(job)
        else:
            closed = True
        if not kernel.CloseHandle(parent_handle) or not closed:
            raise LifetimeError()
