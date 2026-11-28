"""Display-only catalogue membership. A filter ID is never a playback locator."""
import hashlib
import json
import re
import unicodedata
from collections import Counter


def visible_name(value):
    if not isinstance(value, str) or not 0 < len(value) <= 120:
        return ''
    text = value.strip()
    if (not text or any(unicodedata.category(c).startswith('C') for c in text)
            or re.search(r'://|[/\\@?#=\[\]$]|(?:www\.|magnet:)|[a-z0-9_-]{32,}', text, re.I)):
        return ''
    return ' '.join(text.split())


def ref(scope, origin):
    return hashlib.sha256((scope + '\0' + origin).encode('utf8')).hexdigest()[:32]


def public_name(item):
    name = visible_name(item.get('name'))
    code = item.get('shareCode', '')
    code = str(code).casefold()
    return name if name and name.casefold() != code and not (len(code) >= 6 and code in name.casefold()) else ''


def directory(cache):
    """Read one bounded directory per search; the DB already belongs to the captured service."""
    if hasattr(cache, '_library_directory'):
        return cache._library_directory
    scope = 'sharelib:' + cache.root.name
    result = {}
    row = cache.db.execute("SELECT value FROM maintenance WHERE key='directory'").fetchone()
    try:
        entries = json.loads(row[0])['items'] if row else []
        for item in entries[:1000]:
            if item.get('isPublic', True) and isinstance(item.get('shareCode'), str):
                result['shared:' + item['shareCode']] = public_name(item)
    except (ValueError, KeyError, TypeError, AttributeError):
        result = {}
    counts = Counter(v.casefold() for v in result.values() if v)
    cache._library_directory = (scope, result, counts)
    return cache._library_directory


def memberships(origins, lookup):
    scope, names, counts = lookup
    result = {}
    for origin in origins:
        if origin.startswith('main:'):
            origin, name = 'main', '自选服务主库'
        elif origin.startswith('shared:'):
            name = names.get(origin, '')
        else:
            continue
        key = ref(scope, origin)
        suffix = key[:8].upper()
        if not name:
            name = '共享库 ' + suffix + '（未返回名称）'
        elif counts.get(name.casefold(), 0) > 1:
            name += ' · ' + suffix
        result[key] = name
    return dict(sorted(result.items(), key=lambda item: (item[1].casefold(), item[0])))


# A configured Torznab endpoint identifies an indexer, never a release group.
PUBLIC_STATIONS = {'nyaasi': 'Nyaa.si', 'knaben': 'Knaben', 'mikan': 'Mikan',
                   'dmhy': '动漫花园', 'bangumi-moe': 'Bangumi Moe',
                   'bangumimoe': 'Bangumi Moe', 'tokyotosho': 'Tokyo Toshokan'}


def bt_station(identifier, feed_id='', feed_name=''):
    safe = visible_name(feed_name)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identifier or ''):
        identifier = feed_id if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', feed_id or '') else ''
    if identifier == 'all':
        identifier = feed_id if feed_id != 'all' else ''
    if not identifier or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identifier):
        return {}
    label = PUBLIC_STATIONS.get(identifier.casefold()) or (safe if identifier == feed_id else '')
    return {ref('jackett', identifier.casefold()): label} if label else {}


def merge_stations(retained, source):
    sites = getattr(source, 'sourceStations', None)
    if not sites or getattr(retained, 'type', '') != 'Torrent' or source.type != 'Torrent':
        return False
    before = getattr(retained, 'sourceStations', {}) or {}
    merged = dict(sorted({**sites, **before}.items())[:32])
    if before == merged:
        return False
    retained.sourceStations = merged
    return True
