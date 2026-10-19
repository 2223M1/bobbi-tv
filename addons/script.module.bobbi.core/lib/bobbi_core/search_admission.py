"""Cross-interpreter search admission, retained until actual provider IO exits."""
import os
from pathlib import Path
import stat
import threading


class SearchAdmission:
    def __init__(self, fd):
        self.fd, self.references, self.mutex = fd, 1, threading.Lock()

    def retain(self):
        with self.mutex:
            if self.fd is None:
                raise RuntimeError('Closed search admission')
            self.references += 1

    def release(self, _future=None):
        with self.mutex:
            self.references -= 1
            if self.references < 0:
                raise RuntimeError('Search admission released twice')
            if self.references or self.fd is None:
                return
            fd, self.fd = self.fd, None
        # Closing the descriptor releases the OS lock. Do not unlink the
        # inode: another interpreter may already be waiting on that file.
        os.close(fd)


def try_acquire(directory=None):
    if directory is None:
        if os.name == 'nt':
            import tempfile
            directory = Path(tempfile.gettempdir()) / 'bobitv-source-admission'
        else:
            directory = Path('/storage/.local/share/bobitv/search')
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or (os.name != 'nt' and
            (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077)):
        raise ValueError('Private source admission directory required')
    path = directory / 'active.lock'
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and
                (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077)):
            raise ValueError('Private source admission file required')
        try:
            if os.name == 'nt':
                import msvcrt
                if not info.st_size:
                    os.write(fd, b'0')
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            os.close(fd)
            return None
        return SearchAdmission(fd)
    except BaseException:
        os.close(fd)
        raise
