#!/usr/bin/env python3
"""Extract small original metadata from a verified backup. No restore/device writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

from check_backup import inspect, safe_file


def validate_dtb_slots(raw):
    if len(raw) != 512 * 1024:
        raise ValueError('DTB backup must contain two complete 256 KiB slots')
    for pos in (0, 256 * 1024):
        slot = raw[pos:pos+256*1024]
        if slot[:4] != bytes.fromhex('d00dfeed'):
            raise ValueError('Unexpected original DTB format')
        size = struct.unpack_from('>I', slot, 4)[0]
        if not 40 <= size <= len(slot)-16:
            raise ValueError('Invalid DTB payload length')
        stored = struct.unpack_from('<I', slot, len(slot)-4)[0]
        computed = sum(struct.unpack('<65535I', slot[:-4])) & 0xffffffff
        if stored != computed:
            raise ValueError('Original DTB slot checksum mismatch')


def extract(backup, output):
    backup = Path(backup)
    check = inspect(backup)
    before = json.loads(safe_file(backup, 'probe-before.json').read_text())
    rows = before['mpt']['partitions']
    by_name = {p['name']: p for p in rows}
    if len(rows) != 29 or by_name['reserved']['offset'] != 36*1024**2:
        raise ValueError('Unsupported original layout')
    env = by_name['env']
    if env['offset'] != 116*1024**2 or env['size'] != 8*1024**2:
        raise ValueError('Unexpected original environment partition')
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('A new output directory is required')
    output.mkdir(mode=0o700)
    entries = []
    ranges = [('original-mpt-4k.bin',36*1024**2,4096),
              ('original-dtb-two-slots.bin',40*1024**2,512*1024),
              ('original-env-partition.bin',env['offset'],env['size'])]
    with safe_file(backup, 'mmcblk0.img').open('rb') as source:
        for name, offset, size in ranges:
            source.seek(offset)
            raw = source.read(size)
            if len(raw) != size:
                raise ValueError('Short read from verified source image')
            digest = hashlib.sha256(raw).hexdigest()
            if name == 'original-mpt-4k.bin' and digest != before['mpt_sha256']:
                raise ValueError('Original MPT does not match source report')
            if name == 'original-dtb-two-slots.bin':
                validate_dtb_slots(raw)
            path = output/name
            with path.open('xb') as f:
                os.chmod(path, 0o600)
                f.write(raw); f.flush(); os.fsync(f.fileno())
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Extracted recovery metadata readback mismatch')
            entries.append(dict(file=name,source_image='mmcblk0.img',offset=offset,bytes=size,sha256=digest))
    manifest = dict(schema=1,source_backup=str(backup.resolve()),
                    source_manifest_sha256=hashlib.sha256(safe_file(backup,'manifest.json').read_bytes()).hexdigest(),
                    backup_metadata_checks_passed=check['metadata_checks_passed'],
                    backup_full_hashes_rechecked=False,entries=entries,
                    device_writes_performed=False,restore_tested=False,
                    notes=['Original byte ranges only; no flash/restore commands are supplied.',
                           'This small bundle cannot restore overwritten Android applications/data.',
                           'Keep the full verified mmcblk0/boot0/boot1 images on external storage.',
                           'A working external CE or independently verified USB recovery entry is still required.',
                           'Raw environment includes device settings; keep this directory private.'])
    with (output/'manifest.json').open('x') as f:
        json.dump(manifest,f,indent=2); f.flush(); os.fsync(f.fileno())
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try: print(json.dumps(extract(args.backup,args.output),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.exit(1,'Recovery extraction refused: '+str(exc)+'\n')
