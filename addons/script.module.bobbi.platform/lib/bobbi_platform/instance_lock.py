"""Process lease for one local host; no PID guessing or stale-file deletion."""
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, path):
        self.path, self.fd = Path(path), None

    def acquire(self):
        if self.fd is not None:
            raise RuntimeError('HOST_ALREADY_STARTED')
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('HOST_LOCK_PATH_INVALID')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'\0')
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)  # OS releases the lease; keep the stable lock inode.
