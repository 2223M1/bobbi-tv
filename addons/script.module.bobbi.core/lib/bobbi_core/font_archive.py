"""Exact-release font asset selection and strict 7-Zip listing validation.

No archive is unpacked by this pure module. A separate bounded child performs
decompression, never the GUI or the single SQLite owner thread.
"""
from pathlib import PurePosixPath
import re

from bobbi_core.metadata_cache import normalized
from bobbi_core.subtitle_binding import checked_video

# Compressed size is not resident memory. Decode still has independent
# 192 MiB address-space, 256 MiB expansion and unchanged CPU/wall budgets.
ARCHIVE_LIMIT = 128 * 1024 * 1024
FONT_LIMIT = 32 * 1024 * 1024
EXPANSION_LIMIT = 256 * 1024 * 1024
ARCHIVE_EXTENSIONS = {'.7z', '.zip', '.rar'}

def canonical(name):
    if (not isinstance(name, str) or not name or len(name) > 2048
            or any(ord(c) < 32 for c in name) or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute() or any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('Unsafe font asset path')
    return name

def release_assets(video, metadata):
    checked_video(video)
    meta, _ = normalized(metadata)
    chosen = video['selected']
    current = dict(id=chosen['torrent_file_id'], path=chosen['torrent_path'], length=chosen['torrent_file_bytes'])
    if meta['hash'] != chosen['source_info_hash'] or current not in meta['file_stats']:
        raise ValueError('Font assets belong to another release')
    direct, archives = [], []
    parents = tuple(PurePosixPath(chosen['torrent_path']).parents)
    for entry in meta['file_stats']:
        path = PurePosixPath(canonical(entry['path']))
        suffix = path.suffix.casefold()
        scope = path.parent
        # Adjacent or shared ancestor Fonts folders are eligible; another
        # season/release subtree is not. Directory provenance, never title IDs.
        while scope.name.casefold().strip('[]() ') in {'font', 'fonts', '字体', '字體'}:
            scope = scope.parent
        if scope not in parents:
            continue
        if suffix in ('.ttf', '.otf', '.ttc'):
            if not 0 < entry['length'] <= FONT_LIMIT:
                raise ValueError('Individual release font budget')
            direct.append((parents.index(scope), dict(entry)))
        elif (suffix in ARCHIVE_EXTENSIONS
              and re.search(r'(?i)(?:^|[\s\[(_.-])fonts?(?:[\s\])_.-]|$)|字体|字體', path.stem)):
            if not 0 < entry['length'] <= ARCHIVE_LIMIT:
                raise ValueError('Release font archive budget')
            archives.append((parents.index(scope), dict(entry)))
    if direct or archives:
        nearest = min(row[0] for row in direct + archives)
        direct = [row for depth, row in direct if depth == nearest]
        archives = [row for depth, row in archives if depth == nearest]
    if len(direct) > 128 or len(archives) > 2 or sum(f['length'] for f in direct + archives) > EXPANSION_LIMIT:
        raise ValueError('Release font asset budget')
    return direct + archives

def parse_listing(raw):
    if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024:
        raise ValueError('Archive listing budget')
    text = raw.decode('utf-8').replace('\r\n', '\n')
    marker = '\n----------\n'
    if marker not in text: raise ValueError('Unknown archive listing')
    # Empty final properties (e.g. RAR's "NT Security = ") are legitimate.
    # Stripping spaces would turn them into malformed "NT Security =".
    blocks = text.split(marker, 1)[1].strip('\n').split('\n\n')
    if len(blocks) > 512: raise ValueError('Archive entry budget')
    fonts, names, total = [], set(), 0
    for block in blocks:
        row = {}
        for line in block.splitlines():
            if ' = ' not in line: raise ValueError('Ambiguous archive property')
            key, value = line.split(' = ', 1)
            if key in row: raise ValueError('Duplicate archive property')
            row[key] = value
        name = canonical(row.get('Path'))
        if name in names: raise ValueError('Duplicate archive path')
        names.add(name)
        folder = row.get('Folder')
        attributes = row.get('Attributes')
        if attributes is not None:
            # Windows-origin 7z members omit Folder. Accept only the documented
            # simple DOS flags, never infer a regular file from Unix link modes.
            if not re.fullmatch('[RASHDN]+', attributes) or len(set(attributes)) != len(attributes):
                raise ValueError('Unsupported archive attributes')
            inferred = '+' if 'D' in attributes else '-'
            if folder is not None and folder != inferred:
                raise ValueError('Conflicting archive entry type')
            folder = inferred
        if (row.get('Encrypted') not in (None, '-') or row.get('Symbolic Link') or row.get('Hard Link')
                or row.get('Copy Link') or row.get('Alternate Stream') not in (None, '-')
                or row.get('Split Before') not in (None, '-') or row.get('Split After') not in (None, '-')
                or row.get('Anti') not in (None, '-') or folder not in ('+', '-')):
            raise ValueError('Unsupported archive entry type')
        size = row.get('Size', '')
        if not re.fullmatch('[0-9]{1,12}', size): raise ValueError('Missing archive size')
        size = int(size)
        total += size
        if total > EXPANSION_LIMIT: raise ValueError('Archive expansion budget')
        if folder == '+':
            if size: raise ValueError('Nonempty directory entry')
            continue
        if PurePosixPath(name).suffix.casefold() in ('.ttf', '.otf', '.ttc'):
            if not 0 < size <= FONT_LIMIT: raise ValueError('Individual font budget')
            fonts.append(dict(path=name, bytes=size))
    if not 1 <= len(fonts) <= 128: raise ValueError('No bounded font set')
    return fonts
