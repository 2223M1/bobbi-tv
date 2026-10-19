"""Bounded, immutable file-list cache; no torrent/media bodies or locators.

Only called after verified_intents has checked the live selected torrent. This
lets an already prepared cloud episode discover E+1 after TorrServer drops its
in-memory torrent. Cache misses are not permission to invent files or IDs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

LIMIT = 2 * 1024 * 1024
MAX_ENTRIES = 64
BACKEND = 'MatriX.144.1'


def normalized(metadata):
    source = metadata.get('hash')
    files = metadata.get('file_stats')
    title = metadata.get('title', '')
    if (not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source)
            or not isinstance(title, str) or len(title) > 4096 or not isinstance(files, list)
            or not 1 <= len(files) <= 4096):
        raise ValueError('Invalid bounded immutable metadata')
    seen_ids, seen_paths = set(), set()
    for f in files:
        if (not isinstance(f, dict) or set(f) != {'id', 'path', 'length'} or type(f['id']) is not int
                or f['id'] < 0 or type(f['length']) is not int or f['length'] < 0
                or not isinstance(f['path'], str) or not 0 < len(f['path']) <= 4096
                or f['path'].startswith('/') or '\\' in f['path'] or '\x00' in f['path']
                or any(p in ('', '.', '..') for p in f['path'].split('/'))):
            raise ValueError('Cache stores only exact file tuples')
        if f['id'] in seen_ids or f['path'] in seen_paths:
            raise ValueError('Cache file identities must be unique')
        seen_ids.add(f['id'])
        seen_paths.add(f['path'])
    value = dict(hash=source, title=title, file_stats=files)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    if len(raw) > LIMIT:
        raise ValueError('Metadata cache entry budget')
    return value, raw


class MetadataCache:
    def __init__(self, root):
        self.root = Path(root)
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('No symlink metadata cache')
        self.root.mkdir(mode=0o700, exist_ok=True)

    def load(self, source):
        if not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source):
            raise ValueError('Exact metadata hash required')
        path = self.root / (source + '.json')
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT + 1024:
            raise ValueError('Invalid metadata cache file')
        document = json.loads(path.read_bytes())
        if set(document) != {'schema', 'backend', 'sha256', 'metadata'} or document['schema'] != 1 or document['backend'] != BACKEND:
            raise ValueError('Metadata cache format/backend drift')
        value, raw = normalized(document['metadata'])
        if value['hash'] != source or hashlib.sha256(raw).hexdigest() != document['sha256']:
            raise ValueError('Metadata cache identity/integrity failed')
        return value

    def store(self, metadata):
        value, raw = normalized(metadata)
        path = self.root / (value['hash'] + '.json')
        existing = self.load(value['hash'])
        if existing is not None:
            if existing != value:
                raise ValueError('An existing torrent cache entry is immutable')
            return True
        if len(list(self.root.glob('*.json'))) >= MAX_ENTRIES:
            return False  # No silent unbounded growth or broad cache deletion.
        document = dict(schema=1, backend=BACKEND, sha256=hashlib.sha256(raw).hexdigest(), metadata=value)
        tmp = self.root / (value['hash'] + '.' + uuid4().hex + '.partial')
        with tmp.open('xb') as stream:
            stream.write(json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        if self.load(value['hash']) != value:
            raise ValueError('Persisted metadata proof failed')
        return True
