"""Data-only TVBox type-4 subscriptions. Never load a spider, rule or executable."""
import base64
from dataclasses import dataclass, field
import json
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4

from .source_endpoint import endpoint as source_endpoint
from .library_contract import LibraryError, MAX_CATALOG_BYTES, Source, _json, _text, direct_url

MAX_SITES = 128
MAX_ROWS = 512
OPS = {'filter', 'ac', 't', 'pg', 'ext', 'ids', 'wd', 'quick', 'play', 'flag', 'extend'}


def document(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_CATALOG_BYTES:
        raise LibraryError('T4_LIMIT')
    value = _json(raw)
    stack, count = [(value, 0)], 0
    while stack:
        obj, depth = stack.pop()
        count += 1
        if depth > 32 or count > 100000:
            raise LibraryError('T4_LIMIT')
        if isinstance(obj, (dict, list)):
            stack.extend((child, depth + 1) for child in (obj.values() if isinstance(obj, dict) else obj))
        elif isinstance(obj, float) and not (-float('inf') < obj < float('inf')):
            raise LibraryError('INVALID_DOCUMENT')
    if not isinstance(value, dict):
        raise LibraryError('INVALID_DOCUMENT')
    return value


def endpoint(url):
    return source_endpoint(url, 'T4_URL')


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def identifier(value):
    # XML/JSON sites commonly encode category or item keys as integer IDs.
    if type(value) is int and 0 <= value <= 2**63 - 1:
        return str(value)
    return _text(value, 4096)


def _site(key, name, api, extend, searchable):
    _text(key, 128)
    _text(name, 120)
    api = endpoint(api)
    try:
        if any(k in OPS for k, _ in parse_qsl(urlsplit(api).query, max_num_fields=128)):
            raise ValueError()
    except ValueError:
        raise LibraryError('T4_URL') from None
    _text(extend, 8192, True)
    if type(searchable) is not bool:
        raise LibraryError('INVALID_DOCUMENT')
    return dict(key=key, name=name, api=api, extend=extend, searchable=searchable)


@dataclass
class Preview:
    sites: list = field(repr=False)
    unsupported: int = 0
    invalid: int = 0

    def source(self, location, previous=None):
        if not self.sites:
            raise LibraryError('T4_NO_SITES')
        return Source(previous.id if previous else uuid4().hex, previous.name if previous else self.sites[0]['name'],
                      't4', location=location, metadata={'sites': self.sites})


def preview(raw, location=''):
    if location:
        endpoint(location)
    data = document(raw)
    rows = data.get('sites')
    if not isinstance(rows, list) or len(rows) > MAX_SITES:
        raise LibraryError('T4_CONFIG')
    result, seen = Preview([]), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('key'), str) or not row['key'].strip():
            result.invalid += 1
            continue
        key = row['key']
        if key in seen:
            raise LibraryError('T4_DUPLICATE')
        seen.add(key)
        if type(row.get('type')) is not int or row['type'] != 4:
            result.unsupported += 1
            continue
        try:
            raw_url = _text(row.get('api'), 8192)
            ext = row.get('ext', '')
            site = _site(key, row.get('name'), urljoin(location, raw_url) if location else raw_url,
                         ext if isinstance(ext, str) else compact(ext), row.get('searchable', 1) != 0)
            # No implicit authority for a configuration to activate a new LAN target.
            # Import confirms each site origin; parsing itself never contacts any.
            result.sites.append(site)
        except (LibraryError, ValueError):
            result.invalid += 1
    return result


def validate_saved(source):
    if source.location:
        endpoint(source.location)
    if (source.username or source.password or source.items or set(source.metadata) != {'sites'} or
            type(source.metadata['sites']) is not list or not 1 <= len(source.metadata['sites']) <= MAX_SITES):
        raise LibraryError('INVALID_SOURCE')
    seen = set()
    for s in source.metadata['sites']:
        if not isinstance(s, dict) or set(s) != {'key', 'name', 'api', 'extend', 'searchable'}:
            raise LibraryError('INVALID_SOURCE')
        _site(**s)
        if s['key'] in seen:
            raise LibraryError('T4_DUPLICATE')
        seen.add(s['key'])


def _page(page):
    if type(page) is not int or not 1 <= page <= 10000:
        raise LibraryError('INVALID_VALUE')
    return page


class Client:
    def __init__(self, site, fetch):
        self.site, self.fetch = site, fetch

    def _call(self, **query):
        api = self.site['api']
        if self.site['extend']:
            query['extend'] = self.site['extend']
        u = urlsplit(api)
        # Preserve unrelated raw query octets: decoded/re-encoded signatures may expire.
        query = (u.query + '&' if u.query else '') + urlencode(query)
        return document(self.fetch(urlunsplit((u.scheme, u.netloc, u.path, query, ''))))

    def home(self):
        return self._call(filter='true')

    def category(self, category, page, filters=None):
        encoded = base64.urlsafe_b64encode(compact(filters or {}).encode('utf-8')).decode('ascii')
        return self._call(ac='detail', t=_text(category, 512), pg=_page(page), ext=encoded)

    def search(self, term, page):
        if not self.site['searchable']:
            raise LibraryError('T4_NO_SEARCH')
        return self._call(wd=_text(term, 512), quick='false', pg=_page(page))

    def detail(self, item_id):
        rows = self._call(ac='detail', ids=_text(item_id, 4096)).get('list')
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or identifier(rows[0].get('vod_id')) != item_id):
            raise LibraryError('T4_CHANGED')
        row = rows[0]
        names = _text(row.get('vod_play_from'), 8192).split('$$$')
        groups = _text(row.get('vod_play_url'), 1024 * 1024).split('$$$')
        if len(names) != len(groups) or len(set(names)) != len(names) or len(names) > MAX_SITES:
            raise LibraryError('T4_LINES')
        result = []
        for name, group in zip(names, groups):
            episodes, seen = [], set()
            for pair in group.split('#'):
                label, sep, ident = pair.partition('$')
                if not sep or ident in seen or len(episodes) >= 2000:
                    raise LibraryError('T4_LINES')
                seen.add(ident)
                episodes.append((_text(label, 240), _text(ident, 8192)))
            result.append((_text(name, 120), episodes))
        return result

    def play(self, line, episode):
        value = self._call(play=_text(episode, 8192), flag=_text(line, 120))
        if (type(value.get('parse')) not in (int, str) or value.get('parse') not in (0, '0') or
                value.get('jx', 0) not in (0, '0') or any(value.get(k) for k in ('audio', 'audioUrl', 'playUrl', 'proxy'))):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        url = direct_url(endpoint(value.get('url')))
        if urlsplit(url).path.lower().endswith(('.m3u', '.m3u8', '.mpd')):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        headers = value.get('header', {})
        if isinstance(headers, str):
            headers = document(headers.encode('utf-8'))
        if not isinstance(headers, dict):
            raise LibraryError('T4_HEADERS')
        cleaned = {}
        for key, val in headers.items():
            canonical = {'user-agent': 'User-Agent', 'referer': 'Referer'}.get(key.lower())
            if not canonical or canonical in cleaned or not isinstance(val, str) or not val.isascii():
                raise LibraryError('T4_HEADERS')
            _text(val, 1024)
            if canonical == 'Referer':
                origin = urlsplit(endpoint(val))
                if origin.query or origin.path not in ('', '/') or origin.netloc not in (
                        urlsplit(self.site['api']).netloc, urlsplit(url).netloc):
                    raise LibraryError('T4_HEADERS')
            cleaned[canonical] = val
        return url, cleaned
