"""Bounded descriptive metadata only. No playback or same-release authority."""
import re

from .filename_semantics import parse_filename

STATES = ('unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored')


def text(value, maximum=240):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or re.search(r'[\x00-\x1f\x7f]', value) or '://' in value):
        raise ValueError('CATALOG_METADATA_INVALID')
    return value.strip()


def mapping(value):
    if type(value) is not dict or set(value) != {'kind', 'title', 'tmdb_id', 'season', 'episode', 'version'}:
        raise ValueError('CATALOG_MAPPING_INVALID')
    result = dict(value, title=text(value['title']))
    if value['kind'] not in ('custom', 'movie', 'tv'):
        raise ValueError('CATALOG_MAPPING_INVALID')
    if value['version'] is not None:
        result['version'] = text(value['version'], 80)
    if value['kind'] == 'custom':
        if any(value[k] is not None for k in ('tmdb_id', 'season', 'episode')):
            raise ValueError('CATALOG_MAPPING_INVALID')
    else:
        if type(value['tmdb_id']) is not int or not 0 < value['tmdb_id'] < 2**31:
            raise ValueError('CATALOG_MAPPING_INVALID')
        if value['kind'] == 'movie':
            if value['season'] is not None or value['episode'] is not None:
                raise ValueError('CATALOG_MAPPING_INVALID')
        elif (type(value['season']) is not int or not 0 <= value['season'] <= 1000
                or type(value['episode']) is not int or not 1 <= value['episode'] <= 100000):
            raise ValueError('CATALOG_MAPPING_INVALID')
    return result


def suggestion(name):
    """Keep conservative filename evidence, never turn an unknown into S01E01."""
    parsed = parse_filename(name)
    pairs = sorted(parsed.episode_pairs())
    years = sorted(set(re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', name)))
    evidence = dict(origin='filename', season=None, episode=None,
                    year=int(years[0]) if len(years) == 1 else None)
    if len(pairs) == 1:
        evidence['season'], evidence['episode'] = pairs[0]
        return 'proposed', 'FILENAME_ONLY', [evidence]
    if len(pairs) > 1 or len(years) > 1 or parsed.markers:
        return 'ambiguous', 'IDENTITY_UNPROVEN', [evidence]
    return 'unmatched', 'NO_CATALOG_IDENTITY', [evidence]


def command(value):
    if (type(value) is not dict or set(value) != {'file_id', 'expected_revision', 'action', 'mapping'}
            or type(value['file_id']) is not str or not re.fullmatch('[0-9a-f]{64}', value['file_id'])
            or type(value['expected_revision']) is not int or value['expected_revision'] < 0
            or value['action'] not in ('confirm', 'unbind', 'ignore', 'undo')):
        raise ValueError('CATALOG_REVIEW_INVALID')
    result = dict(value)
    if value['action'] == 'confirm':
        result['mapping'] = mapping(value['mapping'])
    elif value['mapping'] is not None:
        raise ValueError('CATALOG_REVIEW_INVALID')
    return result
