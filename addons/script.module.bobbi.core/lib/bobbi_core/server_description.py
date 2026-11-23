"""Bounded server claims, never mappings, content identity or playback grants.

Stored inside reviews.candidates under a nested description. Legacy readers
ignore this origin and cannot mistake its year/season for filename evidence.
"""
from copy import deepcopy
import html
import re

from .server_ref import PROVIDERS, identifier, parts

FIELDS = {'schema', 'provider', 'item_id', 'item_type', 'title', 'overview',
          'year', 'series_title', 'season', 'episode', 'ids'}
LIMITS = {'title': 240, 'overview': 1200, 'series_title': 240}
ID_PATTERNS = {'tmdb': r'[1-9][0-9]{0,8}', 'tvdb': r'[1-9][0-9]{0,8}',
               'imdb': r'tt[0-9]{5,12}'}


def _text(value, limit):
    if type(value) is not str or len(value) > 20000:
        return None
    value = html.unescape(re.sub(r'<[^>]*>', '', value))
    value = ' '.join(value.split())
    if not value or '://' in value or re.search(r'[\x00-\x1f\x7f]', value):
        return None
    return value[:limit]


def observed(provider, item_id, *, item_type=None, title=None, overview=None,
             year=None, series_title=None, season=None, episode=None, ids=None):
    """Optional malformed descriptions stay unknown; file validation is separate."""
    value = dict(schema=1, provider=provider, item_id=identifier(item_id),
        item_type=item_type if item_type in ('movie', 'episode') else 'unknown',
        title=_text(title, 240), overview=_text(overview, 1200),
        series_title=_text(series_title, 240),
        year=year if type(year) is int and 1800 <= year <= 2200 else None,
        season=season if type(season) is int and 0 <= season <= 1000 else None,
        episode=episode if type(episode) is int and 1 <= episode <= 100000 else None,
        ids={})
    for key, pattern in ID_PATTERNS.items():
        candidate = (ids or {}).get(key)
        if type(candidate) is str and re.fullmatch(pattern, candidate):
            value['ids'][key] = candidate
    meaningful = any(value[key] is not None for key in set(LIMITS) | {'year', 'season', 'episode'}) or value['ids']
    return checked(value) if meaningful else None


def checked(value, reference=None):
    if (type(value) is not dict or set(value) != FIELDS or type(value['schema']) is not int
            or value['schema'] != 1 or value['provider'] not in PROVIDERS
            or value['item_type'] not in ('movie', 'episode', 'unknown')):
        raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
    identifier(value['item_id'])
    for key, limit in LIMITS.items():
        if value[key] is not None and (type(value[key]) is not str or not value[key]
                or len(value[key]) > limit or '://' in value[key]
                or re.search(r'[\x00-\x1f\x7f]', value[key])):
            raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
    for key, low, high in (('year', 1800, 2200), ('season', 0, 1000), ('episode', 1, 100000)):
        if value[key] is not None and (type(value[key]) is not int or not low <= value[key] <= high):
            raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
    if (type(value['ids']) is not dict or set(value['ids']) - set(ID_PATTERNS)
            or any(type(v) is not str or not re.fullmatch(ID_PATTERNS[k], v)
                   for k, v in value['ids'].items())):
        raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
    if reference is not None and (reference['provider'] != value['provider']
            or parts(reference['file_id'])[0] != value['item_id']):
        raise ValueError('CATALOG_SERVER_DESCRIPTION_INVALID')
    return deepcopy(value)


def replace_candidate(candidates, description):
    # Never remove/reorder the old filename evidence, including after manual edits.
    result = [deepcopy(row) for row in candidates if row.get('origin') != 'server']
    if description is not None:
        result.append(dict(origin='server', description=checked(description)))
    return result


def effective(candidates, provenance, provider):
    if provenance == 'manual' or provider not in PROVIDERS:
        return None
    rows = [row for row in candidates if row.get('origin') == 'server']
    if len(rows) != 1 or set(rows[0]) != {'origin', 'description'}:
        return None
    try:
        value = checked(rows[0]['description'])
        return value if value['provider'] == provider else None
    except (ValueError, TypeError, KeyError):
        return None


def text(value):
    value = checked(value)
    labels = [value['title'], str(value['year']) if value['year'] else None, value['overview']]
    labels += ['服务器声明 %s=%s（%s）' % (key, number, value['item_type'])
               for key, number in value['ids'].items()]
    labels.append('来源：%s 只读描述；未确认作品匹配，不证明精确内容或续播位置。' % value['provider'])
    return '\n'.join(label for label in labels if label)
