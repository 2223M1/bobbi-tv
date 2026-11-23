"""Re-key the two renamed XBTF2 entries without repacking a single frame."""
import hashlib
from pathlib import Path
import struct


APPROVED = '3d2d8c10db9840ff6d5d2ee7fad29162e3aa687eca4fcab046f1117a6907d16f'
RENAMED = {b'common/bobbi.jpg': b'common/minsk.jpg',
           b'legacy_____logo.png': b'confluence_logo.png'}
MIXED = {b'common/Bobbi.jpg': b'common/bobbi.jpg',
         b'Legacy_____logo.png': b'legacy_____logo.png'}


def rekey(data, changes):
    if data[:5] != b'XBTF2':
        raise ValueError('Unexpected texture archive')
    result = bytearray(data)
    count, = struct.unpack_from('<I', data, 5)
    offset = 9
    seen, changed = set(), set()
    for _ in range(count):
        name, sep, pad = data[offset:offset+256].partition(b'\0')
        if not sep or any(pad):
            raise ValueError('Invalid XBTF path')
        key = changes.get(name, name)
        if key.lower() in seen or len(key) >= 256:
            raise ValueError('Ambiguous XBTF path')
        seen.add(key.lower())
        if name in changes:
            result[offset:offset+256] = key.ljust(256, b'\0')
            changed.add(name)
        frames, = struct.unpack_from('<I', data, offset+260)
        offset += 264 + frames*40
        if offset > len(data):
            raise ValueError('Invalid XBTF frame table')
    if changed != set(changes):
        raise ValueError('Missing approved rename')
    return bytes(result)


def approved_digest(data):
    # Kodi's TextureBundleXBT normalizes requests to lowercase, XBTFReader
    # stores its keys verbatim. Require canonical keys in the shipped archive.
    original = rekey(data, RENAMED)
    digest = hashlib.sha256(original).hexdigest()
    if digest != APPROVED:
        raise ValueError('Texture archive differs beyond the two approved names')
    return digest


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1]/'addons/skin.bobbi.cinema/media/Textures.xbt'
    current = path.read_bytes()
    fixed = rekey(current, MIXED)
    approved_digest(fixed)
    if current != path.read_bytes():
        raise SystemExit('Source changed during normalization')
    path.write_bytes(fixed)
