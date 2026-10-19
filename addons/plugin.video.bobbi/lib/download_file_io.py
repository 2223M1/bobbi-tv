"""Local download ownership and atomic publication without replacing other files."""
import contextlib
import errno
import os


class DownloadBusyError(OSError):
    """Another worker owns this destination."""


def local_path(path):
    # Kodi special:// paths must already have been translated by the caller.
    if "://" in path:
        raise OSError("This download destination cannot guarantee exclusive local publication")
    return os.path.abspath(path)


def open_download_file(path, mode):
    """Use local byte I/O: Kodi VFS does not implement Python's append mode."""
    return open(local_path(path), mode)


@contextlib.contextmanager
def download_lock(destination):
    """Use a kernel lock, released even on interpreter/process exit.

    The small persistent sidecar must not be unlinked: removing a locked inode
    would allow another process to lock a different inode for the same name.
    """
    path = local_path(destination) + ".bobbi.lock"
    with open(path, "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DownloadBusyError("Download already in progress") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DownloadBusyError("Download already in progress") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def publish_download(source, destination):
    """Publish a closed file atomically, preserving any existing destination."""
    source, destination = local_path(source), local_path(destination)
    if os.name == "nt":
        # Windows rename fails if the target already exists, including races.
        os.rename(source, destination)
        return

    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint)
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:
            return
        code = ctypes.get_errno()
        if code not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise OSError(code, os.strerror(code), destination)
    # No replacement can occur even on platforms without renameat2. Unsupported
    # filesystems fail safely and retain the source; never fall back to rename.
    os.link(source, destination)
    with contextlib.suppress(OSError):
        os.unlink(source)
