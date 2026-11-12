"""Ordinary registered local-path observation; never CD2 or content identity.

The generation binds the registered root configuration, not a kernel mount.
Stat fields detect common replacements, not identical content or exact resume.
"""
from .mounted_ref import digest, hexid, relative

KIND = 'local_path'
FIELDS = {'reference_kind', 'schema', 'id', 'source_id', 'namespace', 'relative',
          'name', 'parent', 'size', 'signature', 'source_generation', 'root_signature'}


def root_signature(value):
    if (type(value) is not dict or set(value) != {'device', 'inode'} or
            any(type(v) is not int or v < 0 for v in value.values())):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    return dict(value)


def validate(ref):
    if (type(ref) is not dict or set(ref) != FIELDS or ref['reference_kind'] != KIND or
            type(ref['schema']) is not int or ref['schema'] != 1 or not hexid(ref['source_id'], 32) or
            not hexid(ref['namespace']) or not hexid(ref['source_generation'])):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    path = relative(ref['relative'])
    if (ref['id'] != digest(KIND, 1, ref['source_id'], ref['namespace'], path) or
            ref['name'] != path.rsplit('/', 1)[-1] or ref['parent'] != path.rpartition('/')[0] or
            type(ref['size']) is not int or not 0 < ref['size'] <= 512 * 1024**3 or
            type(ref['signature']) is not dict or set(ref['signature']) != {'device', 'inode', 'mtime_ns', 'ctime_ns'} or
            any(type(v) is not int or v < 0 for v in ref['signature'].values())):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    return dict(ref, signature=dict(ref['signature']), root_signature=root_signature(ref['root_signature']))


def observed(authority, path, stat):
    path = relative(path)
    return validate(dict(reference_kind=KIND, schema=1,
        id=digest(KIND, 1, authority['source_id'], authority['namespace'], path),
        source_id=authority['source_id'], namespace=authority['namespace'], relative=path,
        name=path.rsplit('/', 1)[-1], parent=path.rpartition('/')[0], size=stat.st_size,
        source_generation=authority['generation'], root_signature=authority.get('root_signature'),
        signature=dict(device=stat.st_dev,
            inode=stat.st_ino, mtime_ns=stat.st_mtime_ns, ctime_ns=stat.st_ctime_ns)))


def same_observation(saved, current):
    saved, current = validate(saved), validate(current)
    return all(saved[key] == current[key] for key in ('id', 'size', 'signature', 'source_generation', 'root_signature'))
