"""Shared catalogue metadata adapter, not a cloud account or playback service.

Only public/author-authorised catalogue reads use service credentials. Playback
uses the local user's existing 115 share client, never another library owner's
personal file ID. Shared snapshots refresh off the interactive search path.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qs, unquote, urlsplit

from bobbi_core import juku_api
from bobbi_core.catalog_release import release_envelope
from bobbi_core.movie_years import accepted_years
from bobbi_core.release_identity import WEAK
from bobbi_core.search_completion import SearchCompletion, SearchResults

STATE = juku_api.STATE
SITE = 'Juku · 115分享'
DAY = 86400
FRESH = DAY
STALE = 7 * DAY
# Leave room inside the 512 MiB catalogue budget for SQLite's rollback journal
# (at most another database image) and indexes. No WAL or video cache is used.
MAX_DATABASE = 224 * 1024 * 1024
MAX_METADATA = 144 * 1024 * 1024
MAX_SELECTIONS = 48 * 1024 * 1024
MAX_MOVIES = 30000
MAX_LINKS = 250000
MAX_SOURCES = 1024
VIDEO = ('.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts', '.iso', '.webm')
_HEX = re.compile('[0-9a-f]{64}')
_NUMBER = re.compile('[0-9]{1,32}')
# Exact Juku 0.80 ARM64/x64 ExtractSubFidsFromUrl literal; see research receipt.
_SUBTITLE_PATTERN = r'(?i)[#?&/](?:sub_fid|sub_id|subtitle_id)=([^&#\s]+)'
# Go/RE2 \s omits vertical tab; Python's \s includes it even under re.ASCII.
_SUBTITLE_FIDS = re.compile(_SUBTITLE_PATTERN.replace(r'\s', r'\t\n\f\r '), re.ASCII)
_BAD_ESCAPE = re.compile(r'%(?![0-9a-fA-F]{2})')
_GO_SPACE = '\t\n\v\f\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'


def subtitle_fids(value):
    """Bounded numeric references from a validated share URL, not download URLs.

    Juku uses PathUnescape (preserves '+'), then commas/TrimSpace and stable
    deduplication. A malformed percent escape keeps that capture unchanged.
    Numeric validation and the 16-item limit are our stricter consumer boundary.
    """
    if not isinstance(value, str) or len(value) > 8192:
        return []
    result = []
    for match in _SUBTITLE_FIDS.finditer(value):
        captured = match[1]
        decoded = captured if _BAD_ESCAPE.search(captured) else unquote(captured)
        for item in decoded.split(','):
            item = item.strip(_GO_SPACE)
            if _NUMBER.fullmatch(item) and item not in result:
                result.append(item)
                if len(result) == 16:
                    return result
    return result


def _cancelled(value):
    return value.is_set if hasattr(value, 'is_set') else value or (lambda: False)


def _guard(deadline, cancelled):
    juku_api.guard(deadline, _cancelled(cancelled))


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _number(value, minimum=0):
    if isinstance(value, bool) or not _NUMBER.fullmatch(str(value)):
        raise ValueError('Juku numeric metadata required')
    result = int(value)
    if not minimum <= result < 2 ** 63:
        raise ValueError('Juku numeric metadata range')
    return result


def _text(value, maximum=1024):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or re.search(r'[\x00-\x1f\x7f]', value):
        raise ValueError('Juku bounded text required')
    return value


def media_key(tmdb, mode, season=0, episode=0):
    tmdb = _number(tmdb, 1)
    if mode not in ('movies', 'tv'):
        raise ValueError('Unsupported Juku media kind')
    return '{}:{}:{}:{}'.format(mode, tmdb, _number(season) if mode == 'tv' else 0,
                                _number(episode, 1) if mode == 'tv' else 0)


def _spec(value):
    if not isinstance(value, dict):
        raise ValueError('Juku media context required')
    mode, tmdb = value.get('mode'), _number(value.get('tmdb_id'), 1)
    season = _number(value.get('season', 0)) if mode == 'tv' else 0
    episode = _number(value.get('episode', 0), 1) if mode == 'tv' else 0
    key = media_key(tmdb, mode, season, episode)
    if value.get('media_key', key) != key:
        raise ValueError('Juku media context mismatch')
    aliases = list(dict.fromkeys(_text(alias, 512).strip() for alias in value.get('aliases', [])[:24]))
    aliases = [alias for alias in aliases if alias]
    order = value.get('release_order') or {}
    years = accepted_years(value.get('_movie_years'), tmdb, value.get('year'))
    result = dict(tmdb_id=tmdb, mode=mode, season=season, episode=episode, media_key=key,
        year=int(value.get('year') or 0), years=list(years), aliases=aliases,
        release_season=_number(order.get('season', value.get('release_season', season))) if mode == 'tv' else 0,
        release_episode=_number(order.get('episode', value.get('release_episode', episode)), 1) if mode == 'tv' else 0)
    return result


def share_url(value, password=''):
    """Parse only a 115 share reference; never accept a personal-download URL."""
    value = _text(value, 8192).strip()
    if re.match(r'^s[a-z0-9]+(?:[?#]|$)', value, re.I):
        value = 'https://115.com/s/' + value
    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or parts.hostname not in
            ('115.com', 'www.115.com', '115cdn.com', 'www.115cdn.com')
            or parts.username or parts.password or parts.port not in (None, 80, 443)):
        raise ValueError('Not a 115 share')
    match = re.fullmatch(r'/s/(s[a-z0-9]{5,40})/?', parts.path, re.I)
    if not match:
        raise ValueError('Not a 115 share')
    query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=32)
    fragment = parse_qs(parts.fragment, keep_blank_values=True, max_num_fields=32)
    code = (query.get('password') or query.get('receive_code') or [password or ''])[0]
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9]{0,12}', code):
        raise ValueError('Invalid 115 share password')
    parent = (fragment.get('cid') or [''])[0]
    if not parent:
        path = re.fullmatch(r'/share/\d{1,32}/(\d{1,32})/?', parts.fragment)
        parent = path[1] if path else ''
    fid = (fragment.get('fid') or [''])[0]
    if parent and not _NUMBER.fullmatch(parent) or fid and not _NUMBER.fullmatch(fid):
        raise ValueError('Invalid 115 share file reference')
    return dict(code=match[1].lower(), password=code), parent, fid


def _kind(value):
    number = _number(value)
    # Verified 0.80 details: animation films 千年女优/奇巧剧场版 are type 1,
    # TV animation 奇巧计程车 is type 3. Poster directory is NOT a type field.
    return 'movie' if number == 1 else 'tv' if number in (2, 3) else None


def _filename_episode(name):
    from bobbi_catalog.identity import declared_episodes
    declared = declared_episodes(name)
    if declared:
        if len(declared) != 1:
            raise ValueError('Multi-episode catalogue file')
        season, episode = next(iter(declared))
        return season, episode
    if re.search(r'(?:\s-\s*|\[)\d{1,3}(?:v\d+)?\s*[-~–+&]\s*\d{1,3}(?=[ ._\]\-]|$)', name, re.I):
        raise ValueError('Ambiguous catalogue episode')
    weak = [match for pattern in WEAK for match in pattern.finditer(name)
            if match.start() and not re.match(r'\.\d', name[match.end():])]
    if weak:
        numbers = {int(match['episode']) for match in weak}
        if len(numbers) != 1 or any(re.match(r'\s*[-~–+&]\s*\d', name[m.end():]) for m in weak):
            raise ValueError('Ambiguous catalogue episode')
        seasons = {int(m[1]) for m in re.finditer(r'(?i)(?<!\w)s(\d{1,2})(?!\w)', name)}
        if len(seasons) > 1:
            raise ValueError('Ambiguous catalogue season')
        return next(iter(seasons)) if seasons else None, next(iter(numbers))
    return None, None


def _row(work, link, origin, main=False):
    tmdb, kind = _number(work.get('tmdbId'), 1), _kind(work.get('typeId'))
    if not kind:
        return None
    share, url_parent, url_fid = share_url(link.get('url'), link.get('password', ''))
    fid = str(link.get('fid' if main else 'fileId') or url_fid)
    name = _text(link.get('file_name' if main else 'fileName'))
    size = _number(link.get('size' if main else 'fileSize'), 1)
    if not _NUMBER.fullmatch(fid) or url_fid and url_fid != fid:
        raise ValueError('Invalid shared file ID')
    if '/' in name or '\\' in name or not name.casefold().endswith(VIDEO):
        return None
    parent = str(link.get('pdir_fid' if main else 'parentFolderId') or url_parent or '')
    if parent and not _NUMBER.fullmatch(parent):
        raise ValueError('Invalid shared parent')
    season_known = False
    if kind == 'tv':
        named_season, named_episode = _filename_episode(name)
        season_known = not main and link.get('seasonNumber') not in (None, '')
        season = _number(link.get('seasonNumber')) if season_known else 0
        episode = _number(link.get('episodeNumber') or 0) if not main else 0
        if (named_episode is not None and episode and named_episode != episode
                or named_season is not None and season_known and named_season != season):
            raise ValueError('File and catalogue episodes conflict')
        episode = episode or named_episode or 0
        season = season if season_known else named_season or 0
        season_known = season_known or named_season is not None
        if not episode:
            return None
    else:
        # Movie catalog rows are already bound to the movie namespace. Weak
        # anime syntax would mistake [85.03GB], [5.1] and [12 Years a Slave]
        # for episode numbers; only an actual episode declaration excludes one.
        from bobbi_catalog.identity import declared_episodes
        if declared_episodes(name):
            return None
        season, episode = 0, 0
    sha1 = str(link.get('sha' if main else 'sha1') or '').lower()
    if sha1 and not re.fullmatch('[0-9a-f]{40}', sha1):
        sha1 = ''
    key = hashlib.sha256(_encode([share['code'], fid, size, name]).encode()).hexdigest()
    year = int(work.get('year') or 0)
    return dict(key=key, tmdb=tmdb, kind=kind, season=season, episode=episode,
        share=share, fid=fid, name=name, size=size, parent=parent, sha1=sha1, season_known=season_known,
        subtitle_fids=subtitle_fids(link.get('url')),
        origins=[origin], work_year=year, work_title=str(work.get('title') or '')[:512],
        work_titles=[work[key].strip() for key in ('title', 'originalName', 'subTitle')
                     if isinstance(work.get(key), str) and 0 < len(work[key].strip()) <= 512],
        main_id=str(work.get('id') if main else work.get('vodId') or ''))


def _unique(rows):
    result = {}
    for row in rows:
        previous = result.get(row['key'])
        if previous is None:
            result[row['key']] = deepcopy(row)
        elif all(previous.get(k) == row.get(k) for k in ('tmdb', 'kind', 'season', 'episode')):
            previous['origins'] = sorted(set(previous['origins']) | set(row['origins']))
            if not previous.get('parent'):
                previous['parent'] = row.get('parent', '')
            previous['subtitle_fids'] = list(dict.fromkeys(
                previous.get('subtitle_fids', []) + row.get('subtitle_fids', [])))[:16]
        else:
            # One physical file advertised as different works is not evidence.
            result[row['key']]['conflict'] = True
    return [row for row in result.values() if not row.get('conflict')]


class Cache:
    def __init__(self, state=STATE, deadline=None, cancelled=None, readonly=False):
        self.root = juku_api.state_path(state)
        if not readonly:
            self.root.mkdir(parents=True, exist_ok=True)
        self.deadline = time.monotonic() + 3 if deadline is None else deadline
        self.cancelled = _cancelled(cancelled)
        self.proof_check_done, self.denied_proofs = False, {}
        _guard(self.deadline, self.cancelled)
        path = self.root / 'catalog.sqlite3'
        self.db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro' if readonly else str(path),
                                  timeout=0, uri=readonly)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA busy_timeout=0')
            self.db.set_progress_handler(lambda: int(self.cancelled() or time.monotonic() >= self.deadline), 1000)
            if readonly:
                return
            page_size = self.db.execute('PRAGMA page_size').fetchone()[0]
            self.db.execute('PRAGMA max_page_count={}'.format(MAX_DATABASE // page_size))
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS raw_cache(key TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS libraries(code TEXT PRIMARY KEY, version TEXT, at REAL, count INTEGER, bytes INTEGER);
            CREATE TABLE IF NOT EXISTS shared_rows(library TEXT, key TEXT, tmdb INTEGER, kind TEXT,
                season INTEGER, episode INTEGER, payload TEXT, PRIMARY KEY(library,key));
            CREATE INDEX IF NOT EXISTS shared_media ON shared_rows(tmdb,kind,season,episode);
            CREATE TABLE IF NOT EXISTS selections(key TEXT, media TEXT, at REAL, payload TEXT,
                checked_at REAL DEFAULT 0, checked_account TEXT DEFAULT '', PRIMARY KEY(key,media));
            CREATE TABLE IF NOT EXISTS maintenance(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS library_visibility(code TEXT PRIMARY KEY, revoked INTEGER, reason TEXT);
            CREATE TABLE IF NOT EXISTS snapshot_rows(key TEXT PRIMARY KEY, tmdb INTEGER, kind TEXT,
                season INTEGER, episode INTEGER, payload TEXT, conflict INTEGER DEFAULT 0);
            ''')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def get_raw(self, key, age=FRESH):
        _guard(self.deadline, self.cancelled)
        row = self.db.execute('SELECT payload FROM raw_cache WHERE key=? AND at>?', (key, time.time()-age)).fetchone()
        return json.loads(row[0]) if row else None

    def _metadata_bytes(self):
        return (self.db.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM raw_cache').fetchone()[0]
                + self.db.execute('SELECT COALESCE(SUM(bytes),0) FROM libraries').fetchone()[0])

    def _room(self, incoming, preserve=None):
        if incoming > MAX_METADATA:
            raise ValueError('Juku metadata quota')
        self.db.execute('DELETE FROM raw_cache WHERE at<?', (time.time()-STALE,))
        while self._metadata_bytes() + incoming > MAX_METADATA:
            victim = self.db.execute('SELECT key FROM raw_cache ORDER BY at LIMIT 1').fetchone()
            if victim:
                self.db.execute('DELETE FROM raw_cache WHERE key=?', (victim[0],))
                continue
            victim = self.db.execute('SELECT code FROM libraries WHERE code!=? ORDER BY at LIMIT 1', (preserve or '',)).fetchone()
            if not victim:
                raise ValueError('Juku metadata quota')
            self.db.execute('DELETE FROM shared_rows WHERE library=?', (victim[0],))
            self.db.execute('DELETE FROM libraries WHERE code=?', (victim[0],))

    def put_raw(self, key, value):
        raw = _encode(value)
        with self.db:
            self.db.execute('DELETE FROM raw_cache WHERE key=?', (key,))
            self._room(len(raw.encode()))
            self.db.execute('INSERT INTO raw_cache VALUES(?,?,?)', (key, time.time(), raw))

    def local(self, spec):
        rows = self.db.execute('''SELECT s.payload,l.at FROM shared_rows s JOIN libraries l ON s.library=l.code
            LEFT JOIN library_visibility v ON v.code=l.code
            WHERE s.tmdb=? AND s.kind=? AND s.episode=? AND s.season IN (?,0)
                AND COALESCE(v.revoked,0)=0 ORDER BY s.library,s.key LIMIT 4096''',
            (spec['tmdb_id'], 'movie' if spec['mode'] == 'movies' else 'tv',
             spec['release_episode'], spec['release_season']))
        result = []
        for row in rows:
            value = json.loads(row[0])
            value['_snapshot_age'] = max(0, int(time.time()-row[1]))
            value['_snapshot_stale'] = value['_snapshot_age'] > FRESH
            result.append(value)
        return result

    def remember(self, rows, spec):
        now = time.time()
        with self.db:
            for row in rows:
                _guard(self.deadline, self.cancelled)
                saved = dict(row, spec=spec)
                saved.pop('_verified', None)
                self.db.execute('''INSERT INTO selections(key,media,at,payload) VALUES(?,?,?,?)
                    ON CONFLICT(key,media) DO UPDATE SET at=excluded.at,payload=excluded.payload''',
                    (row['key'], spec['media_key'], now, _encode(saved)))
            size = self.db.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM selections').fetchone()[0]
            if size > MAX_SELECTIONS:
                # Selection proofs never participate in raw-metadata eviction.
                # Retain recently resolved/current locators while retiring old cards.
                self.db.execute('DELETE FROM selections WHERE at<? AND checked_at<?', (now-STALE, now-STALE))
                size = self.db.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM selections').fetchone()[0]
                if size > MAX_SELECTIONS:
                    raise ValueError('Juku selection quota; retain active bindings')

    def select(self, key, media):
        value = self.db.execute('SELECT * FROM selections WHERE key=? AND media=?', (key, media)).fetchone()
        if not value:
            raise ValueError('Juku selection expired; refresh sources')
        row = json.loads(value['payload'])
        origins = row.get('origins') or []
        if origins and all(self.db.execute('SELECT revoked FROM library_visibility WHERE code=? AND revoked=1',
                (origin[7:] if origin.startswith('shared:') else origin,)).fetchone() for origin in origins):
            raise ValueError('Juku selected catalogue reference withdrawn')
        row['_checked_at'], row['_checked_account'] = value['checked_at'], value['checked_account']
        return row

    def invalidate_proof(self, row, media):
        """CAS only this exact grant's old proof; retain the library and card."""
        current = self.db.execute('SELECT payload FROM selections WHERE key=? AND media=?',
                                  (row['key'], media)).fetchone()
        original = {key: value for key, value in row.items()
                    if key not in ('_checked_at', '_checked_account')}
        if current is None or json.loads(current[0]) != original:
            return  # A changed tuple is not the failed grant's old evidence.
        with self.db:
            self.db.execute('''UPDATE selections SET checked_at=0,checked_account=''
                WHERE key=? AND media=? AND payload=? AND checked_at=? AND checked_account=?''',
                (row['key'], media, current[0], row['_checked_at'], row['_checked_account']))

    def replace_library(self, code, version, rows):
        payloads = [_encode(row) for row in rows]
        size = sum(len(raw.encode()) for raw in payloads)
        with self.db:
            self.db.execute('DELETE FROM shared_rows WHERE library=?', (code,))
            self.db.execute('DELETE FROM libraries WHERE code=?', (code,))
            self._room(size, preserve=code)
            self.db.executemany('INSERT INTO shared_rows VALUES(?,?,?,?,?,?,?)',
                [(code, row['key'], row['tmdb'], row['kind'], row['season'], row['episode'], raw)
                 for row, raw in zip(rows, payloads)])
            self.db.execute('INSERT INTO libraries VALUES(?,?,?,?,?)', (code, str(version), time.time(), len(rows), size))
            self.db.execute('DELETE FROM library_visibility WHERE code=?', (code,))


@contextmanager
def _cache(state, deadline=None, cancelled=None, readonly=False):
    cache = Cache(state, deadline, cancelled, readonly)
    try:
        yield cache
    finally:
        cache.close()


def _validate(path, value):
    """Validate a successful endpoint result before it can replace cached data."""
    if path == '/videos/search':
        if (not isinstance(value, dict) or not isinstance(value.get('items'), list)
                or len(value['items']) > 100 or any(not isinstance(row, dict)
                    or not _NUMBER.fullmatch(str(row.get('id', ''))) for row in value['items'])):
            raise ValueError('Juku search shape')
        pagination = value.get('pagination')
        if pagination is not None and not isinstance(pagination, dict):
            raise ValueError('Juku pagination shape')
        if isinstance(pagination, dict) and 'total' in pagination:
            _number(pagination['total'])
        if (isinstance(pagination, dict) and not value['items']
                and _number(pagination.get('total', 0)) > 0):
            raise ValueError('Incomplete Juku first search page')
    elif path.endswith('/cloud-files'):
        if (not isinstance(value, list) or len(value) > 30000
                or any(not isinstance(row, dict) for row in value)):
            raise ValueError('Juku cloud-file shape')
        for row in value:
            if row.get('cloudid') == 7:
                _number(row.get('vod_url_id'), 1)
                if not _NUMBER.fullmatch(str(row.get('fid', ''))) or int(row['fid']) == 0:
                    raise ValueError('Juku file ID required')
                _number(row.get('size'), 1)
                _text(row.get('file_name'))
    elif re.fullmatch('/videos/[0-9]+', path):
        if not isinstance(value, dict) or str(value.get('id')) != path.rsplit('/', 1)[1]:
            raise ValueError('Juku detail identity')
        _number(value.get('tmdbId'), 1)
        _number(value.get('typeId'), 1)
        pans = value.get('panList') or {}
        if not isinstance(pans, dict) or not isinstance(pans.get('7', []), list):
            raise ValueError('Juku detail share shape')
        if len(pans.get('7', [])) > 1024:
            raise ValueError('Juku detail share budget')
        for pan in pans.get('7', []):
            if not isinstance(pan, dict):
                raise ValueError('Juku detail share shape')
            _number(pan.get('id'), 1)
            if pan.get('cloudid') == 7:
                share_url(pan.get('url'))
    else:
        raise ValueError('Unsupported Juku cache endpoint')
    return value


def _fetch(cache, client, path, params, deadline, cancelled, diagnostic):
    _guard(deadline, cancelled)
    key = hashlib.sha256(_encode([path, params]).encode()).hexdigest()
    # Episodic cloud lists change while a season is airing. A successful old
    # list remains a failure fallback, not a 24-hour veto on newly released files.
    fresh = 300 if path.endswith('/cloud-files') else 60 if path == '/videos/search' else FRESH
    cached = cache.get_raw(key, fresh)
    if cached is not None:
        return _validate(path, cached)
    try:
        value = client.get(path, params, deadline)
        _guard(deadline, cancelled)
        _validate(path, value)
        cache.put_raw(key, value)
        main_id = re.fullmatch(r'/videos/(\d+)(?:/cloud-files)?', path)
        if main_id:
            with cache.db:
                cache.db.execute('DELETE FROM library_visibility WHERE code=?', ('main:' + main_id[1],))
        return value
    except (juku_api.JukuError, ValueError, OSError, sqlite3.Error) as error:
        if _cancelled(cancelled)() or time.monotonic() >= cache.deadline:
            raise
        if getattr(error, 'code', '') in ('HTTP_403', 'HTTP_404', 'HTTP_410'):
            with cache.db:
                cache.db.execute('DELETE FROM raw_cache WHERE key=?', (key,))
                main_id = re.fullmatch(r'/videos/(\d+)(?:/cloud-files)?', path)
                if main_id:
                    cache.db.execute('INSERT OR REPLACE INTO library_visibility VALUES(?,1,?)',
                                     ('main:' + main_id[1], error.code))
            raise  # Authoritative withdrawal is not a stale-success fallback.
        stale = cache.get_raw(key, STALE)
        if stale is not None:
            diagnostic(dict(stage='catalog', state='STALE_CACHE', reason=type(error).__name__))
            return _validate(path, stale)
        raise


def _main_rows(detail, cloud, deadline=None, cancelled=None):
    if not isinstance(detail, dict) or not isinstance(cloud, list) or len(cloud) > 30000:
        raise ValueError('Juku main catalogue shape')
    pans = (detail.get('panList') or {}).get('7', [])
    if not isinstance(pans, list) or len(pans) > 1024:
        raise ValueError('Juku 115 share budget')
    shares = {str(row.get('id')): row for row in pans if isinstance(row, dict) and row.get('cloudid') == 7}
    result = []
    for index, file in enumerate(cloud):
        if deadline is not None and not index % 64:
            _guard(deadline, cancelled)
        try:
            share = shares.get(str(file.get('vod_url_id')))
            if file.get('cloudid') != 7 or not share:
                continue
            row = _row(detail, dict(file, url=share['url']), 'main:' + str(detail['id']), main=True)
            if row:
                result.append(row)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return _unique(result)


def _bound(row, spec):
    if row['tmdb'] != spec['tmdb_id'] or row['kind'] != ('movie' if spec['mode'] == 'movies' else 'tv'):
        return None
    from bobbi_catalog.identity import same_title
    titles = row.get('work_titles') or [row.get('work_title', '')]
    if not any(same_title(title, spec['aliases']) for title in titles):
        return None  # Catalog ID and a known work title must corroborate.
    if spec['mode'] == 'movies':
        years = spec['years'] or [spec['year']]
        if row['work_year'] and row['work_year'] not in years:
            return None
        names = {int(year) for year in re.findall(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)', row['name'])}
        if names and years and not names.intersection(years):
            return None  # Same-title remake inside a broad share is not this film.
    else:
        rs, release_episode = spec['release_season'], spec['release_episode']
        # Unnumbered seasons are only useful for an explicitly first-season
        # request. No absolute/cour offsets are guessed from a release name.
        row_season = row['season'] if row.get('season_known', bool(row['season'])) else 1
        if row['episode'] != release_episode or row_season != rs:
            return None
    result = deepcopy(row)
    result.update(season=spec['season'], episode=spec['episode'], spec=spec,
                  release_season=spec['release_season'], release_episode=spec['release_episode'])
    return result


def _account_scope(client=None, timeout=.2):
    try:
        if client is None:
            from bobbi_platform.runtime import call
            scope = call('account_status', {}, timeout=timeout)
        else:
            scope = client.account_scope
        if (not isinstance(scope, dict) or scope.get('authenticated') is not True
                or not isinstance(scope.get('account_id'), str) or not scope['account_id']
                or type(scope.get('epoch')) is not int or scope['epoch'] < 0):
            return None
        return scope
    except (ImportError, OSError, ValueError, RuntimeError, AttributeError):
        return None


def _account(client=None):
    scope = _account_scope(client)
    return hashlib.sha256(_encode([scope['account_id'], scope['epoch']]).encode()).hexdigest() if scope else ''


def _known_failures(cache, rows, spec, scope):
    """One read-only bounded batch; absence/failure never revokes old success."""
    from bobbi_core.share_failure import MAX_PROOFS, tuple_hash, proofs
    if cache.proof_check_done or not scope:
        return
    candidates = []
    for row in rows:
        if row['_verified'] and len(candidates) < MAX_PROOFS:
            old = cache.select(row['key'], spec['media_key'])
            stamp = old['_checked_at']
            if type(stamp) in (int, float) and math.isfinite(stamp) and stamp > 0:
                candidates.append(dict(tuple_sha256=tuple_hash(dict(locator='am6bjuku://'+row['key'],
                    guid='juku:'+row['key'], title=row['name'], size=row['size'], media=spec['media_key'])),
                    checked_at=stamp))
    if not candidates:
        return
    cache.proof_check_done = True
    remaining = cache.deadline-time.monotonic()
    if remaining <= 0 or cache.cancelled():
        return
    try:
        from bobbi_platform.runtime import call
        submitted = proofs(candidates)
        result = call('share_known_failures', dict(account=scope, proofs=candidates), timeout=min(.2, remaining))
        if (type(result) is not dict or set(result) != {'account', 'denied'}
                or result['account'] != scope or type(result['denied']) is not list):
            return
        denied = proofs(result['denied']) if result['denied'] else {}
        if any(key not in submitted or submitted[key] != stamp for key, stamp in denied.items()):
            return
        cache.denied_proofs = {key: (stamp, _account_fingerprint(scope)) for key, stamp in denied.items()}
    except (ImportError, OSError, ValueError, RuntimeError, TypeError):
        pass  # Unknown is not a negative proof and never deletes a candidate.


def _account_fingerprint(scope):
    return hashlib.sha256(_encode([scope['account_id'], scope['epoch']]).encode()).hexdigest()


def verified(row):
    """True only for a recent local-user 115 tuple check, not Juku metadata."""
    return isinstance(row, dict) and row.get('_verified') is True


def _soft_fetch(cache, client, path, params, deadline, cancelled, diagnostic):
    try:
        return _fetch(cache, client, path, params, deadline, cancelled, diagnostic)
    except (juku_api.JukuError, ValueError, OSError, sqlite3.Error, TypeError) as error:
        diagnostic(dict(stage='main', state='UNAVAILABLE', reason=type(error).__name__))
        return None


def _finish(cache, candidates, spec):
    _guard(cache.deadline, cache.cancelled)
    rows = [bound for row in _unique(candidates) if (bound := _bound(row, spec)) is not None][:MAX_SOURCES]
    cache.remember(rows, spec)
    remaining = cache.deadline-time.monotonic()
    scope = _account_scope(timeout=min(.2, remaining)) if remaining > 0 else None
    account = _account_fingerprint(scope) if scope else ''
    for row in rows:
        old = cache.select(row['key'], spec['media_key'])
        row['_verified'] = bool(account and old['_checked_account'] == account
                                and type(old['_checked_at']) in (int, float)
                                and math.isfinite(old['_checked_at'])
                                and old['_checked_at'] > time.time()-DAY)
    _known_failures(cache, rows, spec, scope)
    from bobbi_core.share_failure import tuple_hash
    for row in rows:
        old = cache.select(row['key'], spec['media_key'])
        key = tuple_hash(dict(locator='am6bjuku://'+row['key'], guid='juku:'+row['key'],
            title=row['name'], size=row['size'], media=spec['media_key']))
        if cache.denied_proofs.get(key) == (old['_checked_at'], old['_checked_account']):
            row['_verified'] = False
    _guard(cache.deadline, cache.cancelled)
    return rows


def search(spec, deadline, cancelled, state=STATE, client=None, diagnostic=None, publish=None):
    spec = _spec(spec)
    report = diagnostic or (lambda event: None)
    counts = dict(succeeded=0, failed=0, skipped=0, timed_out=0)
    stale, truncated, snapshot_age = 0, 0, 0
    def receipt(pending=False):
        values = dict(counts)
        if pending:
            values['skipped'] += 1
        return SearchCompletion(planned=sum(values.values()), stale=stale,
                                truncated=truncated, snapshot_age=snapshot_age, **values)
    with _cache(state, deadline, cancelled) as cache:
        candidates = cache.local(spec)
        directory = cache.db.execute("SELECT value FROM maintenance WHERE key='directory'").fetchone()
        if directory and json.loads(directory[0]).get('truncated'):
            truncated += 1
        if len(candidates) >= 4096:
            truncated += 1
        if candidates:
            counts['succeeded'] += 1
            snapshot_age = max(row.get('_snapshot_age', 0) for row in candidates)
            stale = int(any(row.get('_snapshot_stale') for row in candidates))
            if publish is not None:
                # Same stable keys and media binding as final delivery. This
                # is an append, not a UI refresh or a completed cache entry.
                publish(SearchResults(_finish(cache, candidates, spec), receipt(pending=True)))
        _guard(deadline, cancelled)
        client = client or juku_api.Client(state=state, cancelled=_cancelled(cancelled))
        details, searched = [], set()
        # Reserve a small, bounded settle budget for persisted local results.
        # Never remove the outer deadline or SQLite interruption handler.
        main_deadline = deadline - 0.5
        def fetch(path, params):
            nonlocal stale, truncated
            events = []
            def observe(event):
                events.append(event)
                report(event)
            try:
                value = _fetch(cache, client, path, params, main_deadline, cancelled, observe)
            except (juku_api.JukuError, ValueError, OSError, sqlite3.Error, TypeError) as error:
                code = getattr(error, 'code', type(error).__name__)
                counts['timed_out' if code in ('DEADLINE', 'CANCELLED') else 'failed'] += 1
                report(dict(stage='main', state='UNAVAILABLE', reason=code))
                return None
            if any(event.get('state') == 'STALE_CACHE' for event in events):
                counts['failed'] += 1
                counts['succeeded'] += 1  # Separate successful fallback, not network success.
                stale += 1
            else:
                counts['succeeded'] += 1
            if path == '/videos/search':
                pagination = value.get('pagination') or {}
                total = pagination.get('total') if isinstance(pagination, dict) else None
                if (len(value['items']) > 20 or (total is not None and _number(total) > len(value['items']))
                        or (total is None and len(value['items']) >= 20)):
                    truncated += 1
            return value
        if len(spec['aliases']) > 2:
            truncated += 1
        for alias in spec['aliases'][:2]:
            if _cancelled(cancelled)() or time.monotonic() >= main_deadline:
                counts['timed_out'] += 1
                break
            page = fetch('/videos/search', dict(q=alias, page=1, pageSize=20))
            if page is None:
                continue
            for item in page['items'][:20]:
                identifier = str(item['id'])
                if identifier in searched or len(searched) >= 6:
                    if identifier not in searched:
                        truncated += 1
                    continue
                if _cancelled(cancelled)() or time.monotonic() >= main_deadline:
                    counts['timed_out'] += 1
                    break
                # Search names/year only rank discovery. Search years are not
                # authoritative: IDs and release years are verified in detail.
                searched.add(identifier)
                detail = fetch('/videos/' + identifier, {})
                if (detail is not None and str(detail.get('tmdbId')) == str(spec['tmdb_id'])
                        and _kind(detail.get('typeId')) == ('movie' if spec['mode'] == 'movies' else 'tv')):
                    details.append(detail)
                    if len(details) == 2:
                        break
            if details:
                break
        for detail in details[:2]:
            if _cancelled(cancelled)() or time.monotonic() >= main_deadline:
                counts['timed_out'] += 1
                break
            cloud = fetch('/videos/' + str(detail['id']) + '/cloud-files', dict(cloudid=7))
            if cloud is not None:
                candidates.extend(_main_rows(detail, cloud, deadline, cancelled))
        rows = _finish(cache, candidates, spec)
        if len(rows) >= MAX_SOURCES:
            truncated += 1
        return SearchResults(rows, receipt())


def fields(row):
    return dict(type='Direct', title=row['name'], size=row['size'], indexer=SITE,
                guid='juku:' + row['key'], url='am6bjuku://' + row['key'])


def selected(locator, guid, title, size, media, state=STATE, deadline=None, cancelled=None):
    if not isinstance(guid, str) or not guid.startswith('juku:') or not _HEX.fullmatch(guid[5:]):
        raise ValueError('Invalid Juku selection')
    key = guid[5:]
    if locator != 'am6bjuku://' + key:
        raise ValueError('Invalid Juku locator')
    with _cache(state, deadline, cancelled, readonly=True) as cache:
        row = cache.select(key, media)
    if row['name'] != title or type(size) is not int or row['size'] != size:
        raise ValueError('Juku selected file changed')
    return row


def resolve(locator, guid, title, size, media, state=STATE, deadline=None, cancelled=None, client=None):
    deadline = time.monotonic()+8 if deadline is None else deadline
    _guard(deadline, cancelled)
    row = selected(locator, guid, title, size, media, state, deadline, cancelled)
    if client is None:
        from bobbi_catalog.api import Client
        client = Client()
    from bobbi_catalog.api import ShareError
    from bobbi_core.share_failure import PERMANENT
    try:
        url = client.resolve(row['share'], row, deadline)
    except ShareError as error:
        if error.code in PERMANENT and row['_checked_account'] == _account(client):
            error.checked_proof = dict(checked_at=row['_checked_at'], checked_account=row['_checked_account'])
            try:
                with _cache(state, deadline, cancelled) as cache:
                    cache.invalidate_proof(row, media)
            except (OSError, sqlite3.Error, juku_api.JukuError):
                error.invalidation_failed = True
        raise
    _guard(deadline, cancelled)
    try:
        with _cache(state, deadline, cancelled) as cache:
            with cache.db:
                cache.db.execute('UPDATE selections SET checked_at=?,checked_account=? WHERE key=? AND media=?',
                                 (time.time(), _account(client), row['key'], media))
    except (OSError, sqlite3.Error):
        # Evidence only affects BT-card suppression. A busy metadata writer
        # cannot revoke the already verified official 115 download response.
        pass
    return url


def next_file(current, identity, cancelled, deadline, state=STATE, client=None):
    tmdb, season, episode = identity
    pointer = current.get('direct_source') or {}
    try:
        anchor = selected(pointer['locator'], pointer['guid'], pointer['title'], pointer['size'],
                          media_key(tmdb, 'tv', season, episode), state, deadline, cancelled)
        if not anchor.get('parent'):
            return None, 'CURRENT_PARENT_UNKNOWN'
        spec = _spec(dict(anchor['spec'], season=season, episode=episode+1,
                    media_key=media_key(tmdb, 'tv', season, episode+1),
                    release_episode=anchor['spec']['release_episode']+1))
        envelope = release_envelope(anchor['name'], anchor['spec']['release_season'], anchor['spec']['release_episode'])
        if envelope is None:
            return None, 'RELEASE_ENVELOPE_UNPROVEN'
        with _cache(state, deadline, cancelled) as cache:
            candidates = cache.local(spec)
            main_id = anchor.get('main_id', '')
            if _NUMBER.fullmatch(main_id) and time.monotonic() < deadline - 0.5:
                # Supplement only the current work's exact known Juku ID.
                # No global/title search, share enumeration or cloud writes.
                client = client or juku_api.Client(state=state, cancelled=_cancelled(cancelled))
                detail = _soft_fetch(cache, client, '/videos/' + main_id, {}, deadline-0.5,
                                     cancelled, lambda event: None)
                if (detail is not None and str(detail.get('tmdbId')) == str(tmdb)
                        and _kind(detail.get('typeId')) == 'tv'):
                    cloud = _soft_fetch(cache, client, '/videos/' + main_id + '/cloud-files',
                                        dict(cloudid=7), deadline-0.5, cancelled, lambda event: None)
                    if cloud is not None:
                        candidates.extend(_main_rows(detail, cloud, deadline, cancelled))
            rows = [bound for row in _unique(candidates) if (bound := _bound(row, spec)) is not None]
            matches = [row for row in rows if row['parent'] == anchor['parent']
                and row['share']['code'] == anchor['share']['code']
                and release_envelope(row['name'], spec['release_season'], spec['release_episode']) == envelope]
            if len(matches) != 1:
                return None, 'NEXT_MISSING_OR_AMBIGUOUS'
            cache.remember(matches, spec)
            _guard(deadline, cancelled)
            return fields(matches[0]), 'INDEXED_DIRECT_SAME_RELEASE'
    except (ValueError, OSError, juku_api.JukuError, sqlite3.Error, KeyError, TypeError):
        return None, 'DIRECT_CATALOG_UNAVAILABLE'


def _directory_reference(link):
    """A library's folder/share bookmark is not a malformed playable file."""
    name = link.get('fileName')
    return (link.get('linkType') == 'pan' and (name is None or isinstance(name, str) and not name.strip())
            and link.get('fileSize') in (None, '', 0, '0'))


def refresh_one(state=STATE, deadline=None, cancelled=None, client=None):
    """Advance one bounded idle phase; no video/115/private-library IO."""
    from bobbi_core.juku_refresh import refresh
    return refresh(state, deadline, cancelled, client)
