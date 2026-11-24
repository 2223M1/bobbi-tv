"""Open one authorized pointer document without interpreting it as Kodi content."""
from contextlib import ExitStack
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit

from bobbi_core import media_pointer
from bobbi_core.library_contract import LibraryError, SCHEMES, joined_path, relative_path
from bobbi_core.source_endpoint import endpoint


def _local(root, relative):
    parts = relative.split('/')
    if os.name == 'posix':
        # Hold each directory while opening its child; no symlink race or FIFO wait.
        flags = os.O_RDONLY | os.O_NOFOLLOW
        with ExitStack() as stack:
            fd = os.open('/', flags | os.O_DIRECTORY)
            stack.callback(os.close, fd)
            for part in (*Path(root).parts[1:], *parts[:-1]):
                fd = os.open(part.encode('utf-8'), flags | os.O_DIRECTORY, dir_fd=fd)
                stack.callback(os.close, fd)
            fd = os.open(parts[-1].encode('utf-8'), flags | os.O_NONBLOCK, dir_fd=fd)
            stack.callback(os.close, fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise LibraryError('POINTER_INVALID')
            with os.fdopen(fd, 'rb', closefd=False) as f:
                return f.read(media_pointer.LIMIT + 1)
    path = Path(root).joinpath(*parts)
    def regular():
        return (path.is_absolute() and path.resolve(strict=True) == path and path.is_file() and
                not any(p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT for p in (path, *path.parents)))
    if not regular():
        raise LibraryError('POINTER_INVALID')
    with path.open('rb') as f:
        if not regular() or not os.path.samestat(path.stat(), os.fstat(f.fileno())):
            raise LibraryError('POINTER_INVALID')
        return f.read(media_pointer.LIMIT + 1)


def read(source, relative):
    if source.kind != 'vfs' or not relative_path(relative).lower().endswith('.strm'):
        raise LibraryError('POINTER_INVALID')
    try:
        if urlsplit(source.location).scheme in SCHEMES:
            import xbmcvfs
            fh = xbmcvfs.File(joined_path(source, relative))
            try:
                raw = bytes(fh.readBytes(media_pointer.LIMIT + 1))
            finally:
                fh.close()
        else:
            raw = _local(source.location, relative)
        url, observation = media_pointer.parse(raw)
        return endpoint(url), observation
    except (OSError, RuntimeError, UnicodeError):
        raise LibraryError('POINTER_INVALID') from None
