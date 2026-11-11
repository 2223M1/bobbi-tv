"""Typed path observation, intentionally not a NativePan FileRef.

Location is stable only within a Registry root. Stat evidence is conservative
replacement detection, not a content hash or cross-mount resume authority.
"""
import hashlib
import json
import re

KIND = 'mounted_path'
FIELDS = {'reference_kind', 'schema', 'id', 'source_id', 'namespace', 'relative',
          'name', 'parent', 'size', 'signature', 'mount_generation'}


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()


def hexid(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def relative(value, empty=False):
    if (type(value) is not str or len(value) > 4096 or not value and not empty or
            any(ord(c) < 32 or ord(c) == 127 for c in value) or any(c in value for c in ('\\', ':', '|')) or
            value and any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    return value


def validate(ref):
    if (type(ref) is not dict or set(ref) != FIELDS or ref['reference_kind'] != KIND or
            type(ref['schema']) is not int or ref['schema'] != 1 or not hexid(ref['source_id'], 32) or
            not hexid(ref['namespace']) or not hexid(ref['mount_generation'])):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    path = relative(ref['relative'])
    if (ref['id'] != digest(KIND, 1, ref['source_id'], ref['namespace'], path) or
            ref['name'] != path.rsplit('/', 1)[-1] or ref['parent'] != path.rpartition('/')[0] or
            type(ref['size']) is not int or not 0 < ref['size'] <= 512 * 1024**3 or
            type(ref['signature']) is not dict or set(ref['signature']) != {'device', 'inode', 'mtime_ns', 'ctime_ns'} or
            any(type(v) is not int or v < 0 for v in ref['signature'].values())):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    return dict(ref, signature=dict(ref['signature']))


def observed(authority, path, stat):
    path = relative(path)
    return validate(dict(reference_kind=KIND, schema=1,
        id=digest(KIND, 1, authority['source_id'], authority['namespace'], path),
        source_id=authority['source_id'], namespace=authority['namespace'], relative=path,
        name=path.rsplit('/', 1)[-1], parent=path.rpartition('/')[0], size=stat.st_size,
        mount_generation=authority['generation'], signature=dict(device=stat.st_dev,
            inode=stat.st_ino, mtime_ns=stat.st_mtime_ns, ctime_ns=stat.st_ctime_ns)))


def same_observation(saved, current):
    saved, current = validate(saved), validate(current)
    return all(saved[key] == current[key] for key in ('id', 'size', 'signature', 'mount_generation'))
