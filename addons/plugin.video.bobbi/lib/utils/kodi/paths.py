"""Join the path's namespace, not the operating system running the plugin."""
import ntpath
import os
import posixpath


def join_kodi_path(base, *parts):
    base = os.fspath(base)
    values = tuple(os.fspath(part) for part in parts)
    if "://" in base or base.startswith("/"):
        return posixpath.join(base, *values)
    if ntpath.splitdrive(base)[0] or "\\" in base:
        return ntpath.join(base, *values)
    return os.path.join(base, *values)
