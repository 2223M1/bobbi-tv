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
    return [row for row in groups.values() if 5 < progress(row[1]) < 90]


def history_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


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
