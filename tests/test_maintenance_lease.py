import ctypes
import json
import os
import pytest
from bobbi_platform.maintenance_lease import expected_request, validate_receipt, WindowsLease, _windows_parent_pid
from bobbi_platform.updates import Busy, UpdateError


def test_receipt_binds_exact_operation_and_roots(tmp_path):
    expected = expected_request('apply', tmp_path/'signed.zip', tmp_path/'addons', tmp_path/'work', 'windows')
    receipt = dict(expected, parent_pid=123, kodi_pid=234, nonce='a'*64)
    assert validate_receipt(receipt, expected, 123) == receipt
    for changed in (dict(receipt, operation='rollback'), dict(receipt, parent_pid=999),
                    dict(receipt, bundle=str(tmp_path/'other.zip')), dict(receipt, nonce=''),
                    dict(receipt, kodi_pid=True), dict(receipt, extra='no')):
        with pytest.raises(UpdateError):
            validate_receipt(changed, expected, 123)


def test_standalone_invocation_has_no_fake_idle_bypass():
    with pytest.raises(UpdateError):
        WindowsLease(None, {})


class KernelCall:
    def __init__(self, action):
        self.action = action

    def __call__(self, *args):
        return self.action(*args)


class ProcessKernel:
    def __init__(self, rows, current=202, snapshot=17):
        self.rows, self.closed, self.calls = iter(rows), [], []
        self.GetCurrentProcessId = KernelCall(lambda: current)
        self.CreateToolhelp32Snapshot = KernelCall(self.snapshot)
        self.Process32FirstW = KernelCall(self.entry)
        self.Process32NextW = KernelCall(self.entry)
        self.CloseHandle = KernelCall(lambda handle: self.closed.append(handle) or 1)
        self.snapshot_handle = snapshot

    def snapshot(self, flags, pid):
        self.calls.append((flags, pid))
        return self.snapshot_handle

    def entry(self, handle, pointer):
        assert pointer._obj.dwSize == ctypes.sizeof(pointer._obj)
        row = next(self.rows, None)
        if row is None:
            return 0
        pointer._obj.th32ProcessID, pointer._obj.th32ParentProcessID = row
        return 1


def test_toolhelp_parent_is_snapshot_creator_not_python_or_environment(monkeypatch):
    monkeypatch.setattr(os, 'getppid', lambda: 202)
    monkeypatch.setenv('BOBBI_PARENT_PID', '999')
    kernel = ProcessKernel([(55, 4), (202, 101)])
    assert _windows_parent_pid(kernel) == 101
    assert kernel.calls == [(0x2, 0)]
    assert kernel.closed == [17]


@pytest.mark.parametrize('rows', [[], [(55, 4)], [(202, 0)], [(202, 202)]])
def test_toolhelp_missing_or_invalid_creator_fails_closed_and_closes_snapshot(rows):
    kernel = ProcessKernel(rows)
    with pytest.raises(UpdateError, match='parent process'):
        _windows_parent_pid(kernel)
    assert kernel.closed == [17]


@pytest.mark.parametrize('handle', [None, 0, ctypes.c_void_p(-1).value])
def test_toolhelp_invalid_snapshot_is_not_closed(handle):
    kernel = ProcessKernel([], snapshot=handle)
    with pytest.raises(UpdateError, match='parent process'):
        _windows_parent_pid(kernel)
    assert kernel.closed == []


@pytest.mark.skipif(os.name != 'nt', reason='real Windows inherited-pipe API binding')
@pytest.mark.parametrize('condition', ['valid', 'parent-exited', 'kodi-active', 'pipe-closed', 'wrong-parent'])
def test_windows_lease_uses_toolhelp_and_preserves_lifecycle_guards(monkeypatch, tmp_path, condition):
    expected = expected_request('apply', tmp_path/'signed.zip', tmp_path/'addons', tmp_path/'work', 'windows')
    raw = json.dumps(dict(expected, parent_pid=101, kodi_pid=303, nonce='a'*64)).encode() + b'\n'
    kernel = ProcessKernel([(202, 999 if condition == 'wrong-parent' else 101)])
    remaining = [raw]
    opened = []

    def peek(pipe, buffer, length, read, available, left):
        if condition == 'pipe-closed' and not remaining[0]:
            return 0
        available._obj.value = len(remaining[0])
        return 1

    def read(pipe, buffer, length, count, unused):
        ctypes.memmove(buffer, remaining[0], length)
        count._obj.value = length
        remaining[0] = b''
        return 1

    def open_process(access, inherit, pid):
        opened.append(pid)
        if pid == 303 and condition == 'kodi-active':
            return 33
        return 22 if pid == 101 else None

    kernel.PeekNamedPipe = KernelCall(peek)
    kernel.ReadFile = KernelCall(read)
    kernel.OpenProcess = KernelCall(open_process)
    kernel.WaitForSingleObject = KernelCall(
        lambda handle, timeout: 0 if handle == 22 and condition == 'parent-exited' else 258)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *args, **kwargs: kernel)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 87)
    monkeypatch.setattr(os, 'getppid', lambda: 202)
    if condition != 'valid':
        error = UpdateError if condition == 'wrong-parent' else Busy
        with pytest.raises(error):
            WindowsLease(99, expected)
        return
    lease = WindowsLease(99, expected)
    assert opened == [101, 303]
    assert lease.idle()
    lease.close()
    assert kernel.closed == [17, 22]
