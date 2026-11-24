"""Data-only TVBox type-4 subscriptions. Never load a spider, rule or executable."""
import base64
from dataclasses import dataclass, field
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4

from .source_endpoint import endpoint as source_endpoint
from .library_contract import LibraryError, MAX_CATALOG_BYTES, Source, _json, _text, direct_url

MAX_SITES = 128
MAX_ROWS = 512
OPS = {'filter', 'ac', 't', 'pg', 'ext', 'ids', 'wd', 'quick', 'play', 'flag', 'extend'}
ALLOWED_HEADERS = {
    'user-agent': 'User-Agent',
    'referer': 'Referer',
    'accept': 'Accept',
    'accept-language': 'Accept-Language',
}
UNSUPPORTED_TOP_FIELDS = (
    'spider',
    'lives',
    'parses',
    'rules',
    'ijk',
    'ads',
    'doh',
    'hosts',
    'flags',
    'wallpaper',
    'logo',
)
_SENSITIVE_HEADER_VALUE_RE = re.compile(
    r'(?i)(?:'
    r'\b(?:bearer|basic|digest)\s+[A-Za-z0-9._~+/=-]{4,}'
    r'|(?:cookie|set-cookie|authorization|x-emby-token|x-plex-token|x-api-key)\s*[:=]'
    r'|(?:[?&;#]|^)(?:token|access_token|auth|api_?key|secret|password|passwd|pwd|sign|signature|session|sid|jwt)='
    r')'
)


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


def validate_headers(raw_headers, *, allowed_hosts=()):
    """Validate API or media request headers by both field name allowlist and value safety."""
    if raw_headers is None or raw_headers == '' or raw_headers == {}:
        return {}
    headers = raw_headers
    if isinstance(headers, str):
        try:
            headers = document(headers.encode('utf-8'))
        except LibraryError as exc:
            raise LibraryError('T4_HEADERS') from exc
    if not isinstance(headers, dict) or len(headers) > 8:
        raise LibraryError('T4_HEADERS')
    cleaned = {}
    for key, val in headers.items():
        if not isinstance(key, str):
            raise LibraryError('T4_HEADERS')
        canonical = ALLOWED_HEADERS.get(key.strip().lower())
        if not canonical or canonical in cleaned or not isinstance(val, str) or not val.isascii():
            raise LibraryError('T4_HEADERS')
        try:
            _text(val, 1024)
        except LibraryError:
            raise LibraryError('T4_HEADERS') from None
        if _SENSITIVE_HEADER_VALUE_RE.search(val):
            raise LibraryError('T4_HEADERS')
        if canonical == 'Referer':
            try:
                origin = urlsplit(endpoint(val))
            except LibraryError:
                raise LibraryError('T4_HEADERS') from None
            if origin.query or origin.fragment or origin.path not in ('', '/'):
                raise LibraryError('T4_HEADERS')
            if allowed_hosts and origin.netloc not in allowed_hosts:
                raise LibraryError('T4_HEADERS')
        cleaned[canonical] = val
    return cleaned


def _site(key, name, api, extend, searchable, headers=None):
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
    cleaned_headers = validate_headers(headers, allowed_hosts=(urlsplit(api).netloc,))
    out = dict(key=key, name=name, api=api, extend=extend, searchable=searchable)
    if cleaned_headers:
        out['headers'] = cleaned_headers
    return out


@dataclass
class Preview:
    sites: list = field(repr=False)
    unsupported: int = 0
    invalid: int = 0
    unsupported_headers: int = 0
    header_rejected_keys: list = field(default_factory=list)

    def source(self, location, previous=None):
        if not self.sites:
            if self.unsupported_headers > 0 and self.unsupported == 0 and self.invalid == 0:
                raise LibraryError('T4_HEADERS')
            raise LibraryError('T4_NO_SITES')
        return Source(previous.id if previous else uuid4().hex, previous.name if previous else self.sites[0]['name'],
                      't4', location=location, metadata={'sites': self.sites})


def _extract_site_header_field(row: dict):
    has_h1 = 'header' in row
    has_h2 = 'headers' in row
    if has_h1 and has_h2:
        raise LibraryError('T4_HEADERS')
    if has_h1:
        return row['header']
    if has_h2:
        return row['headers']
    return None


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
            raw_hdr = _extract_site_header_field(row)
            site = _site(
                key,
                row.get('name'),
                urljoin(location, raw_url) if location else raw_url,
                ext if isinstance(ext, str) else compact(ext),
                row.get('searchable', 1) != 0,
                headers=raw_hdr,
            )
            # No implicit authority for a configuration to activate a new LAN target.
            # Import confirms each site origin; parsing itself never contacts any.
            result.sites.append(site)
        except LibraryError as exc:
            if exc.code == 'T4_HEADERS':
                result.unsupported_headers += 1
                result.header_rejected_keys.append(key[:80])
            else:
                result.invalid += 1
        except ValueError:
            result.invalid += 1
    return result


def diagnose_config(raw: bytes, base_url: str = '') -> dict:
    """Pure, network-free structural diagnosis for TVBox / T4 JSON configurations (REV-12)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError('raw bytes required')
    raw_bytes = bytes(raw)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    size = len(raw_bytes)
    if base_url:
        try:
            base_url = endpoint(base_url.strip())
        except LibraryError as exc:
            return dict(
                ok=False,
                error_code=exc.code,
                sha256=digest,
                byte_length=size,
                can_save_t4=False,
                counts=dict(type4=0, type3=0, unsupported_type=0, unsupported_headers=0, invalid=0, lives=0),
                type4_sites=[],
                type3_spiders=[],
                unsupported_type_sites=[],
                unsupported_header_sites=[],
                lives_subscriptions=[],
                unsupported_top_fields=[],
                summary_zh='订阅地址不受支持：远程请用 HTTPS，局域网可用私有 IP 的 HTTP 地址。',
            )
    try:
        data = document(raw_bytes)
    except LibraryError as exc:
        msg = (
            '配置文件超过 2 MB 大小或嵌套深度上限。'
            if exc.code == 'T4_LIMIT'
            else '不是合法的标准 UTF-8 JSON 对象（不支持加密壳、注释或网页内容）。'
        )
        return dict(
            ok=False,
            error_code=exc.code,
            sha256=digest,
            byte_length=size,
            can_save_t4=False,
            counts=dict(type4=0, type3=0, unsupported_type=0, unsupported_headers=0, invalid=0, lives=0),
            type4_sites=[],
            type3_spiders=[],
            unsupported_type_sites=[],
            unsupported_header_sites=[],
            lives_subscriptions=[],
            unsupported_top_fields=[],
            summary_zh=msg,
        )

    top_unsupported = sorted(k for k in UNSUPPORTED_TOP_FIELDS if k in data and data.get(k))
    top_spider_jar = data.get('spider') if isinstance(data.get('spider'), str) else ''

    lives_rows = data.get('lives')
    lives_out = []
    if isinstance(lives_rows, list):
        for idx, lrow in enumerate(lives_rows[:128]):
            if not isinstance(lrow, dict):
                continue
            lname = str(lrow.get('name') or f'live_{idx + 1}')[:80]
            lurl = str(lrow.get('url') or '').strip()
            lscheme = urlsplit(lurl).scheme.lower() if lurl else ''
            lives_out.append(dict(
                name=lname,
                live_type=lrow.get('type') if type(lrow.get('type')) is int else None,
                scheme=lscheme if lscheme in ('http', 'https') else 'unsupported',
                has_epg=bool(lrow.get('epg')),
                has_custom_ua=bool(lrow.get('ua') or lrow.get('header')),
            ))

    rows = data.get('sites')
    if not isinstance(rows, list) or len(rows) > MAX_SITES:
        return dict(
            ok=False,
            error_code='T4_CONFIG',
            sha256=digest,
            byte_length=size,
            can_save_t4=False,
            counts=dict(type4=0, type3=0, unsupported_type=0, unsupported_headers=0, invalid=0, lives=len(lives_out)),
            type4_sites=[],
            type3_spiders=[],
            unsupported_type_sites=[],
            unsupported_header_sites=[],
            lives_subscriptions=lives_out,
            unsupported_top_fields=top_unsupported,
            summary_zh='缺少有效的 sites 列表（不支持多仓 urls 递归索引或超过 128 站上限）。',
        )

    type4_sites = []
    type3_spiders = []
    unsupported_type_sites = []
    unsupported_header_sites = []
    invalid_count = 0
    seen_keys = set()

    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('key'), str) or not row['key'].strip():
            invalid_count += 1
            continue
        key = row['key'].strip()[:128]
        name = str(row.get('name') or key).strip()[:120]
        if key in seen_keys:
            return dict(
                ok=False,
                error_code='T4_DUPLICATE',
                sha256=digest,
                byte_length=size,
                can_save_t4=False,
                counts=dict(
                    type4=len(type4_sites),
                    type3=len(type3_spiders),
                    unsupported_type=len(unsupported_type_sites),
                    unsupported_headers=len(unsupported_header_sites),
                    invalid=invalid_count,
                    lives=len(lives_out),
                ),
                type4_sites=type4_sites,
                type3_spiders=type3_spiders,
                unsupported_type_sites=unsupported_type_sites,
                unsupported_header_sites=unsupported_header_sites,
                lives_subscriptions=lives_out,
                unsupported_top_fields=top_unsupported,
                summary_zh=f'配置中存在重复站点标识：{key}，未保存任何配置。',
            )
        seen_keys.add(key)
        stype = row.get('type')
        searchable = row.get('searchable', 1) != 0
        if type(stype) is int and stype == 3:
            api_val = str(row.get('api') or '').strip()[:240]
            api_low = api_val.lower()
            key_low = key.lower()
            if api_val.startswith('csp_'):
                spider_kind = 'csp_jar'
            elif '.js' in api_low or 'drpy' in api_low:
                spider_kind = 'remote_js'
            else:
                spider_kind = 'custom_spider'
            jar_val = str(row.get('jar') or top_spider_jar or '').strip()
            jar_clean = jar_val.split(';', 1)[0].strip()
            rel_jar = bool(jar_clean and '://' not in jar_clean and not base_url)
            hint = None
            if 'alist' in key_low or 'alist' in api_low or 'xiaoya' in key_low or 'xiaoya' in jar_clean.lower():
                hint = 'alist'
            elif 'webdav' in key_low or 'webdav' in api_low:
                hint = 'webdav'
            elif 'emby' in key_low or 'emby' in api_low:
                hint = 'emby'
            type3_spiders.append(dict(
                key=key,
                name=name,
                api=api_val,
                spider_kind=spider_kind,
                has_site_jar=bool(row.get('jar')),
                relative_jar_missing_base=rel_jar,
                searchable=searchable,
                native_hint=hint,
            ))
            continue
        if type(stype) is not int or stype != 4:
            unsupported_type_sites.append(dict(key=key, name=name, site_type=stype))
            continue
        try:
            raw_url = _text(row.get('api'), 8192)
            ext = row.get('ext', '')
            resolved_url = urljoin(base_url, raw_url) if base_url else raw_url
            raw_hdr = _extract_site_header_field(row)
            site = _site(
                key,
                row.get('name'),
                resolved_url,
                ext if isinstance(ext, str) else compact(ext),
                searchable,
                headers=raw_hdr,
            )
            parsed_u = urlsplit(site['api'])
            type4_sites.append(dict(
                key=site['key'],
                name=site['name'],
                origin=f'{parsed_u.scheme}://{parsed_u.netloc}',
                searchable=site['searchable'],
                has_headers=bool(site.get('headers')),
            ))
        except LibraryError as exc:
            if exc.code == 'T4_HEADERS':
                unsupported_header_sites.append(dict(key=key, name=name, reason='T4_HEADERS'))
            else:
                invalid_count += 1
        except ValueError:
            invalid_count += 1

    counts = dict(
        type4=len(type4_sites),
        type3=len(type3_spiders),
        unsupported_type=len(unsupported_type_sites),
        unsupported_headers=len(unsupported_header_sites),
        invalid=invalid_count,
        lives=len(lives_out),
    )
    can_save = counts['type4'] > 0
    parts = [f"可用 T4 站点 {counts['type4']} 个"]
    if counts['type3']:
        rel_cnt = sum(1 for s in type3_spiders if s['relative_jar_missing_base'])
        extra_rel = f'（其中 {rel_cnt} 个引用相对 JAR 且缺少订阅基址）' if rel_cnt else ''
        parts.append(f"传统 type-3 Spider 站点 {counts['type3']} 个{extra_rel}")
    if counts['unsupported_headers']:
        parts.append(f"请求头受限站点 {counts['unsupported_headers']} 个")
    if counts['unsupported_type']:
        parts.append(f"其他不支持 type 站点 {counts['unsupported_type']} 个")
    if counts['invalid']:
        parts.append(f"无效站点 {counts['invalid']} 个")
    if counts['lives']:
        parts.append(f"直播订阅 {counts['lives']} 项")
    tail = '可导入受支持的 T4 站点。' if can_save else '当前无直接可用的 type-4 站点，未写入片库配置；type-3 Spider 需通过外部 T4 桥接服务或改连原生 AList/WebDAV/Emby。'

    return dict(
        ok=True,
        error_code=None if can_save else ('T4_HEADERS' if counts['unsupported_headers'] and not counts['type3'] else 'T4_NO_SITES'),
        sha256=digest,
        byte_length=size,
        can_save_t4=can_save,
        counts=counts,
        type4_sites=type4_sites,
        type3_spiders=type3_spiders,
        unsupported_type_sites=unsupported_type_sites,
        unsupported_header_sites=unsupported_header_sites,
        lives_subscriptions=lives_out,
        unsupported_top_fields=top_unsupported,
        summary_zh='，'.join(parts) + '。' + tail,
    )


def validate_saved(source):
    if source.location:
        endpoint(source.location)
    if (source.username or source.password or source.items or set(source.metadata) != {'sites'} or
            type(source.metadata['sites']) is not list or not 1 <= len(source.metadata['sites']) <= MAX_SITES):
        raise LibraryError('INVALID_SOURCE')
    seen = set()
    for s in source.metadata['sites']:
        if not isinstance(s, dict) or set(s) not in (
            {'key', 'name', 'api', 'extend', 'searchable'},
            {'key', 'name', 'api', 'extend', 'searchable', 'headers'},
        ):
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

    def detail_record(self, item_id):
        rows = self._call(ac='detail', ids=_text(item_id, 4096)).get('list')
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or identifier(rows[0].get('vod_id')) != item_id):
            raise LibraryError('T4_CHANGED')
        row = rows[0]
        names = _text(row.get('vod_play_from'), 8192).split('$$$')
        groups = _text(row.get('vod_play_url'), 1024 * 1024).split('$$$')
        if len(names) != len(groups) or len(set(names)) != len(names) or len(names) > MAX_SITES:
            raise LibraryError('T4_LINES')
        lines = []
        for name, group in zip(names, groups):
            episodes, seen = [], set()
            for pair in group.split('#'):
                label, sep, ident = pair.partition('$')
                if not sep or ident in seen or len(episodes) >= 2000:
                    raise LibraryError('T4_LINES')
                seen.add(ident)
                episodes.append((_text(label, 240), _text(ident, 8192)))
            lines.append((_text(name, 120), episodes))
        pic = str(row.get('vod_pic') or '').strip()
        try:
            pic = endpoint(pic) if pic else ''
        except LibraryError:
            pic = ''
        return dict(
            vod_id=item_id,
            title=_text(row.get('vod_name') or item_id, 240),
            poster=pic,
            remarks=str(row.get('vod_remarks') or '').strip()[:120],
            year=str(row.get('vod_year') or '').strip()[:16],
            type_name=str(row.get('type_name') or '').strip()[:80],
            plot=str(row.get('vod_content') or '').strip()[:4096],
            lines=lines,
        )

    def detail(self, item_id):
        return self.detail_record(item_id)['lines']

    def play(self, line, episode):
        value = self._call(play=_text(episode, 8192), flag=_text(line, 120))
        if (type(value.get('parse')) not in (int, str) or value.get('parse') not in (0, '0') or
                value.get('jx', 0) not in (0, '0') or any(value.get(k) for k in ('audio', 'audioUrl', 'playUrl', 'proxy'))):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        url = direct_url(endpoint(value.get('url')))
        if urlsplit(url).path.lower().endswith(('.m3u', '.m3u8', '.mpd')):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        cleaned = validate_headers(
            value.get('header', {}),
            allowed_hosts=(urlsplit(self.site['api']).netloc, urlsplit(url).netloc),
        )
        return url, cleaned
