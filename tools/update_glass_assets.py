#!/usr/bin/env python3
"""Generate and verify the packaged Liquid Glass renderer & material manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
ADDONS_REL = Path('addons')
RENDERER_REL = 'script.module.bobbi.platform/resources/renderer/ce-armhf/libbobbi_liquid_glass.so'
DEFAULT_OUT_REL = Path('addons/script.module.bobbi.platform/resources/renderer/glass_assets.json')
PROTOCOL = 'bobilg-16x4-v2'
REQUIRED_ADDONS = (
    'skin.bobbi.cinema',
    'plugin.video.bobbi',
    'script.module.bobbi.platform',
    'script.module.bobbi.core',
)

SKIN_GLASS_REL = Path('skin.bobbi.cinema/media/bobbi/glass')
PLUGIN_GLASS_REL = Path('plugin.video.bobbi/resources/skins/Default/media/bobbi/glass')

CRITICAL_XML_AND_FONT_PATHS = (
    'plugin.video.bobbi/resources/skins/Default/1080i/source_select.xml',
    'skin.bobbi.cinema/1080p/DialogButtonMenu.xml',
    'skin.bobbi.cinema/1080p/Font.xml',
    'skin.bobbi.cinema/1080p/Home.xml',
    'skin.bobbi.cinema/1080p/Includes.xml',
    'skin.bobbi.cinema/1080p/Includes_Home.xml',
    'skin.bobbi.cinema/1080p/Includes_Views.xml',
    'skin.bobbi.cinema/fonts/BobbiTV-CCMedium.ttf',
)

CRITICAL_STATIC_TEXTURES = (
    'sidebar-classic.png',
    'cc-power-208x208.png',
    'cc-pill-208x96.png',
    'cc-power-251x242.png',
    'cc-pill-251x112.png',
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def crc8_bobilg(data: bytes | bytearray) -> int:
    crc = 0x5A
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def decode_bobilg_png(raw: bytes, label: str = '<png>') -> dict[str, int]:
    """Decode and validate a 16x4 RGBA steganographic BOBILG tag PNG."""
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{label}: invalid PNG signature')
    pos = 8
    idat = bytearray()
    dims: tuple[int, int, int, int, int, int, int] | None = None
    seen_iend = False
    while pos + 8 <= len(raw):
        length = struct.unpack_from('>I', raw, pos)[0]
        ctype = raw[pos + 4:pos + 8]
        end = pos + 8 + length
        if end + 4 > len(raw):
            raise ValueError(f'{label}: truncated PNG chunk {ctype!r}')
        chunk = raw[pos + 8:end]
        crc_expected = struct.unpack_from('>I', raw, end)[0]
        if (zlib.crc32(raw[pos + 4:end]) & 0xFFFFFFFF) != crc_expected:
            raise ValueError(f'{label}: PNG chunk CRC mismatch in {ctype!r}')
        pos = end + 4
        if ctype == b'IHDR':
            if len(chunk) != 13:
                raise ValueError(f'{label}: invalid IHDR length')
            dims = struct.unpack('>IIBBBBB', chunk)
        elif ctype == b'IDAT':
            idat.extend(chunk)
        elif ctype == b'IEND':
            seen_iend = True
            break
    if not seen_iend or dims is None:
        raise ValueError(f'{label}: incomplete PNG stream')
    width, height, bit_depth, color_type, comp, filt, interlace = dims
    if (width, height, bit_depth, color_type, comp, filt, interlace) != (16, 4, 8, 6, 0, 0, 0):
        raise ValueError(f'{label}: expected 16x4 8-bit non-interlaced RGBA, got {dims}')
    decompressed = zlib.decompress(bytes(idat))
    stride = width * 4
    if len(decompressed) != height * (1 + stride):
        raise ValueError(f'{label}: unexpected decompressed byte length {len(decompressed)}')
    pixels = bytearray()
    prev = bytearray(stride)
    idx = 0
    for _ in range(height):
        ftype = decompressed[idx]
        row = bytearray(decompressed[idx + 1:idx + 1 + stride])
        idx += 1 + stride
        if ftype == 0:
            pass
        elif ftype == 1:
            for x in range(4, stride):
                row[x] = (row[x] + row[x - 4]) & 0xFF
        elif ftype == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif ftype == 3:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                row[x] = (row[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif ftype == 4:
            for x in range(stride):
                a = row[x - 4] if x >= 4 else 0
                b = prev[x]
                c = prev[x - 4] if x >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[x] = (row[x] + pr) & 0xFF
        else:
            raise ValueError(f'{label}: unsupported PNG filter {ftype}')
        pixels.extend(row)
        prev = row

    msg = bytearray(16)
    for i in range(64):
        green = pixels[i * 4 + 1]
        if green < 252:
            raise ValueError(f'{label}: pixel {i} green channel {green} < 252')
        msg[i >> 2] |= (green & 0x03) << ((3 - (i & 3)) * 2)
    if bytes(msg[:6]) != b'BOBILG':
        raise ValueError(f'{label}: missing BOBILG magic')
    crc = crc8_bobilg(msg[:15])
    if crc != msg[15]:
        raise ValueError(f'{label}: BOBILG CRC8 mismatch ({crc:#04x} != {msg[15]:#04x})')
    if msg[6] not in (1, 2):
        raise ValueError(f'{label}: invalid BOBILG kind {msg[6]}')
    return {
        'kind': msg[6],
        'slot': msg[7],
        'layer': msg[7] & 0x03,
        'blur_tier': (msg[7] >> 2) & 0x03,
        'shape_or_roi': msg[8],
        'crc8': msg[15],
    }


def build_manifest(root: Path = ROOT) -> dict[str, object]:
    addons = root / ADDONS_REL
    renderer_path = addons / RENDERER_REL
    if not renderer_path.is_file():
        raise FileNotFoundError(f'Missing renderer binary: {renderer_path}')
    renderer_raw = renderer_path.read_bytes()
    if renderer_raw[:6] != b'\x7fELF\x01\x01' or int.from_bytes(renderer_raw[18:20], 'little') != 40:
        raise ValueError(f'Invalid ELF32 ARM renderer binary: {renderer_path}')

    materials: dict[str, str] = {}
    for rel in CRITICAL_XML_AND_FONT_PATHS:
        target = addons / rel
        if not target.is_file():
            raise FileNotFoundError(f'Missing critical glass asset: {target}')
        materials[rel] = sha256_file(target)

    skin_glass = addons / SKIN_GLASS_REL
    plugin_glass = addons / PLUGIN_GLASS_REL
    skin_tags = sorted(p.name for p in skin_glass.glob('lg-*.png'))
    plugin_tags = sorted(p.name for p in plugin_glass.glob('lg-*.png'))
    if not skin_tags:
        raise ValueError('No lg-*.png steganographic tag textures found')
    if skin_tags != plugin_tags:
        raise ValueError(f'lg-*.png mirror set mismatch: skin={skin_tags} vs plugin={plugin_tags}')

    tags_meta: dict[str, dict[str, int]] = {}
    for name in skin_tags:
        skin_file = skin_glass / name
        plugin_file = plugin_glass / name
        skin_bytes = skin_file.read_bytes()
        plugin_bytes = plugin_file.read_bytes()
        if skin_bytes != plugin_bytes:
            raise ValueError(f'Mirrored tag texture bytes differ for {name}')
        tags_meta[name] = decode_bobilg_png(skin_bytes, name)
        digest = hashlib.sha256(skin_bytes).hexdigest()
        materials[f'{SKIN_GLASS_REL.as_posix()}/{name}'] = digest
        materials[f'{PLUGIN_GLASS_REL.as_posix()}/{name}'] = digest

    for name in CRITICAL_STATIC_TEXTURES:
        for prefix in (SKIN_GLASS_REL, PLUGIN_GLASS_REL):
            rel_str = f'{prefix.as_posix()}/{name}'
            target = addons / rel_str
            if not target.is_file():
                raise FileNotFoundError(f'Missing static glass texture: {target}')
            materials[rel_str] = sha256_file(target)

    return {
        'schema': 1,
        'protocol': PROTOCOL,
        'renderer': RENDERER_REL,
        'renderer_sha256': hashlib.sha256(renderer_raw).hexdigest(),
        'renderer_bytes': len(renderer_raw),
        'required_addons': list(REQUIRED_ADDONS),
        'materials': dict(sorted(materials.items())),
        'tags': dict(sorted(tags_meta.items())),
    }


def render_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=False) + '\n').encode('utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Repository root path')
    parser.add_argument('--output', type=Path, default=None, help='Manifest output path')
    parser.add_argument('--check', action='store_true', help='Verify manifest matches current tree without writing')
    parser.add_argument('--sync-ui', action='store_true', help='Also refresh ui/glass_assets.json PNG mirror hashes')
    args = parser.parse_args(argv)

    root = args.root.resolve()
    out_path = (args.output or (root / DEFAULT_OUT_REL)).resolve()
    manifest = build_manifest(root)
    expected = render_manifest_bytes(manifest)

    if args.check:
        if not out_path.is_file():
            print(f'MISSING: {out_path}', file=sys.stderr)
            return 1
        actual = out_path.read_bytes()
        if actual != expected:
            print(f'MISMATCH: {out_path} is out of date; run tools/update_glass_assets.py', file=sys.stderr)
            return 1
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(expected)

    if args.sync_ui:
        ui_manifest_path = root / 'ui/glass_assets.json'
        skin_glass = root / ADDONS_REL / SKIN_GLASS_REL
        files = {
            p.relative_to(skin_glass).as_posix(): sha256_file(p)
            for p in sorted(skin_glass.rglob('*.png'))
        }
        ui_payload = (json.dumps({'schema': 1, 'files': dict(sorted(files.items()))}, indent=2) + '\n').encode('utf-8')
        ui_manifest_path.write_bytes(ui_payload)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
