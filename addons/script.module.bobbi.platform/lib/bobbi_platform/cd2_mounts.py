"""Discover existing CD2 mounts without opening cloud files or reading logins.

Mount presence is not an account/session or readability check. Kodi's current
namespace is authoritative, including bind mounts exposed by a container.
"""
from pathlib import Path, PurePosixPath
import re

MAX_BYTES = 1024 * 1024
MAX_MOUNTS = 32
FILESYSTEMS = frozenset(('fuse', 'fuse.clouddrive', 'fuse.clouddrive2', 'fuse.cloudfs'))
SOURCES = frozenset(('cloudfs', 'clouddrive', 'clouddrive2'))


def parse_mounts(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        return ()
    mounts = set()
    for line in text.splitlines():
        before, separator, after = line.partition(' - ')
        fields, tail = before.split(), after.split()
        if not separator or len(fields) < 6 or len(tail) < 3:
            continue
        if tail[0].lower() not in FILESYSTEMS or tail[1].lower() not in SOURCES:
            continue
        path = re.sub(r'\\(040|011|012|134)',
                      lambda match: chr(int(match.group(1), 8)), fields[4])
        # Preserve spaces, reject malformed/control paths, never offer root.
        if (not path.startswith('/') or path == '/' or len(path) > 2048
                or any(ord(c) < 32 or ord(c) == 127 for c in path)
                or any(c in path for c in ('\\', '|'))
                or '..' in path.split('/') or str(PurePosixPath(path)) != path):
            continue
        mounts.add(path)
        if len(mounts) > MAX_MOUNTS:
            return ()  # Let the ordinary directory picker handle unusual hosts.
    return tuple(sorted(mounts))


def discover():
    try:
        with Path('/proc/self/mountinfo').open('r', encoding='utf-8') as stream:
            return parse_mounts(stream.read(MAX_BYTES + 1))
    except (OSError, UnicodeError, ValueError):
        return ()
