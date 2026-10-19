"""Immutable native-browser copies of independently qualified subtitle objects.

No cloud/FUSE reads, recursive directory scan or automatic eviction. The
native actor independently rechecks ext4, ownership, size, hash and intent.
"""
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from bobbi_core.font_cache import safe_directory
from bobbi_core.subtitle_binding import style_reviewable

NATIVE_ROOT = '/storage/.kodi/userdata/addon_data/plugin.video.bobbi/subtitle-browser'


def export(store, record, root=NATIVE_ROOT, volume='/storage'):
    if ((record['state'] != 'READY_NOT_VISUAL_PROOF' and not style_reviewable(record))
            or record['extension'] not in {'.srt', '.ass', '.ssa', '.vtt'}):
        raise ValueError('Only qualified text subtitles can enter native automatic loading')
    directory = safe_directory(root)
    info = directory.stat()
    if (info.st_dev != Path(volume).stat().st_dev or stat.S_IMODE(info.st_mode) & 0o022
            or (hasattr(os, 'getuid') and info.st_uid != os.getuid())):
        raise ValueError('Private same-volume native subtitle cache required')
    raw = store._read(record)
    name = record['subtitle_sha256'][:32] + record['extension']
    target = directory / name
    if not target.exists() and not target.is_symlink():
        fd, temporary = tempfile.mkstemp(prefix='.prepare-', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o444)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass  # Another identical publication still requires verification.
        finally:
            Path(temporary).unlink()  # Only this exclusively created partial.
    info = target.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_dev != directory.stat().st_dev
            or info.st_size != len(raw) or stat.S_IMODE(info.st_mode) & 0o222
            or (hasattr(os, 'getuid') and info.st_uid != os.getuid())):
        raise ValueError('Native subtitle cache type/permission/size drift')
    with target.open('rb') as stream:
        digest = hashlib.sha256(stream.read(len(raw) + 1)).hexdigest()
    if digest != record['subtitle_sha256']:
        raise ValueError('Native subtitle hash collision or drift; preserve existing file')
    return dict(path=str(target), sha256=digest, bytes=len(raw))
