"""Network-path metadata observation, never an inode or content identity."""
from datetime import datetime
import re

from .mounted_ref import digest, hexid, relative

KIND = 'network_path'
FIELDS = {'reference_kind', 'schema', 'id', 'source_id', 'namespace', 'relative',
          'name', 'parent', 'size', 'modified', 'source_generation'}


def metadata(size, modified):
    # Require an actual time, retaining server precision/timezone verbatim.
    # Matching metadata does not establish unchanged bytes or exact resume.
    if (type(size) is not int or not 0 < size <= 512 * 1024**3 or
            type(modified) is not str or not re.fullmatch(
                r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?', modified)):
        raise ValueError('CATALOG_NETWORK_METADATA_REQUIRED')
    try:
        datetime.fromisoformat(modified.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('CATALOG_NETWORK_METADATA_REQUIRED') from None
    return dict(size=size, modified=modified)


def validate(ref):
    if (type(ref) is not dict or set(ref) != FIELDS or ref['reference_kind'] != KIND or
            type(ref['schema']) is not int or ref['schema'] != 1 or
            not hexid(ref['source_id'], 32) or not hexid(ref['namespace']) or
            not hexid(ref['source_generation'])):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    path = relative(ref['relative'])
    if (ref['id'] != digest(KIND, 1, ref['source_id'], ref['namespace'], path) or
            ref['name'] != path.rsplit('/', 1)[-1] or ref['parent'] != path.rpartition('/')[0]):
        raise ValueError('CATALOG_REFERENCE_INVALID')
    metadata(ref['size'], ref['modified'])
    return dict(ref)


def observed(authority, path, info):
    path = relative(path)
    return validate(dict(reference_kind=KIND, schema=1,
        id=digest(KIND, 1, authority['source_id'], authority['namespace'], path),
        source_id=authority['source_id'], namespace=authority['namespace'], relative=path,
        name=path.rsplit('/', 1)[-1], parent=path.rpartition('/')[0],
        source_generation=authority['generation'], **metadata(info.get('size'), info.get('modified'))))


def same_observation(saved, current):
    saved, current = validate(saved), validate(current)
    return all(saved[key] == current[key] for key in ('id', 'size', 'modified', 'source_generation'))
