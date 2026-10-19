# -*- coding: utf-8 -*-
"""VFS (Virtual File System) utilities for Kodi and network paths (SMB, NFS, etc.)."""

import contextlib
import io
import os
import re
import tarfile
from urllib.parse import unquote, urlsplit

try:
    import xbmcvfs
except ImportError:
    xbmcvfs = None


def _get_xbmcvfs():
    """Retrieve xbmcvfs module safely, supporting runtime mocks or dynamic imports."""
    global xbmcvfs
    if xbmcvfs is not None:
        return xbmcvfs
    import sys
    if "xbmcvfs" in sys.modules:
        xbmcvfs = sys.modules["xbmcvfs"]
        return xbmcvfs
    try:
        import xbmcvfs
        return xbmcvfs
    except ImportError:
        return None


def is_vfs_path(path: str) -> bool:
    """Return True if path represents a network or Kodi VFS URL."""
    if not path:
        return False
    return "://" in path


def get_filename_from_path(path: str) -> str:
    """Extract clean filename from local path or network URL."""
    if not path:
        return ""
    if "://" in path:
        parsed = urlsplit(path)
        filename = os.path.basename(parsed.path.rstrip("/\\"))
        return unquote(filename)
    clean = path.rstrip("/\\")
    return re.split(r"[/\\]", clean)[-1]


def vfs_file_exists(path: str) -> bool:
    """Check whether a local or VFS file exists."""
    if not path:
        return False
    if os.path.isfile(path):
        return True
    vfs = _get_xbmcvfs()
    if vfs is not None:
        try:
            return bool(vfs.exists(path))
        except Exception:
            pass
    return False


def vfs_file_size(path: str) -> int:
    """Get file size in bytes for local or VFS path."""
    if not path:
        return 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
    except Exception:
        pass
    vfs = _get_xbmcvfs()
    if vfs is not None:
        try:
            f = vfs.File(path, "rb")
            sz = f.size() if hasattr(f, "size") else 0
            f.close()
            return sz
        except Exception:
            pass
    return 0


def vfs_delete_file(path: str) -> bool:
    """Delete a local or VFS file."""
    if not path:
        return False
    if os.path.isfile(path):
        try:
            os.remove(path)
            return True
        except Exception:
            return False
    vfs = _get_xbmcvfs()
    if vfs is not None:
        try:
            return bool(vfs.delete(path))
        except Exception:
            pass
    return False


class VfsFileStream(io.RawIOBase):
    """RawIOBase adapter for xbmcvfs.File enabling standard Python file streaming."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self._pos = 0
        vfs = _get_xbmcvfs()
        if vfs is None:
            raise IOError(f"xbmcvfs is not available to read {path}")
        self._file = vfs.File(path, "rb")
        self._size = self._file.size() if hasattr(self._file, "size") else 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def readinto(self, b) -> int:
        if not self._file:
            return 0
        if self._size > 0 and self._pos >= self._size:
            return 0
        to_read = len(b)
        if self._size > 0:
            to_read = min(to_read, self._size - self._pos)
        if to_read <= 0:
            return 0
        data = self._file.readBytes(to_read)
        n = len(data)
        if n > 0:
            b[:n] = data
            self._pos += n
        return n

    def read(self, size: int = -1) -> bytes:
        if not self._file:
            return b""
        if self._size > 0 and self._pos >= self._size:
            return b""
        if size < 0:
            to_read = (self._size - self._pos) if self._size > 0 else -1
        else:
            to_read = min(size, self._size - self._pos) if self._size > 0 else size
        if to_read == 0:
            return b""
        data = self._file.readBytes(to_read)
        self._pos += len(data)
        return bytes(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self._pos + offset
        elif whence == io.SEEK_END:
            target = self._size + offset
        else:
            raise ValueError(f"Invalid whence: {whence}")

        target = max(0, target)
        if self._size > 0:
            target = min(target, self._size)
        if self._file:
            self._file.seek(target, 0)
        self._pos = target
        return self._pos

    def tell(self) -> int:
        return self._pos

    def close(self) -> None:
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        super().close()


@contextlib.contextmanager
def open_tar_archive(tar_path: str, buffer_size: int = 1024 * 1024):
    """Open a .tar archive from either local filesystem or Kodi VFS (SMB, NFS, etc.)."""
    if "://" in tar_path or not os.path.isfile(tar_path):
        raw_stream = VfsFileStream(tar_path)
        buf_stream = io.BufferedReader(raw_stream, buffer_size=buffer_size)
        tar = tarfile.open(fileobj=buf_stream, mode="r:*")
        try:
            yield tar
        finally:
            try:
                tar.close()
            finally:
                buf_stream.close()
    else:
        with tarfile.open(tar_path, "r:*") as tar:
            yield tar
