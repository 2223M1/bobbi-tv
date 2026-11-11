"""Pure presentation rules. Never rewrite a source or an episode identity."""
import math
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit, urlunsplit


def text(value):
    return value.strip() if isinstance(value, str) else ''


def integer(value):
    if isinstance(value, bool) or value is None:
        return None
    value = str(value)
    return int(value) if value.isdecimal() and len(value) <= 9 else None


def chinese(value):
    value = text(value)
    return value if re.search(r'[\u3400-\u9fff]', value) and not re.search(r'[ぁ-ゖァ-ヺ]', value) else ''


def season_name(value):
    value = chinese(value)
    return '' if re.fullmatch(r'第\s*[\d一二三四五六七八九十百]+\s*[季期部]|特别篇|特別篇', value) else value


def clean_title(value):
    value = unquote(text(value))
    value = re.sub(r'\s*\((?:Torrent|Direct|Debrid|Stremio)\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s+S\d+E\d+\s*$', '', value, flags=re.I)
    return re.sub(r'\s*[·•]\s*第\s*\d+\s*季\s*$', '', value).strip()


def image_url(value, size):
    from bobbi_core.image_cache import image_url as tmdb_image_url
    return tmdb_image_url(text(value), size)


def history_identity(data, fallback=''):
    ids = data.get('ids') or {}
    identifier = integer(ids.get('tmdb_id') or data.get('tmdb_id'))
    tv = data.get('tv_data') or {}
    mode = data.get('mode') or data.get('media_type')
    if not identifier:
        return ('unidentified', fallback)
    if tv or mode in ('tv', 'show', 'episode', 'tvshow'):
        season, episode = integer(tv.get('season')), integer(tv.get('episode'))
        if season is None or episode is None:
            return ('unidentified', fallback)
        return ('tv', identifier, season, episode)
    if mode in ('movie', 'movies'):
        return ('movie', identifier)
    return ('unidentified', fallback)


def progress(data):
    try:
        value = float(data.get('progress', 0))
        return value if math.isfinite(value) else 0
    except (ValueError, TypeError):
        return 0


def history_rows(items, time_key):
    """Deduplicate BEFORE progress filtering, so completed sources stay completed."""
    groups = {}
    for key, data in sorted(reversed(list(items)), key=time_key, reverse=True):
        identity = history_identity(data, key)
        if identity not in groups:
            groups[identity] = [key, data, []]
        groups[identity][2].append(key)
    # New exact-player rows carry an explicit terminal-derived completion bit.
    # A network error at 97% must retain its true resume point. Old records keep
    # their historical threshold; no database-wide rewrite or fake percentage.
    return [row for row in groups.values()
            if ((progress(row[1]) > 0 and not row[1]['completed'])
                if type(row[1].get('completed')) is bool else 5 < progress(row[1]) < 90)]


def history_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


RAIL_STATES = frozenset(('loading', 'ready', 'empty', 'stale', 'error', 'auth_required'))


def rail_properties(state, *, revision='', scope='public', reason=''):
    """Provider-owned presentation receipt, attached to this result, never global.

    A zero item count is not evidence of a successful empty query. Callers must
    explicitly classify their result. This receipt never authorizes playback.
    """
    if state not in RAIL_STATES:
        raise ValueError('RAIL_STATE_INVALID')
    if reason and not re.fullmatch('[A-Z_]{1,64}', reason):
        raise ValueError('RAIL_REASON_INVALID')
    return {'Bobi.Rail.State': state, 'Bobi.Rail.Revision': str(revision),
            'Bobi.Rail.Scope': scope, 'Bobi.Rail.Reason': reason}


def apply_rail_state(items, state, **kwargs):
    properties = rail_properties(state, **kwargs)
    for _, item, _ in items:
        for key, value in properties.items():
            item.setProperty(key, value)
    return items


def personal_file_projection(record, labels):
    """Display only. A ready-looking row never proves remote availability."""
    ref = record['file_ref']
    duration, position = record['duration'], record['position']
    return dict(title=ref['name'], source=labels.get(ref['provider'], ref['provider']),
        percent=min(100, round(100 * position / duration)) if duration else None,
        state='verification_required', kind='原文件',
        detail='恢复时核验原账号与文件 · 待实机验证')


def translations(details, kind):
    field = 'title' if kind == 'movie' else 'name'
    result = {'zh': '', 'en': ''}
    for row in (details.get('translations') or {}).get('translations', []):
        locale = (row.get('iso_639_1'), row.get('iso_3166_1'))
        value = clean_title((row.get('data') or {}).get(field))
        if locale == ('zh', 'CN'):
            result['zh'] = chinese(value)
        elif locale == ('en', 'US'):
            result['en'] = value
    original = text(details.get('original_title') or details.get('original_name'))
    language = details.get('original_language')
    if not result['zh'] and language in ('zh', 'cn'):
        result['zh'] = chinese(original)
    if not result['en'] and language == 'en':
        result['en'] = original
    return result
