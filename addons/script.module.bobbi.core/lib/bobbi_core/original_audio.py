"""Optional, request-bound original-language hint; never playback authority."""
import hashlib
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ISO 639-1. TMDb's original_language is a single code, not a title heuristic.
LANGUAGES = frozenset(('aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs '
    'ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy '
    'ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv '
    'ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi '
    'mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps '
    'pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te '
    'tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu').split())
PROPERTIES = ('language', 'request_id', 'file_identity', 'url_sha256')


def language(value):
    if type(value) is not str or not re.fullmatch('[A-Za-z]{2}', value):
        return ''
    value = value.lower()
    return value if value in LANGUAGES else ''


def fresh(fetched, now):
    return (type(fetched) in (int, float) and type(now) in (int, float)
        and math.isfinite(fetched) and math.isfinite(now) and 0 <= now - fetched < 86400)


def from_successful_cache(data, kind, identifier, request_id, now):
    """A soft preference issued now; not a claim about the fetch timestamp."""
    if (kind not in ('movie', 'tv') or type(identifier) is not int or identifier < 1
            or type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id)
            or type(now) not in (int, float) or not math.isfinite(now)):
        return None
    name = 'title' if kind == 'movie' else 'name'
    if (type(data) is not dict or type(data.get('id')) is not int or data['id'] != identifier
            or type(data.get(name)) is not str or not 1 <= len(data[name].strip()) <= 512
            or data.get('success') is False or 'error' in data or 'errors' in data):
        return None
    code = language(data.get('original_language'))
    if not code:
        return None
    return dict(schema=1, request_id=request_id, kind=kind, tmdb_id=identifier,
                language=code, issued_at=now)


def from_record(record, kind, identifier, request_id, now):
    if type(record) is not dict or not fresh(record.get('fetched'), now):
        return None
    return from_successful_cache(record.get('data'), kind, identifier, request_id, now)


def checked(value, request_id, now):
    if type(value) is str:
        if not 1 <= len(value) <= 512:
            return None
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if (type(value) is not dict or set(value) != {'schema', 'request_id', 'kind', 'tmdb_id', 'language', 'issued_at'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id)
            or value['request_id'] != request_id or value['kind'] not in ('movie', 'tv')
            or type(value['tmdb_id']) is not int or value['tmdb_id'] < 1
            or not fresh(value['issued_at'], now) or now - value['issued_at'] > 300
            or language(value['language']) != value['language']):
        return None
    return value if value['language'] else None


def handoff_url(url, hint, request_id, now):
    """No inheritance assumption: carry a bounded hint to Jacktorr's final item."""
    parts = urlsplit(url)
    if parts.scheme != 'plugin' or parts.netloc not in ('plugin.video.jacktorr', 'plugin.video.bobbi.torrent'):
        return url
    pairs = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key != 'original_audio_hint']
    proof = checked(hint, request_id, now)
    if (proof and [value for key, value in pairs if key == 'request_id'] == [request_id]
            and [value for key, value in pairs if key == 'selection_policy'] == ['exact']):
        pairs.append(('original_audio_hint', json.dumps(proof, separators=(',', ':'))))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


def attach(item, hint, context, url, now):
    """Called only after exact final-file claim; absent/invalid hint is a no-op."""
    for suffix in PROPERTIES:
        item.setProperty('bobitv.original_audio.' + suffix, '')
    if type(context) is not dict:
        return False
    request = context.get('request_id')
    proof = checked(hint, request, now)
    identity = context.get('file_identity')
    if (not proof or type(identity) is not str or not 1 <= len(identity) <= 1024
            or type(url) is not str or not url or url.startswith('plugin://')
            or item.getProperty('bobitv.request_id') != request
            or item.getProperty('bobitv.file_identity') != identity):
        return False
    values = (proof['language'], request, identity, hashlib.sha256(url.encode('utf-8')).hexdigest())
    for suffix, value in zip(PROPERTIES, values):
        item.setProperty('bobitv.original_audio.' + suffix, value)
    return True
