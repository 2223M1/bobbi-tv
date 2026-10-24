"""Bounded archive IO without launching the embedded Kodi Python as a process."""
import hashlib
import os
from pathlib import Path
import select
import subprocess
import time

from .font_archive import parse_listing, FONT_LIMIT, ARCHIVE_LIMIT, EXPANSION_LIMIT
from .fonts import inspect_font_file


def collect(argv, maximum, deadline, allowed):
    """Read one owned child's pipe; bound output even when its listing lies."""
    if allowed() is not True:
        raise InterruptedError('ANDROID_FONT_CANCELLED')
    output = bytearray()
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        while True:
            if allowed() is not True:
                raise InterruptedError('ANDROID_FONT_CANCELLED')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('ANDROID_FONT_DEADLINE')
            if not select.select([child.stdout], [], [], min(.1, remaining))[0]:
                continue
            block = os.read(child.stdout.fileno(), min(65536, maximum-len(output)+1))
            if not block:
                break
            output.extend(block)
            if len(output) > maximum:
                raise ValueError('ANDROID_FONT_EXPANSION_LIMIT')
        if child.wait(timeout=max(.01, deadline-time.monotonic())):
            raise ValueError('ANDROID_FONT_DECODER_REJECTED')
        if allowed() is not True:
            raise InterruptedError('ANDROID_FONT_CANCELLED')
        return bytes(output)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
        child.stdout.close()


def decoder(tool, limiter):
    """Host verifies these PackageManager-installed tools before binding us."""
    def decode(archive, sha256, output, allowed):
        archive, output = Path(archive), Path(output)
        if archive.is_symlink() or not 0 < archive.stat().st_size <= ARCHIVE_LIMIT:
            raise ValueError('ANDROID_FONT_ARCHIVE')
        digest = hashlib.sha256()
        with archive.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                if allowed() is not True:
                    raise InterruptedError('ANDROID_FONT_CANCELLED')
                digest.update(block)
        if digest.hexdigest() != sha256:
            raise ValueError('ANDROID_FONT_ARCHIVE_CHANGED')
        output.mkdir(parents=False, exist_ok=False)
        deadline = time.monotonic()+40
        options = ['-mmt=1', '-sccUTF-8', '-spd', '-y']
        listing = collect([str(limiter), str(tool), 'l', '-slt', *options, '--', str(archive)],
                          2*1024*1024, deadline, allowed)
        members = parse_listing(listing)
        fonts, total = [], 0
        for number, member in enumerate(members):
            # -so never writes archive-controlled paths. Only validated font
            # bytes are published under our own fresh, numeric filenames.
            raw = collect([str(limiter), str(tool), 'x', '-so', *options, '--', str(archive), member['path']],
                          min(FONT_LIMIT, member['bytes']), deadline, allowed)
            total += len(raw)
            if len(raw) != member['bytes'] or total > EXPANSION_LIMIT:
                raise ValueError('ANDROID_FONT_SIZE_CHANGED')
            path = output/(str(number)+Path(member['path']).suffix.lower())
            with path.open('xb') as stream:
                stream.write(raw)
            record = inspect_font_file(path)
            fonts.append(dict(record, path=str(path), origin='same_release_pack'))
        return fonts
    return decode
